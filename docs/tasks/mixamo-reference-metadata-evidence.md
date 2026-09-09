# Task: Expert-reviewed Humanoid Motion reference metadata and visual evidence

## Context

This task is stacked on PR #17 (`data/mixamo-humanoid-reference-samples`). PR #17 adds the trusted Mixamo Humanoid Motion reference set under:

`sample/humanoid_motion/mixamo/<clip>/`

Each clip already has a canonical `animation.json` and rendered `preview.gif`. One clip (`action-idle-to-standing-idle`) currently contains an initial `metadata.json` that can be used as a starting example, but this task must improve the metadata model for animation-reference use rather than merely copy that file.

The purpose of this task is to make the trusted reference set significantly more useful when authoring new Humanoid Motion animations. Metadata must help an animation expert or AI answer not only **what the clip is**, but also **how the body produces the motion, which frames matter, and what the clip is or is not a good reference for**.

## Primary goal

Create reliable, reviewable metadata for every trusted Mixamo reference clip in PR #17, with evidence that allows a human reviewer to validate each inferred field without having to read quaternion tracks manually.

The workflow must combine:

`animation.json + preview.gif -> quantitative analysis -> expert/AI interpretation -> metadata.json -> review evidence -> PR review comment`

The output is not accepted merely because JSON validates. The inferred animation meaning must be visually reviewable.

## Expert role

Treat this as an animation-analysis task first and a data-generation task second.

The expert must reason about:

- pose readability;
- anticipation, action, impact, follow-through, recovery, settle, locomotion cycle or transition phases as applicable;
- balance and weight transfer;
- planted/supporting feet where the data supports that conclusion;
- pelvis, torso, shoulder, arm and head coordination;
- lead/support limb roles;
- motion timing and change of energy;
- which portions of a reference are useful when designing a new animation;
- uncertainty when a claim cannot be established confidently from the available sources.

Do not infer weapons, contact, emotion, intent or exact support-foot semantics when the evidence does not support them.

## Authoritative inputs

For each clip, analyze both sources:

1. `animation.json`
   - authoritative for exact frame count, FPS, duration, joint tracks, root/hips motion and quantitative motion measurements;
   - use it to measure motion rather than estimating numeric facts from the GIF.

2. `preview.gif`
   - authoritative visual review source for what the motion reads like;
   - use it for intent, pose readability, phase interpretation and visual confirmation of quantitative findings.

Neither source should silently override contradictions in the other. If the canonical data and visual interpretation disagree, record that as a note or warning.

## Metadata requirements

Keep useful existing fields such as `intent`, `style`, `characterType`, `breakdown` and `notes` where appropriate, but add structured animation-reference information.

### 1. `phases`

Describe meaningful motion phases with exact frame ranges.

Example roles include, depending on the clip:

- ready / start stance;
- anticipation / load;
- strike / impact;
- follow-through;
- recovery / settle;
- locomotion contact / passing / flight;
- transition start / rise / turn / settle.

Each phase must include at least:

- `name`;
- `startFrame`;
- `endFrame`;
- concise explanation;
- confidence when the phase meaning is inferred rather than directly measurable.

Frame ranges must be within the canonical `frameCount` and should not contain unexplained gaps or overlaps.

### 2. `keyPoses`

Identify only the frames that are materially useful for understanding or reusing the motion.

Each entry should include:

- `frame`;
- `role`;
- short explanation;
- confidence when the role is interpretive.

Do not select many frames merely to make the metadata look detailed. Key poses should remain a compact summary of the clip.

### 3. `weightTransfer`

Describe how body weight appears to move over the clip when the evidence is sufficient.

Useful concepts include:

- left/right bias;
- rear/front bias;
- centered/balanced;
- side-to-side transfer;
- loading one side before an action;
- settling back to center.

Where possible, ground this interpretation in measurable hips/pelvis displacement, lower-body motion and foot-motion evidence.

If a supporting/planted foot is uncertain because of camera occlusion or insufficient data, state the uncertainty instead of presenting a guess as fact.

### 4. `bodyMechanics`

Describe how major body regions coordinate to produce the motion.

Where the data supports it, capture:

- `primaryDriver` or primary driving body region;
- ordered or overlapping motion sequence, for example pelvis -> chest -> shoulder -> arm/hand;
- pelvis path/trajectory characteristics;
- major torso counter-rotation;
- lower-body contribution;
- lead/support limb relationship;
- meaningful lag between major body regions.

