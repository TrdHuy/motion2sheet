from pathlib import Path

from motion2sheet.anim2sheet.common.output.validator import REQUIRED_FILES, validate_output


def test_missing_artifact_files_fail_in_declared_order(tmp_path: Path):
    assert validate_output(tmp_path) == [f"{name} is missing" for name in REQUIRED_FILES]
