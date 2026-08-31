from __future__ import annotations

import json
from pathlib import Path

import json5

REQUIRED_PROFILE_FIELDS = {"action", "frames", "fps", "canvas", "sheetColumns", "phases", "poseReference"}


def load_profile(path: Path) -> dict:
    data = json5.loads(path.read_text(encoding="utf-8"))
    missing = REQUIRED_PROFILE_FIELDS - set(data)
    if missing:
        raise ValueError(f"profile missing fields: {sorted(missing)}")
    if data.get("action") != "gale_slash":
        raise ValueError(f"Gale Slash profile action must be 'gale_slash', got {data.get('action')!r}")
    return data


def load_pose_reference(profile_path: Path, profile: dict) -> tuple[Path, dict]:
    path = Path(str(profile["poseReference"]))
    if not path.is_absolute():
        path = profile_path.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"pose reference not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    frames = int(profile["frames"])
    poses = data.get("keyPoses")
    if int(data.get("version", 0)) < 2:
        raise ValueError("pose reference v2+ required")
    if not isinstance(poses, list) or len(poses) != frames:
        raise ValueError(f"pose reference must contain exactly {frames} keyPoses")
    expected = list(range(1, frames + 1))
    actual = [int(row.get("frame", -1)) for row in poses]
    if actual != expected:
        raise ValueError(f"pose reference frame order must be {expected}, got {actual}")
    return path, data
