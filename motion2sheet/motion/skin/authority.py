from __future__ import annotations

import struct
from typing import Any, Iterable

from .contract import build_skin_document as _build_skin_document
from .contract import validate_skin_document


def blender_float32_weight(value: float) -> float:
    """Return the exact Python float value representable by Blender's float32 vertex-group storage."""
    quantized = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    if quantized <= 0.0:
        raise ValueError("normalized skin influence is not representable as a positive Blender float32 weight")
    return quantized


def canonicalize_blender_weight_precision(document: dict[str, Any]) -> dict[str, Any]:
    """Make Skin Contract weight authority exactly reconstructable by Blender vertex groups.

    Blender stores vertex-group membership weights as IEEE-754 single precision. Keeping
    post-normalization Python doubles in skin.json creates an artificial reconstruction
    error even when Blender stores the nearest representable value correctly. Quantize
    only the already-normalized weights; do not renormalize afterwards, because doing so
    would create new double-precision values that Blender cannot preserve exactly.
    """
    for mesh in document["meshes"]:
        for row in mesh["weights"]:
            for influence in row["influences"]:
                influence[1] = blender_float32_weight(float(influence[1]))
    return document


def build_skin_document(
    *,
    skin_id: str,
    canonical_rig: str,
    character_rig: dict[str, Any],
    model: dict[str, Any],
    bind: dict[str, Any],
    meshes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    document = _build_skin_document(
        skin_id=skin_id,
        canonical_rig=canonical_rig,
        character_rig=character_rig,
        model=model,
        bind=bind,
        meshes=meshes,
    )
    canonicalize_blender_weight_precision(document)
    return validate_skin_document(document, character_rig)
