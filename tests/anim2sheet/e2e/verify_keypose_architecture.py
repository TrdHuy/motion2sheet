from __future__ import annotations

"""Fail-fast checks for the 4-frame deterministic arm architecture proof.

These gates do not judge the full animation. They verify that authored arm
joints survive evaluation exactly, F1 has sane elbow/forearm anatomy, both
hands remain bound to one weapon axis, and the strike key poses preserve the
intended right->depth->left weapon transition while the legs stay grounded.
"""

import json
import sys
from pathlib import Path


root = Path(sys.argv[1])
debug = json.loads((root / "motion_debug.json").read_text(encoding="utf-8"))
samples = debug.get("samples", [])
frames = [int(row["frame"]) for row in samples]
if frames != [1, 6, 7, 8]:
    raise SystemExit(f"expected key poses [1, 6, 7, 8], got {frames}")
if debug.get("armControl") != "deterministic_joint_fk":
    raise SystemExit("fast review must use deterministic_joint_fk arms")

by_frame = {int(row["frame"]): row for row in samples}
checks = {}

# Representation fidelity: Blender must reproduce the exact authored elbow and
# wrist joints, rather than choosing another IK solution.
max_joint_error = max(float(row["maxArmJointContractError"]) for row in samples)
checks["maxArmJointContractError"] = max_joint_error
if max_joint_error > 0.008:
    raise SystemExit(f"authored arm joints drifted after evaluation: {max_joint_error:.4f}m")

max_primary_grip_error = max(
    float(row["weaponGripContract"]["primaryLeftWristError"]) for row in samples
)
max_secondary_axis_error = max(
    float(row["weaponGripContract"]["rightWristAxisError"]) for row in samples
)
grip_spans = [
    float(row["weaponGripContract"]["rightWristAlongGrip"]) for row in samples
]
checks["maxPrimaryGripError"] = max_primary_grip_error
checks["maxSecondaryAxisError"] = max_secondary_axis_error
checks["gripSpans"] = grip_spans
if max_primary_grip_error > 0.008 or max_secondary_axis_error > 0.008:
    raise SystemExit("weapon is not deterministically bound to the authored hand sockets")
if not all(0.10 <= value <= 0.15 for value in grip_spans):
    raise SystemExit(f"two-hand grip span is unstable: {grip_spans}")

# F1 quality proof: elbows must stay on their anatomical sides and below the
# shoulders. The left/pommel wrist must not sweep across the body centerline;
# the second wrist may sit just left of center because both hands share one hilt.
f1 = by_frame[1]["joints"]
left_shoulder, left_elbow = f1["leftShoulder"], f1["leftElbow"]
right_shoulder, right_elbow = f1["rightShoulder"], f1["rightElbow"]
left_wrist = f1["leftWrist"]
if not (left_elbow[0] < left_shoulder[0] and right_elbow[0] > right_shoulder[0]):
    raise SystemExit("F1 elbow topology crosses the torso instead of staying anatomical")
if left_elbow[2] >= left_shoulder[2] or right_elbow[2] >= right_shoulder[2]:
    raise SystemExit("F1 elbows form a chicken-wing/high-guard topology")
if float(left_wrist[0]) > 0.02:
    raise SystemExit(f"F1 left forearm crosses too far through body centerline: wrist x={left_wrist[0]:.3f}")
f1_angles = [
    float(by_frame[1]["leftElbowAngleDeg"]),
    float(by_frame[1]["rightElbowAngleDeg"]),
]
checks["f1ElbowAngles"] = f1_angles
checks["f1LeftWristX"] = float(left_wrist[0])
if not all(55.0 <= value <= 125.0 for value in f1_angles):
    raise SystemExit(f"F1 elbow bend is anatomically implausible: {f1_angles}")
if float(by_frame[1]["root"][1]) > -0.05:
    raise SystemExit("F1 ready stance is not low enough for this key-pose proof")

# F6/F7/F8 weapon path: right, depth, left. F7 should be strongly
# foreshortened without disappearing entirely.
def sword_dx(frame: int) -> float:
    row = by_frame[frame]
    return float(row["swordTip"][0]) - float(row["swordGrip"][0])

f6_dx, f8_dx = sword_dx(6), sword_dx(8)
f6_len = float(by_frame[6]["projectedSwordLengthXZ"])
f7_len = float(by_frame[7]["projectedSwordLengthXZ"])
f8_len = float(by_frame[8]["projectedSwordLengthXZ"])
checks["strike"] = {
    "f6Dx": f6_dx,
    "f7ProjectedLengthXZ": f7_len,
    "f8Dx": f8_dx,
}
if f6_dx < 0.8:
    raise SystemExit(f"F6 sword does not clearly enter screen-right: dx={f6_dx:.3f}")
if f8_dx > -0.8:
    raise SystemExit(f"F8 sword does not clearly exit screen-left: dx={f8_dx:.3f}")
if not (0.12 <= f7_len <= 0.35):
    raise SystemExit(f"F7 depth pose has unreadable projection: {f7_len:.3f}m")
if not (f7_len < f6_len * 0.35 and f7_len < f8_len * 0.35):
    raise SystemExit("F7 does not create a clear foreshortened impact transition")

# Strike poses must not collapse into short arm-only shapes. Check both the
# average chain extension and each individual arm so one arm cannot hide a
# collapsed partner behind a good average.
strike_extensions = {}
individual_extensions = {}
for frame in (6, 7, 8):
    left = float(by_frame[frame]["leftArmExtension"])
    right = float(by_frame[frame]["rightArmExtension"])
    avg = (left + right) * 0.5
    strike_extensions[str(frame)] = avg
    individual_extensions[str(frame)] = {"left": left, "right": right}
    if avg < 0.30:
        raise SystemExit(f"F{frame} arm posture collapsed: avg extension={avg:.3f}")
    if min(left, right) < 0.28:
        raise SystemExit(
            f"F{frame} one arm collapsed despite average extension: left={left:.3f}, right={right:.3f}"
        )
checks["strikeArmExtension"] = strike_extensions
checks["individualArmExtension"] = individual_extensions

# F8 specifically is the topology-stability proof after depth impact; the
# supporting/right arm must remain visibly extended rather than folding into
# the torso as the blade exits screen-left.
if float(by_frame[8]["rightArmExtension"]) < 0.30:
    raise SystemExit(
        f"F8 right arm collapses during strike exit: {by_frame[8]['rightArmExtension']:.3f}"
    )

# Legs remain the existing explicit-pole IK solution and must stay grounded.
stance = {str(frame): float(by_frame[frame]["stanceWidth"]) for frame in (1, 6, 7, 8)}
checks["stanceWidth"] = stance
if min(stance.values()) < 0.25:
    raise SystemExit(f"key-pose stance collapsed: {stance}")
strike_knees = {}
for frame in (6, 7, 8):
    values = [
        float(by_frame[frame]["leftKneeAngleDeg"]),
        float(by_frame[frame]["rightKneeAngleDeg"]),
    ]
    strike_knees[str(frame)] = values
    if min(values) > 160.0:
        raise SystemExit(f"F{frame} strike stance is too straight: {values}")
checks["strikeKneeAngles"] = strike_knees

result = {
    "status": "pass",
    "mode": "fast-keypose-review",
    "frames": frames,
    "checks": checks,
}
(root / "semantic_checks.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(result, indent=2))
