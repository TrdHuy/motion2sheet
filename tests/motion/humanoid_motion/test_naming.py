from pathlib import Path


TEXT_SUFFIXES = {".py", ".json", ".json5", ".md", ".yml", ".yaml", ".sh", ".txt"}


def _find_tokens(root: Path, paths: list[Path], tokens: tuple[str, ...]) -> list[str]:
    failures = []
    for path in paths:
        candidates = [path] if path.is_file() else [
            item for item in path.rglob("*")
            if item.is_file() and item.suffix.lower() in TEXT_SUFFIXES
        ]
        for candidate in candidates:
            text = candidate.read_text(encoding="utf-8")
            for token in tokens:
                if token in text:
                    failures.append(f"{candidate.relative_to(root)} contains legacy token {token!r}")
    return failures


def test_legacy_humanoid_motion_milestone_name_is_absent_from_production_surface():
    root = Path(__file__).resolve().parents[3]
    legacy = ("contract" + "_c", "contract" + "-c", "Contract" + " C")
    paths = [
        root / "README.md",
        root / "docs" / "humanoid-motion.md",
        root / ".github" / "workflows" / "ci.yml",
        root / ".github" / "workflows" / "humanoid-motion-e2e.yml",
        root / "ci" / "components.json",
        root / "motion2sheet" / "motion" / "cli.py",
        root / "motion2sheet" / "motion" / "humanoid_motion",
        root / "profiles" / "humanoid_motion",
        root / "profiles" / "cameras" / "front_humanoid_motion.json5",
        root / "tests" / "ci" / "test_detect_affected.py",
        root / "tests" / "motion" / "humanoid_motion",
    ]
    assert not _find_tokens(root, paths, legacy)


def test_legacy_motion_json_milestone_name_is_absent_from_pr13_surfaces():
    root = Path(__file__).resolve().parents[3]
    legacy = (
        "Contract" + " B",
        "Contract" + "B",
        "contract" + "-b",
        "contract" + "_b",
    )
    paths = [
        root / "docs" / "humanoid-motion.md",
        root / ".github" / "workflows" / "humanoid-motion-e2e.yml",
        root / ".github" / "workflows" / "real-skin-cross-animation-e2e.yml",
        root / ".github" / "workflows" / "real-skin-e2e.yml",
        root / ".github" / "workflows" / "real-skin-preflight.yml",
        root / ".github" / "workflows" / "source-character-render.yml",
        root / "motion2sheet" / "motion" / "character_render",
        root / "motion2sheet" / "motion" / "model_render",
        root / "motion2sheet" / "motion" / "humanoid_motion",
        root / "tests" / "motion" / "character_render",
        root / "tests" / "motion" / "model_render",
        root / "tests" / "motion" / "humanoid_motion",
    ]
    assert not _find_tokens(root, paths, legacy)
