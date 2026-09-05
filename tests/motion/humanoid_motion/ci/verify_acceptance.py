from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

CHARACTERS = ("character-a", "maria", "warrok")
CLIPS = ("idle", "run", "run-inplace")
SMOKE_CELLS = {
    ("character-a", "idle"),
    ("character-a", "run"),
    ("character-a", "run-inplace"),
    ("maria", "run"),
    ("warrok", "run"),
}
FULL_CELLS = {(character, clip) for character in CHARACTERS for clip in CLIPS}
ROTATION_TOLERANCE_DEGREES = 0.005
TRANSLATION_TOLERANCE = 1e-5
ROOT_TOLERANCE = 1e-8
MAX_SAMPLES_PER_CELL = 8
EXPECTED_OUTPUT_FPS = 8.0
EXPECTED_CANVAS = [160, 160]
EXPECTED_RENDER_SAMPLES = 1


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rotation_error(first: list[float], second: list[float]) -> float:
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    dot = abs(sum(a * b for a, b in zip(first, second)) / (first_norm * second_norm))
    return math.degrees(2.0 * math.acos(min(1.0, dot)))


def _run_equivalence(run: dict[str, Any], inplace: dict[str, Any]) -> dict[str, Any]:
    failures = []
    if run["frameCount"] != inplace["frameCount"] or run["fps"] != inplace["fps"]:
        failures.append("Run and Run-in-place timing differs")
    max_rotation = 0.0
    worst_rotation = None
    max_hips = 0.0
    worst_hips = None
    count = min(run["frameCount"], inplace["frameCount"])
    semantics = ("Root", "Hips", *run["joints"].keys())
    for sample in range(count):
        hips_error = math.dist(run["hips"]["translations"][sample], inplace["hips"]["translations"][sample])
        if hips_error > max_hips:
            max_hips, worst_hips = hips_error, {"sample": sample}
        for semantic in semantics:
            if semantic == "Root":
                first, second = run["root"]["rotations"][sample], inplace["root"]["rotations"][sample]
            elif semantic == "Hips":
                first, second = run["hips"]["rotations"][sample], inplace["hips"]["rotations"][sample]
            else:
                first = run["joints"][semantic]["rotations"][sample]
                second = inplace["joints"][semantic]["rotations"][sample]
            error = _rotation_error(first, second)
            if error > max_rotation:
                max_rotation, worst_rotation = error, {"sample": sample, "semantic": semantic}
    if max_rotation > ROTATION_TOLERANCE_DEGREES:
        failures.append("Run and Run-in-place semantic rotations differ")
    if max_hips > TRANSLATION_TOLERANCE:
        failures.append("Run and Run-in-place in-place Hips translations differ")
    return {
        "pass": not failures,
        "maxRotationErrorDegrees": max_rotation,
        "worstRotation": worst_rotation,
        "maxHipsTranslationError": max_hips,
        "worstHipsTranslation": worst_hips,
        "tolerances": {"rotationDegrees": ROTATION_TOLERANCE_DEGREES, "translation": TRANSLATION_TOLERANCE},
        "failures": failures,
    }


