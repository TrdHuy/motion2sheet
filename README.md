# motion2sheet

`motion2sheet` converts humanoid motion files into deterministic 2D skeleton pose outputs that can be used as pose-conditioning references for AI sprite generation.

> Hướng dẫn sử dụng chi tiết bằng tiếng Việt: [`docs/huong-dan-su-dung.md`](docs/huong-dan-su-dung.md)
>
> Reusable humanoid animation: [`docs/humanoid-motion.md`](docs/humanoid-motion.md)

## MVP scope

- Inputs: `.fbx` and `.bvh`
- Humanoid skeletons only
- Blender runs headless; no Blender UI is required
- Canonical 2D joint JSON is the source of truth
- PNG skeleton frames and pose sheets are derived artifacts
- Output can be `both`, `frames`, or `sheet`
- One global normalization scale is used across all directions in a build
- Source coordinate orientation is canonicalized automatically from body landmarks
- Optional proportion profiles can rebuild source motion onto canonical body proportions before projection
- Pull-request CI resolves affected component/test targets; pushes to `master` run the full regression graph

## Pipeline

```text
FBX / BVH
   ↓
Blender headless
   ↓
activate imported animation take
   ↓
canonical bone mapping
   ↓
infer source right / forward / up basis
   ↓
sample evaluated pose matrices
   ↓
optional proportion retarget
   ↓
fixed orthographic 3/4 projection
   ↓
raw 2D joints
   ↓
global normalization
   ↓
pose.json
   ↓
frame PNGs and/or pose_sheet.png
```

## Install

Requirements:

- Python 3.11+
- Blender 4.5 LTS recommended and available as `blender` on `PATH`

```bash
python -m pip install -e .
```

## Build a walk pose output

```bash
motion2sheet build walk.fbx \
  --action walk \
  --frames 8 \
  --directions down,left,right,up \
  --canvas 320x320 \
  --output build/walk
```

For one direction only:

```bash
motion2sheet build walk.fbx \
  --frames 8 \
  --directions down \
  --output build/walk_down
```

## Output modes

The default is `--output-mode both`, preserving the existing behavior.

```text
both    pose.json + frames/*.png + pose_sheet.png
frames  pose.json + frames/*.png
sheet   pose.json + pose_sheet.png
```

Frames only:

```bash
motion2sheet build walk.fbx \
  --frames 8 \
  --directions down \
  --output-mode frames \
  --output build/walk_frames
```

Sheet only:

```bash
motion2sheet build walk.fbx \
  --frames 8 \
  --directions down \
  --output-mode sheet \
  --output build/walk_sheet
```

See the [Vietnamese usage guide](docs/huong-dan-su-dung.md) for detailed examples, Mixamo commands, parameter explanations, output structures, validation rules, and troubleshooting.

## Proportion profiles

The default `source` profile preserves source-rig proportions. Use `chibi_v1` to keep source motion directions while rebuilding the canonical skeleton with compact storybook-RPG bone lengths before 2D projection:

```bash
motion2sheet build walk.fbx \
  --profile chibi_v1 \
  --frames 8 \
  --directions down,left,right,up \
  --output build/walk_chibi
```

`--profile` also accepts a JSON profile path. Profile values define canonical segment lengths; they are not pixel sizes. Root motion is scaled by target/source canonical stature so body translation remains proportional after retargeting.

## Output

Default `both` mode:

```text
build/walk/
├── metadata.json
├── down/
│   ├── pose.json
│   ├── pose_sheet.png
│   └── frames/
│       ├── 01.png
│       └── ...
├── left/
├── right/
└── up/
```

For eight frames, each direction uses a `4 × 2` sheet by default. With a `320 × 320` frame canvas, the resulting sheet is `1280 × 640`.

## Validate output

```bash
motion2sheet validate build/walk
```

Validation reads `metadata.json` and respects `outputMode`. It checks expected frame count, canonical joints, finite/in-bounds coordinates, adjacent-frame continuity, skeleton projection height, actual limb motion, PNG dimensions, and the required frame/sheet filesystem contract. Multi-frame output that is visually static is rejected.

Older metadata without `outputMode` is treated as `both` for backward compatibility.

## Canonical skeleton

```text
head
neck
left_shoulder / left_elbow / left_wrist
right_shoulder / right_elbow / right_wrist
pelvis
left_hip / left_knee / left_ankle
right_hip / right_knee / right_ankle
```

Common Mixamo-style names are mapped automatically. Unknown rigs fail explicitly rather than silently guessing an incorrect skeleton.

## Coordinate and direction convention

The importer no longer assumes the file already uses Blender `Z-up`. At the first animation frame it derives:

- character right from left/right hip landmarks (shoulders are fallback)
- character up from pelvis to head
- character forward from the orthogonal right/up basis

Every sampled joint is transformed into this canonical body space before optional proportion retargeting, direction rotation, and camera projection. That keeps FBX and BVH inputs from collapsing simply because their imported source axes differ.

Canonical directions are:

```text
down   0°
left  +90°
right -90°
up    180°
```

All directions use the same sampled animation timeline.

## Normalization contract

The generated pose is **not resized independently per frame**. `motion2sheet` projects all requested poses, derives a ground anchor from pelvis-X and lowest-ankle-Y, computes one global scale, and applies it to every frame/direction on the same canonical canvas.

## CI

`.github/workflows/ci.yml` uses dependency-aware target selection on pull requests. Motion component changes run only their affected unit/E2E targets, while VFX-only changes do not run motion tests. Sprite-workflow-only changes run a lightweight deterministic contract test and do not install Blender. Pushes to `master` and manual workflow dispatches run the complete graph.

## AI sprite generation skills

```text
skills/
├── storybook-rpg-sprite-pipeline/
│   └── SKILL.md
├── pose-frame-to-sprite-frame/
│   └── SKILL.md
└── pose-sheet-to-sprite-sheet/
    └── SKILL.md
```

- `storybook-rpg-sprite-pipeline`: orchestrates the production flow from pose references to a normalized production sprite asset.
- `pose-frame-to-sprite-frame`: default pose-lock workflow; converts exactly one Pose Reference plus its matching Action Description and Character Reference into one raw sprite frame.
- `pose-sheet-to-sprite-sheet`: legacy/experimental whole-sheet generation workflow retained for A/B comparison.

Recommended high-level architecture:

```text
Motion
  ↓
motion2sheet --output-mode frames
  ↓
Pose Frame N + Action Description N + Character Reference
  ↓
pose-frame-to-sprite-frame
  ↓
Raw Sprite Frame N
  ↓
QA each frame
  ↓
common scale + common anchor + compose
  ↓
Production Sprite Sheet
```

## Current limitations

- humanoid only
- one armature per input file
- proportion retargeting is joint-space only; no planted-foot IK yet
- no quadruped/monster skeleton schema yet
- PNG output is a skeleton reference, not final game art
