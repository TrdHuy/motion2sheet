# Quy ước Character Contract

## Mục đích

Thư mục này lưu các contract nhận diện nhân vật dùng làm nguồn chuẩn khi tạo concept 2D, model 3D, skin, trang bị và asset animation về sau.

Mục tiêu chính là ngăn character identity bị trôi theo thời gian khi tạo thêm nhiều biến thể ngoại hình.

## Nguyên tắc authority

Mỗi nhân vật phải có một contract được version hóa rõ ràng.

Contract phải phân biệt hai nhóm:

- **Thuộc tính bất biến**: những đặc điểm xác định đây vẫn là cùng một nhân vật và không được tự ý thay đổi giữa các skin.
- **Thuộc tính được phép thay đổi**: những đặc điểm thuộc hairstyle, trang phục, armor, weapon, phụ kiện hoặc skin theme.

Khi có xung đột giữa yêu cầu của một skin mới và Character Contract đã khóa, Character Contract có độ ưu tiên cao hơn.

## Trạng thái contract

### `design_locked`

Dùng khi concept và quy tắc nhận diện đã được thống nhất bằng văn bản nhưng chưa có đầy đủ visual evidence đã duyệt.

Ở trạng thái này:

- được phép generate concept 2D để review;
- chưa được coi ảnh generate đầu tiên là nguồn chuẩn cuối cùng;
- chưa được gọi contract là frozen.

### `frozen`

Chỉ dùng sau khi visual evidence đã được review và chấp nhận.

Khi chuyển sang `frozen`, contract phải có evidence thực tế tương ứng. Evidence sẽ được thêm ở một commit/PR riêng sau khi concept được duyệt.

## Versioning

Không sửa âm thầm contract đã frozen.

Nếu thay đổi làm ảnh hưởng character identity hoặc canonical proportion, phải tạo version mới, ví dụ:

```text
swordsman_male/
├── v1/
└── v2/
```

Các thay đổi chỉ thuộc skin, hairstyle, armor, weapon hoặc phụ kiện không tạo version character mới nếu vẫn tuân contract hiện tại.

## Cấu trúc đề xuất

```text
contracts/characters/
├── README.md
└── <character_id>/
    └── v<version>/
        ├── character_contract.json
        ├── design_brief.md
        └── evidence/              # chỉ tạo khi có evidence thật
```

## Quy tắc evidence

Không tạo placeholder giả cho visual evidence, landmark hoặc hash.

Chỉ thêm evidence khi artifact thực tế đã tồn tại và đã được review.

Các evidence dự kiến sau khi freeze gồm:

```text
canonical_reference.png
face_identity.png
canonical_landmarks.json
evidence_manifest.json
```

## Quy tắc generation về sau

Mọi generation skin hoặc appearance variant phải bắt đầu từ canonical character reference của đúng version đã frozen, không được tạo lại character chỉ từ text prompt độc lập.

Nguyên tắc:

```text
Canonical Character
        +
Skin / Equipment Requirement
        ↓
New Appearance Variant
```

không dùng:

```text
Text description only
        ↓
New character
```

Mục tiêu là cho phép thay đổi trang phục và style mạnh nhưng vẫn giữ nguyên character identity.