# Phân tích tồn đầu kỳ, công suất và SLA

Runner chỉ đọc **bản tích hợp đã khóa**; không chấm lại rules/IF, không mở model, không đọc nhãn/holdout, không ghi vào app hoặc đổi chính sách.

```powershell
$env:PYTHONPATH = "$PWD;.runtime/site-packages"
& $projectPython -X utf8 -B -m sme_fraud.audit_baseline_sla `
  --study reports/integrated_rehearsal_20261028_v2 `
  --output reports/baseline_sla_next
```

Theo [DEVELOPMENT](../../docs/DEVELOPMENT.md) để chọn Python. Output phải chưa tồn tại và tách khỏi đầu vào. Bản đã chạy: `reports/baseline_sla_20261028/`.

## Phép thử

- Tái dựng đúng daily cutoff của phép thử gốc; đối chiếu chính xác bốn baseline 5/120 và 10/240 trên 001/003: thứ tự chọn, scope, phút, kiểu công việc, đồng hồ chờ cũ và tổng tồn.
- Tách phạm vi thực sự đã có **trước** 01/07/2025 khỏi scope mới của hồ sơ cũ hoặc hồ sơ xuất hiện trong kỳ. Không xem mọi case có ngày mở cũ là cùng một đầu việc tồn đầu kỳ.
- Tách đồng hồ `wait_days` cũ, ngày đầu **đầu việc cụ thể** đủ điều kiện pending, số ngày pending không được chọn, và khoảng rời hàng đợi. Lượt tái rà chỉ đủ điều kiện sau khi rà đầu đã được chọn và đến ngày hẹn; không gộp thời gian chờ lần đầu vào thời gian chờ tái rà.
- Giữ deadline SLA của case và deadline tái rà riêng. Ngày chọn chỉ cho một khoảng thời gian, không dựng giờ bắt đầu/hoàn thành. Các nhãn `definitely_on_time/late` chỉ mô tả vị trí **ngày được chọn** so với deadline, không chứng nhận con người hoàn thành SLA.
- Phân biệt hết suất, hết phút, cả hai, phần phút lẻ không đủ cho đầu việc còn lại, lịch nghỉ, scope bị thay và việc chưa được chọn khi hết cửa sổ.
- Chạy 11 cấu hình/cohort: cơ sở; tăng riêng suất/phút; tăng cả hai; giả định đã xử lý tồn đầu kỳ với hai ngân sách; FIFO và EDF trong cùng mức ưu tiên, giữ lượt bắt buộc theo ngày; EDF chỉ giữ hard để chẩn đoán; không giới hạn công suất; chỉ làm thứ Hai–thứ Sáu. **22 cấu hình đều là offline.**

FIFO/EDF có `mandatory_pinned` giữ lượt baseline cao nhất và nontransaction, chỉ dùng ngày tham chiếu hiện tại. Nhánh `hard_only_diagnostic` nới điều kiện giữ các scope nguồn; phải xem các lượt nguồn bị chậm/không còn được chọn, không dùng nó làm đề xuất vận hành.

Kịch bản `opening_precleared` giả định đã hoàn thành scope đầu kỳ cùng lượt tái rà cũ đã đến hạn. Nó cũng thay lịch sử tính chi phí rà tiếp. Đây là giả định đánh giá, không xác nhận ai đã rà thật hoặc cho phép đóng tồn tự động.

Các nhánh có thể tạo/coalesce số phiên bản công việc khác nhau. Đọc `reference_only_work`, `alternative_only_work`, `work_scopes.csv` và `censored.csv`; không chỉ so những lượt xuất hiện ở cả hai nhánh, không cộng chênh lệch thành tỷ lệ nguyên nhân thực tế.

## Đầu ra

| File | Nội dung |
| --- | --- |
| `evaluation_plan.json` | Giả định, cutoff, cấu hình và hash mã/nguồn trước chạy |
| `sme_fraud_*/frames/` | Cache daily case snapshots, opening snapshot tại đúng cutoff, hash nguồn và case builder |
| `<scenario>/selected.csv` | Đồng hồ cũ, thời điểm đủ điều kiện, phân rã chờ và hai deadline cho từng lượt được chọn |
| `<scenario>/blocked.csv`, `daily.csv` | Từng ngày không được chọn và giới hạn đang chặn |
| `<scenario>/work_scopes.csv`, `censored.csv` | Lượt đã rà, phiên bản bị thay/rút, tồn cuối kỳ; không đánh đồng các trạng thái |
| `diagnosis.json`, `scenario_comparison.csv` | Tổng hợp đã đối soát và bảng so sánh |

Muốn lặp phần phân tích trên cache đã kiểm chứng, thêm `--frames-root reports/baseline_sla_20261028`, vẫn chọn output mới. Cache phải khớp nguồn và case builder; không sửa cache để làm đẹp số liệu.

[Mã](../../sme_fraud/audit_baseline_sla.py) · [Test](../../tests/test_audit_baseline_sla.py).
