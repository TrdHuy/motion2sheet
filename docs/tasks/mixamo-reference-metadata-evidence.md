# Task: Evidence-first metadata for Humanoid Motion references

## Context

This task is stacked on PR #17 (`data/mixamo-humanoid-reference-samples`).

Each trusted reference clip is under:

`sample/humanoid_motion/mixamo/<clip>/`

and already provides:

- `animation.json`
- `preview.gif`

One clip currently has an initial `metadata.json`, but its current shape is only a starting example.

## Goal

Create reliable metadata for every trusted Mixamo Humanoid Motion reference so future animation authoring can reuse the references with fewer trial-and-error iterations.

The workflow is strictly **evidence first**:

`animation.json + preview.gif`
`-> generate evidence`
`-> visually inspect evidence`
`-> derive metadata from that evidence`
`-> validate metadata/evidence mapping`
`-> publish a short PR review comment`

Do **not** generate metadata first and then search for evidence to justify it afterward.

## Core rule

Every important interpretive metadata field must be derived from already-generated evidence.

Evidence may come from:

- exact canonical motion measurements from `animation.json`;
- exact source frames;
- contact sheets;
- short phase GIFs;
- pelvis/hips trajectory plots;
- joint/region activity measurements;
- motion-onset measurements;
- visual inspection of `preview.gif`.

If the evidence is insufficient, omit the claim or mark it uncertain. Do not invent a confident interpretation.

## Authoritative inputs

### `animation.json`

Authoritative for measurable facts:

- frame count;
- FPS and duration;
- hips/root trajectory;
- joint rotations;
- per-region activity;
- motion peaks;
- candidate foot-contact or low-velocity windows where technically defensible;
- onset ordering between major body regions where technically defensible.

Do not estimate these facts from the GIF when they can be measured directly.

### `preview.gif`

Authoritative visual source for how the motion reads:

- overall motion meaning;
- phase readability;
- key-pose readability;
- whether a measured interpretation makes visual sense;
- ambiguity caused by camera/view/occlusion.

If quantitative evidence and visual evidence disagree, surface the discrepancy instead of hiding it.

## Required workflow per clip

### Step 1 — Generate evidence first

Before writing `metadata.json`, produce a compact evidence package for the clip.

Generate only evidence that answers a concrete review question.

Minimum evidence set:

1. **Full-motion preview**
   - existing `preview.gif`.

2. **Phase evidence**
   - contact sheet and/or short GIFs covering candidate motion phases;
   - exact frame numbers shown.

3. **Key-pose evidence**
   - compact contact sheet of candidate important frames;
   - every image labeled with exact source frame.

4. **Weight-transfer evidence**
   - relevant source frames;
   - hips/pelvis trajectory or displacement measurements;
   - lower-body/foot evidence when available;
   - do not label a planted/support foot unless evidence is strong enough.

5. **Body-mechanics evidence**
   - frames and/or measurements showing coordination between major regions;
   - for example pelvis, chest, shoulders, arms/hands, legs and head;
   - include onset/activity measurements when they are technically defensible.

Evidence is not accepted just because it was generated. The specialist must inspect it visually before using it to create metadata.

### Step 2 — Expert/AI reviews the evidence

Review the evidence as an animation specialist.

Determine only what the evidence supports, including as applicable:

- motion intent/read;
- meaningful phases;
- key poses;
- weight transfer;
- body mechanics;
- useful reference properties;
- uncertainty/warnings.

Do not infer unsupported weapons, props, exact contact semantics, emotion, attack role or support-foot role.

### Step 3 — Generate `metadata.json` from the reviewed evidence

Only after Step 1 and Step 2, generate the metadata.

Keep useful existing fields when appropriate:

- `intent`
- `style`
- `characterType`
- `breakdown`
- `notes`

Add the structured reference fields below.

### `phases`

Meaningful motion phases with exact frame ranges.

Each phase should contain:

- `name`
- `startFrame`
- `endFrame`
- concise meaning
- confidence if interpretive
- supporting frame/evidence references where useful

### `keyPoses`

Only the small set of frames materially useful for understanding or reusing the motion.

Each key pose should contain:

- `frame`
- `role`
- concise meaning
- confidence if interpretive

### `weightTransfer`

Describe how body weight appears to move only when supported by evidence.

Use measurable hips/lower-body evidence where possible.

If a supporting foot cannot be established confidently, do not state it as fact.

### `bodyMechanics`

Describe how major body regions coordinate to produce the motion.

Capture only supported information such as:

- primary driving region;
- major sequencing/lag between regions;
- pelvis path;
- torso counter-rotation;
- lower-body contribution;
- lead/support limb relationship when genuinely supported.

Do not duplicate raw quaternion tracks.

### `referenceUse`

State what this clip is useful or not useful as a future animation reference for.

Examples:

- stance/balance;
- weight shift;
- anticipation;
- impact pose;
- follow-through;
- recovery;
- locomotion cycle;
- pelvis trajectory;
- torso rotation;
- dual-limb coordination.

