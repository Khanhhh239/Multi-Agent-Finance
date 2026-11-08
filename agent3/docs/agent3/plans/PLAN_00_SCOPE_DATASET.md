# PLAN_00 — Chốt lát cắt OCR/PDF và bộ dữ liệu nghiệm thu

> Trạng thái triển khai: **DONE — phạm vi kỹ thuật technical-functional-v1**, 11/10/2026. Người dùng đã chọn bàn giao nền móng bằng fixture project. Yêu cầu dữ liệu thực tế/reviewer chuyển sang PLAN_05–06 theo [quyết định phạm vi](evidence/plan00/technical_scope_decision.md). Xem [gate report](evidence/gate_00.md).

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: Không có · Sau: [PLAN_01](PLAN_01_CONTRACT_FOUNDATION.md)

**Dữ liệu tải về đã kiểm:** [FATURA2 download report](evidence/plan00/fatura_download_check.md) — archive/giải nén PASS; mapping/split đã hoàn tất theo cập nhật bên dưới. Không có PDF/invoice Việt Nam thực tế; FATURA không là dependency của gate kỹ thuật.

**Tiến độ mới nhất:** [bước 1–4 FATURA đã thực hiện](evidence/plan00/fatura_preparation_report.md): mapping toàn bộ, template-disjoint split và 50 pilot AI-reviewed. Chưa chạy OCR/train; reviewer độc lập/terms và real PDF/invoice coverage còn thiếu.

## 1. Kết quả cần đạt và điều kiện bắt đầu

Có scope, hợp đồng nhãn, metric definitions và fixture do project tạo để phát triển/kiểm chứng kỹ thuật. Không nghiệm thu accuracy hóa đơn thực tế ở chặng này. [Decision record](evidence/plan00/technical_scope_decision.md) quy định phạm vi mới và điều kiện DQ-01–05 chuyển sang PLAN_05–06; các yêu cầu dữ liệu thật/người đối chiếu bên dưới được giữ làm yêu cầu nghiệm thu sau.

- Phụ thuộc bắt buộc: Không; đây là điểm bắt đầu.
- Ước lượng: **2–3 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 1, 4.4, 13, 16, 17.
- Đầu vào: NEW_PLAN; báo cáo OCR hiện có; danh mục tài liệu thực tế có thể dùng; yêu cầu taxpayer/tenant.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Benchmark ở data invoice/ocr_e2e_workflow có adapter, postprocess và báo cáo. MC-OCR chủ yếu có seller, address, timestamp, total_cost; không mặc định có nhãn MST, buyer, VAT hoặc bảng hàng. Báo cáo dev100 ghi all_four_fields_accuracy = 0.0 cho các hệ được so sánh: phải điều tra cách đo và lỗi extraction trước khi đặt kỳ vọng.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`docs/agent3/plans/evidence/; agent3_tax_compliance/tests/fixtures/ocr/; agent3_tax_compliance/configs/datasets/`

DatasetManifest: dataset_id, version, document_id, SHA-256, document_family, source_kind, page_count, permission_basis, split, label_coverage, annotation_version. Mỗi nhãn phân biệt OBSERVED, ABSENT_CONFIRMED, UNREADABLE, NOT_ANNOTATED; NOT_ANNOTATED không phải field thiếu trên chứng từ.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P00-T01 — Khóa sản phẩm mốc đầu

- [x] Hoàn thành: [scope và field matrix](evidence/plan00/scope_capture_mvp.md).
- Thực hiện: Chọn PDF có text, PDF scan và ảnh hóa đơn; xác định trường bắt buộc cho bản demo, trường tùy chọn và trường chưa hỗ trợ. Ghi rõ đây là dữ liệu trích xuất có review, chưa có kết luận thuế.
- Đầu ra: scope_capture_mvp.md và bảng field × document family.
- Kiểm chứng: Mỗi field có ý nghĩa, người sử dụng, nguồn chứng minh và cách xử lý khi không đọc được.

### P00-T02 — Kiểm kê tài sản

- [x] Hoàn thành: [inventory và phân tích benchmark](evidence/plan00/inventory.md).
- Thực hiện: Ghi code, model, env, dữ liệu, báo cáo hiện hữu; phân biệt chạy được, chỉ có adapter, chưa kiểm chứng. Kiểm tra phiên bản và đường dẫn nhưng không di chuyển env/model.
- Đầu ra: inventory.md có đường dẫn tương đối, phiên bản, ngày kiểm tra.
- Kiểm chứng: Không đánh dấu model sẵn sàng chỉ vì có file adapter; không đưa dữ liệu nhạy cảm vào báo cáo.

### P00-T03 — Xây ma trận tập dữ liệu

- [x] Hoàn thành: [coverage matrix](evidence/plan00/coverage_matrix.csv); dataset_manifest.jsonl ở `data invoice/plan00_local/`, schemas ở `agent3_tax_compliance/configs/datasets/`.
- Thực hiện: Tách receipt khỏi tax invoice; tách PDF text/scan/mixed, một/nhiều trang, một/nhiều chứng từ, bảng đơn/đa VAT. Ghi nhóm chưa có dữ liệu.
- Đầu ra: dataset_manifest.jsonl và coverage_matrix.csv.
- Kiểm chứng: Số lượng từng nhóm khớp inventory; vùng thiếu nhãn được công khai.

### P00-T04 — Định nghĩa cách gán nhãn

