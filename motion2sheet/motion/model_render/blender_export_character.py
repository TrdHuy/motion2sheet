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
from motion2sheet.motion.model_render.blender_level1 import export_armature_only_fbx
from motion2sheet.motion.roundtrip.blender_common import (
    capture_rig_document,
    import_source,
    integer_action_range,
    stable_profile_id,
)
from motion2sheet.motion.roundtrip.fbx import extract_fbx_metadata_and_diagnostics
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


def _hierarchy(armature) -> dict[str, str | None]:
    return {bone.name: bone.parent.name if bone.parent else None for bone in armature.data.bones}


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

    source_sha = _sha256(source)
    armature, source_action = import_source(source)
    source_start, source_end = integer_action_range(source_action)
    source_frame_count = source_end - source_start + 1
    source_hierarchy = _hierarchy(armature)
    source_bone_names = set(source_hierarchy)
    source_armature_name = armature.name
    source_armature_world = matrix16(armature.matrix_world.copy())
    skinned = [
        obj for obj in mesh_objects()
        if any(modifier.type == "ARMATURE" and modifier.object == armature for modifier in obj.modifiers)
    ]
    if not skinned:
        raise RuntimeError("source FBX is not a usable With-Skin character: no skinned mesh bound to the animation armature")

    # Capture all source skin authority before removing any binding.
    source_skin = capture_source_skin(skinned, armature, source_bone_names)
    source_stats = _source_stats(source_skin)

    # Freeze geometry/material authority into an unskinned staging GLB before the
    # scene is cleared to canonicalize the armature. The staging/final GLBs contain
    # no vertex groups, Armature modifier, armature object, or animation authority.
    strip_source_binding_for_glb(skinned)
    staging = diagnostics / ".model-stage.glb"
    export_geometry_glb(staging, skinned)

    # The real With-Skin FBX imports with a tiny non-TRS matrix_local shear on a
    # Mixamo bone. Do not loosen PR #11. Instead round-trip only the armature/action
    # through FBX, then let the locked PR #11 rig capture validate the canonicalized
    # rest basis. Mesh/skin authority never comes from this temporary FBX.
    canonical_fbx = diagnostics / ".character-rig-canonical.fbx"
    export_armature_only_fbx(armature, canonical_fbx)
    canonical_armature, canonical_action = import_source(canonical_fbx)
    canonical_start, canonical_end = integer_action_range(canonical_action)
    canonical_frame_count = canonical_end - canonical_start + 1
    if (canonical_start, canonical_end) != (source_start, source_end):
        raise RuntimeError(
            "character Level-1 canonicalization changed animation frame range; "
            f"source={[source_start, source_end]} canonical={[canonical_start, canonical_end]}"
        )
    if canonical_frame_count != source_frame_count:
        raise RuntimeError("character Level-1 canonicalization changed source frame count")
    canonical_hierarchy = _hierarchy(canonical_armature)
    if canonical_hierarchy != source_hierarchy:
        raise RuntimeError(
            "character Level-1 canonicalization changed bone names/hierarchy; "
            f"source={source_hierarchy} canonical={canonical_hierarchy}"
        )

    # Mirror the locked PR #11 exporter ordering: capture the Blender rig first,
    # then attach static FBX transform-stack/global metadata before schema validation.
    # Character motion still does not come from this metadata; it is required only
    # because the canonical Contract B rig schema requires FBX source metadata.
    rig = capture_rig_document(canonical_fbx, canonical_armature)
    rig_bone_names = [bone["name"] for bone in rig["bones"]]
    rig_fbx, _animation_fbx, _diagnostic_curves = extract_fbx_metadata_and_diagnostics(
        canonical_fbx,
        rig_bone_names,
        canonical_frame_count,
    )
    rig["sourceFormat"] = {"fbx": rig_fbx}
    if set(rig_bone_names) != source_bone_names:
        raise RuntimeError("character Level-1 canonicalization changed the source bone set")

    # Make the public character-rig identity describe the original release asset,
    # while diagnostics below explicitly record that its numeric rest basis and
    # sourceFormat transform stack were canonicalized through an armature-only FBX
    # solely to remove importer-level non-TRS numerical shear.
    rig["id"] = stable_profile_id(source.stem, "rig")
    rig["source"] = {
        "format": "FBX",
        "filename": source.name,
        "sha256": source_sha,
        "importer": "blender-fbx",
    }
    rig = validate_rig_document(rig)
    canonical_armature_name = rig["armatureObject"]["name"]

    # Re-import the stripped geometry authority and bind Skin Contract weights to
    # the final GLB vertex layout, using the preserved source-index attribute.
    stage_objects = import_geometry_glb(staging)
    build_final_skin_meshes(stage_objects, source_skin, canonical_armature_name)
    model_path = output / "model.glb"
    export_geometry_glb(model_path, stage_objects)

    final_objects = import_geometry_glb(model_path)
    final_meshes = build_final_skin_meshes(final_objects, source_skin, canonical_armature_name)
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
            "armatureObject": canonical_armature_name,
            "armatureObjectTransform": source_armature_world,
        },
        meshes=final_meshes,
    )
    write_canonical_json(output / "rig.json", rig)
    write_skin_document(output / "skin.json", skin, rig)
    stats = skin_statistics(skin, rig)
    if stats["unknownBoneReferences"] != 0:
        raise RuntimeError(f"skin extraction produced unknown bone references: {stats}")

    canonicalization = {
        "mode": "armature-only-fbx-roundtrip",
        "reason": "remove importer-level non-TRS floating-point rest shear without modifying PR #11 tolerance or using mesh/skin authority from the temporary FBX",
        "sourceArmature": source_armature_name,
        "canonicalArmature": canonical_armature_name,
        "sourceBoneCount": len(source_hierarchy),
        "canonicalBoneCount": len(rig["bones"]),
        "exactBoneNames": True,
        "exactHierarchy": True,
        "sourceFrameRange": [source_start, source_end],
        "canonicalFrameRange": [canonical_start, canonical_end],
        "temporaryFbxSha256": _sha256(canonical_fbx),
        "temporaryContainsMesh": False,
        "temporaryContainsSkinAuthority": False,
        "sourceFormatMetadataAuthority": "temporary-armature-only-fbx-static-transform-stack",
        "motionAuthority": False,
    }
    source_diag = {
        "schema": "motion2sheet.diagnostics.source-skin",
        "version": 1,
        "source": {"filename": source.name, "sha256": source_sha},
        "armature": {"name": source_armature_name, "boneCount": len(rig["bones"])},
        "restBasisCanonicalization": canonicalization,
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
    canonical_fbx.unlink(missing_ok=True)

    report = {
        "schema": "motion2sheet.character-export",
        "version": 1,
        "sourceSha256": source_sha,
        "sourceFilename": source.name,
        "sourceSkinStatistics": source_stats,
        "skinStatistics": stats,
        "characterBoneCount": len(rig["bones"]),
        "restBasisCanonicalization": canonicalization,
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
