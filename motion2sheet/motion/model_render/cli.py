from __future__ import annotations

from pathlib import Path

from .runner import export_character


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


def add_model_render_subcommands(subparsers) -> None:
    export_parser = subparsers.add_parser(
        "export-character",
        help="Extract geometry/material model, character rest rig and Skin Contract v1 from a real skinned FBX",
    )
    export_parser.add_argument("input")
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--blender", default="blender")
    export_parser.set_defaults(func=_export_character)
