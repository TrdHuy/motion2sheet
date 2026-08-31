from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import json5

from motion2sheet.anim2sheet.common.camera.config import load_camera_profile, resolve_camera_names
from motion2sheet.anim2sheet.registry import get_authoring_capability


PROFILE_VERSION = 2
RIG_SCHEMA = "anim2sheet.rig"
CHARACTER_SCHEMA = "anim2sheet.character"
MOTION_SCHEMA = "anim2sheet.motion"
ANIMATION_SCHEMA = "anim2sheet.animation"
PROFILE_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
ANIMATION_FIELDS = {
    "schema", "version", "id", "action", "motionProfile", "defaultCharacterProfile",
    "loop", "interpolation", "phases", "render",
}


def _linked_path(owner: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} reference must be a non-empty path string")
    path = Path(value)
    if not path.is_absolute():
        path = owner.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    return path


def _object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _profile_header(data: dict, *, schema: str, label: str, require_id: bool = True) -> None:
    if data.get("schema") != schema:
        raise ValueError(f"{label} schema must be {schema!r}")
    if data.get("version") != PROFILE_VERSION:
        raise ValueError(f"{label} version must be {PROFILE_VERSION}")
    if require_id:
        profile_id = data.get("id")
        if not isinstance(profile_id, str) or not PROFILE_ID.fullmatch(profile_id):
            raise ValueError(f"{label} id must match {PROFILE_ID.pattern}")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _vec3(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must be a 3-number array")
    return [_number(item, label) for item in value]


def _channel_specs(rig_profile: dict, key: str) -> dict[str, dict]:
    contract = _object(rig_profile.get("motionContract"), "rig profile motionContract")
    rows = contract.get(key)
    if not isinstance(rows, list):
        raise ValueError(f"rig profile motionContract.{key} must be an array")
    result: dict[str, dict] = {}
    for index, raw in enumerate(rows):
        row = _object(raw, f"rig profile motionContract.{key}[{index}]")
        semantic = row.get("semantic")
        if not isinstance(semantic, str) or not semantic.strip():
            raise ValueError(f"rig profile motionContract.{key}[{index}].semantic must be non-empty")
        if semantic in result:
            raise ValueError(f"rig profile motionContract.{key} contains duplicate semantic {semantic!r}")
        value_type = row.get("type")
        if value_type not in {"number", "vec3"}:
            raise ValueError(f"rig profile motionContract.{key} {semantic!r} has unsupported type {value_type!r}")
        required = row.get("required", True)
        if not isinstance(required, bool):
            raise ValueError(f"rig profile motionContract.{key} {semantic!r}.required must be boolean")
        result[semantic] = {"type": value_type, "required": required}
    return result


def rig_contract_identity(profile: dict) -> tuple[str, int, str]:
    return str(profile["schema"]), int(profile["version"]), str(profile["id"])


def load_rig_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    data = _object(data, "rig profile")
    _profile_header(data, schema=RIG_SCHEMA, label="rig profile")
    allowed = {"schema", "version", "id", "name", "authoringCapability", "rootObject", "rotationMode", "coordinateSystem", "restPose", "semantics", "targets", "solvers", "motionContract"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"rig profile contains unsupported fields: {sorted(unknown)}")
    required = {"authoringCapability", "coordinateSystem", "restPose", "semantics", "targets", "solvers", "motionContract"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"rig profile missing fields: {sorted(missing)}")
    get_authoring_capability(str(data["authoringCapability"]))

    bones = _object(data.get("restPose"), "rig profile restPose").get("bones")
    if not isinstance(bones, list) or not bones:
        raise ValueError("rig profile restPose.bones must be a non-empty array")
    bone_names = [str(row.get("name")) for row in bones if isinstance(row, dict)]
    if len(bone_names) != len(bones) or len(set(bone_names)) != len(bone_names):
        raise ValueError("rig profile bone names must be present and unique")

    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("rig profile targets must be a non-empty array")
    target_semantics: list[str] = []
    target_objects: list[str] = []
    for index, raw in enumerate(targets):
        row = _object(raw, f"rig profile targets[{index}]")
        semantic = row.get("semantic")
        object_name = row.get("object")
        if not isinstance(semantic, str) or not semantic:
            raise ValueError(f"rig profile targets[{index}].semantic must be non-empty")
        if not isinstance(object_name, str) or not object_name:
            raise ValueError(f"rig profile targets[{index}].object must be non-empty")
        target_semantics.append(semantic)
        target_objects.append(object_name)
    if len(target_semantics) != len(set(target_semantics)):
        raise ValueError("rig profile target semantics must be unique")
    if len(target_objects) != len(set(target_objects)):
        raise ValueError("rig profile target object names must be unique")

    motion_contract = _object(data["motionContract"], "rig profile motionContract")
    if motion_contract.get("space") != "world":
        raise ValueError("rig profile motionContract.space must currently be 'world'")
    root_translation = _object(
        motion_contract.get("rootTranslation"), "rig profile motionContract.rootTranslation"
    )
    if root_translation.get("type") != "vec3" or root_translation.get("required", True) is not True:
        raise ValueError("rig profile motionContract.rootTranslation must be required vec3")
    _channel_specs(data, "bodyChannels")
    _channel_specs(data, "jointChannels")
    motion_targets = _channel_specs(data, "targetChannels")
    unknown_targets = set(motion_targets) - set(target_semantics)
    if unknown_targets:
        raise ValueError(
            f"rig profile motionContract target channels have no target semantics: {sorted(unknown_targets)}"
        )
    return data


def load_character_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    data = _object(data, "character profile")
    _profile_header(data, schema=CHARACTER_SCHEMA, label="character profile")
    allowed = {"schema", "version", "id", "displayName", "rigProfile", "body", "equipment", "attachments", "reviewVisibleMeshes"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"character profile contains unsupported fields: {sorted(unknown)}")
    required = {"rigProfile", "body", "equipment", "reviewVisibleMeshes"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"character profile missing fields: {sorted(missing)}")
    if not isinstance(data["rigProfile"], str) or not data["rigProfile"].strip():
        raise ValueError("character profile rigProfile must be a non-empty path")
    if not isinstance(data["equipment"], list):
        raise ValueError("character profile equipment must be an array")
    if not isinstance(data["reviewVisibleMeshes"], list):
        raise ValueError("character profile reviewVisibleMeshes must be an array")
    if "attachments" in data and not isinstance(data["attachments"], list):
        raise ValueError("character profile attachments must be an array")
    return data


def resolve_character_profile(path: Path) -> dict:
    path = path.resolve()
    profile = load_character_profile(path)
    rig_path = _linked_path(path, profile["rigProfile"], "character rig profile")
    rig_profile = load_rig_profile(rig_path)
    return {"path": path, "profile": profile, "rigPath": rig_path, "rigProfile": rig_profile}


def _validate_channel_values(values: Any, specs: dict[str, dict], label: str) -> None:
    values = _object(values, label)
    unknown = set(values) - set(specs)
    required = {name for name, spec in specs.items() if spec["required"]}
    missing = required - set(values)
    if unknown or missing:
        raise ValueError(f"{label} channels invalid: missing={sorted(missing)} unknown={sorted(unknown)}")
    for name, value in values.items():
        value_type = specs[name]["type"]
        if value_type == "vec3":
            _vec3(value, f"{label}.{name}")
        else:
            _number(value, f"{label}.{name}")


def load_motion_profile(path: Path, *, rig_profile: dict | None = None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data = _object(data, "motion profile")
    _profile_header(data, schema=MOTION_SCHEMA, label="motion profile")
    allowed = {"schema", "version", "id", "rigProfile", "fps", "frameCount", "space", "frames", "provenance"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"motion profile contains unsupported fields: {sorted(unknown)}")
    required = {"rigProfile", "fps", "frameCount", "space", "frames"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"motion profile missing fields: {sorted(missing)}")
    if not isinstance(data["rigProfile"], str) or not data["rigProfile"].strip():
        raise ValueError("motion profile rigProfile must be a non-empty path")
    fps = _number(data["fps"], "motion profile fps")
    if fps <= 0:
        raise ValueError("motion profile fps must be positive")
    frame_count = data["frameCount"]
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count <= 0:
        raise ValueError("motion profile frameCount must be a positive integer")
    frames = data["frames"]
    if not isinstance(frames, list) or len(frames) != frame_count:
        raise ValueError(
            f"motion profile frameCount {frame_count} must equal frames length {len(frames) if isinstance(frames, list) else 'invalid'}"
        )
    frame_numbers = []
    for index, raw in enumerate(frames):
        row = _object(raw, f"motion frame[{index}]")
        frame = row.get("frame")
        if isinstance(frame, bool) or not isinstance(frame, int):
            raise ValueError(f"motion frame[{index}].frame must be an integer")
        frame_numbers.append(frame)
    expected = list(range(1, frame_count + 1))
    if frame_numbers != expected:
        raise ValueError(f"motion frames must be ordered, unique and contiguous {expected}, got {frame_numbers}")

    if rig_profile is not None:
        contract = _object(rig_profile["motionContract"], "rig profile motionContract")
        if data["space"] != contract["space"]:
            raise ValueError(
                f"motion profile space {data['space']!r} does not match rig motion space {contract['space']!r}"
            )
        body_specs = _channel_specs(rig_profile, "bodyChannels")
        joint_specs = _channel_specs(rig_profile, "jointChannels")
        target_specs = _channel_specs(rig_profile, "targetChannels")
        for row in frames:
            frame = int(row["frame"])
            unknown_state = set(row) - {"frame", "root", "body", "joints", "targets"}
            missing_state = {"root", "body", "joints", "targets"} - set(row)
            if unknown_state or missing_state:
                raise ValueError(
                    f"motion F{frame} state fields invalid: missing={sorted(missing_state)} unknown={sorted(unknown_state)}"
                )
            root = _object(row["root"], f"motion F{frame} root")
            if set(root) != {"translation"}:
                raise ValueError(f"motion F{frame} root must contain only translation")
            _vec3(root["translation"], f"motion F{frame} root.translation")
            _validate_channel_values(row["body"], body_specs, f"motion F{frame} body")
            _validate_channel_values(row["joints"], joint_specs, f"motion F{frame} joints")
            _validate_channel_values(row["targets"], target_specs, f"motion F{frame} targets")
    return data


def resolve_motion_profile(path: Path) -> dict:
    path = path.resolve()
    profile = load_motion_profile(path)
    rig_path = _linked_path(path, profile["rigProfile"], "motion rig profile")
    rig_profile = load_rig_profile(rig_path)
    profile = load_motion_profile(path, rig_profile=rig_profile)
    return {"path": path, "profile": profile, "rigPath": rig_path, "rigProfile": rig_profile}


def load_animation_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    data = _object(data, "animation profile")
    _profile_header(data, schema=ANIMATION_SCHEMA, label="animation profile")
    unknown = set(data) - ANIMATION_FIELDS
    if unknown:
        raise ValueError(f"animation profile contains unsupported fields: {sorted(unknown)}")
    required = {
        "id",
        "action",
        "motionProfile",
        "defaultCharacterProfile",
        "loop",
        "interpolation",
        "phases",
        "render",
    }
    missing = required - set(data)
    if missing:
        raise ValueError(f"animation profile missing fields: {sorted(missing)}")
    action = data["action"]
    if not isinstance(action, str) or not PROFILE_ID.fullmatch(action):
        raise ValueError(f"animation profile action must match {PROFILE_ID.pattern}")
    if not isinstance(data["motionProfile"], str) or not data["motionProfile"].strip():
        raise ValueError("animation profile motionProfile must be a non-empty path")
    if not isinstance(data["defaultCharacterProfile"], str) or not data["defaultCharacterProfile"].strip():
        raise ValueError("animation profile defaultCharacterProfile must be a non-empty path")
    if not isinstance(data["loop"], bool):
        raise ValueError("animation profile loop must be boolean")
    if data["interpolation"] not in {"LINEAR", "CONSTANT", "BEZIER"}:
        raise ValueError("animation profile interpolation must be LINEAR, CONSTANT or BEZIER")
    render = _object(data["render"], "animation profile render")
    render_required = {"canvas", "sheetColumns", "background"}
    render_missing = render_required - set(render)
    if render_missing:
        raise ValueError(f"animation profile render missing fields: {sorted(render_missing)}")
    canvas = render["canvas"]
    if not isinstance(canvas, list) or len(canvas) != 2 or any(
        isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in canvas
    ):
        raise ValueError("animation profile render.canvas must contain two positive integers")
    columns = render["sheetColumns"]
    if isinstance(columns, bool) or not isinstance(columns, int) or columns <= 0:
        raise ValueError("animation profile render.sheetColumns must be a positive integer")
    if render["background"] != "transparent":
        raise ValueError("animation profile render.background currently supports only 'transparent'")
    if not isinstance(data["phases"], list):
        raise ValueError("animation profile phases must be an array")
    return data


def _validate_phases(profile: dict, frame_count: int) -> None:
    names: set[str] = set()
    for index, raw in enumerate(profile["phases"]):
        phase = _object(raw, f"animation phase[{index}]")
        name = phase.get("name")
        if not isinstance(name, str) or not PROFILE_ID.fullmatch(name):
            raise ValueError(f"animation phase[{index}].name must be a valid machine id")
        if name in names:
            raise ValueError(f"animation phase names must be unique: {name!r}")
        names.add(name)
        start, end = phase.get("start"), phase.get("end")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end)):
            raise ValueError(f"animation phase {name!r} start/end must be integers")
        if start < 1 or end < start or end > frame_count:
            raise ValueError(f"animation phase {name!r} range {start}..{end} is outside 1..{frame_count}")


