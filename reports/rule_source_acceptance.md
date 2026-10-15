# Nghiệm thu F1/C4/E2/F2/F3/F4 trên nguồn SME thật

## Kết luận hiện tại

Logic và đối chứng mô phỏng của sáu rule đã có, nhưng **chưa rule nào được nghiệm thu trên nguồn SME thật trong workspace**. Dataset nghiệp vụ chính dùng cho báo cáo readiness (`sme_fraud_003`) không khai báo các bảng HR/ERP/công nợ này; bộ `rule_evidence_phase4` có nguồn fixture mô phỏng. Kết quả 301/301 source case phase 4 là kiểm tra đặc tả và tính nhân quả, không phải precision/recall thực địa.

Đã bổ sung `sme_fraud.real_source_acceptance` để nghiệm thu mà không dùng kết quả rule làm nhãn. Quy trình khóa hash dự đoán trước, phát phiếu chấm không có cột prediction, yêu cầu người rà soát và người phân xử khác nhau, rồi mới mở so sánh. Vì thế việc chọn hồ sơ và gán kết luận không thể vô tình tối ưu theo hit của rule.

## Nguồn bắt buộc

| Rule | Nguồn phải có trong manifest |
| --- | --- |
| F1 | `journal_audit_log`, `closing_periods`, `materiality_policies` |
| C4 | `leave_periods`, `system_actions`, `leave_activity_authorizations` |
| E2 | `employment_events`, `payroll_settlements` |
| F2 | `workflow_policies`, `override_events` |
| F3 | `document_series`, `document_register`, `document_cancellations` |
| F4 | `receivable_invoices`, `receipt_allocations`, `receipt_coverage`, `receivable_explanations` |

Mỗi file phải có schema đầy đủ, checksum đúng manifest và có thể rỗng nếu thực tế không phát sinh. File rỗng không tự chứng minh nguồn đầy đủ. Chủ nguồn phải ký coverage cho từng công ty/rule, ghi `data_origin=real_sme_export`, khoảng bao phủ đến cutoff và mã bằng chứng trích xuất.

## Đơn vị nghiệm thu

- F1, C4, E2, F2 và nhánh trùng số F3: giao dịch.
- Khoảng trống F3: dải số chứng từ đã khóa.
- F4: hóa đơn phải thu tại cutoff.

Kết luận `condition_present` chỉ nói predicate của rule có đúng hay không. Nó không đồng nghĩa kết luận gian lận. Hồ sơ thiếu dữ kiện dùng `information_gap=1`; các hồ sơ này không bị ép thành âm tính.

## Cổng chấp nhận

Một rule chỉ có trạng thái `accepted` khi đồng thời thỏa:

1. Toàn bộ file nguồn có schema/checksum hợp lệ và dataset không phải generator mô phỏng.
2. Coverage nguồn thật bao phủ mọi công ty trong phạm vi và toàn cửa sổ đánh giá.
3. Tất cả đơn vị trong phiếu đã có kết luận mù, lý do, bằng chứng và phân xử độc lập.
4. Chính sách ngưỡng đã ở trạng thái `approved` trước khi xem kết quả.
5. Đủ số dương/âm và precision, recall, tỷ lệ information gap đạt ngưỡng riêng từng rule.

Báo cáo ghi cả số đếm, point estimate có trọng số và Wilson 95% theo đơn vị rà soát. Trọng số phục vụ thiết kế mẫu; khoảng Wilson vẫn dựa trên số đơn vị thô và không thay thế bootstrap theo doanh nghiệp nếu mẫu có tương quan mạnh.

Các trạng thái chưa đạt gồm `awaiting_real_data`, `awaiting_source_coverage`, `awaiting_independent_review`, `awaiting_criteria`, `insufficient_review` và `rejected`. Chỉ `accepted` là nghiệm thu.

## Cách chạy

Header nguồn nằm tại [examples/phase4_sources](../examples/phase4_sources/README.md). Mẫu coverage, kết luận và ngưỡng nằm tại [examples/real_source_acceptance](../examples/real_source_acceptance/README.md).

```powershell
python -m sme_fraud.real_source_acceptance prepare `
  --data data/sme_real_export `
  --from 2025-01-01T00:00:00+07:00 `
  --as-of 2025-12-31T23:59:59+07:00 `
  --criteria reviews/acceptance_criteria.json `
  --output reports/real_acceptance/prepared

python -m sme_fraud.real_source_acceptance evaluate `
  --data data/sme_real_export `
  --prepared reports/real_acceptance/prepared `
  --reviews reviews/review_conclusions.csv `
  --coverage reviews/coverage_attestations.csv `
  --criteria reviews/acceptance_criteria.json `
  --output reports/real_acceptance/result
```

Ngưỡng phải được phê duyệt trước `prepare`; hash của file ngưỡng được khóa cùng prediction để không thể chỉnh theo kết quả review. `prepare` giữ toàn bộ lịch sử trước `--from` khi chấm để các rule nhân quả có baseline, nhưng chỉ đưa đơn vị trong cửa sổ vào phiếu. Mọi giao dịch sau `--as-of` bị loại khỏi lần chấm. `evaluate` tính lại và từ chối nếu dataset, packet, mã rule, ngưỡng hoặc prediction khác commitment.

## Việc cần từ dữ liệu thật

Cần một bản xuất đã ẩn danh ở cấp nguồn với ID ổn định, thời điểm quan sát, lịch sử revision và người chịu trách nhiệm coverage. Không đưa `labels.csv`, kết luận điều tra cũ hoặc kết quả rule vào detector. Kết luận rà soát chỉ được nhập sau bước `prepare` và do nhóm nghiệp vụ độc lập thực hiện.
