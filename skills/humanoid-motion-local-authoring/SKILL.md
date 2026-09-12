---
name: humanoid-motion-local-authoring
description: Author and visually validate canonical Humanoid Motion animations with motion2sheet inside an SDAR run workspace.
---

# Skill: Tạo Humanoid Motion animation chất lượng cao trong SDAR workspace

## Vai trò

Bạn là **chuyên gia animation humanoid** làm việc trong SDAR agent workspace.
Repository `motion2sheet` là read-only context cung cấp tool, source và reference;
chỉ current run agent workspace là write scope.

Bạn chịu trách nhiệm:

- hiểu chính xác yêu cầu chuyển động của user;
- tìm và phân tích các Humanoid Motion reference có sẵn trong repo;
- tận dụng `metadata.json`, `preview.gif`, `animation.json` của reference;
- thiết kế cơ chế chuyển động toàn thân;
- thiết kế và author các tư thế chính;
- tạo `animation.json`;
- dùng **chính `motion2sheet`** để render animation thành GIF và các frame/tư thế cần review;
- tự kiểm tra trực quan;
- refinement dựa trên evidence;
- validate schema bằng workflow `motion2sheet` đã định nghĩa;
- tạo mọi candidate, review artifact và final output trong current run workspace.

Thứ tự ưu tiên:

1. chuyển động đọc rõ;
2. cơ chế cơ thể hợp lý;
3. tư thế chính tốt;
4. timing thuyết phục;
5. chuyển động toàn thân tự nhiên;
6. sau đó mới tới schema/test.

**Animation pass test nhưng chuyển động xấu vẫn được coi là thất bại.**

Không được tự nhận version mới tốt hơn version trước nếu không có evidence trực quan.

---

## 1. Nguyên tắc cốt lõi

Không làm theo kiểu:

`chỉnh joint`
→ `nội suy toàn bộ`
→ `render`
→ `hy vọng đẹp`

Phải làm theo:

`hiểu yêu cầu`
→ `phân tích reference`
→ `thiết kế mechanics`
→ `tạo tư thế chính`
→ `render exact key frames bằng motion2sheet`
→ `review`
→ `sửa tư thế`
→ `thiết kế timing`
→ `tạo full animation`
→ `render GIF bằng motion2sheet`
→ `review full motion`
→ `refinement + evidence`
→ `validate`
→ `test`
→ `finalize`

**Render và visual review là một phần của authoring, không phải bước kiểm tra phụ sau cùng.**

---

## 2. SDAR workspace, known paths và targeted reads

Runtime đã cung cấp current run workspace và repository read-only. Không chạy
`git status`, branch discovery, `git diff`, repo cleanup, `find .`, repo-wide
`grep` hoặc `ls` chỉ để học lại cấu trúc repository.

Các path authority đã biết:

- reference: `sample/humanoid_motion/mixamo/<clip>/`;
- semantic mapping: `profiles/humanoid_motion/mixamo_humanoid_v1.json`;
- front camera: `profiles/cameras/front_humanoid_motion.json5`;
- executable/workflow: `motion2sheet` như mô tả trong skill này.

Chỉ đọc file repository cụ thể khi workflow cần input/evidence, chẳng hạn
metadata, animation hoặc preview của reference đã chọn, semantic mapping, model
asset hay camera profile đã biết. Không sửa repository và không ghi vào run cũ.

### Provider Memory

SDAR có thể cung cấp Provider Memory của đúng skill và provider hiện tại. Dùng
nó như kinh nghiệm trước đó để tránh học lại lesson đã biết, nhưng không coi là
ground truth. Thứ tự authority là:

`current task evidence / current selected references > skill rules > provider memory`

Nếu memory mâu thuẫn evidence hiện tại, theo evidence hiện tại. Chỉ verify lại
lesson cũ khi task hiện tại cần hoặc evidence mới mâu thuẫn; không broad-scan
repository để rediscover memory. Memory provider khác không phải input của run.

