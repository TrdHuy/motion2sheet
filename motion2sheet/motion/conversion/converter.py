from __future__ import annotations

import json
import os
import re
from pathlib import Path

from motion2sheet.anim2sheet.common.profile import load_motion_profile, load_rig_profile, resolve_character_profile
from motion2sheet.motion.roundtrip.schema import read_json, validate_animation_document, validate_rig_document

from .diagnostics import (
    conversion_fidelity,
    representation_limitations,
    source_pose_rows,
    source_retarget_fidelity,
    target_pose_rows,
)
from .mapping import load_mapping
from .normalize import normalize_animation
from .retarget import retarget_animation

PROFILE_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _relative(owner_dir: Path, target: Path) -> str:
    return Path(os.path.relpath(target.resolve(), owner_dir.resolve())).as_posix()


def _machine_id(value: str, *, fallback: str) -> str:
    value = Path(value).stem.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    if not value:
        value = fallback
    if not value[0].isalpha():
        value = f"motion_{value}"
    if not PROFILE_ID.fullmatch(value):
        value = re.sub(r"_+", "_", value)
    if not PROFILE_ID.fullmatch(value):
        raise ValueError(f"unable to derive valid Anim2Sheet machine id from {value!r}")
    return value


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False, separators=(",", ": ")) + "\n", encoding="utf-8")


def _validate_character_target(character_path: Path, target_rig_path: Path, target_rig: dict) -> dict:
    resolution = resolve_character_profile(character_path)
    character_rig = resolution["rigProfile"]
    if character_rig != target_rig:
        raise ValueError(f"character profile rig does not exactly match requested target rig: character={resolution['rigPath']} target={target_rig_path}")
    return resolution["profile"]


