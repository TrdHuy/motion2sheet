from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


DURATION_TOLERANCE_SECONDS = 1e-6
FPS_TOLERANCE = 1e-9
FBX_KTIME_V7 = 46_186_158_000
FBX_KTIME_V8 = 141_120_000
FBX_TIMECODE_DEFINITION_TO_TICKS_PER_SECOND = {
    0: FBX_KTIME_V8,
    127: FBX_KTIME_V7,
}
FBX_TIME_MODE_FPS = {
    1: 120.0,
    2: 100.0,
    3: 60.0,
    4: 50.0,
    5: 48.0,
    6: 30.0,
    7: 30.0,
    8: 30.0 / 1.001,
    9: 30.0 / 1.001,
    10: 25.0,
    11: 24.0,
    12: 1000.0,
    13: 24.0 / 1.001,
    15: 96.0,
    16: 72.0,
    17: 60.0 / 1.001,
    18: 120.0 / 1.001,
}


def resolve_fbx_ticks_per_second(
    fbx_version: int,
    *,
    header_version: int,
    timecode_definition: int | None,
) -> int:
    """Resolve the FBX KTime unit without consulting animation FPS."""

    ticks_per_second = FBX_KTIME_V8 if fbx_version >= 8000 else FBX_KTIME_V7
    if header_version >= 1004 and timecode_definition is not None:
        try:
            ticks_per_second = FBX_TIMECODE_DEFINITION_TO_TICKS_PER_SECOND[timecode_definition]
        except KeyError as exc:
            raise ValueError(
                f"unsupported FBX TCDefinition {timecode_definition}; cannot establish native timebase"
            ) from exc
    return ticks_per_second


def fbx_declared_fps(global_settings: dict[str, Any]) -> float:
    mode = int(global_settings["TimeMode"])
    if mode in FBX_TIME_MODE_FPS:
        return FBX_TIME_MODE_FPS[mode]
    if mode in {0, 14}:
        custom = float(global_settings["CustomFrameRate"])
        if math.isfinite(custom) and custom > 0.0:
            return custom
    raise ValueError(
        f"unsupported FBX TimeMode/CustomFrameRate combination: mode={mode} "
        f"custom={global_settings.get('CustomFrameRate')!r}"
    )


def representation_duration_seconds(frame_count: int, fps: float) -> float:
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count <= 0:
        raise ValueError("frameCount must be a positive integer")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(float(fps)) or float(fps) <= 0:
        raise ValueError("fps must be a positive finite number")
    return (frame_count - 1) / float(fps)


def _require_consistent_duration(native_duration: float, frame_count: int, fps: float, label: str) -> None:
    represented = representation_duration_seconds(frame_count, fps)
    error = abs(native_duration - represented)
    if error > DURATION_TOLERANCE_SECONDS:
        raise ValueError(
            f"{label} native duration contradicts endpoint-inclusive frameCount/fps: "
            f"nativeDurationSeconds={native_duration:.12g} representedDurationSeconds={represented:.12g} "
            f"errorSeconds={error:.12g} toleranceSeconds={DURATION_TOLERANCE_SECONDS:.12g}"
        )


