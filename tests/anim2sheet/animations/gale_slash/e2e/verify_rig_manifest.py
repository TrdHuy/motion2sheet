from __future__ import annotations

"""Verify default Blender rig exports and canonical GameHumanoidV2 hierarchy."""

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops


root = Path(sys.argv[1])
manifest = json.loads((root / "rig_bones.json").read_text(encoding="utf-8"))

expected = {
    "Root": None,
    "Pelvis": "Root",
    "Spine": "Pelvis",
    "Chest": "Spine",
    "Neck": "Chest",
    "Head": "Neck",
    "LeftClavicle": "Chest",
    "LeftUpperArm": "LeftClavicle",
    "LeftForeArm": "LeftUpperArm",
    "LeftHand": "LeftForeArm",
    "RightClavicle": "Chest",
    "RightUpperArm": "RightClavicle",
    "RightForeArm": "RightUpperArm",
    "RightHand": "RightForeArm",
    "LeftHip": "Pelvis",
    "LeftThigh": "LeftHip",
    "LeftShin": "LeftThigh",
    "LeftFoot": "LeftShin",
    "RightHip": "Pelvis",
    "RightThigh": "RightHip",
    "RightShin": "RightThigh",
    "RightFoot": "RightShin",
}

if manifest.get("armature") != "GameHumanoidV2":
    raise SystemExit(f"unexpected armature: {manifest.get('armature')}")
if manifest.get("objectRoot") != "MotionRoot":
    raise SystemExit(f"unexpected object root: {manifest.get('objectRoot')}")

by_name = {row["name"]: row for row in manifest.get("bones", [])}
if set(by_name) != set(expected):
    raise SystemExit(
        f"bone set mismatch missing={sorted(set(expected)-set(by_name))} "
        f"extra={sorted(set(by_name)-set(expected))}"
    )
for name, parent in expected.items():
    if by_name[name].get("parent") != parent:
        raise SystemExit(
            f"{name} parent={by_name[name].get('parent')!r}, expected {parent!r}"
        )

overview = Image.open(root / "rig_default_overview.png").convert("RGBA")
labeled = Image.open(root / "rig_default_labeled.png").convert("RGBA")
if overview.size != labeled.size:
    raise SystemExit("rig overview/labeled image sizes differ")
if overview.width < 512 or overview.height < 512:
    raise SystemExit(f"rig inspection image too small: {overview.size}")
if ImageChops.difference(overview, labeled).getbbox() is None:
    raise SystemExit(
        "labeled rig image is identical to overview; bone names were not captured"
    )

text = (root / "rig_bones.txt").read_text(encoding="utf-8")
for required in ("Pelvis", "LeftHip", "RightHip", "LeftClavicle", "RightClavicle"):
    if required not in text:
        raise SystemExit(f"rig_bones.txt missing {required}")

print(json.dumps({
    "armature": manifest["armature"],
    "boneCount": manifest["boneCount"],
    "overviewSize": overview.size,
    "labeledDiffers": True,
}, indent=2))
