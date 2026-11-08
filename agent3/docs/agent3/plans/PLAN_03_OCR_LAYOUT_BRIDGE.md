# PLAN_03 — OCR, layout và cầu nối benchmark vào ứng dụng

> Trạng thái triển khai: **DONE — phạm vi kỹ thuật/chức năng**, 12/10/2026. **Mặc định hiện tại: PP-OCRv6 + VietOCR**, đã tách engine registry để thay model bằng cấu hình. [Gate_03](evidence/gate_03.md) bổ sung model switch: 72 tests PASS, 12 schemas, 5 tài liệu/6 trang. Baseline Tesseract ban đầu giữ làm lịch sử; chưa chứng nhận accuracy hóa đơn thật hoặc auto acceptance. [Bằng chứng model switch](evidence/plan03/model_switch/README.md) · [Runbook hiện hành](evidence/plan03/model_switch/runbook.md).

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_02](PLAN_02_INGESTION_PDF.md) · Sau: [PLAN_04](PLAN_04_EXTRACTION_CFR.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Có OCR service ổn định, tái hiện được và trả text/layout/evidence; chọn baseline bằng dữ liệu, không bằng tên model.

- Phụ thuộc bắt buộc: PLAN_02 đạt gate.
- Ước lượng: **4–6 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 4.4, 5, 6.3, 13, 16.
- Đầu vào: Page artifacts, model inventory, functional/calibration splits, budget CPU/GPU và latency.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

OCRResult benchmark schema_version=1.1 có image_id, dimensions, detections, raw_text, timings, metadata; chưa có document/page/envelope identity đầy đủ. Adapter EasyOCR/PPOCR/VietOCR/Tesseract đã có thí nghiệm; VLM có adapter không đồng nghĩa env sẵn sàng. Hai project đều có package src nên không import trực tiếp vào cùng sys.path.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/adapters/ocr/{bridge,protocol,normalizer,worker_client}.py; configs/ocr/; tests/ocr/`

OCRBridgeRequest v1: request_id/source_id/page_id/image_hash/path_or_artifact_ref/timeout/model_config_version. OCRBridgeResponse v1 bọc benchmark OCRResult 1.1 và giữ engine/model/runtime versions, coordinate transform, raw scores, normalized blocks, errors. Raw scores không được gọi là xác suất chính xác của field.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P03-T01 — Khóa giao thức bridge

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Tạo JSONL protocol có schema validation, request/response correlation, version negotiation và giới hạn output. Worker chạy bằng absolute interpreter của env benchmark với cwd riêng.
- Đầu ra: protocol.py, fixtures request/response.
- Kiểm chứng: Không có import collision src; response sai page_id/version bị reject trước canonicalization.

### P03-T02 — Kết nối baseline ít rủi ro

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chạy smoke model đã có env trên một trang; ghi cold/warm latency, RAM/VRAM, model hash. Không tự tải/chạy mọi model nặng.
- Đầu ra: adapter_runtime_matrix.json.
- Kiểm chứng: Chứng minh invocation bằng interpreter thật; thiếu model/env trả MODEL_UNAVAILABLE, không fallback im lặng.

### P03-T03 — Chuẩn hóa detections/layout

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Map polygon, text_raw, confidence, block_type, source_id sang blocks có ID ổn định; giữ raw response. Full-page text không có geometry phải ghi geometry unavailable.
- Đầu ra: normalizer.py.
- Kiểm chứng: Polygon ngoài trang/NaN/confidence sai range bị reject hoặc issue có lý do; không bịa bbox.

### P03-T04 — Hợp nhất native text và OCR

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Dùng page route, deduplicate text layer/ảnh theo vùng; định nghĩa reading order cho cột và table candidates. Giữ provenance từng nguồn thay vì trộn mất dấu.
- Đầu ra: layout_merge.py.
- Kiểm chứng: Tiền xuất hiện hai lần do overlay không thành hai line items; conflict giữ hai candidates.

### P03-T05 — Timeout, retry và cách ly

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Giới hạn worker process/concurrency; phân biệt crash, timeout, transient IO, bad input. Retry bounded; cache theo page hash + preprocess/model/config versions.
- Đầu ra: worker_client.py, retry policy.
- Kiểm chứng: Kill worker chỉ ảnh hưởng job tương ứng; cache không dùng kết quả model/config cũ.

### P03-T06 — So baseline trên cùng split

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chọn 2–3 cấu hình chạy được từ inventory; đo CER/WER, total/date exact match, latency p50/p95, failure rate và khả năng evidence. Tách loadtime khỏi inference.
- Đầu ra: ocr_baseline_comparison.md + run manifests.
- Kiểm chứng: Cùng split/hash/hardware; raw OCR tốt không được suy thành field accuracy tốt.

### P03-T07 — Phân tích lỗi và chọn route

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Phân nhóm dấu tiếng Việt, tiền, ngày, ảnh mờ, bảng nhiều cột. Chọn engine mặc định và fallback có điều kiện/budget, không gọi fallback vô hạn.
- Đầu ra: OCR_SELECTION.md.
- Kiểm chứng: Quyết định kèm hạn chế và nhóm không hỗ trợ; fallback tạo provenance mới và đo riêng.

### P03-T08 — Đóng gói bridge reproducible

- [x] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Lưu command/config/checksum và smoke fixtures; kiểm tra process restart và output mapping.
- Đầu ra: bridge_runbook.md, tests/ocr/.
- Kiểm chứng: Người khác tái hiện smoke không chỉnh đường dẫn hardcode; raw/evidence còn đủ cho PLAN_04.

## 5. Tiến độ bên trong chặng

- Ngày 1: protocol và worker invocation.
- Ngày 2: normalization, geometry và layout merge.
- Ngày 3–4: recovery/caching + benchmark đồng nhất.
- Ngày 5–6: error analysis, lựa chọn baseline và runbook.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] Worker trả đúng text nhưng sai page_id.
- [x] OCR không có boxes; geometry phải UNAVAILABLE.
- [x] Hai engine đọc 8.000.000 và 3.000.000: giữ candidates.
- [x] Timeout giữa trang 2 của tài liệu 3 trang; không coi tài liệu đầy đủ.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** Bridge contract/recovery qua; có baseline tái hiện được và báo cáo giới hạn. Không chuyển sang auto acceptance chỉ dựa CER; model thiếu env không được ghi triển khai xong.

- [x] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [x] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [x] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [x] Ghi `evidence/gate_03.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [x] Bàn giao: PLAN_04 nhận NormalizedDocumentExtraction và evidence blocks; PLAN_05 nhận raw-score distribution, lỗi và run versions.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
