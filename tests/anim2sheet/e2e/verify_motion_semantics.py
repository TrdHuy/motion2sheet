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
ref_by_frame = {int(row["frame"]): row for row in reference["keyPoses"]}
if sorted(by_frame) != list(range(1, 17)):
    raise SystemExit("debug samples are not exactly frames 1..16")


def point(frame: int, name: str) -> tuple[float, float, float]:
    values = by_frame[frame]["joints"][name]
    return tuple(float(value) for value in values)


def distance(a, b) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def vector(a, b):
    return tuple(float(b[i]) - float(a[i]) for i in range(3))


def length(v) -> float:
    return math.sqrt(sum(value * value for value in v))


def angle_deg(a, b) -> float:
    la = length(a)
    lb = length(b)
    if la < 1e-9 or lb < 1e-9:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(3)) / (la * lb)
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def sword_vector(frame: int):
    row = by_frame[frame]
    return vector(row["swordGrip"], row["swordTip"])


def sword_dx(frame: int) -> float:
    row = by_frame[frame]
    return float(row["swordTip"][0]) - float(row["swordGrip"][0])


def authored_body(frame: int, key: str) -> float:
    return float(ref_by_frame[frame]["body"][key])


max_ik = 0.0
worst_ik = None
for row in samples:
    for name, raw in row["ikError"].items():
        value = float(raw)
        if value > max_ik:
            max_ik = value
            worst_ik = (row["frame"], name, value)
if max_ik > 0.18:
    raise SystemExit(f"IK fit too loose: max={max_ik:.4f} worst={worst_ik}")

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
    raise SystemExit(f"pelvis rotation is too weak: yaw range={pelvis_yaw_range:.2f}deg")
if shoulder_yaw_range < 28.0:
    raise SystemExit(f"upper-body rotation is too weak: yaw range={shoulder_yaw_range:.2f}deg")

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
    raise SystemExit(f"impact arm extension is too compressed: {impact_extension:.4f}")

# Sword trajectory: allow the intentional depth transition around impact, but
# reject large orientation flips elsewhere. This catches the historical
# F2->F3, F3->F4, F4->F5, F11->F12 and F14->F15 teleports.
impact_transitions = {(6, 7), (7, 8)}
max_nonimpact_sword_angle = 0.0
worst_sword_transition = None
for frame in range(1, 16):
    value = angle_deg(sword_vector(frame), sword_vector(frame + 1))
    if (frame, frame + 1) not in impact_transitions:
        if value > max_nonimpact_sword_angle:
            max_nonimpact_sword_angle = value
            worst_sword_transition = (frame, frame + 1, value)
        if value > 70.0:
            raise SystemExit(
                f"sword orientation discontinuity F{frame}->F{frame + 1}: {value:.2f}deg"
            )

# Recovery should be especially smooth because there is no impact exception.
for frame in range(10, 16):
    tip_step = distance(by_frame[frame]["swordTip"], by_frame[frame + 1]["swordTip"])
    if tip_step > 0.85:
        raise SystemExit(
            f"recovery sword tip teleports F{frame}->F{frame + 1}: {tip_step:.4f}m"
        )

# Elbow-pop regression check. Keep the threshold intentionally conservative so
# legitimate strike acceleration still passes, while recovery/guard cannot
# snap to a different bend plane in one frame.
max_left_elbow_step = 0.0
worst_left_elbow_step = None
for frame in range(1, 16):
    step = distance(point(frame, "leftElbow"), point(frame + 1, "leftElbow"))
    if step > max_left_elbow_step:
        max_left_elbow_step = step
        worst_left_elbow_step = (frame, frame + 1, step)
    limit = 0.34 if frame in (4, 5, 6, 7, 8) else 0.24
    if step > limit:
        raise SystemExit(
            f"left elbow pop F{frame}->F{frame + 1}: {step:.4f}m > {limit:.2f}m"
        )

# Ready/return guard must not produce the former high/cross-body chicken-wing.
for frame in (1, 2, 15, 16):
    shoulder = point(frame, "leftShoulder")
    elbow = point(frame, "leftElbow")
    if elbow[2] - shoulder[2] > 0.16:
        raise SystemExit(
            f"left elbow too high in guard F{frame}: dz={elbow[2] - shoulder[2]:.4f}m"
        )

# Grounded strike: during impact/follow-through at least the supporting leg must
# remain visibly flexed. 180deg is fully straight in the sampled debug metric.
strike_knee_angles = {}
for frame in (7, 8, 9, 10):
    left = float(by_frame[frame]["leftKneeAngleDeg"])
    right = float(by_frame[frame]["rightKneeAngleDeg"])
    strike_knee_angles[frame] = (left, right)
    if min(left, right) > 162.0:
        raise SystemExit(
            f"strike stance too straight F{frame}: left={left:.2f} right={right:.2f}"
        )

# Pelvis must visibly lead upper-body release. The authored contract intentionally
# keeps chest rotation behind pelvis at F4, then allows chest/shoulders to catch
# up through F5-F7 before the weapon exits left.
if authored_body(4, "pelvisYawDeg") - authored_body(4, "chestYawDeg") < 6.0:
    raise SystemExit("force-chain anticipation missing: pelvis must lead chest at F4")
if authored_body(6, "chestYawDeg") - authored_body(6, "pelvisYawDeg") < 8.0:
    raise SystemExit("force-chain release missing: chest must catch pelvis by F6")

# Strike direction and readable depth impact.
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
if not (0.12 <= len7 <= 0.26):
    raise SystemExit(
        f"impact projected blade length must remain readable: F7={len7:.4f}m"
    )
if not (len7 < len6 * 0.35 and len7 < len8 * 0.35):
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
    "maxLeftElbowStep": max_left_elbow_step,
    "worstLeftElbowStep": worst_left_elbow_step,
    "maxNonImpactSwordAngleDeg": max_nonimpact_sword_angle,
    "worstSwordTransition": worst_sword_transition,
    "strikeKneeAngles": strike_knee_angles,
    "impactArmExtension": impact_extension,
    "strike": {
        "frame6Dx": dx6,
        "frame7ProjectedLength": len7,
        "frame8Dx": dx8,
        "frame9Dx": dx9,
    },
}, indent=2))
