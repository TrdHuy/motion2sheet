from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from motion2sheet.motion.humanoid_motion.schema import read_animation

ANIMATION_ID = "heavy-right-cross"
EXPECTED_FRAMES = list(range(10))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite(value: Any) -> bool:
    if isinstance(value, dict):
        return all(finite(item) for item in value.values())
    if isinstance(value, list):
        return all(finite(item) for item in value)
    if isinstance(value, (bool, str)) or value is None:
        return True
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def classify_assets(manifest: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    character_keys: list[str] = []
    non_characters: list[dict[str, str]] = []
    for key, asset in sorted(manifest["assets"].items()):
        filename = str(asset["filename"])
        if "without-skin" in filename.lower():
            non_characters.append({"key": key, "filename": filename, "reason": "motion-only fixture (without skin)"})
        else:
            character_keys.append(key)
    return character_keys, non_characters


def normalize_key(key: str) -> str:
    return key.strip().lower().replace("_", "-")


def check(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.fixtures.read_text(encoding="utf-8"))
    animation = read_animation(args.root / "animation.json")
    animation_sha = sha(args.root / "animation.json")
    character_keys, non_characters = classify_assets(manifest)
    overall_failures: list[str] = []
    results: list[dict[str, Any]] = []

    check(animation["id"] == ANIMATION_ID, "wrong shared animation id", overall_failures)
    check(animation["frameCount"] == 10 and float(animation["fps"]) == 8.0, "wrong shared animation timing", overall_failures)
    check(abs(float(animation["durationSeconds"]) - 1.125) <= 1e-9, "wrong shared animation duration", overall_failures)
    check(animation["loop"] is False, "shared animation must be non-looping", overall_failures)
    check(all(value == [0.0, 0.0, 0.0] for value in animation["root"]["translations"]), "shared Root drift", overall_failures)

    for key in character_keys:
        safe_key = normalize_key(key)
        char_root = args.root / "characters" / safe_key
        failures: list[str] = []
        asset = manifest["assets"][key]
        asset_report_path = char_root / "diagnostics" / "release-asset-verification.json"
        mapping_report_path = char_root / "diagnostics" / "character-mapping.json"
        render_path = char_root / f"{safe_key}__render.json"
        pose_sheet = char_root / f"{safe_key}__pose_sheet.png"
        preview = char_root / f"{safe_key}__preview.gif"
        render_diagnostics = char_root / "diagnostics" / "render"
        export_report_path = char_root / "diagnostics" / "character-export" / "export.json"

        for path in (asset_report_path, mapping_report_path, render_path, pose_sheet, preview, render_diagnostics, export_report_path):
            check(path.exists(), f"{key}: missing {path.name}", failures)

        asset_report = json.loads(asset_report_path.read_text(encoding="utf-8")) if asset_report_path.is_file() else {}
        check(asset_report.get("assetKey") == key, f"{key}: wrong asset key", failures)
        check(asset_report.get("filename") == asset["filename"], f"{key}: wrong asset filename", failures)
        check(asset_report.get("url") == asset["url"], f"{key}: wrong asset URL", failures)
        check(asset_report.get("expectedSha256") == asset["sha256"] == asset_report.get("actualSha256"), f"{key}: SHA mismatch", failures)
        check(asset_report.get("expectedSize") == asset["size"] == asset_report.get("actualSize"), f"{key}: size mismatch", failures)
        check(asset_report.get("sha256Pass") is True and asset_report.get("sizePass") is True, f"{key}: asset verification failed", failures)

        mapping_report = json.loads(mapping_report_path.read_text(encoding="utf-8")) if mapping_report_path.is_file() else {}
        check(mapping_report.get("leftRightVerification", {}).get("pass") is True, f"{key}: L/R mapping failed", failures)
        check(mapping_report.get("skinValidationPass") is True, f"{key}: skin validation failed", failures)

        export_report = json.loads(export_report_path.read_text(encoding="utf-8")) if export_report_path.is_file() else {}
        skin_stats = export_report.get("skinStatistics", {})
        check(int(skin_stats.get("weightedVertexCount", 0)) > 0, f"{key}: no weighted vertices", failures)
        check(int(skin_stats.get("influenceCount", 0)) > 0, f"{key}: no skin influences", failures)
        check(export_report.get("sourceSha256") == asset["sha256"], f"{key}: export source SHA mismatch", failures)

        render = json.loads(render_path.read_text(encoding="utf-8")) if render_path.is_file() else {}
        check(render.get("renderedSamples") == EXPECTED_FRAMES, f"{key}: render does not cover F0..F9", failures)
        check(render.get("frameCount") == 10, f"{key}: render frameCount mismatch", failures)
        check(float(render.get("fps", -1)) == 8.0 and float(render.get("outputFps", -1)) == 8.0, f"{key}: render FPS mismatch", failures)
        check(render.get("animationSha256Before") == render.get("animationSha256After") == animation_sha, f"{key}: animation mutated", failures)
        check(render.get("animationMutated") is False, f"{key}: renderer reports mutation", failures)
        check(render.get("sourceFbxRequired") is False and render.get("sourceRigRequired") is False, f"{key}: playback requires source motion", failures)
        check(render.get("playback", {}).get("pass") is True, f"{key}: playback failed", failures)
        check(render.get("playback", {}).get("nanInfCheck") is True, f"{key}: playback NaN/Inf", failures)
        check(render.get("rootMotion", {}).get("canonical", {}).get("isInPlace") is True, f"{key}: Root is not in-place", failures)
        check(render.get("semanticMapping", {}).get("leftRightVerification", {}).get("pass") is True, f"{key}: render L/R failed", failures)
        check(finite(render), f"{key}: render report contains NaN/Inf", failures)

        skin_reconstruction_path = render_diagnostics / "skin_reconstruction.json"
        skin_reconstruction = json.loads(skin_reconstruction_path.read_text(encoding="utf-8")) if skin_reconstruction_path.is_file() else {}
        check(skin_reconstruction.get("pass") is True, f"{key}: skin reconstruction failed", failures)

        required_diagnostics = (
            "model_identity.json",
            "skin_reconstruction.json",
            "semantic_mapping.json",
            "retarget.json",
            "playback.json",
            "root_motion.json",
            "contact.json",
            "render_request.json",
        )
        for name in required_diagnostics:
            check((render_diagnostics / name).is_file(), f"{key}: missing render diagnostic {name}", failures)

        acceptance = {
            "schema": "motion2sheet.humanoid-motion.authored-attack-character-acceptance",
            "version": 1,
            "characterKey": key,
            "outputKey": safe_key,
            "filename": asset["filename"],
            "pass": not failures,
            "failures": failures,
            "animationId": ANIMATION_ID,
            "animationSha256": animation_sha,
            "assetVerification": asset_report,
            "characterExport": {
                "weightedVertexCount": skin_stats.get("weightedVertexCount"),
                "influenceCount": skin_stats.get("influenceCount"),
                "boneCount": skin_stats.get("boneCount"),
                "mappingPass": mapping_report.get("leftRightVerification", {}).get("pass") is True,
                "skinValidationPass": mapping_report.get("skinValidationPass") is True,
            },
            "render": {
                "pass": render.get("playback", {}).get("pass") is True and skin_reconstruction.get("pass") is True,
                "renderedSamples": render.get("renderedSamples"),
                "playback": render.get("playback"),
                "rootMotion": render.get("rootMotion"),
                "skinReconstruction": skin_reconstruction,
            },
            "outputs": {
                "poseSheet": str(pose_sheet.relative_to(args.root)),
                "previewGif": str(preview.relative_to(args.root)),
                "renderJson": str(render_path.relative_to(args.root)),
                "diagnostics": str(render_diagnostics.relative_to(args.root)),
            },
        }
        acceptance_path = char_root / f"{safe_key}__acceptance.json"
        acceptance_path.write_text(json.dumps(acceptance, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        results.append(acceptance)
        overall_failures.extend(failures)

    summary = {
        "schema": "motion2sheet.humanoid-motion.authored-attack-multi-character-summary",
        "version": 1,
        "pass": not overall_failures,
        "failures": overall_failures,
        "animation": {
            "id": ANIMATION_ID,
            "sha256": animation_sha,
            "frameCount": 10,
            "fps": 8.0,
            "durationSeconds": 1.125,
            "impactFrame": 5,
        },
        "manifestAssetCount": len(manifest["assets"]),
        "characterCount": len(character_keys),
        "renderedCharacterCount": sum(1 for result in results if result["pass"]),
        "nonCharacterAssetCount": len(non_characters),
        "nonCharacterAssets": non_characters,
        "characters": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if overall_failures:
        raise SystemExit("multi-character Heavy Right Cross acceptance failed: " + "; ".join(overall_failures))
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
