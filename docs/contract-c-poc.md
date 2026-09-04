# Contract C v1 POC

Contract C is reusable semantic humanoid motion. Its authority is one immutable
`animations/<clip>/animation.json`; target bone transforms produced while playing it
are runtime data, never a per-character animation asset.

## Authority and schema

The strict schema is `motion2sheet.contract-c.animation`, version 1, canonical
skeleton `humanoid_v1`. It stores FPS, frame count, loop intent, coordinate and
quaternion conventions, then:

- virtual `Root`: translation and rotation tracks;
- `Hips`: rotation and optional translation tracks;
- every other required semantic joint: rotation track only.

Translation is dimensionless in mean-leg-length units. No source joint position,
bone length, bind matrix, source local axis, or actual source/target bone name is
stored. Required mapped semantics are Hips, Spine, Chest, Neck, Head, and left/right
Shoulder, UpperArm, LowerArm, Hand, UpperLeg, LowerLeg, Foot, Toe.

Quaternions use `[w,x,y,z]`. In Blender canonical scene space the exporter computes
`D = inverse(Qroot) * RsourcePose * inverse(RsourceRest)`. Playback computes
`RtargetPose = Qroot * D * RtargetRest`. Each track is normalized and made
nearest-hemisphere sign-continuous with a deterministic tie break.

Root translation is full Hips displacement from sample zero, normalized by source
mean leg length. Root rotation is the relative Hips yaw twist. Hips translation
stores the remaining rest-relative displacement. Runtime multiplies translations by
the target mean leg length, so target proportions remain authoritative.

## Character mapping

`motion2sheet.contract-c.character-map` version 1 maps all 21 non-virtual semantics
to distinct target bones. Validation fails closed for missing bones or an invalid
ancestor path. Unmapped twist/finger/helper bones are diagnostic-only; bridge bones
on a required path receive deterministic rest-chain interpolation.

The checked-in examples are `profiles/contract_c/mixamo_humanoid_v1.json` and
`profiles/contract_c/derived_humanoid_v1.json`.

## Commands

Start from the requested PR #12 commit without touching its branch:

```bash
git fetch origin
git switch -c feature/contract-c-poc 48fb394770369a9f6b540d8446fb2b337d7055b1
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Create a Contract B adapter input, then export the reusable authority:

```bash
/usr/bin/blender --background --factory-startup --python-exit-code 1 \
  --python motion2sheet/motion/model_render/blender_prepare_motion_source.py -- \
  --input /home/huy/Downloads/run-without-skin-not-inplace.fbx \
  --output build/contract_c_poc/intermediate/run-normalized.fbx \
  --report build/contract_c_poc/diagnostics/run-normalization.json
.venv/bin/motion2sheet export-animation-json \
  build/contract_c_poc/intermediate/run-normalized.fbx \
  --output build/contract_c_poc/contract_b/run --blender /usr/bin/blender
.venv/bin/motion2sheet export-contract-c-animation \
  --source-rig build/contract_c_poc/contract_b/run/rig.json \
  --source-animation build/contract_c_poc/contract_b/run/animation.json \
  --mapping profiles/contract_c/mixamo_humanoid_v1.json --id run --loop \
  --output build/contract_c_poc/animations/run --blender /usr/bin/blender
```

Render that exact file on a target; use the other mapping and character directory
for Character B without changing `--animation`:

```bash
.venv/bin/motion2sheet render-contract-c-animation \
  --model build/contract_c_poc/characters/character-a/model.glb \
  --character-rig build/contract_c_poc/characters/character-a/rig.json \
  --skin build/contract_c_poc/characters/character-a/skin.json \
  --character-mapping profiles/contract_c/mixamo_humanoid_v1.json \
  --animation build/contract_c_poc/animations/run/animation.json \
  --camera-profile profiles/cameras/front_final.json5 --canvas 160x160 \
  --sheet-columns 5 --render-samples 8 --gif \
  --output build/contract_c_poc/renders/character-a/run --blender /usr/bin/blender
```

Verify every artifact, both pre/post playback SHAs, real mesh identity, semantic
mapping, left/right identity, quaternion playback, and root-motion classification:

```bash
.venv/bin/python tests/motion/contract_c/verify_local_acceptance.py
```

The POC reuses PR #12 character export, GLB/skin authorities and reconstruction,
armature reconstruction, camera, PNG/sheet/GIF composition, canonical rest capture,
and root-motion/reporting patterns. Contract B is only an exporter adapter; final
Contract C playback reads no FBX and no source rig.

## POC boundary

Character B is deliberately derived from the available real skinned character by a
deterministic non-uniform mesh/rest-rig transform, upper-arm roll changes, and bone
renaming. This proves phase-1 variation in proportions, rest basis, and naming. It is
not a second independently authored model; that remains the final acceptance step
when such an asset is available. Foot contact is reported without IK and is not a
gate; source world-space XYZ is never introduced as a workaround.
