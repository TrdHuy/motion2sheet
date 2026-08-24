"""CI helper executed by Blender after opening generated source.blend."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def argv():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv())

    scene = bpy.context.scene
    renderer = str(scene.get("vfx_renderer", ""))
    if not renderer.startswith("blender-native"):
        raise RuntimeError("source.blend does not identify itself as blender-native")
    required = {
        "VFX_ROOT", "VFX_BODY", "VFX_CORE", "VFX_LIGHTNING", "VFX_WISPS",
        "VFX_PLUMES", "VFX_PLASMA", "VFX_FRAGMENTS", "VFX_DISSOLVE",
    }
    missing = sorted(required - set(bpy.data.collections.keys()))
    if missing:
        raise RuntimeError(f"source.blend missing editable VFX collections: {missing}")
    for text_name in ("VFX_PROFILE_RESOLVED.json", "VFX_README.txt", "SOURCE_native_generate_vfx.py"):
        if text_name not in bpy.data.texts:
            raise RuntimeError(f"source.blend missing embedded text: {text_name}")

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for frame in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(frame)
        scene.render.filepath = str(output / f"{frame:02d}.png")
        bpy.ops.render.render(write_still=True)
    print(f"re-rendered saved Blender source -> {output}")


if __name__ == "__main__":
    main()
