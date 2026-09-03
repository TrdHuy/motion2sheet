from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import bpy

from motion2sheet.motion.model_render.blender_helpers import (
    build_final_skin_meshes,
    capture_source_skin,
    export_geometry_glb,
    import_geometry_glb,
    matrix16,
    mesh_objects,
    strip_source_binding_for_glb,
)
from motion2sheet.motion.roundtrip.blender_common import capture_rig_document, import_source, stable_profile_id
from motion2sheet.motion.roundtrip.schema import validate_rig_document, write_canonical_json
from motion2sheet.motion.skin import build_skin_document, skin_statistics, write_skin_document


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_stats(source_skin: dict[str, dict]) -> dict[str, int]:
    return {
        "meshCount": len(source_skin),
        "vertexCount": sum(int(mesh["sourceVertexCount"]) for mesh in source_skin.values()),
        "weightedVertexCount": sum(len(mesh["weights"]) for mesh in source_skin.values()),
        "influenceCount": sum(len(influences) for mesh in source_skin.values() for influences in mesh["weights"].values()),
    }


def _orthogonalize_imported_edit_rest(armature) -> None:
    """Rewrite imported edit-bone head/tail/roll to themselves.

    Some real Mixamo With-Skin FBX files contain tiny floating-point shear in
    Bone.matrix_local after import. The character contract's rest authority is
    Blender edit-bone geometry, so explicitly committing the exact imported
    head/tail/roll values removes only that non-representable matrix shear.
    """
    bpy.ops.object.mode_set(mode="OBJECT") if armature.mode != "OBJECT" else None
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        snapshots = [
            (bone.name, bone.head.copy(), bone.tail.copy(), float(bone.roll))
            for bone in armature.data.edit_bones
        ]
        for name, head, tail, roll in snapshots:
            bone = armature.data.edit_bones[name]
            bone.head = head
            bone.tail = tail
            bone.roll = roll
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(_argv())
    source = Path(args.input).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    diagnostics = output / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() != ".fbx":
        raise RuntimeError("export-character supports FBX With-Skin sources only")

    armature, _action = import_source(source)
    source_bone_names = {bone.name for bone in armature.data.bones}
    armature_name = armature.name
    armature_world = matrix16(armature.matrix_world.copy())
    skinned = [
        obj for obj in mesh_objects()
        if any(modifier.type == "ARMATURE" and modifier.object == armature for modifier in obj.modifiers)
    ]
    if not skinned:
        raise RuntimeError("source FBX is not a usable With-Skin character: no skinned mesh bound to the animation armature")
    source_skin = capture_source_skin(skinned, armature, source_bone_names)
    source_stats = _source_stats(source_skin)

    _orthogonalize_imported_edit_rest(armature)
    rig = validate_rig_document(capture_rig_document(source, armature))
    rig_names = {bone["name"] for bone in rig["bones"]}
    if rig_names != source_bone_names:
        raise RuntimeError("character rest-basis normalization changed the source bone set")

    strip_source_binding_for_glb(skinned)
    staging = diagnostics / ".model-stage.glb"
    export_geometry_glb(staging, skinned)

    stage_objects = import_geometry_glb(staging)
    build_final_skin_meshes(stage_objects, source_skin, armature_name)
    model_path = output / "model.glb"
    export_geometry_glb(model_path, stage_objects)

    final_objects = import_geometry_glb(model_path)
    final_meshes = build_final_skin_meshes(final_objects, source_skin, armature_name)
    if any(obj.vertex_groups for obj in final_objects):
        raise RuntimeError("model.glb unexpectedly retained vertex groups; skin.json authority proof would be invalid")
    if any(any(modifier.type == "ARMATURE" for modifier in obj.modifiers) for obj in final_objects):
        raise RuntimeError("model.glb unexpectedly retained Armature modifiers; skin.json authority proof would be invalid")
    if any(obj.type == "ARMATURE" for obj in bpy.context.scene.objects):
        raise RuntimeError("model.glb unexpectedly retained an armature object; final model must be geometry/material authority only")

    model_sha = _sha256(model_path)
    skin = build_skin_document(
        skin_id=stable_profile_id(source.stem, "skin"),
        canonical_rig="mixamo-compatible-v1",
        character_rig=rig,
        model={
            "filename": "model.glb",
            "format": "GLB",
            "sha256": model_sha,
            "coordinateSystem": rig["coordinateSystem"],
        },
        bind={
            "mode": "blender-armature-modifier-v1",
            "restConvention": "blender-edit-bone-y-axis-roll-v1",
            "armatureObject": armature_name,
            "armatureObjectTransform": armature_world,
        },
        meshes=final_meshes,
    )
    write_canonical_json(output / "rig.json", rig)
    write_skin_document(output / "skin.json", skin, rig)
    stats = skin_statistics(skin, rig)
    if stats["unknownBoneReferences"] != 0:
        raise RuntimeError(f"skin extraction produced unknown bone references: {stats}")

    source_diag = {
        "schema": "motion2sheet.diagnostics.source-skin",
        "version": 1,
        "source": {"filename": source.name, "sha256": _sha256(source)},
        "armature": {"name": armature_name, "boneCount": len(rig["bones"])},
        "restBasisNormalization": {
            "mode": "commit-imported-edit-head-tail-roll",
            "reason": "remove only non-TRS floating-point shear while preserving exact edit-bone rest authority",
            "boneSetPreserved": True,
        },
        "statistics": source_stats,
        "meshes": [
            {
                "object": name,
                "vertexCount": int(row["sourceVertexCount"]),
                "weightedVertexCount": len(row["weights"]),
                "influenceCount": sum(len(value) for value in row["weights"].values()),
            }
            for name, row in sorted(source_skin.items())
        ],
    }
    write_canonical_json(diagnostics / "source_skin.json", source_diag)
    staging.unlink(missing_ok=True)
    report = {
        "schema": "motion2sheet.character-export",
        "version": 1,
        "sourceSha256": _sha256(source),
        "sourceFilename": source.name,
        "sourceSkinStatistics": source_stats,
        "skinStatistics": stats,
        "characterBoneCount": len(rig["bones"]),
        "restBasisNormalization": source_diag["restBasisNormalization"],
        "modelAuthority": {
            "format": "GLB",
            "sha256": model_sha,
            "containsArmatureObjects": False,
            "containsArmatureModifiers": False,
            "containsVertexGroups": False,
            "sourceVertexMappingAttribute": "_M2S_SOURCE_VERTEX",
        },
        "outputs": {
            "modelGlb": "model.glb",
            "modelGlbBytes": model_path.stat().st_size,
            "rigJson": "rig.json",
            "rigJsonBytes": (output / "rig.json").stat().st_size,
            "skinJson": "skin.json",
            "skinJsonBytes": (output / "skin.json").stat().st_size,
            "sourceSkinDiagnostics": "diagnostics/source_skin.json",
        },
    }
    write_canonical_json(diagnostics / "export.json", report)
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