The purpose is to explain **why the motion works**, not to duplicate quaternion data.

### 5. `referenceUse`

State what the clip should and should not be used as a reference for.

Example useful categories:

- stance and balance;
- weight shift;
- attack anticipation;
- impact pose;
- follow-through;
- recovery;
- guard acquisition;
- locomotion cycle;
- pelvis trajectory;
- torso rotation;
- dual-limb coordination.

Include both:

- `usefulFor`;
- `notUsefulFor` when a common but unsupported interpretation should be discouraged.

### 6. Confidence and provenance

Interpretive claims must be traceable.

For important inferred fields, include:

- confidence value or level;
- source(s), such as `animation.json`, `preview.gif`, or both;
- supporting frame numbers where applicable.

Do not add confidence to deterministic facts such as canonical FPS or frame count.

The exact JSON structure may be refined during implementation, but it must remain consistent across all reference clips and must be tested.

## Quantitative analysis before AI/expert interpretation

Do not rely on visual guessing for facts that can be measured from `animation.json`.

Implement reusable analysis for useful signals such as:

- hips/pelvis translation trajectory;
- hips and major torso rotational activity;
- per-joint or per-region rotational activity;
- hand/arm activity;
- lower-leg/foot activity;
- candidate low-velocity foot-contact windows where technically defensible;
- frames with local/major motion peaks;
- onset ordering between major regions where technically defensible.

The exact metrics can be adjusted to the canonical Humanoid Motion representation. Existing schema tolerances must not be weakened.

The metrics are evidence for interpretation, not a substitute for visual review.

## Evidence generation

Every important inferred metadata field must have corresponding review evidence.

Evidence is **review material**, not a requirement to permanently merge PNG/GIF files into the reference dataset.

Generate compact evidence per clip, including as applicable:

1. full `preview.gif` link;
2. phase evidence — contact sheet and/or short GIFs for phase ranges;
3. key-pose contact sheet with exact frame labels;
4. weight-transfer image showing relevant frames and pelvis/hips path, with supporting-foot annotations only when confidence is sufficient;
5. body-mechanics evidence showing the frames used to infer pelvis/torso/shoulder/limb ordering;
6. compact quantitative table for the measurements supporting the conclusion;
7. warnings/uncertainties when evidence is ambiguous.

Do not create decorative evidence. Every image/GIF must answer a specific review question.

## Evidence publication policy

Metadata belongs in the PR diff. Review evidence should not be merged by default.

Preferred review flow:

- workflow generates evidence files;
- publish them in a review-only location that can be embedded or linked from PR comments (for example a temporary review-evidence branch or another non-merge publication mechanism);
- post/update PR conversation comments using stable links during review;
- remove temporary review evidence when no longer needed;
- do not add evidence binaries to the final PR diff unless explicitly approved.

GitHub Actions artifacts may be kept as supplemental downloadable evidence, but do not rely on expiring artifact links as the only review path if the PR comments are expected to remain useful during the review window.

## PR review comment format

Use **one top-level review comment per animation clip**. The reviewer should not need to read the raw JSON first.

Each comment should be easy to scan and should follow this structure:

```markdown
## Metadata review — `<clip-name>`

### 1. Ý nghĩa chuyển động
**Kết luận:** <short interpretation>
**Độ tin cậy:** <confidence if inferred>
**Evidence:** <full preview link/embed>

- [ ] Đúng
- [ ] Cần sửa

### 2. Các giai đoạn chuyển động
| Giai đoạn | Frame | Ý nghĩa |
|---|---:|---|
| ... | ... | ... |

**Evidence:** <phase contact sheet/GIF>

- [ ] Các phase hợp lý
- [ ] Frame boundary cần chỉnh

### 3. Các tư thế quan trọng
| Frame | Vai trò |
|---:|---|
| ... | ... |

**Evidence:** <key-pose contact sheet>

- [ ] Key pose đúng
- [ ] Cần thêm/bỏ key pose

### 4. Chuyển trọng lượng cơ thể
**Kết luận:** <weight-transfer interpretation>
**Dữ liệu hỗ trợ:** <compact measurements>
**Evidence:** <annotated evidence image>
**Độ tin cậy:** <confidence>

- [ ] Đồng ý
- [ ] Sai chân / sai hướng chuyển trọng lượng
- [ ] Evidence chưa đủ rõ

### 5. Cách các phần cơ thể phối hợp
**Kết luận:** <body-mechanics interpretation>
**Thứ tự quan sát được:** <sequence if supported>
**Evidence:** <mechanics evidence image>
**Dữ liệu đo được:** <compact onset/activity table>
**Độ tin cậy:** <confidence>

- [ ] Đúng
- [ ] Thứ tự chưa đúng
- [ ] Không đủ evidence để kết luận

### 6. Animation này hữu ích để tham khảo gì?
**Nên dùng làm reference cho:** <list>
**Không nên dùng làm reference chính cho:** <list if applicable>

### 7. Cảnh báo / uncertainty
<only warnings that materially matter>

### Reviewer decision
- [ ] Metadata có thể accept
- [ ] Cần sửa một số field
- [ ] Phân tích sai, cần generate lại

Reviewer correction format:
`field: <field-name> — <correction>`
```

