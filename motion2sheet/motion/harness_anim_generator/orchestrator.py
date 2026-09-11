from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Protocol

from .contracts import (
    CandidateResult,
    GenerationExhaustedError,
    GenerationPlan,
    GenerationRequest,
    GenerationResult,
    HarnessError,
    IterationResult,
    ProviderRequest,
    ProviderResponse,
    ReviewIssue,
    SelectedReference,
    ValidationResult,
)
from .metadata import MetadataBuilder
from .motion2sheet_adapter import MotionEngineAdapter, humanoid_animation_json_schema
from .providers.base import AIProvider
from .review import ReviewRequest, Reviewer


GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "animation": humanoid_animation_json_schema(),
        "plan": {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "phases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "startFrame": {"type": "integer"},
                            "endFrame": {"type": "integer"},
                            "description": {"type": "string"},
                        },
                        "required": ["name", "startFrame", "endFrame", "description"],
                        "additionalProperties": False,
                    },
                },
                "keyPoses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "frame": {"type": "integer"},
                            "role": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["frame", "role", "description"],
                        "additionalProperties": False,
                    },
                },
                "weightTransfer": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "contactCaveat": {"type": "string"},
                    },
                    "required": ["description", "contactCaveat"],
                    "additionalProperties": False,
                },
                "bodyMechanics": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "coordinationFocus": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["description", "coordinationFocus"],
                    "additionalProperties": False,
                },
                "referenceUse": {
                    "type": "object",
                    "properties": {
                        "recommended": {"type": "array", "items": {"type": "string"}},
                        "notRecommended": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["recommended", "notRecommended"],
                    "additionalProperties": False,
                },
            },
            "required": [
                "intent",
                "phases",
                "keyPoses",
                "weightTransfer",
                "bodyMechanics",
                "referenceUse",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["animation", "plan"],
    "additionalProperties": False,
}


class ReferenceSelector(Protocol):
    def select(self, prompt: str) -> SelectedReference:
        """Select one trusted reference before provider invocation."""


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _reference_context(reference: SelectedReference) -> dict[str, Any]:
    return {
        "animationHash": reference.animation_hash,
        "name": reference.name,
        "score": reference.score,
        "animation": reference.animation,
        "metadata": reference.metadata,
    }


def _reference_summary(reference: SelectedReference) -> dict[str, Any]:
    return {
        "animationHash": reference.animation_hash,
        "name": reference.name,
        "score": reference.score,
        "directory": str(reference.directory),
        "preview": str(reference.preview_path),
    }


def _plan_payload(plan: GenerationPlan) -> dict[str, Any]:
    return {
        "intent": plan.intent,
        "phases": list(plan.phases),
        "keyPoses": list(plan.key_poses),
        "weightTransfer": plan.weight_transfer,
        "bodyMechanics": plan.body_mechanics,
        "referenceUse": plan.reference_use,
    }


def _validation_payload(result: ValidationResult) -> dict[str, Any]:
    return {"pass": result.passed, "issues": list(result.issues)}


def _issue_payload(issue: ReviewIssue) -> dict[str, Any]:
    return {
        "frames": list(issue.frames),
        "region": issue.region,
        "problem": issue.problem,
        "severity": issue.severity,
        "suggestion": issue.suggestion,
    }


