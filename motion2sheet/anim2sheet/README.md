# anim2sheet

`anim2sheet` is the Blender-native character-animation pipeline in `motion2sheet`. The current architecture is **profile-driven**: an animation clip is data, while reusable authoring behavior is selected by the rig capability.

The core flow is:

```text
Rig Profile
    +
Character / Equipment Profile
    +
Animation Profile / Pose / Joint Contract
        ↓
Generic profile resolver
        ↓
Authoring capability registry
        ↓
Generic Humanoid Author
        ↓
source.blend
        ↓
authoritative PNG frames
        ↓
sheets / overlays / optional GIF preview
```

`gale_slash` and `sword_idle` are the canonical proof: both use the same `GameHumanoidV2` rig profile, the same `swordsman_v1` character/equipment profile, and the same `humanoid_v2` generic Blender author. Adding `sword_idle` required only profile data; there is no `animations/sword_idle/` Python implementation.

## Architecture

```text
motion2sheet/anim2sheet/
├── __init__.py
├── cli.py
├── registry.py
├── blender_entry.py
└── common/
    ├── profile.py
    ├── equipment.py
    ├── authoring/
    │   └── humanoid.py
    ├── camera/
    ├── output/
    ├── rig/
    ├── authority/
    └── review/

profiles/anim2sheet/
├── rigs/
│   └── game_humanoid_v2.json5
├── characters/
│   └── swordsman_v1.json5
├── cameras/
│   └── fast_keypose_review.json
└── animations/
    ├── gale_slash/
    │   ├── animation.json5
    │   ├── pose_reference.json
    │   └── joint_contract.json
    └── sword_idle/
        ├── animation.json5
        ├── pose_reference.json
        └── joint_contract.json
```

There is intentionally no Python package per clip. Clip names are not implementation identities.

## Responsibility boundaries

### Package root

- `cli.py` exposes `anim2sheet build`, `anim2sheet review`, and `anim2sheet validate`.
- `registry.py` resolves reusable **authoring capabilities**, currently `humanoid_v2`; it does not register `gale_slash`, `sword_idle`, or other clips.
- `blender_entry.py` reads the resolved source spec, resolves its `authoringCapability`, loads the corresponding generic Blender author, and executes it.

### `common/profile.py`

The generic resolver loads and validates:

- the animation profile,
- linked rig profile,
- linked character/equipment profile,
- pose reference,
- joint contract,
- camera profile,
- requested execution frame/camera subsets.

An animation profile owns links to its rig, character and joint contract. CLI `--rig-profile`, `--character-profile`, and `--joint-contract` are optional overrides; `--animation` is only an optional assertion that the requested name matches the profile `action`.

### Rig profile

`profiles/anim2sheet/rigs/game_humanoid_v2.json5` owns fixed rig knowledge rather than a clip:

- bone rest pose and parent/topology assumptions,
- semantic bone/target mapping,
- coordinate and local-axis conventions,
- torso FK channels,
- deterministic arm joint-FK convention,
- leg IK chain convention,
- knee-guide targets,
- mirrored pole angles (`left=0°`, `right=180°`),
- IK constraint names and chain counts.

This information is shared by every clip authored for the same rig.

### Character / equipment profile

`profiles/anim2sheet/characters/swordsman_v1.json5` owns the reusable swordsman construction:

- proxy body materials and dimensions,
- review connectors,
- sword controller, grip and blade dimensions,
- sword materials,
- reference guide names,
- two-hand binding (`leftWrist` primary, `rightWrist` secondary),
- weapon local axis, grip-span minimum and tip distance,
- meshes visible in skeleton review.

Therefore idle, slash, and future clips for this same swordsman reuse the same character/equipment data.

### Generic Humanoid Author

`common/authoring/humanoid.py` consumes the resolved rig, character/equipment, pose, and joint-contract data. It does not branch on the animation name.

For the current `GameHumanoidV2` + swordsman contract it performs:

- torso/body FK from profile-defined channels,
- optional root/body/leg overrides supplied by clip data,
- deterministic elbow/wrist-driven arm FK,
- profile-configured leg IK and knee poles,
- profile-configured two-hand equipment binding,
- deterministic keyframe authoring,
- `source.blend` save and motion diagnostics.

The same author is used for both canonical clips.

## Canonical clips

### Gale Slash

`profiles/anim2sheet/animations/gale_slash/**` remains the full F1-F16 authoritative clip data. The architecture refactor does not change the accepted authored pose values.

The canonical Gale review still uses:

- deterministic joint-FK arms,
- explicit knee-guide leg IK,
- `front_final` and `side_diag`,
- saved-`source.blend` reopen verification,
- proxy/joint authority checks,
- Gale-specific semantic regression checks.

### Sword Idle

`profiles/anim2sheet/animations/sword_idle/**` is the proof that a second clip needs no Python implementation. It has four subtle guard-idle frames and reuses exactly:

