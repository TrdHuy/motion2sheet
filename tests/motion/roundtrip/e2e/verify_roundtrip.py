from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED = (
    "rig.json",
    "animation.json",
    "reconstructed.blend",
    "reconstructed.fbx",
    "verification.json",
    "visual/source_sheet.png",
    "visual/reconstructed_sheet.png",
    "visual/diff_sheet.png",
    "visual/overlay_sheet.png",
)


def main() -> None:
    root = Path(sys.argv[1])
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise AssertionError(f"missing round-trip artifacts: {missing}")
    verification = json.loads((root / "verification.json").read_text(encoding="utf-8"))
    gates = {
        "overall": verification.get("pass"),
        "structure": verification.get("structure", {}).get("pass"),
        "localTransform": verification.get("localTransform", {}).get("pass"),
        "worldPose": verification.get("worldPose", {}).get("pass"),
        "jsonOnlyReconstruction": verification.get("jsonOnlyReconstruction", {}).get("pass"),
        "fbxReimport": verification.get("fbxReimport", {}).get("pass"),
        "visual": verification.get("visual", {}).get("pass"),
        "determinism": verification.get("determinism", {}).get("pass"),
    }
    failed = [name for name, value in gates.items() if value is not True]
    if failed:
        raise AssertionError(f"round-trip acceptance gates failed: {failed}")
    print(
        "round-trip PASS: "
        f"translation={verification['localTransform']['maxTranslationError']:.9g}, "
        f"angleDeg={verification['localTransform']['maxAngularErrorDeg']:.9g}, "
        f"scale={verification['localTransform']['maxScaleError']:.9g}, "
        f"world={verification['worldPose']['maxWorldError']:.9g}, "
        f"pixels={verification['visual']['changedPixels']}"
    )


if __name__ == "__main__":
    main()
