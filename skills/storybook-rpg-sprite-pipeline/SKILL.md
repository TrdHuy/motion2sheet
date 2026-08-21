# Hand-drawn Storybook RPG Sprite Pipeline

## Mục đích

- Tạo sprite animation 2D RPG nhất quán về nhân vật, chuyển động và thông số kỹ thuật.
- Dùng Pose Sheet có sẵn làm nguồn chuyển động.
- Dùng Character Reference làm nguồn nhận diện và phong cách.
- Tách phần AI tạo hình khỏi phần chuẩn hóa kỹ thuật.

## Nguyên tắc cốt lõi

- Pose Sheet quyết định chuyển động.
- Character Reference quyết định ngoại hình.
- AI tạo artwork.
- Tool deterministic xử lý crop, scale, anchor và compose.
- Raw AI output không được coi là production asset.
- Không tự tạo hoặc chỉnh sửa Pose Sheet trong skill này.

## Input

- Character Reference:
  - khuôn mặt;
  - tóc;
  - tỷ lệ cơ thể;
  - trang phục;
  - equipment;
  - màu sắc;
  - phong cách hình ảnh.
- Pose Sheet:
  - một action;
  - một direction;
  - frame order rõ ràng;
  - layout xác định.
- Technical Spec:
  - frame size;
  - anchor;
  - frame count;
  - layout;
  - direction;
  - naming convention.

## Quy trình

- Khóa Character Reference và art style.
- Khóa Technical Spec.
- Nhận Pose Sheet tương ứng với action và direction cần tạo.
- Generate một action + một direction trong mỗi lần AI generation.
- Dùng skill `pose-sheet-to-sprite-sheet` để tạo raw sprite sheet.
- Crop raw sheet theo fixed grid.
- Alpha-trim bên trong từng cell sau khi crop.
- Normalize toàn bộ frame bằng cùng một scale.
- Đặt toàn bộ frame theo cùng một anchor.
- Compose lại production sprite sheet.
- Tạo animation preview.
- Validate trước khi export.

## Quy tắc generation

- Chỉ generate một direction tại một thời điểm.
- Giữ đúng số frame và layout của Pose Sheet.
- Không generate nhiều direction trong cùng một raw image.
- Không yêu cầu AI tự xử lý pixel-perfect alignment.
- Ưu tiên pose, character consistency và temporal continuity.

## Quy tắc xử lý frame

- Crop bằng tọa độ grid cố định trước.
- Không dùng whole-sheet connected component để tìm frame.
- Chỉ alpha-trim sau khi từng frame đã được tách riêng.
- Không resize từng frame độc lập để fill canvas.
- Dùng một common scale cho toàn bộ animation.
- Dùng một common anchor cho toàn bộ animation.

## Validation

- Motion:
  - đúng frame order;
  - đúng pose sequence;
  - chuyển động liên tục;
  - loop hợp lý.
- Character:
  - cùng identity;
  - cùng tỷ lệ;
  - cùng trang phục;
  - cùng equipment;
  - không design drift.
- Technical:
  - đúng frame count;
  - đúng canvas;
  - đúng anchor;
  - cùng scale;
  - không clipping;
  - không contamination giữa các cell;
  - transparency hợp lệ.

## Preview

- Luôn tạo animation preview sau khi normalize.
- Dùng preview để phát hiện:
  - motion jump;
  - anchor jitter;
  - scale jitter;
  - frame order sai;
  - character inconsistency.

## Output

- Production sprite sheet.
- Animation preview.
- Metadata kỹ thuật của animation.

## Cấu trúc đề xuất

```text
character/
└── <action>/
    ├── down/
    │   ├── sprite_sheet.png
    │   ├── preview.gif
    │   └── metadata.json
    ├── left/
    ├── right/
    └── up/
```

## Delegation

- Khi cần chuyển Pose Sheet thành raw character sprite sheet, dùng skill `pose-sheet-to-sprite-sheet`.
- Skill này không mô tả cách tạo Pose Sheet.
