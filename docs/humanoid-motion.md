# Humanoid Motion v1

Humanoid Motion v1 is a reusable semantic humanoid **in-place animation authority**.
One immutable `animations/<clip>/animation.json` is played on every compatible
character. Target-bone transforms created during playback are runtime data, never
per-character animation authority.

## Authority separation

| Authority | Owns |
| --- | --- |
| Character/model/rig/skin | Geometry, material, bind/rest skeleton, bone proportions, skin weights and appearance |
| Humanoid Motion | Semantic joint rotations, local Hips articulation, vertical Hips bounce, cyclic/local Hips sway, canonical body yaw, timing and loop intent |
| Game/world | Absolute X/Y position, movement speed, navigation, pathfinding, collision and gameplay displacement |

The strict schema is `motion2sheet.humanoid-motion.animation` version 1 with
canonical skeleton `humanoid_v1`. It stores:

- `durationSeconds` as the explicit action timing authority;
- `fps` and `frameCount` as the endpoint-inclusive sampling representation;
- virtual `Root` translation and yaw tracks;
- `Hips` local/residual translation and rotation;
- rotation tracks for every other required humanoid semantic.

`Root.translation` is reserved and must remain within `1e-8` mean-leg-length
units of `[0,0,0]` on every frame. Root yaw is retained only as canonical body
orientation. It does not own world movement.

## Timing authority

`export-animation-json` captures `durationSeconds` from source-native timing,
independently of Blender's imported/sample FPS:

```text
FBX: durationSeconds = (AnimationStack.LocalStop - AnimationStack.LocalStart) / KTimeTicksPerSecond
BVH: durationSeconds = (Frames - 1) * Frame Time
```

FBX `LocalStart`, `LocalStop`, `ReferenceStart`, `ReferenceStop`, and animation
curve `KeyTime` values are integer KTime ticks, not frame indices. The timebase is
resolved from the FBX version and `FBXHeaderExtension/OtherFlags/TCDefinition`:
legacy KTime is `46186158000` ticks/second and the opt-in v8 definition is
`141120000` ticks/second. `TimeMode`/`CustomFrameRate` declares the sample rate;
it never defines duration. Stack spans, curve endpoints, every sample time, and
the imported representation must agree or export fails closed.

Current Source Animation exports retain the resolved FBX timebase or BVH
`Frames`/`Frame Time` metadata. The validator accepts older v1 files without the
additive `durationSeconds` field for round-trip compatibility, but current
Humanoid Motion export requires duration and asks callers to re-export legacy
source authority when it is absent.

`export-humanoid-animation` requires that Source Animation field and copies it
unchanged into Humanoid Motion. It does not recompute duration at the Humanoid
boundary. The representation invariant is:

```text
(frameCount - 1) / fps == durationSeconds
```

within `1e-6` seconds. This formula is a consistency check only; it is **not** the
source duration authority. Changing imported/sample FPS while native timing stays
unchanged fails closed instead of silently speeding up or slowing down the action.

## In-place locomotion canonicalization

Translations are dimensionless mean-leg-length units. For source Hips
rest-relative position `P_i`, frame fraction `u_i`, and relative Hips yaw `Q_i`,
the v1 exporter applies `linear-endpoint-planar-detrend-v1`:

```text
planarTravel = [P_last.x - P_first.x, P_last.y - P_first.y, 0]
Root.translation_i = [0, 0, 0]
Hips.translation_i = inverse(Q_i) * (P_i - u_i * planarTravel)
```

This strips a source Run's forward travel while retaining cyclic lateral sway,
vertical pelvis bounce and other local Hips motion. A moving Run and its matching
Run-in-place source therefore produce equivalent in-place body semantics within
the acceptance tolerance.

Quaternions use `[w,x,y,z]`. The semantic rotation formula is
`D = inverse(Qroot) * RsourcePose * inverse(RsourceRest)`. Playback applies
`RtargetPose = Qroot * D * RtargetRest`. Tracks are normalized and use a
deterministic nearest-hemisphere continuity policy.

Humanoid Motion stores no source joint positions, bone lengths, bind matrices,
local axes, source/target bone names, FBX paths or model paths.

## Independent fidelity oracle

Before Motion JSON or source FBX files are deleted, run:

```bash
motion2sheet verify-humanoid-animation-fidelity \
  --source-rig build/motion/humanoid-motion/motion_json/run/rig.json \
  --source-animation build/motion/humanoid-motion/motion_json/run/animation.json \
  --source-mapping profiles/humanoid_motion/mixamo_humanoid_v1.json \
  --animation build/motion/humanoid-motion/animations/run/animation.json \
  --output build/motion/humanoid-motion/animations/run/diagnostics/source_humanoid_motion_fidelity.json
```

The oracle evaluates the Source Rig + Source Animation hierarchy/rest/matrix-basis
transforms in a separate pure-Python numeric path. It does not call the Humanoid
Motion exporter, Blender playback, or their math helpers. It compares all samples,
the exact copied `durationSeconds`, FPS/frame count, Root yaw, all 21 semantic
rotations, Hips residual translation, left/right identity, Root invariants and
quaternion validity/continuity.

