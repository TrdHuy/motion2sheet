from __future__ import annotations

from dataclasses import dataclass

from .math3d import (
    Mat3,
    Mat4,
    Vec3,
    add,
    cross,
    distance,
    dot,
    from_trs,
    inverse_affine,
    length,
    mul,
    mul3,
    mul3v,
    mul4,
    point,
    rest_matrix,
    rotation4,
    sub,
    transpose3,
    translation4,
    unit,
    with_rotation,
)


@dataclass(frozen=True)
class BoneRest:
    name: str
    parent: str | None
    matrix: Mat4
    length: float


def axis_vector(axis: str) -> Vec3:
    values = {
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    try:
        return values[str(axis).upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported anatomical reference axis {axis!r}") from exc


def _columns(x: Vec3, y: Vec3, z: Vec3) -> Mat3:
    return (
        (x[0], y[0], z[0]),
        (x[1], y[1], z[1]),
        (x[2], y[2], z[2]),
    )


def anatomical_frame(rotation: Mat3, reference_axis: Vec3, label: str) -> Mat3:
    """Build a roll-independent anatomical frame for a bone rest/pose basis.

    +Y is always the bone head->tail axis. The explicit mapping reference axis
    defines anatomical +Z after projection onto the plane perpendicular to +Y.
    This intentionally does not trust Blender/EditBone roll equivalence between
    unrelated source and target rigs.
    """
    y = unit((rotation[0][1], rotation[1][1], rotation[2][1]), f"{label} +Y")
    projected = sub(reference_axis, mul(y, dot(reference_axis, y)))
    if length(projected) <= 1e-6:
        raise ValueError(
            f"{label} anatomical reference axis is parallel to bone +Y; "
            "mapping must declare a different per-bone reference axis"
        )
    z = unit(projected, f"{label} anatomical +Z")
    x = unit(cross(y, z), f"{label} anatomical +X")
    return _columns(x, y, z)


def _target_rest(target_rig: dict) -> tuple[dict[str, BoneRest], list[str]]:
    rests: dict[str, BoneRest] = {}
    order: list[str] = []
    for row in target_rig["restPose"]["bones"]:
        name = str(row["name"])
        parent = str(row["parent"]) if row.get("parent") is not None else None
        if parent and parent not in rests:
            raise ValueError(f"target rig restPose is not parent-before-child at {name!r}")
        head = row["head"]
        tail = row["tail"]
        matrix = rest_matrix(head, tail, 0.0)
        rests[name] = BoneRest(name, parent, matrix, distance(tuple(head), tuple(tail)))
        order.append(name)
    return rests, order


def _source_rest(source_rig: dict) -> tuple[dict[str, BoneRest], list[str]]:
    rows = {str(row["name"]): row for row in source_rig["bones"]}
    rests: dict[str, BoneRest] = {}
    visiting: set[str] = set()

    def build(name: str) -> BoneRest:
        if name in rests:
            return rests[name]
        if name in visiting:
            raise ValueError(f"source rig hierarchy cycle at {name!r}")
        try:
            row = rows[name]
        except KeyError as exc:
            raise ValueError(f"source rig references unknown bone {name!r}") from exc
        visiting.add(name)
        parent = str(row["parent"]) if row.get("parent") is not None else None
        if parent:
            build(parent)
        geometry = row["editGeometry"]
        matrix = rest_matrix(geometry["head"], geometry["tail"], float(geometry["roll"]))
        rest = BoneRest(name, parent, matrix, float(row["length"]))
        rests[name] = rest
        visiting.remove(name)
        return rest

    for name in rows:
        build(name)
    order: list[str] = []
    pending = set(rows)
    while pending:
        advanced = False
        for name in rows:
            if name not in pending:
                continue
            parent = rests[name].parent
            if parent is None or parent in order:
                order.append(name)
                pending.remove(name)
                advanced = True
        if not advanced:
            raise ValueError("unable to topologically order source rig")
    return rests, order


def _pose_matrices(frame: dict, rests: dict[str, BoneRest], order: list[str], armature_transform: Mat4) -> dict[str, Mat4]:
    result: dict[str, Mat4] = {}
    for name in order:
        rest = rests[name]
        basis = from_trs(
            frame["bones"][name]["translation"],
            frame["bones"][name]["rotationQuaternion"],
            frame["bones"][name]["scale"],
        )
        if rest.parent is None:
            local_pose = mul4(rest.matrix, basis)
        else:
            parent_rest = rests[rest.parent].matrix
            local_rest = mul4(inverse_affine(parent_rest), rest.matrix)
            local_pose = mul4(result[rest.parent], mul4(local_rest, basis))
        result[name] = local_pose
    return {name: mul4(armature_transform, matrix) for name, matrix in result.items()}


def _rest_world(rests: dict[str, BoneRest], armature_transform: Mat4) -> dict[str, Mat4]:
    return {name: mul4(armature_transform, rest.matrix) for name, rest in rests.items()}


def _mapped_source(mapping: dict, target_name: str) -> str:
    try:
        return str(mapping["targetToSource"][target_name])
    except KeyError as exc:
        raise ValueError(f"required target bone has no explicit source mapping: {target_name}") from exc


def _source_tail_world(matrix: Mat4, bone_length: float) -> Vec3:
    # Contract B editGeometry length is armature-local. Transform the actual tail
    # through the full armature/object matrix so source object scale is respected.
    return point(matrix, (0.0, bone_length, 0.0))


def _source_stature(source_rests: dict[str, BoneRest], source_rest_world: dict[str, Mat4], target_rests: dict[str, BoneRest], mapping: dict) -> tuple[float, float]:
    def head(name: str) -> Vec3:
        return translation4(source_rest_world[_mapped_source(mapping, name)])

    def tail(name: str) -> Vec3:
        src = _mapped_source(mapping, name)
        return _source_tail_world(source_rest_world[src], source_rests[src].length)

    source_torso = distance(head("Pelvis"), tail("Head"))
    source_leg = 0.5 * (
        distance(head("LeftThigh"), tail("LeftShin"))
        + distance(head("RightThigh"), tail("RightShin"))
    )
    source_size = source_torso + source_leg

    def target_head(name: str) -> Vec3:
        return translation4(target_rests[name].matrix)

    def target_tail(name: str) -> Vec3:
        m = target_rests[name].matrix
        r = rotation4(m)
        return add(translation4(m), mul((r[0][1], r[1][1], r[2][1]), target_rests[name].length))

    target_torso = distance(target_head("Pelvis"), target_tail("Head"))
    target_leg = 0.5 * (
        distance(target_head("LeftThigh"), target_tail("LeftShin"))
        + distance(target_head("RightThigh"), target_tail("RightShin"))
    )
    target_size = target_torso + target_leg
    if source_size <= 1e-8 or target_size <= 1e-8:
        raise ValueError(f"invalid retarget stature source={source_size} target={target_size}")
    return source_size, target_size


def _transfer_rotation(
    *,
    source_pose_rotation: Mat3,
    source_rest_rotation: Mat3,
    target_rest_rotation: Mat3,
    source_reference_axis: str,
    target_reference_axis: str,
    source_to_target_axes: Mat3,
    label: str,
) -> Mat3:
    """Transfer a pose through explicit source-rest/target-rest anatomical bases.

    The source world basis is first expressed in the target coordinate system.
    We then remove source EditBone roll by building an anatomical rest frame from
    bone +Y plus the mapping's explicit secondary reference axis. The source pose
    delta is measured in that anatomical frame and applied to the independently
    built target anatomical rest frame. Finally we convert back to the target
    rig's raw rest basis. This is deliberately not a world-space delta replay.
    """
    source_rest_target = mul3(source_to_target_axes, source_rest_rotation)
    source_pose_target = mul3(source_to_target_axes, source_pose_rotation)
    source_reference_target = mul3v(source_to_target_axes, axis_vector(source_reference_axis))
    target_reference = axis_vector(target_reference_axis)

    source_anatomical_rest = anatomical_frame(source_rest_target, source_reference_target, f"{label} source rest")
    target_anatomical_rest = anatomical_frame(target_rest_rotation, target_reference, f"{label} target rest")

    source_raw_to_anatomical = mul3(transpose3(source_rest_target), source_anatomical_rest)
    target_raw_to_anatomical = mul3(transpose3(target_rest_rotation), target_anatomical_rest)
    source_pose_anatomical = mul3(source_pose_target, source_raw_to_anatomical)
    anatomical_delta = mul3(transpose3(source_anatomical_rest), source_pose_anatomical)
    target_pose_anatomical = mul3(target_anatomical_rest, anatomical_delta)
    return mul3(target_pose_anatomical, transpose3(target_raw_to_anatomical))


def _target_pose(source_pose_world: dict[str, Mat4], source_rest_world: dict[str, Mat4], target_rests: dict[str, BoneRest], target_order: list[str], mapping: dict) -> dict[str, Mat4]:
    axes: Mat3 = mapping["sourceToTargetAxes"]
    result: dict[str, Mat4] = {}
    for name in target_order:
        rest = target_rests[name]
        if rest.parent is None:
            base = rest.matrix
        else:
            local_rest = mul4(inverse_affine(target_rests[rest.parent].matrix), rest.matrix)
            base = mul4(result[rest.parent], local_rest)
        source_name = mapping["targetToSource"].get(name)
        if source_name is None:
            result[name] = base
            continue
        desired_rotation = _transfer_rotation(
            source_pose_rotation=rotation4(source_pose_world[source_name]),
            source_rest_rotation=rotation4(source_rest_world[source_name]),
            target_rest_rotation=rotation4(rest.matrix),
            source_reference_axis=mapping["targetToSourceReferenceAxis"][name],
            target_reference_axis=mapping["targetToTargetReferenceAxis"][name],
            source_to_target_axes=axes,
            label=f"{source_name} -> {name}",
        )
        result[name] = with_rotation(base, desired_rotation)
    return result


def _endpoint(matrix: Mat4, bone_length: float, *, tail: bool) -> Vec3:
    head = translation4(matrix)
    if not tail:
        return head
    r = rotation4(matrix)
    return add(head, mul((r[0][1], r[1][1], r[2][1]), bone_length))


def semantic_points(pose: dict[str, Mat4], rests: dict[str, BoneRest], root_translation: Vec3) -> dict[str, Vec3]:
    def p(name: str, tail: bool = False) -> Vec3:
        return add(_endpoint(pose[name], rests[name].length, tail=tail), root_translation)

    return {
        "root": root_translation,
        "pelvis": p("Pelvis"),
        "head": p("Head", True),
        "leftShoulder": p("LeftUpperArm"),
        "leftElbow": p("LeftUpperArm", True),
        "leftWrist": p("LeftForeArm", True),
        "rightShoulder": p("RightUpperArm"),
        "rightElbow": p("RightUpperArm", True),
        "rightWrist": p("RightForeArm", True),
        "leftHip": p("LeftThigh"),
        "leftKnee": p("LeftThigh", True),
        "leftAnkle": p("LeftShin", True),
        "rightHip": p("RightThigh"),
        "rightKnee": p("RightThigh", True),
        "rightAnkle": p("RightShin", True),
    }


def source_semantic_points(source_pose: dict[str, Mat4], source_rests: dict[str, BoneRest], mapping: dict) -> dict[str, Vec3]:
    axes: Mat3 = mapping["sourceToTargetAxes"]

    def p(target_name: str, tail: bool = False) -> Vec3:
        source_name = _mapped_source(mapping, target_name)
        matrix = source_pose[source_name]
        value = _source_tail_world(matrix, source_rests[source_name].length) if tail else translation4(matrix)
        return mul3v(axes, value)

    return {
        "pelvis": p("Pelvis"),
        "head": p("Head", True),
        "leftShoulder": p("LeftUpperArm"),
        "leftElbow": p("LeftUpperArm", True),
        "leftWrist": p("LeftForeArm", True),
        "rightShoulder": p("RightUpperArm"),
        "rightElbow": p("RightUpperArm", True),
        "rightWrist": p("RightForeArm", True),
        "leftHip": p("LeftThigh"),
        "leftKnee": p("LeftThigh", True),
        "leftAnkle": p("LeftShin", True),
        "rightHip": p("RightThigh"),
        "rightKnee": p("RightThigh", True),
        "rightAnkle": p("RightShin", True),
    }


def source_direction_descriptor(source_pose: dict[str, Mat4], source_rest_world: dict[str, Mat4], mapping: dict, target_name: str) -> Vec3:
    source_name = _mapped_source(mapping, target_name)
    axes: Mat3 = mapping["sourceToTargetAxes"]
    rest_rotation = mul3(axes, rotation4(source_rest_world[source_name]))
    pose_rotation = mul3(axes, rotation4(source_pose[source_name]))
    reference = mul3v(axes, axis_vector(mapping["targetToSourceReferenceAxis"][target_name]))
    frame = anatomical_frame(rest_rotation, reference, f"{source_name} source descriptor")
    pose_y = (pose_rotation[0][1], pose_rotation[1][1], pose_rotation[2][1])
    return mul3v(transpose3(frame), pose_y)


def target_direction_descriptor(target_pose: dict[str, Mat4], target_rests: dict[str, BoneRest], mapping: dict, target_name: str) -> Vec3:
    rest_rotation = rotation4(target_rests[target_name].matrix)
    pose_rotation = rotation4(target_pose[target_name])
    reference = axis_vector(mapping["targetToTargetReferenceAxis"][target_name])
    frame = anatomical_frame(rest_rotation, reference, f"{target_name} target descriptor")
    pose_y = (pose_rotation[0][1], pose_rotation[1][1], pose_rotation[2][1])
    return mul3v(transpose3(frame), pose_y)


def retarget_animation(source_rig: dict, source_animation: dict, target_rig: dict, mapping: dict) -> dict:
    source_rests, source_order = _source_rest(source_rig)
    target_rests, target_order = _target_rest(target_rig)
    source_names = set(source_rests)
    missing_sources = {source for source in mapping["targetToSource"].values() if source not in source_names}
    if missing_sources:
        raise ValueError(f"explicit source mappings missing from Contract B rig: {sorted(missing_sources)}")
    root_source = str(mapping["rootSourceBone"])
    if root_source not in source_names:
        raise ValueError(f"rootSourceBone {root_source!r} is absent from Contract B rig")

    armature = source_rig["armatureObject"]["transform"]
    armature_transform = from_trs(armature["translation"], armature["rotationQuaternion"], armature["scale"])
    source_rest_world = _rest_world(source_rests, armature_transform)
    source_size, target_size = _source_stature(source_rests, source_rest_world, target_rests, mapping)
    scale = target_size / source_size
    axes: Mat3 = mapping["sourceToTargetAxes"]
    root_rest_head = translation4(source_rest_world[root_source])
    frames = []
    for source_frame in source_animation["frames"]:
        source_pose = _pose_matrices(source_frame, source_rests, source_order, armature_transform)
        root_pose_head = translation4(source_pose[root_source])
        source_root_delta = mul3v(axes, sub(root_pose_head, root_rest_head))
        root_translation = mul(source_root_delta, scale)
        target_pose = _target_pose(source_pose, source_rest_world, target_rests, target_order, mapping)
        frames.append({
            "sourceFrame": int(source_frame["frame"]),
            "sourceRootDelta": source_root_delta,
            "rootTranslation": root_translation,
            "sourcePose": source_pose,
            "sourceSemantics": source_semantic_points(source_pose, source_rests, mapping),
            "pose": target_pose,
            "semantics": semantic_points(target_pose, target_rests, root_translation),
        })
    return {
        "frames": frames,
        "sourceStature": source_size,
        "targetStature": target_size,
        "rootMotionScale": scale,
        "sourceRests": source_rests,
        "sourceRestWorld": source_rest_world,
        "targetRests": target_rests,
        "targetOrder": target_order,
    }
