# PLAN_04 — Trích xuất field, line items và chuẩn hóa CFR

> Trạng thái triển khai: **DONE — phạm vi kỹ thuật/tổng hợp**, 12/10/2026. [Gate_04](evidence/gate_04.md): 99 tests PASS, 7 schema mới, 15 tài liệu/17 trang; có field/line-item extraction, CFR producer, Decimal/identity/VAT, rederive/DAG/evidence, persistence/API/CLI. OCR mặc định vẫn **PP-OCRv6 + VietOCR**; extraction dùng hợp đồng chung. [Baseline và giới hạn](evidence/plan04/extraction_baseline.md): native 162/162 field; hybrid 37/49 field, còn 6 wrong PRESENT; mọi artifact review. Accuracy thực tế/calibration chưa nghiệm thu. [Runbook](evidence/plan04/runbook.md).

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_03](PLAN_03_OCR_LAYOUT_BRIDGE.md) · Sau: [PLAN_05](PLAN_05_QUALITY_CALIBRATION.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Biến text/layout thành CFR từng field có evidence, candidates và trạng thái trung thực; có thể tái derive sau sửa.

- Phụ thuộc bắt buộc: PLAN_01 và PLAN_03 đạt gate.
- Ước lượng: **5–8 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 4.4, 5, 7.2.2, 8.
- Đầu vào: Normalized document extraction, field definitions, taxpayer master revision, annotated set.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Benchmark field_extractor dùng heuristic seller/address/time/total, score nhân hệ số và mặc định currency VND ở một số nhánh. Có thể tái dùng parser sau test nhưng không copy score thành CALIBRATED hoặc coi currency mặc định là quan sát từ tài liệu.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các module sau đã triển khai và kiểm chứng trong phạm vi kỹ thuật:

`agent3_tax_compliance/src/extraction/{invoice_fields,tables,candidates}.py; src/canonicalization/{normalize,derive,identity}.py; tests/extraction_v1/`

Có thêm `extraction/{contracts,service,vat_group_builder,evidence,repository,api,cli}.py`, migration `004_extraction.sql` và `contracts/extraction-v1/`. Các checklist đã tích dưới đây chỉ xác nhận phạm vi và giới hạn tại [gate_04](evidence/gate_04.md), không xác nhận production accuracy.

ExtractionCandidate có candidate_id, semantic_field, raw/normalized value, evidence_refs, method_version, raw_score. CFR giữ observed riêng derived, derivation inputs/version. items[*].item_id immutable; line_number là thuộc tính hiển thị. item discovery COMPLETE/INCOMPLETE/UNKNOWN; VAT category tạm chưa biết nếu chưa có taxonomy evidence.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P04-T01 — Trích field header và parties

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Dùng label/region/context để lấy invoice no/series/date, seller/buyer name/MST/address; giữ candidate cạnh tranh. Không lấy MST đầu tiên làm seller vô điều kiện.
- Đầu ra: invoice_fields.py + field-specific fixtures.
- Kiểm chứng: Hóa đơn có hai MST không đảo parties; field không thấy là MISSING/AMBIGUOUS theo evidence, không tự chứng minh absent.

### P04-T02 — Chuẩn hóa tiền/ngày/currency

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Parser decimal xử lý dấu phân cách, số âm, ngoặc, rounding; ngày locale rõ ràng. Currency từ tài liệu hoặc deterministic profile có provenance, không suy chỉ từ tiền có dấu chấm.
- Đầu ra: normalize.py, parser fixtures.
- Kiểm chứng: 1.234,56 và 1,234.56 không bị chọn sai im lặng; ngày 03/04 mơ hồ giữ candidates.

### P04-T03 — Trích bảng có identity ổn định

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Phát hiện header/rows/continuation, assign item_id khi tạo item lần đầu; giữ ID qua correction/reorder. Document re-extraction dùng explicit reconciliation mapping, không hash theo line index/giá trị dễ đổi.
- Đầu ra: tables.py, item_identity_map.
- Kiểm chứng: Bảng sang trang không mất hàng; reorder/sửa tên hàng không đổi item_id; split/merge ghi lineage.

### P04-T04 — Chuẩn hóa VAT treatment/group

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Parse rate và nhãn KCT/KKKNT/0%; không dùng số rate để tự tạo legal category. Nhóm VAT có group_id + item_refs + discovery status, tổng bằng Decimal.
- Đầu ra: vat_group_builder.py.
- Kiểm chứng: KCT/KKKNT rate NOT_APPLICABLE/null; 0% TAXABLE_RATE vẫn có rate 0; mỗi ref trỏ item_id tồn tại.

### P04-T05 — Derive identity và totals

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: So seller/buyer với taxpayer theo master revision và quan hệ branch hiệu lực; derive direction/counterparty/totals nhưng giữ original amounts. Tạo dependency DAG cho derived fields.
- Đầu ra: derive.py, derivation_manifest.
- Kiểm chứng: Không xác định direction → AMBIGUOUS/null; sửa seller MST invalidates direction/counterparty và bước phụ thuộc.

### P04-T06 — Xử lý nhiều chứng từ/trang thiếu

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Xác định document boundary trong upload; nếu chưa chắc thì review splitting thay vì ghép totals. Trang thiếu và bảng chưa đọc hết đặt discovery INCOMPLETE/UNKNOWN.
- Đầu ra: segmentation issues + CFR partial fixtures.
- Kiểm chứng: Không đánh dấu COMPLETE chỉ vì parser trả items=[]; nhiều invoice không bị gộp thành một record.

### P04-T07 — Xây provenance end-to-end

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Gắn field tới raw span/block/page + preprocessing/OCR/extractor versions; candidate nào được chọn phải nêu selection reason. Lưu cả observed và derived evidence graph.
- Đầu ra: provenance resolver.
- Kiểm chứng: Click/resolve evidence ra đúng vùng gốc; không tạo circular references hay field không có nguồn.

### P04-T08 — Chạy extraction evaluation

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Đo từng field, party role, tiền và row recall trên split được phép; phân biệt parser lỗi với OCR lỗi và không đủ nhãn. Lưu false acceptance samples.
- Đầu ra: extraction_baseline.md và predicted CFR snapshots.
- Kiểm chứng: Các mẫu test khóa không dùng tune; báo cáo cả nhóm thất bại, không chỉ average tốt.

### P04-T09 — Đóng interface rederive

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Hàm canonicalize/rederive thuần theo observed revision + master/profile versions; không phụ thuộc hidden global state.
- Đầu ra: canonicalization API + replay fixtures.
- Kiểm chứng: Cùng input/versions cho cùng derived output; reviewer correction có thể gọi lại trước Layer 6.

## 5. Tiến độ bên trong chặng

- Ngày 1–2: header/parties, money/date normalization.
- Ngày 3–4: items/VAT groups, document boundary và identity.
- Ngày 5–6: derivation/provenance + evaluation.
- Ngày 7–8 dự phòng: bảng nhiều trang và nhóm lỗi lớn nhất.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] Seller và buyer cùng tên gần giống nhưng khác MST.
- [x] KCT, KKKNT và VAT 0% trong cùng bảng.
- [x] Bảng trống vì OCR mất trang không phải không có hàng.
- [x] Invoice total khác sum items; giữ cả hai và issue, không sửa raw.
- [x] Một PDF có hai hóa đơn; không merge làm một.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** CFR schema pass cho mọi fixture trong scope; tiền không float; item identity/provenance/rederive được kiểm tra; accuracy thấp được phản ánh bằng review hoặc giới hạn phạm vi, không che bằng confidence.

- [x] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [x] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [x] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [x] Ghi `evidence/gate_04.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [x] Bàn giao: PLAN_05 nhận CFR + candidate scores + evaluation errors; PLAN_06 nhận evidence resolver và dependency DAG.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh worker/API/replay và kiểm chứng đã ghi trong [runbook PLAN_04](evidence/plan04/runbook.md). Metric từng field, wrong PRESENT và giới hạn table/layout nằm trong [baseline report](evidence/plan04/extraction_baseline.md). Tiếp theo PLAN_05 quality/calibration; DQ-01–05 về dữ liệu thực và nhãn độc lập vẫn chưa được nghiệm thu.
