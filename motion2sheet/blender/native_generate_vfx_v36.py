"""Blender-native VFX renderer V36: more organic torn asymmetric powered silhouette."""
from __future__ import annotations

import importlib.util
import math
import random
from pathlib import Path

import bpy

_V35_PATH = Path(__file__).with_name("native_generate_vfx_v35.py")
_SPEC = importlib.util.spec_from_file_location("motion2sheet_native_vfx_v35", _V35_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load V35")
v35 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v35)

v34, v33, v32, v31, v30, v29, v28, v27, v23 = v35.v34, v35.v33, v35.v32, v35.v31, v35.v30, v35.v29, v35.v28, v35.v27, v35.v23
v21, v19, v18, v17, v16, v14 = v35.v21, v35.v19, v35.v18, v35.v17, v35.v16, v35.v14
v12, v9, v8, v7, v6, base = v35.v12, v35.v9, v35.v8, v35.v7, v35.v6, v35.base


def setup_scene(spec):
    scene, layers = v35.setup_scene(spec)
    scene["vfx_renderer"] = "blender-native-v36"
    scene["vfx_shell_model"] = "torn-asymmetric-belly-with-local-bites-and-flares"
    return scene, layers


def _g(q, c, w):
    return math.exp(-((q-c)/w)**2)


def band_polygon(p, radius, tail, head, outer_scale, inner_scale, seed, phase_shift=0.0):
    rng = random.Random(seed)
    phase = rng.uniform(0.0, math.tau) + phase_shift
    nominal = float(p["thickness"]) * float(p["shape.body_scale"])
    edge = float(p["shape.edge_noise"])
    ef = float(p["shape.edge_noise_frequency"])
    detail = float(p["shape.detail_noise"])
    df = float(p["shape.detail_noise_frequency"])
    taper = max(.18, float(p["shape.taper_power"]))
    flare = float(p["shape.flare"])
    outer, inner = [], []
    samples = 148

    # Localized contour events deliberately avoid periodic/ribbon-like geometry.
    # Positive values flare outward; negative values bite into the shell.
    events = (
        (.10, .030, .18), (.18, .042, -.16), (.29, .055, .22),
        (.39, .036, -.13), (.51, .060, .27), (.62, .040, -.18),
        (.73, .052, .24), (.83, .034, -.14), (.91, .028, .20),
    )
    inner_events = ((.24,.050,-.07),(.46,.042,.06),(.67,.050,-.08),(.82,.038,.05))

    for i in range(samples):
        q = i / (samples - 1)
        u = tail + (head-tail) * q
        x, y, a = v16.point_on_spine(radius, u, p)
        nx, ny = math.cos(a), math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)

        env = math.sin(math.pi*q) ** taper
        belly = _g(q,.54,.24)
        upper = _g(q,.20,.15)
        lower = _g(q,.80,.16)
        waist = _g(q,.39,.075)
        # Unequal top/bottom body weighting removes the perfect horseshoe feel.
        macro = (.57 + (1.02 + .42*flare)*belly + .26*upper + .43*lower - .18*waist) * (.43 + .57*env)

        low = math.sin(math.tau*1.18*q + phase) + .42*math.sin(math.tau*2.35*q + phase*.53)
        med = math.sin(math.tau*(ef*.12)*q + phase*.73)
        fine = math.sin(math.tau*(df*.072)*q + phase*.37) + .36*math.sin(math.tau*(df*.145)*q + phase*.81)
        local = sum(d*_g(q,c,w) for c,w,d in events)
        ilocal = sum(d*_g(q,c,w) for c,w,d in inner_events)

        outer_mod = 1.0 + .075*edge*low + .026*edge*med + .045*detail*fine + local
        inner_mod = 1.0 + .018*edge*low - .012*detail*fine + ilocal
        ow = nominal*outer_scale*macro*max(.25, outer_mod)
        iw = nominal*inner_scale*(.47 + .22*belly + .06*lower)*(.38 + .62*env)*max(.30, inner_mod)

        # Low-frequency center drift plus three localized lateral kicks creates
        # a torn slash mass with a dominant belly instead of a concentric C.
        kick = .13*_g(q,.28,.060) - .11*_g(q,.59,.072) + .10*_g(q,.78,.052)
        shift = nominal*(.11*math.sin(math.tau*1.12*q + phase) + .042*math.sin(math.tau*2.75*q + phase*.41) + kick)
        tangent_shift = nominal*(.035*math.sin(math.tau*.92*q + phase*.61) + .022*math.sin(math.tau*2.1*q + phase*.28))
        cx = x + nx*shift + tx*tangent_shift
        cy = y + ny*shift + ty*tangent_shift

        outer.append((cx + nx*max(nominal*.08, ow), cy + ny*max(nominal*.08, ow)))
        inner.append((cx - nx*max(nominal*.04, iw), cy - ny*max(nominal*.04, iw)))
    return outer + list(reversed(inner))


def embed_sources(spec):
    v35.embed_sources(spec)
    try:
        text = bpy.data.texts.new("SOURCE_native_generate_vfx_v36.py")
        text.write(Path(__file__).read_text(encoding="utf-8"))
    except OSError:
        pass

v29.tri_visibility = v32.tri_visibility
v9.tri_visibility = v32.tri_visibility
v9.add_ribbon = v29.add_ribbon
v8.add_fragments = v29.add_fragments
v9.add_ignition = v30.add_ignition
v21.add_lightning = v35.add_lightning
v6.motion_window = v27.motion_window
v18.add_core = v33.add_core
v17._band_polygon = band_polygon
v12.point_on_spine = v16.point_on_spine; v9.point_on_spine = v16.point_on_spine; v8.point_on_spine = v16.point_on_spine; v7.point_on_spine = v16.point_on_spine; base.point_on_arc = v16.point_on_spine
base.setup_scene = setup_scene; base.make_materials = v14.make_materials; base.build_frame = v23.build_frame; base.embed_sources = embed_sources

if __name__ == "__main__":
    base.main()
