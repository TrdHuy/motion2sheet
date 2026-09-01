import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from motion2sheet.motion.cli import parser as root_parser
from motion2sheet.motion.roundtrip import cli
from motion2sheet.motion.roundtrip.visual import render_pose_sheet


def _pose_data(frame_count=32):
    return {
        "frameRange": [1, frame_count],
        "frames": {
            str(frame): {
                "Bone": {
                    "head": [0.0, 0.0, 0.0],
                    # Keep every fixture pose visibly distinct after canonical
                    # integer pixel snap so GIF frame-count assertions measure
                    # temporal packaging rather than duplicate-frame coalescing.
                    "tail": [0.1 + frame * 0.02, 0.0, 1.0],
                }
            }
            for frame in range(1, frame_count + 1)
        },
    }


def _validated_animation(frame_count=32):
    return {
        "fps": 30.0,
        "frameRange": [1, frame_count],
        "frames": [{"frame": frame} for frame in range(1, frame_count + 1)],
    }


def _args(tmp_path, renderer, gif=True):
    rig_path = tmp_path / "rig.json"
    animation_path = tmp_path / "animation.json"
    rig_path.write_text("{}\n", encoding="utf-8")
    animation_path.write_text("{}\n", encoding="utf-8")
    return SimpleNamespace(
        rig=str(rig_path),
        animation=str(animation_path),
        renderer=renderer,
        output=str(tmp_path / f"render-{renderer}"),
        gif=gif,
        blender="blender",
    )


def _install_validators(monkeypatch):
    rig_document = {"bones": [{"name": "Bone"}]}
    animation_document = _validated_animation()
    monkeypatch.setattr(cli, "validate_rig_document", lambda _data: rig_document)
    monkeypatch.setattr(cli, "validate_animation_document", lambda _data, _rig: animation_document)


def test_public_parser_exposes_render_animation_json():
    args = root_parser().parse_args([
        "render-animation-json",
        "--rig", "rig.json",
        "--animation", "animation.json",
        "--renderer", "blender",
        "--output", "build/render",
        "--gif",
    ])
    assert args.command == "render-animation-json"
    assert args.renderer == "blender"
    assert args.gif is True


@pytest.mark.parametrize("renderer", ["pillow", "blender"])
def test_render_animation_json_uses_only_json_inputs_and_emits_full_sheet(monkeypatch, tmp_path, renderer):
    args = _args(tmp_path, renderer)
    _install_validators(monkeypatch)
    calls = []

    def fake_run_blender(script, _blender, arguments, *, check=True):
        calls.append((script, list(arguments)))
        assert check is True
        assert not any(value.lower().endswith(".fbx") for value in arguments)
        if script == "blender_pose_json.py":
            output = Path(arguments[arguments.index("--output") + 1])
            output.write_text(json.dumps(_pose_data()), encoding="utf-8")
        elif script == "blender_visual.py":
            pose_path = Path(arguments[arguments.index("--input") + 1])
            output = Path(arguments[arguments.index("--output") + 1])
            render_pose_sheet(pose_path, output / "pose_sheet.png")
        else:
            raise AssertionError(f"unexpected Blender script: {script}")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli, "run_blender", fake_run_blender)
    assert cli.render_animation_json(args) == 0

    output = Path(args.output)
    pose_sheet = output / "pose_sheet.png"
    preview = output / "preview.gif"
    report = json.loads((output / "render.json").read_text(encoding="utf-8"))
    assert pose_sheet.is_file() and preview.is_file()
    assert not (output / ".pose_data.json").exists()
    with Image.open(pose_sheet) as image:
        assert image.size == (2048, 1024)
    with Image.open(preview) as image:
        assert image.n_frames == 32
    assert report["sourceMotionFileRequired"] is False
    assert report["frameCount"] == 32
    assert report["visual"]["frameCount"] == 32
    assert report["visual"]["columns"] == 8
    assert report["visual"]["rows"] == 4
    assert report["visual"]["canvasPerFrame"] == [256, 256]
    assert report["visual"]["layout"]["occupiedCells"] == 32
    assert report["visual"]["layout"]["emptyCells"] == []
    assert calls[0][0] == "blender_pose_json.py"
    assert all("verify" not in script for script, _arguments in calls)


def test_invalid_canonical_json_fails_before_renderer(monkeypatch, tmp_path):
    args = _args(tmp_path, "pillow", gif=False)
    called = False

    def forbidden_run_blender(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("renderer must not run for invalid canonical JSON")

    monkeypatch.setattr(cli, "run_blender", forbidden_run_blender)
    with pytest.raises(ValueError):
        cli.render_animation_json(args)
    assert called is False
    assert not Path(args.output).exists()
