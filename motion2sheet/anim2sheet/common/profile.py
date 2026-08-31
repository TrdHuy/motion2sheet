from __future__ import annotations

import json
from pathlib import Path

import json5

from motion2sheet.anim2sheet.common.camera.config import load_camera_profile, resolve_camera_names
from motion2sheet.anim2sheet.registry import get_authoring_capability


REQUIRED_ANIMATION_FIELDS = {
    "action",
    "frames",
    "fps",
    "canvas",
    "sheetColumns",
    "phases",
    "poseReference",
    "jointContract",
    "rigProfile",
    "characterProfile",
}


def _linked_path(owner: Path, value: object, label: str) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = owner.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    return path


def load_animation_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    missing = REQUIRED_ANIMATION_FIELDS - set(data)
    if missing:
        raise ValueError(f"animation profile missing fields: {sorted(missing)}")
    frames = int(data["frames"])
    fps = float(data["fps"])
    if frames <= 0:
        raise ValueError("animation profile frames must be positive")
    if fps <= 0:
        raise ValueError("animation profile fps must be positive")
    canvas = data.get("canvas")
    if not isinstance(canvas, list) or len(canvas) != 2 or any(int(v) <= 0 for v in canvas):
        raise ValueError("animation profile canvas must contain two positive integers")
    return data


def load_rig_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    required = {"name", "authoringCapability", "coordinateSystem", "restPose", "semantics", "targets", "solvers"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"rig profile missing fields: {sorted(missing)}")
    get_authoring_capability(str(data["authoringCapability"]))
    bones = data.get("restPose", {}).get("bones")
    if not isinstance(bones, list) or not bones:
        raise ValueError("rig profile restPose.bones must be a non-empty array")
    bone_names = [str(row.get("name")) for row in bones if isinstance(row, dict)]
    if len(bone_names) != len(bones) or len(set(bone_names)) != len(bone_names):
        raise ValueError("rig profile bone names must be unique")
    target_rows = data.get("targets")
    if not isinstance(target_rows, list) or not target_rows:
        raise ValueError("rig profile targets must be a non-empty array")
    return data


def load_character_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    required = {"name", "rig", "body", "equipment", "reviewVisibleMeshes"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"character profile missing fields: {sorted(missing)}")
    return data


def load_pose_reference(path: Path, *, frame_count: int) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    poses = data.get("keyPoses")
    if int(data.get("version", 0)) < 2:
        raise ValueError("pose reference v2+ required")
    if not isinstance(poses, list) or len(poses) != frame_count:
        raise ValueError(f"pose reference must contain exactly {frame_count} keyPoses")
    expected = list(range(1, frame_count + 1))
    actual = [int(row.get("frame", -1)) for row in poses]
    if actual != expected:
        raise ValueError(f"pose reference frame order must be {expected}, got {actual}")
    return data


def load_joint_contract(path: Path, *, frame_count: int, rig_profile: dict) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    frames = [int(v) for v in data.get("reviewFrames", [])]
    if not frames or frames != sorted(set(frames)):
        raise ValueError(f"reviewFrames must be non-empty, sorted and unique, got {frames}")
    invalid = [frame for frame in frames if frame < 1 or frame > frame_count]
    if invalid:
        raise ValueError(f"reviewFrames outside animation frame range 1..{frame_count}: {invalid}")
    arm_cfg = rig_profile["solvers"]["arms"]
    required_pose_fields = []
    for side in ("left", "right"):
        side_cfg = arm_cfg["sides"][side]
        required_pose_fields.extend([side_cfg["elbowPoseField"], side_cfg["wristPoseField"]])
    poses = data.get("poses", {})
    for frame in frames:
        row = poses.get(str(frame))
        if not isinstance(row, dict):
            raise ValueError(f"joint contract missing frame {frame}")
        for name in required_pose_fields:
            value = row.get(name)
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError(f"F{frame} {name} must be a 3D position")
    return data


