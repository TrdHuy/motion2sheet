from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from motion2sheet.motion.humanoid_motion.mapping import mapping_diagnostics, read_mapping, validate_character_mapping
from motion2sheet.motion.humanoid_motion.runner import select_even_samples
from motion2sheet.motion.humanoid_motion.schema import ROTATION_JOINTS, read_animation
from motion2sheet.motion.roundtrip.schema import read_json, validate_rig_document
from motion2sheet.motion.skin import validate_skin_document

ANIMATION_ID = "right-overhand-smash"
ATTACKING_SIDE = "Right"
READY_FRAME = 0
WINDUP_FRAME = 2
IMPACT_FRAME = 4
FOLLOW_THROUGH_FRAME = 5
RECOVERY_FRAME = 6
EXPECTED_SAMPLE_COUNT = 8
EXPECTED_OUTPUT_FPS = 8.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_tree(value: Any) -> bool:
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_tree(item) for item in value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def angle_degrees(first: list[float], second: list[float]) -> float:
    dot = abs(sum(a * b for a, b in zip(first, second)))
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, dot))))


def track(animation: dict[str, Any], semantic: str) -> list[list[float]]:
    return animation["hips"]["rotations"] if semantic == "Hips" else animation["joints"][semantic]["rotations"]


def excursion(animation: dict[str, Any], semantic: str) -> float:
    values = track(animation, semantic)
    return max(angle_degrees(values[READY_FRAME], sample) for sample in values)


