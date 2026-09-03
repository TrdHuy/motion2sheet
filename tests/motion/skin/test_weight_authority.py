from __future__ import annotations

from motion2sheet.motion.skin import build_skin_document
from motion2sheet.motion.skin.authority import (
    blender_float32_weight,
    canonicalize_blender_weight_precision,
)


def test_real_mixamo_worst_weight_uses_exact_blender_float32_authority():
    # Real Mixamo Skin E2E #15, Ch39 vertex 2647 / mixamorig:LeftArm.
    source_normalized = 0.9499854147391422
    assert blender_float32_weight(source_normalized) == 0.9499853849411011
    assert source_normalized - blender_float32_weight(source_normalized) == 2.9798041145667753e-08


def test_float32_skin_authority_is_idempotent_and_keeps_normalized_sum_valid():
    document = {
        "meshes": [
            {
                "weights": [
                    {
                        "vertex": 2647,
                        "influences": [
                            ["mixamorig:LeftArm", 0.9499854147391422],
                            ["mixamorig:LeftShoulder", 0.050014585260857745],
                        ],
                    }
                ]
            }
        ]
    }
    canonicalize_blender_weight_precision(document)
    first = [row[1] for row in document["meshes"][0]["weights"][0]["influences"]]
    assert first == [0.9499853849411011, 0.05001458525657654]
    assert abs(sum(first) - 1.0) == 2.9802322387695312e-08
    canonicalize_blender_weight_precision(document)
    second = [row[1] for row in document["meshes"][0]["weights"][0]["influences"]]
    assert second == first


def test_public_skin_builder_routes_through_blender_weight_authority():
    assert build_skin_document.__module__ == "motion2sheet.motion.skin.authority"
