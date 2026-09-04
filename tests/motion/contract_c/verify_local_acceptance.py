from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="build/contract_c_poc")
    parser.add_argument("--output", default="build/contract_c_poc/acceptance.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    failures: list[str] = []
    results: dict[str, Any] = {}

    for clip in ("idle", "run", "run-inplace"):
        animation_path = (root / "animations" / clip / "animation.json").resolve()
        animation_sha = _sha256(animation_path)
        animation = _read(animation_path)
        character_rows = {}
        for character in ("character-a", "character-b"):
            render_dir = root / "renders" / character / clip
            report = _read(render_dir / "render.json")
            request = _read(render_dir / "diagnostics" / "render_request.json")
            playback = _read(render_dir / "diagnostics" / "playback.json")
            model = _read(render_dir / "diagnostics" / "model_identity.json")
            retarget = _read(render_dir / "diagnostics" / "retarget.json")
            mapping = _read(render_dir / "diagnostics" / "semantic_mapping.json")
            hashes = (report["animationSha256Before"], report["animationSha256After"], request["animationSha256"])
            if any(value != animation_sha for value in hashes):
                failures.append(f"{character}/{clip}: animation SHA mismatch")
            if Path(request["animationPath"]).resolve() != animation_path:
                failures.append(f"{character}/{clip}: did not read the shared authority path")
            if not playback["pass"] or not playback["leftRightIdentity"] or not playback["nanInfCheck"]:
                failures.append(f"{character}/{clip}: playback gate failed")
            if not model["pass"] or model["vertexCount"] <= 0:
                failures.append(f"{character}/{clip}: real model identity gate failed")
            if mapping["missingRequiredJoints"] or mapping["mappedJointCount"] != 21:
                failures.append(f"{character}/{clip}: semantic mapping incomplete")
            if not all(row["restCorrectionApplied"] for row in retarget["joints"]):
                failures.append(f"{character}/{clip}: target rest correction missing")
            for relative in ("pose_sheet.png", "preview.gif", "diagnostics/playback.json"):
                if not (render_dir / relative).is_file():
                    failures.append(f"{character}/{clip}: missing {relative}")
            character_rows[character] = {
                "characterId": report["characterId"],
                "mappingId": report["mappingId"],
                "animationPath": request["animationPath"],
                "animationSha256Before": hashes[0],
                "animationSha256After": hashes[1],
                "mappedJointCount": mapping["mappedJointCount"],
                "ignoredBoneCount": len(mapping["ignoredBones"]),
                "leftRightIdentity": playback["leftRightIdentity"],
                "maxSemanticRotationErrorDegrees": playback["maxSemanticRotationErrorDegrees"],
                "targetMeanLegLengthSceneUnits": retarget["targetMeanLegLengthSceneUnits"],
                "actualSkinnedMesh": {"meshCount": model["meshCount"], "vertexCount": model["vertexCount"]},
                "poseSheet": str((render_dir / "pose_sheet.png").resolve()),
                "previewGif": str((render_dir / "preview.gif").resolve()),
                "diagnostics": str((render_dir / "diagnostics").resolve()),
            }
        if character_rows["character-a"]["characterId"] == character_rows["character-b"]["characterId"]:
            failures.append(f"{clip}: targets unexpectedly have the same character id")
        root_motion = _read(root / "animations" / clip / "export.json")["rootMotion"]
        results[clip] = {
            "animation": {
                "path": str(animation_path),
                "sha256": animation_sha,
                "schema": animation["schema"],
                "fps": animation["fps"],
                "frameCount": animation["frameCount"],
            },
            "rootMotion": root_motion,
            "characters": character_rows,
            "sameExactAnimationAuthority": len(
                {
                    animation_sha,
                    *(row["animationSha256Before"] for row in character_rows.values()),
                    *(row["animationSha256After"] for row in character_rows.values()),
                }
            ) == 1,
        }

    if results["run"]["rootMotion"]["isInPlace"]:
        failures.append("run: expected non-in-place root motion")
    if not results["run-inplace"]["rootMotion"]["isInPlace"]:
        failures.append("run-inplace: expected in-place root motion")
    if results["run"]["rootMotion"]["displacement"] <= 1.0:
        failures.append("run: root displacement was not preserved")

    report = {
        "schema": "motion2sheet.contract-c.local-acceptance",
        "version": 1,
        "pass": not failures,
        "phase": "phase-1-derived-second-target",
        "failures": failures,
        "proof": results,
        "knownLimitation": "Character B is a deterministic skinned derivative used to vary proportions, rest basis and bone names; final acceptance still needs a second independently authored skinned character when available.",
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("Contract C local acceptance FAIL: " + "; ".join(failures))
    print(f"Contract C local acceptance PASS -> {output}")


if __name__ == "__main__":
    main()
