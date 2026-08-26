# Hướng dẫn sử dụng motion2sheet

Tài liệu này mô tả chi tiết cách dùng `motion2sheet` để chuyển animation humanoid từ FBX/BVH thành dữ liệu pose 2D, ảnh pose theo từng frame và/hoặc pose sheet dùng làm reference cho pipeline AI sprite generation.

## 1. Tool làm gì?

Luồng xử lý chính:

```text
FBX / BVH
   ↓
Blender headless
   ↓
map bone về canonical humanoid skeleton
   ↓
sample animation theo số frame yêu cầu
   ↓
chuẩn hóa hệ trục cơ thể
   ↓
optional: retarget tỷ lệ cơ thể, ví dụ chibi_v1
   ↓
project sang 2D theo direction
   ↓
normalize bằng cùng canvas / scale / ground anchor
   ↓
pose.json
   ↓
frame PNG riêng lẻ và/hoặc pose_sheet.png
```

`pose.json` là dữ liệu pose chuẩn. Ảnh PNG chỉ là output render từ cùng dữ liệu đó.

## 2. Cài đặt

Yêu cầu:

- Python 3.11 trở lên
- Blender 4.5 LTS khuyến nghị
- command `blender` có trong `PATH`

Cài package ở chế độ editable:

```bash
python -m pip install -e .
```

Kiểm tra Blender:

```bash
blender --version
```

Kiểm tra CLI:

```bash
motion2sheet --help
motion2sheet build --help
```

## 3. Lệnh build cơ bản

Ví dụ tạo walk animation 8 frame, 4 hướng:

```bash
motion2sheet build walk.fbx \
  --action walk \
  --frames 8 \
  --directions down,left,right,up \
  --canvas 320x320 \
  --output build/walk
```

Nếu không truyền `--output-mode`, tool mặc định dùng:

```text
--output-mode both
```

Nghĩa là mỗi direction sẽ có cả:

- ảnh từng frame trong `frames/`
- `pose_sheet.png`

## 4. Chế độ output

`--output-mode` có 3 giá trị:

```text
both
frames
sheet
```

### 4.1. `both` - tạo cả frame riêng và pose sheet

Đây là mặc định và tương thích với behavior cũ.

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --profile chibi_v1 \
  --action walk \
  --frames 8 \
  --directions down \
  --canvas 320x320 \
  --output-mode both \
  --output build/walk_down_both
```

Output:

```text
build/walk_down_both/
├── metadata.json
└── down/
    ├── pose.json
    ├── pose_sheet.png
    └── frames/
        ├── 01.png
        ├── 02.png
        ├── 03.png
        ├── 04.png
        ├── 05.png
        ├── 06.png
        ├── 07.png
        └── 08.png
```

Dùng mode này khi cần vừa kiểm tra từng pose vừa cần sheet để đưa vào AI.

### 4.2. `frames` - chỉ giữ từng frame PNG riêng

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --profile chibi_v1 \
  --action walk \
  --frames 8 \
  --directions down \
  --canvas 320x320 \
  --output-mode frames \
  --output build/walk_down_frames
```

Output:

```text
build/walk_down_frames/
├── metadata.json
└── down/
    ├── pose.json
    └── frames/
        ├── 01.png
        ├── 02.png
        ├── 03.png
        ├── 04.png
        ├── 05.png
        ├── 06.png
        ├── 07.png
        └── 08.png
```

Trong mode này `pose_sheet.png` không được tạo.

Mode này phù hợp khi:

- muốn đưa từng pose frame riêng vào AI;
- muốn inspect từng frame rõ hơn;
- muốn tự compose theo layout riêng ở bước sau;
- muốn dùng từng frame làm input cho workflow khác.

### 4.3. `sheet` - chỉ giữ pose sheet

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --profile chibi_v1 \
  --action walk \
  --frames 8 \
  --directions down \
  --canvas 320x320 \
  --output-mode sheet \
  --output build/walk_down_sheet
```

Output:

```text
build/walk_down_sheet/
├── metadata.json
└── down/
    ├── pose.json
    └── pose_sheet.png
