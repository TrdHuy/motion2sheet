from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from motion2sheet.motion.cli import parser
from motion2sheet.motion.humanoid_motion import review_target


ROOT = Path(__file__).resolve().parents[3]
PROFILE = ROOT / "profiles/humanoid_motion/review_target_character_a_v1.json"
SKILL = ROOT / "skills/humanoid-motion-local-authoring/SKILL.md"


def test_default_character_a_profile_uses_pinned_validated_fixture():
    profile = review_target.load_review_target_profile(PROFILE)
    release = json.loads(
        (ROOT / "tests/motion/humanoid_motion/fixtures/release_assets.json").read_text()
    )["assets"]["character-a"]
    assert profile["id"] == "character-a-v1"
    assert profile["source"] == {
        key: release[key] for key in ("filename", "url", "sha256", "size")
    }
    for path in (
        PROFILE,
        ROOT / "profiles/humanoid_motion/mixamo_humanoid_v1.json",
        ROOT / "profiles/cameras/front_humanoid_motion.json5",
    ):
        assert path.is_file()
        assert path.stat().st_size > 0


def test_prepare_review_target_materializes_exact_render_contract(tmp_path, monkeypatch):
    source = b"with-skin-fbx-fixture"
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "mapping.json").write_text("{}", encoding="utf-8")
    profile = profile_dir / "target.json"
    profile.write_text(
        json.dumps(
            {
                "schema": "motion2sheet.humanoid-motion.review-target",
                "version": 1,
                "id": "test-target",
                "source": {
                    "filename": "character.fbx",
                    "url": "https://example.invalid/character.fbx",
                    "sha256": hashlib.sha256(source).hexdigest(),
                    "size": len(source),
                },
                "characterMapping": "mapping.json",
            }
        ),
        encoding="utf-8",
    )

    def exporter(*, input_path, output, blender):
        assert input_path.read_bytes() == source
        assert blender == "fake-blender"
        (output / "model.glb").write_bytes(b"glb")
        (output / "rig.json").write_text("{}", encoding="utf-8")
        (output / "skin.json").write_text("{}", encoding="utf-8")
        return {"validated": True}

    monkeypatch.setattr(review_target, "validate_rig_document", lambda value: {"id": "rig"})
    monkeypatch.setattr(review_target, "read_mapping", lambda path: {"id": "mapping"})
    monkeypatch.setattr(
        review_target,
        "validate_character_mapping",
        lambda mapping, rig: mapping,
    )
    output = tmp_path / "review-target/character-a-v1"
    report = review_target.prepare_humanoid_review_target(
        output=output,
        profile_path=profile,
        blender="fake-blender",
        opener=lambda *_args, **_kwargs: io.BytesIO(source),
        sleeper=lambda _seconds: None,
        exporter=exporter,
    )
    assert report["id"] == "test-target"
    assert {path.name for path in output.iterdir()} == {
        "model.glb",
        "rig.json",
        "skin.json",
        "review-target.json",
    }
    assert all((output / name).stat().st_size > 0 for name in ("model.glb", "rig.json", "skin.json"))


def test_review_target_and_render_cli_accept_exact_skill_paths():
    root = parser()
    prepare = root.parse_args(
        [
            "prepare-humanoid-review-target",
            "--output",
            "review-target/character-a-v1",
        ]
    )
    assert prepare.profile == str(review_target.DEFAULT_REVIEW_TARGET_PROFILE)
    render = root.parse_args(
        [
            "render-humanoid-animation",
            "--model",
            "review-target/character-a-v1/model.glb",
            "--character-rig",
            "review-target/character-a-v1/rig.json",
            "--skin",
            "review-target/character-a-v1/skin.json",
            "--character-mapping",
            str(ROOT / "profiles/humanoid_motion/mixamo_humanoid_v1.json"),
            "--animation",
            "candidate/animation.json",
            "--camera-profile",
            str(ROOT / "profiles/cameras/front_humanoid_motion.json5"),
            "--output",
            "review/front",
        ]
    )
    assert render.model == "review-target/character-a-v1/model.glb"


def test_skill_documents_resolved_default_target_without_asset_placeholders():
    text = SKILL.read_text(encoding="utf-8")
    assert "motion2sheet prepare-humanoid-review-target" in text
    for path in (
        "review-target/character-a-v1/model.glb",
        "review-target/character-a-v1/rig.json",
        "review-target/character-a-v1/skin.json",
        "$SDAR_REPOSITORY/profiles/humanoid_motion/mixamo_humanoid_v1.json",
        "$SDAR_REPOSITORY/profiles/cameras/front_humanoid_motion.json5",
    ):
        assert path in text
    assert "<model.glb>" not in text
    assert "<rig.json>" not in text
    assert "<skin.json>" not in text
