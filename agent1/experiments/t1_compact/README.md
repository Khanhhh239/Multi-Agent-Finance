# T1 compact · Dữ liệu và helper catalog

Thư mục chứa helper chuẩn bị/huấn luyện/đối chiếu nghiên cứu và một số nguồn còn dùng để dựng catalog. Runtime doanh nghiệp nằm ở `agent1/adaptive/`, không gọi toàn bộ chuỗi nghiên cứu ở đây cho mỗi cập nhật.

| Nhóm | File tiêu biểu | Vai trò |
|---|---|---|
| Dựng World và landmark | `prepare_worlds.py`, `landmark_data.py`, `fresh_refit_worlds.py` | Kiểm manifest/config/role, tạo lịch sử và snapshot theo ngày biết |
| Sửa nhãn và bridge | `aligned_data.py`, `build_corrected_study.py`, `historical_workspace.py` | Nhãn tiền quan sát đúng cửa sổ, nối dữ liệu/cache cha và module frozen đúng phiên bản |
| Họ global/học tiếp | `global_local_families.py`, `refit_landmark.py` | Công cụ nghiên cứu các họ và adaptation; không tự chọn lại bag local khi `/v1/predict` |
| Benchmark/verifier | `verify_*.py`, `benchmark_*.py`, `compare_*.py` | Kiểm/phân tích đúng protocol của từng lần; có mặc định trỏ payload đã dọn |

Đóng gói serving dùng `scripts/package_t1_global_catalog.py`; catalog mặc định là v3. G0 Neural 75% + customer 25%, ba global và ba nhánh học tiếp có cùng schema 18 feature. Hợp đồng đầy đủ và audit nằm trong [T1 + partial](../../docs/04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md); không dùng hướng dẫn ensemble 10 feature cũ làm luồng hiện tại.

## Ranh giới dữ liệu

Chỉ dùng thông tin ledger đã biết tại origin; ID dùng join/sampling, không là feature. Nhãn tất toán bằng tiền phải phân biệt credit/write-off và có 91 ngày follow-up khi đánh giá đầy đủ. Thiếu coverage phải censor; giữ riêng cutoff kinh tế và cutoff biết nhãn. Test chỉ mở sau khi khóa cấu hình/đặc trưng; nguồn test đã dùng để phát triển chỉ là reference.

World mới từ recipe còn giữ có thể dùng fallback generator khi raw gốc vắng mặt. Chúng không tái lập số đo raw lịch sử. Kiểm [Data](../../docs/02_Data/README.md), [artifact](../../outputs/README.md), prepared/receipt và source hash trước khi chạy; không sinh đè World/output frozen.

`historical_workspace.py` còn đọc một số module source snapshot; không xóa chúng theo tên cũ. Các loader legacy còn phục vụ giải tuần tự hóa/thí nghiệm, không là quyền override catalog runtime. Muốn thử cấu hình khác phải tạo thư mục/protocol mới, không sửa khóa để resume lượt cũ.

[Pipeline](../../docs/04_AI_Methods/01_pipeline_he_thong.md) mô tả serving; [nghiệm thu](../../docs/03_Evaluation/03_cong_nghiem_thu.md) mô tả cách đánh giá tiền hiện tại. README này không giữ bảng điểm hoặc nhật ký các lượt nghiên cứu.