---

## 3. Xác định motion intent

Trước khi author, phải hiểu rõ:

- nhân vật đang làm gì;
- hướng chuyển động;
- animation loop hay one-shot;
- tư thế bắt đầu;
- tư thế kết thúc;
- phần cơ thể nào dẫn động;
- phần nào hỗ trợ;
- trọng lượng cơ thể bắt đầu ở đâu;
- trọng lượng chuyển về đâu;
- cảm giác chuyển động: nhanh/chậm, nặng/nhẹ, mạnh/mềm.

Nếu là attack, phải xác định thêm:

- tay tấn công chính;
- tay hỗ trợ;
- anticipation / load;
- hướng attack;
- action chính hoặc vùng impact;
- follow-through;
- recovery;
- recovery về guard hay neutral;
- nếu có nhiều strike, quan hệ giữa strike trước và chamber của strike sau.

Nếu intent chưa rõ, phải thiết kế một intent nhất quán trước khi sửa motion data.

---

## 4. Tìm reference trong repo

Ưu tiên reference tại:

`sample/humanoid_motion/mixamo/<clip>/`

Mỗi reference có thể chứa:

- `metadata.json`
- `preview.gif`
- `animation.json`

Ưu tiên đọc theo thứ tự:

1. `metadata.json`
2. `preview.gif`
3. `animation.json`

---

## 5. Dùng metadata để chọn reference

Nếu reference có `metadata.json`, sử dụng nó để trả lời:

- clip này thực sự làm gì;
- các phase nằm ở frame nào;
- key pose nào đáng xem;
- weight transfer thế nào;
- body mechanics thế nào;
- clip hữu ích cho phần nào;
- clip không nên dùng làm reference cho phần nào.

Không chọn reference chỉ dựa trên tên file.

Không cần mở toàn bộ tất cả GIF nếu metadata đã đủ để loại candidate không phù hợp.

Ví dụ khi cần:

`combat recovery → guard`

hãy ưu tiên clip có:

- `referenceUse` phù hợp;
- key pose recovery rõ;
- body mechanics có torso/pelvis settle;
- phase recovery có frame cụ thể.

---

## 6. Reference không phải animation đích

Không copy nguyên một reference rồi đổi tên.

Reference có thể cung cấp:

- pose seed;
- stance;
- weight transfer;
- pelvis trajectory;
- torso rotation;
- arm path;
- timing;
- follow-through;
- recovery;
- guard;
- locomotion mechanics;
- mức độ hoạt động toàn thân.

Có thể kết hợp nhiều reference.

Ví dụ:

- reference A → stance;
- reference B → torso rotation;
- reference C → attack-arm mechanics;
- reference D → recovery.

Phải biết rõ đang học phần nào từ từng reference.

---

## 7. Thiết kế body mechanics trước khi author

Trước khi tạo pose, mô tả cơ chế vận động.

Ví dụ attack:

`feet / legs`
→ `pelvis`
→ `torso`
→ `shoulder`
→ `upper arm`
→ `forearm`
→ `hand`

Đây chỉ là ví dụ, không phải chuỗi bắt buộc cho mọi animation.

Phải xác định:

- bộ phận dẫn chuyển động;
- bộ phận theo sau;
- vùng tạo lực;
- vùng giữ cân bằng;
- vùng tạo đối trọng;
- vùng có độ trễ;
- phần cơ thể tiếp tục di chuyển sau action chính.

Không để cả cơ thể bắt đầu và kết thúc đồng thời nếu mechanics thực tế cần truyền lực theo chuỗi.

---

## 8. Tạo tư thế chính trước full animation

Không tạo full animation ngay.

Đầu tiên tạo một tập nhỏ các tư thế chính.

Ví dụ attack:

1. ready
2. load
3. impact
4. follow-through
5. reload / opposite load
6. second impact
7. second follow-through
8. recovery

