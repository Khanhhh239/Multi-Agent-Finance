# FATURA — kết quả bước 1–4

Ngày: **11/10/2026**. Dataset: `fatura-mapped-v1`. Scope: annotation preparation và QA cục bộ; chưa chạy OCR/train, chưa là tập accuracy được human-adjudicate.

**Đã thực hiện:** mapping toàn bộ 10.000 instance, chia template-disjoint dev/calibration/test, chọn và rà pilot 50 instance, cập nhật manifests/catalog và gate. Source archive, ảnh, nhãn gốc và split tác giả giữ nguyên.

## 1. Mapping annotation

Cấu hình: [fatura_mapping_v1.json](../../../../../agent3_tax_compliance/configs/datasets/fatura_mapping_v1.json). Dùng JSON Schema annotation/manifest v1 đã có; không tạo schema CFR mới hoặc sửa contract để vừa dữ liệu.

| Field chuẩn | Source key | Quy tắc | Instance có OBSERVED proposal |
|---|---|---|---:|
| seller.name | SELLER_NAME | Giữ tên từ nhãn, không suy từ logo/email | 6.800 |
| buyer.name | BUYER / BILL_TO | Bỏ label rồi lấy dòng tên; không lấy SHIP_TO/SEND_TO | 7.400 |
| invoice.issue_date | DATE | ISO khi ngày rõ; không dùng DUE_DATE; ngày số mơ hồ để chưa gán | 9.798 |
| invoice.number | NUMBER | Bỏ label INVOICE/#/NO/NUMBER/ID; giữ leading zeros | 8.800 |
| totals.gross | TOTAL | Decimal string; không thay bằng AMOUNT_DUE | 8.000 |
| totals.net | SUB_TOTAL | Decimal string từ nguồn, không tự tính lại | 6.797 |
| totals.vat | TAX | Chỉ khi text ghi rõ VAT và có một amount; GST không tự là VAT | 3.800 |
| currency | TOTAL/SUB_TOTAL/TAX/AMOUNT_DUE | Chỉ ISO code rõ, không suy từ `$`; candidate conflict/không đủ nghĩa giữ chưa gán | 6.129 |
| seller.tax_id / buyer.tax_id | Không map GSTIN | Không đổi mã nước ngoài thành MST Việt Nam | 0 |
| vat_category | Không có | Không suy nhóm pháp lý từ rate/tax label | 0 |
| items | TABLE chỉ là region | Chưa có row/cell semantics đã xác minh | 0 |

Số trên là **proposal có đủ cấu trúc**, không phải field đã được người độc lập xác nhận đúng. Annotation `review_status=SECOND_REVIEW_PENDING`; tất cả manifest rows `accuracy_evaluation_eligible=false`. Không có confidence giả hoặc accuracy được công bố.

Không đủ nhãn/normalization/geometry → `NOT_ANNOTATED`, value/raw_text null trong nhãn chuẩn; source candidates và raw text giữ ở provenance sidecar. Không chuyển thành `ABSENT_CONFIRMED` chỉ vì key không có hoặc parser chưa map được. Có 3.273 field instances normalization chưa đủ; phần lớn cần currency semantics/khả năng parse, không phải OCR failure. Coverage chi tiết có cả split/status trong local CSV.

## 2. Tọa độ và provenance

Original bbox là hai góc với frame gốc dưới trái. Image/HF frame gốc trên trái. Với width W, height H lấy từ ảnh, chuyển:

```text
x0 = min(ax,bx) / W
y0 = (H - max(ay,by)) / H
x1 = max(ax,bx) / W
y1 = (H - min(ay,by)) / H
```

Sau chuyển kiểm bounds và đối chiếu HF pixel boxes với sai khác tối đa 1,1 pixel, phù hợp rounding trong nhãn HF. Candidate không match hình học sẽ không thành OBSERVED. Không clip out-of-bounds tùy tiện. Mọi candidate đã dùng đạt đối chiếu HF; không có mismatch hình học trong lần build này. Đây là cross-format consistency, chưa chứng minh field nằm đúng text trên mọi ảnh.

