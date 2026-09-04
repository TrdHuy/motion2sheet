# Contract C v1 POC

Contract C v1 is a reusable semantic humanoid **in-place animation authority**.
One immutable `animations/<clip>/animation.json` is played on every compatible
character. Target-bone transforms created during playback are runtime data, never
per-character animation authority.

## Authority separation

| Authority | Owns |
| --- | --- |
| Game/world | Absolute X/Y position, movement speed, navigation, pathfinding, collision and gameplay displacement |
| Contract C | In-place pelvis/body articulation, semantic joint rotations, FPS, frame count and loop intent |

The strict schema remains `motion2sheet.contract-c.animation` version 1 with
canonical skeleton `humanoid_v1`. It stores:

- virtual `Root` translation and yaw tracks;
- `Hips` local/residual translation and rotation;
- rotation tracks for every other required humanoid semantic.

`Root.translation` is reserved and must remain within `1e-8` mean-leg-length
units of `[0,0,0]` on every frame. Root yaw is retained only as canonical body
orientation. It does not own world movement.

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
Run-in-place source therefore produce equivalent in-place body semantics.

Quaternions use `[w,x,y,z]`. The semantic rotation formula is
`D = inverse(Qroot) * RsourcePose * inverse(RsourceRest)`. Playback applies
`RtargetPose = Qroot * D * RtargetRest`. Tracks are normalized and use a
deterministic nearest-hemisphere continuity policy.

Contract C stores no source joint positions, bone lengths, bind matrices, local
axes or source/target bone names.

## Independent fidelity oracle

Before Contract B or source FBX files are deleted, run:

```bash
motion2sheet verify-contract-c-fidelity \
  --source-rig build/contract_c_poc/contract_b/run/rig.json \
  --source-animation build/contract_c_poc/contract_b/run/animation.json \
  --source-mapping profiles/contract_c/mixamo_humanoid_v1.json \
  --animation build/contract_c_poc/animations/run/animation.json \
  --output build/contract_c_poc/animations/run/diagnostics/source_contract_c_fidelity.json
```

The oracle evaluates Contract B hierarchy/rest/matrix-basis transforms in a
separate pure-Python numeric path. It does not call the Contract C exporter,
Blender playback, or their math helpers. It compares all frames, timing, Root
yaw, all 21 semantic rotations, Hips residual translation, left/right identity,
Root invariants and quaternion validity/continuity.

Tolerances are `1e-9` for FPS, `0.005` degrees for rotations, `1e-5` for Hips
translation and `1e-8` for Root translation.

## Character mapping and independent targets

`motion2sheet.contract-c.character-map` v1 maps all 21 non-virtual semantics to
distinct target bones. Validation fails closed for missing bones, invalid
ancestry, or left/right rest geometry inconsistent with canonical `+X`.

The primary acceptance matrix is:

| Target | Source | Purpose |
| --- | --- | --- |
| Character A | `walking_mixamo_with_skin.fbx` | Existing real baseline |
| Maria | `Maria.WProp.J.J.Ong.fbx` | Independently authored real target #1 |
| Warrok | `Warrok.W.Kurniawan.fbx` | Independently authored real target #2 |

All three rigs use the validated `mixamo_humanoid_v1` semantic naming profile,
while their model, rest rig, skin and runtime corrections remain target-specific.
The derived Character B fixture remains available as optional controlled stress
tooling but is not run or counted as independent-character acceptance.

Maria and Warrok are pinned release assets under tag `e2e_gh_action_asset`.
Exact URLs, asset IDs, SHA-256 values and byte sizes are recorded in
`tests/motion/contract_c/fixtures/release_assets.json`; CI downloads those fixed
URLs and fails closed on any hash or size mismatch. The dedicated GitHub Actions
workflow is manual-only (`workflow_dispatch`); routine PR pushes do not consume
CI capacity. Contract acceptance is run locally with the same commands and gates.

## Export and playback

Export one reusable Contract C authority from Contract B:

```bash
motion2sheet export-contract-c-animation \
  --source-rig build/contract_c_poc/contract_b/run/rig.json \
  --source-animation build/contract_c_poc/contract_b/run/animation.json \
  --mapping profiles/contract_c/mixamo_humanoid_v1.json \
  --id run --loop --output build/contract_c_poc/animations/run
```

Then render that same exact file on each target without adaptation:

```bash
motion2sheet render-contract-c-animation \
  --model build/contract_c_poc/characters/maria/model.glb \
  --character-rig build/contract_c_poc/characters/maria/rig.json \
  --skin build/contract_c_poc/characters/maria/skin.json \
  --character-mapping profiles/contract_c/mixamo_humanoid_v1.json \
  --animation build/contract_c_poc/animations/run/animation.json \
  --camera-profile profiles/cameras/front_contract_c_inplace.json5 \
  --frames all --canvas 224x224 --sheet-columns 10 --render-samples 8 --gif \
  --output build/contract_c_poc/renders/maria/run
```

The Contract C camera is fixed (`followRoot: false`) so rendering cannot conceal
locomotion drift. Each target/clip produces a real-skinned `pose_sheet.png`,
`preview.gif`, `render.json` and diagnostics directory. Reports record the same
animation SHA before and after every playback.

## Known v1 boundary

The v1 stripping policy treats planar locomotion as linear end-to-end travel.
Curved or strongly non-linear world paths can leave local residual motion and
will need a later explicit trajectory policy. Foot contact remains diagnostic;
Contract C v1 does not store source joint XYZ or apply foot IK.
