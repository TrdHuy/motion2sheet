from __future__ import annotations

import secrets
import shutil
import time
import uuid
from pathlib import Path

from .artifacts import ArtifactRegistry, owned_file
from .contracts import (
    AgentRunRequest,
    GenerationRequest,
    GenerationResult,
    HarnessError,
    MemorySecurityError,
    OutputContractError,
    SkillManifest,
)
from .events import EventProcessor, RunEventBus, RunState, initial_run_state
from .history import load_resume_history
from .memory import ProviderMemoryBank
from .providers.base import AgentProvider, AgentSession
from .redaction import SecretRedactor, write_json
from .report.server import ReportServer, materialize_static_report
from .report.store import ProcessedEventStore
from .session import LivenessTicker, ProviderEventPump
from .skill import DEFAULT_SKILL, load_skill
from .workspace import RunWorkspace, create_workspace, preflight_output


class ActiveRun:
    def __init__(
        self,
        *,
        request: GenerationRequest,
        parent_run_id: str | None,
        workspace: RunWorkspace,
        output: Path,
        session: AgentSession,
        pump: ProviderEventPump,
        liveness: LivenessTicker,
        bus: RunEventBus,
        processor: EventProcessor,
        state: RunState,
        store: ProcessedEventStore,
        server: ReportServer,
        redactor: SecretRedactor,
        memory_bank: ProviderMemoryBank,
        skill_manifest: SkillManifest,
    ) -> None:
        self.request = request
        self.parent_run_id = parent_run_id
        self.workspace = workspace
        self.output = output
        self.session = session
        self.pump = pump
        self.liveness = liveness
        self.bus = bus
        self.processor = processor
        self.state = state
        self.store = store
        self.server = server
        self.redactor = redactor
        self.memory_bank = memory_bank
        self.skill_manifest = skill_manifest

    @property
    def run_id(self) -> str:
        return self.bus.run_id

    @property
    def report_url(self) -> str:
        return self.server.report_url

    def close_report_server(self) -> None:
        """Stop a retained terminal report server; safe to call more than once."""

        self.server.stop()

    def wait(self) -> GenerationResult:
        failure: HarnessError | None = None
        result: GenerationResult | None = None
        try:
            exit_result = self.session.wait()
            self.liveness.stop()
            if not self.pump.join():
                raise HarnessError("provider event streams did not close after process exit")
            self.bus.submit_harness(
                "runtime.process.exited",
                {"exitCode": exit_result.exit_code, "endedAt": exit_result.ended_at},
            )
            self.processor.drain()
            if self.processor.error is not None:
                raise HarnessError(f"event processor failed: {self.processor.error}")
            snapshot = self.state.snapshot()
            if snapshot["failure"] is not None:
                raise HarnessError(f"agent reported failure: {snapshot['failure']}")
            if exit_result.exit_code != 0:
                raise HarnessError(f"agent process exited with code {exit_result.exit_code}")
            completion = snapshot.get("completion")
            if not isinstance(completion, dict):
                raise OutputContractError("agent exited successfully without an agent.completed event")
            outputs = completion.get("outputs")
            if not isinstance(outputs, dict):
                raise OutputContractError("agent.completed must declare an outputs object")
            archive = self._collect_outputs(outputs)
            self._persist_memory(snapshot)
            published = self._publish(archive)
            self.bus.submit_harness("run.completed", {"output": str(self.output)})
            self.processor.drain()
            result = GenerationResult(
                run_id=self.run_id,
                status="completed",
                output=self.output,
                animation_path=published["animation"],
                metadata_path=published["metadata"],
                preview_path=published["preview"],
                workspace=self.workspace.root,
                report_path=self.workspace.report / "index.html",
                report_url=self.report_url,
                parent_run_id=self.parent_run_id,
            )
        except Exception as exc:
            failure = exc if isinstance(exc, HarnessError) else HarnessError(str(exc))
            self.bus.submit_harness("run.failed", {"message": self.redactor.text(str(exc))})
            self.processor.drain()
        finally:
            self.liveness.stop()
            self.redactor.scrub_tree(self.workspace.root)
            self.server.enter_terminal_mode()
            self.processor.stop()
            materialize_static_report(
                self.workspace.report,
                state=self.state.snapshot(),
                events=self.store.snapshot(),
                redactor=self.redactor,
            )
            self.redactor.scrub_tree(self.workspace.root)
            if not self.request.keep_report_server:
                self.close_report_server()
        if failure is not None:
            raise failure
        assert result is not None
        return result

    def _persist_memory(self, snapshot: dict[str, object]) -> None:
        proposal = snapshot.get("memoryProposal")
        if proposal is None:
            return
        declared = proposal.get("path") if isinstance(proposal, dict) else None
        try:
            if not isinstance(declared, str):
                raise HarnessError("memory proposal must declare a path")
            result = self.memory_bank.persist_proposal(
                declared_path=declared,
                agent_workspace=self.workspace.agent,
                run_id=self.run_id,
                manifest=self.skill_manifest,
                provider=self.request.provider,
                redactor=self.redactor,
                reported_files=[
                    item
                    for bucket in (snapshot.get("evidence"), snapshot.get("artifacts"))
                    if isinstance(bucket, list)
                    for item in bucket
                    if isinstance(item, dict)
                ],
            )
        except MemorySecurityError:
            raise
        except Exception as exc:
            self.bus.submit_harness(
                "memory.rejected", {"message": self.redactor.text(str(exc))}
            )
        else:
            self.bus.submit_harness("memory.persisted", result)
        self.processor.drain()
        if self.processor.error is not None:
            raise HarnessError(f"event processor failed: {self.processor.error}")

    def _collect_outputs(self, outputs: dict[str, object]) -> dict[str, Path]:
        names = {
            "animation": "animation.json",
            "metadata": "metadata.json",
            "preview": "preview.gif",
        }
        sources: dict[str, Path] = {}
        for key, filename in names.items():
            declared = outputs.get(key)
            if not isinstance(declared, str):
                raise OutputContractError(f"agent output declaration is missing {key}")
            try:
                source = owned_file(self.workspace.agent, declared, self.redactor)
            except HarnessError as exc:
                raise OutputContractError(str(exc)) from exc
            if source.stat().st_size == 0:
                raise OutputContractError(f"agent output is empty: {declared}")
            sources[key] = source
        archive: dict[str, Path] = {}
        for key, filename in names.items():
            target = self.workspace.final / filename
            shutil.copyfile(sources[key], target)
            archive[key] = target
        return archive

    def _publish(self, archive: dict[str, Path]) -> dict[str, Path]:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        staging = self.output.parent / f".{self.output.name}.sdar-{self.run_id}"
        if staging.exists():
            raise HarnessError(f"output staging path already exists: {staging}")
        staging.mkdir()
        names = {
            "animation": "animation.json",
            "metadata": "metadata.json",
            "preview": "preview.gif",
        }
        try:
            for key, filename in names.items():
                shutil.copyfile(archive[key], staging / filename)
            if self.output.exists():
                self.output.rmdir()
            staging.replace(self.output)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        return {key: self.output / filename for key, filename in names.items()}


