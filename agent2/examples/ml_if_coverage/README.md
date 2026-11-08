# Kiểm toán độ phủ IF từ điểm đã khóa

Runner chỉ đọc dữ liệu/feature/điểm hiện có, tách loại trừ theo cửa sổ khỏi lỗi dữ liệu, đối chiếu từng lượt rà đúng cutoff. Không load estimator, huấn luyện, chấm điểm hoặc ghi hàng đợi. Dùng môi trường Python với các phiên bản trong `requirements-lock.txt`.

```powershell
python -B -m sme_fraud.audit_if_coverage --dataset data/synthetic_sources_20261017_v2/sme_fraud_001 --baseline reports/pipeline_rehearsal_20261018_v2/sme_fraud_001 --comparison reports/ml_shadow_comparison_20261022/sme_fraud_001 --temporal reports/ml_temporal_split_20261022/sme_fraud_001 --output reports/my_if_coverage_001
```

Đổi `001` thành `003` cho cohort còn lại; luôn chọn thư mục output mới. Nguồn phải là reporting mô phỏng, khớp manifest/hợp đồng feature và hash comparison/model/temporal audit. Không dùng holdout 005, nhãn hoặc oracle.

Đọc `summary.json` để xem cả mẫu số toàn bộ lượt hồ sơ giao dịch và phần chỉ chứa thành viên evaluation. Không thay tỷ lệ trên toàn bộ công việc bằng tỷ lệ trên phần đủ điều kiện. `historical_only_unscored` và `mixed_history_evaluation` là thiếu phạm vi có chủ ý; `data_error` là lỗi cần điều tra. Hash không khớp làm runner dừng, không tự sửa đầu vào.

CSV cho coverage ở cấp giao dịch, lượt rà và thành viên mỗi lượt; `coverage_breakdown.csv` theo công ty/tháng. Tệp `.private.csv` có nhánh/ID hồ sơ/work key, không đưa cho reviewer mù. `input_commitment.json` và `output_commitment.json` ghi hash để kiểm chứng. [Kết quả 22/10/2026](../../reports/ml_if_coverage_20261022.md).
