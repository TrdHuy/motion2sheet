from __future__ import annotations

import json
import sys
from pathlib import Path


root = Path(sys.argv[1])
expected_action = sys.argv[2] if len(sys.argv) > 2 else None

required = [
    "source.json",
    "source.blend",
    "invocation.json",
    "resolved_config.json",
    "metadata.json",
    "motion_debug.json",
    "camera_config.json",
    "camera_debug.json",
    "leg_ik_debug.json",
    "reopen_debug.json",
    "object_keyposes.png",
    "skeleton_keyposes.png",
    "object_skeleton_overlay.png",
]
missing = [name for name in required if not (root / name).is_file()]
if missing:
    raise SystemExit(f"profile-driven artifact missing files: {missing}")

source = json.loads((root / "source.json").read_text(encoding="utf-8"))
invocation = json.loads((root / "invocation.json").read_text(encoding="utf-8"))
resolved = json.loads((root / "resolved_config.json").read_text(encoding="utf-8"))
metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
debug = json.loads((root / "motion_debug.json").read_text(encoding="utf-8"))
camera = json.loads((root / "camera_config.json").read_text(encoding="utf-8"))

action = str(invocation.get("animation"))
if expected_action and action != expected_action:
    raise SystemExit(f"artifact action mismatch: expected={expected_action} actual={action}")
if source.get("action") != action or metadata.get("animation") != action or resolved.get("animation") != action:
    raise SystemExit("resolved artifact action is inconsistent")

capability = invocation.get("authoringCapability")
if capability != "humanoid_v2":
    raise SystemExit(f"unexpected authoring capability: {capability}")
if source.get("authoringCapability") != capability or resolved.get("authoringCapability") != capability:
    raise SystemExit("authoring capability is inconsistent across artifact metadata")
if source.get("generator") != "profile-driven-humanoid-v1":
    raise SystemExit(f"unexpected generic generator: {source.get('generator')}")

rig_profile = Path(str(invocation.get("rigProfile", "")))
character_profile = Path(str(invocation.get("characterProfile", "")))
if rig_profile.name != "game_humanoid_v2.json5":
    raise SystemExit(f"unexpected rig profile: {rig_profile}")
if character_profile.name != "swordsman_v1.json5":
    raise SystemExit(f"unexpected character profile: {character_profile}")
if Path(str(metadata.get("rigProfile", ""))).name != rig_profile.name:
    raise SystemExit("metadata rig profile does not match invocation")
if Path(str(metadata.get("characterProfile", ""))).name != character_profile.name:
    raise SystemExit("metadata character profile does not match invocation")

frames = [int(value) for value in invocation.get("executionFrames", [])]
if not frames or frames != [int(value) for value in metadata.get("reviewFrames", [])]:
    raise SystemExit("execution frames do not match metadata")
if frames != [int(value) for value in camera.get("reviewFrames", [])]:
    raise SystemExit("execution frames do not match camera config")
if frames != [int(value) for value in debug.get("reviewFrames", [])]:
    raise SystemExit("execution frames do not match motion debug")

cameras = list(invocation.get("cameras", []))
if not cameras or cameras != list(camera.get("selectedCameras", [])):
    raise SystemExit("selected cameras are inconsistent")
for camera_name in cameras:
    camera_root = root / "cameras" / camera_name
    for frame in frames:
        if not (camera_root / "frames" / f"{frame:02d}.png").is_file():
            raise SystemExit(f"missing rendered frame: {camera_name}/F{frame}")
    for name in ("object_keyposes.png", "skeleton_keyposes.png", "object_skeleton_overlay.png"):
        if not (camera_root / name).is_file():
            raise SystemExit(f"missing camera review output: {camera_name}/{name}")
    if invocation.get("gif") and not (camera_root / "preview.gif").is_file():
        raise SystemExit(f"missing camera GIF: {camera_name}")

if invocation.get("gif") and not (root / "preview.gif").is_file():
    raise SystemExit("top-level preview.gif is missing")
if debug.get("armControl") != "deterministic_joint_fk":
    raise SystemExit("generic humanoid artifact lost deterministic joint-FK arms")
if debug.get("legControl") != "ik_with_explicit_knee_poles":
    raise SystemExit("generic humanoid artifact lost explicit-knee-pole leg IK")

print(json.dumps({
    "status": "pass",
    "action": action,
    "authoringCapability": capability,
    "rigProfile": rig_profile.name,
    "characterProfile": character_profile.name,
    "frames": frames,
    "cameras": cameras,
    "gif": bool(invocation.get("gif")),
}, indent=2))
