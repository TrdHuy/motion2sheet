# Motion animation JSON round-trip POC

This POC defines a **source-authority** text representation for skeleton + sampled animation. It is intentionally independent from Anim2Sheet, GameHumanoidV2, proportion retargeting, projected skeleton output, character/equipment data, meshes, skinning, materials and textures.

## Pipeline

```text
Mixamo FBX
  -> export-animation-json
  -> rig.json + animation.json
  -> reconstruct-animation (JSON only)
  -> reconstructed.blend + reconstructed.fbx
  -> verify-animation-roundtrip
  -> numerical + FBX re-import + deterministic visual proof
```

`motion2sheet export-animation-json sample/walk_mixamo.fbx --output build/motion_roundtrip/walk_mixamo`

`motion2sheet reconstruct-animation --rig build/motion_roundtrip/walk_mixamo/rig.json --animation build/motion_roundtrip/walk_mixamo/animation.json --output build/motion_roundtrip/walk_mixamo/reconstructed.blend`

## Transform authority

`rig.json` stores each rest bone transform **relative to its parent rest matrix**. Root bones are relative to armature object space. A transform is explicit translation + normalized quaternion `[w,x,y,z]` + scale, plus bone length and structural Blender bone properties required by the POC.

`animation.json` stores every bone at every integer source frame using Blender `PoseBone.matrix_basis`. This is the pose-local delta relative to the bone rest basis. It is not a normalized humanoid pose and it does not rename source bones. FPS and the inclusive integer action range are preserved from the imported source scene.

Before serialization each matrix is decomposed to TRS and immediately recomposed. If the matrix residual exceeds the strict tolerance, extraction fails rather than approximating shear/non-TRS state.

Canonical JSON uses stable key ordering, normalized quaternion sign, finite numbers, deterministic source filename/SHA256 provenance and no timestamps, UUIDs, absolute machine paths or opaque binary data.

## POC v1 fidelity boundary

The acceptance promise is exact-equivalent state at every integer source frame. FCurve tangents and continuous subframe interpolation are deliberately not authority in v1. No frame reduction or terminal-loop synthesis occurs.

Verification checks source vs JSON-only reconstructed Blend and source vs re-imported reconstructed FBX for bone names/parents/rest state, armature transform, FPS/range, all-frame local TRS and evaluated world matrices/head/tail positions. A shared deterministic skeleton renderer produces source/reconstructed/diff/overlay sheets.

Semantic humanoid annotations may be added later only as removable metadata. Reconstruction must remain possible after deleting all semantic annotations.
