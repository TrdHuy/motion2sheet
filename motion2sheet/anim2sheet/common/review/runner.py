from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from motion2sheet.anim2sheet.common.camera.config import final_camera_name
from motion2sheet.anim2sheet.common.output.packer import compose_sheet, write_camera_previews
from motion2sheet.anim2sheet.common.profile import resolve_review_request
from .overlay import write_camera_overlays, copy_camera_aliases


def blender_executable(name: str) -> str:
    value = shutil.which(name) if Path(name).name == name else name
    if not value:
        raise RuntimeError(f"Blender executable not found: {name}")
    return str(value)


def _optional_path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _visible_mesh_args(resolved: dict) -> list[str]:
    names = list(resolved.get("visibleReviewMeshes", []))
    return ["--visible-meshes", ",".join(names)] if names else []


def run_review(args, *, command: str = "review") -> int:
    if command not in {"build", "review"}:
        raise ValueError(f"unsupported anim2sheet command: {command}")
    resolved = resolve_review_request(
        profile_path=Path(args.profile),
        joint_contract_path=_optional_path(getattr(args, "joint_contract", None)),
        rig_profile_path=_optional_path(getattr(args, "rig_profile", None)),
        character_profile_path=_optional_path(getattr(args, "character_profile", None)),
        camera_profile_path=Path(args.camera_profile),
        frames=args.frames,
        cameras=args.cameras,
        animation=getattr(args, "animation", None),
    )
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    frames = list(resolved["executionFrames"])
    camera_names = list(resolved["cameraNames"])
    camera_profile = resolved["cameraProfile"]
    final_name = final_camera_name(camera_profile, camera_names)
    alias_name = final_name or camera_names[0]
    gif_enabled = bool(getattr(args, "gif", False))
    gif_fps = int(resolved["profile"]["fps"])
    camera_config = {
        "version": camera_profile["version"],
        "source": camera_profile["source"],
        "selectedCameras": camera_names,
        "finalCamera": final_name,
        "reviewFrames": frames,
        "cameras": {name: camera_profile["cameras"][name] for name in camera_names},
    }
    source = dict(resolved["source"])
    source_path = output / "source.json"
    camera_config_path = output / "camera_config.json"
    _write_json(source_path, source)
    _write_json(camera_config_path, camera_config)
    invocation = {
        "tool": "anim2sheet",
        "command": command,
        "animation": resolved["animation"],
        "authoringCapability": resolved["authoringCapability"],
        "profile": str(resolved["profilePath"]),
        "rigProfile": str(resolved["rigProfilePath"]),
        "characterProfile": str(resolved["characterProfilePath"]),
        "jointContract": str(resolved["jointContractPath"]),
        "cameraProfile": str(resolved["cameraProfilePath"]),
        "contractFrames": resolved["contractFrames"],
        "executionFrames": frames,
        "cameras": camera_names,
        "gif": gif_enabled,
        "blender": args.blender,
        "output": str(output),
    }
    _write_json(output / "invocation.json", invocation)
    _write_json(output / "resolved_config.json", {
        "animation": resolved["animation"],
        "authoringCapability": resolved["authoringCapability"],
        "profile": resolved["profile"],
        "rigProfile": resolved["rigProfile"],
        "characterProfile": resolved["characterProfile"],
        "jointContract": resolved["contract"],
        "cameraConfig": camera_config,
        "contractFrames": resolved["contractFrames"],
        "executionFrames": frames,
        "cameras": camera_names,
        "gif": gif_enabled,
    })
    blender = blender_executable(args.blender)
    root = Path(__file__).resolve().parents[2]
    subprocess.run([
        blender, "--background", "--factory-startup", "--python", str(root / "blender_entry.py"), "--",
        "--spec", str(source_path), "--output", str(output),
    ], check=True, timeout=300)
    blend_path = output / "source.blend"
    debug_path = output / "motion_debug.json"
    if not blend_path.is_file() or not debug_path.is_file():
        raise RuntimeError("authoring stage did not produce source.blend/motion_debug.json")
    subprocess.run([
        blender, "--background", str(blend_path), "--python", str(root / "common/rig/leg_ik.py"), "--",
        "--output", str(output), "--frames", ",".join(map(str, frames)),
    ], check=True, timeout=120)
    subprocess.run([
        blender, "--background", str(blend_path), "--python", str(root / "common/camera/render.py"), "--",
        "--camera-config", str(camera_config_path), "--output", str(output),
    ], check=True, timeout=300)
    camera_debug = json.loads((output / "camera_debug.json").read_text(encoding="utf-8"))
    subprocess.run([
        blender, "--background", str(blend_path), "--python", str(root / "common/authority/reopen.py"), "--",
        "--output", str(output), "--contract", str(resolved["jointContractPath"]),
        "--pre-debug", str(debug_path), "--frames", ",".join(map(str, frames)),
    ], check=True, timeout=120)
    skeleton_entry = root / "common/rig/skeleton_viewport.py"
    xvfb = shutil.which("xvfb-run")
    columns = int(resolved["profile"].get("sheetColumns", 4))
    for name in camera_names:
        camera_root = output / "cameras" / name
        object_frames = [camera_root / "frames" / f"{frame:02d}.png" for frame in frames]
        for path in object_frames:
            if not path.is_file():
                raise RuntimeError(f"camera object output missing: {path}")
        compose_sheet(object_frames, camera_root / "object_keyposes.png", columns=columns)
        command_args = [
            blender, str(blend_path), "--python", str(skeleton_entry), "--",
            "--output", str(camera_root / "skeleton_frames"), "--rig-output", str(output),
            "--frames", ",".join(map(str, frames)), "--skip-rig-docs",
            "--camera-config", str(camera_config_path), "--camera-name", name,
            *_visible_mesh_args(resolved),
        ]
        if xvfb:
            command_args = [xvfb, "-a", *command_args]
        subprocess.run(command_args, check=True, timeout=180)
        skeleton_frames = [camera_root / "skeleton_frames" / f"{frame:02d}.png" for frame in frames]
        for path in skeleton_frames:
            if not path.is_file():
                raise RuntimeError(f"camera skeleton output missing: {path}")
        compose_sheet(skeleton_frames, camera_root / "skeleton_keyposes.png", columns=columns)
    write_camera_overlays(output, camera_debug, camera_names, frames)
    copy_camera_aliases(output, alias_name)
    write_camera_previews(
        output,
        camera_names,
        frames,
        fps=gif_fps,
        alias_camera=alias_name,
        enabled=gif_enabled,
    )
    _write_json(output / "metadata.json", {
        "tool": "anim2sheet",
        "mode": command,
        "animation": resolved["animation"],
        "authoringCapability": resolved["authoringCapability"],
        "rigProfile": str(resolved["rigProfilePath"]),
        "characterProfile": str(resolved["characterProfilePath"]),
        "contractFrames": resolved["contractFrames"],
        "reviewFrames": frames,
        "armControl": resolved["rigProfile"]["solvers"]["arms"]["mode"],
        "legControl": resolved["rigProfile"]["solvers"]["legs"]["mode"],
        "cameraProfile": str(resolved["cameraProfilePath"]),
        "reviewCameras": camera_names,
        "finalCamera": final_name,
        "aliasCamera": alias_name,
        "gifEnabled": gif_enabled,
        "gifFps": gif_fps if gif_enabled else None,
        "previewGif": "preview.gif" if gif_enabled else None,
        "cameraDebug": "camera_debug.json",
        "legIkDebug": "leg_ik_debug.json",
        "debug": "motion_debug.json",
        "reopenDebug": "reopen_debug.json",
        "sourceBlend": "source.blend",
        "invocation": "invocation.json",
        "resolvedConfig": "resolved_config.json",
    })
    print(
        f"anim2sheet {command} OK -> {output}; action={resolved['animation']}; capability={resolved['authoringCapability']}; frames={frames}; cameras={camera_names}; gif={gif_enabled}",
        flush=True,
    )
    return 0