def convert_animation_profile(*, source_rig_path: Path, source_animation_path: Path, target_rig_path: Path, mapping_path: Path, character_profile_path: Path, output: Path) -> dict:
    source_rig_path = source_rig_path.resolve()
    source_animation_path = source_animation_path.resolve()
    target_rig_path = target_rig_path.resolve()
    mapping_path = mapping_path.resolve()
    character_profile_path = character_profile_path.resolve()
    output = output.resolve()

    source_rig = validate_rig_document(read_json(source_rig_path))
    source_animation = validate_animation_document(read_json(source_animation_path), source_rig)
    target_rig = load_rig_profile(target_rig_path)
    mapping = load_mapping(mapping_path, target_rig=target_rig)
    character = _validate_character_target(character_profile_path, target_rig_path, target_rig)
    if source_rig["coordinateSystem"] != mapping["sourceCoordinateSystem"]:
        raise ValueError("Contract B source coordinate convention differs from explicit mapping profile")

    retargeted = retarget_animation(source_rig, source_animation, target_rig, mapping)
    retarget_fidelity = source_retarget_fidelity(retargeted, mapping)
    if not retarget_fidelity["pass"]:
        if retarget_fidelity["orderingMismatches"]:
            mismatch = retarget_fidelity["orderingMismatches"][0]
            raise ValueError(
                "Contract B -> target retarget semantic gate failed: "
                f"ordering mismatch at F{mismatch['frame']} {mismatch['semantic']} "
                f"source={mismatch['source']} target={mismatch['target']}"
            )
        if retarget_fidelity["leftRightFailures"]:
            mismatch = retarget_fidelity["leftRightFailures"][0]
            raise ValueError(
                "Contract B -> target retarget semantic gate failed: "
                f"left/right identity mismatch at F{mismatch['frame']} {mismatch['pair']}"
            )
        worst = retarget_fidelity["worst"]
        raise ValueError(
            "Contract B -> target retarget semantic gate failed: "
            f"metric={worst['metric']} value={worst['value']} tolerance={worst['tolerance']} "
            f"at F{worst['frame']} {worst['semantic']}"
        )

    normalized = normalize_animation(retargeted, target_rig)
    fidelity = conversion_fidelity(retargeted, normalized, float(mapping["poseErrorToleranceMeters"]))
    source_filename = str(source_animation["source"]["filename"])
    action = _machine_id(source_filename, fallback="converted_motion")
    motion_id = f"{action}_converted"
    if not PROFILE_ID.fullmatch(motion_id):
        raise ValueError(f"generated motion id is invalid: {motion_id!r}")

    output.mkdir(parents=True, exist_ok=True)
    motion = {
        "schema": "anim2sheet.motion", "version": 2, "id": motion_id,
        "rigProfile": _relative(output, target_rig_path), "fps": float(source_animation["fps"]),
        "frameCount": int(source_animation["frameCount"]), "space": str(target_rig["motionContract"]["space"]),
        "frames": normalized["frames"],
        "provenance": {"sourceContract": {"rigId": str(source_rig["id"]), "animationId": str(source_animation["id"])}, "mappingProfile": str(mapping["id"]), "conversion": "source-authority-pose-retarget-then-motion-contract-normalization"},
    }
    animation_profile = {
        "schema": "anim2sheet.animation", "version": 2, "id": motion_id, "action": action,
        "motionProfile": "motion.json", "defaultCharacterProfile": _relative(output, character_profile_path),
        "loop": False, "interpolation": "LINEAR", "phases": [],
        "render": {"canvas": [320, 320], "sheetColumns": 8, "background": "transparent"},
    }
    basis_alignment = {
        target_name: {"source": mapping["targetToSource"][target_name], "sourceReferenceAxis": mapping["targetToSourceReferenceAxis"][target_name], "targetReferenceAxis": mapping["targetToTargetReferenceAxis"][target_name]}
        for target_name in sorted(mapping["targetToSource"])
    }
    report = {
        "schema": "motion2sheet.animation-profile-conversion", "version": 1, "sourceMotionFileRequired": False,
        "architecture": {"sourceAuthority": "Contract B animation.frames[].bones + rig.editGeometry", "retarget": "evaluate source pose -> per-bone anatomical rest-basis transfer -> GameHumanoidV2 target pose", "normalization": "derive channels declared by target rig motionContract/solvers", "contractA": "Anim2Sheet Profile Contract v2"},
        "source": {"rigId": str(source_rig["id"]), "animationId": str(source_animation["id"]), "sourceFilename": source_filename, "fps": float(source_animation["fps"]), "frameCount": int(source_animation["frameCount"])},
        "target": {"rigId": str(target_rig["id"]), "characterProfileId": str(character["id"]), "mappingId": str(mapping["id"])},
        "retarget": {"sourceStature": retargeted["sourceStature"], "targetStature": retargeted["targetStature"], "rootMotionScale": retargeted["rootMotionScale"], "mappingStrategy": "explicit-one-to-one-map-with-per-bone-source-rest-target-rest-anatomical-basis-no-fuzzy-fallback", "mappedBones": dict(sorted(mapping["targetToSource"].items())), "basisAlignment": basis_alignment},
        "retargetFidelity": retarget_fidelity,
        "normalization": {"targetMotionContract": target_rig["motionContract"], "frameDiagnostics": normalized["diagnostics"]},
        "fidelity": fidelity,
        "sourcePoseFrames": source_pose_rows(retargeted), "targetPoseFrames": target_pose_rows(retargeted),
        "limitations": representation_limitations(mapping, target_rig, normalized),
        "outputs": {"motion": "motion.json", "animation": "animation.json5", "conversion": "conversion.json"},
    }
    _write_json(output / "motion.json", motion)
    _write_json(output / "animation.json5", animation_profile)
    _write_json(output / "conversion.json", report)
    load_motion_profile(output / "motion.json", rig_profile=target_rig)
    if not fidelity["pass"]:
        raise ValueError(f"Contract A expressiveness gate failed: max={fidelity['maxErrorMeters']}m tolerance={fidelity['toleranceMeters']}m at F{fidelity['worstFrame']} {fidelity['worstSemantic']}; see {output / 'conversion.json'}")
    return report
