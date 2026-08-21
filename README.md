# motion2sheet

`motion2sheet` converts humanoid motion files into deterministic 2D skeleton pose sheets that can be used as pose-conditioning references for AI sprite generation.

## MVP scope

- Inputs: `.fbx` and `.bvh`
- Humanoid skeletons only
- Blender runs headless; no Blender UI is required
- Canonical 2D joint JSON is the source of truth
- PNG skeleton frames and pose sheets are derived artifacts
- One global normalization scale is used across all directions in a build
- Source coordinate orientation is canonicalized automatically from body landmarks
- CI generates deterministic FBX/BVH fixtures, builds pose sheets, validates actual movement/projection, and uploads the generated output as a GitHub Actions artifact

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
fixed orthographic 3/4 projection
   ↓
raw 2D joints
   ↓
global normalization
   ↓
pose.json
   ↓
frame PNGs
   ↓
pose_sheet.png
```

## Install

Requirements:

- Python 3.11+
- Blender 4.5 LTS recommended and available as `blender` on `PATH`

```bash
python -m pip install -e .
```

## Build a walk pose sheet

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

## Output

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

Validation checks include expected frame count, canonical joints, finite/in-bounds coordinates, adjacent-frame continuity, skeleton projection height, actual limb motion, PNG dimensions, and sheet layout. Multi-frame output that is visually static is rejected.

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

Every sampled joint is transformed into this canonical body space before direction rotation and camera projection. That keeps FBX and BVH inputs from collapsing simply because their imported source axes differ.

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

`.github/workflows/ci.yml` runs on pull requests and `master` pushes. It runs unit tests, installs Blender 4.5 LTS, creates a deterministic synthetic humanoid walk, exports FBX/BVH, imports both formats again, builds four-direction pose sheets, rejects static/collapsed output, validates JSON/PNG structure, and uploads `motion2sheet-e2e-output` for visual inspection. Raw projected JSON and source fixtures are retained in the CI artifact for debugging.

## AI sprite generation skills

```text
skills/
├── storybook-rpg-sprite-pipeline/
│   └── SKILL.md
└── pose-sheet-to-sprite-sheet/
    └── SKILL.md
```

- `storybook-rpg-sprite-pipeline`: orchestrates the full flow from an existing Pose Sheet to a normalized production sprite asset.
- `pose-sheet-to-sprite-sheet`: converts an existing Pose Sheet plus Character Reference into a raw AI-generated character sprite sheet.
- The skill layer treats Pose Sheets as existing inputs and does not define how they are created.

High-level architecture:

```text
Motion
  ↓
motion2sheet
  ↓
Pose Sheet
  ↓
AI sprite generation skills
  ↓
Sprite Sheet
```

## Current limitations

- humanoid only
- one armature per input file
- no retargeting yet
- no quadruped/monster skeleton schema yet
- PNG output is a skeleton reference, not final game art
