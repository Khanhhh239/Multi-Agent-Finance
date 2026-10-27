# Model IF tương thích định dạng nguồn mới — 22/10/2026

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

**Đã giải quyết chặn tương thích cho nguồn mô phỏng `synthetic-source-world-v1` bằng hai model mới.** Không đổi metadata của model cũ hoặc nới kiểm tra phiên bản. Chưa nghiệm thu nguồn SME thật hay lợi ích vận hành.

## Thay đổi

- Thêm [runner huấn luyện](../../../sme_fraud/train_source_model.py) tạo IF mới từ cache đã xác minh checksum/hợp đồng feature. Hai cache 001/003 hiện có đúng 190 feature và cùng fingerprint ngữ nghĩa hiện hành, nên dùng lại cache; không cần dựng lại hoặc sửa manifest nguồn.
- Kế hoạch khai báo công ty và cửa sổ train/calibration/evaluation có múi giờ, đầu cuối loại trừ. Chặn chồng lấn, sai thứ tự, nguồn holdout hoặc công ty thiếu hàng train/calibration. Chỉ hàng train được fit; chỉ điểm calibration được dùng tính quantile.
- Artifact lưu phiên bản nguồn/sklearn, fingerprint ma trận, hash nguồn, phạm vi và thống kê thời gian/công ty. Nạp lại artifact để đối chiếu điểm calibration trước khi công bố thư mục hoàn chỉnh.
- [Runner shadow](../../../sme_fraud/shadow_scoring.py) kiểm tra provenance của model mới và từ chối scope thuộc train/calibration, ngoài cửa sổ evaluation hoặc công ty chưa khai báo. Model cũ không có provenance vẫn ghi trạng thái thời gian chưa xác minh; cổng tương thích cũ giữ nguyên.
- Không đọc nhãn/splits/oracle để chọn hàng, fit hoặc hiệu chỉnh; không gọi engine rules, sửa hàng đợi, kết luận hay thông báo. Source checks xác nhận checksum toàn bộ đầu vào manifest, bỏ nhãn/splits; kiểm tra cấu trúc/cache có đọc hàng feature ngoài train/calibration nhưng không dùng các hàng đó để fit/hiệu chỉnh.

## Model và kết quả

Thông số cố định: IF 300 cây, tối đa 2.048 mẫu/cây, `contamination=auto`, random state 20261022, 4 jobs. Calibration dùng quantile `higher` tại ngân sách kỹ thuật 0,3%; threshold được lưu riêng và không đưa vào hàng đợi vận hành. Môi trường sklearn 1.9.1 khớp `requirements-lock.txt`.

| Phạm vi | Cửa sổ giờ Việt Nam, đầu cuối loại trừ |
|---|---|
| Train | 01/01/2024–01/01/2025 |
| Calibration | 01/01/2025–01/07/2025 |
| Evaluation | 01/07/2025–01/01/2026 |

Cả ba cửa sổ khai báo cùng 8 công ty C001–C008. Kế hoạch được ghi trước khi fit; nhãn/splits của nguồn không tham gia phân chia.

| Bộ | Hàng train | Hàng calibration | Hàng evaluation | Kết quả |
|---|---:|---:|---:|---|
| 001 | 9.321 | 5.304 | 5.934 | Tương thích; hai lượt shadow giống hash |
| 003 | 9.289 | 5.357 | 5.877 | Tương thích; hai lượt shadow giống hash |
| Tổng | 18.610 | 10.661 | 11.811 | 23.622 lượt tính điểm evaluation |

Mỗi bộ chạy shadow hai lần với batch 2048 và 257, không gọi fit trong suy luận. Scope evaluation đã được kiểm tra nằm sau train/calibration theo provenance ghi trong model. Không tính precision/recall hoặc coi cửa sổ này là pilot thực địa.

Đầu ra mới:

- [Model 001](../../../reports/model_source_sync_20261022/sme_fraud_001/model/isolation_forest.joblib), [provenance 001](../../../reports/model_source_sync_20261022/sme_fraud_001/model/training_run.json), [điểm 001](../../../reports/model_source_sync_20261022/sme_fraud_001/shadow_2048/shadow_scores.csv).
- [Model 003](../../../reports/model_source_sync_20261022/sme_fraud_003/model/isolation_forest.joblib), [provenance 003](../../../reports/model_source_sync_20261022/sme_fraud_003/model/training_run.json), [điểm 003](../../../reports/model_source_sync_20261022/sme_fraud_003/shadow_2048/shadow_scores.csv).
- [Kế hoạch](../../../reports/model_source_sync_20261022/plan.synthetic.json), [scope evaluation](../../../reports/model_source_sync_20261022/scope.evaluation.json), [biên bản máy đọc và SHA256](../../../reports/model_source_sync_20261022/verification.json).

Hai model benchmark cũ vẫn bị từ chối trên chính cache mới với `dataset_format_version_mismatch`. Không công bố output cho các lượt bị từ chối.

## Kiểm chứng

**45 kiểm thử đạt, 0 failure/error/skipped**: 17 kiểm thử mới, 17 kiểm thử shadow và 11 kiểm thử đồng bộ feature/model cũ. Bao phủ fit đúng hàng train, calibration đúng cửa sổ, dữ liệu evaluation không làm thay đổi cây/threshold, so múi giờ, nhãn/splits không được đọc, hợp đồng cache, version gate, scope công ty, provenance bị sửa/thiếu, input thay đổi giữa lúc chạy, không ghi đè và dọn output dở dang. [Kết quả](../../../reports/model_source_sync_20261022/tests.json), [log](../../../reports/model_source_sync_20261022/tests.log).

Đã xác nhận **1.215 tệp bảo toàn không đổi** trước/sau fit và suy luận, gồm danh sách 1.209 tệp khóa cùng các artifact bổ sung trong audit ML trước đó. 005 chỉ được băm opaque trong kiểm tra bảo toàn, không parse/nạp/chấm. Hợp đồng feature hiện hành không đổi. Có bổ sung dependency networkx 3.6.1 còn thiếu trong môi trường kiểm thử từ wheel cục bộ khớp lock; không tải mạng hoặc đổi lock.

## Cách dùng và giới hạn

[Hướng dẫn CLI và kế hoạch mẫu](../../../examples/ml_source_model/README.md). Model cần đúng phiên bản sklearn và cache đúng hợp đồng/định dạng; không tự chuyển model này thành model phù hợp mọi SME. Cache ngữ nghĩa cũ hoặc khác producer vẫn phải dựng lại đúng cách.

Đợt này xác minh khả năng huấn luyện và suy luận trên nguồn mới, cùng sự tách cửa sổ khai báo của artifact tin cậy. Chưa có importer bản xuất SME thật, nguồn được nghiệm thu, đánh giá kế toán độc lập hoặc bằng chứng ML giúp tăng số hồ sơ hữu ích tại cùng ngân sách rà. Chưa nối điểm vào thứ tự vận hành; các cổng nguồn thật/protocol/lợi ích tiếp tục chờ. RR09 giữ trạng thái riêng và không được thay đổi trong đợt ML này.
