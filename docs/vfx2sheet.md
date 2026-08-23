# vfx2sheet

`vfx2sheet` generates standalone VFX sprite sheets deterministically with Blender headless plus deterministic Pillow post-processing. The renderer is rule-based: there is no prompt or LLM dependency.

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
  --set core.width_jitter=0.60 \
  --set lightning.major_width_max=12 \
  --set energy.cyan_threshold=0.72 \
  --set energy.root_width_coupling=0.82 \
  --set colors.outer=#0010F0 \
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

## Shared EnergyGraph

The lightning-slash final image is no longer assembled as independent white-core and external-lightning overlays. A deterministic `EnergyGraph` is generated once per frame and stores the slash spine as shared nodes:

```text
EnergyNode
├── position
├── tangent / outward normal
├── local core width
└── local energy
```

The same nodes drive:

```text
organic core geometry
    ↓
major lightning roots embedded inside the core
    ↓
parent → child branch topology
    ↓
micro filaments
```

Major bolts begin inside the hot core, cross the local core boundary and then fork outward. Their root thickness is coupled to the local core width, avoiding a visible pasted-on junction between core and lightning.

## Energy-field color model

Blender provides the deterministic slash silhouette, breakup geometry, surface detail and alpha support. The final color is derived from a scalar energy field rather than alpha-stacking separate blue/cyan/white slabs:

```text
low energy
    ↓
deep saturated blue
    ↓
electric blue
    ↓
cyan
    ↓
white-hot energy
```

Color interpolation is performed in linear-light space before encoding back to RGBA. Core and lightning raise the same scalar field, so their brightness/color transitions share one model. Glow is also derived from the unified field.

Artist-facing energy controls include:

```text
energy.body_floor
energy.body_gain
energy.cyan_threshold
energy.white_threshold
energy.turbulence
energy.turbulence_frequency
energy.core_gain
energy.lightning_gain
energy.root_width_coupling
energy.alpha_power
energy.alpha_gain
energy.base_alpha_mix
energy.glow_radius
energy.glow_strength
```

## Other configurable visual parameters

Core controls:

```text
core.width_min
core.width_max
core.width_jitter
core.width_smoothness
core.center_jitter
core.center_frequency
core.streak_count
core.streak_width_ratio
core.split_probability
core.hotspot_count
core.hotspot_scale
```

Hierarchical external-lightning controls:

```text
lightning.major_count
lightning.major_width_min
lightning.major_width_max
lightning.tip_width
lightning.width_jitter
lightning.width_smoothness
lightning.taper_power
lightning.branch_probability
lightning.branch_depth
lightning.minor_width_ratio
lightning.minor_length_ratio
lightning.micro_count
lightning.micro_width
lightning.micro_intensity
lightning.length
lightning.jitter
lightning.spread
```

Blender/base-shape controls remain available for silhouette and surface structure:

```text
shape.body_scale
shape.inner_scale
shape.core_scale
shape.form_noise
shape.form_noise_frequency
shape.edge_noise
shape.edge_noise_frequency
shape.detail_noise
shape.detail_noise_frequency
shape.taper_power
shape.flare
shape.tongue_count
shape.tongue_length
shape.tongue_curve
shape.tongue_width

lightning.surface_crack_count
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

Stochastic details are controlled by the master `seed`. EnergyGraph, field turbulence, branching and decay all derive stable seeds from it. CI renders the same resolved profile twice and compares decoded RGBA pixels frame-by-frame and for the final sheet.

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
    ├── canonical slash silhouette
    ├── deterministic body turbulence/tongues
    ├── surface cracks + sparks
    └── breakup support
    ↓
shared EnergyGraph
    ├── organic core spine
    ├── core-connected major bolts
    ├── real child branches
    └── micro filaments
    ↓
scalar energy field
    ↓
linear-light energy gradient + glow
    ↓
deterministic late-decay shards
    ↓
RGBA frames
    ↓
Pillow packer
    ├── vfx_sheet.png
    └── preview.gif
```

AI can later be an optional authoring layer that produces or edits profiles/specs. `vfx2sheet` itself remains deterministic and AI-independent.
