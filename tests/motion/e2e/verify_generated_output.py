from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

DIRECTIONS = ("down", "left", "right", "up")
DYNAMIC_JOINTS = ("left_wrist", "right_wrist", "left_knee", "right_knee", "left_ankle", "right_ankle")


def motion_span(frames, joint):
    points = [frame[joint] for frame in frames]
    best = 0.0
    for i, first in enumerate(points):
        for second in points[i + 1 :]:
            best = max(best, math.hypot(second[0] - first[0], second[1] - first[1]))
    return best


def verify_root(root: Path):
    metadata = json.loads((root / "metadata.json").read_text())
    canvas_h = metadata["canvas"][1]
    for direction in DIRECTIONS:
        pose = json.loads((root / direction / "pose.json").read_text())
        frames = pose["frames"]
        if len(frames) != 8:
            raise AssertionError(f"{root.name}/{direction}: expected 8 frames")

        heights = []
        for index, frame in enumerate(frames, start=1):
            ys = [point[1] for point in frame.values()]
            heights.append(max(ys) - min(ys))
            if frame["head"][1] >= frame["pelvis"][1]:
                raise AssertionError(f"{root.name}/{direction}/frame {index}: head below pelvis")
        if min(heights) < canvas_h * 0.35:
            raise AssertionError(f"{root.name}/{direction}: skeleton projection visually collapsed: {min(heights):.1f}px")

        moving = [joint for joint in DYNAMIC_JOINTS if motion_span(frames, joint) >= 4.0]
        if len(moving) < 4:
            raise AssertionError(f"{root.name}/{direction}: motion too weak/static; moving={moving}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+")
    args = parser.parse_args()
    for value in args.roots:
        verify_root(Path(value))
    print("E2E visual semantics verified:", ", ".join(args.roots))


if __name__ == "__main__":
    main()
