# vfx2sheet

`vfx2sheet` generates standalone VFX sprite sheets deterministically with Blender headless. The core renderer is rule-based: there is no prompt or LLM dependency.

## MVP

The first production slice supports one template and one variant:

```text
template: slash
variant: lightning
```

## Build

```bash
vfx2sheet build \
  --template slash \
  --variant lightning \
  --frames 8 \
  --fps 12 \
  --canvas 512x512 \
  --sheet-columns 4 \
  --seed 42891 \
  --set radius=1.5 \
  --set arc_angle=150 \
  --set thickness=0.12 \
  --set sparks.count=22 \
  --output build/vfx/lightning_slash
```

Output:

```text
build/vfx/lightning_slash/
├── source.json
├── metadata.json
├── frames/
│   ├── 01.png
│   └── ... 08.png
├── vfx_sheet.png
└── preview.gif
```

All frames use a fixed RGBA canvas with transparent background. `vfx_sheet.png` preserves the same per-frame canvas; frames are never independently cropped/rescaled.

## Validate

```bash
vfx2sheet validate build/vfx/lightning_slash
```

Validation checks frame count, dimensions, transparent corners, non-empty alpha content, animation change, buildup/decay, sheet dimensions and metadata/spec agreement.

## Determinism contract

The stochastic details of the effect are controlled only by `seed` plus explicit parameters. CI renders the canonical lightning slash twice and compares decoded RGBA pixels frame-by-frame and for the final sheet.

The reproducibility boundary is the same generator code + Blender version + input spec + seed. CI pins Blender 4.5.

## Supported parameters

```text
radius
arc_angle
thickness
core.intensity
glow.intensity
sparks.count
sparks.spread
sparks.size
lightning.jitter
lightning.branches
start_angle
rotation
fade_in
fade_out
```

Unknown keys fail instead of being ignored. Numeric ranges are validated before Blender starts.

## Architecture

```text
CLI parameters
    ↓
VfxSpec / source.json
    ↓
Blender 4.5 headless
    ↓
procedural slash geometry
    ├── outer energy body
    ├── bright core
    ├── lightning branches
    └── seeded sparks
    ↓
RGBA frame PNGs
    ↓
Pillow packer
    ├── vfx_sheet.png
    └── preview.gif
```

AI can be added later as an optional authoring layer that creates/edits specs, but `vfx2sheet` itself remains deterministic and AI-independent.