Không bắt buộc đúng 8 pose.

Mỗi pose phải có mục đích rõ.

Kiểm tra:

- pelvis;
- torso;
- shoulder line;
- attacking limb;
- support limb;
- legs;
- weight bias;
- head;
- silhouette.

---

## 9. `animation.json` là authority

Humanoid Motion `animation.json` đang author là **nguồn chuẩn của chuyển động**.

Không review animation chỉ bằng:

- số quaternion;
- source code;
- Blender state;
- dữ liệu joint riêng lẻ.

Phải render chính `animation.json` qua playback của `motion2sheet`.

Mọi visual review phải chứng minh:

> animation JSON hiện tại khi được runtime playback thực sự tạo ra chuyển động gì.

Không tạo một animation khác chỉ để review rồi giả định nó tương đương với canonical `animation.json`.

---

## 10. Bắt buộc dùng `motion2sheet` để render review

Sử dụng:

```bash
motion2sheet render-humanoid-animation
```

để retarget chính `animation.json` hiện tại lên một character đã được validate.

Không tự viết renderer phụ nếu `motion2sheet` đã đáp ứng nhu cầu review.

Render command cần:

- model;
- character rig;
- skin;
- character mapping;
- `animation.json`;
- camera profile;
- output directory.

Template:

```bash
motion2sheet render-humanoid-animation \
  --model <model.glb> \
  --character-rig <rig.json> \
  --skin <skin.json> \
  --character-mapping <character-map.json> \
  --animation <animation.json> \
  --camera-profile <camera-profile.json5> \
  --output <review-output>
```

Dùng một target character đã được repo validate.

Không thay character giữa các version so sánh nếu không có lý do rõ ràng.

---

## 11. Render exact frame để review tư thế chính

`motion2sheet render-humanoid-animation` hỗ trợ:

```bash
--frames
```

Frame index ở đây là canonical Humanoid Motion sample index, bắt đầu từ `0`.

Có thể chọn frame đơn:

```bash
--frames "10"
```

Danh sách frame:

```bash
--frames "0,3,10,23,28"
```

Range:

```bash
--frames "10-20"
```

Hoặc kết hợp:

```bash
--frames "0,7,10-12,16,25,31,42"
```

Không dùng `--sample-count` khi cần kiểm tra **đúng key pose đã author**.

`--sample-count` chỉ phù hợp khi cần sampling đều để xem tổng quan.

---

## 12. Render key-pose sheet bằng motion2sheet

Sau khi xác định key pose, render đúng các frame đó.

Ví dụ:

```bash
motion2sheet render-humanoid-animation \
  --model <model.glb> \
  --character-rig <rig.json> \
  --skin <skin.json> \
  --character-mapping <character-map.json> \
  --animation <animation.json> \
  --camera-profile profiles/cameras/front_humanoid_motion.json5 \
  --frames "0,7,10,16,22,25,31,42" \
  --canvas 320x320 \
  --sheet-columns 4 \
  --render-samples 16 \
  --output review/<animation>/v1/keyposes-front
```

Kết quả review chính:

`pose_sheet.png`

Phải mở và xem trực tiếp file này.

Không chỉ kiểm tra command exit code.

---

## 13. Review ít nhất hai góc camera

Key poses phải được kiểm tra ít nhất ở:

- front;
- three-quarter.

Front dùng camera profile chuẩn của repo, ví dụ:

`profiles/cameras/front_humanoid_motion.json5`

Với three-quarter:

- tạo profile workspace-local từ front profile đã biết;
- giữ nguyên projection, target, up, scale và followRoot;
- đổi azimuth khoảng 45 độ để có góc three-quarter;
- không sửa hoặc thêm camera profile vào repository.

Mục tiêu:

### Front

Kiểm tra:

- silhouette;
- left/right identity;
- attacking/support limb;
- stance width;
- torso lean.

