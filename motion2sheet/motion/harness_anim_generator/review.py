from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .contracts import (
    GenerationPlan,
    HarnessError,
    ProviderRequest,
    ReviewIssue,
    ReviewResult,
    SelectedReference,
    ValidationResult,
)
from .providers.base import AIProvider


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "frames": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                    "region": {"type": "string"},
                    "problem": {"type": "string"},
                    "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                    "suggestion": {"type": "string"},
                },
                "required": ["frames", "region", "problem", "severity", "suggestion"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["pass", "issues"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ReviewRequest:
    prompt: str
    iteration: int
    animation_path: Path
    key_frame_sheet: Path
    plan: GenerationPlan
    reference: SelectedReference
    validation: ValidationResult


class Reviewer(Protocol):
    def review(self, request: ReviewRequest) -> ReviewResult:
        """Review one valid rendered candidate."""


def _plan_context(plan: GenerationPlan) -> dict[str, Any]:
    return {
        "intent": plan.intent,
        "phases": list(plan.phases),
        "keyPoses": list(plan.key_poses),
        "weightTransfer": plan.weight_transfer,
        "bodyMechanics": plan.body_mechanics,
        "referenceUse": plan.reference_use,
    }


class ProviderReviewer:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def review(self, request: ReviewRequest) -> ReviewResult:
        provider_request = ProviderRequest(
            operation="review",
            instruction=(
                "Review the rendered humanoid animation key-frame sheet against the user prompt and "
                "generation plan. Return only the requested structured review. Do not select references, "
                "decide retry policy, write files, or package outputs."
            ),
            context={
                "prompt": request.prompt,
                "iteration": request.iteration,
                "animationPath": str(request.animation_path),
                "plan": _plan_context(request.plan),
                "validationIssues": list(request.validation.issues),
                "reference": {
                    "animationHash": request.reference.animation_hash,
                    "name": request.reference.name,
                    "metadata": request.reference.metadata,
                },
            },
            response_schema=REVIEW_SCHEMA,
            attachments=(request.key_frame_sheet,),
        )
        response = self.provider.generate(provider_request)
        payload = response.payload
        if set(payload) != {"pass", "issues"} or not isinstance(payload["pass"], bool):
            raise HarnessError("review response must contain exactly boolean pass and issues fields")
        if not isinstance(payload["issues"], list):
            raise HarnessError("review response issues must be an array")
        issues = tuple(ReviewIssue.from_payload(issue) for issue in payload["issues"])
        if not payload["pass"] and not issues:
            raise HarnessError("failed review must contain at least one issue")
        return ReviewResult(passed=payload["pass"], issues=issues)