def validate_fbx_native_timing(
    animation_fbx: dict[str, Any],
    *,
    global_settings: dict[str, Any],
    frame_count: int,
    fps: float,
) -> dict[str, Any]:
    ticks_per_second = int(animation_fbx["ktimeTicksPerSecond"])
    if ticks_per_second not in {FBX_KTIME_V7, FBX_KTIME_V8}:
        raise ValueError(f"unsupported FBX KTime ticks-per-second value: {ticks_per_second}")

    timing = animation_fbx["stackTiming"]
    local_start = int(timing["LocalStart"])
    local_stop = int(timing["LocalStop"])
    reference_start = int(timing["ReferenceStart"])
    reference_stop = int(timing["ReferenceStop"])
    if local_stop < local_start:
        raise ValueError("FBX AnimationStack LocalStop must not precede LocalStart")
    if (reference_start, reference_stop) != (local_start, local_stop):
        raise ValueError(
            "FBX AnimationStack reference span contradicts local span: "
            f"local={[local_start, local_stop]} reference={[reference_start, reference_stop]}"
        )

    sample_times = animation_fbx["sampleKeyTimes"]
    if len(sample_times) != frame_count:
        raise ValueError(
            f"FBX native sample count contradicts frameCount: native={len(sample_times)} frameCount={frame_count}"
        )
    if (sample_times[0], sample_times[-1]) != (local_start, local_stop):
        raise ValueError(
            "FBX sample timeline endpoints contradict AnimationStack local span: "
            f"samples={[sample_times[0], sample_times[-1]]} local={[local_start, local_stop]}"
        )

    native_duration = (local_stop - local_start) / ticks_per_second
    _require_consistent_duration(native_duration, frame_count, fps, "FBX")

    for index, key_time in enumerate(sample_times):
        native_elapsed = (int(key_time) - local_start) / ticks_per_second
        represented_elapsed = index / float(fps)
        error = abs(native_elapsed - represented_elapsed)
        if error > DURATION_TOLERANCE_SECONDS:
            raise ValueError(
                "FBX native sample timeline contradicts imported FPS: "
                f"sample={index} nativeElapsedSeconds={native_elapsed:.12g} "
                f"representedElapsedSeconds={represented_elapsed:.12g} "
                f"errorSeconds={error:.12g} toleranceSeconds={DURATION_TOLERANCE_SECONDS:.12g}"
            )

    declared_fps = fbx_declared_fps(global_settings)
    fps_error = abs(declared_fps - float(fps))
    if fps_error > FPS_TOLERANCE:
        raise ValueError(
            "FBX TimeMode/CustomFrameRate contradicts imported FPS: "
            f"declaredFps={declared_fps:.12g} importedFps={float(fps):.12g} "
            f"error={fps_error:.12g} tolerance={FPS_TOLERANCE:.12g}"
        )

    return {
        "authority": "fbx-animation-stack-ktime",
        "durationSeconds": native_duration,
        "ticksPerSecond": ticks_per_second,
        "localSpanTicks": local_stop - local_start,
        "declaredFps": declared_fps,
    }


_BVH_FRAMES_RE = re.compile(r"^Frames:\s*([0-9]+)\s*$", re.IGNORECASE)
_BVH_FRAME_TIME_RE = re.compile(
    r"^Frame\s+Time:\s*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*$",
    re.IGNORECASE,
)


def extract_bvh_native_timing(path: Path) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError(f"BVH must be UTF-8/ASCII text: {path}") from exc
    motion_rows = [index for index, line in enumerate(lines) if line.strip().upper() == "MOTION"]
    if len(motion_rows) != 1:
        raise ValueError(f"BVH must contain exactly one MOTION section; found {len(motion_rows)}")
    following = [line.strip() for line in lines[motion_rows[0] + 1 :] if line.strip()]
    frame_matches = [match for line in following if (match := _BVH_FRAMES_RE.fullmatch(line))]
    time_matches = [match for line in following if (match := _BVH_FRAME_TIME_RE.fullmatch(line))]
    if len(frame_matches) != 1 or len(time_matches) != 1:
        raise ValueError(
            "BVH MOTION section must contain exactly one Frames and one Frame Time declaration"
        )
    declared_frame_count = int(frame_matches[0].group(1))
    frame_time_seconds = float(time_matches[0].group(1))
    if declared_frame_count <= 0:
        raise ValueError("BVH Frames must be positive")
    if not math.isfinite(frame_time_seconds) or frame_time_seconds <= 0.0:
        raise ValueError("BVH Frame Time must be a positive finite number")
    return {
        "declaredFrameCount": declared_frame_count,
        "frameTimeSeconds": frame_time_seconds,
    }


def validate_bvh_native_timing(
    animation_bvh: dict[str, Any],
    *,
    frame_count: int,
    fps: float,
) -> dict[str, Any]:
    declared_frame_count = int(animation_bvh["declaredFrameCount"])
    frame_time_seconds = float(animation_bvh["frameTimeSeconds"])
    if declared_frame_count != frame_count:
        raise ValueError(
            f"BVH declared Frames contradict frameCount: declared={declared_frame_count} frameCount={frame_count}"
        )
    if not math.isfinite(frame_time_seconds) or frame_time_seconds <= 0.0:
        raise ValueError("BVH Frame Time must be a positive finite number")
    native_duration = (declared_frame_count - 1) * frame_time_seconds
    _require_consistent_duration(native_duration, frame_count, fps, "BVH")
    return {
        "authority": "bvh-motion-frame-time",
        "durationSeconds": native_duration,
        "frameTimeSeconds": frame_time_seconds,
    }
