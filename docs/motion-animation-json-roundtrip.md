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
  -> numerical + selectable visual proof
```

`motion2sheet export-animation-json sample/walk_mixamo.fbx --output build/motion_roundtrip/walk_mixamo`

`motion2sheet reconstruct-animation --rig build/motion_roundtrip/walk_mixamo/rig.json --animation build/motion_roundtrip/walk_mixamo/animation.json --output build/motion_roundtrip/walk_mixamo/reconstructed.blend`

## Canonical motion authority

`animation.frames[].bones` is the **only normative motion authority**.

Each frame stores every source bone as translation + normalized quaternion `[w,x,y,z]` + scale using Blender `PoseBone.matrix_basis`. This is the pose-local delta relative to the source bone rest basis. It is not a normalized humanoid pose and it does not rename source bones. FPS and the inclusive integer action range are preserved from the imported source scene.

Canonical `animation.json` is not allowed to contain independent FBX animation curve values. In particular `sourceFormat.fbx.curves` is rejected by schema validation. Therefore conflicting states such as "frames say pose A, FBX curves say pose B" cannot exist in the canonical contract.

## Rig/rest authority

`rig.editGeometrySpace = "armature-local"` and `rig.restAuthority = "editGeometry"` explicitly make each bone's `editGeometry {head, tail, roll}` the **single canonical rest authority**. The reconstructor creates Blender EditBones only from this representation.

The per-bone parent-relative `rest` TRS and `length` fields remain in `rig.json` as derived inspection/verifier caches; they are not independent authorities. Schema validation reconstructs the bone basis from canonical head/tail/roll using Blender-compatible `vec_roll_to_mat3` semantics and rejects the document if `rest` or `length` conflicts with `editGeometry`. A dedicated cache-consistency tolerance accounts only for Blender float32 FBX/EditBone conversion noise; it does not change any round-trip fidelity gate.

Before serialization each captured matrix is decomposed to TRS and immediately recomposed. If the matrix residual exceeds the strict transform tolerance, extraction fails rather than approximating shear/non-TRS state.

Canonical JSON uses stable key ordering, normalized quaternion sign, finite numbers, deterministic source filename/SHA256 provenance and no timestamps, UUIDs, absolute machine paths or opaque binary data.

## Fail-closed canonical schema

Canonical `rig.json` and `animation.json` are closed contracts rather than extensible property bags. Every fixed-shape object has an exact allowed-field set. Unknown fields fail validation rather than being ignored, and missing required fields also fail validation.

JSON scalar types are strict: integer fields reject booleans and float equivalents, while boolean fields reject numeric `0/1`.

## FBX encoding metadata

FBX needs additional **static encoding metadata** because FBX local T/R/S channels are not the same parameterization as Blender `PoseBone.matrix_basis`.

The canonical documents may retain format metadata required to encode the canonical frames back into FBX, including FBX version/GlobalSettings, per-bone transform-stack metadata, static Blender importer adapter matrices, AnimationStack/Layer identity and effective KTime sampling. These values describe **how to encode/decode motion**, not another motion sequence.

For every canonical frame the FBX inverse encoder removes the static importer/transform-stack factors from `matrix_basis`, deterministically decomposes the remaining transform into FBX `Lcl Translation`, Euler `Lcl Rotation` in the source `RotationOrder`, and `Lcl Scaling`, then verifies that recomposition matches the canonical matrix within tolerance. Unsupported shear, reflection/negative scale, missing adapters, or unexpected varying container animation fails closed.

## Diagnostic oracle

Original source FBX curve values may be written to `diagnostics/original_fbx_curves.json`; derived encoder values may be written to `diagnostics/derived_fbx_curves.json`. These are diagnostics only and never canonical reconstruction inputs.

## Visual proof renderers

`verify-animation-roundtrip` supports two visual proof renderers using the same Blender-evaluated source/reconstructed world-pose data.

### Pillow (default)

```bash
motion2sheet verify-animation-roundtrip \
  --source sample/walk_mixamo.fbx \
  --rig build/motion_roundtrip/walk_mixamo/rig.json \
  --animation build/motion_roundtrip/walk_mixamo/animation.json \
  --blend build/motion_roundtrip/walk_mixamo/reconstructed.blend \
  --fbx build/motion_roundtrip/walk_mixamo/reconstructed.fbx \
  --visual-renderer pillow \
  --output build/motion_roundtrip/walk_mixamo
```

`pillow` keeps the existing deterministic skeleton renderer. It projects Blender-evaluated world bone head/tail positions to a canonical 256x256 grid and rasterizes them with Pillow. This remains the default acceptance path.

### Blender native

```bash
motion2sheet verify-animation-roundtrip \
  --source sample/walk_mixamo.fbx \
  --rig build/motion_roundtrip/walk_mixamo/rig.json \
  --animation build/motion_roundtrip/walk_mixamo/animation.json \
  --blend build/motion_roundtrip/walk_mixamo/reconstructed.blend \
  --fbx build/motion_roundtrip/walk_mixamo/reconstructed.fbx \
  --visual-renderer blender \
  --output build/motion_roundtrip/walk_mixamo/blender_native
```

`blender` creates the source and reconstructed skeleton sheet geometry inside Blender and renders both full sheets with an orthographic camera using `BLENDER_EEVEE_NEXT`. World-pose projection is snapped to the declared 256x256 raster grid before geometry creation, matching the visual proof's resolution semantics and preventing valid sub-pixel numeric residuals from becoming an implicit new fidelity tolerance. Pillow does **not** rasterize the source/reconstructed proof sheets in this mode; it is used afterwards only for pixel metrics and diagnostic diff/overlay images.

Both modes emit:

```text
visual/
├── source_sheet.png
├── reconstructed_sheet.png
├── diff_sheet.png
└── overlay_sheet.png
```

The dedicated real-Mixamo workflow exercises both modes. On the current proof both report `32` frames, `0` changed pixels and max channel delta `0`.

## A/B/C proof

The dedicated real-Mixamo workflow records three cases:

- **A** — canonical frames -> reconstructed Blend;
- **B** — canonical frames -> generic Blender FBX export -> clean re-import;
- **C** — canonical frames + static FBX metadata -> inverse encoder -> clean re-import.

Case B demonstrates why generic Blender FBX export is insufficient for strict source-state preservation. Case C recovers local/rest/world-space fidelity without using original source curve values.

## POC v1 fidelity boundary

The acceptance promise is equivalent state at every integer source frame. FCurve tangents and continuous subframe interpolation are deliberately not authority in v1. No frame reduction or terminal-loop synthesis occurs.

Verification checks source vs JSON-only reconstructed Blend and source vs re-imported reconstructed FBX for bone names/parents/rest state, armature transform, FPS/range, all-frame local TRS and evaluated world matrices/head/tail positions. Visual proof can use the deterministic Pillow skeleton renderer or the optional Blender-native Eevee skeleton-sheet renderer.

Semantic humanoid annotations may be added later only as removable metadata. Reconstruction must remain possible after deleting all semantic annotations.
