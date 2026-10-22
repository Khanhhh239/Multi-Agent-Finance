# Tách cửa sổ huấn luyện, hiệu chỉnh và đánh giá — 22/10/2026

**Đã xác minh phân chia thực tế của 41.082 giao dịch thuộc 001/003, với 0 ID giao nhau giữa ba cửa sổ.** Feature train/calibration khớp artifact đã lưu; model và threshold không thay đổi. Đây là kiểm chứng kỹ thuật trên nguồn mô phỏng, chưa phải kết quả SME thật.

## Các cửa sổ đang áp dụng

Phân chia theo `transactions.posted_at`, so thời điểm tuyệt đối bằng UTC. Bảng dưới trình bày theo giờ Việt Nam (UTC+07:00); mọi mốc đều là **00:00:00**, bao gồm đầu và loại trừ cuối.

| Cửa sổ | Khoảng thời gian | Được phép dùng để |
|---|---|---|
| Huấn luyện — train | `01/01/2024 <= t < 01/01/2025` | Fit cây IF; không dùng hàng calibration/evaluation |
| Hiệu chỉnh — calibration | `01/01/2025 <= t < 01/07/2025` | Chấm bằng model đã fit, tính quantile ngưỡng kỹ thuật; không fit lại cây |
| Đánh giá — evaluation | `01/07/2025 <= t < 01/01/2026` | Chấm sau khi lưu model/threshold; không fit hoặc hiệu chỉnh ngưỡng |

Ví dụ: đúng 00:00 ngày 01/01/2025 thuộc calibration; đúng 00:00 ngày 01/07/2025 thuộc evaluation; đúng 00:00 ngày 01/01/2026 nằm ngoài kế hoạch này. Timestamp ghi bằng UTC hoặc UTC+07:00 nhưng cùng thời điểm được phân chia giống nhau. ID không thuộc công ty khai báo hoặc nằm ngoài các cửa sổ được ghi riêng, không tự gán vào train.

Phạm vi hiện tại giữ cùng 8 công ty C001–C008 ở cả ba cửa sổ, đo sự thay đổi theo thời gian trong các công ty này. Không dùng phép chia này để tuyên bố khả năng khái quát sang doanh nghiệp chưa thấy.

## Phân chia từng giao dịch

| Bộ | Train | Calibration | Evaluation | Tổng | ID giao nhau |
|---|---:|---:|---:|---:|---:|
| 001 | 9.321 | 5.304 | 5.934 | 20.559 | 0 |
| 003 | 9.289 | 5.357 | 5.877 | 20.523 | 0 |
| Tổng | 18.610 | 10.661 | 11.811 | 41.082 | 0 |

Mỗi file membership ghi `transaction_id`, `company_id`, thời điểm nguồn, thời điểm UTC và đúng một phân vùng. Không chứa nhãn hoặc điểm bất thường.

- 001: [membership CSV](ml_temporal_split_20261022/sme_fraud_001/temporal_partitions.csv), [audit và thống kê từng công ty](ml_temporal_split_20261022/sme_fraud_001/audit.json).
- 003: [membership CSV](ml_temporal_split_20261022/sme_fraud_003/temporal_partitions.csv), [audit và thống kê từng công ty](ml_temporal_split_20261022/sme_fraud_003/audit.json).

## Kiểm soát trong mã và bằng chứng bổ sung

[Luồng huấn luyện hiện có](../sme_fraud/train_source_model.py) chặn cửa sổ chồng lấn/sai thứ tự/thiếu múi giờ; chỉ hàng train đi vào `fit`, chỉ hàng calibration dùng tính quantile. [Runner shadow](../sme_fraud/shadow_scoring.py) buộc scope của model mới nằm trong evaluation đã khai báo và các công ty tương ứng.

Đợt này thêm [CLI kiểm toán cửa sổ](../sme_fraud/audit_model_windows.py). CLI không fit hoặc chấm điểm. Nó kiểm tra checksum model/cache, đối chiếu bản ghi huấn luyện, tính lại membership theo thời gian và fingerprint ma trận thực tế. Các fingerprint/count/thời điểm/ID của train và calibration phải khớp provenance đã lưu; threshold phải khớp bản ghi huấn luyện. Nguồn thay đổi, fingerprint khai báo sai, model/threshold lệch hoặc output đã tồn tại đều bị từ chối.

Không huấn luyện lại chỉ để đổi cách trình bày cửa sổ. Hai model cùng điểm evaluation đã lưu trong [lượt tương thích nguồn](model_source_sync_20261022.md) được giữ nguyên. Cửa sổ evaluation đã được chấm kỹ thuật ở lượt trước; nó không còn là một bộ điểm chưa từng được xem. Không dùng điểm evaluation để chọn lại siêu tham số hoặc quantile rồi báo như đánh giá giữ kín. Nếu cần phát triển model dựa trên kết quả này, phải xác định giai đoạn đánh giá mới trước khi thử; 005 vẫn chưa mở.

## Kiểm chứng

**61 kiểm thử đạt, 0 failure/error/skipped**: 10 kiểm thử audit mới, 45 kiểm thử model/shadow/hợp đồng và 6 kiểm thử causality hiện có. Bao phủ mốc đầu/cuối, khoảng trống, hai múi giờ biểu diễn cùng thời điểm, ID trùng, fingerprint thực tế khác khai báo, threshold lệch bản ghi, nguồn đổi giữa lúc chạy, bảo toàn output và tác động dữ liệu tương lai lên feature quá khứ. [Kết quả](ml_temporal_split_20261022/tests.json), [log](ml_temporal_split_20261022/tests.log).

Audit trên nguồn 001/003 chạy dưới chặn `fit` và `score_samples`: **0 model được fit, 0 giao dịch được chấm** trong audit. Không đọc nhãn/splits/oracle của nguồn. **1.232 tệp được kiểm tra bảo toàn không đổi**, gồm danh sách khóa cũ và toàn bộ đầu ra lần tương thích model; 005 chỉ băm opaque trong kiểm tra bảo toàn. Hàng đợi và thông báo không thay đổi. [Biên bản máy đọc](ml_temporal_split_20261022/verification.json).

Các kiểm thử causality dùng fixture của bộ kiểm thử. Audit cache thực tế không dựng lại feature từ ERP thô, nên không thay thế nghiệm thu producer/đơn vị/thời điểm nguồn SME thật. Các cổng nguồn thật, review độc lập và lợi ích vận hành tiếp tục chờ.

## Chạy lại cho một model đã huấn luyện

Dùng Python và thư viện khớp artifact, SHA256 lấy từ `training_run.json`, thư mục output mới nằm ngoài nguồn/model:

```powershell
python -B -m sme_fraud.audit_model_windows `
  --dataset data/synthetic_sources_20261017_v2/sme_fraud_001 `
  --model reports/model_source_sync_20261022/sme_fraud_001/model/isolation_forest.joblib `
  --model-sha256 6c2f9313fd9888437734c5894fdbc96bd6e283370031ba91ecc408387657a4a7 `
  --output reports/my_temporal_audit_001
```

CLI này dành cho artifact có provenance và bản ghi huấn luyện mới, cùng cache gốc. Không tự cấp chứng nhận thời gian cho model cũ thiếu provenance hoặc cache mới khác nguồn huấn luyện.
