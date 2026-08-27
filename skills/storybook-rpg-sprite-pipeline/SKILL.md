# Storybook RPG Sprite Pipeline

## Mục đích

- Tạo sprite animation 2D RPG nhất quán về nhân vật, chuyển động và thông số kỹ thuật.
- Dùng từng Pose Reference riêng làm nguồn chuyển động cho từng frame.
- Dùng Character Reference làm nguồn nhận diện và phong cách.
- Dùng Action Description riêng cho từng frame để khóa action, direction, camera và semantics của pose.
- Tách phần AI tạo hình khỏi phần chuẩn hóa kỹ thuật.

## Nguyên tắc cốt lõi

- Pose Reference của frame quyết định exact pose và limb topology.
- Action Description của frame quyết định action, direction, camera/view và motion semantics.
- Character Reference quyết định ngoại hình.
- AI tạo artwork từng frame độc lập.
- Tool deterministic xử lý crop, scale, anchor và compose.
- Raw AI output không được coi là production asset.

## Input

Cho một action + một direction:

- `character reference.png`.
- `general prompt.txt`.
- các cặp Pose/Description:

```text
<action> pose 1.png <-> <action> description 1.txt
<action> pose 2.png <-> <action> description 2.txt
...
<action> pose N.png <-> <action> description N.txt
```

Ví dụ Walk Down 8 frame:

```text
walk pose 1.png <-> walk description 1.txt
walk pose 2.png <-> walk description 2.txt
walk pose 3.png <-> walk description 3.txt
walk pose 4.png <-> walk description 4.txt
walk pose 5.png <-> walk description 5.txt
walk pose 6.png <-> walk description 6.txt
walk pose 7.png <-> walk description 7.txt
walk pose 8.png <-> walk description 8.txt
```

- Technical Spec:
  - frame size;
  - anchor;
  - frame count;
  - final layout;
  - direction;
  - naming convention.

## Pairing contract

- Số trong tên Pose Reference và Action Description phải giống nhau.
- `pose N` chỉ được dùng với `description N`.
- Không dùng pose của frame này với description của frame khác.
- Không đưa nhiều pose vào cùng một lần AI generation.

## Quy trình

1. Khóa Character Reference và art style.
2. Khóa Technical Spec.
3. Nhận các Pose Reference riêng cho action + direction.
4. Chuẩn bị một Action Description riêng cho từng pose frame.
5. Với mỗi frame N, gọi skill `pose-frame-to-sprite-frame` với:
   - Character Reference;
   - `<action> pose N.png`;
   - `<action> description N.txt`;
   - General Prompt.
6. QA pose của từng frame độc lập.
7. Frame nào fail thì chỉ regenerate frame đó.
8. Khi tất cả frame PASS:
   - alpha-trim từng raw frame;
   - normalize toàn bộ frame bằng cùng một scale;
   - đặt toàn bộ frame theo cùng một anchor;
   - compose production sprite sheet;
   - tạo animation preview;
   - validate trước khi export.

## Quy tắc generation

- Chỉ generate một frame tại một thời điểm.
- Không đưa neighboring raw sprite frame vào làm pose reference trong pass pose-lock đầu tiên.
- Không yêu cầu AI tự xử lý pixel-perfect alignment.
- Ưu tiên:
  1. direction / camera;
  2. limb identity và topology;
  3. exact pose;
  4. character identity;
  5. visual polish.

## Quy tắc xử lý frame

- Không resize từng frame độc lập để fill canvas.
- Dùng một common scale cho toàn bộ animation.
- Dùng một common anchor cho toàn bộ animation.
- Compose sheet chỉ sau khi tất cả raw frame đã PASS QA.

## Validation

- Motion:
  - đúng frame order;
  - đúng pose sequence;
  - không swap limb;
  - không mirror pose;
  - loop hợp lý.
- Character:
  - cùng identity;
  - cùng tỷ lệ;
  - cùng trang phục;
  - cùng equipment;
  - không design drift nghiêm trọng.
- Technical:
  - đúng frame count;
  - đúng canvas;
  - đúng anchor;
  - cùng scale;
  - không clipping;
  - transparency hợp lệ.

## Preview

Luôn tạo animation preview sau khi normalize để phát hiện:

- motion jump;
- anchor jitter;
- scale jitter;
- frame order sai;
- character inconsistency.

## Output

- Production sprite sheet.
- Animation preview.
- Metadata kỹ thuật của animation.

## Delegation

- Workflow mặc định: dùng `pose-frame-to-sprite-frame` cho từng frame.
- `pose-sheet-to-sprite-sheet` chỉ giữ lại như workflow cũ / thử nghiệm để A/B test.