### Confidence and provenance

Interpretive claims should include confidence and source provenance where useful.

Deterministic facts such as FPS/frame count do not need confidence.

## Step 4 — Validate metadata against evidence

Validation must confirm at least:

- metadata parses;
- frame references exist;
- phase ranges are within `[0, frameCount - 1]`;
- phase ranges are ordered and logically valid;
- key-pose frames exist;
- evidence frames referenced by metadata exist;
- duplicated deterministic facts match `animation.json`;
- confidence values are valid;
- provenance values are from the allowed source set;
- no important interpretive field exists without corresponding evidence;
- trusted `animation.json` and `preview.gif` remain unchanged.

## Step 5 — Publish a short evidence comment for review

Use **one top-level PR comment per animation clip**.

The comment is a review UI, not a report. Keep it short.

Do not repeat long explanations already present in metadata.

Use a compact format like:

```markdown
<!-- metadata-review:action-idle-to-standing-idle -->
## `action-idle-to-standing-idle`

▶️ [Full preview]

| Metadata field | Proposed value | Evidence | Confidence |
|---|---|---|---:|
| `intent` | low staggered idle -> upright standing idle | [preview] | 97% |
| `phases` | start / dip+shift / rise+turn / settle | [phase sheet] [phase GIF] | 92% |
| `keyPoses` | f0, f7, f16, f28 | [key poses] | 95% |
| `weightTransfer` | side-biased -> centered | [weight evidence] | 86% |
| `bodyMechanics` | pelvis leads, torso follows | [mechanics evidence] | 91% |
| `referenceUse` | weight shift, stance recovery, pelvis rise | [key poses] | 93% |

⚠️ `loop=true` does not visually read as a seamless loop.

Review: [ ] accept  [ ] revise  [ ] regenerate
```

Rules for the comment:

- one row per metadata field that requires human review;
- evidence link/image corresponds directly to that field;
- keep proposed values short;
- omit deterministic fields such as FPS/frameCount unless they are relevant to a warning;
- warnings only when they materially matter;
- no essay-style explanation;
- reviewer should understand the proposal primarily by opening the evidence.

## Comment update behavior

Publication must be idempotent.

Use a stable hidden marker containing the clip identity so reruns update the existing comment instead of creating duplicates.

Do not silently overwrite an explicit reviewer correction. If regenerated analysis conflicts with reviewed feedback, surface it for review.

## Evidence publication policy

Evidence is review material and should **not be merged as binary dataset content by default**.

Preferred approach:

- generate evidence in CI/workflow;
- publish it in a review-only location with stable links during review;
- optionally keep an Actions artifact as supplemental downloadable evidence;
- link/embed evidence in the compact PR comment;
- remove temporary evidence when no longer required;
- final PR diff should not contain review-only evidence binaries unless explicitly approved.

## Implementation order

1. Inventory all trusted clips from the exact PR #17 base.
2. Implement deterministic motion measurements from `animation.json`.
3. Implement evidence generation.
4. Generate evidence for a clip.
5. Visually inspect the evidence.
6. Generate that clip's metadata from the inspected evidence.
7. Validate metadata against the evidence and canonical animation.
8. Publish/update the short PR evidence comment.
9. Repeat for the remaining clips.
10. Run focused tests on the exact final HEAD.

The implementation must prove the workflow on at least one clip before scaling to all references. Do not bulk-generate all metadata until the evidence/comment format has been visually reviewed and shown to be useful.

## Tests

Add focused tests for at least:

- metadata coverage;
- JSON structure;
- valid phase/key-pose frame references;
- valid confidence/provenance;
- metadata-to-evidence traceability;
- canonical-data consistency;
- deterministic evidence manifest/comment rendering;
- idempotent PR comment update behavior.

Do not loosen the Humanoid Motion schema or tolerances.

## Non-goals

Do not:

- modify trusted PR #17 `animation.json` files;
- modify trusted PR #17 `preview.gif` files;
- regenerate source motion;
- create evidence after metadata merely to justify an already-made conclusion;
- infer unsupported weapons/props/contact semantics;
- create a large unrelated ontology/framework;
- commit review-only evidence binaries by default;
- merge directly into `master`;
- merge or mark this PR Ready for Review without explicit user instruction.

## Acceptance criteria

The task is complete only when:

- evidence is generated before metadata for every processed clip;
- metadata is derived from inspected evidence;
- each important interpretive field maps to corresponding evidence;
- each clip has one concise, idempotently updated PR review comment;
- all trusted reference clips have consistent `metadata.json` files;
- focused tests pass on exact final HEAD;
- trusted PR #17 motion assets remain unchanged;
- review-only evidence is absent from the final merge diff unless explicitly approved;
- this PR remains stacked on `data/mixamo-humanoid-reference-samples` and is not merged or marked Ready without explicit instruction.
