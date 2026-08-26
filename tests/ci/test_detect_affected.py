from ci.detect_affected import load_manifest, resolve_targets


def resolve(*paths):
    return resolve_targets(load_manifest(), list(paths))


def test_component_change_runs_only_dependent_targets():
    components, targets = resolve("motion2sheet/motion/normalize/core.py")
    assert "motion-normalize" in components
    assert "motion-cli" in components
    assert "motion-normalize-unit" in targets
    assert "motion-synthetic-fbx" in targets
    assert "motion-synthetic-bvh" in targets
    assert "motion-mixamo-real" in targets
    assert "motion-retarget-unit" not in targets
    assert "vfx-unit" not in targets
    assert "vfx-splash-e2e" not in targets


def test_vfx_effect_change_does_not_run_motion():
    components, targets = resolve("motion2sheet/vfx2sheet/effects/splash/config.py")
    assert "vfx-splash" in components
    assert "vfx-unit" in targets
    assert "vfx-splash-e2e" in targets
    assert not any(name.startswith("motion-") for name in targets)


def test_direct_mixamo_test_change_runs_only_mixamo_target():
    _, targets = resolve("tests/motion/e2e/verify_mixamo_output.py")
    assert targets == {"motion-mixamo-real"}


def test_global_ci_change_runs_every_target():
    manifest = load_manifest()
    _, targets = resolve(".github/workflows/ci.yml")
    assert targets == set(manifest["test_targets"])


def test_unknown_path_fails_safe_to_full_ci():
    manifest = load_manifest()
    _, targets = resolve("motion2sheet/new_unmapped_module.py")
    assert targets == set(manifest["test_targets"])


def test_docs_only_change_runs_no_tests():
    _, targets = resolve("README.md", "docs/vfx2sheet.md")
    assert targets == set()
