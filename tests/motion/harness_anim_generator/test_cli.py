from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.harness_anim_generator.cli import generation_request_from_args


def test_cli_parser_creates_sdar_request():
    args = parser().parse_args(
        [
            "generate-humanoid-animation",
            "--prompt",
            "Tạo một heavy spinning attack",
            "--provider",
            "codex-cli",
            "--output",
            "build/generated/spinning-attack",
            "--resume-run",
            "previous-run",
            "--report-port",
            "8123",
            "--no-open-report",
        ]
    )
    request = generation_request_from_args(args)
    assert request.prompt == "Tạo một heavy spinning attack"
    assert request.output == Path("build/generated/spinning-attack")
    assert request.resume_run_id == "previous-run"
    assert request.report_port == 8123
    assert request.open_report is False
    assert request.skill_directory is None


def test_cli_reads_prompt_file_and_has_default_skill_implicitly(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("walk carefully\n", encoding="utf-8")
    args = parser().parse_args(
        ["generate-humanoid-animation", "--prompt-file", str(prompt), "--output", "out"]
    )
    request = generation_request_from_args(args)
    assert request.prompt == "walk carefully"
    assert request.provider == "codex-cli"
    assert request.skill_directory is None


def test_cli_parses_skill_directory_override():
    args = parser().parse_args(
        [
            "generate-humanoid-animation",
            "--prompt",
            "smoke test",
            "--skill",
            "tests/manual/sdar-smoke/skill",
            "--output",
            "out",
        ]
    )
    request = generation_request_from_args(args)
    assert request.skill_directory == Path("tests/manual/sdar-smoke/skill")


def test_cli_rejects_invalid_report_port():
    with pytest.raises(SystemExit):
        parser().parse_args(
            ["generate-humanoid-animation", "--prompt", "walk", "--output", "out", "--report-port", "-1"]
        )
