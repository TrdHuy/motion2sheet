from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

import bpy

from motion2sheet.motion.model_render.blender_helpers import mesh_objects, setup_camera_and_render
from motion2sheet.motion.roundtrip.blender_common import import_source, integer_action_range, scene_fps


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _rename_frames_to_contract_ids(
    output: Path,
    source_frames: list[int],
    contract_frames: list[int],
) -> None:
    if len(source_frames) != len(contract_frames):
        raise RuntimeError("source/reference frame mapping length mismatch")
    frame_dir = output / ".frames"
    staged: list[tuple[Path, Path]] = []
    for index, (source_frame, contract_frame) in enumerate(zip(source_frames, contract_frames)):
        source_path = frame_dir / f"frame_{source_frame:04d}.png"
        if not source_path.is_file():
            raise RuntimeError(f"source reference renderer did not produce mapped frame: {source_path}")
        temporary = frame_dir / f".m2s_remap_{index:04d}.png"
        source_path.replace(temporary)
        staged.append((temporary, frame_dir / f"frame_{contract_frame:04d}.png"))
    for temporary, target in staged:
        if target.exists():
            raise RuntimeError(f"source reference frame remap would overwrite an existing output: {target}")
        temporary.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args(_argv())
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    source = Path(request["sourcePath"])
    if not source.is_file():
        raise RuntimeError(f"source reference FBX missing: {source}")
    armature, action = import_source(source)
    skinned = [
        obj for obj in mesh_objects()
        if any(modifier.type == "ARMATURE" and modifier.object == armature for modifier in obj.modifiers)
    ]
    if not skinned:
        raise RuntimeError("source reference does not contain a real skinned mesh")
    roots = [bone.name for bone in armature.data.bones if bone.parent is None]
    if len(roots) != 1:
        raise RuntimeError(f"source reference requires exactly one root bone; found {roots}")

    start, end = integer_action_range(action)
    available = set(range(start, end + 1))
    contract_frames = [int(frame) for frame in request["selectedFrames"]]
    if len(set(contract_frames)) != len(contract_frames):
        raise RuntimeError("source reference Contract B frame ids must be unique")
    frame_offset = int(request.get("frameOffset", 0))
    source_frames = [frame - frame_offset for frame in contract_frames]
    if len(set(source_frames)) != len(source_frames):
        raise RuntimeError("source reference mapped source frame ids must be unique")
    missing = [frame for frame in source_frames if frame not in available]
    if missing:
        raise RuntimeError(
            "source reference mapped frames fall outside original source action; "
            f"frameOffset={frame_offset} missing={missing} sourceRange={[start, end]}"
        )

    render_request = dict(request)
    render_request["rootBone"] = roots[0]
    render_request["selectedFrames"] = source_frames
    fps, fps_int, fps_base = scene_fps(bpy.context.scene)
    bpy.context.scene.render.fps = fps_int
    bpy.context.scene.render.fps_base = fps_base
    setup_camera_and_render(render_request, armature)

    output = Path(request["output"])
    _rename_frames_to_contract_ids(output, source_frames, contract_frames)
    report = {
        "schema": "motion2sheet.diagnostics.source-skinned-render",
        "version": 1,
        "source": str(source),
        "meshCount": len(skinned),
        "vertexCount": sum(len(obj.data.vertices) for obj in skinned),
        "boneCount": len(armature.data.bones),
        "rootBone": roots[0],
        "sourceFrameRange": [start, end],
        "sourceFrames": source_frames,
        "contractFrames": contract_frames,
        "frameOffset": frame_offset,
        "frameMapping": "sourceFrame = contractFrame - frameOffset",
        "frameCount": len(contract_frames),
        "fps": fps,
        "actualSkinnedMesh": True,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "source_reference.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source_reference.blend"))
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
