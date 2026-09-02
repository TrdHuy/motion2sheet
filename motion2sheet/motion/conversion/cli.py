from __future__ import annotations

from pathlib import Path

from .converter import convert_animation_profile


def convert_command(args) -> int:
    report = convert_animation_profile(
        source_rig_path=Path(args.source_rig),
        source_animation_path=Path(args.source_animation),
        target_rig_path=Path(args.target_rig),
        mapping_path=Path(args.mapping),
        character_profile_path=Path(args.character_profile),
        output=Path(args.output),
    )
    fidelity = report["fidelity"]
    print(
        "motion2sheet: convert-animation-profile OK -> "
        f"{Path(args.output)}; frames={report['source']['frameCount']} fps={report['source']['fps']} "
        f"maxPoseError={fidelity['maxErrorMeters']}m"
    )
    return 0


def add_conversion_subcommands(sub) -> None:
    parser = sub.add_parser(
        "convert-animation-profile",
        help="Convert Contract B source-authority JSON into Anim2Sheet Profile Contract v2",
    )
    parser.add_argument("--source-rig", required=True)
    parser.add_argument("--source-animation", required=True)
    parser.add_argument("--target-rig", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--character-profile", required=True)
    parser.add_argument("--output", required=True)
    parser.set_defaults(func=convert_command)
