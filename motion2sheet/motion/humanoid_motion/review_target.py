from __future__ import annotations

import hashlib
import json
import shutil
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from ..model_render.runner import export_character
from ..roundtrip.schema import validate_rig_document
from .mapping import read_mapping, validate_character_mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REVIEW_TARGET_PROFILE = (
    REPO_ROOT / "profiles" / "humanoid_motion" / "review_target_character_a_v1.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_review_target_profile(path: Path = DEFAULT_REVIEW_TARGET_PROFILE) -> dict[str, Any]:
    path = Path(path).resolve()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load Humanoid Motion review target profile {path}: {exc}") from exc
    required = {"schema", "version", "id", "source", "characterMapping"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("review target profile must contain the exact v1 fields")
    if value["schema"] != "motion2sheet.humanoid-motion.review-target" or value["version"] != 1:
        raise ValueError("unsupported Humanoid Motion review target profile")
    if not isinstance(value["id"], str) or not value["id"]:
        raise ValueError("review target id must be a non-empty string")
    source = value["source"]
    if not isinstance(source, dict) or set(source) != {"filename", "url", "sha256", "size"}:
        raise ValueError("review target source must contain filename, url, sha256 and size")
    if Path(str(source["filename"])).name != source["filename"] or not str(
        source["filename"]
    ).lower().endswith(".fbx"):
        raise ValueError("review target source filename must be an FBX basename")
    if not isinstance(source["url"], str) or not source["url"].startswith("https://"):
        raise ValueError("review target source URL must use HTTPS")
    sha = source["sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("review target source sha256 must be 64 lowercase hex characters")
    if isinstance(source["size"], bool) or not isinstance(source["size"], int) or source["size"] <= 0:
        raise ValueError("review target source size must be a positive integer")
    mapping = value["characterMapping"]
    if not isinstance(mapping, str) or Path(mapping).name != mapping:
        raise ValueError("review target characterMapping must be a sibling filename")
    mapping_path = path.parent / mapping
    if not mapping_path.is_file():
        raise ValueError(f"review target character mapping does not exist: {mapping_path}")
    return value


def _download(
    source: dict[str, Any],
    destination: Path,
    *,
    opener: Callable[..., Any],
    sleeper: Callable[[float], None],
) -> None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with opener(source["url"], timeout=60) as response, destination.open("wb") as output:
                shutil.copyfileobj(response, output)
            if destination.stat().st_size != source["size"]:
                raise ValueError("downloaded review target source size does not match profile")
            if _sha256(destination) != source["sha256"]:
                raise ValueError("downloaded review target source SHA-256 does not match profile")
            return
        except (OSError, urllib.error.URLError, ValueError) as exc:
            last_error = exc
            destination.unlink(missing_ok=True)
            if attempt < 2:
                sleeper(0.5 * (2**attempt))
    raise RuntimeError(f"could not download validated review target source: {last_error}")


def prepare_humanoid_review_target(
    *,
    output: Path,
    profile_path: Path = DEFAULT_REVIEW_TARGET_PROFILE,
    blender: str = "blender",
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    exporter: Callable[..., dict[str, Any]] = export_character,
) -> dict[str, Any]:
    profile_path = Path(profile_path).resolve()
    profile = load_review_target_profile(profile_path)
    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"review target output must not exist or must be empty: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.prepare-{uuid.uuid4().hex}"
    staging.mkdir()
    source_path = staging / str(profile["source"]["filename"])
    try:
        _download(profile["source"], source_path, opener=opener, sleeper=sleeper)
        export_report = exporter(input_path=source_path, output=staging, blender=blender)
        model = staging / "model.glb"
        rig_path = staging / "rig.json"
        skin = staging / "skin.json"
        for path in (model, rig_path, skin):
            if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"review target exporter did not produce {path.name}")
        rig = validate_rig_document(json.loads(rig_path.read_text(encoding="utf-8")))
        mapping_path = profile_path.parent / str(profile["characterMapping"])
        mapping = validate_character_mapping(read_mapping(mapping_path), rig)
        source_path.unlink()
        report = {
            "schema": "motion2sheet.humanoid-motion.prepared-review-target",
            "version": 1,
            "id": profile["id"],
            "profile": str(profile_path),
            "source": profile["source"],
            "characterMapping": {"id": mapping["id"], "path": str(mapping_path)},
            "outputs": {
                "model": {"path": "model.glb", "sha256": _sha256(model)},
                "rig": {"path": "rig.json", "sha256": _sha256(rig_path)},
                "skin": {"path": "skin.json", "sha256": _sha256(skin)},
            },
            "export": export_report,
        }
        (staging / "review-target.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            output.rmdir()
        staging.replace(output)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
