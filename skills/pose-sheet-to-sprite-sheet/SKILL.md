# Pose Sheet to Sprite Sheet

## Mục đích

- Chuyển Pose Sheet có sẵn thành raw character sprite sheet bằng AI image generation.
- Giữ đúng chuyển động, nhân vật và thứ tự frame.
- Không tạo Pose Sheet và không làm production normalization.

## Input

- Pose Sheet:
  - một action;
  - một direction;
  - frame count xác định;
  - layout xác định.
- Character Reference:
  - identity;
  - khuôn mặt;
  - tóc;
  - tỷ lệ cơ thể;
  - trang phục;
  - equipment;
  - màu sắc;
  - art style.

## Authority

- Pose Sheet là nguồn quyết định chuyển động.
- Character Reference là nguồn quyết định ngoại hình.
- Không dùng Character Reference để thay thế pose trong Pose Sheet.

## Frame mapping

- Mapping frame theo đúng vị trí trong Pose Sheet.
- Với layout 4×2:

```text
F1  F2  F3  F4
F5  F6  F7  F8
```

- Bắt buộc giữ mapping `Pose Fn → Sprite Fn`.
- Không reorder, bỏ, duplicate hoặc tự thay pose.
- Không xem Pose Sheet như reference chung; phải bám theo từng frame.

## Character consistency

- Giữ cùng một nhân vật ở tất cả frame.
- Không thay đổi:
  - face;
  - hairstyle;
  - head size;
  - body proportions;
  - clothing design;
  - equipment;
  - colors;
  - materials.
- Chỉ thay đổi các yếu tố do chuyển động yêu cầu như limb position, body lean, body bob và secondary motion.

## Temporal continuity

- Xem toàn bộ output là một animation sequence liên tục, không phải các illustration độc lập.
- Giữ progression tự nhiên từ `F1 → F2 → ... → Fn`.
- Tránh limb teleport, body rotation ngẫu nhiên, scale jump, camera drift và character design drift.

## Direction lock

- Giữ nguyên direction của Pose Sheet trong toàn bộ frame.
- Pose thay đổi không được làm nhân vật đổi hướng.

## Priority

- Ưu tiên theo thứ tự:
  1. Pose adherence.
  2. Character consistency.
  3. Temporal continuity.
  4. Art polish.
- Không hy sinh pose correctness để làm một frame đẹp hơn.

## Layout

- Output giữ cùng logical layout và frame count với Pose Sheet.
- Mỗi sprite nằm trong cell tương ứng.
- Không thêm text, frame number, border, grid, UI, scenery hoặc object không liên quan.
- Ưu tiên transparent background nếu image generator hỗ trợ.

## Default art style

- Hand-drawn Storybook RPG.
- Top-down / high 3/4 RPG view.
- Expressive ink outlines.
- Hand-painted / watercolor feel.
- Soft textured shading.
- Warm earthy fantasy palette.
- Slightly chibi proportions.
- Clear game-readable silhouette.
- Tránh pixel art, photorealism, realistic 3D, glossy CGI/plastic và unrelated anime redesign.

## Generation instruction

- Generate đúng một animation sprite sheet.
- Dùng Pose Sheet làm authoritative motion reference.
- Giữ đúng frame count, layout và frame order.
- Map từng output frame với đúng pose frame tương ứng.
- Bám sát head, shoulders, elbows, wrists, pelvis, knees, ankles và overall body gesture.
- Giữ cùng character identity, proportions, clothing, equipment, colors, materials và art style ở tất cả frame.
- Giữ cùng camera direction và character scale.
- Không tự invent, improve, replace hoặc reinterpret pose.

## Failure rules

- Regenerate nếu:
  - sai pose đáng kể;
  - sai frame mapping;
  - duplicate hoặc thiếu frame;
  - đổi direction;
  - character identity drift;
  - clothing/equipment drift;
  - thiếu limb hoặc anatomy lỗi lớn;
  - frame merge hoặc có content không liên quan.
- Không cần regenerate chỉ vì:
  - padding không đều;
  - lệch vài pixel;
  - center chưa chuẩn;
  - alpha chưa sạch hoàn toàn.

## Output

- Raw character sprite sheet.
- Raw output chưa phải production asset.

## Scope boundary

- Skill này không:
  - tạo Pose Sheet;
  - crop final frames;
  - normalize scale;
  - normalize anchor;
  - compose production sprite sheet;
  - tạo preview GIF;
  - export metadata/game asset.
