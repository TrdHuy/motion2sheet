# Sample workflow: Walk Down, generate từng frame

Folder này là sample input cho workflow AI mới: mỗi lần chỉ generate **một frame**.

## File dùng chung

- `character reference.png`: nguồn chuẩn ngoại hình nhân vật.
- `general prompt.txt`: prompt tổng dùng cho mọi frame trong sample này.

## Pairing bắt buộc

- `walk pose 1.png` <-> `walk description 1.txt`
- `walk pose 2.png` <-> `walk description 2.txt`
- `walk pose 3.png` <-> `walk description 3.txt`
- `walk pose 4.png` <-> `walk description 4.txt`
- `walk pose 5.png` <-> `walk description 5.txt`
- `walk pose 6.png` <-> `walk description 6.txt`
- `walk pose 7.png` <-> `walk description 7.txt`
- `walk pose 8.png` <-> `walk description 8.txt`

Không được ghép pose của frame này với description của frame khác.

## Cách generate frame N

Input:

1. `character reference.png`
2. `walk pose N.png`
3. `walk description N.txt`
4. nội dung trong `general prompt.txt`

Output:

- đúng một raw sprite frame cho N.

Không đưa pose frame khác hoặc raw sprite frame lân cận vào cùng lần generation.

## QA

Ưu tiên kiểm tra:

1. direction và camera;
2. limb identity;
3. hip -> knee -> ankle;
4. shoulder -> elbow -> wrist;
5. exact pose;
6. character identity;
7. visual polish.

Frame nào fail thì chỉ regenerate frame đó.

Sau khi tất cả frame PASS, mới dùng deterministic pipeline để alpha-trim, normalize common scale, align common anchor và compose sprite sheet.

Layout 8 frame sau compose:

```text
F1  F2  F3  F4
F5  F6  F7  F8
```
