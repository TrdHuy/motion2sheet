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

ID = "right-overhand-smash"
READY, WINDUP, IMPACT, FOLLOW, RECOVERY = 0, 2, 4, 5, 6


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def finite(value: Any) -> bool:
    if isinstance(value, dict):
        return all(finite(v) for v in value.values())
    if isinstance(value, list):
        return all(finite(v) for v in value)
    if isinstance(value, (bool, str)) or value is None:
        return True
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def angle(a: list[float], b: list[float]) -> float:
    dot = max(-1.0, min(1.0, abs(sum(x * y for x, y in zip(a, b)))))
    return math.degrees(2.0 * math.acos(dot))


def track(animation: dict[str, Any], semantic: str) -> list[list[float]]:
    return animation["hips"]["rotations"] if semantic == "Hips" else animation["joints"][semantic]["rotations"]


def excursion(animation: dict[str, Any], semantic: str) -> float:
    values = track(animation, semantic)
    return max(angle(values[READY], sample) for sample in values)


def pose_distance(animation: dict[str, Any], a: int, b: int, semantics: tuple[str, ...]) -> float:
    return sum(angle(track(animation, semantic)[a], track(animation, semantic)[b]) for semantic in semantics)


def check(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    p = argparse.ArgumentParser()
    for name in ("animation", "committed_animation", "generation_a", "generation_b", "asset_verification", "character_dir", "mapping", "render_dir", "output"):
        p.add_argument("--" + name.replace("_", "-"), dest=name, type=Path, required=True)
    args = p.parse_args()
    failures: list[str] = []

    animation = read_animation(args.animation)
    committed = read_animation(args.committed_animation)
    artifact_bytes = args.animation.read_bytes()
    committed_bytes = args.committed_animation.read_bytes()
    gen_a = args.generation_a.read_bytes()
    gen_b = args.generation_b.read_bytes()

    check(animation["id"] == ID, "wrong animation id", failures)
    check(animation["canonicalSkeleton"] == "humanoid_v1", "wrong canonical skeleton", failures)
    check(animation["frameCount"] == 8 and float(animation["fps"]) == 8.0, "timing must stay 8 frames @ 8 FPS", failures)
    check(abs(float(animation["durationSeconds"]) - 0.875) <= 1e-9, "duration invariant mismatch", failures)
    check(animation["loop"] is False, "scenario must be non-looping", failures)
    check(animation == committed and artifact_bytes == committed_bytes, "artifact differs from committed animation authority", failures)
    check(gen_a == gen_b == committed_bytes, "generation is not deterministic/byte-identical", failures)
    check(set(animation["joints"]) == set(ROTATION_JOINTS), "semantic joint set is incomplete", failures)
    check(all(v == [0.0, 0.0, 0.0] for v in animation["root"]["translations"]), "Root translation drift", failures)
    check(finite(animation), "animation contains NaN/Inf", failures)

    metrics = {semantic: excursion(animation, semantic) for semantic in (
        "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperArm", "LeftLowerArm", "Chest", "Spine", "Hips"
    )}
    metrics.update({
        "readyToImpactComposite": pose_distance(animation, READY, IMPACT, ("Hips", "Spine", "Chest", "RightShoulder", "RightUpperArm", "RightLowerArm", "RightHand")),
        "impactToRecoveryComposite": pose_distance(animation, IMPACT, RECOVERY, ("Hips", "Spine", "Chest", "RightUpperArm", "RightLowerArm", "RightHand")),
        "followThroughToRecoveryComposite": pose_distance(animation, FOLLOW, RECOVERY, ("Chest", "RightUpperArm", "RightLowerArm", "RightHand")),
    })
    hips_shift = max(math.dist(animation["hips"]["translations"][0], v) for v in animation["hips"]["translations"])
    check(metrics["RightUpperArm"] >= 80 and metrics["RightLowerArm"] >= 120 and metrics["RightHand"] >= 100, "attacking limb excursion is too small", failures)
    check(metrics["RightUpperArm"] >= metrics["LeftUpperArm"] + 60 and metrics["RightLowerArm"] >= metrics["LeftLowerArm"] + 90, "right attacking side is not dominant", failures)
    check(metrics["Chest"] >= 25 and metrics["Spine"] >= 18 and metrics["Hips"] >= 12, "torso articulation is too small", failures)
    check(metrics["readyToImpactComposite"] >= 250, "impact is too close to ready", failures)
    check(metrics["impactToRecoveryComposite"] >= 160, "recovery is too close to impact", failures)
    check(metrics["followThroughToRecoveryComposite"] >= 120, "recovery is too close to follow-through", failures)
    check(hips_shift >= 0.05, "Hips weight shift/dip is too small", failures)

    asset = json.loads(args.asset_verification.read_text(encoding="utf-8"))
    check(asset.get("assetKey") == "warrok", "selected character must be warrok", failures)
    check(asset.get("expectedSha256") == asset.get("actualSha256") and asset.get("sha256Pass") is True, "release SHA mismatch", failures)
    check(asset.get("expectedSize") == asset.get("actualSize") and asset.get("sizePass") is True, "release size mismatch", failures)

    model, rig_path, skin_path = (args.character_dir / name for name in ("model.glb", "rig.json", "skin.json"))
    for path in (model, rig_path, skin_path):
        check(path.is_file() and path.stat().st_size > 0, f"export-character missing {path.name}", failures)
    mapping_report: dict[str, Any] = {}
    if rig_path.is_file() and skin_path.is_file():
        rig = validate_rig_document(read_json(rig_path))
        mapping = validate_character_mapping(read_mapping(args.mapping), rig)
        mapping_report = mapping_diagnostics(mapping, rig)
        validate_skin_document(read_json(skin_path), rig)
        check(mapping_report["leftRightVerification"]["pass"] is True, "character L/R mapping failed", failures)

    render_path = args.render_dir / "render.json"
    pose_sheet, preview = args.render_dir / "pose_sheet.png", args.render_dir / "preview.gif"
    diagnostics = args.render_dir / "diagnostics"
    for path in (render_path, pose_sheet, preview, diagnostics):
        check(path.exists(), f"missing render output {path.name}", failures)
    render = json.loads(render_path.read_text(encoding="utf-8")) if render_path.is_file() else {}
    expected_samples = select_even_samples(animation["frameCount"], 8)
    check(render.get("renderedSamples") == expected_samples == list(range(8)), "render samples do not cover the full timeline", failures)
    check(render.get("frameCount") == 8 and float(render.get("fps", -1)) == 8.0 and float(render.get("outputFps", -1)) == 8.0, "render timing differs from contract", failures)
    check(render.get("animationSha256Before") == render.get("animationSha256After") == sha(args.animation), "animation mutated during playback", failures)
    check(render.get("animationMutated") is False, "renderer reports animation mutation", failures)
    check(render.get("sourceFbxRequired") is False and render.get("sourceRigRequired") is False, "playback depends on Source Motion", failures)
    check(render.get("playback", {}).get("pass") is True and render.get("playback", {}).get("nanInfCheck") is True, "playback diagnostics failed", failures)
    check(render.get("rootMotion", {}).get("canonical", {}).get("isInPlace") is True, "rendered Root is not in-place", failures)
    check(render.get("semanticMapping", {}).get("leftRightVerification", {}).get("pass") is True, "render L/R mapping failed", failures)
    check(finite(render), "render report contains NaN/Inf", failures)

    required = ("model_identity.json", "skin_reconstruction.json", "semantic_mapping.json", "retarget.json", "playback.json", "root_motion.json", "contact.json", "render_request.json")
    for name in required:
        check((diagnostics / name).is_file(), f"missing diagnostic {name}", failures)
    skin_reconstruction = json.loads((diagnostics / "skin_reconstruction.json").read_text(encoding="utf-8")) if (diagnostics / "skin_reconstruction.json").is_file() else {}
    check(skin_reconstruction.get("pass") is True, "skin reconstruction failed", failures)

    report = {
        "schema": "motion2sheet.humanoid-motion.authored-attack-acceptance", "version": 1,
        "pass": not failures, "failures": failures,
        "selectedCharacter": asset,
        "animation": {"id": ID, "canonicalSkeleton": "humanoid_v1", "frameCount": 8, "fps": 8.0, "durationSeconds": 0.875, "loop": False, "attackingSide": "Right", "sha256": sha(args.animation), "schemaValidation": True, "quaternionValidation": True, "rootTranslationZero": True, "finite": finite(animation), "completeSemanticJointSet": set(animation["joints"]) == set(ROTATION_JOINTS)},
        "determinism": {"generationAEqualsGenerationB": gen_a == gen_b, "generationEqualsCommitted": gen_a == committed_bytes, "artifactEqualsCommitted": artifact_bytes == committed_bytes, "pass": gen_a == gen_b == committed_bytes == artifact_bytes},
        "motionMetricsDegrees": metrics, "hipsTranslationMaxDistanceFromReady": hips_shift,
        "phaseFrames": {"ready": 0, "anticipation": 1, "windUpPeak": 2, "acceleration": 3, "impact": 4, "followThrough": 5, "recovery": 6, "settle": 7},
        "characterExport": {"pass": model.is_file() and rig_path.is_file() and skin_path.is_file(), "modelSha256": sha(model) if model.is_file() else None, "rigSha256": sha(rig_path) if rig_path.is_file() else None, "skinSha256": sha(skin_path) if skin_path.is_file() else None, "mapping": mapping_report},
        "render": {"pass": bool(render) and render.get("playback", {}).get("pass") is True and skin_reconstruction.get("pass") is True, "selectedSamples": render.get("renderedSamples"), "canonicalFps": render.get("fps"), "outputFps": render.get("outputFps"), "canvas": render.get("layout", {}).get("cellSize"), "renderSamples": render.get("renderSamples"), "animationSha256Before": render.get("animationSha256Before"), "animationSha256After": render.get("animationSha256After"), "outputs": {"poseSheet": str(pose_sheet), "previewGif": str(preview), "renderJson": str(render_path), "diagnostics": str(diagnostics)}},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("direct-authored attack acceptance failed: " + "; ".join(failures))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
