from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EXPECTED = {
    "pelvis_neck": ("pelvis", "neck", 0.27),
    "neck_head": ("neck", "head", 0.11),
    "upper_arm_l": ("left_shoulder", "left_elbow", 0.15),
    "lower_arm_l": ("left_elbow", "left_wrist", 0.14),
    "upper_arm_r": ("right_shoulder", "right_elbow", 0.15),
    "lower_arm_r": ("right_elbow", "right_wrist", 0.14),
    "upper_leg_l": ("left_hip", "left_knee", 0.17),
    "lower_leg_l": ("left_knee", "left_ankle", 0.16),
    "upper_leg_r": ("right_hip", "right_knee", 0.17),
    "lower_leg_r": ("right_knee", "right_ankle", 0.16),
}


def dist(frame, a, b):
    return math.dist(frame[a], frame[b])


def verify(root: Path):
    metadata = json.loads((root / "metadata.json").read_text())
    if metadata.get("proportionProfile") != "chibi_v1":
        raise AssertionError(f"{root}: expected chibi_v1 profile")

    raw = json.loads((root / ".raw_projected.json").read_text())
    if raw.get("retarget", {}).get("profile") != "chibi_v1":
        raise AssertionError(f"{root}: missing retarget metadata")

    frames = raw["canonicalFrames"]
    if len(frames) != 8:
        raise AssertionError(f"{root}: expected 8 canonical frames")

    for index, frame in enumerate(frames, start=1):
        for label, (a, b, expected) in EXPECTED.items():
            actual = dist(frame, a, b)
            if abs(actual - expected) > 1e-5:
                raise AssertionError(
                    f"{root}/frame {index}/{label}: expected {expected}, got {actual}"
                )
        if frame["left_hip"][0] >= frame["right_hip"][0]:
            raise AssertionError(f"{root}/frame {index}: left/right hips swapped")

    moving = max(
        math.dist(frames[0]["left_knee"], frame["left_knee"])
        for frame in frames[1:]
    )
    if moving < 0.01:
        raise AssertionError(f"{root}: retargeted sequence became static")

    if raw["retarget"]["targetStature"] >= raw["retarget"]["sourceStature"]:
        raise AssertionError(f"{root}: chibi profile did not compact source stature")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+")
    args = parser.parse_args()
    for value in args.roots:
        verify(Path(value))
    print("Retarget semantics verified:", ", ".join(args.roots))


if __name__ == "__main__":
    main()