def pose_distance(animation: dict[str, Any], first: int, second: int, semantics: tuple[str, ...]) -> float:
    return sum(angle_degrees(track(animation, semantic)[first], track(animation, semantic)[second]) for semantic in semantics)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--animation", type=Path, required=True)
    parser.add_argument("--committed-animation", type=Path, required=True)
    parser.add_argument("--generation-a", type=Path, required=True)
    parser.add_argument("--generation-b", type=Path, required=True)
    parser.add_argument("--asset-verification", type=Path, required=True)
    parser.add_argument("--character-dir", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--render-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    failures: list[str] = []
    animation = read_animation(args.animation)
    committed = read_animation(args.committed_animation)
    animation_bytes = args.animation.read_bytes()
    committed_bytes = args.committed_animation.read_bytes()
    generation_a = args.generation_a.read_bytes()
    generation_b = args.generation_b.read_bytes()

    require(animation["id"] == ANIMATION_ID, "unexpected animation id", failures)
    require(animation["canonicalSkeleton"] == "humanoid_v1", "canonical skeleton must be humanoid_v1", failures)
    require(animation["frameCount"] == 8 and float(animation["fps"]) == 8.0, "canonical timing must stay 8 frames @ 8 FPS", failures)
    require(abs(float(animation["durationSeconds"]) - 7.0 / 8.0) <= 1e-9, "duration invariant mismatch", failures)
    require(animation["loop"] is False, "scenario is non-looping", failures)
    require(animation == committed and animation_bytes == committed_bytes, "artifact animation differs from committed authority", failures)
    require(generation_a == generation_b == committed_bytes, "deterministic regeneration is not byte-identical", failures)
    require(all(sample == [0.0, 0.0, 0.0] for sample in animation["root"]["translations"]), "Root translation drift detected", failures)
    require(set(animation["joints"]) == set(ROTATION_JOINTS), "complete semantic joint set missing", failures)
    require(finite_tree(animation), "animation contains NaN/Inf", failures)

    metrics = {
        "RightUpperArmExcursion": excursion(animation, "RightUpperArm"),
        "RightLowerArmExcursion": excursion(animation, "RightLowerArm"),
        "RightHandExcursion": excursion(animation, "RightHand"),
        "LeftUpperArmExcursion": excursion(animation, "LeftUpperArm"),
        "LeftLowerArmExcursion": excursion(animation, "LeftLowerArm"),
        "ChestExcursion": excursion(animation, "Chest"),
        "SpineExcursion": excursion(animation, "Spine"),
        "HipsExcursion": excursion(animation, "Hips"),
    }
    metrics["readyToImpactComposite"] = pose_distance(
        animation, READY_FRAME, IMPACT_FRAME,
        ("Hips", "Spine", "Chest", "RightShoulder", "RightUpperArm", "RightLowerArm", "RightHand"),
    )
    metrics["impactToRecoveryComposite"] = pose_distance(
        animation, IMPACT_FRAME, RECOVERY_FRAME,
        ("Hips", "Spine", "Chest", "RightUpperArm", "RightLowerArm", "RightHand"),
    )
    metrics["followThroughToRecoveryComposite"] = pose_distance(
        animation, FOLLOW_THROUGH_FRAME, RECOVERY_FRAME,
        ("Chest", "RightUpperArm", "RightLowerArm", "RightHand"),
    )
    hips_translation_range = max(math.dist(animation["hips"]["translations"][0], sample) for sample in animation["hips"]["translations"])

    require(metrics["RightUpperArmExcursion"] >= 80.0, "RightUpperArm excursion is too small", failures)
    require(metrics["RightLowerArmExcursion"] >= 120.0, "RightLowerArm excursion is too small", failures)
    require(metrics["RightHandExcursion"] >= 100.0, "RightHand excursion is too small", failures)
    require(metrics["RightUpperArmExcursion"] >= metrics["LeftUpperArmExcursion"] + 60.0, "right upper arm is not dominant", failures)
    require(metrics["RightLowerArmExcursion"] >= metrics["LeftLowerArmExcursion"] + 90.0, "right lower arm is not dominant", failures)
    require(metrics["ChestExcursion"] >= 25.0 and metrics["SpineExcursion"] >= 18.0 and metrics["HipsExcursion"] >= 12.0, "torso articulation is too small", failures)
    require(metrics["readyToImpactComposite"] >= 250.0, "impact is not sufficiently distinct from ready", failures)
    require(metrics["impactToRecoveryComposite"] >= 160.0, "recovery is not sufficiently distinct from impact", failures)
    require(metrics["followThroughToRecoveryComposite"] >= 120.0, "recovery is not sufficiently distinct from follow-through", failures)
    require(hips_translation_range >= 0.05, "Hips local weight shift/dip is too small", failures)

    asset = json.loads(args.asset_verification.read_text(encoding="utf-8"))
    require(asset.get("assetKey") == "warrok", "selected release asset must be warrok", failures)
    require(asset.get("expectedSha256") == asset.get("actualSha256") and asset.get("sha256Pass") is True, "release SHA-256 mismatch", failures)
    require(asset.get("expectedSize") == asset.get("actualSize") and asset.get("sizePass") is True, "release byte-size mismatch", failures)

    model_path = args.character_dir / "model.glb"
    rig_path = args.character_dir / "rig.json"
    skin_path = args.character_dir / "skin.json"
    for path, label in ((model_path, "model.glb"), (rig_path, "rig.json"), (skin_path, "skin.json")):
        require(path.is_file() and path.stat().st_size > 0, f"export-character missing {label}", failures)

    mapping_report: dict[str, Any] = {"pass": False}
    skin_validation: dict[str, Any] = {"pass": False}
    if rig_path.is_file() and skin_path.is_file():
        rig = validate_rig_document(read_json(rig_path))
        mapping = validate_character_mapping(read_mapping(args.mapping), rig)
        mapping_report = mapping_diagnostics(mapping, rig)
        validate_skin_document(read_json(skin_path), rig)
        skin_validation = {"pass": True, "rigId": rig["id"]}
        require(mapping_report["leftRightVerification"]["pass"] is True, "Mixamo semantic L/R mapping failed", failures)

    render_json = args.render_dir / "render.json"
    pose_sheet = args.render_dir / "pose_sheet.png"
    preview_gif = args.render_dir / "preview.gif"
    diagnostics_dir = args.render_dir / "diagnostics"
    for path, label in ((render_json, "render.json"), (pose_sheet, "pose_sheet.png"), (preview_gif, "preview.gif"), (diagnostics_dir, "diagnostics/")):
        require(path.exists(), f"missing render output {label}", failures)

    render: dict[str, Any] = {}
    expected_samples = select_even_samples(animation["frameCount"], EXPECTED_SAMPLE_COUNT)
    selected_samples: list[int] = []
    if render_json.is_file():
        render = json.loads(render_json.read_text(encoding="utf-8"))
        selected_samples = render.get("renderedSamples", [])
        require(render.get("animationId") == ANIMATION_ID, "render used wrong animation", failures)
        require(render.get("frameCount") == animation["frameCount"], "render frameCount mismatch", failures)
        require(float(render.get("fps", -1)) == float(animation["fps"]), "canonical FPS changed during render", failures)
        require(float(render.get("outputFps", -1)) == EXPECTED_OUTPUT_FPS, "presentation FPS must be 8", failures)
        require(selected_samples == expected_samples == list(range(8)), "render samples must cover the complete canonical timeline", failures)
        require(render.get("animationSha256Before") == render.get("animationSha256After") == sha256(args.animation), "animation SHA changed during playback", failures)
        require(render.get("animationMutated") is False, "renderer reports animation mutation", failures)
        require(render.get("sourceFbxRequired") is False and render.get("sourceRigRequired") is False, "render incorrectly depends on Source Motion", failures)
        require(render.get("playback", {}).get("pass") is True and render.get("playback", {}).get("nanInfCheck") is True, "playback diagnostics failed", failures)
        require(render.get("rootMotion", {}).get("isInPlace") is True, "rendered Root is not in-place", failures)
        require(render.get("semanticMapping", {}).get("leftRightVerification", {}).get("pass") is True, "render L/R mapping failed", failures)
        require(finite_tree(render), "render report contains NaN/Inf", failures)

    required_diagnostics = (
        "model_identity.json", "skin_reconstruction.json", "semantic_mapping.json", "retarget.json",
        "playback.json", "root_motion.json", "contact.json", "render_request.json",
    )
    for name in required_diagnostics:
        require((diagnostics_dir / name).is_file(), f"missing render diagnostic {name}", failures)
    skin_reconstruction: dict[str, Any] = {}
    skin_reconstruction_path = diagnostics_dir / "skin_reconstruction.json"
    if skin_reconstruction_path.is_file():
        skin_reconstruction = json.loads(skin_reconstruction_path.read_text(encoding="utf-8"))
        require(skin_reconstruction.get("pass") is True, "skin reconstruction failed", failures)
        require(finite_tree(skin_reconstruction), "skin reconstruction contains NaN/Inf", failures)

    report = {
        "schema": "motion2sheet.humanoid-motion.authored-attack-acceptance",
        "version": 1,
        "pass": not failures,
        "failures": failures,
        "selectedCharacter": asset,
        "animation": {
            "id": animation["id"], "canonicalSkeleton": animation["canonicalSkeleton"],
            "frameCount": animation["frameCount"], "fps": animation["fps"],
            "durationSeconds": animation["durationSeconds"], "loop": animation["loop"],
            "attackingSide": ATTACKING_SIDE, "sha256": sha256(args.animation),
            "schemaValidation": True, "quaternionValidation": True,
            "rootTranslationZero": all(sample == [0.0, 0.0, 0.0] for sample in animation["root"]["translations"]),
            "finite": finite_tree(animation), "completeSemanticJointSet": set(animation["joints"]) == set(ROTATION_JOINTS),
        },
        "determinism": {
            "generationAEqualsGenerationB": generation_a == generation_b,
            "generationEqualsCommitted": generation_a == committed_bytes,
            "artifactEqualsCommitted": animation_bytes == committed_bytes,
            "pass": generation_a == generation_b == committed_bytes == animation_bytes,
        },
        "motionMetricsDegrees": metrics,
        "hipsTranslationMaxDistanceFromReady": hips_translation_range,
        "phaseFrames": {"ready": 0, "anticipation": 1, "windUpPeak": 2, "acceleration": 3, "impact": 4, "followThrough": 5, "recovery": 6, "settle": 7},
        "characterExport": {
            "pass": model_path.is_file() and rig_path.is_file() and skin_path.is_file(),
            "modelSha256": sha256(model_path) if model_path.is_file() else None,
            "rigSha256": sha256(rig_path) if rig_path.is_file() else None,
            "skinSha256": sha256(skin_path) if skin_path.is_file() else None,
            "mapping": mapping_report, "skinValidation": skin_validation,
        },
        "render": {
            "pass": bool(render) and render.get("playback", {}).get("pass") is True and skin_reconstruction.get("pass") is True,
            "selectedSamples": selected_samples, "expectedSamples": expected_samples,
            "canonicalFps": animation["fps"], "outputFps": render.get("outputFps"),
            "canvas": render.get("layout", {}).get("cellSize"), "renderSamples": render.get("renderSamples"),
            "animationSha256Before": render.get("animationSha256Before"), "animationSha256After": render.get("animationSha256After"),
            "outputs": {"poseSheet": str(pose_sheet), "previewGif": str(preview_gif), "renderJson": str(render_json), "diagnostics": str(diagnostics_dir)},
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("direct-authored attack acceptance failed: " + "; ".join(failures))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
