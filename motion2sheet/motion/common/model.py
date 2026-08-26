from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

Point = Tuple[float, float]

CANONICAL_JOINTS: tuple[str, ...] = (
    "head",
    "neck",
    "left_shoulder",
    "left_elbow",
    "left_wrist",
    "right_shoulder",
    "right_elbow",
    "right_wrist",
    "pelvis",
    "left_hip",
    "left_knee",
    "left_ankle",
    "right_hip",
    "right_knee",
    "right_ankle",
)

BONES: tuple[tuple[str, str], ...] = (
    ("head", "neck"),
    ("neck", "left_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("neck", "right_shoulder"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("neck", "pelvis"),
    ("pelvis", "left_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("pelvis", "right_hip"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
)


@dataclass(frozen=True)
class PoseFrame:
    joints: Dict[str, Point]

    def to_dict(self) -> dict:
        return {name: [float(x), float(y)] for name, (x, y) in self.joints.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "PoseFrame":
        return cls({name: (float(value[0]), float(value[1])) for name, value in data.items()})


@dataclass(frozen=True)
class PoseSequence:
    action: str
    direction: str
    canvas: Tuple[int, int]
    anchor: Point
    frames: List[PoseFrame]

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "direction": self.direction,
            "canvas": [int(self.canvas[0]), int(self.canvas[1])],
            "anchor": [float(self.anchor[0]), float(self.anchor[1])],
            "frames": [frame.to_dict() for frame in self.frames],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PoseSequence":
        return cls(
            action=str(data["action"]),
            direction=str(data["direction"]),
            canvas=(int(data["canvas"][0]), int(data["canvas"][1])),
            anchor=(float(data["anchor"][0]), float(data["anchor"][1])),
            frames=[PoseFrame.from_dict(item) for item in data["frames"]],
        )


def missing_joints(frame: PoseFrame, required: Iterable[str] = CANONICAL_JOINTS) -> list[str]:
    return [joint for joint in required if joint not in frame.joints]
