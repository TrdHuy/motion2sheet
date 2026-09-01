# Motion animation JSON round-trip POC

This POC defines a **source-authority** text representation for skeleton + sampled animation. It is intentionally independent from Anim2Sheet, GameHumanoidV2, proportion retargeting, projected skeleton output, character/equipment data, meshes, skinning, materials and textures.

## Pipeline

```text
Mixamo FBX
  -> export-animation-json
  -> rig.json + animation.json
  -> reconstruct-animation (JSON only)
       -> reconstructed.blend
       -> generic Blender FBX container
       -> deterministic FBX inverse transform-stack encoder
       -> reconstructed.fbx
  -> clean Blender re-import
  -> verify-animation-roundtrip
  -> numerical + deterministic visual proof
```

`motion2sheet export-animation-json sample/walk_mixamo.fbx --output build/motion_roundtrip/walk_mixamo`

`motion2sheet reconstruct-animation --rig build/motion_roundtrip/walk_mixamo/rig.json --animation build/motion_roundtrip/walk_mixamo/animation.json --output build/motion_roundtrip/walk_mixamo/reconstructed.blend`

## Canonical motion authority

`animation.frames[].bones` is the **only normative motion authority**.

Each frame stores every source bone as translation + normalized quaternion `[w,x,y,z]` + scale using Blender `PoseBone.matrix_basis`. This is the pose-local delta relative to the source bone rest basis. It is not a normalized humanoid pose and it does not rename source bones. FPS and the inclusive integer action range are preserved from the imported source scene.

Canonical `animation.json` is not allowed to contain independent FBX animation curve values. In particular `sourceFormat.fbx.curves` is rejected by schema validation. Therefore conflicting states such as "frames say pose A, FBX curves say pose B" cannot exist in the canonical contract.

## Rig/rest authority

`rig.json` stores each rest bone transform **relative to its parent rest matrix**. Root bones are relative to armature object space. It also stores explicit Blender edit-bone head/tail/roll geometry required to reconstruct the same rest basis.

Before serialization each matrix is decomposed to TRS and immediately recomposed. If the matrix residual exceeds the strict tolerance, extraction fails rather than approximating shear/non-TRS state.

Canonical JSON uses stable key ordering, normalized quaternion sign, finite numbers, deterministic source filename/SHA256 provenance and no timestamps, UUIDs, absolute machine paths or opaque binary data.

## FBX encoding metadata

FBX needs additional **static encoding metadata** because FBX local T/R/S channels are not the same parameterization as Blender `PoseBone.matrix_basis`.

The canonical documents may retain format metadata required to encode the canonical frames back into FBX, including:

- FBX version and GlobalSettings axis/unit/time settings;
- per-bone `PreRotation`, `PostRotation`, `RotationOrder`;
- rotation/scaling offsets and pivots;
- `InheritType` and static local defaults;
- static matrices captured from Blender's FBX importer that map FBX node transforms to Blender pose-bone basis;
- AnimationStack/AnimationLayer identity, effective stack timing and one KTime sample per canonical integer frame.

These values describe **how to encode/decode motion**, not another motion sequence.

For every canonical frame the FBX inverse encoder removes the static importer/transform-stack factors from `matrix_basis`, deterministically decomposes the remaining transform into FBX `Lcl Translation`, Euler `Lcl Rotation` in the source `RotationOrder`, and `Lcl Scaling`, then verifies that recomposition matches the canonical matrix within tolerance. Euler continuity uses the previous derived Euler as a deterministic compatibility branch. Unsupported shear, reflection/negative scale, missing adapters, or unexpected varying container animation fails closed.

The generic Blender-exported FBX is only a structural container. All canonical bone T/R/S curves are derived from `animation.frames`. Any other generated container curve is permitted only when constant and is retimed to the canonical KTime range; a varying non-canonical curve fails closed so the container cannot become a second motion authority.

## Diagnostic oracle

Original source FBX curve values may be written to:

`diagnostics/original_fbx_curves.json`

Derived encoder values may be written to:

`diagnostics/derived_fbx_curves.json`

These are diagnostic artifacts only. They are not canonical input and the reconstructor does not read them. Numerical curve equality is not an acceptance requirement because multiple Euler branches can evaluate to the same pose.

## A/B/C proof

The dedicated real-Mixamo workflow records three cases:

- **A** — canonical frames -> reconstructed Blend;
- **B** — canonical frames -> generic Blender FBX export -> clean re-import;
- **C** — canonical frames + static FBX metadata -> inverse encoder -> clean re-import.

Case B demonstrates why generic Blender FBX export is insufficient for strict source-state preservation: Blender may refactor the source FBX bone basis/`PreRotation` representation even when the evaluated pose looks similar. Case C must recover local, rest and world-space fidelity without using original source curve values.

## POC v1 fidelity boundary

The acceptance promise is equivalent state at every integer source frame. FCurve tangents and continuous subframe interpolation are deliberately not authority in v1. No frame reduction or terminal-loop synthesis occurs.

Verification checks source vs JSON-only reconstructed Blend and source vs re-imported reconstructed FBX for bone names/parents/rest state, armature transform, FPS/range, all-frame local TRS and evaluated world matrices/head/tail positions. A shared deterministic skeleton renderer produces source/reconstructed/diff/overlay sheets.

Semantic humanoid annotations may be added later only as removable metadata. Reconstruction must remain possible after deleting all semantic annotations.
