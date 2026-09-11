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
    OutputContractError,
)
from .events import EventProcessor, RunEventBus, RunState, initial_run_state
from .history import load_resume_history
from .providers.base import AgentProvider, AgentSession
from .redaction import SecretRedactor, write_json
from .report.server import ReportServer, materialize_static_report
from .report.store import ProcessedEventStore
from .session import ProviderEventPump
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
        bus: RunEventBus,
        processor: EventProcessor,
        state: RunState,
        store: ProcessedEventStore,
        server: ReportServer,
        redactor: SecretRedactor,
    ) -> None:
        self.request = request
        self.parent_run_id = parent_run_id
        self.workspace = workspace
        self.output = output
        self.session = session
        self.pump = pump
        self.bus = bus
        self.processor = processor
        self.state = state
        self.store = store
        self.server = server
        self.redactor = redactor

    @property
    def run_id(self) -> str:
        return self.bus.run_id

    @property
    def report_url(self) -> str:
        return self.server.report_url

    def wait(self) -> GenerationResult:
        failure: HarnessError | None = None
        result: GenerationResult | None = None
        try:
            exit_result = self.session.wait()
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
            self.redactor.scrub_tree(self.workspace.root)
            self.processor.stop()
            materialize_static_report(
                self.workspace.report,
                state=self.state.snapshot(),
                events=self.store.snapshot(),
                redactor=self.redactor,
            )
            self.redactor.scrub_tree(self.workspace.root)
            self.server.stop()
        if failure is not None:
            raise failure
        assert result is not None
        return result

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
        skill_directory: Path | None = None,
        processing_hook=None,
    ) -> None:
        self.provider = provider
        self.repo_root = Path(repo_root).resolve()
        self.workspace_root = Path(workspace_root).resolve()
        self.skill_directory = (
            Path(skill_directory).resolve()
            if skill_directory is not None
            else (self.repo_root / DEFAULT_SKILL).resolve()
        )
        self.processing_hook = processing_hook

    def start(self, request: GenerationRequest) -> ActiveRun:
        # All configuration and resume validation happens before launching an agent.
        skill = load_skill(self.skill_directory)
        output = preflight_output(request.output)
        history = load_resume_history(self.workspace_root, request.resume_run_id)
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
            )
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
            },
            redactor,
        )
        processor.start()
        server.start()
        bus.submit_harness("run.started", {"reportUrl": server.report_url})
        agent_request = AgentRunRequest(
            run_id=run_id,
            prompt=request.prompt,
            skill_text=skill.text,
            skill_manifest=skill.manifest,
            repository=self.repo_root,
            workspace=workspace.agent,
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
            bus=bus,
            processor=processor,
            state=state,
            store=store,
            server=server,
            redactor=redactor,
        )

    def run(self, request: GenerationRequest) -> GenerationResult:
        return self.start(request).wait()
