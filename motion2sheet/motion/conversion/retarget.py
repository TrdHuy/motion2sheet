from __future__ import annotations

from dataclasses import dataclass

from .math3d import (
    Mat3,
    Mat4,
    Vec3,
    add,
    distance,
    from_trs,
    inverse_affine,
    mul,
    mul3,
    mul3v,
    mul4,
    rest_matrix,
    rotation4,
    sub,
    transpose3,
    translation4,
    with_rotation,
)


@dataclass(frozen=True)
class BoneRest:
    name: str
    parent: str | None
    matrix: Mat4
    length: float


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


def _source_stature(source_rests: dict[str, BoneRest], source_rest_world: dict[str, Mat4], target_rests: dict[str, BoneRest], mapping: dict) -> tuple[float, float]:
    def head(name: str) -> Vec3:
        return translation4(source_rest_world[_mapped_source(mapping, name)])

    def tail(name: str) -> Vec3:
        src = _mapped_source(mapping, name)
        m = source_rest_world[src]
        r = rotation4(m)
        return add(translation4(m), mul((r[0][1], r[1][1], r[2][1]), source_rests[src].length))

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


def _target_pose(source_pose_world: dict[str, Mat4], source_rest_world: dict[str, Mat4], target_rests: dict[str, BoneRest], target_order: list[str], mapping: dict) -> dict[str, Mat4]:
    axes: Mat3 = mapping["sourceToTargetAxes"]
    axes_inv = transpose3(axes)
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
        source_pose_rotation = rotation4(source_pose_world[source_name])
        source_rest_rotation = rotation4(source_rest_world[source_name])
        delta_source = mul3(source_pose_rotation, transpose3(source_rest_rotation))
        delta_target = mul3(axes, mul3(delta_source, axes_inv))
        desired_rotation = mul3(delta_target, rotation4(rest.matrix))
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
        root_delta = mul3v(axes, sub(root_pose_head, root_rest_head))
        root_translation = mul(root_delta, scale)
        target_pose = _target_pose(source_pose, source_rest_world, target_rests, target_order, mapping)
        frames.append({
            "sourceFrame": int(source_frame["frame"]),
            "rootTranslation": root_translation,
            "pose": target_pose,
            "semantics": semantic_points(target_pose, target_rests, root_translation),
        })
    return {
        "frames": frames,
        "sourceStature": source_size,
        "targetStature": target_size,
        "rootMotionScale": scale,
        "targetRests": target_rests,
        "targetOrder": target_order,
    }