class AnimationGenerationOrchestrator:
    def __init__(
        self,
        *,
        provider: AIProvider,
        references: ReferenceSelector,
        adapter: MotionEngineAdapter,
        reviewer: Reviewer,
        metadata_builder: MetadataBuilder,
        workspace_root: Path,
    ) -> None:
        self.provider = provider
        self.references = references
        self.adapter = adapter
        self.reviewer = reviewer
        self.metadata_builder = metadata_builder
        self.workspace_root = Path(workspace_root)

    @staticmethod
    def _preflight_output(output: Path) -> None:
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise HarnessError(f"output must not exist or must be an empty directory: {output}")

    @staticmethod
    def _provider_request(
        request: GenerationRequest,
        reference: SelectedReference,
        iteration: int,
        feedback: tuple[str, ...],
    ) -> ProviderRequest:
        return ProviderRequest(
            operation="generate",
            instruction=(
                "Create one Humanoid Motion v1 animation candidate and a semantic generation plan. "
                "Return only the requested structured response. Do not write files, choose references, "
                "validate, review, retry, or package final output."
            ),
            context={
                "prompt": request.prompt,
                "iteration": iteration,
                "feedback": list(feedback),
                "selectedReference": _reference_context(reference),
            },
            response_schema=GENERATION_SCHEMA,
        )

    @staticmethod
    def _candidate(
        response: ProviderResponse,
        *,
        iteration: int,
        iteration_dir: Path,
    ) -> CandidateResult:
        if set(response.payload) != {"animation", "plan"}:
            raise HarnessError("generation response must contain exactly animation and plan fields")
        animation = response.payload["animation"]
        if not isinstance(animation, dict):
            raise HarnessError("generation response animation must be an object")
        plan = GenerationPlan.from_payload(response.payload["plan"])
        response_path = iteration_dir / "provider-response.json"
        _write_json(
            response_path,
            {
                "exitCode": response.exit_code,
                "payload": response.payload,
                "stdout": response.stdout,
                "stderr": response.stderr,
            },
        )
        animation_path = iteration_dir / "animation.json"
        _write_json(animation_path, animation)
        return CandidateResult(
            iteration=iteration,
            animation=animation,
            plan=plan,
            animation_path=animation_path,
            provider_response_path=response_path,
        )

    @staticmethod
    def _finalize(
        *,
        request: GenerationRequest,
        run_id: str,
        adapter: MotionEngineAdapter,
        animation: dict[str, Any],
        metadata: dict[str, Any],
        preview: Path,
    ) -> tuple[Path, Path, Path]:
        output = request.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = output.parent / f".{output.name}.harness-{run_id}"
        if staging.exists():
            raise HarnessError(f"finalization staging path already exists: {staging}")
        staging.mkdir()
        try:
            adapter.materialize_animation(animation, staging / "animation.json")
            _write_json(staging / "metadata.json", metadata)
            shutil.copyfile(preview, staging / "preview.gif")
            actual = {path.name for path in staging.iterdir()}
            expected = {"animation.json", "metadata.json", "preview.gif"}
            if actual != expected or any(not (staging / name).is_file() for name in expected):
                raise HarnessError(f"final output contract mismatch: expected={sorted(expected)} actual={sorted(actual)}")
            if output.exists():
                output.rmdir()
            staging.replace(output)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        return output / "animation.json", output / "metadata.json", output / "preview.gif"

    def run(self, request: GenerationRequest) -> GenerationResult:
        output = request.output.resolve()
        self._preflight_output(output)
        run_id = uuid.uuid4().hex
        workspace = (self.workspace_root / run_id).resolve()
        workspace.mkdir(parents=True)
        _write_json(
            workspace / "request.json",
            {
                "prompt": request.prompt,
                "provider": request.provider,
                "output": str(output),
                "maxIterations": request.max_iterations,
            },
        )
        iterations: list[IterationResult] = []
        feedback: tuple[str, ...] = ()
        try:
            reference = self.references.select(request.prompt)
            _write_json(workspace / "references.json", [_reference_summary(reference)])
            for iteration in range(1, request.max_iterations + 1):
                iteration_dir = workspace / f"v{iteration}"
                iteration_dir.mkdir()
                provider_request = self._provider_request(request, reference, iteration, feedback)
                _write_json(
                    iteration_dir / "provider-request.json",
                    {
                        "operation": provider_request.operation,
                        "instruction": provider_request.instruction,
                        "context": provider_request.context,
                    },
                )
                candidate = self._candidate(
                    self.provider.generate(provider_request),
                    iteration=iteration,
                    iteration_dir=iteration_dir,
                )
                validation = self.adapter.validate_animation(candidate.animation)
                _write_json(iteration_dir / "validation.json", _validation_payload(validation))
                if not validation.passed:
                    result = IterationResult(iteration, candidate, validation, None, None, False)
                    iterations.append(result)
                    feedback = tuple(f"validation: {issue}" for issue in validation.issues)
                    continue
                if validation.animation is None:
                    raise HarnessError("adapter returned a passing validation without an animation")
                self.adapter.materialize_animation(validation.animation, candidate.animation_path)
                render = self.adapter.render_candidate(candidate.animation_path, iteration_dir / "renders")
                review = self.reviewer.review(
                    ReviewRequest(
                        prompt=request.prompt,
                        iteration=iteration,
                        animation_path=candidate.animation_path,
                        key_frame_sheet=render.key_frame_sheet,
                        plan=candidate.plan,
                        reference=reference,
                        validation=validation,
                    )
                )
                _write_json(
                    iteration_dir / "review.json",
                    {"pass": review.passed, "issues": [_issue_payload(issue) for issue in review.issues]},
                )
                accepted = review.passed
                iterations.append(IterationResult(iteration, candidate, validation, render, review, accepted))
                if not accepted:
                    feedback = tuple(
                        "review: "
                        f"frames={list(issue.frames)} region={issue.region} severity={issue.severity} "
                        f"problem={issue.problem} suggestion={issue.suggestion}"
                        for issue in review.issues
                    )
                    continue
                accepted_animation = dict(validation.animation)
                metadata = self.metadata_builder.build(
                    animation=accepted_animation,
                    plan=candidate.plan,
                    reference=reference,
                )
                animation_path, metadata_path, preview_path = self._finalize(
                    request=request,
                    run_id=run_id,
                    adapter=self.adapter,
                    animation=accepted_animation,
                    metadata=metadata,
                    preview=render.preview_path,
                )
                _write_json(
                    workspace / "run.json",
                    {"status": "accepted", "acceptedIteration": iteration, "output": str(output)},
                )
                return GenerationResult(
                    output=output,
                    animation_path=animation_path,
                    metadata_path=metadata_path,
                    preview_path=preview_path,
                    workspace=workspace,
                    selected_reference=reference,
                    iterations=tuple(iterations),
                )
            _write_json(
                workspace / "run.json",
                {"status": "exhausted", "iterations": request.max_iterations, "output": str(output)},
            )
            raise GenerationExhaustedError(
                f"animation generation exhausted {request.max_iterations} iterations; diagnostics: {workspace}"
            )
        except Exception as exc:
            run_path = workspace / "run.json"
            if not run_path.exists():
                _write_json(
                    run_path,
                    {"status": "failed", "errorType": type(exc).__name__, "error": str(exc)},
                )
            raise
