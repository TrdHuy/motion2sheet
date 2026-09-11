from __future__ import annotations

from pathlib import Path

from motion2sheet.motion.harness_anim_generator.motion2sheet_adapter import Motion2SheetAdapter


def test_adapter_reuses_character_export_and_humanoid_renderer(tmp_path, monkeypatch, animation_document):
    root = tmp_path / "repo"
    (root / "sample").mkdir(parents=True)
    (root / "sample" / "walk_mixamo.fbx").write_bytes(b"fbx")
    (root / "profiles" / "humanoid_motion").mkdir(parents=True)
    (root / "profiles" / "cameras").mkdir(parents=True)
    (root / "profiles" / "humanoid_motion" / "mixamo_humanoid_v1.json").write_text("{}")
    (root / "profiles" / "cameras" / "front_humanoid_motion.json5").write_text("{}")
    calls = {"export": 0, "render": 0}

    def fake_export(*, input_path, output, blender):
        calls["export"] += 1
        output.mkdir(parents=True)
        for name in ("model.glb", "rig.json", "skin.json"):
            (output / name).write_bytes(b"asset")
        return {}

    def fake_render(**kwargs):
        calls["render"] += 1
        output = kwargs["output"]
        output.mkdir(parents=True)
        (output / "pose_sheet.png").write_bytes(b"png")
        (output / "preview.gif").write_bytes(b"gif")
        assert kwargs["sample_count"] == 8
        assert kwargs["output_fps"] == 8.0
        assert kwargs["canvas"] == (160, 160)
        assert kwargs["gif"] is True
        return {"pass": True}

    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.motion2sheet_adapter.export_character",
        fake_export,
    )
    monkeypatch.setattr(
        "motion2sheet.motion.harness_anim_generator.motion2sheet_adapter.render_humanoid_animation",
        fake_render,
    )
    adapter = Motion2SheetAdapter(repo_root=root, workspace=tmp_path / "workspace")
    validation = adapter.validate_animation(animation_document)
    assert validation.passed is True
    animation_path = adapter.materialize_animation(validation.animation, tmp_path / "candidate.json")
    result = adapter.render_candidate(animation_path, tmp_path / "v1" / "renders")
    adapter.render_candidate(animation_path, tmp_path / "v2" / "renders")
    assert result.preview_path.is_file()
    assert calls == {"export": 1, "render": 2}
