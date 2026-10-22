# Runner ML chỉ xuất điểm từ feature cache

Module: [shadow_scoring.py](../../sme_fraud/shadow_scoring.py). Runner kiểm tra cache/model hiện có, chọn công ty và khoảng thời gian rồi xuất điểm Isolation Forest vào thư mục mới. Không gọi `fit`, dựng lại feature, đọc nhãn/splits, chọn ngưỡng hoặc sửa hàng đợi/kết luận/thông báo. [Biên bản kiểm chứng](../../reports/ml_shadow_runner_20261019.md).

**Cập nhật 22/10/2026:** đã có [hai model mới tương thích `synthetic-source-world-v1`](../../reports/model_source_sync_20261022.md) và [luồng huấn luyện riêng](../ml_source_model/README.md). Khi artifact có provenance mới, runner bắt buộc scope nằm trong evaluation đã khai báo và kiểm tra tách cửa sổ với train/calibration; model cũ vẫn giữ trạng thái thời gian chưa xác minh.

## Thử trên mô phỏng

```powershell
python -B -m sme_fraud.shadow_scoring --dataset data/feature_model_sync_20261017/sme_fraud_001 --model reports/feature_model_sync_20261017/sme_fraud_001/isolation_forest.joblib --model-sha256 71ce3b8f883bc76947a9ba58161def2d7375eddafbcb552f522ee1d854a3bbcb --scope examples/ml_shadow_runner/scope.synthetic.json --output .runtime/ml_shadow_runner_demo_001_NEW
```

Chọn thư mục output chưa tồn tại. Model ở lệnh mẫu do workspace tạo, đã kiểm tra trong audit 19/10. Chỉ nạp artifact joblib đáng tin cậy; checksum nhận diện chính xác tệp đã chọn, không tự chứng minh một artifact ngoài workspace đáng tin.

[Scope mẫu](scope.synthetic.json) chỉ định 5 công ty và khoảng `[01/01/2025, 01/07/2025)`. Khoảng cuối loại trừ; thời điểm phải có múi giờ. Đây là cache validation mô phỏng cũ đã dùng để hiệu chỉnh ngưỡng của model. Chạy lại kiểm tra đường tính điểm và tính tái lập, chưa phải phép đánh giá hiệu năng độc lập hoặc pilot SME.

Output:

- `shadow_scores.csv`: `run_id`, `transaction_id`, `company_id`, `posted_at`, `anomaly_score`. Điểm cao hơn biểu thị bất thường hơn, chưa phải xác suất gian lận; không sinh nhãn hợp lệ/gian lận hoặc cờ mở hồ sơ.
- `run.json`: phiên bản runner, scope, model/cache/source checksums, hợp đồng feature, provenance huấn luyện được model khai báo, hướng điểm, số dòng và hash kết quả. Các cổng nguồn thật/thiết kế/temporal provenance/lợi ích vẫn được ghi chưa xác minh.

## Các kiểm tra bắt buộc

Cache cần `manifest.json`, `features.csv`, `transactions.csv` và các đầu vào đã được manifest ràng buộc. Runner kiểm tra hợp đồng ngữ nghĩa hiện tại, phiên bản sklearn, phiên bản định dạng model/cache, thứ tự/độ rộng feature, ID duy nhất, số hữu hạn và coverage giao dịch. Những file nguồn được manifest khai báo được băm để đối chiếu, trừ nhãn/splits; chỉ parse CSV feature và các cột định danh/công ty/thời điểm của giao dịch.

Runner kiểm tra hash trước/sau tính điểm và chỉ công bố output hoàn chỉnh khi tất cả kiểm tra qua. Không ghi đè run cũ, ghi trong thư mục nguồn/model/snapshot, hoặc nạp/chấm đường dẫn 005. Hai model benchmark cũ vẫn bị từ chối với `synthetic_sources_20261017_v2` vì `dataset_format_version_mismatch`; không sửa metadata để ép qua cổng.

## Trước khi dùng nguồn thật

Runner chạy ở chế độ `technical_cache_replay`. Nó chưa nạp trực tiếp bản xuất ERP, chưa xác minh nghiệm thu nguồn hoặc tự dựng feature mới. Việc tách cửa sổ được xác minh theo provenance khai báo với model mới; model cũ không có provenance vẫn ghi `model_training_window_disjointness_verified=false`. Việc nạp điểm từ cache đúng checksum không thay thế các kiểm tra thời điểm của producer feature. Ma trận phạm vi được nạp vào RAM; chưa benchmark dung lượng/độ trễ trên nguồn SME thật.

Để nối pilot cần: nguồn/mapping được chủ nguồn xác nhận; feature đúng thời điểm; model phù hợp được train/calibrate trên cửa sổ riêng; provenance thời gian và công ty được kiểm tra; thiết kế so sánh được duyệt và có người rà độc lập. Sau đó mới kết nối runner với nguồn đó. Giữ điểm riêng để quan sát, chưa đổi ngân sách/thứ tự hồ sơ hoặc áp threshold benchmark cho SME mới.

Protocol và phiếu review vẫn là [bản nháp](../../reports/ml_pilot_readiness_20261019/comparison_protocol.draft.json). Không lấy kỳ vọng mô phỏng hay nhận xét của trợ lý làm nhãn thực địa. Trạng thái lợi ích vận hành vẫn `not_measured`.
