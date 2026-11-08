# Huấn luyện IF tương thích cache nguồn mới

`sme_fraud.train_source_model` tạo model mới từ cache có hợp đồng ngữ nghĩa và checksum hợp lệ. Không sửa phiên bản của model cũ để vượt cổng tương thích. Cache `synthetic-source-world-v1` hiện đã có cùng 190 feature và hợp đồng hiện hành, nên được kiểm tra và dùng lại; cache không đạt kiểm tra phải dựng lại từ producer phù hợp.

## Chạy trên nguồn mô phỏng

Chạy bằng Python 3.12 cùng bộ thư viện trong `requirements-lock.txt`. Module tự dùng `.runtime/site-packages` nếu thư mục đó tồn tại; model chỉ suy luận bằng đúng phiên bản sklearn được ghi trong artifact.

```powershell
python -B -m sme_fraud.train_source_model `
  --dataset data/synthetic_sources_20261017_v2/sme_fraud_001 `
  --plan examples/ml_source_model/plan.synthetic.json `
  --output reports/my_source_model_001
```

Đầu ra phải là thư mục mới ngoài nguồn và ngoài các snapshot/model đã có. CLI nhận thêm `--alert-budget` (mặc định 0,003), `--n-estimators` (300), `--max-samples` (2048), `--random-state` (20261022) và `--jobs` (4). Đây là cấu hình kỹ thuật cố định cho lần thử, chưa phải ngưỡng vận hành đã hiệu chỉnh cho SME thật.

Kế hoạch mẫu có cùng phạm vi 8 công ty ở ba cửa sổ, đầu cuối loại trừ:

| Cửa sổ | Phạm vi theo giờ Việt Nam | Dùng để |
|---|---|---|
| Train | 01/01/2024–01/01/2025 | Fit cây IF |
| Calibration | 01/01/2025–01/07/2025 | Tính quantile từ điểm không nhãn |
| Evaluation | 01/07/2025–01/01/2026 | Suy luận riêng sau khi model đã được lưu |

Runner từ chối cửa sổ chồng lấn, không theo thứ tự, thiếu múi giờ hoặc công ty thiếu dữ liệu train/calibration. Không đọc `labels.csv`, `splits.csv`, oracle hay điểm rules để chọn hàng/train/hiệu chỉnh. Thư mục 005 và nguồn có `role=holdout` bị từ chối. Cache được kiểm tra toàn bộ ID/độ phủ/độ rộng/giá trị hữu hạn; chỉ hàng thuộc train/calibration đi vào ma trận dùng bởi estimator.

Đầu ra gồm `isolation_forest.joblib` và `training_run.json`, lưu phiên bản nguồn/sklearn, hợp đồng feature, hash nguồn, tham số model, fingerprint ma trận và thống kê từng cửa sổ/công ty. Trước công bố, runner nạp lại model và xác nhận điểm calibration giống hệt. Không ghi đè kết quả cũ; lỗi ghi hoặc nguồn đổi giữa lúc chạy không công bố output dở dang.

## Chấm cửa sổ evaluation

Tạo scope có `company_ids`, `source_ref`, `start_at`, `end_at` nằm trong evaluation đã khai báo; dùng SHA256 model trong `training_run.json`:

```powershell
python -B -m sme_fraud.shadow_scoring `
  --dataset data/synthetic_sources_20261017_v2/sme_fraud_001 `
  --model reports/my_source_model_001/isolation_forest.joblib `
  --model-sha256 <SHA256_TRONG_TRAINING_RUN> `
  --scope scope.evaluation.json `
  --output reports/my_source_model_scores_001
```

Model mới buộc scope suy luận nằm trong cửa sổ evaluation và các công ty đã khai báo; không thể dùng nó để chấm lại train/calibration bằng runner này. `model_training_window_disjointness_verified=true` xác nhận kiểm tra provenance cửa sổ của artifact tin cậy, không chứng nhận nguồn SME hoặc hiệu quả phát hiện. Model cũ chưa có provenance thời gian vẫn chỉ được ghi nhận là replay kỹ thuật chưa xác minh tách cửa sổ.

## Kiểm toán phân vùng thực tế

`sme_fraud.audit_model_windows` đối chiếu cache gốc với model và bản ghi huấn luyện, xuất membership theo từng ID cùng fingerprint/count của ba cửa sổ. Không fit hay chấm điểm; không ghi đè output cũ. Cần đủ dữ liệu của các công ty khai báo trong cả ba cửa sổ để hoàn tất audit. [Kết quả 41.082 giao dịch và cách chạy](../../docs/reports/ml/ml_temporal_split_20261022.md).

Khoảng thời gian luôn bao gồm đầu và loại trừ cuối; đúng 01/01/2025 chuyển sang calibration, đúng 01/07/2025 chuyển sang evaluation. Phân chia dùng `posted_at` và so bằng UTC; ngày trong kế hoạch mẫu là 00:00 giờ Việt Nam. Threshold được chọn từ calibration trước khi chấm evaluation. Không dùng kết quả evaluation để chọn lại model/threshold rồi báo như đánh giá giữ kín; cửa sổ đã xem cần được ghi nhận đúng vai trò trong lần thử tiếp theo.

Quantile lưu trong artifact không được runner shadow dùng để mở hồ sơ hoặc gửi cảnh báo. Kết quả chỉ là điểm bất thường; chưa phải xác suất gian lận. Nguồn thật, phép so sánh vận hành và review độc lập vẫn cần hoàn tất riêng.
