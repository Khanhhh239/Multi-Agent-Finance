# Kiểm tra phép lấy max IF thành hồ sơ

Audit từ điểm/case stream đã khóa; không load estimator, huấn luyện, chấm mới hoặc thử cách gộp thay thế. Môi trường cần các phiên bản trong `requirements-lock.txt`. Đầu vào phải khớp audit độ phủ trước đó.

```powershell
python -B -m sme_fraud.audit_if_aggregation --dataset data/synthetic_sources_20261017_v2/sme_fraud_001 --baseline reports/pipeline_rehearsal_20261018_v2/sme_fraud_001 --comparison reports/ml_shadow_comparison_20261022/sme_fraud_001 --coverage reports/ml_if_coverage_20261022/sme_fraud_001 --output reports/my_if_aggregation_001 --repetitions 1000 --seed 20261022
```

Đổi 001 thành 003 cho cohort kia; dùng thư mục output mới. Model/source/score/code/coverage đã khóa phải giữ hash. Không nhận holdout 005 hoặc nguồn thật chưa có protocol.

Đơn vị chính là tập thành viên khác nhau ở lần đầu nhìn thấy, trong mọi hồ sơ giao dịch đã admission. Phần đầy đủ điểm evaluation mới được phân tích max; lịch sử không chấm bù. `txn_group=mixed` giữ số lượng từng txn_type cho đối chứng. Đối chứng lấy điểm sẵn có cùng công ty/nghiệp vụ, trước cutoff, không hoàn lại; vẫn dùng max. Đối chứng chỉ đo cơ chế, không tạo điểm xếp hàng mới.

`member_sets.private.csv` giữ ID thành viên/cutoff/phạm vi/điểm/reference; `group_statistics.csv` theo quy mô/công ty/nghiệp vụ/tháng/ưu tiên. `transaction_score_groups.csv` mô tả nguồn, `selection_size_groups.csv` mô tả các lượt rà đã khóa. Không gộp điểm thô của hai model.

Các tập mở rộng còn dùng lại giao dịch. Dùng `dependence_profiles` trong [audit_if_aggregation_dependence.py](../../sme_fraud/audit_if_aggregation_dependence.py) để lấy tập đầu tiên hoặc lớn nhất mỗi case, và một đại diện lớn nhất mỗi thành phần trùng giao dịch. Đây là kiểm tra hồi cứu, không đổi queue. [Bản chạy chuẩn và giới hạn](../../reports/ml_if_aggregation_20261022.md) có commitment đầu vào/đầu ra và mapping các đại diện.

Các CSV `.private` có thông tin nhánh/ID/điểm, giữ nội bộ. Lợi ích chỉ được đánh giá tiếp bằng rà độc lập và phút xử lý thực tế, cùng ngân sách/ưu tiên/membership và phân tầng như nhau.
