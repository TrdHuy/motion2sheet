from __future__ import annotations

import json
from pathlib import Path

CORE_REVIEW_FRAMES = {1, 6, 7, 8}
FRAME_MIN = 1
FRAME_MAX = 16


def load_joint_contract(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("armControl") != "deterministic_joint_fk":
        raise ValueError("joint contract must use deterministic_joint_fk")
    frames = [int(v) for v in data.get("reviewFrames", [])]
    if not frames or frames != sorted(set(frames)):
        raise ValueError(f"reviewFrames must be non-empty, sorted and unique, got {frames}")
    if any(frame < FRAME_MIN or frame > FRAME_MAX for frame in frames):
        raise ValueError(f"reviewFrames must stay inside F1-F16, got {frames}")
    missing = CORE_REVIEW_FRAMES - set(frames)
    if missing:
        raise ValueError(f"Gale Slash contract must retain frozen core frames; missing={sorted(missing)}")
    poses = data.get("poses", {})
    for frame in frames:
        row = poses.get(str(frame))
        if not isinstance(row, dict):
            raise ValueError(f"joint contract missing frame {frame}")
        for name in ("leftElbow", "leftWrist", "rightElbow", "rightWrist"):
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
