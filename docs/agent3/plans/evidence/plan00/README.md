# Hồ sơ thực hiện PLAN_00

Ngày thực hiện: 11/10/2026. Người thực hiện: Codex. Phiên bản: `plan00-v1`.

**Trạng thái hiện hành: DONE — phạm vi kỹ thuật `technical-functional-v1`.** Xem [quyết định phạm vi](technical_scope_decision.md) và [gate hiện hành](../gate_00.md). Fixture project đủ để bàn giao PLAN_01; dữ liệu thực tế, independent review và accuracy freeze chuyển DQ-01–05 tại PLAN_05–06. Các ghi nhận thiếu điều kiện bên dưới giữ làm lịch sử và giới hạn dataset, không chặn gate kỹ thuật.

**Cập nhật dữ liệu tải về:** FATURA2 đã qua kiểm checksum/CRC và đối chiếu 50.004 file giải nén. Xem [báo cáo download](fatura_download_check.md); chưa import hoặc chạy model, gate PLAN_00 vẫn thiếu các điều kiện ghi trong báo cáo.

**Cập nhật bước 1–4:** đã [mapping FATURA, chia template và rà pilot 50](fatura_preparation_report.md). Có 20.000 manifest/annotation rows riêng, catalog mới và QA reports. Chưa chạy OCR/train, chưa adjudicate nhãn hoặc mở accuracy eligibility; thông tin “chưa import” ở audit download là snapshot trước bước này.

## Đọc theo thứ tự

1. [Phạm vi capture MVP](scope_capture_mvp.md).
2. [Kiểm kê và phân tích benchmark](inventory.md).
3. [Nguồn tải dữ liệu và cách đặt vào workspace](data_sources_and_downloads.md).
4. [Hướng dẫn nhãn](annotation_guideline.md) và [JSON Schema](../../../../../agent3_tax_compliance/configs/datasets/annotation_v1.schema.json).
5. [Chỉ tiêu nghiệm thu](acceptance_matrix.csv), [coverage](coverage_matrix.csv), [dataset card](dataset_card.md).
6. [Báo cáo gate](../gate_00.md).

Artifacts được sinh khi chạy script:

- `build_summary.json`: hashes, số tài liệu, phiên bản runtime và duplicate diagnostics; không có field thực tế.
- `annotation_examples.json`: 5 ví dụ tổng hợp có bằng chứng tọa độ; chưa có người thứ hai đối chiếu.
- `agent3_tax_compliance/tests/fixtures/ocr/functional_set_v1/`: 30 file chính, nhãn, 2 biến thể duplicate và ca âm tính dạng contract.
- `data invoice/plan00_local/`: manifest đầy đủ, split và duplicate report cục bộ, được bỏ qua bởi git.

## Tái hiện

Từ `D:\financial`, dùng môi trường đã tồn tại; chưa cần cài hoặc chạy OCR:

```powershell
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\prepare_plan00_dataset.py
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\prepare_plan00_dataset.py --verify-only
```

Build ghi lại fixture do project sinh và metadata riêng, không sửa raw, benchmark, model/env hoặc database cũ. Lần đánh giá release phải giữ bộ đã khóa, tăng version trước thay đổi generator/config. Native PDF/scan/image được kiểm cấu trúc và evidence, chưa chạy OCR để đo độ chính xác.

**Gate hiện tại chưa đạt đầy đủ:** người dùng xác nhận chưa có hóa đơn thuế thực tế hoặc người đối chiếu. Có thể bàn giao scope/schema/fixture cho việc chuẩn bị PLAN_01; không đánh dấu PLAN_00 DONE hoặc coi đã nghiệm thu accuracy thực tế.
