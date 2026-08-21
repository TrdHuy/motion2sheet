from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image

from .model import PoseSequence, missing_joints


class ValidationError(RuntimeError):
    pass


def validate_sequence(sequence: PoseSequence, expected_frames: int | None = None) -> list[str]:
    errors: list[str] = []
    width, height = sequence.canvas
    if expected_frames is not None and len(sequence.frames) != expected_frames:
        errors.append(f"expected {expected_frames} frames, got {len(sequence.frames)}")

    for index, frame in enumerate(sequence.frames, start=1):
        missing = missing_joints(frame)
        if missing:
            errors.append(f"frame {index}: missing joints: {', '.join(missing)}")
        for joint, (x, y) in frame.joints.items():
            if not math.isfinite(x) or not math.isfinite(y):
                errors.append(f"frame {index}: joint {joint} is not finite")
            elif not (0 <= x < width and 0 <= y < height):
                errors.append(f"frame {index}: joint {joint} outside canvas at ({x:.2f}, {y:.2f})")

    max_jump = max(width, height) * 0.5
    for index in range(1, len(sequence.frames)):
        prev = sequence.frames[index - 1]
        curr = sequence.frames[index]
        shared = set(prev.joints).intersection(curr.joints)
        for joint in shared:
            x1, y1 = prev.joints[joint]
            x2, y2 = curr.joints[joint]
            if math.hypot(x2 - x1, y2 - y1) > max_jump:
                errors.append(f"frame {index}->{index+1}: joint {joint} jumps too far")
    return errors


def validate_output_directory(root: Path) -> list[str]:
    errors: list[str] = []
    metadata_path = root / "metadata.json"
    if not metadata_path.exists():
        return ["metadata.json is missing"]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_frames = int(metadata["frames"])
    canvas = tuple(metadata["canvas"])
    columns = int(metadata["sheetColumns"])

    for direction in metadata["directions"]:
        direction_dir = root / direction
        pose_path = direction_dir / "pose.json"
        sheet_path = direction_dir / "pose_sheet.png"
        frames_dir = direction_dir / "frames"
        if not pose_path.exists():
            errors.append(f"{direction}: pose.json is missing")
            continue
        sequence = PoseSequence.from_dict(json.loads(pose_path.read_text(encoding="utf-8")))
        errors.extend(f"{direction}: {error}" for error in validate_sequence(sequence, expected_frames))

        frame_paths = sorted(frames_dir.glob("*.png"))
        if len(frame_paths) != expected_frames:
            errors.append(f"{direction}: expected {expected_frames} frame PNGs, got {len(frame_paths)}")
        for frame_path in frame_paths:
            with Image.open(frame_path) as image:
                if image.size != canvas:
                    errors.append(f"{direction}: {frame_path.name} has size {image.size}, expected {canvas}")

        if not sheet_path.exists():
            errors.append(f"{direction}: pose_sheet.png is missing")
        else:
            rows = (expected_frames + columns - 1) // columns
            expected_size = (canvas[0] * columns, canvas[1] * rows)
            with Image.open(sheet_path) as sheet:
                if sheet.size != expected_size:
                    errors.append(f"{direction}: sheet size {sheet.size}, expected {expected_size}")
    return errors


def assert_valid_output(root: Path) -> None:
    errors = validate_output_directory(root)
    if errors:
        raise ValidationError("\n".join(errors))
