# Motion animation JSON round-trip POC

This POC defines a **source-authority** text representation for skeleton + sampled animation. It is intentionally independent from Anim2Sheet, GameHumanoidV2, proportion retargeting, projected skeleton output, character/equipment data, meshes, skinning, materials and textures.

## Pipeline

```text
Mixamo FBX
  -> export-animation-json
  -> rig.json + animation.json
       |-> render-animation-json (JSON only)
       |    -> pose_sheet.png
       |    -> preview.gif (optional)
       |
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

All public JSON-consuming commands validate this canonical schema before renderer/reconstructor work starts.

## FBX encoding metadata

FBX needs additional **static encoding metadata** because FBX local T/R/S channels are not the same parameterization as Blender `PoseBone.matrix_basis`.

The canonical documents may retain format metadata required to encode the canonical frames back into FBX, including FBX version/GlobalSettings, per-bone transform-stack metadata, static Blender importer adapter matrices, AnimationStack/Layer identity and effective KTime sampling. These values describe **how to encode/decode motion**, not another motion sequence.

For every canonical frame the FBX inverse encoder removes the static importer/transform-stack factors from `matrix_basis`, deterministically decomposes the remaining transform into FBX `Lcl Translation`, Euler `Lcl Rotation` in the source `RotationOrder`, and `Lcl Scaling`, then verifies that recomposition matches the canonical matrix within tolerance. Unsupported shear, reflection/negative scale, missing adapters, or unexpected varying container animation fails closed.

## Diagnostic oracle

Original source FBX curve values may be written to `diagnostics/original_fbx_curves.json`; derived encoder values may be written to `diagnostics/derived_fbx_curves.json`. These are diagnostics only and never canonical reconstruction inputs.

## Standalone JSON rendering

`render-animation-json` is a public command independent from `verify-animation-roundtrip`. Its only motion/rest inputs are canonical `rig.json + animation.json`; it has no source-FBX argument and does not read diagnostic source curves.

```bash
motion2sheet render-animation-json \
  --rig build/motion_roundtrip/walk_mixamo/rig.json \
  --animation build/motion_roundtrip/walk_mixamo/animation.json \
  --renderer blender \
  --gif \
  --output build/render/walk_mixamo
```

Renderer choices are `pillow` and `blender`. Both consume the same `visual_contract.py` projection, canonical integer pixel snap, 256x256 cell size and 8-column sheet layout. The command first validates both canonical documents, materializes world-space pose geometry from `editGeometry + animation.frames`, and then delegates rasterization to the selected renderer. It does not invoke the round-trip verifier.

The canonical output is:

```text
output/
├── pose_sheet.png
├── preview.gif      # only with --gif
└── render.json
```

Per-frame PNGs are intentionally not required because `pose_sheet.png` is the canonical visual artifact. `preview.gif` is derived by cropping the canonical 256x256 sheet cells in frame order.

The 32-frame Mixamo contract remains:

```text
32 expected frame cells
8 columns x 4 rows
256 x 256 pixels per cell
2048 x 1024 pose_sheet.png
```

The command applies the same per-cell foreground/layout gate used by round-trip visual verification. Every expected cell must contain skeleton foreground.

## Visual proof renderers

`verify-animation-roundtrip` supports two visual proof renderers using the same Blender-evaluated source/reconstructed world-pose data and the same pure visual projection/layout contract.

The shared `visual_contract.py` owns the canonical 256x256 panel, 8-column sheet layout, projection bounds/formula, integer pixel snap and sheet/panel mapping. It is pure Python and does not import Pillow or `bpy`.

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

`pillow` keeps the deterministic skeleton rasterizer and owns pixel-diff / diagnostic diff-overlay utilities. It remains the default acceptance renderer.

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

`blender` creates the source and reconstructed skeleton sheet geometry inside Blender and renders both full sheets with an orthographic camera using `BLENDER_EEVEE_NEXT`. World-pose projection is snapped to the declared 256x256 raster grid before geometry creation. Pillow does not rasterize the proof sheets in this mode; it is used afterwards only for deterministic pixel metrics, layout validation and diagnostic diff/overlay images.

For the 32-frame real Mixamo proof the native sheet contract is exactly:

```text
32 frames
8 columns x 4 rows
256 x 256 pixels per cell
2048 x 1024 pixels per sheet
```

The orthographic camera is framed from the full sheet width and verifies that render aspect ratio matches sheet aspect ratio. This prevents the previous failure mode where using sheet height as `ortho_scale` cropped a 2048x1024 image down to the centered equivalent of roughly 4x2 cells.

Visual acceptance is not based only on `source_sheet == reconstructed_sheet`. Each expected cell must independently contain skeleton foreground. The validator estimates each cell's dominant background luma and requires a minimum number of pixels with strong foreground contrast, so two identically cropped or blank Blender renders fail even if their pixel diff is zero. Regression tests explicitly cover the old centered-crop shape and Eevee's color-managed gray background.

Both verification modes emit:

```text
visual/
├── source_sheet.png
├── reconstructed_sheet.png
├── diff_sheet.png
└── overlay_sheet.png
```

The dedicated real-Mixamo workflow exercises both verification modes and asserts the native 8x4/2048x1024 contract plus all 32 occupied cells.

## Public-command workflow dispatch

`.github/workflows/motion-roundtrip.yml` exposes a `workflow_dispatch` choice input named `command`:

```text
export
reconstruct
render-pillow
render-blender
verify
full
```

Each standalone mode invokes only the selected **public** command. Required fixtures are prepared with internal implementation scripts so a reconstruct/render/verify dispatch does not silently test another public command first.

For `render-pillow` and `render-blender`, the workflow internally prepares canonical JSON and then deletes `sample/walk_mixamo.fbx` before calling `render-animation-json`. The successful render therefore proves the public command does not consult the original source file.

Artifacts are mode-scoped:

```text
motion-json-export
motion-json-reconstruct
motion-json-render-pillow
motion-json-render-blender
motion-json-verify
motion-json-full
```

Render artifacts contain `pose_sheet.png`, `render.json`, and `preview.gif`. `full` remains the pull-request acceptance path and retains deterministic extraction, reconstruction, A/B/C fidelity, Pillow verification, Blender-native source/reconstructed verification, and both standalone render commands.

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