def resolve_execution_frames(contract: dict, requested: str | None) -> list[int]:
    contract_frames = [int(v) for v in contract["reviewFrames"]]
    if requested is None or not requested.strip():
        return contract_frames
    try:
        frames = [int(v.strip()) for v in requested.split(",") if v.strip()]
    except ValueError as exc:
        raise ValueError("--frames must be a comma-separated list of integers") from exc
    if not frames or frames != sorted(set(frames)):
        raise ValueError(f"--frames must be non-empty, sorted and unique, got {frames}")
    invalid = [frame for frame in frames if frame not in contract_frames]
    if invalid:
        raise ValueError(f"requested frames are outside contract reviewFrames: {invalid}")
    return frames


def resolve_review_request(
    *,
    profile_path: Path,
    camera_profile_path: Path,
    frames: str | None,
    cameras: str | None,
    animation: str | None = None,
    joint_contract_path: Path | None = None,
    rig_profile_path: Path | None = None,
    character_profile_path: Path | None = None,
) -> dict:
    profile_path = profile_path.resolve()
    camera_profile_path = camera_profile_path.resolve()
    profile = load_animation_profile(profile_path)
    action = str(profile["action"])
    if animation and animation != action:
        raise ValueError(f"--animation {animation!r} does not match profile action {action!r}")

    rig_path = (rig_profile_path.resolve() if rig_profile_path else _linked_path(profile_path, profile["rigProfile"], "rig profile"))
    character_path = (
        character_profile_path.resolve()
        if character_profile_path
        else _linked_path(profile_path, profile["characterProfile"], "character profile")
    )
    contract_path = (
        joint_contract_path.resolve()
        if joint_contract_path
        else _linked_path(profile_path, profile["jointContract"], "joint contract")
    )
    reference_path = _linked_path(profile_path, profile["poseReference"], "pose reference")

    rig_profile = load_rig_profile(rig_path)
    character_profile = load_character_profile(character_path)
    if str(character_profile["rig"]) != str(rig_profile["name"]):
        raise ValueError(
            f"character profile rig {character_profile['rig']!r} does not match rig profile {rig_profile['name']!r}"
        )
    frame_count = int(profile["frames"])
    reference = load_pose_reference(reference_path, frame_count=frame_count)
    contract = load_joint_contract(contract_path, frame_count=frame_count, rig_profile=rig_profile)
    execution_frames = resolve_execution_frames(contract, frames)
    camera_profile = load_camera_profile(camera_profile_path)
    camera_names = resolve_camera_names(camera_profile, cameras)

    capability = str(rig_profile["authoringCapability"])
    get_authoring_capability(capability)
    source = dict(profile)
    source.update(
        {
            "animation": action,
            "authoringCapability": capability,
            "generator": "profile-driven-humanoid-v1",
            "reviewMode": "review",
            "executionFrames": execution_frames,
            "rigProfileSource": str(rig_path),
            "rigProfileData": rig_profile,
            "characterProfileSource": str(character_path),
            "characterProfileData": character_profile,
            "poseReferenceSource": str(reference_path),
            "poseReferenceData": reference,
            "jointContractSource": str(contract_path),
            "jointContractData": contract,
            "cameraProfileSource": str(camera_profile_path),
        }
    )
    return {
        "animation": action,
        "authoringCapability": capability,
        "profilePath": profile_path,
        "rigProfilePath": rig_path,
        "characterProfilePath": character_path,
        "jointContractPath": contract_path,
        "cameraProfilePath": camera_profile_path,
        "profile": profile,
        "rigProfile": rig_profile,
        "characterProfile": character_profile,
        "referencePath": reference_path,
        "reference": reference,
        "contract": contract,
        "contractFrames": [int(v) for v in contract["reviewFrames"]],
        "executionFrames": execution_frames,
        "cameraProfile": camera_profile,
        "cameraNames": camera_names,
        "visibleReviewMeshes": list(character_profile.get("reviewVisibleMeshes", [])),
        "source": source,
    }
