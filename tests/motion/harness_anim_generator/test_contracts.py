from pathlib import Path

import pytest

from motion2sheet.motion.harness_anim_generator.contracts import GenerationRequest


def test_generation_request_normalizes_runtime_inputs():
    request = GenerationRequest(
        "  attack  ",
        " codex-cli ",
        Path("out"),
        resume_run_id="old-run",
        report_port=8123,
        open_report=False,
    )
    assert request.prompt == "attack"
    assert request.provider == "codex-cli"
    assert request.resume_run_id == "old-run"
    assert request.report_port == 8123
    assert request.open_report is False


@pytest.mark.parametrize("run_id", ["", "../old", "old/run", ".", ".."])
def test_generation_request_rejects_unsafe_resume_id(run_id):
    with pytest.raises(ValueError, match="run identifier"):
        GenerationRequest("attack", "fake", Path("out"), resume_run_id=run_id)


def test_generation_request_validates_prompt_and_port():
    with pytest.raises(ValueError, match="prompt"):
        GenerationRequest(" ", "fake", Path("out"))
    with pytest.raises(ValueError, match="report_port"):
        GenerationRequest("attack", "fake", Path("out"), report_port=70000)
