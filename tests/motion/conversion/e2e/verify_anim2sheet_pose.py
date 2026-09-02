from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SEMANTICS = {
    "pelvis": ("Pelvis","head"), "head": ("Head","tail"),
    "leftElbow": ("LeftUpperArm","tail"), "leftWrist": ("LeftForeArm","tail"),
    "rightElbow": ("RightUpperArm","tail"), "rightWrist": ("RightForeArm","tail"),
    "leftKnee": ("LeftThigh","tail"), "leftAnkle": ("LeftShin","tail"),
    "rightKnee": ("RightThigh","tail"), "rightAnkle": ("RightShin","tail"),
}


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def vec(values) -> list[float]:
    return [round(float(value), 9) for value in values]


def find_one(kind: str):
    values = [obj for obj in bpy.context.scene.objects if obj.type == kind]
    if len(values) != 1:
        raise RuntimeError(f"expected exactly one {kind}, got {len(values)}")
    return values[0]


def point_world(arm, bone_name: str, endpoint: str) -> Vector:
    bone = arm.pose.bones[bone_name]
    local = bone.head if endpoint == "head" else bone.tail
    return arm.matrix_world @ local


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversion", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv())
    conversion = json.loads(Path(args.conversion).read_text(encoding="utf-8"))
    expected_by_frame = {int(row["frame"]): row["semantics"] for row in conversion["targetPoseFrames"]}
    tolerance = float(conversion["fidelity"]["toleranceMeters"])
    arm = find_one("ARMATURE")
    motion_root = arm.parent
    if motion_root is None:
        raise RuntimeError("Anim2Sheet armature has no MotionRoot parent")
    max_error = -1.0
    worst_frame = None
    worst_semantic = None
    per_semantic = {}
    frames = []
    for frame, expected in sorted(expected_by_frame.items()):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        actual = {"root": vec(motion_root.location)}
        for semantic, (bone, endpoint) in SEMANTICS.items():
            actual[semantic] = vec(point_world(arm, bone, endpoint))
        errors = {}
        for semantic, expected_values in expected.items():
            if semantic not in actual:
                continue
            error = (Vector(actual[semantic]) - Vector(expected_values)).length
            errors[semantic] = round(float(error), 9)
            previous = per_semantic.get(semantic, {"maxErrorMeters": -1.0, "worstFrame": None})
            if error > previous["maxErrorMeters"]:
                per_semantic[semantic] = {"maxErrorMeters": round(float(error), 9), "worstFrame": frame}
            if error > max_error:
                max_error, worst_frame, worst_semantic = float(error), frame, semantic
        frames.append({"frame": frame, "actual": actual, "errorsMeters": errors})
    report = {
        "schema":"motion2sheet.anim2sheet-pose-fidelity","version":1,"sourceBlend":bpy.data.filepath,
        "toleranceMeters":tolerance,"pass":bool(max_error <= tolerance),"maxErrorMeters":round(max(0.0,max_error),9),
        "worstFrame":worst_frame,"worstSemantic":worst_semantic,"perSemantic":per_semantic,"frames":frames,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key:report[key] for key in ("pass","maxErrorMeters","worstFrame","worstSemantic")}, indent=2))
    if not report["pass"]:
        raise RuntimeError(f"Anim2Sheet consumed pose exceeds converter tolerance: {report['maxErrorMeters']}m > {tolerance}m at F{worst_frame} {worst_semantic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
