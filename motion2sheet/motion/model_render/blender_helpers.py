from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import bpy
from mathutils import Quaternion, Vector

from motion2sheet.motion.skin import compare_skin_bindings, vertex_order_hash

SOURCE_INDEX_ATTRIBUTE = "_M2S_SOURCE_VERTEX"
SOURCE_OBJECT_EXTRA = "m2sSourceObject"


def matrix16(matrix) -> list[float]:
    return [float(matrix[row][column]) for row in range(4) for column in range(4)]


def mesh_objects() -> list[bpy.types.Object]:
    return sorted((obj for obj in bpy.context.scene.objects if obj.type == "MESH"), key=lambda obj: obj.name)


def mesh_layout(objects: list[bpy.types.Object] | None = None) -> list[dict[str, Any]]:
    objects = objects if objects is not None else mesh_objects()
    return [
        {
            "object": obj.name,
            "vertexCount": len(obj.data.vertices),
            "vertexOrderHash": vertex_order_hash([tuple(float(value) for value in vertex.co) for vertex in obj.data.vertices]),
            "objectTransform": matrix16(obj.matrix_world),
        }
        for obj in sorted(objects, key=lambda item: item.name)
    ]


def capture_source_skin(objects: list[bpy.types.Object], armature: bpy.types.Object, rig_bones: set[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for obj in sorted(objects, key=lambda item: item.name):
        modifiers = [modifier for modifier in obj.modifiers if modifier.type == "ARMATURE" and modifier.object == armature]
        if len(modifiers) != 1:
            raise RuntimeError(f"mesh {obj.name!r} must have exactly one Armature modifier bound to {armature.name!r}; found {len(modifiers)}")
        group_names = {group.index: group.name for group in obj.vertex_groups}
        rows: dict[int, list[list[Any]]] = {}
        unknown: set[str] = set()
        for vertex in obj.data.vertices:
            influences: list[list[Any]] = []
            for membership in vertex.groups:
                weight = float(membership.weight)
                if weight <= 0.0:
                    continue
                name = group_names.get(membership.group)
                if name is None:
                    raise RuntimeError(f"mesh {obj.name!r} vertex {vertex.index} references missing vertex-group index {membership.group}")
                if name not in rig_bones:
                    unknown.add(name)
                influences.append([name, weight])
            if influences:
                rows[int(vertex.index)] = influences
        if unknown:
            raise RuntimeError(f"mesh {obj.name!r} skin references unknown character-rig bones: {sorted(unknown)}")
        if not rows:
            raise RuntimeError(f"mesh {obj.name!r} has no weighted vertices")
        modifier = modifiers[0]
        result[obj.name] = {
            "sourceVertexCount": len(obj.data.vertices),
            "weights": rows,
            "armatureModifier": {"name": modifier.name, "object": armature.name},
            "objectTransform": matrix16(obj.matrix_world),
        }
    if not result:
        raise RuntimeError("source FBX contains no usable skinned mesh objects")
    return result


def bake_source_meshes_to_frame(
    objects: list[bpy.types.Object],
    armature: bpy.types.Object,
    frame: int,
) -> dict[str, Any]:
    """Bake the source Armature deformation into geometry at the canonical rest frame.

    Mixamo FBX mesh bind geometry can differ from the canonicalized Blender rig rest
    geometry even when the visible skinned character is correct. Skin Contract v1
    reconstructs Blender Armature deformation from a geometry-only GLB, rest rig and
    vertex weights, so the GLB base geometry must represent the same rest pose as the
    exported character rig. Apply only the source Armature modifier at the proven rest
    frame before stripping binding authority. Armature deformation preserves topology.
    """
    scene = bpy.context.scene
    scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    rows: list[dict[str, Any]] = []
    for obj in sorted(objects, key=lambda item: item.name):
        modifiers = [modifier for modifier in obj.modifiers if modifier.type == "ARMATURE" and modifier.object == armature]
        if len(modifiers) != 1:
            raise RuntimeError(
                f"mesh {obj.name!r} rest bake requires exactly one source Armature modifier; found {len(modifiers)}"
            )
        modifier = modifiers[0]
        vertex_count = len(obj.data.vertices)
        world_before = matrix16(obj.matrix_world.copy())
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        result = bpy.ops.object.modifier_apply(modifier=modifier.name)
        if "FINISHED" not in result:
            raise RuntimeError(f"mesh {obj.name!r} Armature rest bake failed: {sorted(result)}")
        if len(obj.data.vertices) != vertex_count:
            raise RuntimeError(
                f"mesh {obj.name!r} Armature rest bake changed topology: {vertex_count} -> {len(obj.data.vertices)}"
            )
        if matrix16(obj.matrix_world) != world_before:
            raise RuntimeError(f"mesh {obj.name!r} Armature rest bake changed object transform")
        rows.append({"object": obj.name, "vertexCount": vertex_count})
    if not rows:
        raise RuntimeError("Armature rest bake received no skinned meshes")
    bpy.context.view_layer.update()
    return {
        "mode": "apply-source-armature-at-canonical-rest-frame",
        "frame": int(frame),
        "meshCount": len(rows),
        "vertexCount": sum(int(row["vertexCount"]) for row in rows),
        "topologyPreserved": True,
        "meshes": rows,
    }


def _add_source_index_attribute(obj: bpy.types.Object) -> None:
    mesh = obj.data
    existing = mesh.attributes.get(SOURCE_INDEX_ATTRIBUTE)
    if existing is not None:
        mesh.attributes.remove(existing)
    attribute = mesh.attributes.new(name=SOURCE_INDEX_ATTRIBUTE, type="FLOAT", domain="POINT")
    for vertex in mesh.vertices:
        attribute.data[vertex.index].value = float(vertex.index)


def strip_source_binding_for_glb(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        source_name = obj.name
        world = obj.matrix_world.copy()
        obj[SOURCE_OBJECT_EXTRA] = source_name
        _add_source_index_attribute(obj)
        for modifier in list(obj.modifiers):
            if modifier.type == "ARMATURE":
                obj.modifiers.remove(modifier)
        obj.vertex_groups.clear()
        obj.animation_data_clear()
        obj.parent = None
        obj.matrix_world = world


def export_geometry_glb(path: Path, objects: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in sorted(objects, key=lambda item: item.name):
        obj.select_set(True)
    if objects:
        bpy.context.view_layer.objects.active = sorted(objects, key=lambda item: item.name)[0]
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_animations=False,
        export_skins=False,
        export_morph=False,
        export_attributes=True,
        export_extras=True,
        export_materials="EXPORT",
        export_apply=False,
    )


def import_geometry_glb(path: Path) -> list[bpy.types.Object]:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects = mesh_objects()
    if not objects:
        raise RuntimeError("model.glb imported without mesh geometry")
    return objects


def _source_vertex_ids(obj: bpy.types.Object, source_vertex_count: int) -> list[int]:
    attribute = obj.data.attributes.get(SOURCE_INDEX_ATTRIBUTE)
    if attribute is None or attribute.domain != "POINT":
        raise RuntimeError(f"model mesh {obj.name!r} lost required {SOURCE_INDEX_ATTRIBUTE} POINT attribute during GLB round-trip")
    result: list[int] = []
    for vertex in obj.data.vertices:
        raw = float(attribute.data[vertex.index].value)
        source_index = int(round(raw))
        if abs(raw - source_index) > 1e-4 or source_index < 0 or source_index >= source_vertex_count:
            raise RuntimeError(f"model mesh {obj.name!r} has invalid source vertex mapping at vertex {vertex.index}: {raw}")
        result.append(source_index)
    return result


def build_final_skin_meshes(objects: list[bpy.types.Object], source_skin: dict[str, dict[str, Any]], armature_name: str) -> list[dict[str, Any]]:
    meshes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in sorted(objects, key=lambda item: item.name):
        source_name = str(obj.get(SOURCE_OBJECT_EXTRA, obj.name))
        if source_name not in source_skin:
            raise RuntimeError(f"GLB mesh {obj.name!r} has no exact source mesh identity {source_name!r}")
        if source_name in seen:
            raise RuntimeError(f"GLB contains duplicate source mesh identity: {source_name}")
        seen.add(source_name)
        if obj.name != source_name:
            obj.name = source_name
        source = source_skin[source_name]
        source_ids = _source_vertex_ids(obj, int(source["sourceVertexCount"]))
        weights = []
        for vertex_index, source_index in enumerate(source_ids):
            influences = source["weights"].get(source_index)
            if influences:
                weights.append({"vertex": vertex_index, "influences": influences})
        meshes.append(
            {
                "object": obj.name,
                "vertexCount": len(obj.data.vertices),
                "vertexOrderHash": vertex_order_hash([tuple(float(value) for value in vertex.co) for vertex in obj.data.vertices]),
                "objectTransform": matrix16(obj.matrix_world),
                "armatureModifier": {"name": source["armatureModifier"]["name"], "object": armature_name},
                "weights": weights,
            }
        )
    missing = sorted(set(source_skin) - seen)
    if missing:
        raise RuntimeError(f"model.glb lost source mesh objects: {missing}")
    return meshes


def reconstruct_skin(objects: list[bpy.types.Object], armature: bpy.types.Object, skin: dict[str, Any]) -> dict[str, Any]:
    by_name = {obj.name: obj for obj in objects}
    reconstructed = copy.deepcopy(skin)
    rebuilt_meshes = []
    for mesh in skin["meshes"]:
        obj = by_name.get(mesh["object"])
        if obj is None:
            raise RuntimeError(f"model missing skin mesh object: {mesh['object']}")
        obj.vertex_groups.clear()
        for bone_name in skin["boneTable"]:
            obj.vertex_groups.new(name=bone_name)
        groups = {group.name: group for group in obj.vertex_groups}
        for row in mesh["weights"]:
            vertex = int(row["vertex"])
            for bone_name, weight in row["influences"]:
                groups[bone_name].add([vertex], float(weight), "REPLACE")
        for modifier in list(obj.modifiers):
            if modifier.type == "ARMATURE":
                obj.modifiers.remove(modifier)
        modifier = obj.modifiers.new(name=mesh["armatureModifier"]["name"], type="ARMATURE")
        modifier.object = armature
        weights = []
        group_names = {group.index: group.name for group in obj.vertex_groups}
        for vertex in obj.data.vertices:
            influences = sorted(
                [[group_names[membership.group], float(membership.weight)] for membership in vertex.groups if float(membership.weight) > 0.0],
                key=lambda item: item[0],
            )
            if influences:
                weights.append({"vertex": int(vertex.index), "influences": influences})
        rebuilt = copy.deepcopy(mesh)
        rebuilt["weights"] = weights
        rebuilt_meshes.append(rebuilt)
    reconstructed["meshes"] = rebuilt_meshes
    return reconstructed


def setup_camera_and_render(request: dict[str, Any], armature: bpy.types.Object) -> None:
    scene = bpy.context.scene
    canvas = request["canvas"]
    background = request["background"]
    camera_profile = request["camera"]
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    if "renderSamples" in request:
        render_samples = int(request["renderSamples"])
        if render_samples <= 0:
            raise ValueError("renderSamples must be positive")
        scene.eevee.taa_render_samples = render_samples
    scene.render.resolution_x = int(canvas[0])
    scene.render.resolution_y = int(canvas[1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = bool(background["transparent"])
    scene.world.color = tuple(float(value) for value in background["rgba"][:3])
    camera_data = bpy.data.cameras.new("RenderCamera")
    camera = bpy.data.objects.new("RenderCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = float(camera_profile["orthoScale"])
    base_location = Vector(tuple(float(value) for value in camera_profile["location"]))
    base_target = Vector(tuple(float(value) for value in camera_profile["target"]))
    root = request["rootBone"]
    frames = sorted(int(frame) for frame in request["selectedFrames"])
    scene.frame_set(frames[0])
    base_root = armature.matrix_world @ armature.pose.bones[root].head
    for frame in frames:
        scene.frame_set(frame)
        current_root = armature.matrix_world @ armature.pose.bones[root].head
        delta = current_root - base_root if camera_profile.get("followRoot") else Vector((0.0, 0.0, 0.0))
        camera.location = base_location + delta
        target = base_target + delta
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
    for name, energy, location, size in (("Key", 700, (3, -4, 6), 5), ("Fill", 350, (-3, -2, 3), 4)):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.size = size
        light = bpy.data.objects.new(name, light_data)
        bpy.context.collection.objects.link(light)
        light.location = location
    output = Path(request["output"])
    frame_dir = output / ".frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        scene.frame_set(frame)
        scene.render.filepath = str(frame_dir / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)


def _world_point(armature: bpy.types.Object, point) -> Vector:
    return armature.matrix_world @ point


def _bone_direction(armature: bpy.types.Object, name: str) -> Vector:
    bone = armature.pose.bones[name]
    direction = _world_point(armature, bone.tail) - _world_point(armature, bone.head)
    return direction.normalized()


def _angle(first: Vector, second: Vector) -> float:
    return math.degrees(first.angle(second)) if first.length and second.length else 0.0


def _bend(armature: bpy.types.Object, first: str, second: str) -> float:
    return _angle(_bone_direction(armature, first), _bone_direction(armature, second))


def playback_diagnostics(reference_arm: bpy.types.Object, character_arm: bpy.types.Object, animation: dict[str, Any], root_bone: str) -> dict[str, Any]:
    semantics = {
        "leftUpperArm": "mixamorig:LeftArm",
        "leftForeArm": "mixamorig:LeftForeArm",
        "rightUpperArm": "mixamorig:RightArm",
        "rightForeArm": "mixamorig:RightForeArm",
        "leftThigh": "mixamorig:LeftUpLeg",
        "leftShin": "mixamorig:LeftLeg",
        "rightThigh": "mixamorig:RightUpLeg",
        "rightShin": "mixamorig:RightLeg",
    }
    required = set(semantics.values()) | {"mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:RightUpLeg", "mixamorig:RightLeg"}
    missing = sorted(required - set(character_arm.pose.bones.keys()))
    if missing:
        raise RuntimeError(f"Level-1 Mixamo playback diagnostics missing required bones: {missing}")
    max_direction = max_bend = max_local = max_root = 0.0
    worst_direction = worst_bend = worst_local = worst_root = None
    frames = {int(row["frame"]): row for row in animation["frames"]}
    first, last = min(frames), max(frames)
    reference_root: list[Vector] = []
    character_root: list[Vector] = []
    for frame in sorted(frames):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        for semantic, bone_name in semantics.items():
            error = _angle(_bone_direction(reference_arm, bone_name), _bone_direction(character_arm, bone_name))
            if error > max_direction:
                max_direction, worst_direction = error, {"frame": frame, "semantic": semantic, "bone": bone_name}
        for label, upper, lower in (
            ("leftElbow", "mixamorig:LeftArm", "mixamorig:LeftForeArm"),
            ("rightElbow", "mixamorig:RightArm", "mixamorig:RightForeArm"),
            ("leftKnee", "mixamorig:LeftUpLeg", "mixamorig:LeftLeg"),
            ("rightKnee", "mixamorig:RightUpLeg", "mixamorig:RightLeg"),
        ):
            error = abs(_bend(reference_arm, upper, lower) - _bend(character_arm, upper, lower))
            if error > max_bend:
                max_bend, worst_bend = error, {"frame": frame, "semantic": label}
        for bone_name, transform in frames[frame]["bones"].items():
            expected = Quaternion(tuple(float(value) for value in transform["rotationQuaternion"]))
            actual = character_arm.pose.bones[bone_name].rotation_quaternion.normalized()
            error = math.degrees(expected.rotation_difference(actual).angle)
            if error > max_local:
                max_local, worst_local = error, {"frame": frame, "bone": bone_name}
        if frame in (first, last):
            reference_root.append(_world_point(reference_arm, reference_arm.pose.bones[root_bone].head))
            character_root.append(_world_point(character_arm, character_arm.pose.bones[root_bone].head))
    if len(reference_root) == 2:
        reference_delta = reference_root[1] - reference_root[0]
        character_delta = character_root[1] - character_root[0]
        if reference_delta.length > 1e-9 and character_delta.length > 1e-9:
            max_root = _angle(reference_delta, character_delta)
            worst_root = {"firstFrame": first, "lastFrame": last}
    expected_names = set(frames[first]["bones"])
    names_ok = set(reference_arm.pose.bones.keys()) == set(character_arm.pose.bones.keys()) == expected_names
    passed = max_direction <= 0.001 and max_bend <= 0.001 and max_local <= 0.0001 and max_root <= 0.001 and names_ok
    return {
        "pass": passed,
        "appliedBoneCount": len(expected_names),
        "leftRightIdentityPass": names_ok,
        "fullBonePlayback": names_ok,
        "maxSemanticDirectionErrorDegrees": max_direction,
        "worstSemanticDirection": worst_direction,
        "maxJointBendErrorDegrees": max_bend,
        "worstJointBend": worst_bend,
        "maxLocalRotationErrorDegrees": max_local,
        "worstLocalRotation": worst_local,
        "rootMotion": {"directionPreserved": max_root <= 0.001, "directionErrorDegrees": max_root, "worst": worst_root},
    }
