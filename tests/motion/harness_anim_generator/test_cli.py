from pathlib import Path

import pytest

from motion2sheet.motion.cli import parser
from motion2sheet.motion.harness_anim_generator.cli import generation_request_from_args


def test_cli_parser_creates_generation_request():
    args = parser().parse_args(
        [
            "generate-humanoid-animation",
            "--prompt",
            "Tạo một heavy spinning attack",
            "--provider",
            "codex-cli",
            "--output",
            "build/generated/spinning-attack",
            "--max-iterations",
            "4",
        ]
    )
    request = generation_request_from_args(args)
    assert request.prompt == "Tạo một heavy spinning attack"
    assert request.provider == "codex-cli"
    assert request.output == Path("build/generated/spinning-attack")
    assert request.max_iterations == 4


def test_cli_reads_prompt_file_and_uses_defaults(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("walk carefully\n", encoding="utf-8")
    args = parser().parse_args(
        ["generate-humanoid-animation", "--prompt-file", str(prompt), "--output", "out"]
    )
    request = generation_request_from_args(args)
    assert request.prompt == "walk carefully"
    assert request.provider == "codex-cli"
    assert request.max_iterations == 3


def test_cli_rejects_non_positive_iteration_limit():
    with pytest.raises(SystemExit):
        parser().parse_args(
            [
                "generate-humanoid-animation",
                "--prompt",
                "walk",
                "--output",
                "out",
                "--max-iterations",
                "0",
            ]
        )
