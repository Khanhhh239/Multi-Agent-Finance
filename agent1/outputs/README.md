# Artifact và bằng chứng Agent 1

Catalog mặc định hiện tại là `t1/settlement_partial_catalog_v3_20261114/catalog.json`, được khai báo trong `agent1/adaptive/t1_catalog.py`; biến `AGENT1_T1_GLOBAL_CATALOG` có thể chọn đường dẫn khác. Tên thư mục/ngày mới nhất không xác định model đang phục vụ một doanh nghiệp.

| Nhóm | Cách sử dụng |
|---|---|
| Catalog T1 + partial | Giữ manifest, model, prior, replay và hash đồng bộ; kiểm contract khi nạp |
| Nguồn đóng gói/train trong `t1/` | Dữ liệu đã sửa nhãn, prepared/receipt, module frozen và reference còn được helper đọc; không tự là incumbent |
| `implementation/`, `review/` | Artifact kiểm tra chức năng, JSON/XML/ảnh và ca tái hiện; kết quả chỉ có nghĩa với source/runtime của lần chạy |
| `t6/` và các nhánh nghiên cứu | Có nhánh chỉ còn bảng/config/manifest sau dọn; kiểm payload trước khi tái lập |
| `data/`, `analysis/` | Recipe/protocol/design/manifest còn giữ không chứng minh model hoặc Parquet lịch sử còn đủ |
| `maintenance/` | Mapping/hash của các lần bảo trì; khôi phục còn cần payload nguồn thực tế |
| Báo cáo/kho riêng | Không đưa dữ liệu, khóa, model tenant hoặc báo cáo giải mã vào Git |

Markdown báo cáo/review/fix và nhật ký chạy đã bỏ khỏi các nhánh output. Hợp đồng kỹ thuật tập trung ở [pipeline](../docs/04_AI_Methods/01_pipeline_he_thong.md), [T1](../docs/04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md), [T6](../docs/04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md) và [T10](../docs/04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md).

Không sửa hash, protocol hoặc số đo lưu sẵn để ép chạy với mã mới. Kiểm source/runtime/dữ liệu trước khi replay; nếu khác thì dùng đúng môi trường hoặc khai báo lượt mới ở thư mục mới. Forecast tenant và replay của nó nằm trong kho Workspace mã hóa, không đồng nhất với các output nghiên cứu ở đây.

Tái lập chất lượng theo [nghiệm thu](../docs/03_Evaluation/03_cong_nghiem_thu.md); kiểm tồn kho theo [Data](../docs/02_Data/README.md). Dọn tài liệu không chạy lại benchmark hoặc thay trạng thái pilot.