Tolerances remain `1e-9` for FPS, `1e-6` seconds for the explicit duration
invariant, `0.005` degrees for rotations, `1e-5` for Hips translation and `1e-8`
for Root translation.

## Character mapping and independent targets

`motion2sheet.humanoid-motion.character-map` v1 maps all 21 non-virtual semantics
to distinct target bones. Validation fails closed for missing bones, invalid
ancestry, or left/right rest geometry inconsistent with canonical `+X`.

The canonical independent acceptance matrix is:

| Target | Source | Purpose |
| --- | --- | --- |
| Character A | `walking_mixamo_with_skin.fbx` | Existing real baseline |
| Maria | `Maria.WProp.J.J.Ong.fbx` | Independently authored real target #1 |
| Warrok | `Warrok.W.Kurniawan.fbx` | Independently authored real target #2 |

All three rigs use the validated `mixamo_humanoid_v1` semantic naming profile,
while their model, rest rig, skin and runtime corrections remain target-specific.
Derived Character B is not part of acceptance and must never be counted as an
independent target.

Maria and Warrok are pinned release assets under tag `e2e_gh_action_asset`.
Exact URLs, asset IDs, SHA-256 values and byte sizes are recorded in
`tests/motion/humanoid_motion/fixtures/release_assets.json`; CI downloads those
fixed URLs and fails closed on any hash or size mismatch.

## Canonical CI proof

PR13 has one dedicated workflow:

```text
.github/workflows/humanoid-motion.yml
```

and one orchestration directory:

```text
tests/motion/humanoid_motion/ci/
  run_unit.sh
  run_timing.sh
  run_smoke.sh
  run_full.sh
  run_e2e.sh
  verify_acceptance.py
```

Pull-request changes use `smoke` by default. `workflow_dispatch` supports explicit
`smoke` and `full` modes. Both modes run full unit/data validation, full
Source -> Humanoid fidelity, deterministic serialization, Root/L/R checks,
native timing regressions and Run/Run-in-place equivalence.

Only the raster proof is sparse:

| Mode | Visual cells | Maximum raster samples |
| --- | ---: | ---: |
| Smoke | Character A: Idle/Run/Run-inplace; Maria: Run; Warrok: Run | 40 |
| Full | Character A/Maria/Warrok × Idle/Run/Run-inplace | 72 |

Each cell renders at most eight deterministic, evenly distributed canonical
samples, including first and last. CI uses `160x160`, one render sample and an
8 FPS preview GIF. This is presentation policy only; the canonical Humanoid
Motion `fps`, `frameCount`, `durationSeconds` and serialized SHA stay unchanged.

The standalone `Motion JSON Round-trip POC` workflow remains available only by
manual dispatch for its independent Source Motion commands. Legacy direct Source
Motion cross-animation/model-render POC workflows are not PR13 portability gates.

## Export and playback

Export one reusable Humanoid Motion authority from Motion JSON:

```bash
motion2sheet export-humanoid-animation \
  --source-rig build/motion/humanoid-motion/motion_json/run/rig.json \
  --source-animation build/motion/humanoid-motion/motion_json/run/animation.json \
  --mapping profiles/humanoid_motion/mixamo_humanoid_v1.json \
  --id run --loop --output build/motion/humanoid-motion/animations/run
```

Then render that same exact file on each target without adaptation. A lightweight
CI-style presentation render is:

```bash
motion2sheet render-humanoid-animation \
  --model build/motion/humanoid-motion/characters/maria/model.glb \
  --character-rig build/motion/humanoid-motion/characters/maria/rig.json \
  --skin build/motion/humanoid-motion/characters/maria/skin.json \
  --character-mapping profiles/humanoid_motion/mixamo_humanoid_v1.json \
  --animation build/motion/humanoid-motion/animations/run/animation.json \
  --camera-profile profiles/cameras/front_humanoid_motion.json5 \
  --sample-count 8 \
  --output-fps 8 \
  --canvas 160x160 \
  --sheet-columns 8 \
  --render-samples 1 \
  --gif \
  --output build/motion/humanoid-motion/renders/maria/run
```

`--sample-count N` selects at most N evenly distributed canonical sample indices.
It is mutually exclusive with explicit `--frames`. `--output-fps` controls only
presentation/GIF playback speed. When omitted, GIF output uses canonical
`animation.fps` for backward compatibility.

The render report keeps `fps` as canonical animation FPS and records presentation
speed separately as `outputFps`. `renderedSamples` records the selected canonical
sample indices. The renderer verifies the Humanoid Motion SHA before and after
playback and fails if the authority changes.

The Humanoid Motion camera is fixed (`followRoot: false`) so rendering cannot
conceal locomotion drift. Each target/clip produces a real-skinned
`pose_sheet.png`, `preview.gif`, `render.json` and diagnostics directory.

## Known v1 boundary

The v1 stripping policy treats planar locomotion as linear end-to-end travel.
Curved or strongly non-linear world paths can leave local residual motion and
will need a later explicit trajectory policy. Foot contact remains diagnostic;
Humanoid Motion v1 does not store source joint XYZ or apply foot IK.
