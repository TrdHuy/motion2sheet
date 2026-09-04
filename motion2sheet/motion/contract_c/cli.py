from __future__ import annotations

import argparse
from pathlib import Path

from .runner import export_contract_c_animation, render_contract_c_animation, verify_contract_c_fidelity


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
    report = export_contract_c_animation(
        source_rig_path=Path(args.source_rig),
        source_animation_path=Path(args.source_animation),
        mapping_path=Path(args.mapping),
        animation_id=args.id,
        loop=args.loop,
        output=Path(args.output),
        blender=args.blender,
    )
    print(
        "motion2sheet: Contract C export PASS; "
        f"id={report['animationId']} frames={report['frameCount']} sha256={report['animationSha256']}"
    )
    return 0


def _render(args) -> int:
    report = render_contract_c_animation(
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
        render_samples=args.render_samples,
        blender=args.blender,
    )
    print(
        "motion2sheet: Contract C render PASS; "
        f"character={report['characterId']} animation={report['animationId']} frames={len(report['renderedSamples'])}"
    )
    return 0


def _verify_fidelity(args) -> int:
    report = verify_contract_c_fidelity(
        source_rig_path=Path(args.source_rig),
        source_animation_path=Path(args.source_animation),
        mapping_path=Path(args.source_mapping),
        animation_path=Path(args.animation),
        output=Path(args.output),
    )
    errors = report["maxErrors"]
    print(
        "motion2sheet: Source -> Contract C fidelity PASS; "
        f"rotationDeg={errors['semanticRotationDegrees']:.12g} "
        f"hips={errors['hipsTranslationMeanLegLength']:.12g}"
    )
    return 0


def add_contract_c_subcommands(subparsers) -> None:
    export = subparsers.add_parser(
        "export-contract-c-animation",
        help="Convert Contract B rest+motion authorities into reusable semantic humanoid Contract C",
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
        "verify-contract-c-fidelity",
        help="Independently compare Contract B source semantics with a Contract C authority",
    )
    fidelity.add_argument("--source-rig", required=True)
    fidelity.add_argument("--source-animation", required=True)
    fidelity.add_argument("--source-mapping", required=True)
    fidelity.add_argument("--animation", required=True)
    fidelity.add_argument("--output", required=True)
    fidelity.set_defaults(func=_verify_fidelity)

    render = subparsers.add_parser(
        "render-contract-c-animation",
        help="Retarget one immutable Contract C animation to a mapped real skinned humanoid",
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
    render.add_argument("--frames", default="all")
    render.add_argument("--gif", action="store_true")
    render.add_argument("--render-samples", type=int, default=16)
    render.add_argument("--output", required=True)
    render.add_argument("--blender", default="blender")
    render.set_defaults(func=_render)