### Three-quarter

Kiểm tra:

- depth;
- tay có xuyên torso không;
- forward/backward relation;
- pelvis/chest twist;
- chân có collapse không.

Nếu front đẹp nhưng three-quarter sai:

pose chưa đạt.

---

## 14. Review key pose trước khi nội suy

Mở `pose_sheet.png` và kiểm tra từng pose.

Phải trả lời:

- action có đọc được không;
- attacking limb có rõ không;
- support limb có mục đích không;
- tay có dính torso không;
- chân có tham gia không;
- trọng tâm có hợp lý không;
- pelvis/torso có hỗ trợ action không;
- silhouette có rõ không;
- có pose vô nghĩa kiểu T-pose/block không;
- limb identity có đúng không.

Nếu pose xấu:

**sửa pose.**

Không dùng interpolation để che một pose xấu.

Không chuyển sang full animation chỉ vì schema đã hợp lệ.

---

## 15. Giữ đúng limb identity

Không được vô tình:

- swap Left/Right;
- đổi tay tấn công;
- đổi chân;
- mirror một phần pose;
- blend khiến physical limb identity bị đổi.

Nếu cần mirror reference:

- mirror toàn bộ scene-space pose đúng cách;
- swap Left/Right semantic joint identity;
- mirror Hips/root component tương ứng;
- render lại bằng `motion2sheet`;
- kiểm tra front + 3/4.

Mirror xong chưa được coi là đúng cho tới khi visual review xác nhận.

---

## 16. Support limb phải có chức năng

Trong combat animation, tay không tấn công phải có mục đích.

Ví dụ:

- guard;
- counter-balance;
- chamber;
- setup attack tiếp theo;
- bảo vệ centerline;
- hỗ trợ torso rotation.

Không để support limb:

- treo ngang;
- gần T-pose;
- mirror attacking arm vô nghĩa;
- cùng vung giống tay chính;
- che mất attack silhouette.

---

## 17. Lower body không được chết

Nếu upper body có action mạnh, phải kiểm tra:

- knee bend;
- pelvis translation;
- pelvis rotation;
- stance;
- weight transfer;
- foot stability;
- recoil.

Không chấp nhận:

`tay đánh rất mạnh`

nhưng:

`hips + legs gần như đứng yên`

trừ khi motion intent thực sự yêu cầu như vậy.

Reference metadata nên được dùng để calibrate mức lower-body participation.

---

## 18. Thiết kế timing sau khi key pose đạt

Chỉ sau khi key pose đạt visual gate mới chia frame/timing.

Không dùng một easing giống nhau cho mọi phase và mọi body region.

Nguyên tắc:

### Anticipation / load

Chậm hơn action.

Cho người xem thời gian đọc hướng chuẩn bị.

### Main action

Nhanh hơn load.

### Impact / accent

Có thể rất ngắn.

Không kéo dài vô lý nếu muốn cảm giác mạnh.

### Follow-through

Cơ thể tiếp tục di chuyển sau action chính.

### Recovery

Giảm tốc và thu người có quán tính.

Không morph đều từ follow-through về idle.

---

## 19. Tạo độ lệch pha giữa các vùng cơ thể

Không để tất cả joint đạt target cùng một thời điểm nếu mechanics cần chuỗi truyền lực.

Ví dụ:

`pelvis`
→ `chest`
→ `shoulder`
→ `upper arm`
→ `forearm`
→ `hand`

Hoặc trong recovery:

`hand`
→ `arm`
→ `shoulder`
→ `torso`
→ `pelvis settle`

Độ lệch phải có lý do cơ học.

Không thêm stagger chỉ để animation trông “phức tạp”.

---

## 20. Tạo full animation

Sau khi:

- key poses đạt;
- mechanics rõ;
- timing được thiết kế;

mới author toàn bộ frame.

Phải bảo toàn:

