# Pose Frame to Sprite Frame

## Mục đích

- Chuyển một Pose Reference của đúng một frame thành một raw character sprite frame bằng AI image generation.
- Tối đa hóa độ bám pose và giảm lỗi average/collapse giữa các frame.
- Không generate nhiều frame trong cùng một lần gọi AI.

## Input bắt buộc

Mỗi generation nhận:

1. Character Reference.
2. Một Pose Reference duy nhất.
3. Một Action Description tương ứng với đúng Pose Reference đó.
4. General Prompt của workflow.

## Authority

- Character Reference quyết định ngoại hình.
- Pose Reference quyết định geometry và topology của frame hiện tại.
- Action Description quyết định action, direction, camera/view và cách diễn giải motion của frame hiện tại.
- General Prompt quyết định các luật generation dùng chung.

## Quy tắc tên file và pairing

Trong sample Walk Down, bắt buộc pair theo cùng số frame:

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

Contract tổng quát:

```text
<action> pose N.png <-> <action> description N.txt
```

Không được:

- dùng pose N với description M khi `N != M`;
- đưa nhiều Pose Reference vào cùng generation;
- dùng pose sheet nhiều frame thay cho pose frame khi đang chạy workflow này;
- dùng raw sprite frame trước/sau làm pose authority.

## Quy trình một frame

Ví dụ frame 4:

```text
character reference.png
+ walk pose 4.png
+ walk description 4.txt
+ general prompt.txt
        ↓
AI image generation
        ↓
raw sprite frame 4
```

Lặp độc lập cho từng frame.

## Limb topology

- Theo dõi đúng từng physical limb.
- Chân: `hip -> knee -> ankle`.
- Tay: `shoulder -> elbow -> wrist`.
- Không swap left/right.
- Không mirror pose.
- Không đổi bent/straight, lifted/planted hoặc support/swing leg nếu Pose Reference không yêu cầu.
- Foreshortening và occlusion trong Pose Reference phải được giữ nguyên.

## Character consistency

- Mọi frame dùng cùng Character Reference.
- Giữ face, tóc, tỷ lệ cơ thể, quần áo, equipment, màu sắc, vật liệu và art style.
- Tuy nhiên pose correctness có ưu tiên cao hơn visual consistency.

## Direction và camera

- Direction và camera/view lấy từ Action Description.
- Không đổi direction hoặc projection trong frame output.

## QA từng frame

Ưu tiên:

1. direction / camera;
2. limb identity;
3. limb topology;
4. exact pose;
5. character identity;
6. visual polish.

Nếu một frame fail, chỉ regenerate frame đó.

## Output

- Một raw sprite frame.
- Background trong suốt nếu generator hỗ trợ.
- Chưa phải production asset.

## Scope boundary

Skill này không:

- tạo Pose Reference;
- generate nhiều frame trong một ảnh;
- normalize scale;
- normalize anchor;
- compose sprite sheet;
- tạo preview;
- export metadata.