def _validate_sparse_samples(character: str, clip: str, animation: dict[str, Any], report: dict[str, Any], request: dict[str, Any], failures: list[str]) -> None:
    selected = report["renderedSamples"]
    frame_count = animation["frameCount"]
    expected_count = min(frame_count, MAX_SAMPLES_PER_CELL)
    if len(selected) != expected_count:
        failures.append(f"{character}/{clip}: sparse render count {len(selected)} != {expected_count}")
    if selected != sorted(set(selected)):
        failures.append(f"{character}/{clip}: rendered samples are not unique ascending")
    if selected and selected[0] != 0:
        failures.append(f"{character}/{clip}: sparse render does not include first sample")
    if selected and selected[-1] != frame_count - 1:
        failures.append(f"{character}/{clip}: sparse render does not include last sample")
    if request.get("selectedSamples") != selected:
        failures.append(f"{character}/{clip}: render request/report sample mismatch")
    if report.get("outputFps") != EXPECTED_OUTPUT_FPS:
        failures.append(f"{character}/{clip}: outputFps must be {EXPECTED_OUTPUT_FPS:g}")
    if report.get("fps") != animation["fps"]:
        failures.append(f"{character}/{clip}: canonical animation FPS changed")
    if report.get("renderSamples") != EXPECTED_RENDER_SAMPLES or request.get("renderSamples") != EXPECTED_RENDER_SAMPLES:
        failures.append(f"{character}/{clip}: CI render samples must be {EXPECTED_RENDER_SAMPLES}")
    if report.get("layout", {}).get("cellSize") != EXPECTED_CANVAS or request.get("canvas") != EXPECTED_CANVAS:
        failures.append(f"{character}/{clip}: CI canvas must be 160x160")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="build/motion/humanoid-motion")
    parser.add_argument("--output", default="build/motion/humanoid-motion/acceptance.json")
    parser.add_argument("--mode", choices=("smoke", "full"), default="full")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    expected_cells = SMOKE_CELLS if args.mode == "smoke" else FULL_CELLS
    failures: list[str] = []
    results: dict[str, Any] = {}
    character_ids: dict[str, str] = {}
    rendered_visual_samples = 0
    visual_matrix = {character: {clip: (character, clip) in expected_cells for clip in CLIPS} for character in CHARACTERS}

    for clip in CLIPS:
        animation_path = (root / "animations" / clip / "animation.json").resolve()
        animation_sha = _sha256(animation_path)
        animation = _read(animation_path)
        fidelity = _read(root / "animations" / clip / "diagnostics" / "source_humanoid_motion_fidelity.json")
        export = _read(root / "animations" / clip / "export.json")
        if not fidelity["pass"]:
            failures.append(f"{clip}: independent Source -> Humanoid Motion fidelity failed")
        if not fidelity["rootInvariant"]["pass"] or fidelity["rootInvariant"]["maxAbsComponent"] > ROOT_TOLERANCE:
            failures.append(f"{clip}: Humanoid Motion Root invariant failed")

        character_rows = {}
        for character in CHARACTERS:
            if (character, clip) not in expected_cells:
                continue
            render_dir = root / "renders" / character / clip
            report = _read(render_dir / "render.json")
            request = _read(render_dir / "diagnostics" / "render_request.json")
            playback = _read(render_dir / "diagnostics" / "playback.json")
            model = _read(render_dir / "diagnostics" / "model_identity.json")
            skin = _read(render_dir / "diagnostics" / "skin_reconstruction.json")
            retarget = _read(render_dir / "diagnostics" / "retarget.json")
            mapping = _read(render_dir / "diagnostics" / "semantic_mapping.json")
            hashes = (report["animationSha256Before"], report["animationSha256After"], request["animationSha256"])
            if any(value != animation_sha for value in hashes):
                failures.append(f"{character}/{clip}: animation SHA mismatch")
            if report.get("animationMutated") is not False:
                failures.append(f"{character}/{clip}: animation mutation flag is not false")
            if Path(request["animationPath"]).resolve() != animation_path:
                failures.append(f"{character}/{clip}: did not read the shared Humanoid Motion path")
            if report["cameraFollowsRoot"] or request["camera"].get("followRoot"):
                failures.append(f"{character}/{clip}: camera followed Hips and could mask locomotion")
            _validate_sparse_samples(character, clip, animation, report, request, failures)
            rendered_visual_samples += len(report["renderedSamples"])
            if not playback["pass"] or not playback["leftRightIdentity"] or not playback["nanInfCheck"]:
                failures.append(f"{character}/{clip}: playback gate failed")
            if not model["pass"] or model["vertexCount"] <= 0 or not skin["pass"]:
                failures.append(f"{character}/{clip}: actual skinned mesh gate failed")
            if mapping["missingRequiredJoints"] or mapping["mappedJointCount"] != 21:
                failures.append(f"{character}/{clip}: semantic mapping incomplete")
            if not mapping["leftRightVerification"]["pass"]:
                failures.append(f"{character}/{clip}: left/right mapping failed")
            if not all(row["restCorrectionApplied"] for row in retarget["joints"]):
                failures.append(f"{character}/{clip}: target rest correction missing")
            for relative in ("pose_sheet.png", "preview.gif", "render.json", "diagnostics/playback.json"):
                if not (render_dir / relative).is_file():
                    failures.append(f"{character}/{clip}: missing {relative}")
            character_ids[character] = report["characterId"]
            character_rows[character] = {
                "characterId": report["characterId"],
                "mappingId": report["mappingId"],
                "animationPath": request["animationPath"],
                "animationSha256Before": hashes[0],
                "animationSha256After": hashes[1],
                "canonicalFps": report["fps"],
                "outputFps": report["outputFps"],
                "renderedSamples": report["renderedSamples"],
                "renderSamples": report["renderSamples"],
                "mappedJointCount": mapping["mappedJointCount"],
                "leftRightIdentity": mapping["leftRightVerification"]["pass"],
                "maxSemanticRotationErrorDegrees": playback["maxSemanticRotationErrorDegrees"],
                "targetMeanLegLengthSceneUnits": retarget["targetMeanLegLengthSceneUnits"],
                "actualSkinnedMesh": {"meshCount": model["meshCount"], "vertexCount": model["vertexCount"]},
                "poseSheet": str((render_dir / "pose_sheet.png").resolve()),
                "previewGif": str((render_dir / "preview.gif").resolve()),
                "diagnostics": str((render_dir / "diagnostics").resolve()),
            }

        same_sha = len({animation_sha, *(row["animationSha256Before"] for row in character_rows.values()), *(row["animationSha256After"] for row in character_rows.values())}) == 1
        if not same_sha:
            failures.append(f"{clip}: same exact animation authority proof failed")
        results[clip] = {
            "animation": {
                "path": str(animation_path),
                "sha256": animation_sha,
                "schema": animation["schema"],
                "durationSeconds": animation["durationSeconds"],
                "fps": animation["fps"],
                "frameCount": animation["frameCount"],
            },
            "rootMotion": export["rootMotion"],
            "fidelity": fidelity,
            "characters": character_rows,
            "sameExactAnimationAuthority": same_sha,
        }

    if set(character_ids) != set(CHARACTERS) or len(set(character_ids.values())) != len(CHARACTERS):
        failures.append(f"independent targets do not have three distinct character IDs: {character_ids}")
    if not results["run"]["fidelity"]["locomotionStripping"]["sourceHadPlanarLocomotion"]:
        failures.append("run: source locomotion was not detected")
    if results["run"]["fidelity"]["locomotionStripping"]["actualHipsVerticalRange"] <= 1e-4:
        failures.append("run: vertical pelvis motion was lost")
    if results["run-inplace"]["fidelity"]["locomotionStripping"]["actualHipsVerticalRange"] <= 1e-4:
        failures.append("run-inplace: vertical pelvis motion was lost")
    equivalence = _run_equivalence(_read(root / "animations" / "run" / "animation.json"), _read(root / "animations" / "run-inplace" / "animation.json"))
    failures.extend(f"canonical locomotion equivalence: {failure}" for failure in equivalence["failures"])

    expected_visual_samples_upper_bound = len(expected_cells) * MAX_SAMPLES_PER_CELL
    if rendered_visual_samples > expected_visual_samples_upper_bound:
        failures.append(
            f"visual raster workload {rendered_visual_samples} exceeds sparse upper bound {expected_visual_samples_upper_bound}"
        )

    report = {
        "schema": "motion2sheet.humanoid-motion.local-acceptance",
        "version": 1,
        "pass": not failures,
        "phase": "in-place-three-independent-real-targets-sparse-visual-proof",
        "mode": args.mode,
        "independentCharacters": list(CHARACTERS),
        "derivedCharacterBCountedAsIndependent": False,
        "expectedVisualCellCount": len(expected_cells),
        "renderedVisualSampleCount": rendered_visual_samples,
        "maxSamplesPerCell": MAX_SAMPLES_PER_CELL,
        "outputFps": EXPECTED_OUTPUT_FPS,
        "canvas": EXPECTED_CANVAS,
        "renderSamples": EXPECTED_RENDER_SAMPLES,
        "visualMatrix": visual_matrix,
        "failures": failures,
        "proof": results,
        "runVsRunInplaceCanonicalEquivalence": equivalence,
        "knownLimitations": [
            "Humanoid Motion v1 strips linear end-to-end planar travel; curved/non-linear paths may leave local residual motion.",
            "Foot contact remains diagnostic-only; Humanoid Motion v1 does not apply IK.",
        ],
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("Humanoid Motion local acceptance FAIL: " + "; ".join(failures))
    print(f"Humanoid Motion {args.mode} acceptance PASS -> {output}")


if __name__ == "__main__":
    main()