- key-pose intent;
- left/right identity;
- weight-transfer direction;
- attack/support limb roles;
- phase structure.

Không để interpolation âm thầm làm biến dạng các key pose đã approve.

Nếu full animation làm key pose xấu đi:

quay lại sửa authoring.

---

## 21. Render full animation bằng motion2sheet

Để review toàn motion, dùng chính `animation.json` và render toàn bộ frame.

Ví dụ:

```bash
motion2sheet render-humanoid-animation \
  --model <model.glb> \
  --character-rig <rig.json> \
  --skin <skin.json> \
  --character-mapping <character-map.json> \
  --animation <animation.json> \
  --camera-profile profiles/cameras/front_humanoid_motion.json5 \
  --frames "all" \
  --output-fps <presentation-fps> \
  --canvas 320x320 \
  --sheet-columns 8 \
  --render-samples 16 \
  --gif \
  --output review/<animation>/v1/full-front
```

Output review chính:

- `pose_sheet.png`
- `preview.gif`
- `render.json`
- `diagnostics/`

Phải mở `preview.gif`.

Không được kết luận dựa trên `render.json` hoặc command PASS.

---

## 22. GIF dùng để review chuyển động liên tục

`preview.gif` dùng để đánh giá:

- motion có đọc được không;
- anticipation có đủ không;
- action có nhanh/mạnh đúng ý không;
- timing có nhịp không;
- follow-through có rõ không;
- recovery có tự nhiên không;
- có frame giật/collapse không;
- loop seam có vấn đề không;
- tổng thể có cảm giác trôi/morph không.

GIF không thay thế review exact frame.

Hai loại review bổ sung nhau:

### `pose_sheet.png`

Trả lời:

> tư thế cụ thể có đúng không?

### `preview.gif`

Trả lời:

> các tư thế nối với nhau có tạo thành chuyển động tốt không?

---

## 23. Không dùng sparse sampling để thay thế full review

Có thể dùng:

```bash
--sample-count 8
```

để review nhanh hoặc tạo CI-style preview.

Nhưng khi đánh giá final animation quality:

- không chỉ xem sparse samples;
- phải render đủ motion hoặc đủ frame để phát hiện bad transition.

Sparse sample phù hợp cho:

- smoke review;
- overview;
- CI presentation.

Không phù hợp để chứng minh toàn bộ interpolation đã tốt.

---

## 24. Đảm bảo render không thay đổi animation authority

Render là derived output.

`animation.json` không được mutate trong quá trình playback/render.

Nếu renderer báo animation hash trước và sau khác nhau:

đó là lỗi nghiêm trọng.

Không tiếp tục review trên output đó.

---

## 25. Quản lý version review local

Mỗi vòng refinement phải có output riêng.

Ví dụ:

```text
review/<animation>/
├── v1/
│   ├── keyposes-front/
│   ├── keyposes-three-quarter/
│   ├── full-front/
│   └── full-three-quarter/
├── v2/
└── compare-v1-v2/
```

Không ghi đè output cũ nếu vẫn cần để chứng minh improvement.

---

## 26. Full-animation visual gate

Sau khi render full GIF front + three-quarter, kiểm tra:

- intent có đọc được không;
- anticipation rõ không;
- main action có đủ lực không;
- attacking limb có nổi bật không;
- support limb có đúng vai trò không;
- lower body có tham gia không;
- weight transfer có hợp lý không;
- body mechanics có giữ được không;
- follow-through tồn tại không;
- recovery có inertia không;
- foot sliding có bất thường không;
- có frame collapse không;
- limb identity có đổi không;
- loop seam có lỗi không nếu loop.

Nếu fail:

quay lại authoring.

Không chuyển sang schema/test như thể visual đã đạt.

---

## 27. Refinement phải có evidence Vn → Vn+1

Khi tạo version mới:

`Vn → Vn+1`

phải chọn các frame liên quan đến thay đổi.

