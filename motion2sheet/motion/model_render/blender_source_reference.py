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
    request["rootBone"] = roots[0]
    start, end = integer_action_range(action)
    available = set(range(start, end + 1))
    selected = [int(frame) for frame in request["selectedFrames"]]
    missing = [frame for frame in selected if frame not in available]
    if missing:
        raise RuntimeError(f"source reference requested frames outside source action: {missing}")
    fps, fps_int, fps_base = scene_fps(bpy.context.scene)
    bpy.context.scene.render.fps = fps_int
    bpy.context.scene.render.fps_base = fps_base
    setup_camera_and_render(request, armature)
    report = {
        "schema": "motion2sheet.diagnostics.source-skinned-render",
        "version": 1,
        "source": str(source),
        "meshCount": len(skinned),
        "vertexCount": sum(len(obj.data.vertices) for obj in skinned),
        "boneCount": len(armature.data.bones),
        "rootBone": roots[0],
        "frameRange": [start, end],
        "frameCount": len(selected),
        "fps": fps,
        "actualSkinnedMesh": True,
    }
    output = Path(request["output"])
    output.mkdir(parents=True, exist_ok=True)
    (output / "source_reference.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "source_reference.blend"))
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