class AnimationGenerationOrchestrator:
    """SDAR supervisor; it intentionally contains no animation-domain workflow."""

    def __init__(
        self,
        *,
        provider: AgentProvider,
        repo_root: Path,
        workspace_root: Path,
        processing_hook=None,
        liveness_idle_seconds: float = 15.0,
        liveness_stalled_seconds: float = 60.0,
        liveness_tick_seconds: float = 1.0,
        memory_root: Path | None = None,
    ) -> None:
        self.provider = provider
        self.repo_root = Path(repo_root).resolve()
        self.workspace_root = Path(workspace_root).resolve()
        self.processing_hook = processing_hook
        self.liveness_idle_seconds = liveness_idle_seconds
        self.liveness_stalled_seconds = liveness_stalled_seconds
        self.liveness_tick_seconds = liveness_tick_seconds
        self.memory_root = (
            Path(memory_root).resolve()
            if memory_root is not None
            else self.workspace_root.parent / "sdar-memory"
        )
        self.memory_bank = ProviderMemoryBank(self.memory_root)

    def start(self, request: GenerationRequest) -> ActiveRun:
        # All configuration and resume validation happens before launching an agent.
        skill_directory = (
            request.skill_directory.resolve()
            if request.skill_directory is not None
            else (self.repo_root / DEFAULT_SKILL).resolve()
        )
        skill = load_skill(skill_directory)
        output = preflight_output(request.output)
        history = load_resume_history(self.workspace_root, request.resume_run_id)
        memory = self.memory_bank.load(skill.manifest, request.provider)
        run_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        redactor = SecretRedactor(token)
        workspace = create_workspace(self.workspace_root, run_id)
        bus = RunEventBus(run_id)
        store = ProcessedEventStore()
        state = RunState(
            initial_run_state(
                run_id=run_id,
                parent_run_id=request.resume_run_id,
                prompt=request.prompt,
                provider=request.provider,
                manifest=skill.manifest,
            ),
            idle_seconds=self.liveness_idle_seconds,
            stalled_seconds=self.liveness_stalled_seconds,
        )
        registry = ArtifactRegistry(
            agent_workspace=workspace.agent,
            iterations=workspace.iterations,
            redactor=redactor,
        )
        processor = EventProcessor(
            bus=bus,
            state=state,
            registry=registry,
            store=store,
            run_path=workspace.root / "run.json",
            history_path=workspace.root / "history.json",
            events_path=workspace.logs / "events.jsonl",
            provider_events_path=workspace.logs / "provider-events.jsonl",
            stdout_path=workspace.logs / "stdout.log",
            stderr_path=workspace.logs / "stderr.log",
            redactor=redactor,
            processing_hook=self.processing_hook,
        )
        server = ReportServer(
            run_id=run_id,
            token=token,
            bus=bus,
            state=state,
            store=store,
            port=request.report_port,
        )
        write_json(
            workspace.root / "request.json",
            {
                "runId": run_id,
                "parentRunId": request.resume_run_id,
                "prompt": request.prompt,
                "provider": request.provider,
                "output": str(output),
                "skill": str(skill.directory),
                "skillManifest": skill.manifest.to_dict(),
                "history": history,
                "memory": memory,
            },
            redactor,
        )
        processor.start()
        server.start()
        bus.submit_harness("run.started", {"reportUrl": server.report_url})
        bus.submit_harness(
            "memory.loaded",
            {
                key: memory[key]
                for key in (
                    "skillId",
                    "skillVersion",
                    "provider",
                    "archiveEntryCount",
                    "injectedEntryCount",
                    "truncated",
                    "selectionPolicy",
                    "limits",
                )
            },
        )
        agent_request = AgentRunRequest(
            run_id=run_id,
            prompt=request.prompt,
            skill_text=skill.text,
            skill_manifest=skill.manifest,
            repository=self.repo_root,
            workspace=workspace.agent,
            memory=memory,
            history=history,
            event_url=server.event_url,
            event_token=token,
            notify_command=workspace.notify_command,
        )
        try:
            session = self.provider.start(agent_request)
        except Exception as exc:
            detail = redactor.text(str(exc))
            bus.submit_harness("run.failed", {"message": f"could not launch agent: {detail}"})
            processor.drain()
            processor.stop()
            materialize_static_report(
                workspace.report,
                state=state.snapshot(),
                events=store.snapshot(),
                redactor=redactor,
            )
            redactor.scrub_tree(workspace.root)
            server.stop()
            raise HarnessError(f"could not launch agent: {detail}") from exc
        bus.submit_harness(
            "runtime.process.started",
            {"pid": session.pid, "sessionId": session.session_id},
        )
        pump = ProviderEventPump(session, bus.submit_provider)
        pump.start()
        liveness = LivenessTicker(
            session,
            state,
            bus.submit_harness,
            interval_seconds=self.liveness_tick_seconds,
        )
        liveness.start()
        # Let the initial lifecycle events reach the report before returning to the CLI.
        deadline = time.monotonic() + 1
        while state.snapshot()["status"] == "starting" and time.monotonic() < deadline:
            time.sleep(0.005)
        return ActiveRun(
            request=request,
            parent_run_id=request.resume_run_id,
            workspace=workspace,
            output=output,
            session=session,
            pump=pump,
            liveness=liveness,
            bus=bus,
            processor=processor,
            state=state,
            store=store,
            server=server,
            redactor=redactor,
            memory_bank=self.memory_bank,
            skill_manifest=skill.manifest,
        )

    def run(self, request: GenerationRequest) -> GenerationResult:
        active = self.start(request)
        try:
            return active.wait()
        finally:
            # Synchronous API calls never leak a retained HTTP server. The CLI
            # owns the optional post-terminal hold lifecycle.
            active.close_report_server()