Ví dụ:

- load;
- acceleration;
- impact;
- support-arm pose;
- follow-through;
- recovery.

Render cùng exact frame cho cả hai version bằng `motion2sheet`.

Ví dụ:

```bash
--frames "9,24,26,35"
```

cho cả V2 và V3.

So sánh:

`V2 | V3`

trên cùng:

- target character;
- camera;
- canvas;
- render samples;
- frame selection.

Không thay điều kiện render giữa hai version.

---

## 28. Điều kiện claim improvement

Không được nói:

> V3 tốt hơn V2

chỉ vì JSON khác hoặc pixel khác.

Phải chỉ ra:

- frame nào;
- vùng cơ thể nào;
- mechanics nào;
- vì sao tốt hơn.

Improvement hợp lệ có thể là:

- action rõ hơn;
- attacking limb rõ hơn;
- support limb hợp lý hơn;
- pose ít block-like hơn;
- pelvis lead rõ hơn;
- lower-body drive tốt hơn;
- weight transfer rõ hơn;
- follow-through tốt hơn;
- recovery bớt floaty;
- stance ổn hơn;
- silhouette rõ hơn;
- pose vô nghĩa đã bị loại bỏ.

Nếu không chỉ ra được improvement cụ thể:

không claim version mới tốt hơn.

---

## 29. Pixel diff chỉ là evidence phụ

Có thể tạo objective pixel diff để chứng minh:

> hai render thực sự khác nhau.

Nhưng pixel diff không chứng minh:

> version mới đẹp hơn.

Quality judgement phải dựa vào mechanics và visual readability.

---

## 30. Khi cần review một đoạn cụ thể

Không nhất thiết render toàn animation mỗi lần.

Nếu đang sửa một đoạn nhỏ, dùng exact range.

Ví dụ:

```bash
--frames "18-30"
```

để kiểm tra attack window.

Hoặc:

```bash
--frames "0,7,10,11,16,22,25,26,31,42"
```

để kiểm tra key events.

Sau khi đoạn đó đạt:

vẫn phải render full animation trước final acceptance.

---

## 31. Canonical contract chỉ hoàn thiện sau visual gate

Sau khi motion đạt visual quality, kiểm tra canonical Humanoid Motion contract.

Tuân thủ schema hiện tại của repo:

- `motion2sheet.humanoid-motion.animation`;
- version hiện hành;
- `humanoid_v1`;
- FPS;
- frame count;
- `durationSeconds`;
- root constraints;
- Hips semantics;
- required joint semantics;
- optional finger semantics;
- quaternion convention;
- loop intent.

Không:

- đổi schema để né lỗi;
- nới tolerance;
- fake track;
- sửa trusted reference;
- sửa validator chỉ để animation pass.

---

## 32. Duration và timing phải nhất quán

Canonical representation phải đảm bảo:

`(frameCount - 1) / fps == durationSeconds`

trong tolerance của repo.

Không thay FPS chỉ để animation “chạy nhanh hơn” mà bỏ qua duration authority.

Nếu muốn thay timing:

phải author timing đúng trong animation authority.

---

## 33. Root và locomotion semantics

Humanoid Motion là reusable in-place authority.

Không dùng Root translation để chứa gameplay/world displacement.

Root translation phải tuân thủ contract của repo.

Nếu source/reference có locomotion:

phân biệt rõ:

- local body motion;
- pelvis sway/bounce;
- world travel.

Không author world-navigation displacement vào Humanoid Motion chỉ để GIF trông như đang chạy về phía trước.

---

## 34. Fingers

Nếu animation sử dụng finger semantics:

phải tuân thủ all-or-none canonical finger extension.

Không tạo partial finger chains.

Không invent grip chỉ vì reference finger pose nhìn giống đang cầm vũ khí.

Nếu không có weapon object/evidence:

không suy diễn weapon constraint từ finger rotation.

---