Provenance lưu source annotation paths/hashes, bbox gốc, bbox chuẩn, source key, raw value, normalized candidate và lý do unresolved. Mỗi white/colored variant có annotation sở hữu đúng document ID, cùng logical duplicate family. Kiểm dimensions hai ảnh bằng nhau; rà trực quan pilot trên **ảnh trắng**, chưa rà từng ảnh màu hoặc toàn bộ pixel.

## 3. Chia tập của project

Seed `20261011`; gán theo template ID và thứ tự hash ổn định. Các template đã mở khảo sát trước đó (1,7,10,17,47,50) giữ trong dev. Không dùng kết quả model để chọn tập. Split gốc tác giả chỉ làm provenance, không chỉnh CSV đi kèm.

| Split | Templates | Logical invoices | Image variants |
|---|---:|---:|---:|
| dev | 30 | 6.000 | 12.000 |
| calibration | 10 | 2.000 | 4.000 |
| test | 10 | 2.000 | 4.000 |
| Tổng | 50 | 10.000 | 20.000 |

| Split | Template IDs |
|---|---|
| dev | 1,3,4,7,9,10,11,13,16,17,18,20,25,27,28,29,30,31,32,35,36,37,39,41,42,43,45,46,47,50 |
| calibration | 5,8,12,14,21,23,26,38,44,49 |
| test | 2,6,15,19,22,24,33,34,40,48 |

Mỗi source template chỉ ở một tập; cả 200 instance và hai nền cùng template đều theo tập đó. Kiểm exact hash toàn 20.000 ảnh không có ảnh trùng cross-split. `template-disjoint` ở đây theo IDs của tác giả, chưa là chứng minh near-template/layout styles hoàn toàn độc lập. Chưa chạy audit perceptual/semantic similarity của mọi cặp template; cần xem xét trước claim generalization rộng.

Đã khóa assignments/hash cho replay kỹ thuật, nhưng `accuracy_test_frozen=false`: chưa hoàn tất terms/independent label review. Test không được dùng tune/parser-debug từ model predictions; generic schema/coordinate audit không phải model evaluation. Khi đủ điều kiện, freeze version mới với exposure history rõ.

## 4. Pilot 50 instance

25 dev templates, mỗi template lấy instance 0 và 100. Tổng 50 logical invoices có 100 ảnh nguồn đi kèm, không tính thành 100 samples độc lập. Không đưa calibration/test vào pilot.

Templates: **1,3,4,7,9,10,11,13,16,17,18,20,27,29,30,31,32,35,36,37,41,45,46,47,50**.

Đã mở/rà 50 ảnh trắng bằng Codex, đối chiếu header roles/date/number và printed amounts. Đây là **AI visual inspection**, không là annotator B độc lập hoặc transcription từng ký tự/cell. Có [review notes riêng](../../../../../agent3_tax_compliance/configs/datasets/fatura_pilot_visual_review_v1.json), 41 facts nhập thủ công từ quan sát ảnh được kiểm lại với annotation sau mapping, và [review summary](fatura_pilot_review_summary.json).

| Phát hiện | Xử lý |
|---|---|
| Parser giữ label ID trong invoice number | Đã sửa và test hồi quy; pilot facts kiểm đúng identifier |
| Template 18/30 chỉ có SHIP_TO | Không tự lấy recipient làm buyer |
| Template 36/37 có AMOUNT_DUE/DUE_AMOUNT nhưng không TOTAL tương ứng | Giữ gross NOT_ANNOTATED, không alias bừa |
| `$` không rõ ISO; một số core fields không hiện trong supported labels | Giữ partial labels, không tự điền |
| Source có due date trước issue date hoặc totals không khớp phép cộng đơn giản | Giữ printed source values; không dùng làm đáp án tuân thủ thuế |
| TABLE bbox không đủ cell/row semantics | Chưa map items; giữ raw annotation để nghiên cứu sau |

`pilot_review.csv` ghi review AI cho 50 IDs và independent review PENDING. Annotations không đổi sang ADJUDICATED. Người đối chiếu tiếp theo cần xem critical fields/bbox, các trường missing/ambiguous và source semantics trước mở accuracy eligibility.

## 5. Artifacts và cách chạy

