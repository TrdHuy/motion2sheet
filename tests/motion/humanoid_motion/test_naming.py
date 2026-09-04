from pathlib import Path


TEXT_SUFFIXES = {".py", ".json", ".json5", ".md", ".yml", ".yaml", ".sh", ".txt"}


def test_legacy_milestone_name_is_absent_from_production_surface():
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
    failures = []
    for path in paths:
        candidates = [path] if path.is_file() else [
            item for item in path.rglob("*")
            if item.is_file() and item.suffix.lower() in TEXT_SUFFIXES
        ]
        for candidate in candidates:
            text = candidate.read_text(encoding="utf-8")
            for token in legacy:
                if token in text:
                    failures.append(f"{candidate.relative_to(root)} contains legacy token {token!r}")
    assert not failures, failures
