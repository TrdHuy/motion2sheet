from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from .schema import read_json, validate_animation_document, validate_rig_document
from .visual import compare_blender_rendered_visuals, render_visuals


def package_root() -> Path:
    return Path(__file__).resolve().parent


def blender_executable(value: str) -> str:
    resolved = shutil.which(value) if Path(value).name == value else value
    if not resolved:
        raise RuntimeError(f"Blender executable not found: {value}")
    return str(resolved)


def run_blender(script: str, blender: str, arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    command = [
        blender_executable(blender),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(package_root() / script),
        "--",
        *arguments,
    ]
    return subprocess.run(command, check=check)


def export_animation_json(args) -> int:
    source = Path(args.input)
    if not source.exists():
        raise RuntimeError(f"Input motion file does not exist: {source}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    run_blender("blender_export.py", args.blender, ["--input", str(source.resolve()), "--output", str(output.resolve())])
    rig = validate_rig_document(read_json(output / "rig.json"))
    validate_animation_document(read_json(output / "animation.json"), rig)
    return 0


def reconstruct_animation(args) -> int:
    rig_path = Path(args.rig)
    animation_path = Path(args.animation)
    rig = validate_rig_document(read_json(rig_path))
    validate_animation_document(read_json(animation_path), rig)
    blend_output = Path(args.output)
    fbx_output = Path(args.fbx_output) if args.fbx_output else blend_output.with_suffix(".fbx")
    run_blender(
        "blender_reconstruct.py",
        args.blender,
        [
            "--rig", str(rig_path.resolve()),
            "--animation", str(animation_path.resolve()),
            "--blend-output", str(blend_output.resolve()),
            "--fbx-output", str(fbx_output.resolve()),
        ],
    )
    return 0


def _render_verification_visuals(args, visual_pose: Path, visual_dir: Path) -> dict:
    if args.visual_renderer == "pillow":
        return render_visuals(visual_pose, visual_dir)
    run_blender(
        "blender_visual.py",
        args.blender,
        ["--input", str(visual_pose.resolve()), "--output", str(visual_dir.resolve())],
    )
    return compare_blender_rendered_visuals(visual_pose, visual_dir)


def verify_animation_roundtrip(args) -> int:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    numeric_path = output / "verification.numeric.json"
    visual_dir = output / "visual"
    visual_pose = visual_dir / "pose_data.json"
    completed = run_blender(
        "blender_verify.py",
        args.blender,
        [
            "--source", str(Path(args.source).resolve()),
            "--rig", str(Path(args.rig).resolve()),
            "--animation", str(Path(args.animation).resolve()),
            "--blend", str(Path(args.blend).resolve()),
            "--fbx", str(Path(args.fbx).resolve()),
            "--output", str(output.resolve()),
        ],
        check=False,
    )
    if not numeric_path.exists() or not visual_pose.exists():
        raise RuntimeError(f"Blender verifier did not produce expected outputs (exit={completed.returncode})")
    verification = json.loads(numeric_path.read_text(encoding="utf-8"))
    visual = _render_verification_visuals(args, visual_pose, visual_dir)
    determinism = {"pass": True, "checked": False}
    if args.determinism_rig or args.determinism_animation:
        if not args.determinism_rig or not args.determinism_animation:
            raise RuntimeError("--determinism-rig and --determinism-animation must be provided together")
        rig_equal = Path(args.rig).read_bytes() == Path(args.determinism_rig).read_bytes()
        animation_equal = Path(args.animation).read_bytes() == Path(args.determinism_animation).read_bytes()
        determinism = {
            "pass": rig_equal and animation_equal,
            "checked": True,
            "rigByteIdentical": rig_equal,
            "animationByteIdentical": animation_equal,
        }
    verification["visual"] = visual
    verification["determinism"] = determinism
    verification["pass"] = bool(verification.get("pass")) and visual["pass"] and determinism["pass"]
    (output / "verification.json").write_text(
        json.dumps(verification, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    numeric_path.unlink(missing_ok=True)
    visual_pose.unlink(missing_ok=True)
    if completed.returncode != 0 or not verification["pass"]:
        raise RuntimeError("Round-trip verification failed; see verification.json")
    print(
        "motion2sheet: round-trip verification PASS; "
        f"renderer={verification['visual']['renderer']}, "
        f"maxTranslation={verification['localTransform']['maxTranslationError']:.9g}, "
        f"maxAngleDeg={verification['localTransform']['maxAngularErrorDeg']:.9g}, "
        f"maxScale={verification['localTransform']['maxScaleError']:.9g}, "
        f"maxWorld={verification['worldPose']['maxWorldError']:.9g}, "
        f"changedPixels={verification['visual']['changedPixels']}"
    )
    return 0


def add_roundtrip_subcommands(subparsers) -> None:
    export_parser = subparsers.add_parser(
        "export-animation-json",
        help="Extract source skeleton + every integer animation frame to lossless source-authority JSON",
    )
    export_parser.add_argument("input")
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--blender", default="blender")
    export_parser.set_defaults(func=export_animation_json)

    reconstruct_parser = subparsers.add_parser(
        "reconstruct-animation",
        help="Reconstruct a Blender armature/action using only rig.json + animation.json",
    )
    reconstruct_parser.add_argument("--rig", required=True)
    reconstruct_parser.add_argument("--animation", required=True)
    reconstruct_parser.add_argument("--output", required=True, help="Output reconstructed .blend path")
    reconstruct_parser.add_argument("--fbx-output", default=None, help="Optional reconstructed FBX path; defaults beside .blend")
    reconstruct_parser.add_argument("--blender", default="blender")
    reconstruct_parser.set_defaults(func=reconstruct_animation)

    verify_parser = subparsers.add_parser(
        "verify-animation-roundtrip",
        help="Compare source FBX, JSON-only Blender reconstruction and re-imported reconstructed FBX",
    )
    verify_parser.add_argument("--source", required=True)
    verify_parser.add_argument("--rig", required=True)
    verify_parser.add_argument("--animation", required=True)
    verify_parser.add_argument("--blend", required=True)
    verify_parser.add_argument("--fbx", required=True)
    verify_parser.add_argument("--output", required=True)
    verify_parser.add_argument("--determinism-rig", default=None)
    verify_parser.add_argument("--determinism-animation", default=None)
    verify_parser.add_argument(
        "--visual-renderer",
        choices=("pillow", "blender"),
        default="pillow",
        help="Visual proof renderer: pillow (default deterministic skeleton) or Blender-native Eevee sheet render",
    )
    verify_parser.add_argument("--blender", default="blender")
    verify_parser.set_defaults(func=verify_animation_roundtrip)