def resolve_execution_frames(motion: dict, requested: str | None) -> list[int]:
    motion_frames = [int(row["frame"]) for row in motion["frames"]]
    if requested is None or not requested.strip():
        return motion_frames
    try:
        frames = [int(v.strip()) for v in requested.split(",") if v.strip()]
    except ValueError as exc:
        raise ValueError("--frames must be a comma-separated list of integers") from exc
    if not frames or frames != sorted(set(frames)):
        raise ValueError(f"--frames must be non-empty, sorted and unique, got {frames}")
    invalid = [frame for frame in frames if frame not in motion_frames]
    if invalid:
        raise ValueError(f"requested frames are outside motion frames: {invalid}")
    return frames


def resolve_review_request(
    *,
    profile_path: Path,
    camera_profile_path: Path,
    frames: str | None,
    cameras: str | None,
    animation: str | None = None,
    character_profile_path: Path | None = None,
) -> dict:
    profile_path = profile_path.resolve()
    camera_profile_path = camera_profile_path.resolve()
    profile = load_animation_profile(profile_path)
    action = str(profile["action"])
    if animation and animation != action:
        raise ValueError(f"--animation {animation!r} does not match profile action {action!r}")

    motion_path = _linked_path(profile_path, profile["motionProfile"], "motion profile")
    motion_resolution = resolve_motion_profile(motion_path)
    motion = motion_resolution["profile"]
    rig_path = motion_resolution["rigPath"]
    rig_profile = motion_resolution["rigProfile"]

    if character_profile_path is None:
        character_path = _linked_path(
            profile_path, profile["defaultCharacterProfile"], "default character profile"
        )
    else:
        character_path = character_profile_path.resolve()
        if not character_path.is_file():
            raise ValueError(f"character profile not found: {character_path}")
    character_resolution = resolve_character_profile(character_path)
    character_profile = character_resolution["profile"]
    character_rig_path = character_resolution["rigPath"]
    character_rig_profile = character_resolution["rigProfile"]

    motion_identity = rig_contract_identity(rig_profile)
    character_identity = rig_contract_identity(character_rig_profile)
    if motion_identity != character_identity or rig_profile != character_rig_profile:
        raise ValueError(
            "motion rig / character rig mismatch: "
            f"motion={motion_identity}@{rig_path} character={character_identity}@{character_rig_path}"
        )

    _validate_phases(profile, int(motion["frameCount"]))
    execution_frames = resolve_execution_frames(motion, frames)
    camera_profile = load_camera_profile(camera_profile_path)
    camera_names = resolve_camera_names(camera_profile, cameras)

    capability = str(rig_profile["authoringCapability"])
    get_authoring_capability(capability)
    source = {
        "schema": "anim2sheet.resolved-review",
        "version": PROFILE_VERSION,
        "animation": action,
        "animationProfileId": str(profile["id"]),
        "motionProfileId": str(motion["id"]),
        "rigProfileId": str(rig_profile["id"]),
        "characterProfileId": str(character_profile["id"]),
        "authoringCapability": capability,
        "generator": "profile-contract-v2",
        "reviewMode": "review",
        "executionFrames": execution_frames,
        "animationProfileSource": str(profile_path),
        "animationProfileData": profile,
        "motionProfileSource": str(motion_path),
        "motionProfileData": motion,
        "rigProfileSource": str(rig_path),
        "rigProfileData": rig_profile,
        "characterProfileSource": str(character_path),
        "characterProfileData": character_profile,
        "cameraProfileSource": str(camera_profile_path),
        "cameraProfileId": str(camera_profile["id"]),
    }
    motion_frames = [int(row["frame"]) for row in motion["frames"]]
    return {
        "animation": action,
        "animationId": str(profile["id"]),
        "motionId": str(motion["id"]),
        "rigId": str(rig_profile["id"]),
        "characterId": str(character_profile["id"]),
        "cameraId": str(camera_profile["id"]),
        "authoringCapability": capability,
        "profilePath": profile_path,
        "motionProfilePath": motion_path,
        "rigProfilePath": rig_path,
        "characterProfilePath": character_path,
        "cameraProfilePath": camera_profile_path,
        "profile": profile,
        "motionProfile": motion,
        "rigProfile": rig_profile,
        "characterProfile": character_profile,
        "motionFrames": motion_frames,
        "executionFrames": execution_frames,
        "cameraProfile": camera_profile,
        "cameraNames": camera_names,
        "visibleReviewMeshes": list(character_profile.get("reviewVisibleMeshes", [])),
        "source": source,
    }
