# Anim2Sheet — Profile Contract v2

Anim2Sheet is a Blender-native, profile-driven character animation renderer. Profile Contract v2 removes the old split motion authority and makes `motion.json` the canonical target for authored data and future FBX/BVH/Mixamo importers.

## Runtime dependency graph

```text
                       animation.json5
                       /             \
                      v               v
                motion.json      character profile
                     |                |
                     | rigProfile     | rigProfile
                     +-------+  +-----+
                             v  v
                         rig profile

camera profile -----------------------> render
```

The runtime resolves both Motion and Character to a Rig and rejects the request unless they identify the same Rig Contract. Camera remains independent.

## Ownership

| Domain | Owns | Does not own |
| --- | --- | --- |
| Rig | skeleton identity, rest pose, hierarchy/topology, semantic targets, axes, constraints, IK/FK solver conventions, capability motion-channel contract | character appearance, equipment, frames, camera, render/package settings |
| Character | identity, `rigProfile`, body/model/proxy, materials, equipment, attachments/binding, character review visualization | animation motion |
| Motion | identity, target `rigProfile`, FPS, frame count, coordinate/space, one final frame state, optional non-authoritative provenance | character appearance, camera, render settings, override layers |
| Animation | action semantics, `motionProfile`, default Character, loop/playback, phases, render/package composition | Rig link, FPS, frame count, duplicate skeletal motion |
| Camera | camera identity, definitions, projection, transforms, scale/lens, roles/default review cameras | Motion/Character/Rig ownership |

Stable machine identity uses `schema`, `version`, and `id` on Rig, Character, Motion, Animation, and Camera profiles. `action` is playback semantics, not profile identity.

## Canonical file tree

```text
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
    │   └── motion.json
    └── sword_idle/
        ├── animation.json5
        └── motion.json
```

There is no canonical dual runtime format. Each clip has one Motion file and one Animation composition manifest.

## Motion v2: one effective state per frame

`motion.json` is the single authoritative frame-motion source. Each frame contains one explicit final state:

```json
{
  "frame": 1,
  "root": {"translation": [0.0, 0.0, -0.06]},
  "body": {"pelvisYawDeg": 0},
  "joints": {"leftElbow": [0.0, 0.0, 0.0]},
  "targets": {"leftAnkle": [0.0, 0.0, 0.0]}
}
```

The exact required semantic channels are declared by the target Rig profile's `motionContract` and validated generically. The generic profile loader does not encode left/right humanoid assumptions. `humanoid_v2` capability code interprets the channels its Rig declares.

Root translation is a proper XYZ transform. Motion has no correction/precedence layer. Equipment guide positions are not duplicate motion authority: the current swordsman's sword transform is derived deterministically from Character equipment binding plus the authored wrist joints.

Optional Motion `provenance` may describe source asset/type, source skeleton, importer version, or sampling. Provenance never participates in final pose authority.

## Runtime resolution

```text
Animation
  -> Motion -> Rig
  -> Character -> Rig
  -> validate identical Rig Contract
  -> capability registry
  -> Generic Humanoid Author
  -> apply_motion_frame(frame)
  -> source.blend
  -> authoritative PNG / diagnostics
```

The author consumes one canonical frame state. There is no staged correction precedence in the v2 runtime.

## Canonical CLI

```bash
anim2sheet review \
  --profile profiles/anim2sheet/animations/sword_idle/animation.json5 \
  --camera-profile profiles/anim2sheet/cameras/fast_keypose_review.json \
  --gif \
  --output build/anim/sword_idle
```

Optional execution/presentation controls are `--animation` (action assertion), `--character-profile` (compatible Character only), `--frames`, `--cameras`, and `--gif`. A Character override must resolve to the same Rig Contract as Motion.

Target-Rig replacement is deliberately not a render-time override. Retarget/import tools own that concern.

## Authority and regression

`source.blend`, rendered PNGs, evaluated joint/proxy diagnostics, and saved-blend reopen diagnostics remain authoritative. `front_final` remains the final presentation camera and `side_diag` remains diagnostic. GIF remains presentation-only.

Gale Slash and Sword Idle were migrated by computing each old frame's effective final root/body/leg state and authoritative arm joints, then writing that result once to Motion v2. The old split files are not runtime inputs after migration.

## Dynamic CI

A valid clip directory contains `animation.json5` + `motion.json`. CI discovers it dynamically; no workflow/manifest clip whitelist is required. Clip-only changes select only that clip E2E, while Rig/Character/Camera/common changes fan out to all discovered clips. Incomplete clip directories fail closed.

## Future importer boundary

Profile Contract v2 is the required target for future source-motion importers:

```text
FBX / BVH / Mixamo source
        |
source rig inspection
        |
semantic mapping / retarget
        |
target Rig Profile
        |
sample target motion
        |
        +--> motion.json
        +--> animation.json5
                  |
          existing compatible Character
                  |
              anim2sheet
```

An importer should not create a new Character for every animation and should not require another motion-profile redesign. Importer implementation is outside this refactor.

## Scope

This refactor does not add Mixamo conversion, new animations, visual polish, quadruped/facial/cloth systems, or broader equipment abstraction. It preserves the accepted current humanoid/swordsman behavior while making the contract single-owner and importer-ready.
