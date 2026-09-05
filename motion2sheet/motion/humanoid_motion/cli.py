from __future__ import annotations

import argparse
from pathlib import Path

from .runner import export_humanoid_animation, render_humanoid_animation, verify_humanoid_animation_fidelity


def _canvas(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        result = int(width), int(height)
    except (AttributeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("canvas must look like 320x320") from exc
    if min(result) <= 0:
        raise argparse.ArgumentTypeError("canvas dimensions must be positive")
    return result


def _export(args) -> int:
    report = export_humanoid_animation(
        source_rig_path=Path(args.source_rig),
        source_animation_path=Path(args.source_animation),
        mapping_path=Path(args.mapping),
        animation_id=args.id,
        loop=args.loop,
        output=Path(args.output),
        blender=args.blender,
    )
    print(
        "motion2sheet: Humanoid Motion export PASS; "
        f"id={report['animationId']} durationSeconds={report['durationSeconds']} "
        f"frames={report['frameCount']} sha256={report['animationSha256']}"
    )
    return 0


def _render(args) -> int:
    report = render_humanoid_animation(
        model_path=Path(args.model),
        character_rig_path=Path(args.character_rig),
        skin_path=Path(args.skin),
        mapping_path=Path(args.character_mapping),
        animation_path=Path(args.animation),
        camera_profile_path=Path(args.camera_profile),
        output=Path(args.output),
        sheet_columns=args.sheet_columns,
        canvas=args.canvas,
        background=args.background,
        gif=args.gif,
        frames=args.frames,
        sample_count=args.sample_count,
        output_fps=args.output_fps,
        render_samples=args.render_samples,
        blender=args.blender,
    )
    print(
        "motion2sheet: Humanoid Motion render PASS; "
        f"character={report['characterId']} animation={report['animationId']} "
        f"durationSeconds={report['durationSeconds']} frames={len(report['renderedSamples'])}"
    )
    return 0


def _verify_fidelity(args) -> int:
    report = verify_humanoid_animation_fidelity(
        source_rig_path=Path(args.source_rig),
        source_animation_path=Path(args.source_animation),
        mapping_path=Path(args.source_mapping),
        animation_path=Path(args.animation),
        output=Path(args.output),
    )
    errors = report["maxErrors"]
    print(
        "motion2sheet: Source -> Humanoid Motion fidelity PASS; "
        f"durationErrorSeconds={report['timing']['durationErrorSeconds']:.12g} "
        f"rotationDeg={errors['semanticRotationDegrees']:.12g} "
        f"hips={errors['hipsTranslationMeanLegLength']:.12g}"
    )
    return 0


def add_humanoid_motion_subcommands(subparsers) -> None:
    export = subparsers.add_parser(
        "export-humanoid-animation",
        help="Convert Motion JSON Source Rig + Source Animation authorities into reusable semantic Humanoid Motion",
    )
    export.add_argument("--source-rig", required=True)
    export.add_argument("--source-animation", required=True)
    export.add_argument("--mapping", required=True)
    export.add_argument("--id", required=True)
    export.add_argument("--loop", action="store_true")
    export.add_argument("--output", required=True)
    export.add_argument("--blender", default="blender")
    export.set_defaults(func=_export)

    fidelity = subparsers.add_parser(
        "verify-humanoid-animation-fidelity",
        help="Independently compare Motion JSON source semantics with a Humanoid Motion authority",
    )
    fidelity.add_argument("--source-rig", required=True)
    fidelity.add_argument("--source-animation", required=True)
    fidelity.add_argument("--source-mapping", required=True)
    fidelity.add_argument("--animation", required=True)
    fidelity.add_argument("--output", required=True)
    fidelity.set_defaults(func=_verify_fidelity)

    render = subparsers.add_parser(
        "render-humanoid-animation",
        help="Retarget one immutable Humanoid Motion animation to a mapped real skinned humanoid",
    )
    render.add_argument("--model", required=True)
    render.add_argument("--character-rig", required=True)
    render.add_argument("--skin", required=True)
    render.add_argument("--character-mapping", required=True)
    render.add_argument("--animation", required=True)
    render.add_argument("--camera-profile", required=True)
    render.add_argument("--sheet-columns", type=int, default=8)
    render.add_argument("--canvas", type=_canvas, default=(320, 320))
    render.add_argument("--background", default="transparent")
    selection = render.add_mutually_exclusive_group()
    selection.add_argument("--frames", default=None)
    selection.add_argument("--sample-count", type=int, default=None)
    render.add_argument("--output-fps", type=float, default=None)
    render.add_argument("--gif", action="store_true")
    render.add_argument("--render-samples", type=int, default=16)
    render.add_argument("--output", required=True)
    render.add_argument("--blender", default="blender")
    render.set_defaults(func=_render)
