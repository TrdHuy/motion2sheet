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

ID = "heavy-right-cross"
READY, PRELOAD, COIL, LAUNCH, ACCELERATION, IMPACT, FOLLOW, RECOIL, RECOVER, SETTLE = range(10)


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


def angle(first: list[float], second: list[float]) -> float:
    dot = max(-1.0, min(1.0, abs(sum(a * b for a, b in zip(first, second)))))
    return math.degrees(2.0 * math.acos(dot))


def track(animation: dict[str, Any], semantic: str) -> list[list[float]]:
    return animation["hips"]["rotations"] if semantic == "Hips" else animation["joints"][semantic]["rotations"]


def excursion(animation: dict[str, Any], semantic: str) -> float:
    values = track(animation, semantic)
    return max(angle(values[READY], sample) for sample in values)


def pose_distance(animation: dict[str, Any], first: int, second: int, semantics: tuple[str, ...]) -> float:
    return sum(angle(track(animation, semantic)[first], track(animation, semantic)[second]) for semantic in semantics)


def rotate_vector(quaternion: list[float], vector: tuple[float, float, float]) -> tuple[float, float, float]:
    w, x, y, z = quaternion
    vx, vy, vz = vector
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def right_arm_direction(animation: dict[str, Any], semantic: str, frame: int) -> tuple[float, float, float]:
    return rotate_vector(track(animation, semantic)[frame], (-1.0, 0.0, 0.0))


def forward_alignment(animation: dict[str, Any], semantic: str, frame: int) -> float:
    return -right_arm_direction(animation, semantic, frame)[1]


