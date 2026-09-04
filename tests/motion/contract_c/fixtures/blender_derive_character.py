from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


RENAMES = {
    "mixamorig:Hips": "Pelvis",
    "mixamorig:Spine": "SpineLower",
    "mixamorig:Spine1": "SpineBridge",
    "mixamorig:Spine2": "ChestUpper",
    "mixamorig:Neck": "NeckBase",
    "mixamorig:Head": "Head",
    "mixamorig:LeftShoulder": "Shoulder_L",
    "mixamorig:LeftArm": "UpperArm_L",
    "mixamorig:LeftForeArm": "LowerArm_L",
    "mixamorig:LeftHand": "Hand_L",
    "mixamorig:RightShoulder": "Shoulder_R",
    "mixamorig:RightArm": "UpperArm_R",
    "mixamorig:RightForeArm": "LowerArm_R",
    "mixamorig:RightHand": "Hand_R",
    "mixamorig:LeftUpLeg": "UpperLeg_L",
    "mixamorig:LeftLeg": "LowerLeg_L",
    "mixamorig:LeftFoot": "Foot_L",
    "mixamorig:LeftToeBase": "Toe_L",
    "mixamorig:RightUpLeg": "UpperLeg_R",
    "mixamorig:RightLeg": "LowerLeg_R",
    "mixamorig:RightFoot": "Foot_R",
    "mixamorig:RightToeBase": "Toe_R",
}


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--diagnostics", required=True)
    args = parser.parse_args(_argv())
    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    diagnostics = Path(args.diagnostics).resolve()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(source), use_anim=False, ignore_leaf_bones=True)
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(armatures) != 1 or not meshes:
        raise RuntimeError(f"expected one armature and at least one mesh; found {len(armatures)} and {len(meshes)}")
    armature = armatures[0]
    missing = sorted(set(RENAMES) - set(armature.data.bones.keys()))
    if missing:
        raise RuntimeError(f"source character lacks required derived-fixture bones: {missing}")

    # A deterministic non-uniform world-space rest/proportion change. Applying the
    # same affine transform to mesh vertices and edit bones preserves skin binding.
    scale = Matrix.Diagonal((1.25, 0.90, 0.78, 1.0))
    for mesh in meshes:
        local_affine = mesh.matrix_world.inverted_safe() @ scale @ mesh.matrix_world
        for vertex in mesh.data.vertices:
            vertex.co = local_affine @ vertex.co

    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    armature_affine = armature.matrix_world.inverted_safe() @ scale @ armature.matrix_world
    for bone in armature.data.edit_bones:
        bone.head = armature_affine @ bone.head
        bone.tail = armature_affine @ bone.tail
    armature.data.edit_bones["mixamorig:LeftArm"].roll += math.radians(15.0)
    armature.data.edit_bones["mixamorig:RightArm"].roll -= math.radians(15.0)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Rename the armature and corresponding vertex groups to prove character-side
    # mapping rather than accidental source bone-name coupling.
    for old, new in RENAMES.items():
        armature.data.bones[old].name = new
    for mesh in meshes:
        for old, new in RENAMES.items():
            group = mesh.vertex_groups.get(old)
            if group is not None:
                group.name = new
    armature.name = "DerivedHumanoidB"
    armature.data.name = "DerivedHumanoidB"
    if armature.animation_data:
        armature.animation_data_clear()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    for mesh in meshes:
        mesh.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.export_scene.fbx(
        filepath=str(output),
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        add_leaf_bones=False,
        bake_anim=False,
        axis_forward="-Z",
        axis_up="Y",
    )
    diagnostics.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.write_text(
        json.dumps(
            {
                "schema": "motion2sheet.contract-c.derived-character-fixture",
                "version": 1,
                "sourceSha256": _sha256(source),
                "outputSha256": _sha256(output),
                "worldScale": [1.25, 0.90, 0.78],
                "upperArmRollDegrees": {"left": 15.0, "right": -15.0},
                "renamedBones": RENAMES,
                "meshCount": len(meshes),
                "vertexCount": sum(len(mesh.data.vertices) for mesh in meshes),
                "purpose": "Local phase-1 target with different proportions, rest basis and bone names; not an independently authored character.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
