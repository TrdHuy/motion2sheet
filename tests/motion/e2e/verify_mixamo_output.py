from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

DIRECTIONS = ("down", "left", "right", "up")
REQUIRED_BONE_KEYS = {
    "pelvis", "neck", "head",
    "left_shoulder", "left_elbow", "left_wrist",
    "right_shoulder", "right_elbow", "right_wrist",
    "left_hip", "left_knee", "left_ankle",
    "right_hip", "right_knee", "right_ankle",
}


def motion_span(frames, joint):
    points = [frame[joint] for frame in frames]
    best = 0.0
    for i, first in enumerate(points):
        for second in points[i + 1 :]:
            best = max(best, math.dist(first, second))
    return best


def pose_height(frame):
    ys = [point[1] for point in frame.values()]
    return max(ys) - min(ys)


def verify_root(root: Path, *, expect_profile: str):
    metadata = json.loads((root / "metadata.json").read_text())
    raw = json.loads((root / ".raw_projected.json").read_text())
    if metadata.get("action") != "walk":
        raise AssertionError(f"{root}: expected walk action")
    if metadata.get("frames") != 8:
        raise AssertionError(f"{root}: expected 8 frames")
    if tuple(metadata.get("directions", [])) != DIRECTIONS:
        raise AssertionError(f"{root}: expected directions {DIRECTIONS}")
    bone_map = raw.get("boneMap", {})
    missing = REQUIRED_BONE_KEYS - set(bone_map)
    if missing:
        raise AssertionError(f"{root}: missing Mixamo bone mappings: {sorted(missing)}")
    mapped_names = [name.lower() for name in bone_map.values()]
    if not any("mixamo" in name for name in mapped_names):
        raise AssertionError(f"{root}: bone map does not look like a Mixamo rig: {bone_map}")
    if len(raw.get("sampleTimes", [])) != 8:
        raise AssertionError(f"{root}: expected 8 sample times")
    frame_range = raw.get("frameRange")
    if not frame_range or frame_range[1] <= frame_range[0]:
        raise AssertionError(f"{root}: invalid animation frame range {frame_range}")
    if metadata.get("proportionProfile") != expect_profile:
        raise AssertionError(f"{root}: expected {expect_profile} profile metadata")
    if raw.get("retarget", {}).get("profile") != expect_profile:
        raise AssertionError(f"{root}: expected retarget profile {expect_profile}")
    for direction in DIRECTIONS:
        pose = json.loads((root / direction / "pose.json").read_text())
        frames = pose["frames"]
        if len(frames) != 8:
            raise AssertionError(f"{root}/{direction}: expected 8 frames")
        if min(pose_height(frame) for frame in frames) < 100:
            raise AssertionError(f"{root}/{direction}: projected skeleton too small")
        if motion_span(frames, "left_ankle") < 4 and motion_span(frames, "right_ankle") < 4:
            raise AssertionError(f"{root}/{direction}: walk leg motion is too weak/static")


def compare_source_and_chibi(source: Path, chibi: Path):
    source_raw = json.loads((source / ".raw_projected.json").read_text())
    chibi_raw = json.loads((chibi / ".raw_projected.json").read_text())
    if source_raw["sampleTimes"] != chibi_raw["sampleTimes"]:
        raise AssertionError("source/chibi builds did not sample the same Mixamo timeline")
    if source_raw["boneMap"] != chibi_raw["boneMap"]:
        raise AssertionError("source/chibi builds used different Mixamo bone maps")
    retarget = chibi_raw.get("retarget", {})
    if retarget["targetStature"] >= retarget["sourceStature"]:
        raise AssertionError("chibi target stature was not smaller than Mixamo source stature")
    print(
        "Mixamo source/chibi verified; "
        f"sourceStature={retarget['sourceStature']:.4f}, "
        f"targetStature={retarget['targetStature']:.4f}, "
        f"rootMotionScale={retarget['rootMotionScale']:.4f}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("chibi")
    args = parser.parse_args()
    source = Path(args.source)
    chibi = Path(args.chibi)
    verify_root(source, expect_profile="source")
    verify_root(chibi, expect_profile="chibi_v1")
    compare_source_and_chibi(source, chibi)


if __name__ == "__main__":
    main()