```

Tool vẫn render frame nội bộ để compose sheet nhưng sẽ xóa thư mục `frames/` trước khi hoàn tất build.

Mode này phù hợp khi chỉ cần pose sheet cuối cùng và muốn artifact nhỏ gọn.

## 5. Tạo 4 hướng

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --profile chibi_v1 \
  --action walk \
  --frames 8 \
  --directions down,left,right,up \
  --canvas 320x320 \
  --output-mode frames \
  --output build/walk_chibi_frames
```

Output:

```text
build/walk_chibi_frames/
├── metadata.json
├── down/
│   ├── pose.json
│   └── frames/01.png ... 08.png
├── left/
│   ├── pose.json
│   └── frames/01.png ... 08.png
├── right/
│   ├── pose.json
│   └── frames/01.png ... 08.png
└── up/
    ├── pose.json
    └── frames/01.png ... 08.png
```

Thứ tự direction canonical:

```text
down   =   0°
left   = +90°
right  = -90°
up     = 180°
```

## 6. Dùng proportion profile

Mặc định:

```text
--profile source
```

`source` giữ tỷ lệ cơ thể của rig đầu vào.

Để chuyển motion sang tỷ lệ chibi dùng:

```text
--profile chibi_v1
```

Ví dụ:

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --profile chibi_v1 \
  --frames 8 \
  --directions down,left,right,up \
  --output-mode both \
  --output build/walk_chibi
```

Motion vẫn lấy từ source FBX/BVH nhưng bone length canonical được rebuild theo profile trước khi project sang 2D.

Có thể truyền file profile JSON riêng:

```bash
motion2sheet build walk.fbx \
  --profile path/to/my_profile.json \
  --frames 8 \
  --directions down \
  --output build/custom_profile_walk
```

## 7. Ý nghĩa các tham số chính

### `input`

Đường dẫn FBX/BVH đầu vào.

```bash
motion2sheet build sample/walk_mixamo.fbx ...
```

### `--action`

Tên action logic ghi vào output. Nếu bỏ qua, tool dùng action được extractor xác định từ source.

```text
--action walk
```

### `--frames`

Số frame cần sample đều trên animation timeline.

```text
--frames 8
```

Ví dụ animation source có 32 frame nhưng `--frames 8`, tool lấy 8 pose đại diện theo timeline thay vì xuất toàn bộ 32 frame.

### `--directions`

Danh sách hướng, phân cách bằng dấu phẩy.

```text
--directions down
--directions down,left,right,up
```

### `--canvas`

Kích thước canvas của từng frame.

```text
--canvas 320x320
```

Nếu dùng 8 frame, `--sheet-columns 4` và canvas `320x320`, pose sheet mặc định có kích thước:

```text
1280 × 640
```

### `--sheet-columns`

Số cột khi compose pose sheet.

```text
--sheet-columns 4
```

Tham số này chỉ ảnh hưởng ảnh sheet. Với `--output-mode frames`, nó vẫn được ghi vào metadata nhưng không có sheet để compose.

### `--padding`

Khoảng padding dùng khi normalize skeleton vào canvas.

```text
--padding 20
```

Không nên thay đổi tùy từng frame. Tool dùng global normalization để giữ scale ổn định giữa các frame và direction.

### `--camera-elevation`

Góc camera elevation khi project skeleton 3D sang 2D.

```text
--camera-elevation 35
```

Mặc định 35 độ, phù hợp với view high 3/4 đang dùng cho pose reference.

### `--blender`

Chỉ định executable Blender nếu `blender` không nằm trong PATH.

```bash
motion2sheet build walk.fbx \
  --blender /opt/blender/blender \
  --output build/walk