Artifacts đầy đủ nằm trong ignored local data, không chép dataset/nhãn thực tế vào repo fixture CI:

```text
data invoice/plan00_local/
  dataset_catalog.json                 # giữ dataset PLAN_00 trước + thêm FATURA
  fatura_v1/
    dataset_manifest.jsonl            # 20.000 variant rows, dùng chung schema v1
    annotations/                     # 20.000 annotation files có ID riêng
    provenance.jsonl                 # 10.000 logical source mappings/candidates
    split_manifest.json              # template assignments + manifest hash
    annotation_checksums.json         # checksum snapshot cho mọi annotation
    field_coverage.csv                # logical counts theo split/field/status
    pilot_manifest.json              # 50 logical IDs + image/annotation paths
    pilot_review.csv                  # AI review và phần chờ độc lập
```

Báo cáo không có full label text: [mapping summary](fatura_mapping_summary.json), [contract validation](fatura_contract_validation.json) và [pilot review](fatura_pilot_review_summary.json). Main manifest PLAN_00 cũ và hash cũ không bị ghi đè. FATURA thêm dưới dataset ID riêng trong catalog, chưa ghép thành một accuracy benchmark với MC-OCR.

[Coverage tổng](coverage_matrix.csv) bổ sung các dòng `origin=SYNTHETIC_FATURA`, đếm **image variants** (12.000/4.000/4.000); không cộng chúng như logical invoices độc lập. Bảng split và field coverage ở trên đếm logical instances. Chạy lại generator PLAN_00 gốc có thể tái tạo CSV nền; chạy finalize pilot sau đó sẽ bổ sung lại FATURA mà không nhân đôi các dòng.

Từ `D:\financial`:

```powershell
# Build/rebuild draft dataset; không sửa sources hoặc chạy OCR.
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\prepare_fatura_dataset.py
# Ghi lại các review AI đã thực hiện trong phiên, không tự xem ảnh bằng script.
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\finalize_fatura_pilot.py
# Validate với jsonschema đã có ở system Python; không cần cài vào venv cũ.
python .\scripts\validate_fatura_contracts.py
# Semantic regression tests dùng unittest sẵn có.
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\test_fatura_preparation.py
```

Importer cũng chạy verify toàn bộ nguồn/hash/ownership/geometry/grouping sau build. Muốn chỉ verify artifacts hiện có dùng `prepare_fatura_dataset.py --verify-only`. Sau validation, annotation checksum snapshot sẽ bị từ chối nếu sửa nội dung rồi chạy validate lại; cần version/review dataset trước tạo snapshot mới. Rebuild ghi lại pilot CSV về PENDING; lệnh finalize nối lại review notes đã có và chỉ thành công khi curated facts còn khớp. Nếu thay model/annotation/parser rồi review không còn phù hợp, tạo review version mới thay vì tự đổi facts để test xanh.

## 6. Kết quả kiểm chứng và gate

- 20.000 image variants / 10.000 logical instances đầy đủ, source image hashes được kiểm.
- 20.000 annotation files sở hữu đúng manifest row; geometry nằm trong trang, value/status/field coverage nhất quán.
- Template và duplicate family không cross-split; 50 pilot IDs duy nhất, dev-only.
- 8 semantic regression tests qua: ngày mơ hồ, Decimal tiền lớn, rate vs amount, tax vs VAT, buyer block, invoice ID/leading zeros, geometry frame và split exposure.
- JSON Schema annotation/manifest validate toàn bộ đầu ra; checksum snapshot giúp phát hiện sửa nhãn sau QA.
- 50 AI visual reviews đã ghi; 41 curated fact checks qua. Không có OCR accuracy, training, tax verdict hoặc human adjudication.

**Gate PLAN_00 vẫn BLOCKED một phần**, không vì bước chuẩn bị FATURA chưa làm, mà vì scope gốc còn PDF/invoice Việt Nam thực tế, independent reviewer và terms provenance. Các bước 1–4 được yêu cầu đã có đầu ra kỹ thuật review được. Scope/schema/fixture/mapped pilot có thể bàn giao để chuẩn bị contracts PLAN_01; không tự triển khai PLAN_01 trong phiên này.