- `game_humanoid_v2.json5`,
- `swordsman_v1.json5`,
- `humanoid_v2` generic authoring capability,
- common camera/render/output/authority/review pipeline.

It produces the same artifact classes as Gale Slash: `source.blend`, PNG frames, object/skeleton sheets, overlays, diagnostics, and GIF previews when enabled.

## Public CLI

The profile is the main animation input:

```bash
anim2sheet review \
  --profile profiles/anim2sheet/animations/gale_slash/animation.json5 \
  --camera-profile profiles/anim2sheet/cameras/fast_keypose_review.json \
  --gif \
  --output build/anim/gale_slash
```

The same command for Idle changes only profile/output data:

```bash
anim2sheet review \
  --profile profiles/anim2sheet/animations/sword_idle/animation.json5 \
  --camera-profile profiles/anim2sheet/cameras/fast_keypose_review.json \
  --gif \
  --output build/anim/sword_idle
```

`--frames` selects an execution/debug subset and never mutates the authoritative contract. `--cameras` selects a valid camera subset. Optional rig/character/contract flags override links in the animation profile without changing the generic authoring path.

## Solver and authority model

### Deterministic arm FK

The joint contract provides elbow and wrist world positions. Shoulder positions derive from the evaluated torso/clavicle hierarchy. Upper-arm and forearm segments are solved deterministically from profile-mapped bones and pose fields; endpoint IK is not used to choose elbow topology.

### Leg IK and knee authority

The rig profile defines both leg IK chains, ankle targets, knee guides, constraint names, and mirrored pole angles. `leg_ik_debug.json` verifies the evaluated knee bend lies in the same bend-plane half-space as its authored guide.

### Saved-blend authority

`source.blend` remains the authoritative Blender state. The review pipeline reopens the saved file and verifies joint persistence plus proxy/bone consistency. PNGs and authority diagnostics remain the regression authority; GIF is presentation-only.

## Multi-camera review and output

Camera definitions remain generic data under `profiles/anim2sheet/cameras/**`. The canonical reviews use `front_final` and `side_diag`.

A review artifact is self-describing and can contain:

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
preview.gif                 # optional Python packaging
cameras/
  front_final/
    frames/*.png
    object_keyposes.png
    skeleton_keyposes.png
    object_skeleton_overlay.png
    preview.gif             # optional
  side_diag/
    ...
```

GIF encoding happens only in Python under `common/output/` after authoritative PNG rendering. Blender never encodes GIF and GIF is not an authority input.

## Adding another clip for this rig/character

For another swordsman clip such as `walk`, add only data:

```text
profiles/anim2sheet/animations/walk/
├── animation.json5
├── pose_reference.json
└── joint_contract.json
```

Point `animation.json5` at the existing rig and character profiles. Do **not** add a clip-specific author, solver, registry entry, or `if animation == ...` branch.

A new Python authoring capability is justified only when the actual reusable authoring model changes, not when a new motion clip is added.

## Central affected CI

Anim2sheet uses the repository's central affected graph:

- `anim-common` owns reusable `common/**`, camera profiles, rig profiles, and character/equipment profiles.
- `anim-core` owns the public CLI, capability registry, and Blender bootstrap.
- `anim-gale-slash` owns only Gale Slash profile data.
- `anim-sword-idle` owns only Sword Idle profile data.

A common rig/character/camera change therefore runs both clip targets. A change limited to `profiles/anim2sheet/animations/sword_idle/**` runs Idle targets without pulling Gale E2E; the inverse holds for Gale profile-only changes. VFX changes do not pull anim E2E.

Canonical automatic CI runs both registered proof clips through the same public CLI and generic humanoid author. Gale keeps its full F1-F16 semantic regression gate; Idle proves profile-only generation and common saved-blend/proxy authority.

Push to `master` and central `workflow_dispatch` retain full-repository CI behavior.

## Manual remote review

`.github/workflows/anim2sheet-debug.yml` is a thin `workflow_dispatch` adapter for public `anim2sheet review`. Its inputs mirror the CLI: profile, optional action assertion, optional rig/character/contract overrides, camera profile, frame/camera subsets, GIF flag, Blender executable, and output path. The YAML contains no animation or solver logic.

## Tests

Tests remain organized by responsibility:

```text
tests/anim2sheet/
├── common/
│   └── authority/
├── cli/
└── animations/
    ├── gale_slash/
    │   ├── unit/
    │   └── e2e/
    └── sword_idle/
        └── unit/
```

Common tests prove rig/character ownership and the absence of clip-specific Python authors. CLI tests prove both profiles resolve to the same generic authoring stack. A generic E2E verifier checks self-describing profile-driven artifacts, while the saved-blend/proxy authority verifier runs for both clips.

Default local `pytest` discovery includes `tests/anim2sheet`.

## Scope

This profile-driven layer is intentionally limited to the current humanoid/swordsman contract. It does not attempt to pre-design quadruped, facial, cloth, death, or hurt frameworks. Gale Slash visual polish is a separate task and is not part of this architecture refactor.
