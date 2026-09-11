from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import (
    GenerationPlan,
    HarnessError,
    ProviderResponse,
    SelectedReference,
    ValidationResult,
)
from motion2sheet.motion.harness_anim_generator.review import ProviderReviewer, ReviewRequest


class FakeReviewProvider:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return ProviderResponse(self.payload, "", "", 0)


def review_request(tmp_path: Path) -> ReviewRequest:
    sheet = tmp_path / "pose_sheet.png"
    sheet.write_bytes(b"png")
    plan = GenerationPlan.from_payload(
        {
            "intent": "attack",
            "phases": [],
            "keyPoses": [],
            "weightTransfer": {"description": "centered", "contactCaveat": "unknown"},
            "bodyMechanics": {"description": "coordinated", "coordinationFocus": []},
            "referenceUse": {"recommended": [], "notRecommended": []},
        }
    )
    reference = SelectedReference(
        "a" * 64,
        "attack-reference",
        1,
        tmp_path,
        {},
        {"name": "attack-reference"},
        tmp_path / "preview.gif",
    )
    return ReviewRequest(
        prompt="attack",
        iteration=1,
        animation_path=tmp_path / "animation.json",
        key_frame_sheet=sheet,
        plan=plan,
        reference=reference,
        validation=ValidationResult(True),
    )


def test_provider_reviewer_uses_review_operation_and_pose_sheet(tmp_path):
    provider = FakeReviewProvider(
        {
            "pass": False,
            "issues": [
                {
                    "frames": [1],
                    "region": "hips",
                    "problem": "balance",
                    "severity": "error",
                    "suggestion": "shift weight",
                }
            ],
        }
    )
    result = ProviderReviewer(provider).review(review_request(tmp_path))
    assert result.passed is False
    assert result.issues[0].problem == "balance"
    assert provider.requests[0].operation == "review"
    assert provider.requests[0].attachments == (tmp_path / "pose_sheet.png",)


def test_failed_review_without_issues_is_rejected(tmp_path):
    provider = FakeReviewProvider({"pass": False, "issues": []})
    with pytest.raises(HarnessError, match="at least one issue"):
        ProviderReviewer(provider).review(review_request(tmp_path))
