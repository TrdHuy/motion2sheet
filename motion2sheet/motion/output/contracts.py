from __future__ import annotations

OUTPUT_MODES = ("both", "frames", "sheet")
DEFAULT_OUTPUT_MODE = "both"


def mode_emits_frames(mode: str) -> bool:
    return mode in ("both", "frames")


def mode_emits_sheet(mode: str) -> bool:
    return mode in ("both", "sheet")
