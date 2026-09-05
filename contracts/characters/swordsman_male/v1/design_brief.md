# Design Brief — Swordsman Nam v1

## 1. Mục tiêu

Tạo concept 2D canonical cho nhân vật Swordsman nam đầu tiên của game mobile 2D phong cách fantasy chibi hand-drawn storybook.

Concept này không phải splash art quảng bá. Đây là nguồn chuẩn để:

- review và khóa character identity;
- làm input tham chiếu cho AI tạo model 3D;
- làm nguồn chuẩn khi tạo skin, hairstyle, armor và weapon variant về sau;
- giảm character drift giữa các lần generation.

Ưu tiên cao nhất là form readability, identity consistency, tỷ lệ chibi ổn định và khả năng chuyển thành model 3D ổn định.

## 2. Fantasy và cảm giác nhân vật

Nhân vật là một kiếm sĩ lang thang trẻ trưởng thành, có phong thái bình tĩnh, tự tin và hơi bụi bặm.

Nhân vật phải nhìn rõ là chibi storybook ngay từ silhouette, nhưng vẫn giữ cảm giác nam trẻ trưởng thành chứ không phải trẻ em.

Không đi theo hướng knight nặng giáp, barbarian cơ bắp, nhân vật realistic hoặc protagonist anime quá trẻ.

Cảm giác mục tiêu:

```text
wandering swordsman
+ mature young adult
+ chibi heroic proportion
+ lean athletic
+ grounded fantasy
+ hand-drawn storybook
```

## 3. Tỷ lệ cơ thể canonical

Target canonical:

- 4.5 đầu chiều cao;
- đầu lớn rõ rệt so với người realistic;
- torso compact và gọn;
- tay và chân được rút ngắn có kiểm soát để giữ tỷ lệ chibi;
- chân vẫn đủ dài để animation chạy, né và chém kiếm đọc rõ silhouette;
- bàn tay và bàn chân hơi lớn hơn tỷ lệ realistic để động tác đọc tốt ở kích thước sprite mobile;
- vai vừa phải, không quá rộng;
- thân hình gọn, athletic theo ngôn ngữ chibi;
- silhouette phải đọc rõ là chibi kể cả khi bỏ chi tiết trang phục.

Không được dùng:

- tỷ lệ 5.25–5.5 đầu của bản draft cũ;
- tỷ lệ semi-realistic;
- tỷ lệ realistic 7–8 đầu;
- super-deformed cực đoan khiến nhân vật trông như trẻ nhỏ.

Các tỷ lệ landmark chi tiết chỉ được freeze sau khi canonical reference đã được duyệt và đo từ artwork thực tế.

## 4. Khuôn mặt

Hướng khuôn mặt:

- nam trẻ trưởng thành;
- mặt hơi góc cạnh nhưng được đơn giản hóa để phù hợp đầu chibi;
- hàm và cằm rõ vừa phải;
- mắt lớn hơn realistic vừa phải để đọc tốt trên đầu chibi;
- eyebrow rõ;
- mũi đơn giản, dễ chuyển sang 3D;
- miệng nhỏ gọn, expression trung tính;
- không beard ở bản canonical đầu tiên;
- biểu cảm neutral/confident;
- không baby-face;
- không làm nhân vật trông như trẻ em.

Khi tạo skin về sau, expression có thể đổi nhưng cấu trúc khuôn mặt không được đổi.

## 5. Tóc canonical ban đầu

Kiểu tóc mặc định đề xuất:

- short layered messy hair;
- medium-short;
- phần mái tách nhẹ;
- silhouette có một chút bất đối xứng tự nhiên;
- gáy ngắn;
- không có tóc dài cần secondary animation phức tạp;
- màu nâu đậm ấm hoặc charcoal-brown;
- tránh đen tuyệt đối để giữ chi tiết trong style watercolor/storybook.

Hairstyle không phải thuộc tính bất biến tuyệt đối. Các skin hoặc appearance variant có thể đổi hairstyle nếu vẫn giữ head shape, hairline cơ bản và character identity.

## 6. Starter Outfit

Starter outfit chỉ là trang phục mặc định phục vụ concept và model 3D đầu tiên. Nó không phải character identity bắt buộc.

Hướng đề xuất:

- linen undershirt màu kem hoặc sáng trung tính;
- leather vest hoặc short tunic màu nâu tối;
- belt rõ nhưng không quá lớn;
- trousers tối màu;
- leather bracers;
- mid-height leather boots;
- có thể có một shoulder strap nhẹ;
- vật liệu đơn giản, dễ đọc ở kích thước sprite nhỏ;
- form trang phục phải tôn được tỷ lệ chibi 4.5 đầu, không kéo silhouette về tỷ lệ người realistic.