Only show fields that actually require human interpretation. Deterministic facts such as FPS/frame count can stay compact and should not dominate the comment.

## Comment update behavior

The workflow must be rerunnable without spamming duplicate comments.

Use a stable hidden marker containing the clip identity so the automation can find and update the existing comment for that clip rather than posting another one every run.

Reviewer corrections must not be silently overwritten. If regeneration changes a field that the reviewer previously corrected, surface the change clearly for another review.

## Validation and tests

Add focused automated checks for at least:

- every trusted reference directory expected by PR #17 has `metadata.json`;
- metadata JSON parses;
- required field structure is consistent;
- phase/key-pose frame numbers are within `[0, frameCount - 1]`;
- phase ranges are ordered and logically valid;
- referenced evidence frames exist;
- deterministic canonical facts in metadata, if duplicated, agree with `animation.json`;
- confidence values are within the defined range;
- provenance/source values use allowed values;
- review-comment generation is deterministic for the same metadata/evidence manifest;
- rerunning comment publication updates the same clip comment rather than creating duplicates.

Do not loosen the canonical Humanoid Motion schema or existing tolerances to make these tests pass.

## Scope for PR #17 reference set

Apply the workflow to all trusted Mixamo Humanoid Motion reference clips currently present on PR #17.

`action-idle-to-standing-idle/metadata.json` is an initial example only. Migrate/enrich it into the final common structure instead of treating its current shape as an immutable contract.

## Non-goals

Do not:

- modify the trusted `animation.json` files;
- modify the trusted `preview.gif` files merely to make metadata easier to generate;
- regenerate or replace source motion;
- infer unsupported weapons/props from finger poses;
- create a general-purpose ontology unrelated to the current Humanoid Motion reference use case;
- add a large catalog/framework beyond what is required to make the metadata reliable and reusable;
- store review-only evidence binaries in the final PR diff by default;
- merge this stacked PR into `master` directly;
- merge or mark the PR ready for review without explicit user instruction.

## Implementation order

1. Inventory all trusted reference clips from the exact PR #17 base.
2. Define the smallest consistent metadata structure covering the fields above.
3. Implement deterministic motion-analysis metrics from `animation.json`.
4. Implement evidence generation from canonical data + preview frames.
5. Generate metadata using the quantitative results and visual interpretation.
6. Generate one review package/comment per clip.
7. Visually inspect the evidence; reject obvious bad inferences before requesting human review.
8. Run metadata validation/tests.
9. Post/update PR comments.
10. Report exact HEAD, number of clips processed, generated metadata paths, evidence publication location, test results, and known uncertainties.

## Acceptance criteria

This task is complete only when:

- every trusted PR #17 reference clip has consistent `metadata.json`;
- important interpretive fields include adequate provenance/confidence/evidence references;
- every clip has an easy-to-review PR comment with corresponding visual/quantitative evidence;
- the comment publisher is idempotent;
- the expert has visually reviewed generated evidence before claiming success;
- focused metadata/evidence tests pass on the exact final HEAD;
- trusted PR #17 `animation.json` and `preview.gif` files remain unchanged;
- review-only evidence is not accidentally included in the final merge diff;
- the PR remains stacked on `data/mixamo-humanoid-reference-samples` and is not merged or marked Ready without explicit instruction.