- [x] DONE kỹ thuật: guideline/schema/examples và generator ground truth. Independent review/adjudication chuyển DQ-02; không đổi annotation thành HUMAN_CONFIRMED.
- Đã có guideline/schema, 20.000 FATURA annotations và [50 pilot AI-reviewed](evidence/plan00/fatura_pilot_review_summary.json); **còn thiếu annotator B/adjudication**, không gọi review AI là xác nhận độc lập của người dùng.
- Thực hiện: Viết hướng dẫn MST seller/buyer, ngày, tiền, currency, invoice number, line item và evidence vùng trang. Nhãn không nhìn thấy phải UNREADABLE, không suy đoán.
- Đầu ra: annotation_guideline.md, schema nhãn và 5 ví dụ đã đối chiếu.
- Kiểm chứng: Người thứ hai gán lại mẫu; mọi bất đồng quan trọng được lưu và phân xử.

### P00-T05 — Tạo bộ ca chức năng nhỏ

- [x] DONE kỹ thuật: 30 file project-generated/10 logical documents. Bộ thực tế bên dưới chuyển DQ-01; không dùng FATURA thay real invoice.
- Đã có 30 project-generated file và FATURA pilot **50 logical invoices từ 25 dev templates**, có 100 ảnh nền trắng/màu đi kèm. Không thay bộ tài liệu thực tế/PDF; coverage real invoice còn thiếu và được theo dõi ở DQ-01, ngoài gate kỹ thuật.
- Thực hiện: Khởi đầu tối thiểu 30 tài liệu nếu đủ quyền sử dụng: 10 text PDF, 10 scan, 10 ảnh; nếu thiếu nhóm thì ghi BLOCKED cho coverage đó. Thêm fixture tổng hợp riêng cho âm tính, không gộp chúng vào độ chính xác thực tế.
- Đầu ra: functional_set_v1 và provenance từng mẫu.
- Kiểm chứng: Bộ 30 chỉ dùng kiểm tra chức năng, không quảng bá là benchmark đại diện.

### P00-T06 — Chia tập chống rò rỉ

- [x] DONE cho fixture kỹ thuật: grouping/splits và known variants đã kiểm. Real/FATURA accuracy freeze chuyển DQ-03/04; MC-OCR tiếp tục QUARANTINE.
- FATURA đã có split 30 dev/10 calibration/10 test templates, không cross-template/family split hoặc exact hash duplicates; labels/terms chưa đủ để freeze accuracy test. MC-OCR vẫn QUARANTINE vì legacy leakage/template/permission audit chưa xong.
- Thực hiện: Chia theo nhóm nhà cung cấp/template, giữ mọi trang của một chứng từ cùng split; phát hiện ảnh trùng và biến thể scan gần trùng. Đóng băng test, tách calibration khỏi evaluation.
- Đầu ra: split_manifest.json, duplicate_report.json.
- Kiểm chứng: Không có document/template group rò giữa các split được tuyên bố độc lập; không tune trên test.

### P00-T07 — Chốt phép đo và mục tiêu

- [x] Hoàn thành: [14 metric definitions](evidence/plan00/acceptance_matrix.csv); target chưa có baseline giữ TBD với owner role và gate chốt, auto acceptance tắt.
- Thực hiện: Định nghĩa exact match cho MST/ngày/tiền, tolerance geometry, accuracy theo field/document, false acceptance, review rate, latency. Chưa có baseline thì để ngưỡng TBD cùng người quyết định và ngày chốt.
- Đầu ra: acceptance_matrix.csv.
- Kiểm chứng: Mỗi metric có tử số, mẫu số, cách xử lý missing label và nhóm tài liệu; không có mục tiêu phần trăm tùy tiện.

### P00-T08 — Đóng gói bàn giao

- [x] Đã đóng gói [dataset card](evidence/plan00/dataset_card.md) và [gate report](evidence/gate_00.md); **gate kỹ thuật PASS, chất lượng thực tế chưa nghiệm thu**.
- Thực hiện: Tạo dataset card: phạm vi, quyền, hạn chế, split hash, storage policy. Lưu mẫu giả lập để test CI, lưu chứng từ thật trong kho hạn chế.
- Đầu ra: dataset_card.md và gate_00.md.
- Kiểm chứng: Tái tạo được manifest; file log không chứa MST hay nội dung chứng từ thật.

## 5. Tiến độ bên trong chặng

- Ngày 1: scope, inventory, ma trận dữ liệu và hướng dẫn nhãn.
- Ngày 2: functional set, split, phép đo; xử lý bất đồng nhãn.
- Ngày 3 dự phòng: bổ sung nhóm thiếu và đóng băng manifest.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] Hai trang fixture syn-08 cùng invoice không tách split; real multipage chưa có.
- [x] Known resize/rotate variants nhận diện được; text/scan/image cùng logical family và split. Real near-duplicate audit vẫn pending.
- [ ] Bàn giao assertion runtime PLAN_04: receipt không có buyer không tự gán buyer từ tenant.
- [ ] Bàn giao assertion metric runtime PLAN_05: nhãn chưa gán không bị tính thành extraction failure. PLAN_00 đã định nghĩa mẫu số; chưa chạy pipeline.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate kỹ thuật:** Scope, annotation guide, manifest/split fixture project và metric definitions có đủ phiên bản; checks hash/status/geometry/splits qua. Dữ liệu thực tế, independent review và accuracy freeze chuyển DQ-01–05. Nhóm chưa đủ điều kiện không được dùng để tuyên bố hỗ trợ thực tế.

- [x] Mỗi task bắt buộc trong phạm vi kỹ thuật có artifact và cách tái hiện kiểm chứng.
- [x] Checks annotation/manifest fixture đã qua; hợp đồng tiền/tenant runtime thuộc gate PLAN_01.
- [x] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [x] Ghi [evidence/gate_00.md](evidence/gate_00.md): input versions, commands, kết quả và blockers.
- [x] Bàn giao: PLAN_01 nhận scope kỹ thuật + schema nhãn; PLAN_02–05 nhận dataset card, split fixture và acceptance matrix. DQ-01–05 còn mở.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
