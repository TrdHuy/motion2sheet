from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify_output(root: Path, expected_mode: str) -> None:
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    actual_mode = metadata.get("outputMode")
    if actual_mode != expected_mode:
        raise AssertionError(f"{root}: expected outputMode={expected_mode}, got {actual_mode!r}")

    expected_frames = int(metadata["frames"])
    directions = metadata["directions"]
    for direction in directions:
        direction_dir = root / direction
        pose_path = direction_dir / "pose.json"
        frames_dir = direction_dir / "frames"
        sheet_path = direction_dir / "pose_sheet.png"
        if not pose_path.is_file():
            raise AssertionError(f"{root}/{direction}: pose.json is missing")

        if expected_mode == "frames":
            if not frames_dir.is_dir():
                raise AssertionError(f"{root}/{direction}: frames directory is missing")
            frame_paths = sorted(frames_dir.glob("*.png"))
            if len(frame_paths) != expected_frames:
                raise AssertionError(
                    f"{root}/{direction}: expected {expected_frames} frame PNGs, got {len(frame_paths)}"
                )
            if sheet_path.exists():
                raise AssertionError(f"{root}/{direction}: stale pose_sheet.png remained after frames rebuild")
        elif expected_mode == "sheet":
            if not sheet_path.is_file():
                raise AssertionError(f"{root}/{direction}: pose_sheet.png is missing")
            if frames_dir.exists():
                raise AssertionError(f"{root}/{direction}: stale frames directory remained after sheet rebuild")
        else:
            raise AssertionError(f"unsupported verifier mode: {expected_mode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_output")
    parser.add_argument("sheet_output")
    args = parser.parse_args()
    verify_output(Path(args.frames_output), "frames")
    verify_output(Path(args.sheet_output), "sheet")
    print("output-mode filesystem contracts verified")


if __name__ == "__main__":
    main()
