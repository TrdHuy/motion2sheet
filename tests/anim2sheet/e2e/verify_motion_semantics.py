from __future__ import annotations

"""Semantic quality gates for the actual evaluated Blender rig.

These checks deliberately go beyond IK target error. A small IK error only says
an end effector reached its target; it does not prove useful body mechanics.
"""

import json
import math
import sys
from pathlib import Path


root = Path(sys.argv[1])
debug = json.loads((root / "motion_debug.json").read_text(encoding="utf-8"))
reference = json.loads((root / "pose_reference.json").read_text(encoding="utf-8"))
samples = debug["samples"]

if int(reference.get("version", 0)) < 2:
    raise SystemExit("full-body pose reference v2+ required")
if len(samples) != 16 or len(reference.get("keyPoses", [])) != 16:
    raise SystemExit("expected exactly 16 debug/reference poses")

by_frame = {int(row["frame"]): row for row in samples}
if sorted(by_frame) != list(range(1, 17)):
    raise SystemExit("debug samples are not exactly frames 1..16")


def point(frame: int, name: str) -> tuple[float, float, float]:
    values = by_frame[frame]["joints"][name]
    return tuple(float(value) for value in values)


def distance(a, b) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def sword_dx(frame: int) -> float:
    row = by_frame[frame]
    return float(row["swordTip"][0]) - float(row["swordGrip"][0])


max_ik = 0.0
worst_ik = None
for row in samples:
    for name, raw in row["ikError"].items():
        value = float(raw)
        if value > max_ik:
            max_ik = value
            worst_ik = (row["frame"], name, value)
if max_ik > 0.18:
    raise SystemExit(
        f"IK fit too loose: max={max_ik:.4f} worst={worst_ik}"
    )

root_x = [float(row["root"][0]) for row in samples]
root_z = [float(row["root"][1]) for row in samples]
root_drive = max(root_x) - min(root_x)
min_root_z = min(root_z)
if root_drive < 0.35:
    raise SystemExit(f"attack drive too small: root range={root_drive:.4f}")
if min_root_z > -0.08:
    raise SystemExit(f"anticipation crouch too weak: min root z={min_root_z:.4f}")

left_step = distance(point(1, "leftAnkle"), point(7, "leftAnkle"))
right_plant = distance(point(1, "rightAnkle"), point(7, "rightAnkle"))
if left_step < 0.22:
    raise SystemExit(f"left-foot drive is too small: {left_step:.4f}")
if right_plant > 0.12:
    raise SystemExit(
        f"rear/right foot is not planted through impact: travel={right_plant:.4f}"
    )

strike_stance = min(float(by_frame[f]["stanceWidth"]) for f in (6, 7, 8, 9))
if strike_stance < 0.22:
    raise SystemExit(f"strike stance collapsed: min width={strike_stance:.4f}")

pelvis_yaw = [float(by_frame[f]["pelvisYawDeg"]) for f in range(3, 11)]
shoulder_yaw = [float(by_frame[f]["shoulderYawDeg"]) for f in range(3, 11)]
pelvis_yaw_range = max(pelvis_yaw) - min(pelvis_yaw)
shoulder_yaw_range = max(shoulder_yaw) - min(shoulder_yaw)
if pelvis_yaw_range < 18.0:
    raise SystemExit(
        f"pelvis rotation is too weak: yaw range={pelvis_yaw_range:.2f}deg"
    )
if shoulder_yaw_range < 28.0:
    raise SystemExit(
        f"upper-body rotation is too weak: yaw range={shoulder_yaw_range:.2f}deg"
    )

left_elbow_travel = distance(point(4, "leftElbow"), point(9, "leftElbow"))
right_elbow_travel = distance(point(4, "rightElbow"), point(9, "rightElbow"))
if left_elbow_travel < 0.14 or right_elbow_travel < 0.14:
    raise SystemExit(
        "elbow trajectories are too static: "
        f"left={left_elbow_travel:.4f}, right={right_elbow_travel:.4f}"
    )

impact_extension = (
    float(by_frame[7]["leftArmExtension"])
    + float(by_frame[7]["rightArmExtension"])
) * 0.5
if impact_extension < 0.28:
    raise SystemExit(
        f"impact arm extension is too compressed: {impact_extension:.4f}"
    )

dx6 = sword_dx(6)
dx8 = sword_dx(8)
dx9 = sword_dx(9)
len6 = float(by_frame[6]["projectedSwordLengthXZ"])
len7 = float(by_frame[7]["projectedSwordLengthXZ"])
len8 = float(by_frame[8]["projectedSwordLengthXZ"])
if dx6 < 0.45:
    raise SystemExit(f"frame 6 sword must read screen-right: dx={dx6:.4f}")
if dx8 > -0.45 or dx9 > -0.45:
    raise SystemExit(
        f"frames 8/9 sword must read screen-left: dx8={dx8:.4f}, dx9={dx9:.4f}"
    )
if not (len7 < len6 * 0.55 and len7 < len8 * 0.55):
    raise SystemExit(
        "impact foreshortening missing: "
        f"len6={len6:.4f}, len7={len7:.4f}, len8={len8:.4f}"
    )

impact = int(debug.get("impactFrame") or 0)
if impact != 7:
    raise SystemExit(f"expected impact frame 7, got {impact}")

final_yaw = abs(float(by_frame[16]["shoulderYawDeg"]))
if final_yaw > 18.0:
    raise SystemExit(f"recovery does not settle: final shoulder yaw={final_yaw:.2f}")

print(json.dumps({
    "reference": debug.get("reference"),
    "rig": debug.get("rig"),
    "maxIKError": max_ik,
    "worstIK": worst_ik,
    "rootDrive": root_drive,
    "minRootZ": min_root_z,
    "leftFootDrive": left_step,
    "rightFootPreImpactTravel": right_plant,
    "minStrikeStance": strike_stance,
    "pelvisYawRange": pelvis_yaw_range,
    "shoulderYawRange": shoulder_yaw_range,
    "leftElbowTravel": left_elbow_travel,
    "rightElbowTravel": right_elbow_travel,
    "impactArmExtension": impact_extension,
    "strike": {
        "frame6Dx": dx6,
        "frame7ProjectedLength": len7,
        "frame8Dx": dx8,
        "frame9Dx": dx9,
    },
}, indent=2))
