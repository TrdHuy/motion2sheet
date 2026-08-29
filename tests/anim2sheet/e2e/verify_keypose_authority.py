from __future__ import annotations

"""Fail-fast saved-blend and proxy authority checks for the 4 key poses."""

import json
import sys
from pathlib import Path


root = Path(sys.argv[1])
path = root / "reopen_debug.json"
if not path.is_file():
    raise SystemExit("reopen_debug.json is missing")

data = json.loads(path.read_text(encoding="utf-8"))
if data.get("frames") != [1, 6, 7, 8]:
    raise SystemExit(f"unexpected reopen diagnostic frames: {data.get('frames')}")

summary = data["summary"]

# Persistence must be tighter than the normal authored-joint semantic gate:
# reopening the same saved blend should not materially change an evaluated
# transform at all. Authored-vs-post uses the existing deterministic tolerance.
if float(summary["maxPrePostJointError"]) > 0.001:
    raise SystemExit(
        "saved source.blend is not authoritative: pre-save/post-reopen joint "
        f"drift={summary['maxPrePostJointError']:.6f}m"
    )
if float(summary["maxAuthoredPostReopenJointError"]) > 0.008:
    raise SystemExit(
        "post-reopen evaluated arm joints no longer match authored contract: "
        f"{summary['maxAuthoredPostReopenJointError']:.6f}m"
    )

required_proxies = {
    "Body_LeftUpperArm",
    "Body_LeftForeArm",
    "Body_RightUpperArm",
    "Body_RightForeArm",
    "Review_LeftClavicle",
    "Review_RightClavicle",
    "Review_LeftHand",
    "Review_RightHand",
}
missing = []
max_endpoint = 0.0
max_center = 0.0
max_angle = 0.0
max_length = 0.0
for frame_row in data["framesData"]:
    frame = int(frame_row["frame"])
    segments = frame_row["proxySegments"]
    for name in sorted(required_proxies):
        row = segments.get(name)
        if not row or row.get("missing"):
            missing.append(f"F{frame}:{name}")
            continue
        max_endpoint = max(max_endpoint, float(row["endpointError"]))
        max_center = max(max_center, float(row["centerError"]))
        max_angle = max(max_angle, float(row["axisAngleDeg"]))
        max_length = max(max_length, float(row["lengthError"]))

if missing:
    raise SystemExit(f"required proxy authority segments are missing: {missing}")
if max_endpoint > 0.006:
    raise SystemExit(f"proxy endpoints drift from evaluated bones: {max_endpoint:.6f}m")
if max_center > 0.004:
    raise SystemExit(f"proxy centers drift from evaluated bones: {max_center:.6f}m")
if max_angle > 1.0:
    raise SystemExit(f"proxy axes disagree with evaluated bones: {max_angle:.3f}deg")
if max_length > 0.006:
    raise SystemExit(f"proxy segment length disagrees with evaluated bone: {max_length:.6f}m")

for required in [
    root / "object_skeleton_overlay.png",
    *(root / "overlay_frames" / f"{frame:02d}.png" for frame in (1, 6, 7, 8)),
]:
    if not required.is_file():
        raise SystemExit(f"authority overlay missing: {required}")

result = {
    "status": "pass",
    "mode": "keypose-authority",
    "jointPersistence": {
        "maxPrePostJointError": summary["maxPrePostJointError"],
        "maxAuthoredPostReopenJointError": summary["maxAuthoredPostReopenJointError"],
    },
    "proxyConsistency": {
        "maxEndpointError": round(max_endpoint, 6),
        "maxCenterError": round(max_center, 6),
        "maxAxisAngleDeg": round(max_angle, 6),
        "maxLengthError": round(max_length, 6),
    },
}
(root / "authority_checks.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
