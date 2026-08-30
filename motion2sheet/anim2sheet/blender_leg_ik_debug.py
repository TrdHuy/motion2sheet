"""Inspect leg IK basis and authored-guide/evaluated-knee bend-plane authority.

Runs on the already-authored saved source.blend. It does not modify the rig or
pose. The diagnostic is intentionally camera-independent and compares 3D bend
vectors after projecting both the evaluated knee and authored knee guide onto
the plane perpendicular to the hip->ankle chain axis.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


LEGS = {
    "left": {
        "thigh": "LeftThigh",
        "shin": "LeftShin",
        "guide": "LeftKneeGuideTarget",
        "constraint": "ReferenceIK_LeftShin",
    },
    "right": {
        "thigh": "RightThigh",
        "shin": "RightShin",
        "guide": "RightKneeGuideTarget",
        "constraint": "ReferenceIK_RightShin",
    },
}


def argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def vec(v: Vector) -> list[float]:
    return [round(float(x), 6) for x in v]


def find_armature():
    values = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(values) != 1:
        raise RuntimeError(f"expected exactly one armature, got {len(values)}")
    return values[0]


def bone_world_point(arm, name: str, endpoint: str) -> Vector:
    bone = arm.pose.bones[name]
    point = bone.head if endpoint == "head" else bone.tail
    return arm.matrix_world @ point


def perpendicular_bend(point: Vector, hip: Vector, ankle: Vector) -> Vector:
    axis = ankle - hip
    denom = axis.length_squared
    if denom < 1e-12:
        raise RuntimeError("hip and ankle are coincident")
    t = (point - hip).dot(axis) / denom
    closest = hip + axis * t
    return point - closest


def normalized_bend(point: Vector, hip: Vector, ankle: Vector, label: str) -> Vector:
    value = perpendicular_bend(point, hip, ankle)
    if value.length < 1e-6:
        raise RuntimeError(f"{label} lies on hip-ankle axis; bend plane is undefined")
    return value.normalized()


def rest_bone_debug(arm, name: str) -> dict:
    bone = arm.data.bones[name]
    basis = bone.matrix_local.to_3x3()
    return {
        "name": name,
        "rollDeg": round(math.degrees(float(bone.roll)), 6),
        "headLocal": vec(Vector(bone.head_local)),
        "tailLocal": vec(Vector(bone.tail_local)),
        "xAxisArmature": vec(Vector(basis.col[0]).normalized()),
        "yAxisArmature": vec(Vector(basis.col[1]).normalized()),
        "zAxisArmature": vec(Vector(basis.col[2]).normalized()),
    }


def constraint_debug(arm, cfg: dict) -> dict:
    constraint = arm.pose.bones[cfg["shin"]].constraints.get(cfg["constraint"])
    if constraint is None:
        raise RuntimeError(f"missing IK constraint {cfg['constraint']}")
    return {
        "bone": cfg["shin"],
        "name": constraint.name,
        "chainCount": int(constraint.chain_count),
        "poleAngleDeg": round(math.degrees(float(constraint.pole_angle)), 6),
        "target": constraint.target.name if constraint.target else None,
        "poleTarget": constraint.pole_target.name if constraint.pole_target else None,
    }


def frame_leg_debug(arm, frame: int, side: str, cfg: dict) -> dict:
    guide_obj = bpy.data.objects.get(cfg["guide"])
    if guide_obj is None:
        raise RuntimeError(f"missing knee guide object {cfg['guide']}")

    hip = bone_world_point(arm, cfg["thigh"], "head")
    knee = bone_world_point(arm, cfg["thigh"], "tail")
    ankle = bone_world_point(arm, cfg["shin"], "tail")
    guide = guide_obj.matrix_world.translation.copy()
    knee_dir = normalized_bend(knee, hip, ankle, f"F{frame} {side} knee")
    guide_dir = normalized_bend(guide, hip, ankle, f"F{frame} {side} knee guide")
    alignment = float(knee_dir.dot(guide_dir))

    return {
        "hip": vec(hip),
        "knee": vec(knee),
        "ankle": vec(ankle),
        "kneeGuide": vec(guide),
        "evaluatedBendDirection": vec(knee_dir),
        "guideBendDirection": vec(guide_dir),
        "evaluatedWorldYSign": -1 if knee_dir.y < 0 else (1 if knee_dir.y > 0 else 0),
        "guideWorldYSign": -1 if guide_dir.y < 0 else (1 if guide_dir.y > 0 else 0),
        "alignmentCos": round(alignment, 6),
        "match": bool(alignment > 0.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", required=True)
    args, _ = parser.parse_known_args(argv())

    frames = [int(v.strip()) for v in args.frames.split(",") if v.strip()]
    if not frames:
        raise RuntimeError("--frames did not contain frame numbers")

    arm = find_armature()
    setup = {}
    for side, cfg in LEGS.items():
        setup[side] = {
            "thigh": rest_bone_debug(arm, cfg["thigh"]),
            "shin": rest_bone_debug(arm, cfg["shin"]),
            "ik": constraint_debug(arm, cfg),
        }

    rows = []
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        rows.append({
            "frame": frame,
            "legs": {
                side: frame_leg_debug(arm, frame, side, cfg)
                for side, cfg in LEGS.items()
            },
        })

    payload = {
        "mode": "leg-ik-bend-plane-diagnostic",
        "sourceBlend": bpy.data.filepath,
        "frames": frames,
        "rigSetup": setup,
        "framesData": rows,
    }
    path = Path(args.output).resolve() / "leg_ik_debug.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "poleAngles": {side: setup[side]["ik"]["poleAngleDeg"] for side in LEGS},
        "matches": {
            str(row["frame"]): {side: row["legs"][side]["match"] for side in LEGS}
            for row in rows
        },
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
