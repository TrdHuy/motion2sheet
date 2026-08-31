from __future__ import annotations

from pathlib import Path


def test_common_does_not_depend_on_gale_slash():
    root = Path(__file__).resolve().parents[3] / "motion2sheet/anim2sheet/common"
    violations = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "animations.gale_slash" in text or "animations/gale_slash" in text:
            violations.append(str(path.relative_to(root)))
        if 'animation == "gale_slash"' in text or "animation == 'gale_slash'" in text:
            violations.append(str(path.relative_to(root)))
    assert not violations, f"common -> gale_slash dependency found: {violations}"
