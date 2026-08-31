"""Reusable profile-driven equipment construction and binding."""
from __future__ import annotations

from mathutils import Vector

from motion2sheet.anim2sheet.common.rig import humanoid as rig


def build_equipment(character_profile: dict) -> dict[str, object]:
    result = {}
    for item in character_profile.get("equipment", []):
        item_type = str(item.get("type", ""))
        if item_type != "sword":
            raise RuntimeError(f"unsupported humanoid equipment type: {item_type}")
        materials = {}
        for row in item.get("materials", []):
            materials[str(row["name"])] = rig.material(
                str(row["name"]),
                tuple(float(v) for v in row["color"]),
                float(row.get("metallic", 0.0)),
            )
        ctrl = rig.empty(str(item["controller"])); ctrl.rotation_mode = "QUATERNION"
        for part in item["parts"]:
            rig.controller_cylinder(
                ctrl,
                str(part["object"]),
                float(part["z0"]),
                float(part["z1"]),
                float(part["radius"]),
                materials[str(part["material"])],
            )
        result[str(item["name"])] = ctrl
    return result


def primary_equipment(character_profile: dict, equipment: dict[str, object]) -> tuple[dict, object]:
    rows = character_profile.get("equipment", [])
    if len(rows) != 1:
        raise RuntimeError(f"humanoid author currently requires exactly one equipment item, got {len(rows)}")
    row = rows[0]
    return row, equipment[str(row["name"])]


def apply_reference_guides(controller, item_profile: dict, row_targets: dict, *, frame: int) -> None:
    guides = item_profile.get("referenceGuides")
    if not guides:
        return
    grip = Vector(row_targets[str(guides["gripTarget"])])
    tip = Vector(row_targets[str(guides["tipTarget"])])
    direction = tip - grip
    if direction.length < 1e-6:
        raise RuntimeError(f"frame {frame}: equipment grip/tip guide are coincident")
    local_axis = Vector(item_profile["binding"].get("localAxis", [0, 0, 1]))
    controller.location = grip
    controller.rotation_quaternion = local_axis.rotation_difference(direction.normalized())
    controller.keyframe_insert(data_path="location", frame=frame)
    controller.keyframe_insert(data_path="rotation_quaternion", frame=frame)


def bind_two_hand(controller, binding: dict, joint_pose: dict, *, frame: int) -> tuple[Vector, Vector, Vector]:
    if binding.get("mode") != "two_hand_axis":
        raise RuntimeError(f"unsupported equipment binding: {binding.get('mode')}")
    primary_key = str(binding["primaryJoint"])
    secondary_key = str(binding["secondaryJoint"])
    primary = Vector(joint_pose[primary_key])
    secondary = Vector(joint_pose[secondary_key])
    axis = secondary - primary
    if axis.length < float(binding.get("minGripSpan", 0.08)):
        raise RuntimeError("two-hand grip points are too close")
    axis.normalize()
    local_axis = Vector(binding.get("localAxis", [0, 0, 1]))
    controller.location = primary
    controller.rotation_mode = "QUATERNION"
    controller.rotation_quaternion = local_axis.rotation_difference(axis)
    controller.keyframe_insert(data_path="location", frame=frame)
    controller.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    return primary, secondary, axis