def vector_angle(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    denominator = math.sqrt(sum(v * v for v in first) * sum(v * v for v in second))
    dot = sum(a * b for a, b in zip(first, second)) / denominator
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def check(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "animation",
        "committed_animation",
        "generation_a",
        "generation_b",
        "asset_verification",
        "character_dir",
        "mapping",
        "render_dir",
        "output",
    ):
        parser.add_argument("--" + name.replace("_", "-"), dest=name, type=Path, required=True)
    args = parser.parse_args()
    failures: list[str] = []

    animation = read_animation(args.animation)
    committed = read_animation(args.committed_animation)
    artifact_bytes = args.animation.read_bytes()
    committed_bytes = args.committed_animation.read_bytes()
    generation_a = args.generation_a.read_bytes()
    generation_b = args.generation_b.read_bytes()

    check(animation["id"] == ID, "wrong animation id", failures)
    check(animation["canonicalSkeleton"] == "humanoid_v1", "wrong canonical skeleton", failures)
    check(animation["frameCount"] == 10 and float(animation["fps"]) == 8.0, "timing must stay locked at 10 frames @ 8 FPS", failures)
    check(abs(float(animation["durationSeconds"]) - 1.125) <= 1e-9, "duration invariant mismatch", failures)
    check(animation["loop"] is False, "Heavy Right Cross must be non-looping", failures)
    check(animation == committed and artifact_bytes == committed_bytes, "artifact differs from committed animation authority", failures)
    check(generation_a == generation_b == committed_bytes, "generation is not deterministic/byte-identical", failures)
    check(set(animation["joints"]) == set(ROTATION_JOINTS), "semantic joint set is incomplete", failures)
    check(all(sample == [0.0, 0.0, 0.0] for sample in animation["root"]["translations"]), "Root translation drift", failures)
    check(finite(animation), "animation contains NaN/Inf", failures)

    metrics = {semantic: excursion(animation, semantic) for semantic in (
        "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperArm", "LeftLowerArm",
        "Hips", "Spine", "Chest", "RightUpperLeg", "RightFoot",
    )}
    metrics.update({
        "coilToLaunchHips": angle(track(animation, "Hips")[COIL], track(animation, "Hips")[LAUNCH]),
        "coilToLaunchRightUpperArm": angle(track(animation, "RightUpperArm")[COIL], track(animation, "RightUpperArm")[LAUNCH]),
        "readyToImpactComposite": pose_distance(animation, READY, IMPACT, ("Hips", "Spine", "Chest", "RightShoulder", "RightUpperArm", "RightLowerArm", "RightHand", "RightFoot")),
        "impactToFollowComposite": pose_distance(animation, IMPACT, FOLLOW, ("Hips", "Spine", "Chest", "RightShoulder", "RightUpperArm", "RightLowerArm", "RightHand", "RightFoot")),
        "impactToRecoilComposite": pose_distance(animation, IMPACT, RECOIL, ("Hips", "Spine", "Chest", "RightUpperArm", "RightLowerArm", "RightHand")),
        "followToRecoilComposite": pose_distance(animation, FOLLOW, RECOIL, ("Chest", "RightUpperArm", "RightLowerArm", "RightHand")),
        "recoilToRecoverComposite": pose_distance(animation, RECOIL, RECOVER, ("Chest", "RightUpperArm", "RightLowerArm", "RightHand")),
        "recoverToSettleComposite": pose_distance(animation, RECOVER, SETTLE, ("Chest", "RightUpperArm", "RightLowerArm", "RightHand")),
    })

    alignments = {
        str(frame): {semantic: forward_alignment(animation, semantic, frame) for semantic in ("RightUpperArm", "RightLowerArm")}
        for frame in (COIL, LAUNCH, ACCELERATION, IMPACT, FOLLOW, RECOIL, RECOVER)
    }
    impact_directions = {semantic: list(right_arm_direction(animation, semantic, IMPACT)) for semantic in ("RightUpperArm", "RightLowerArm")}
    impact_elbow_bend = vector_angle(
        right_arm_direction(animation, "RightUpperArm", IMPACT),
        right_arm_direction(animation, "RightLowerArm", IMPACT),
    )
    impact_wrist_to_forearm = angle(track(animation, "RightLowerArm")[IMPACT], track(animation, "RightHand")[IMPACT])
    metrics["impactElbowBendDegrees"] = impact_elbow_bend
    metrics["impactWristToForearmDegrees"] = impact_wrist_to_forearm

    hips_y = [float(sample[1]) for sample in animation["hips"]["translations"]]
    hips_shift = max(math.dist(animation["hips"]["translations"][READY], sample) for sample in animation["hips"]["translations"])
    coil_to_impact_forward_shift = hips_y[COIL] - hips_y[IMPACT]

    check(65.0 <= metrics["RightUpperArm"] <= 100.0, "right upper-arm excursion is outside the Heavy Right Cross range", failures)
    check(110.0 <= metrics["RightLowerArm"] <= 145.0, "right forearm excursion is outside the Heavy Right Cross range", failures)
    check(70.0 <= metrics["RightHand"] <= 135.0, "RightHand excursion is implausibly small or over-rotated", failures)
    check(metrics["LeftUpperArm"] <= 12.0 and metrics["LeftLowerArm"] <= 12.0, "left guard moves too much", failures)
    check(metrics["RightUpperArm"] >= metrics["LeftUpperArm"] + 55.0, "right upper arm is not dominant over left guard", failures)
    check(metrics["RightLowerArm"] >= metrics["LeftLowerArm"] + 100.0, "right lower arm is not dominant over left guard", failures)

    check(30.0 <= metrics["Hips"] <= 50.0, "Hips rotation is too small or overtwisted", failures)
    check(12.0 <= metrics["Spine"] <= 28.0, "Spine rotation is too small or overtwisted", failures)
    check(18.0 <= metrics["Chest"] <= 35.0, "Chest rotation is too small or overtwisted", failures)
    check(metrics["Hips"] >= metrics["Chest"] + 8.0, "Hips must provide the largest torso-chain rotation", failures)
    check(metrics["Chest"] >= metrics["Spine"] + 3.0, "Chest should add rotation after Spine without corkscrewing", failures)
    check(20.0 <= metrics["RightUpperLeg"] <= 45.0, "rear-leg contribution is too small or exaggerated", failures)
    check(25.0 <= metrics["RightFoot"] <= 55.0, "rear-foot pivot is too small or exaggerated", failures)

    check(15.0 <= metrics["coilToLaunchHips"] <= 35.0, "F2->F3 Hips reversal is too weak or too abrupt", failures)
    check(metrics["coilToLaunchHips"] >= metrics["coilToLaunchRightUpperArm"] + 4.0, "F2->F3 is not body-led; the arm leaves before sufficient Hips reversal", failures)
    check(alignments[str(LAUNCH)]["RightUpperArm"] >= 0.25, "right upper arm does not begin forward launch at F3", failures)
    check(alignments[str(LAUNCH)]["RightLowerArm"] < 0.20, "right forearm extends too early at F3", failures)
    check(alignments[str(ACCELERATION)]["RightUpperArm"] >= 0.75, "right upper arm lacks forward acceleration at F4", failures)
    check(alignments[str(ACCELERATION)]["RightLowerArm"] >= 0.60, "right forearm lacks forward acceleration at F4", failures)

    for semantic, direction in impact_directions.items():
        check(-direction[1] >= 0.95, f"{semantic} is not aligned to canonical forward at F5 impact", failures)
        check(abs(direction[0]) <= 0.20, f"{semantic} has too much lateral sweep at F5 impact", failures)
        check(abs(direction[2]) <= 0.20, f"{semantic} has too much vertical deviation at F5 impact", failures)

    check(5.0 <= impact_elbow_bend <= 15.0, "F5 elbow must remain slightly flexed instead of locking", failures)
    check(impact_wrist_to_forearm <= 25.0, "F5 wrist is not aligned naturally with the forearm", failures)

    check(alignments[str(FOLLOW)]["RightUpperArm"] >= 0.95, "right upper arm loses commitment too early at F6", failures)
    check(alignments[str(FOLLOW)]["RightLowerArm"] >= 0.95, "right forearm loses commitment too early at F6", failures)
    check(metrics["impactToFollowComposite"] <= 35.0, "F6 is too different from F5 to be a small overshoot", failures)
    check(alignments[str(IMPACT)]["RightUpperArm"] >= alignments[str(FOLLOW)]["RightUpperArm"], "F6 upper-arm extension exceeds the F5 hero impact", failures)
    check(alignments[str(IMPACT)]["RightLowerArm"] >= alignments[str(FOLLOW)]["RightLowerArm"], "F6 forearm extension exceeds the F5 hero impact", failures)

    recoil_alignment = alignments[str(RECOIL)]["RightLowerArm"]
    recover_alignment = alignments[str(RECOVER)]["RightLowerArm"]
    check(0.35 <= recoil_alignment <= 0.85, "F7 must be a partial recoil, not full guard or continued impact", failures)
    check(recoil_alignment <= alignments[str(FOLLOW)]["RightLowerArm"] - 0.20, "F7 forearm has not begun a meaningful recoil", failures)
    check(recover_alignment <= recoil_alignment - 0.20, "F8 must continue recovery after the partial F7 recoil", failures)
    check(60.0 <= metrics["followToRecoilComposite"] <= 130.0, "F6->F7 recoil is too weak or snaps too far in one 125ms frame", failures)
    check(80.0 <= metrics["impactToRecoilComposite"] <= 140.0, "F5->F7 recoil amount is outside the staged-recovery range", failures)

    check(0.10 <= coil_to_impact_forward_shift <= 0.18, "Hips forward weight transfer must be meaningful without becoming an in-place slide", failures)
    check(0.05 <= hips_shift <= 0.18, "Hips local translation is too small or too large for in-place mechanics", failures)
    check(300.0 <= metrics["readyToImpactComposite"] <= 520.0, "Ready->Impact pose change is too small or globally over-exaggerated", failures)
    check(angle(track(animation, "RightUpperArm")[READY], track(animation, "RightUpperArm")[SETTLE]) <= 5.0, "F9 does not settle near the right-hand guard", failures)

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
    pose_sheet = args.render_dir / "pose_sheet.png"
    preview = args.render_dir / "preview.gif"
    diagnostics = args.render_dir / "diagnostics"
    for path in (render_path, pose_sheet, preview, diagnostics):
        check(path.exists(), f"missing render output {path.name}", failures)

    render = json.loads(render_path.read_text(encoding="utf-8")) if render_path.is_file() else {}
    expected_samples = select_even_samples(animation["frameCount"], 10)
    check(render.get("renderedSamples") == expected_samples == list(range(10)), "render samples do not cover locked F0..F9 timeline", failures)
    check(render.get("frameCount") == 10 and float(render.get("fps", -1)) == 8.0 and float(render.get("outputFps", -1)) == 8.0, "render timing differs from locked contract", failures)
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

    skin_reconstruction_path = diagnostics / "skin_reconstruction.json"
    skin_reconstruction = json.loads(skin_reconstruction_path.read_text(encoding="utf-8")) if skin_reconstruction_path.is_file() else {}
    check(skin_reconstruction.get("pass") is True, "skin reconstruction failed", failures)

    report = {
        "schema": "motion2sheet.humanoid-motion.authored-attack-acceptance",
        "version": 3,
        "pass": not failures,
        "failures": failures,
        "selectedCharacter": asset,
        "animation": {
            "id": ID,
            "canonicalSkeleton": "humanoid_v1",
            "frameCount": 10,
            "fps": 8.0,
            "durationSeconds": 1.125,
            "loop": False,
            "attackingSide": "Right",
            "impactFrame": 5,
            "impactTimeSeconds": 0.625,
            "sha256": sha(args.animation),
            "schemaValidation": True,
            "quaternionValidation": True,
            "rootTranslationZero": True,
            "finite": finite(animation),
            "completeSemanticJointSet": set(animation["joints"]) == set(ROTATION_JOINTS),
        },
        "determinism": {
            "generationAEqualsGenerationB": generation_a == generation_b,
            "generationEqualsCommitted": generation_a == committed_bytes,
            "artifactEqualsCommitted": artifact_bytes == committed_bytes,
            "pass": generation_a == generation_b == committed_bytes == artifact_bytes,
        },
        "motionMetricsDegrees": metrics,
        "forwardAlignmentToMinusY": alignments,
        "impactArmDirections": impact_directions,
        "hipsTranslationMaxDistanceFromReady": hips_shift,
        "coilToImpactForwardHipsShift": coil_to_impact_forward_shift,
        "phaseFrames": {
            "ready": READY,
            "preload": PRELOAD,
            "maximumCoil": COIL,
            "launch": LAUNCH,
            "acceleration": ACCELERATION,
            "impactHeroPose": IMPACT,
            "followThrough": FOLLOW,
            "recoil": RECOIL,
            "recoverStance": RECOVER,
            "settle": SETTLE,
        },
        "mechanicsConstraints": {
            "impactElbowBendDegrees": impact_elbow_bend,
            "impactWristToForearmDegrees": impact_wrist_to_forearm,
            "impactArmAlignmentAtF5": alignments[str(IMPACT)],
            "followArmAlignmentAtF6": alignments[str(FOLLOW)],
            "recoilArmAlignmentAtF7": alignments[str(RECOIL)],
            "recoverArmAlignmentAtF8": alignments[str(RECOVER)],
        },
        "characterExport": {"pass": model.is_file() and rig_path.is_file() and skin_path.is_file(), "mapping": mapping_report},
        "render": render,
        "skinReconstruction": skin_reconstruction,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit("direct-authored Heavy Right Cross acceptance failed: " + "; ".join(failures))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
