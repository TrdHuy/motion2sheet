from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import LoadedSkill, SkillError, SkillManifest, SkillStep


DEFAULT_SKILL = Path("skills/humanoid-motion-local-authoring")


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillError(f"{label} must be a non-empty string")
    return value.strip()


def load_skill(directory: Path) -> LoadedSkill:
    directory = Path(directory).resolve()
    skill_path = directory / "SKILL.md"
    manifest_path = directory / "skill.json"
    for path in (skill_path, manifest_path):
        if not path.is_file():
            raise SkillError(f"required skill file is missing: {path}")
    try:
        text = skill_path.read_text(encoding="utf-8")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SkillError(f"cannot load skill from {directory}: {exc}") from exc
    if not text.strip():
        raise SkillError(f"skill authority is empty: {skill_path}")
    if not isinstance(raw, dict) or set(raw) != {"id", "version", "steps"}:
        raise SkillError("skill.json must contain exactly id, version and steps")
    skill_id = _nonempty_text(raw["id"], "skill id")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise SkillError("skill version must be a positive integer")
    items = raw["steps"]
    if not isinstance(items, list) or not items:
        raise SkillError("skill steps must be a non-empty array")
    steps: list[SkillStep] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != {"id", "title"}:
            raise SkillError(f"skill step {index} must contain exactly id and title")
        step_id = _nonempty_text(item["id"], f"skill step {index} id")
        title = _nonempty_text(item["title"], f"skill step {index} title")
        if step_id in seen:
            raise SkillError(f"duplicate skill step id: {step_id}")
        seen.add(step_id)
        steps.append(SkillStep(step_id, title))
    return LoadedSkill(directory, text, SkillManifest(skill_id, version, tuple(steps)))
