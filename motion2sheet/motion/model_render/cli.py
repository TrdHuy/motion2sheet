from __future__ import annotations

import argparse
from pathlib import Path

from .runner import export_character, render_model_animation


def _canvas(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        parsed = (int(width), int(height))
    except (AttributeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("canvas must look like 320x320") from exc
    if parsed[0] <= 0 or parsed[1] <= 0:
        raise argparse.ArgumentTypeError("canvas dimensions must be positive")
    return parsed


def _export_character(args) -> int:
    report = export_character(input_path=Path(args.input), output=Path(args.output), blender=args.blender)
    stats = report["skinStatistics"]
    print(
        "motion2sheet: export-character PASS; "
        f"meshes={stats['meshCount']} vertices={stats['vertexCount']} "
        f"weighted={stats['weightedVertexCount']} influences={stats['influenceCount']} bones={stats['boneCount']} "
        f"modelBytes={report['outputs']['modelGlbBytes']} skinBytes={report['outputs']['skinJsonBytes']}"
    )
    return 0


def _render_model_animation(args) -> int:
    report = render_model_animation(
        model_path=Path(args.model),
        character_rig_path=Path(args.character_rig),
        skin_path=Path(args.skin),
        animation_rig_path=Path(args.animation_rig),
        animation_path=Path(args.animation),
        camera_profile_path=Path(args.camera_profile),
        output=Path(args.output),
        sheet_columns=args.sheet_columns,
        canvas=args.canvas,
        background=args.background,
        gif=args.gif,
        frames=args.frames,
        blender=args.blender,
    )
    skin = report["skinReconstruction"]
    playback = report["animationFidelity"]
    print(
        "motion2sheet: render-model-animation PASS; "
        f"frames={report['frameCount']} maxWeightDelta={skin['maxWeightDelta']:.12g} "
        f"maxSemanticDirectionDeg={playback['maxSemanticDirectionErrorDegrees']:.12g}"
    )
    return 0


def add_model_render_subcommands(subparsers) -> None:
    export_parser = subparsers.add_parser(
        "export-character",
        help="Extract geometry/material model, character rest rig and Skin Contract v1 from a real skinned FBX",
    )
    export_parser.add_argument("input")
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--blender", default="blender")
    export_parser.set_defaults(func=_export_character)

    render_parser = subparsers.add_parser(
        "render-model-animation",
        help="Render an actual skinned model from model.glb + character rig + skin.json + Contract B animation",
    )
    render_parser.add_argument("--model", required=True)
    render_parser.add_argument("--character-rig", required=True)
    render_parser.add_argument("--skin", required=True)
    render_parser.add_argument("--animation-rig", required=True)
    render_parser.add_argument("--animation", required=True)
    render_parser.add_argument("--camera-profile", required=True)
    render_parser.add_argument("--sheet-columns", type=int, default=8)
    render_parser.add_argument("--canvas", type=_canvas, default=(320, 320))
    render_parser.add_argument("--background", default="transparent")
    render_parser.add_argument("--frames", default="all")
    render_parser.add_argument("--gif", action="store_true")
    render_parser.add_argument("--output", required=True)
    render_parser.add_argument("--blender", default="blender")
    render_parser.set_defaults(func=_render_model_animation)
