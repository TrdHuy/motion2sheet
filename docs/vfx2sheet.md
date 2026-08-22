# vfx2sheet

`vfx2sheet` generates standalone VFX sprite sheets deterministically with Blender headless. The core renderer is rule-based: there is no prompt or LLM dependency.

## MVP

```text
template: slash
variant: lightning
```

## Recommended build: profile + overrides

```bash
vfx2sheet build \
  --profile profiles/vfx/lightning_slash_contract.json \
  --output build/vfx/lightning_slash
```

A profile is an artist-facing preset. Any profile value can be overridden without editing the renderer:

```bash
vfx2sheet build \
  --profile profiles/vfx/lightning_slash_contract.json \
  --set lightning.branch_count=28 \
  --set lightning.jitter=0.38 \
  --set shape.edge_noise=1.9 \
  --set colors.outer=#112EFF \
  --output build/vfx/lightning_slash_tuned
```

Explicit build arguments can also override profile-level build settings such as `--fps`, `--frames`, `--canvas`, `--sheet-columns` and `--seed`.

Resolution order:

```text
template/variant defaults
    ↓
profile JSON
    ↓
explicit CLI build arguments
    ↓
--set overrides
    ↓
resolved source.json
```

`source.json` is the complete reproducible render contract written to the output directory.

The original explicit form remains supported:

```bash
vfx2sheet build \
  --template slash \
  --variant lightning \
  --frames 8 --fps 12 --canvas 512x512 --sheet-columns 4 \
  --seed 42891 \
  --set radius=1.5 \
  --output build/vfx/lightning_slash
```

## Configurable visual parameters

The lightning slash renderer is config-driven. Current groups include:

```text
colors.outer
colors.body
colors.inner
colors.core
colors.lightning

intensity.outer
intensity.body
intensity.inner
intensity.core
intensity.lightning

shape.body_scale
shape.inner_scale
shape.core_scale
shape.edge_noise
shape.edge_noise_frequency
shape.taper_power
shape.flare
shape.tongue_count
shape.tongue_length

lightning.branch_count
lightning.secondary_branch_count
lightning.surface_crack_count
lightning.jitter
lightning.length
lightning.spread

sparks.count
sparks.spread
sparks.size

fragments.count
fragments.spread
fragments.size

timing.peak
timing.decay
```

Geometry/orientation parameters such as `radius`, `arc_angle`, `thickness`, `start_angle` and `rotation` are also configurable. Unknown keys, invalid colors, non-integral counts and out-of-range values fail before Blender starts.

Backward-compatible aliases remain accepted for the first MVP CLI keys:

```text
core.intensity       → intensity.core
glow.intensity       → intensity.outer
lightning.branches   → lightning.branch_count
```

## Output

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

All frames use a fixed RGBA canvas with transparent background. Frames are never independently cropped or rescaled.

## Validate

```bash
vfx2sheet validate build/vfx/lightning_slash
```

Validation checks frame count, dimensions, transparent corners, non-empty alpha content, animation change, buildup/decay, sheet dimensions and metadata/spec agreement.

## Determinism contract

Stochastic details are controlled by the master `seed`. Renderer subsystems derive stable seeds for shape, lightning, sparks and fragments. CI renders the same resolved profile twice and compares decoded RGBA pixels frame-by-frame and for the final sheet.

The reproducibility boundary is the same generator code + Blender version + resolved `source.json`. CI pins Blender 4.5.

## Architecture

```text
profile JSON + CLI overrides
    ↓
VfxSpec
    ↓
resolved source.json
    ↓
Blender 4.5 headless
    ↓
canonical slash path
    ├── outer/body/inner/core palette layers
    ├── configurable edge noise + tongues
    ├── surface lightning
    ├── primary + secondary branches
    ├── directional sparks
    └── deterministic breakup fragments
    ↓
RGBA frame PNGs
    ↓
Pillow packer
    ├── vfx_sheet.png
    └── preview.gif
```

AI can later be an optional authoring layer that produces or edits profiles/specs. `vfx2sheet` itself remains deterministic and AI-independent.
