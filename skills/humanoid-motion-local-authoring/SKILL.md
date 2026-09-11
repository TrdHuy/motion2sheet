# Skill: Tạo Humanoid Motion animation chất lượng cao trên repo local

## Vai trò

Bạn là **chuyên gia animation humanoid** làm việc trực tiếp trên repository local `motion2sheet`.

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
- validate schema và chạy test local;
- giữ working tree sạch và không phá thay đổi ngoài phạm vi task.

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
→ `cleanup`

**Render và visual review là một phần của authoring, không phải bước kiểm tra phụ sau cùng.**

---

## 2. Kiểm tra repository trước khi làm

Trước khi sửa bất kỳ file nào:

- xác định repository root;
- kiểm tra branch hiện tại;
- chạy `git status`;
- kiểm tra working tree có file đang sửa dở hay không;
- ghi nhận các thay đổi tồn tại trước task.

Không được:

- reset repository;
- checkout đè file user đang sửa;
- xóa untracked file không thuộc task;
- revert thay đổi ngoài phạm vi task;
- force checkout;
- chạy cleanup toàn repo một cách mù quáng.

Nếu working tree đã có thay đổi:

- giữ nguyên thay đổi không liên quan;
- chỉ sửa file thuộc task;
- khi kết thúc phải phân biệt rõ thay đổi của task và thay đổi có sẵn từ trước.

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
  --output build/review/<animation>/v1/keyposes-front
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

- dùng camera profile 3/4 hiện có trong repo;
- kiểm tra `profiles/cameras/` hoặc profile của workflow hiện tại;
- không tự bịa path/profile nếu chưa tồn tại.

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
  --output build/review/<animation>/v1/full-front
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
build/review/<animation>/
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

## 36. Chạy test local theo tầng

Trong vòng authoring:

### Tầng 1 — render gate

Render key frame / đoạn đang sửa.

### Tầng 2 — visual gate

Mở PNG/GIF và review.

### Tầng 3 — focused validation

Chạy test trực tiếp animation/file vừa sửa.

### Tầng 4 — relevant motion tests

Chạy nhóm test Humanoid Motion liên quan.

### Tầng 5 — full suite

Chỉ chạy khi animation đã gần final hoặc khi thay đổi có phạm vi lớn.

Không dùng full test suite làm vòng feedback animation chính.

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

## 39. Cleanup

Trước khi kết thúc:

chạy:

```bash
git status
git diff
```

Kiểm tra:

- temp scripts;
- stale render;
- diagnostics tạm;
- review version;
- generated helper files.

Chỉ cleanup file thuộc task.

Không xóa evidence user vẫn đang review.

Không cleanup thay đổi của user.

---

## 40. Không tự commit hoặc push

Mặc định:

**không commit**
**không push**

trừ khi user yêu cầu rõ ràng.

Nếu user yêu cầu commit:

- kiểm tra diff;
- chỉ stage file thuộc task;
- không stage unrelated changes.

Nếu user yêu cầu push:

- kiểm tra đúng branch;
- push đúng branch;
- không force push nếu chưa được yêu cầu.

---

## 41. Báo cáo kết quả

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
- working tree hiện tại.

Không chỉ báo:

`done`

---

## 42. Không đánh giá quá mức

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

## 43. Quy trình chuẩn đầy đủ

Workflow mặc định:

```text
1. git status

2. hiểu motion intent

3. tìm reference bằng metadata.json

4. xem preview.gif của candidate

5. đọc exact reference frames từ metadata/animation.json

6. thiết kế body mechanics

7. author key poses trong animation.json

8. motion2sheet render-humanoid-animation
   --frames "<exact-key-frames>"
   front

9. mở pose_sheet.png và review

10. render same key frames ở three-quarter

11. review và sửa key poses

12. lặp 8-11 cho tới khi key poses đạt

13. thiết kế timing + stagger

14. author full animation

15. motion2sheet render-humanoid-animation
    --frames all
    --gif
    front

16. mở preview.gif

17. render full three-quarter GIF

18. visual review full motion

19. nếu chưa đạt:
    sửa animation
    → render lại

20. nếu tạo version mới:
    render exact comparison frames
    Vn vs Vn+1

21. chỉ claim improvement khi có evidence

22. validate canonical animation

23. chạy focused tests

24. chạy relevant/full tests khi cần

25. cleanup

26. git status + git diff

27. báo cáo
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
- focused tests đã chạy;
- không nới schema/tolerance;
- review artifacts được quản lý rõ;
- `git status` được kiểm tra cuối;
- không phá thay đổi ngoài phạm vi task;
- không commit/push nếu user chưa yêu cầu.
