# anim2sheet

`anim2sheet` is the Blender-native character-animation pipeline in `motion2sheet`. Its architecture mirrors the responsibility boundaries used by `vfx2sheet`: generic orchestration stays at the package root, reusable implementation lives under `common/`, and animation-specific behavior lives under `animations/<animation>/`.

The first registered animation is the 16-frame two-handed swordsman **Gale Slash**. Pose and solver values remain profile/contract data; the generic runtime does not own Gale Slash semantics.

## Architecture

```text
motion2sheet/anim2sheet/
├── __init__.py
├── cli.py
├── registry.py
├── blender_entry.py
├── common/
│   ├── camera/
│   ├── output/
│   ├── rig/
│   ├── authority/
│   └── review/
└── animations/
    └── gale_slash/
        ├── animation.py
        ├── config.py
        ├── contract.py
        └── blender/
            └── author.py
```

Dependency direction is intentionally one-way:

```text
cli -> registry -> animation runtime -> common
```

`animations/gale_slash/**` may import reusable helpers from `common/**`. `common/**` must not import Gale Slash or branch on `animation == "gale_slash"`.

### Root responsibilities

- `cli.py` exposes the public `anim2sheet build`, `anim2sheet review`, and `anim2sheet validate` commands.
- `registry.py` resolves an animation name to its runtime module and Blender author.
- `blender_entry.py` is the generic Blender bootstrap: it loads the resolved source spec, resolves the registered animation, loads its Blender author, and executes it.

The package root does not contain frame-specific strike semantics, authored wrists/elbows, body overrides, or Gale Slash review rules.

### `common/**`

Reusable implementation shared by animation definitions lives here:

- `common/camera/` — camera profile loading, selection, Blender camera setup, projection, and rendering.
- `common/output/` — sheet packing and output validation.
- `common/rig/` — humanoid rig helpers, exact arm-segment FK math, leg IK convention/diagnostics, and Blender skeleton viewport rendering.
- `common/authority/` — saved-`source.blend` reopen and proxy/joint authority diagnostics.
- `common/review/` — generic review orchestration and object/skeleton overlays.

Generic camera profiles are data under `profiles/anim2sheet/cameras/**` and are owned by the common anim2sheet layer, not by Gale Slash.

### `animations/gale_slash/**`

Gale Slash owns only action-specific behavior and contracts:

- `animation.py` resolves the Gale Slash profile, joint contract, execution-frame subset, and selected cameras.
- `config.py` validates and loads animation profile and pose-reference data.
- `contract.py` validates Gale Slash joint-contract semantics and resolves `--frames` without mutating the authoritative contract.
- `blender/author.py` applies Gale Slash body/leg overrides, deterministic two-hand arm authoring, weapon binding, and animation-specific diagnostics.

Animation data is under `profiles/anim2sheet/animations/gale_slash/**`. The joint contract remains authoritative for the complete configured pose set; an execution subset never rewrites it.

## Solver and authority model

### Deterministic joint-FK arms

Both arms use deterministic joint-driven FK. The contract authors elbow and wrist positions; shoulder positions are derived from the torso/clavicle hierarchy. Each upper-arm and forearm segment is solved exactly from its evaluated parent joint to the authored next joint. Endpoint IK is not used to choose elbow topology.

The two-handed sword is derived from the authored grip relationship and remains bound to the solved hand chain rather than being independently animated.

### Leg IK and knee authority

Legs use IK with explicit knee guides/pole targets. The mirrored pole convention is reusable rig behavior: the left and right legs use opposite pole-angle conventions. `leg_ik_debug.json` checks evaluated knee bend direction against the authored knee-guide half-space and fails when knee-guide authority is violated.

### Saved-blend authority

`source.blend` is the authoritative saved Blender state. Review performs save/reopen verification and checks:

- pre-save vs post-reopen evaluated joint persistence,
- authored arm joints vs reopened evaluated joints,
- proxy endpoints, centers, axes, and lengths vs evaluated bones.

Authority diagnostics are written to `reopen_debug.json`; canonical CI also runs the verifier under `tests/anim2sheet/common/authority/`.

## Multi-camera review

Camera definitions are config-driven. The canonical Gale Slash review uses:

- `front_final` — authoritative final/readability camera,
- `side_diag` — diagnostic camera for depth and biomechanical inspection.

The public command is the single local/CI execution authority:

```bash
anim2sheet review \
  --animation gale_slash \
  --profile profiles/anim2sheet/animations/gale_slash/animation.json5 \
  --joint-contract profiles/anim2sheet/animations/gale_slash/joint_contract.json \
  --camera-profile profiles/anim2sheet/cameras/fast_keypose_review.json \
  --output build/anim/review
```

`--frames` is an execution/debug subset only. Omitting it uses the contract's configured review frames. For example, `--frames 8` reviews only F8 while the source joint contract remains unchanged. `--cameras` similarly selects a valid subset from the camera profile.

Every build/review artifact records the resolved invocation in `invocation.json` and resolved profile/contract/camera data in `resolved_config.json`, including `contractFrames`, `executionFrames`, and selected cameras.

## Central affected CI

Automatic repository validation uses the existing central affected-CI architecture:

- `ci/components.json` owns component paths and dependency edges.
- `ci/detect_affected.py` resolves affected components and test targets.
- `.github/workflows/ci.yml` runs affected targets for pull requests.
- push to `master` and generic central `workflow_dispatch` use full CI.

The anim2sheet graph separates generic/common ownership from Gale Slash ownership. Changes under `motion2sheet/anim2sheet/common/**` or `profiles/anim2sheet/cameras/**` flow through dependent anim targets. Changes limited to `animations/gale_slash/**` or `profiles/anim2sheet/animations/gale_slash/**` select Gale Slash targets without pulling unrelated VFX work.

The canonical automatic Gale Slash E2E is always full F1-F16 with `front_final` and `side_diag`, output validation, saved-blend/proxy authority, semantic validation, and artifact upload. Automatic CI does not use a frame subset.

## Manual remote review

`.github/workflows/anim2sheet-debug.yml` is a thin `workflow_dispatch` wrapper around the same public `anim2sheet review` CLI. Its inputs mirror the user-facing review parameters: animation, profile, joint contract, camera profile, optional frames, optional cameras, Blender executable, and output directory.

Examples:

```text
frames=8             cameras=front_final,side_diag
frames=7,8           cameras=front_final
frames=<empty>       cameras=<empty>   # configured canonical defaults
```

No animation semantics live in the workflow YAML.

## Tests

Tests follow module ownership:

```text
tests/anim2sheet/
├── common/
├── cli/
└── animations/
    └── gale_slash/
        ├── unit/
        └── e2e/
```

Default `pytest` discovery includes `tests/anim2sheet`, so local `pytest` runs the anim2sheet pytest suite together with the repository's other configured test roots.

## Canonical review outputs

A review directory is self-describing and includes the authoritative Blender source plus diagnostics such as:

```text
source.json
source.blend
invocation.json
resolved_config.json
metadata.json
motion_debug.json
camera_config.json
camera_debug.json
leg_ik_debug.json
reopen_debug.json
cameras/
  front_final/
  side_diag/
object_keyposes.png
skeleton_keyposes.png
object_skeleton_overlay.png
```

Visual review remains important, but architecture/CI refactors must preserve the accepted F1-F16 pose and render state exactly unless a separate visual-polish change explicitly changes it.
