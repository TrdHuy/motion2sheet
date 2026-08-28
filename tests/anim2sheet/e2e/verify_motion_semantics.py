from __future__ import annotations

import json
import math
import sys
from pathlib import Path

root = Path(sys.argv[1])
debug = json.loads((root / "motion_debug.json").read_text(encoding="utf-8"))
reference = json.loads((root / "pose_reference.json").read_text(encoding="utf-8"))
samples = debug["samples"]

if len(samples) != 16:
    raise SystemExit(f"expected 16 debug samples, got {len(samples)}")
if len(reference.get("keyPoses", [])) != 16:
    raise SystemExit("expected 16 reference key poses")

by_frame = {int(row["frame"]): row for row in samples}
if sorted(by_frame) != list(range(1, 17)):
    raise SystemExit("debug samples are not exactly frames 1..16")

max_ik = 0.0
worst = None
for row in samples:
    for name, value in row["ikError"].items():
        value = float(value)
        if value > max_ik:
            max_ik = value
            worst = (row["frame"], name, value)
if max_ik > 0.18:
    raise SystemExit(f"reference IK fit too loose: max={max_ik:.4f} worst={worst}")

root_delta = float(samples[-1]["root"][0]) - float(samples[0]["root"][0])
min_root_z = min(float(row["root"][1]) for row in samples)
if root_delta < 0.15:
    raise SystemExit(f"forward/root displacement too small: {root_delta}")
if min_root_z > -0.04:
    raise SystemExit(f"anticipation crouch too weak: min root z={min_root_z}")

def sword_dx(frame: int) -> float:
    row = by_frame[frame]
    return float(row["swordTip"][0]) - float(row["swordGrip"][0])

dx6 = sword_dx(6)
dx8 = sword_dx(8)
dx9 = sword_dx(9)
len6 = float(by_frame[6]["projectedSwordLengthXZ"])
len7 = float(by_frame[7]["projectedSwordLengthXZ"])
len8 = float(by_frame[8]["projectedSwordLengthXZ"])

if dx6 < 0.45:
    raise SystemExit(f"frame 6 must show sword to screen-right: dx={dx6}")
if dx8 > -0.45 or dx9 > -0.45:
    raise SystemExit(f"frames 8/9 must show sword to screen-left: dx8={dx8}, dx9={dx9}")
if not (len7 < len6 * 0.55 and len7 < len8 * 0.55):
    raise SystemExit(f"impact foreshortening missing: len6={len6}, len7={len7}, len8={len8}")

impact = int(debug.get("impactFrame") or 0)
if impact != 7:
    raise SystemExit(f"expected reference impact frame 7, got {impact}")

print(json.dumps({
    "reference": debug.get("reference"),
    "rootDelta": root_delta,
    "minRootZ": min_root_z,
    "maxIKError": max_ik,
    "worstIK": worst,
    "strike": {"frame6Dx": dx6, "frame7ProjectedLength": len7, "frame8Dx": dx8, "frame9Dx": dx9},
}, indent=2))
