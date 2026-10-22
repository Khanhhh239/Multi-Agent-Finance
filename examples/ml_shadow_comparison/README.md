# So sánh IF shadow với rules + graph + A5 trên cùng ngân sách

`sme_fraud.compare_shadow` chạy phép thử kỹ thuật trên nguồn mô phỏng reporting 001/003. Nó giữ model và kết quả detector đã khóa, xuất điểm IF riêng, dựng lại hồ sơ theo cutoff mỗi ngày và dùng hai sổ nghiên cứu độc lập cho hai nhánh. Không ghi feedback vận hành, sửa queue hoặc gửi thông báo.

```powershell
python -B -m sme_fraud.compare_shadow `
  --dataset data/synthetic_sources_20261017_v2/sme_fraud_001 `
  --baseline reports/pipeline_rehearsal_20261018_v2/sme_fraud_001 `
  --model reports/model_source_sync_20261022/sme_fraud_001/model/isolation_forest.joblib `
  --model-sha256 6c2f9313fd9888437734c5894fdbc96bd6e283370031ba91ecc408387657a4a7 `
  --scope reports/model_source_sync_20261022/scope.evaluation.json `
  --output reports/my_if_shadow_comparison_001
```

Dùng Python/thư viện khớp artifact. Output phải là thư mục mới ngoài nguồn/model/baseline. CLI chỉ nhận nguồn `is_synthetic=true, role=reporting`; chưa phải quy trình pilot trên SME thật.

## Kế hoạch cố định trước khi chạy

- Ngân sách chính: **5 hồ sơ/120 phút/công ty/ngày**; đối chứng: **10 hồ sơ/240 phút/công ty/ngày**. Chạy mọi ngày lịch như cấu hình mô phỏng hiện có, không suy diễn lịch nghỉ hoặc ngày lễ. Đây là trần bằng nhau, không yêu cầu số phút tiêu dùng thực tế của hai nhánh luôn bằng nhau.
- Scope là cửa sổ evaluation đã khai báo của model. Cutoff mỗi ngày là 00:00 đầu ngày kế tiếp theo giờ Việt Nam, loại trừ mốc cuối. Kế hoạch/hash model/nguồn/baseline/mã được ghi trước khi chấm điểm.
- Baseline giữ thứ tự priority giảm dần, điểm rules giảm dần, thời điểm mở và ID. Detector phải đã bật graph và A5 theo rolling account; kiểm tra source manifest và các file frozen trước khi dùng.
- Nhánh IF giữ các lượt `cao_nhat` và hồ sơ ngoài loại `transaction` do baseline chọn mà nhánh IF chưa rà. IF chỉ đổi thứ tự vị trí có đủ điểm thành viên trong cùng mức ưu tiên, lấy max điểm thành viên đã biết tại cutoff. Vị trí thiếu điểm giữ thứ tự baseline; không điền 0. Không mở hồ sơ mới chỉ vì điểm IF.
- Mỗi ngày dựng hồ sơ từ prefix scores/hits/batch/source findings; không dùng max score, thành viên hoặc ước lượng phút của snapshot cuối để quyết định trong quá khứ. Toàn bộ hồ sơ trước giai đoạn đánh giá còn hoạt động ở cutoff đầu tham gia tồn ban đầu; không giả lập rằng đã có người rà đóng chúng.
- Sổ nghiên cứu không đếm lại work scope đã rà. Scope mới cần lượt rà tiếp, pending cũ chưa rà được gộp về phiên bản hiện tại; source đã hết điều kiện được rút khỏi pending. Bản ghi nguồn chỉ đổi cutoff hoặc `overdue_days` không được xem là bằng chứng mới. Thay đổi số dư/chứng từ/trạng thái nguồn vẫn tạo work scope mới.
- Hồ sơ thiếu dữ kiện được ghi là đã thực hiện lượt yêu cầu/rà mô phỏng và chờ thông tin; không tạo kết luận hợp lệ hoặc bất thường. Nguồn có lịch rà lại hiện hữu được phép một lượt follow-up khi đến hạn. Chi phí là ước lượng as-of; lượt tiếp theo dùng `max(10, ceil(phút cơ sở/2))`, chưa phải thời gian đo từ kế toán.

## Đầu ra và cách đọc

`status.json` phải là `complete`; `failed`/`running` không phải kết quả hoàn tất. `evaluation_plan.json` lưu giả định và hash trước khi chạy. `if_scores/` giữ kết quả suy luận tách biệt. Mỗi `budget_5/` hoặc `budget_10/` gồm:

- `daily_comparison.csv`: số lượt/phút, giao nhau, các lựa chọn chỉ có ở từng nhánh, số suất bắt buộc và tồn từng công ty/ngày.
- `selections.private.csv`: work scope, nhánh, thứ tự, điểm IF, số phút ước lượng và thời gian chờ. Không đưa file này cho người rà mù.
- `summary.json`: tổng hợp ngân sách, độ phủ, kích thước hồ sơ, thay đổi lựa chọn và độ trễ; `actionable_gain/precision/recall` để trống khi chưa có outcome độc lập.

`review_union.blind.csv` chuẩn bị hợp các work scope đã chọn, không chứa nhánh/thứ hạng/điểm IF. ID reviewer và kết luận còn trống; file này chưa phải người dùng đã review. Lượt kỹ thuật chưa chạy mẫu tham chiếu ngẫu nhiên hoặc phân xử độc lập, vì vậy không dùng tập này để suy precision/recall toàn quần thể.

Mã dựng queue có thể khác hash ghi trong detector snapshot. Runner chỉ cho phép trường hợp riêng `case_queue.py` khi mã hiện tại tái dựng khớp toàn bộ scope ở snapshot cuối; mã phụ thuộc khác vẫn phải khớp. Kế hoạch ghi cả hash cũ/mới và dùng cách dựng queue hiện tại đã khóa trên cùng đầu ra detector. Không có snapshot trung gian lịch sử để khẳng định replay từng ngày trùng một phiên bản cũ; các ngày được tái dựng nhân quả cho phép thử hiện tại.

`comparison.json` và `predictions_frozen.json` chốt kết quả. Các chỉ số là tải và thay đổi lựa chọn trên mô phỏng, không phải gian lận được xác nhận hoặc lợi ích vận hành. Trước pilot thật vẫn cần nguồn được nghiệm thu, ngân sách/lịch/người rà/tiêu chí được chốt, mẫu tham chiếu và phân xử; không chỉnh model/ngưỡng sau khi xem evaluation rồi báo như đánh giá giữ kín.
