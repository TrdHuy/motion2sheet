import random

from motion2sheet.vfx.energy_graph import build_energy_graph
from motion2sheet.vfx.spec import VfxSpec


def test_energy_graph_is_deterministic_for_same_seed_and_frame():
    spec = VfxSpec.create(template="slash", variant="lightning")
    first = build_energy_graph((512, 512), spec.params, seed=42891, frame_index=4, frame_count=8)
    second = build_energy_graph((512, 512), spec.params, seed=42891, frame_index=4, frame_count=8)
    assert first == second
    assert len(first.nodes) == 72


def test_energy_graph_exposes_shared_core_geometry_for_lightning_anchors():
    spec = VfxSpec.create(template="slash", variant="lightning")
    graph = build_energy_graph((512, 512), spec.params, seed=42891, frame_index=4, frame_count=8)
    anchors = graph.major_anchor_indices(4, random.Random(7))
    assert len(anchors) == 4
    for index in anchors:
        node = graph.nodes[index]
        assert 0.1 < node.u < 0.9
        assert node.width > 0.0
        assert 0.0 < node.energy <= 1.0
        assert abs(node.tangent[0] * node.normal[0] + node.tangent[1] * node.normal[1]) < 1e-6
