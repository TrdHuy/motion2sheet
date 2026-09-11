from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping


JsonObject = Mapping[str, Any]


class HarnessError(RuntimeError):
    """Base error raised by the animation generator harness."""


class ProviderError(HarnessError):
    """The configured AI provider could not return a usable response."""


class GenerationExhaustedError(HarnessError):
    """No candidate passed all gates before the iteration limit."""


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    provider: str
    output: Path
    max_iterations: int = 3

    def __post_init__(self) -> None:
        prompt = self.prompt.strip()
        provider = self.provider.strip()
        if not prompt:
            raise ValueError("generation prompt must not be empty")
        if not provider:
            raise ValueError("provider must not be empty")
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, int)
            or self.max_iterations <= 0
        ):
            raise ValueError("max_iterations must be a positive integer")
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "output", Path(self.output))


@dataclass(frozen=True)
class ProviderRequest:
    operation: Literal["generate", "review"]
    instruction: str
    context: JsonObject
    response_schema: JsonObject
    attachments: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        if self.operation not in {"generate", "review"}:
            raise ValueError(f"unsupported provider operation: {self.operation!r}")
        if not self.instruction.strip():
            raise ValueError("provider instruction must not be empty")
        object.__setattr__(self, "attachments", tuple(Path(path) for path in self.attachments))


@dataclass(frozen=True)
class ProviderResponse:
    payload: JsonObject
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True)
class SelectedReference:
    animation_hash: str
    name: str
    score: int
    directory: Path
    animation: JsonObject
    metadata: JsonObject
    preview_path: Path


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderError(f"{label} must be an object")
    return value


def _object_sequence(value: Any, label: str) -> tuple[JsonObject, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ProviderError(f"{label} must be an array of objects")
    return tuple(value)


def _exact_fields(value: dict[str, Any], label: str, fields: set[str]) -> None:
    missing = fields - set(value)
    unknown = set(value) - fields
    if missing or unknown:
        raise ProviderError(f"{label} fields mismatch; missing={sorted(missing)} extra={sorted(unknown)}")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderError(f"{label} must be a non-empty string")
    return value.strip()


def _string_sequence(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProviderError(f"{label} must be an array of strings")
    return value


@dataclass(frozen=True)
class GenerationPlan:
    intent: str
    phases: tuple[JsonObject, ...]
    key_poses: tuple[JsonObject, ...]
    weight_transfer: JsonObject
    body_mechanics: JsonObject
    reference_use: JsonObject

    @classmethod
    def from_payload(cls, value: Any) -> GenerationPlan:
        data = _object(value, "provider plan")
        required = {
            "intent",
            "phases",
            "keyPoses",
            "weightTransfer",
            "bodyMechanics",
            "referenceUse",
        }
        missing = required - set(data)
        unknown = set(data) - required
        if missing or unknown:
            raise ProviderError(
                f"provider plan fields mismatch; missing={sorted(missing)} extra={sorted(unknown)}"
            )
        intent = _text(data["intent"], "provider plan intent")
        phases = _object_sequence(data["phases"], "provider plan phases")
        for phase in phases:
            row = dict(phase)
            _exact_fields(row, "provider plan phase", {"name", "startFrame", "endFrame", "description"})
            _text(row["name"], "provider plan phase name")
            _text(row["description"], "provider plan phase description")
            start, end = row["startFrame"], row["endFrame"]
            if any(isinstance(frame, bool) or not isinstance(frame, int) or frame < 0 for frame in (start, end)):
                raise ProviderError("provider plan phase frames must be non-negative integers")
            if end < start:
                raise ProviderError("provider plan phase endFrame must not precede startFrame")
        key_poses = _object_sequence(data["keyPoses"], "provider plan keyPoses")
        for pose in key_poses:
            row = dict(pose)
            _exact_fields(row, "provider plan key pose", {"frame", "role", "description"})
            if isinstance(row["frame"], bool) or not isinstance(row["frame"], int) or row["frame"] < 0:
                raise ProviderError("provider plan key pose frame must be a non-negative integer")
            _text(row["role"], "provider plan key pose role")
            _text(row["description"], "provider plan key pose description")
        weight_transfer = _object(data["weightTransfer"], "provider plan weightTransfer")
        _exact_fields(weight_transfer, "provider plan weightTransfer", {"description", "contactCaveat"})
        _text(weight_transfer["description"], "provider plan weightTransfer description")
        _text(weight_transfer["contactCaveat"], "provider plan weightTransfer contactCaveat")
        body_mechanics = _object(data["bodyMechanics"], "provider plan bodyMechanics")
        _exact_fields(body_mechanics, "provider plan bodyMechanics", {"description", "coordinationFocus"})
        _text(body_mechanics["description"], "provider plan bodyMechanics description")
        _string_sequence(body_mechanics["coordinationFocus"], "provider plan coordinationFocus")
        reference_use = _object(data["referenceUse"], "provider plan referenceUse")
        _exact_fields(reference_use, "provider plan referenceUse", {"recommended", "notRecommended"})
        _string_sequence(reference_use["recommended"], "provider plan referenceUse recommended")
        _string_sequence(reference_use["notRecommended"], "provider plan referenceUse notRecommended")
        return cls(
            intent=intent,
            phases=phases,
            key_poses=key_poses,
            weight_transfer=weight_transfer,
            body_mechanics=body_mechanics,
            reference_use=reference_use,
        )


@dataclass(frozen=True)
class CandidateResult:
    iteration: int
    animation: JsonObject
    plan: GenerationPlan
    animation_path: Path
    provider_response_path: Path


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    issues: tuple[str, ...] = ()
    animation: JsonObject | None = None


@dataclass(frozen=True)
class ReviewIssue:
    frames: tuple[int, ...]
    region: str
    problem: str
    severity: Literal["info", "warning", "error"]
    suggestion: str

    @classmethod
    def from_payload(cls, value: Any) -> ReviewIssue:
        data = _object(value, "review issue")
        required = {"frames", "region", "problem", "severity", "suggestion"}
        missing = required - set(data)
        unknown = set(data) - required
        if missing or unknown:
            raise ProviderError(
                f"review issue fields mismatch; missing={sorted(missing)} extra={sorted(unknown)}"
            )
        frames = data["frames"]
        if (
            not isinstance(frames, list)
            or any(isinstance(frame, bool) or not isinstance(frame, int) or frame < 0 for frame in frames)
        ):
            raise ProviderError("review issue frames must be non-negative integers")
        severity = data["severity"]
        if severity not in {"info", "warning", "error"}:
            raise ProviderError(f"unsupported review severity: {severity!r}")
        text_fields = {}
        for field in ("region", "problem", "suggestion"):
            item = data[field]
            if not isinstance(item, str) or not item.strip():
                raise ProviderError(f"review issue {field} must be a non-empty string")
            text_fields[field] = item.strip()
        return cls(tuple(frames), severity=severity, **text_fields)


@dataclass(frozen=True)
class ReviewResult:
    passed: bool
    issues: tuple[ReviewIssue, ...] = ()


@dataclass(frozen=True)
class RenderResult:
    output_dir: Path
    key_frame_sheet: Path
    preview_path: Path
    report: JsonObject


@dataclass(frozen=True)
class IterationResult:
    iteration: int
    candidate: CandidateResult
    validation: ValidationResult
    render: RenderResult | None
    review: ReviewResult | None
    accepted: bool


@dataclass(frozen=True)
class GenerationResult:
    output: Path
    animation_path: Path
    metadata_path: Path
    preview_path: Path
    workspace: Path
    selected_reference: SelectedReference
    iterations: tuple[IterationResult, ...]