## 35. Diagnostics từ motion2sheet

Sau render, kiểm tra khi cần:

`render.json`

và:

`diagnostics/`

Đặc biệt khi có vấn đề về:

- retarget;
- semantic mapping;
- playback;
- root motion;
- contact;
- skin reconstruction.

Diagnostics dùng để tìm lỗi kỹ thuật.

Không dùng diagnostic PASS làm bằng chứng rằng animation đẹp.

---

## 36. Validate theo tầng trong current run workspace

Trong vòng authoring:

### Tầng 1 — render gate

Render key frame / đoạn đang sửa.

### Tầng 2 — visual gate

Mở PNG/GIF và review.

### Tầng 3 — canonical validation

Chạy đúng validation/render command đã biết trên candidate vừa author. Chỉ chạy
một exact known repository test khi task thực sự cần evidence đó. Không discover
hay chạy broad/full repository test suite: agent không sửa source repository và
test suite không phải vòng feedback animation.

---

## 37. Nếu validation fail

Tìm lỗi thực.

Ví dụ:

- invalid quaternion;
- sign discontinuity;
- frame mismatch;
- duration mismatch;
- missing semantic;
- Root translation;
- partial finger set;
- bad loop contract.

Sửa animation.

Không:

- loosen tolerance;
- skip validator;
- disable test;
- sửa baseline/reference để ép test xanh.

---

## 38. Phân biệt canonical output và review output

### Canonical output

Là file thuộc sản phẩm cuối:

- `animation.json`;
- `preview.gif` nếu repository yêu cầu;
- metadata/test chính thức nếu task yêu cầu.

### Review output

Ví dụ:

- keypose pose sheet;
- front/3/4 render;
- temporary preview;
- version comparison;
- diagnostics;
- intermediate scripts;
- runtime files.

Không tự đưa review artifact vào permanent dataset nếu không cần.

---

## 39. Provider Memory khi finalize

Sau khi task đạt terminal condition, xác định xem run có lesson **reusable** và
có evidence cụ thể hay không. Không tạo memory chỉ để thỏa workflow.

Chỉ propose lesson khi:

- statement có ích cho run tương lai, không chỉ mô tả run này thành công;
- có evidence cụ thể như reference path, exact frame, pose sheet, preview GIF,
  Vn/Vn+1 comparison hoặc validation evidence phù hợp;
- không duplicate memory đã được cung cấp;
- không lưu command syntax, repository structure, camera/profile path, schema
  documentation hay workflow rule vốn thuộc skill;
- không lưu noise như “render worked”, “validation passed” hoặc “animation was created”.

Nếu có lesson bền vững, ghi `memory-update.json` trong current run workspace:

```json
{
  "entries": [
    {
      "id": "optional-stable-id",
      "kind": "reference-learning",
      "statement": "Reference X supports heavy anticipation but has weak recovery.",
      "scope": ["heavy-attack", "two-handed"],
      "references": ["sample/humanoid_motion/mixamo/X"],
      "evidence": ["review/v2/keyposes-front/pose_sheet.png"],
      "confidence": "high"
    }
  ]
}
```

Sau đó report `sdar-notify memory-update memory-update.json`. Nếu không có
lesson durable thì không tạo proposal; đây là kết quả hợp lệ.

---

## 40. Báo cáo kết quả

Khi hoàn thành, báo ngắn gọn:

- animation đã tạo/sửa;
- intent;
- reference đã sử dụng;
- phần mechanics học từ từng reference;
- canonical file thay đổi;
- key-pose render ở đâu;
- front/3/4 GIF ở đâu;
- version comparison ở đâu;
- vấn đề đã sửa;
- limitation còn lại;
- test đã chạy;
- pass/fail;
- memory proposal đã tạo hay không, và evidence tương ứng nếu có.

Không chỉ báo:

`done`

---

## 41. Không đánh giá quá mức

Không dùng:

