from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import (
    GenerationPlan,
    GenerationRequest,
    ProviderError,
    ReviewIssue,
)


def test_generation_request_normalizes_and_validates_input():
    request = GenerationRequest("  attack  ", " codex-cli ", Path("out"), 2)
    assert request.prompt == "attack"
    assert request.provider == "codex-cli"
    assert request.max_iterations == 2
    with pytest.raises(ValueError, match="prompt"):
        GenerationRequest(" ", "codex-cli", Path("out"))
    with pytest.raises(ValueError, match="positive"):
        GenerationRequest("attack", "codex-cli", Path("out"), 0)


def test_generation_plan_maps_public_camel_case_contract():
    plan = GenerationPlan.from_payload(
        {
            "intent": "heavy attack",
            "phases": [
                {"name": "windup", "startFrame": 0, "endFrame": 1, "description": "wind up"}
            ],
            "keyPoses": [{"frame": 0, "role": "start", "description": "start pose"}],
            "weightTransfer": {"description": "forward", "contactCaveat": "unknown"},
            "bodyMechanics": {"description": "rotate", "coordinationFocus": []},
            "referenceUse": {"recommended": ["timing"], "notRecommended": []},
        }
    )
    assert plan.intent == "heavy attack"
    assert plan.key_poses[0]["frame"] == 0
    with pytest.raises(ProviderError, match="fields mismatch"):
        GenerationPlan.from_payload({"intent": "incomplete"})


def test_review_issue_contract_is_strict():
    issue = ReviewIssue.from_payload(
        {
            "frames": [1, 2],
            "region": "hips",
            "problem": "balance",
            "severity": "error",
            "suggestion": "shift weight",
        }
    )
    assert issue.frames == (1, 2)
    with pytest.raises(ProviderError, match="severity"):
        ReviewIssue.from_payload(
            {
                "frames": [],
                "region": "hips",
                "problem": "balance",
                "severity": "fatal",
                "suggestion": "shift weight",
            }
        )
