# anim2sheet Blender rig pipeline

`motion2sheet.anim2sheet` is a deterministic Blender-native proof of concept for turning an authored motion contract into a 2D sprite sheet. The current sample is the 16-frame swordsman **Gale Slash** attack.

## Source-of-truth boundaries

```text
pose_reference.json
        |
        v
blender_entry.py
        |
        +--> source.blend       <- editable/authoritative Blender source
        +--> frames/*.png       <- Eevee proxy-object render
        +--> motion_debug.json  <- evaluated post-IK measurements
        |
        v
blender_skeleton_viewport.py
        |
        +--> skeleton_frames/*.png
        +--> rig_default_overview.png
        +--> rig_default_labeled.png
        +--> rig_bones.json
        +--> rig_bones.txt
```

External Python packages already-rendered PNGs into sheets/GIFs and validates outputs. It does **not** redraw the skeleton.

## `blender_entry.py`

This script runs in Blender background mode and:

1. builds the canonical `GameHumanoidV2` armature,
2. builds the segmented proxy character,
3. reads the v2 pose contract embedded in `source.json`,
4. applies hybrid FK + IK,
5. animates the sword,
6. samples the actual evaluated rig after constraints,
7. saves `source.blend`,
8. renders normal object frames with Eevee.

### Canonical `GameHumanoidV2`

`MotionRoot` is an object-level motion controller, not a bone.

```text
Root
`- Pelvis
   |- LeftHip
   |  `- LeftThigh
   |     `- LeftShin
   |        `- LeftFoot
   |- RightHip
   |  `- RightThigh
   |     `- RightShin
   |        `- RightFoot
   `- Spine
      `- Chest
         |- LeftClavicle
         |  `- LeftUpperArm
         |     `- LeftForeArm
         |        `- LeftHand
         |- RightClavicle
         |  `- RightUpperArm
         |     `- RightForeArm
         |        `- RightHand
         `- Neck
            `- Head
```

The explicit `LeftHip` / `RightHip` connector bones remove the visually detached thigh-to-pelvis hierarchy from the first POC rig. Clavicles are also explicit so shoulder motion can participate in the strike.

### Hybrid FK + IK

The v1 POC only authored wrist/ankle end-effectors and a few body lean values. That allowed Blender to reach targets while still producing poor silhouettes.

V2 separates responsibilities:

**FK body controls**

- pelvis yaw + lean,
- spine yaw + lean,
- chest yaw + lean,
- head counter-rotation,
- left/right clavicle swing.

**IK end-effectors**

- `leftWrist`,
- `rightWrist`,
- `leftAnkle`,
- `rightAnkle`.

**Authored bend guides / pole targets**

- `leftElbowGuide`,
- `rightElbowGuide`,
- `leftKneeGuide`,
- `rightKneeGuide`.

Targets are authored in world space. This lets one foot stay planted while `MotionRoot` advances and lets the other foot perform an actual step instead of simply translating with the whole character.

`motion_debug.json` records actual evaluated joints, IK error, stance width, pelvis/shoulder yaw, arm extension and elbow/knee bend angles.

## `blender_skeleton_viewport.py`

Blender armature bones are viewport display elements rather than ordinary Eevee/Cycles render geometry. This script therefore opens the saved `source.blend` in a regular Blender UI process (CI runs it under Xvfb), hides the proxy character meshes, selects the real armature, sets it to `OCTAHEDRAL + In Front`, and keeps the Blender 3D Viewport as the rendering authority.

### Animated skeleton frames

Animation inspection uses Blender Viewport Render:

```python
bpy.ops.render.opengl(write_still=True, view_context=True)
```

So `skeleton_frames/*.png` and `skeleton_sheet.png` show the **actual evaluated Blender armature after IK**. No Pillow/ImageDraw skeleton and no fake bone mesh are used.

### Default rig exports

The script temporarily switches the armature to Blender `REST` pose and exports:

- `rig_default_overview.png` — full default/rest rig without names,
- `rig_default_labeled.png` — the same actual Blender rig with Blender bone-name overlays,
- `rig_bones.json` — exact names, parent hierarchy, connect/deform flags and rest head/tail coordinates,
- `rig_bones.txt` — human-readable hierarchy.

`rig_default_overview.png` uses the same Viewport Render operator as the animation.

Blender Viewport Render does not reliably include editor text overlays such as bone names. Therefore the **labeled** diagnostic intentionally captures the actual Blender 3D View editor instead:

```python
bpy.ops.screen.screenshot_area(
    filepath=...,
    check_existing=False,
    hide_props_region=True,
)
```

Before that screenshot, the script enables `arm.data.show_names`, keeps viewport overlays/text enabled, hides toolbar/sidebar clutter where supported, and forces a Blender redraw. The resulting labels are Blender's own bone-name overlay; they are **not** rendered or composited by Python/Pillow.

These temporary rest/viewport settings are never saved back into `source.blend`.

## Pose reference v2

Every frame authors root X/Z, torso and clavicle FK controls, wrist and ankle end-effectors, elbow and knee bend guides, and sword grip/tip guide. The pose reference is authority for motion/timing/weapon trajectory only; character appearance remains out of scope.

## Quality gates

CI deliberately checks more than IK error: maximum IK end-effector error, anticipation crouch, attack/root drive, actual left-foot step, rear/right-foot planting through impact, strike stance width, evaluated pelvis yaw range, evaluated shoulder yaw range, elbow trajectory, impact arm extension, sword right -> depth -> left trajectory, impact foreshortening, and recovery orientation.

The rig-export gate also checks that the manifest is `GameHumanoidV2`, the canonical hierarchy is intact, both default rig images exist at inspection resolution, and the labeled capture is pixel-different from the unlabeled overview.

A low IK error only means the end effector reached its target. It does **not** mean the animation is visually good. The actual Blender skeleton artifact remains the primary manual motion-quality review surface.

## Generated run layout

```text
run_a/
├── source.json
├── source.blend
├── pose_reference.json
├── motion_debug.json
├── metadata.json
├── frames/
│   `-- 01.png ... 16.png
├── object_sheet.png
├── sprite_sheet.png
├── preview.gif
├── skeleton_frames/
│   `-- 01.png ... 16.png
├── skeleton_sheet.png
├── rig_default_overview.png
├── rig_default_labeled.png
├── rig_bones.json
`-- rig_bones.txt
```

CI performs deterministic A/B builds, compares object and skeleton pixels, re-opens `source.blend`, re-renders the object animation, and compares decoded RGBA pixels with the original render.