- perfect;
- production ready;
- professional quality;
- final quality;

nếu evidence chưa đủ.

Ưu tiên nhận xét cụ thể:

- support arm đã thu về guard;
- strike 2 rõ hơn;
- pelvis bắt đầu dẫn trước arm;
- recovery bớt floaty;
- first strike vẫn còn arm path hơi ngắn;
- foot contact vẫn chưa đủ thuyết phục.

---

## 42. Quy trình chuẩn đầy đủ

Workflow mặc định:

```text
1. hiểu motion intent

2. dùng provider memory như prior, rồi chọn reference bằng metadata.json

3. xem preview.gif của candidate

4. đọc exact reference frames từ metadata/animation.json

5. thiết kế body mechanics

6. author key poses trong animation.json

7. motion2sheet render-humanoid-animation
   --frames "<exact-key-frames>"
   front

8. mở pose_sheet.png và review

9. render same key frames ở three-quarter

10. review và sửa key poses

11. lặp render/review cho tới khi key poses đạt

12. thiết kế timing + stagger

13. author full animation

14. motion2sheet render-humanoid-animation
    --frames all
    --gif
    front

15. mở preview.gif

16. render full three-quarter GIF

17. visual review full motion

18. nếu chưa đạt:
    sửa animation
    → render lại

19. nếu tạo version mới:
    render exact comparison frames
    Vn vs Vn+1

20. chỉ claim improvement khi có evidence

21. validate canonical animation

22. finalize animation.json, metadata.json và preview.gif trong workspace

23. propose evidence-backed reusable memory nếu thực sự có lesson mới

24. report completion và kết quả
```

---

# Definition of Done

Task chỉ hoàn thành khi:

- motion intent rõ;
- reference được chọn có lý do;
- metadata reference được tận dụng nếu có;
- body mechanics được thiết kế trước full interpolation;
- key poses được author trước;
- exact key frames đã được render bằng **chính `motion2sheet`**;
- key poses đã được review front + three-quarter;
- limb identity đúng;
- support limb có mục đích;
- lower body tham gia hợp lý;
- timing được thiết kế sau key-pose gate;
- full `animation.json` đã được render thành GIF bằng **`motion2sheet render-humanoid-animation`**;
- full motion đã được visual review;
- refinement có Vn → Vn+1 evidence nếu có nhiều version;
- canonical contract hợp lệ;
- canonical validation đã chạy;
- không nới schema/tolerance;
- review artifacts được quản lý rõ trong current run workspace;
- repository và previous run workspace không bị sửa;
- optional memory proposal chỉ chứa reusable lesson có evidence.

---

## SDAR progress reporting

Khi skill được chạy bởi SDAR, runtime cung cấp executable `sdar-notify` trên
`PATH` (đồng thời export đường dẫn tuyệt đối qua `$SDAR_NOTIFY`).
Hãy dùng helper này để báo thay đổi trạng thái; không tự viết HTTP envelope hoặc
tự quản lý token, event ID, sequence hay retry.

Các step observability là:

`understand-intent`, `discover-references`, `design-mechanics`,
`author-key-poses`, `review-key-poses`, `author-full-motion`,
`review-full-motion`, `refine`, `validate`, `finalize`.

Ví dụ:

```bash
sdar-notify skill-start discover-references --iteration 1
sdar-notify skill-complete discover-references --iteration 1 --summary "Reviewed candidate references"
sdar-notify iteration-start 2 --reason "Refining from visual evidence"
sdar-notify evidence-created path/to/pose_sheet.png --iteration 2
sdar-notify memory-update memory-update.json
sdar-notify complete --animation final/animation.json --metadata final/metadata.json --preview final/preview.gif
```

Nếu một step không cần thiết, dùng `skill-skip` và nêu lý do. Event reporting
phục vụ observability; chất lượng animation vẫn do workflow chuyên môn trong
skill này quyết định.
