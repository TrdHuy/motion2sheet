from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from conftest import make_animation
from motion2sheet.motion.harness_anim_generator.contracts import (
    GenerationExhaustedError,
    GenerationRequest,
    ProviderResponse,
    RenderResult,
    ReviewIssue,
    ReviewResult,
    SelectedReference,
    ValidationResult,
)
from motion2sheet.motion.harness_anim_generator.metadata import MetadataBuilder
from motion2sheet.motion.harness_anim_generator.orchestrator import AnimationGenerationOrchestrator


def plan_payload(intent: str) -> dict:
    return {
        "intent": intent,
        "phases": [{"name": "action", "startFrame": 0, "endFrame": 1, "description": "act"}],
        "keyPoses": [{"frame": 1, "role": "impact", "description": "impact"}],
        "weightTransfer": {"description": "centered", "contactCaveat": "none"},
        "bodyMechanics": {"description": "coordinated", "coordinationFocus": []},
        "referenceUse": {"recommended": ["timing"], "notRecommended": []},
    }


class FakeReferenceSelector:
    def __init__(self, tmp_path: Path):
        self.reference = SelectedReference(
            animation_hash="a" * 64,
            name="reference",
            score=5,
            directory=tmp_path / "reference",
            animation=make_animation("reference"),
            metadata={"name": "reference", "intent": "reference motion"},
            preview_path=tmp_path / "reference" / "preview.gif",
        )

    def select(self, prompt: str) -> SelectedReference:
        return self.reference


class FakeProvider:
    def __init__(self, animation_ids: list[str]):
        self.animation_ids = animation_ids
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        animation_id = self.animation_ids[len(self.requests) - 1]
        return ProviderResponse(
            payload={
                "animation": make_animation(animation_id),
                "plan": plan_payload(f"plan for {request.context['prompt']}"),
            },
            stdout="provider stdout",
            stderr="",
            exit_code=0,
        )


class FakeAdapter:
    def __init__(self, invalid_ids=()):
        self.invalid_ids = set(invalid_ids)
        self.rendered_ids = []

    def validate_animation(self, animation):
        if animation["id"] in self.invalid_ids:
            return ValidationResult(False, (f"invalid {animation['id']}",), None)
        return ValidationResult(True, (), copy.deepcopy(animation))

    def materialize_animation(self, animation, output):
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(animation, sort_keys=True) + "\n", encoding="utf-8")
        return output

    def render_candidate(self, animation_path, output):
        animation = json.loads(Path(animation_path).read_text(encoding="utf-8"))
        animation_id = animation["id"]
        self.rendered_ids.append(animation_id)
        output = Path(output)
        output.mkdir(parents=True)
        sheet = output / "pose_sheet.png"
        preview = output / "preview.gif"
        color = (len(self.rendered_ids) * 40, 0, 0, 255)
        Image.new("RGBA", (2, 2), color).save(sheet)
        Image.new("RGBA", (2, 2), color).save(preview, format="GIF")
        return RenderResult(output, sheet, preview, {"animationId": animation_id})


class FakeReviewer:
    def __init__(self, reviews: list[ReviewResult]):
        self.reviews = reviews
        self.requests = []

    def review(self, request):
        self.requests.append(request)
        return self.reviews[len(self.requests) - 1]


def failed_review(problem="needs refinement") -> ReviewResult:
    return ReviewResult(
        False,
        (
            ReviewIssue(
                frames=(1,),
                region="hips",
                problem=problem,
                severity="error",
                suggestion="shift the weight",
            ),
        ),
    )


def build_orchestrator(tmp_path, provider, adapter, reviewer):
    return AnimationGenerationOrchestrator(
        provider=provider,
        references=FakeReferenceSelector(tmp_path),
        adapter=adapter,
        reviewer=reviewer,
        metadata_builder=MetadataBuilder(),
        workspace_root=tmp_path / "workspaces",
    )


def test_full_flow_carries_prompt_through_every_component_and_packages_output(tmp_path):
    provider = FakeProvider(["accepted"])
    adapter = FakeAdapter()
    reviewer = FakeReviewer([ReviewResult(True)])
    output = tmp_path / "output"
    result = build_orchestrator(tmp_path, provider, adapter, reviewer).run(
        GenerationRequest("heavy spinning attack", "fake", output, 3)
    )
    assert provider.requests[0].context["prompt"] == "heavy spinning attack"
    assert reviewer.requests[0].prompt == "heavy spinning attack"
    assert {path.name for path in output.iterdir()} == {
        "animation.json",
        "metadata.json",
        "preview.gif",
    }
    assert json.loads((output / "animation.json").read_text())["id"] == "accepted"
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["intent"] == "plan for heavy spinning attack"
    assert metadata["referenceUse"]["selectedReferences"][0]["animationHash"] == "a" * 64
    assert result.iterations[0].accepted is True


def test_review_failure_retries_with_feedback_and_packages_second_candidate(tmp_path):
    provider = FakeProvider(["candidate-v1", "candidate-v2"])
    adapter = FakeAdapter()
    reviewer = FakeReviewer([failed_review("impact is weak"), ReviewResult(True)])
    output = tmp_path / "output"
    result = build_orchestrator(tmp_path, provider, adapter, reviewer).run(
        GenerationRequest("attack", "fake", output, 3)
    )
    assert len(provider.requests) == 2
    feedback = provider.requests[1].context["feedback"]
    assert any("impact is weak" in item and "shift the weight" in item for item in feedback)
    assert json.loads((output / "animation.json").read_text())["id"] == "candidate-v2"
    assert [item.accepted for item in result.iterations] == [False, True]
    assert (result.workspace / "v1" / "animation.json").is_file()
    assert (result.workspace / "v2" / "animation.json").is_file()


def test_validation_failure_skips_reviewer_and_retries(tmp_path):
    provider = FakeProvider(["invalid-v1", "valid-v2"])
    adapter = FakeAdapter(invalid_ids={"invalid-v1"})
    reviewer = FakeReviewer([ReviewResult(True)])
    output = tmp_path / "output"
    build_orchestrator(tmp_path, provider, adapter, reviewer).run(
        GenerationRequest("attack", "fake", output, 2)
    )
    assert len(provider.requests) == 2
    assert provider.requests[1].context["feedback"] == ["validation: invalid invalid-v1"]
    assert len(reviewer.requests) == 1
    assert reviewer.requests[0].iteration == 2
    assert adapter.rendered_ids == ["valid-v2"]
    assert json.loads((output / "animation.json").read_text())["id"] == "valid-v2"


def test_max_iterations_is_enforced_without_final_output(tmp_path):
    provider = FakeProvider(["v1", "v2", "v3"])
    adapter = FakeAdapter()
    reviewer = FakeReviewer([failed_review(), failed_review(), failed_review()])
    output = tmp_path / "output"
    with pytest.raises(GenerationExhaustedError, match="exhausted 3 iterations"):
        build_orchestrator(tmp_path, provider, adapter, reviewer).run(
            GenerationRequest("attack", "fake", output, 3)
        )
    assert len(provider.requests) == 3
    assert len(reviewer.requests) == 3
    assert not output.exists()
    workspace = next((tmp_path / "workspaces").iterdir())
    assert json.loads((workspace / "run.json").read_text())["status"] == "exhausted"
    assert all((workspace / f"v{iteration}").is_dir() for iteration in (1, 2, 3))
