from pathlib import Path
from motion2sheet.anim2sheet.common.output.validator import validate_output

def test_missing_source_fails(tmp_path: Path):
    assert validate_output(tmp_path) == ["source.json is missing", "metadata.json is missing", "source.blend is missing", "motion_debug.json is missing"]