```

### `--keep-raw`

Giữ lại file debug `.raw_projected.json`.

```text
--keep-raw
```

Nên bật khi debug import, bone mapping, projection hoặc retarget.

## 8. Validate output

Sau khi build:

```bash
motion2sheet validate build/walk_chibi
```

Validator đọc `metadata.json`, bao gồm `outputMode`, rồi validate đúng contract tương ứng.

### Với `both`

Phải có:

- `pose.json`
- đủ frame PNG
- `pose_sheet.png`

### Với `frames`

Phải có:

- `pose.json`
- đủ frame PNG
- không có `pose_sheet.png`

### Với `sheet`

Phải có:

- `pose.json`
- `pose_sheet.png`
- không còn frame PNG

Ngoài file structure, validator còn kiểm tra:

- frame count;
- canonical joints;
- coordinate hữu hạn và nằm trong canvas;
- skeleton không collapse;
- head nằm phía trên pelvis;
- continuity giữa frame liền kề;
- animation nhiều frame phải có chuyển động thực;
- kích thước PNG đúng canvas;
- kích thước pose sheet đúng layout.

## 9. Ví dụ thực tế với Mixamo sample trong repository

### 9.1. Chibi Walk Down - từng frame riêng

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --action walk \
  --profile chibi_v1 \
  --frames 8 \
  --directions down \
  --canvas 320x320 \
  --output-mode frames \
  --output build/mixamo_walk_down_frames

motion2sheet validate build/mixamo_walk_down_frames
```

Các ảnh dùng trực tiếp:

```text
build/mixamo_walk_down_frames/down/frames/01.png
...
build/mixamo_walk_down_frames/down/frames/08.png
```

### 9.2. Chibi Walk - 4 pose sheet

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --action walk \
  --profile chibi_v1 \
  --frames 8 \
  --directions down,left,right,up \
  --canvas 320x320 \
  --output-mode sheet \
  --output build/mixamo_walk_sheets
```

Các sheet:

```text
build/mixamo_walk_sheets/down/pose_sheet.png
build/mixamo_walk_sheets/left/pose_sheet.png
build/mixamo_walk_sheets/right/pose_sheet.png
build/mixamo_walk_sheets/up/pose_sheet.png
```

### 9.3. Chibi Walk - vừa frame vừa sheet

```bash
motion2sheet build sample/walk_mixamo.fbx \
  --action walk \
  --profile chibi_v1 \
  --frames 8 \
  --directions down,left,right,up \
  --canvas 320x320 \
  --output-mode both \
  --output build/mixamo_walk_full
```

## 10. `metadata.json`

Build mới ghi thêm:

```json
{
  "outputMode": "frames"
}
```

Validator dùng field này để biết artifact nào bắt buộc tồn tại.

Các build cũ chưa có `outputMode` vẫn được hiểu là:

```text
both
```

nhằm giữ backward compatibility.

## 11. Build lại cùng output directory

Tool xóa output cũ của từng direction trước khi render lại. Vì vậy chuyển từ:

```text
both → frames
```

sẽ không để sót `pose_sheet.png` cũ; và chuyển từ:

```text
both → sheet
```

sẽ không để sót thư mục frame cũ.

Điều này quan trọng vì validator của mỗi mode yêu cầu filesystem đúng contract, không chỉ kiểm tra file cần thiết có tồn tại.

## 12. Gợi ý sử dụng trong pipeline game asset

Nếu mục tiêu là AI generation từ một pose sheet:

```text
--output-mode sheet
```

Nếu muốn AI hoặc workflow xử lý từng pose độc lập:

```text
--output-mode frames
```

Nếu đang phát triển, debug hoặc review motion:

```text
--output-mode both
--keep-raw
```

Workflow khuyến nghị:

```text
Mixamo/Rokoko FBX
      ↓
motion2sheet --profile chibi_v1
      ↓
pose.json
      ├─ frames/*.png
      └─ pose_sheet.png
      ↓
AI sprite generation
```

## 13. Troubleshooting

### Blender executable not found

Kiểm tra:

```bash
blender --version
```

Nếu command không tồn tại, cài Blender hoặc dùng `--blender` với đường dẫn executable.

### Unknown proportion profile

Ví dụ lỗi khi gõ sai:

```text
--profile chibi-v1
```

Profile built-in hiện tại là:

```text
chibi_v1
```

### Missing joints / unknown rig

Tool chỉ support humanoid rig có thể map về canonical skeleton. Rig không nhận diện được sẽ fail thay vì tự đoán bone mapping.

### Animation appears static

Validator phát hiện quá ít limb joint di chuyển. Kiểm tra source animation/action và bật:

```text
--keep-raw
```

để xem dữ liệu projected debug.

### Output mode không đúng như mong đợi

Xem:

```text
metadata.json → outputMode
```

và chạy lại:

```bash
motion2sheet validate <output-directory>
```

Validator sẽ báo nếu sheet/frame tồn tại sai với mode đã chọn.
