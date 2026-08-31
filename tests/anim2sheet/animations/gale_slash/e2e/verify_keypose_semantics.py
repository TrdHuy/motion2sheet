from __future__ import annotations

import json
import math
import sys
from pathlib import Path


root = Path(sys.argv[1])
debug = json.loads((root / "motion_debug.json").read_text(encoding="utf-8"))
samples = debug.get("samples", [])
frames = [int(row["frame"]) for row in samples]
if frames != [1, 6, 7, 8]:
    raise SystemExit(f"expected only F1/F6/F7/F8, got {frames}")
if debug.get("armControl") != "deterministic_joint_fk":
    raise SystemExit("fast review must use deterministic_joint_fk arms")

by_frame = {int(row["frame"]): row for row in samples}


def point(frame: int, name: str):
    return tuple(float(v) for v in by_frame[frame]["joints"][name])


def distance(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def sword_dx(frame: int):
    row = by_frame[frame]
    return float(row["swordTip"][0]) - float(row["swordGrip"][0])


max_joint_error = max(float(row["maxArmJointContractError"]) for row in samples)
if max_joint_error > 0.008:
    raise SystemExit(f"arm joint contract drift too high: {max_joint_error:.6f}m")

for frame in frames:
    grip = by_frame[frame]["weaponGripContract"]
    if float(grip["primaryLeftWristError"]) > 0.008:
        raise SystemExit(f"F{frame} sword origin drifted from primary hand")
    if float(grip["rightWristAxisError"]) > 0.008:
        raise SystemExit(f"F{frame} secondary hand is off sword grip axis")
    along = float(grip["rightWristAlongGrip"])
    if not (0.08 <= along <= 0.18):
        raise SystemExit(f"F{frame} two-hand spacing is implausible: {along:.4f}m")

# F1 anatomy proof: elbows must remain on their own anatomical side, below the
# shoulders, while the low stance is visibly loaded. This specifically guards
# against the old cross-body/chicken-wing result that endpoint IK allowed.
f1 = by_frame[1]
ls = point(1, "leftShoulder")
le = point(1, "leftElbow")
rs = point(1, "rightShoulder")
re = point(1, "rightElbow")
if le[0] >= ls[0] + 0.03:
    raise SystemExit(f"F1 left elbow crossed inward: shoulder={ls[0]:.3f} elbow={le[0]:.3f}")
if re[0] <= rs[0] - 0.03:
    raise SystemExit(f"F1 right elbow crossed inward: shoulder={rs[0]:.3f} elbow={re[0]:.3f}")
if le[2] >= ls[2] - 0.08 or re[2] >= rs[2] - 0.08:
    raise SystemExit("F1 elbows are not relaxed below shoulders")
if float(f1["root"][1]) > -0.05:
    raise SystemExit(f"F1 ready stance is not low enough: rootZ={f1['root'][1]}")
if min(float(f1["leftKneeAngleDeg"]), float(f1["rightKneeAngleDeg"])) > 165.0:
    raise SystemExit("F1 ready stance lacks visible knee flexion")
if not (55.0 <= float(f1["leftElbowAngleDeg"]) <= 125.0):
    raise SystemExit(f"F1 left elbow angle is anatomically weak: {f1['leftElbowAngleDeg']}")
if not (55.0 <= float(f1["rightElbowAngleDeg"]) <= 125.0):
    raise SystemExit(f"F1 right elbow angle is anatomically weak: {f1['rightElbowAngleDeg']}")

# F6 strike entry must read as a real two-arm drive, not a compressed wrist-only
# reach, and the sword axis must already be screen-right.
f6 = by_frame[6]
avg_ext6 = (float(f6["leftArmExtension"]) + float(f6["rightArmExtension"])) * 0.5
if avg_ext6 < 0.34:
    raise SystemExit(f"F6 arm drive too compressed: avg extension={avg_ext6:.4f}")
if sword_dx(6) < 0.8:
    raise SystemExit(f"F6 sword must clearly point screen-right: dx={sword_dx(6):.4f}")

# F7 must keep readable depth foreshortening while both hands remain on the same
# deterministic grip axis.
f7_len = float(by_frame[7]["projectedSwordLengthXZ"])
if not (0.18 <= f7_len <= 0.30):
    raise SystemExit(f"F7 depth projection not readable: {f7_len:.4f}m")

# F8 must exit to screen-left and the elbow topology must evolve continuously
# from F7 rather than flipping to a different solver solution.
if sword_dx(8) > -0.8:
    raise SystemExit(f"F8 sword must clearly point screen-left: dx={sword_dx(8):.4f}")
left_78 = distance(point(7, "leftElbow"), point(8, "leftElbow"))
right_78 = distance(point(7, "rightElbow"), point(8, "rightElbow"))
if left_78 > 0.24 or right_78 > 0.24:
    raise SystemExit(
        f"F7->F8 elbow topology jump too large: left={left_78:.4f} right={right_78:.4f}"
    )

print(json.dumps({
    "mode": debug.get("mode"),
    "frames": frames,
    "maxArmJointContractError": max_joint_error,
    "f1": {
        "leftElbowAngleDeg": f1["leftElbowAngleDeg"],
        "rightElbowAngleDeg": f1["rightElbowAngleDeg"],
        "leftKneeAngleDeg": f1["leftKneeAngleDeg"],
        "rightKneeAngleDeg": f1["rightKneeAngleDeg"],
    },
    "f6AverageArmExtension": avg_ext6,
    "f7ProjectedSwordLengthXZ": f7_len,
    "f7ToF8ElbowTravel": {"left": left_78, "right": right_78},
    "swordDx": {"6": sword_dx(6), "8": sword_dx(8)},
}, indent=2))
