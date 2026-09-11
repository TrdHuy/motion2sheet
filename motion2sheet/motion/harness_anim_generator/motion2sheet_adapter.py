from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Protocol

from motion2sheet.motion.humanoid_motion.runner import render_humanoid_animation
from motion2sheet.motion.humanoid_motion.schema import CORE_ROTATION_JOINTS, validate_animation, write_animation
from motion2sheet.motion.model_render.runner import export_character

from .contracts import HarnessError, RenderResult, ValidationResult


def humanoid_animation_json_schema() -> dict[str, Any]:
    """Return an output-shaping schema; canonical validation remains authoritative."""

    def vector(size: int) -> dict[str, Any]:
        return {
            "type": "array",
            "items": {"type": "number"},
            "minItems": size,
            "maxItems": size,
        }

    def track(size: int) -> dict[str, Any]:
        return {"type": "array", "items": vector(size)}

    def rotation_joint() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"rotations": track(4)},
            "required": ["rotations"],
            "additionalProperties": False,
        }

    joints = {semantic: rotation_joint() for semantic in CORE_ROTATION_JOINTS}
    return {
        "type": "object",
        "properties": {
            "schema": {"type": "string"},
            "version": {"type": "integer"},
            "id": {"type": "string"},
            "canonicalSkeleton": {"type": "string"},
            "durationSeconds": {"type": "number"},
            "fps": {"type": "number"},
            "frameCount": {"type": "integer"},
            "loop": {"type": "boolean"},
            "coordinateSystem": {
                "type": "object",
                "properties": {
                    "handedness": {"type": "string"},
                    "rightAxis": {"type": "string"},
                    "forwardAxis": {"type": "string"},
                    "upAxis": {"type": "string"},
                    "translationUnit": {"type": "string"},
                },
                "required": ["handedness", "rightAxis", "forwardAxis", "upAxis", "translationUnit"],
                "additionalProperties": False,
            },
            "quaternionConvention": {
                "type": "object",
                "properties": {
                    "componentOrder": {"type": "string"},
                    "deltaSpace": {"type": "string"},
                    "signPolicy": {"type": "string"},
                },
                "required": ["componentOrder", "deltaSpace", "signPolicy"],
                "additionalProperties": False,
            },
            "root": {
                "type": "object",
                "properties": {"translations": track(3), "rotations": track(4)},
                "required": ["translations", "rotations"],
                "additionalProperties": False,
            },
            "hips": {
                "type": "object",
                "properties": {"translations": track(3), "rotations": track(4)},
                "required": ["translations", "rotations"],
                "additionalProperties": False,
            },
            "joints": {
                "type": "object",
                "properties": joints,
                "required": list(CORE_ROTATION_JOINTS),
                "additionalProperties": False,
            },
        },
        "required": [
            "schema",
            "version",
            "id",
            "canonicalSkeleton",
            "durationSeconds",
            "fps",
            "frameCount",
            "loop",
            "coordinateSystem",
            "quaternionConvention",
            "root",
            "hips",
            "joints",
        ],
        "additionalProperties": False,
    }


class MotionEngineAdapter(Protocol):
    def validate_animation(self, animation: Mapping[str, Any]) -> ValidationResult:
        """Validate a candidate against the canonical Humanoid Motion schema."""

    def materialize_animation(self, animation: Mapping[str, Any], output: Path) -> Path:
        """Write a validated animation using the canonical serializer."""

    def render_candidate(self, animation_path: Path, output: Path) -> RenderResult:
        """Render review frames and a preview through motion2sheet."""


class Motion2SheetAdapter:
    def __init__(self, *, repo_root: Path, workspace: Path, blender: str = "blender") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.workspace = Path(workspace).resolve()
        self.blender = blender

    def validate_animation(self, animation: Mapping[str, Any]) -> ValidationResult:
        try:
            validated = validate_animation(copy.deepcopy(dict(animation)))
        except (TypeError, ValueError) as exc:
            return ValidationResult(passed=False, issues=(str(exc),), animation=None)
        return ValidationResult(passed=True, issues=(), animation=validated)

    def materialize_animation(self, animation: Mapping[str, Any], output: Path) -> Path:
        write_animation(Path(output), copy.deepcopy(dict(animation)))
        return Path(output)

    def _prepare_character(self, character_dir: Path) -> None:
        outputs = tuple(character_dir / name for name in ("model.glb", "rig.json", "skin.json"))
        if all(path.is_file() for path in outputs):
            return
        source = self.repo_root / "sample" / "walk_mixamo.fbx"
        if not source.is_file():
            raise HarnessError(f"renderer bootstrap source is missing: {source}")
        try:
            export_character(input_path=source, output=character_dir, blender=self.blender)
        except Exception as exc:
            raise HarnessError(f"failed to bootstrap renderer character assets: {exc}") from exc

    def render_candidate(self, animation_path: Path, output: Path) -> RenderResult:
        output = Path(output)
        run_workspace = output.parent.parent if output.parent.name.startswith("v") else self.workspace
        character_dir = run_workspace / "renderer" / "character"
        self._prepare_character(character_dir)
        try:
            report = render_humanoid_animation(
                model_path=character_dir / "model.glb",
                character_rig_path=character_dir / "rig.json",
                skin_path=character_dir / "skin.json",
                mapping_path=self.repo_root / "profiles" / "humanoid_motion" / "mixamo_humanoid_v1.json",
                animation_path=Path(animation_path),
                camera_profile_path=self.repo_root / "profiles" / "cameras" / "front_humanoid_motion.json5",
                output=output,
                sheet_columns=8,
                canvas=(160, 160),
                background="transparent",
                gif=True,
                sample_count=8,
                output_fps=8.0,
                render_samples=1,
                blender=self.blender,
            )
        except Exception as exc:
            raise HarnessError(f"failed to render candidate {animation_path}: {exc}") from exc
        sheet = output / "pose_sheet.png"
        preview = output / "preview.gif"
        if not sheet.is_file() or not preview.is_file():
            raise HarnessError("motion2sheet renderer did not produce pose_sheet.png and preview.gif")
        return RenderResult(
            output_dir=output,
            key_frame_sheet=sheet,
            preview_path=preview,
            report=report,
        )