Không dùng ở starter set:

- cape dài;
- long coat chạm chân;
- giant shoulder armor;
- helmet che mặt;
- quá nhiều pouch hoặc dây nhỏ;
- plate armor nặng toàn thân;
- chi tiết micro-decoration khó đọc trên mobile.

## 7. Starter Weapon

Weapon mặc định là một thanh kiếm thép fantasy đơn giản, tỷ lệ vừa phải.

Mục tiêu:

- silhouette rõ;
- không quá lớn so với cơ thể;
- dễ dùng làm reference grip khi tạo model 3D và animation;
- không có hình dạng quá đặc thù khiến starter weapon bị nhầm thành character identity.

Starter weapon được phép thay thế hoàn toàn bằng weapon khác trong gameplay hoặc skin về sau.

## 8. Phong cách hình ảnh

Phong cách mục tiêu:

```text
fantasy
chibi
hand-drawn
storybook illustration
watercolor-like fill
pencil/ink contour
soft irregular shading
clean readable silhouette
```

Yêu cầu quan trọng:

- chibi proportion phải rõ trước khi xét texture hoặc trang phục;
- form phải rõ hơn brush texture;
- không dùng painterly noise quá mạnh;
- không tạo lighting dramatic làm mất shape;
- không thêm VFX;
- không thêm motion blur;
- không thêm environment phức tạp;
- không biến style thành anime cel-shading thuần túy;
- không biến style thành realistic PBR concept art;
- không để anatomy drift về semi-realistic chỉ vì armor hoặc pose.

Concept phải đủ sạch để AI tạo model 3D hiểu được geometry của character.

## 9. Cách trình bày canonical concept

Ưu tiên tạo production character reference sheet thay vì một artwork đơn lẻ.

Reference mong muốn có:

- full-body front view;
- full-body 3/4 front view;
- side view;
- back view;
- face close-up nếu bố cục cho phép.

Tất cả view:

- cùng scale;
- cùng canonical 4.5-head proportion;
- neutral pose;
- neutral expression;
- nền đơn giản/off-white;
- ánh sáng trung tính;
- không VFX;
- không cinematic composition.

Pose nên gần A-pose nhẹ hoặc neutral standing pose, tay và chân tách khỏi torso vừa đủ để đọc rõ topology khi tạo model 3D.

## 10. Thuộc tính phải giữ khi tạo skin mới

Skin mới không được tự ý thay đổi:

- character identity;
- cấu trúc khuôn mặt;
- skull/head geometry;
- canonical height;
- canonical 4.5-head ratio;
- underlying chibi body build;
- chiều dài tương đối của tay và chân;
- vị trí tương đối của các joint chính;
- skin tone;
- màu tóc nền nếu contract hiện tại chưa được version hóa lại.

## 11. Thuộc tính được phép thay đổi khi tạo skin mới

Có thể thay đổi:

- hairstyle;
- armor;
- clothing;
- helmet;
- bracer/glove;
- boots;
- belt;
- accessory;
- weapon;
- material;
- palette của trang phục;
- skin theme.

Trang phục có thể thay đổi silhouette mạnh ở bên ngoài nhưng không được làm underlying chibi body proportion bị drift.

## 12. Quy tắc generation skin về sau

Không tạo skin mới chỉ bằng text prompt mô tả lại nhân vật.

Luôn dùng:

```text
Canonical Swordsman Male Reference
        +
Skin Requirement
        ↓
Skin Concept mới
```

Canonical reference quyết định character identity và chibi proportion.

Skin requirement chỉ quyết định các phần được phép thay đổi.

## 13. Điều kiện để chuyển contract sang frozen

Contract v1 chỉ được chuyển từ `design_locked` sang `frozen` sau khi:

1. canonical concept thực tế đã được generate;
2. artwork được review trực quan;
3. character identity và canonical 4.5-head proportion được chấp nhận;
4. các view không mâu thuẫn nghiêm trọng;
5. ảnh đủ rõ để dùng làm input tạo model 3D;
6. evidence thật được commit vào repo;
7. landmark và hash được tạo từ artifact thực tế, không phải số giả.

Nếu concept chưa đạt, tiếp tục chỉnh concept nhưng không âm thầm thay đổi các rule đã khóa trong contract.
