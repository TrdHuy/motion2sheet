import json
import math

import pytest

from motion2sheet.vfx2sheet.cli import parser, resolve_trajectory
from motion2sheet.vfx2sheet.effects.splash.config import VfxSpec
from motion2sheet.vfx2sheet.common.trajectory.config import load_trajectory_config, validate_trajectory_config
from motion2sheet.vfx2sheet.common.trajectory.blender import BlenderTrajectory, BlenderTrajectory3D, LEGACY_POINTS


def _v16_catmull(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return (
        .5 * ((2*p1[0])+(-p0[0]+p2[0])*t+(2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2+(-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3),
        .5 * ((2*p1[1])+(-p0[1]+p2[1])*t+(2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2+(-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3),
    )


def _v16_raw(radius, t, p):
    t = max(0.0, min(1.0, t))
    n = len(LEGACY_POINTS) - 1
    s = t * n
    seg = min(n - 1, int(s))
    q = s - seg
    p1, p2 = LEGACY_POINTS[seg], LEGACY_POINTS[seg + 1]
    p0 = LEGACY_POINTS[seg - 1] if seg > 0 else p1
    p3 = LEGACY_POINTS[seg + 2] if seg + 2 < len(LEGACY_POINTS) else p2
    x, y = _v16_catmull(p0, p1, p2, p3, q)
    form = float(p["shape.form_noise"])
    ff = float(p["shape.form_noise_frequency"])
    x += form*(.042*math.sin(math.tau*.43*ff*t+.22)+.016*math.sin(math.tau*.79*ff*t+1.10))
    y += form*(.030*math.sin(math.tau*.37*ff*t+.91)+.012*math.sin(math.tau*.73*ff*t+.35))
    rot = math.radians(float(p.get("rotation", 0.0)))
    cr, sr = math.cos(rot), math.sin(rot)
    x, y = x*cr-y*sr, x*sr+y*cr
    x *= radius
    y *= radius
    x += float(p["shape.offset_x"])*radius*3.0
    y -= float(p["shape.offset_y"])*radius*3.0
    return x, y


def test_cli_accepts_trajectory_config():
    args = parser().parse_args([
        "build", "--profile", "profiles/vfx2sheet/splash/lightning_slash.json5",
        "--trajectory-config", "path.json5", "--output", "build/vfx",
    ])
    assert args.trajectory_config == "path.json5"


def test_direct_and_wrapped_trajectory_config_are_supported(tmp_path):
    config = {"type": "points", "points": [[0, 0], [1, 1], [2, 0]]}
    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps(config), encoding="utf-8")
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"trajectory": config}), encoding="utf-8")
    assert load_trajectory_config(direct) == load_trajectory_config(wrapped)


def test_cli_trajectory_config_overrides_profile(tmp_path):
    path = tmp_path / "trajectory.json"
    path.write_text(json.dumps({"points": [[0, 0], [1, 0], [1, 1]]}), encoding="utf-8")
    args = parser().parse_args([
        "build", "--profile", "profile.json5", "--trajectory-config", str(path), "--output", "out",
    ])
    resolved = resolve_trajectory(args, {"trajectory": {"points": [[0, 0], [-1, 0]]}})
    assert resolved["points"][1] == [1.0, 0.0]


def test_invalid_trajectory_inputs_are_rejected():
    with pytest.raises(ValueError, match="at least 2"):
        validate_trajectory_config({"points": [[0, 0]]})
    with pytest.raises(ValueError, match="duplicates"):
        validate_trajectory_config({"points": [[0, 0], [0, 0]]})
    with pytest.raises(ValueError, match="closed"):
        validate_trajectory_config({"points": [[0, 0], [1, 0]], "closed": True})
    with pytest.raises(ValueError, match="interpolation"):
        validate_trajectory_config({"points": [[0, 0], [1, 0]], "interpolation": "bezier"})
    with pytest.raises(ValueError, match="exactly 3"):
        validate_trajectory_config({"dimensions": 3, "points": [[0, 0, 0], [1, 1]]})
    with pytest.raises(ValueError, match="top"):
        validate_trajectory_config({"type": "conical-helix", "bottom": 1, "top": 0})


def test_legacy_blender_trajectory_matches_v16_raw_spine_exactly():
    p = VfxSpec.create(template="slash", variant="lightning").params
    trajectory = BlenderTrajectory(None)
    for radius in (1.0, 1.9):
        for t in (0.0, .001, .06, .25, .55, .88, .999, 1.0):
            assert trajectory.raw_position(radius, t, p) == pytest.approx(_v16_raw(radius, t, p), abs=1e-12)


def test_points_trajectory_returns_finite_unit_basis():
    p = VfxSpec.create(template="slash", variant="lightning").params
    trajectory = BlenderTrajectory({
        "type": "points", "interpolation": "catmull-rom", "closed": False,
        "points": [[-.8, .8], [-.2, .9], [.3, .3], [-.1, -.2], [.8, -.7]],
    })
    for t in (0.0, .1, .5, .9, 1.0):
        x, y, tx, ty, nx, ny = trajectory.sample(1.5, t, p)
        assert all(math.isfinite(v) for v in (x, y, tx, ty, nx, ny))
        assert math.hypot(tx, ty) == pytest.approx(1.0)
        assert math.hypot(nx, ny) == pytest.approx(1.0)
        assert tx * nx + ty * ny == pytest.approx(0.0, abs=1e-12)


def test_v48_2d_points_preserve_v47_projected_positions():
    p = VfxSpec.create(template="slash", variant="lightning").params
    config = {
        "type": "points", "dimensions": 2, "interpolation": "catmull-rom", "closed": False,
        "points": [[-.8, .8], [-.2, .9], [.3, .3], [-.1, -.2], [.8, -.7]],
    }
    old = BlenderTrajectory(config)
    new = BlenderTrajectory3D(config)
    for t in (0.0, .06, .25, .5, .8, 1.0):
        assert new.raw_position(1.4, t, p) == pytest.approx(old.raw_position(1.4, t, p), abs=1e-12)


def test_v48_3d_points_return_orthonormal_basis_and_scale():
    p = VfxSpec.create(template="slash", variant="lightning").params
    trajectory = BlenderTrajectory3D({
        "type": "points", "dimensions": 3, "interpolation": "catmull-rom", "closed": False,
        "points": [[1, -1, 0], [0, -.4, 1], [-.7, .2, 0], [0, .8, -.4]],
        "scale": {"start": 1.2, "end": .3},
    })
    assert trajectory.has_depth
    for t in (0.0, .2, .5, .8, 1.0):
        sample = trajectory.sample3d(1.0, t, p)
        assert len(sample) == 13
        assert all(math.isfinite(v) for v in sample)
        tangent = sample[3:6]
        normal = sample[6:9]
        binormal = sample[9:12]
        assert math.sqrt(sum(v*v for v in tangent)) == pytest.approx(1.0)
        assert math.sqrt(sum(v*v for v in normal)) == pytest.approx(1.0)
        assert math.sqrt(sum(v*v for v in binormal)) == pytest.approx(1.0)
        assert sum(a*b for a, b in zip(tangent, normal)) == pytest.approx(0.0, abs=1e-10)
    assert trajectory.scale_at(0.0) == pytest.approx(1.2)
    assert trajectory.scale_at(1.0) == pytest.approx(.3)


def test_conical_helix_is_3d_and_tapers_upward():
    config = validate_trajectory_config({
        "type": "conical-helix", "turns": 2.0, "bottom": -1.0, "top": 1.0,
        "radiusStart": 1.0, "radiusEnd": .1, "phaseDegrees": 0, "samples": 33,
    })
    trajectory = BlenderTrajectory3D(config)
    assert trajectory.kind == "conical-helix"
    assert trajectory.dimensions == 3
    assert trajectory.has_depth
    assert len(trajectory.points) == 33
    start_radius = math.hypot(trajectory.points[0][0], trajectory.points[0][2])
    end_radius = math.hypot(trajectory.points[-1][0], trajectory.points[-1][2])
    assert start_radius == pytest.approx(1.0)
    assert end_radius == pytest.approx(.1)
    assert trajectory.points[0][1] == pytest.approx(-1.0)
    assert trajectory.points[-1][1] == pytest.approx(1.0)
