# 02 · Dữ liệu và hợp đồng đánh giá

Đối chiếu filesystem và mã ngày **14/11/2026**. Thư mục này giữ đặc tả dùng tiếp; các nhật ký, kiểm toán theo lần chạy và kế hoạch đã bị thay thế đã được bỏ sau khi gộp quy tắc còn giá trị.

## Tồn kho đã kiểm tra

| Vị trí | Thực tế trên đĩa |
|---|---|
| `data/raw/`, `data/interim/`, `data/processed/` | Thư mục làm việc trống, được `agent1/paths.py` tự tạo khi import; chưa có raw manifest, WDI hoặc OxCGRT thô |
| `data/synthetic/` | 10 thư mục template, mỗi thư mục có `config.json` và `manifest.json`, **không có Parquet**; cùng 3 JSON cohort/design/calibration, tổng 23 file |
| [Cohort v4](../../data/synthetic/v4_shortpay_4shock_20261028_cohort.json) | Metadata khóa 4 train, 2 validation, 2 test; không đổi vai trò hoặc hash |
| [Thiết kế v4](../../data/synthetic/v4_shortpay_4shock_20261028_design.json) và [calibration](../../data/synthetic/calibration_fit.json) | JSON còn giữ; không thay dữ liệu giao dịch hoặc nguồn raw |
| [Đầu vào BCTC](vn_listed_inputs.json) | Số chép của ba DN-kỳ; input của `scripts/run_vn_listed_check.py`; PDF nguồn không có trong raw |

10 template gồm 8 World trong cohort v4 và 2 `practical_v6_20261105_aug_supported_*`. [Bộ dựng compact](../../experiments/t1_compact/prepare_worlds.py) đọc chúng để khai báo 14 World mới, gồm 4 ca stress bổ sung dùng lại template với seed/giả định riêng. [Bộ kiểm manifest](../../experiments/t1_compact/audit_manifests.py) còn đọc cả cohort/design/calibration; giữ nguyên byte của các file này.

Metadata smoke v4, holdout v6, practical fresh và unified holdout đã nghỉ dùng không còn trong thư mục này. Runner nghiên cứu cũ cần chuẩn bị lại đầu vào theo protocol riêng khi tái lập; không coi chúng là dữ liệu có sẵn. Manifest/hash còn giữ cho biết dữ liệu từng được khóa thế nào, **chưa đủ để train hoặc chạy lại benchmark** khi file giao dịch thiếu.

## Đọc theo nhu cầu

| Tài liệu | Nội dung |
|---|---|
| [Chiến lược và dữ liệu Workspace](01_chien_luoc_du_lieu.md) | Ba tầng bằng chứng, ngày biết, schema ứng dụng và tách nhãn nghiên cứu |
| [Nguồn thật và điều kiện sử dụng](02_du_lieu_that_dung.md) | Nguồn từng thử, nguồn loại/hoãn, đối chiếu BCTC và giới hạn |
| [Máy phát synthetic](04_may_phat_tong_hop.md) | Kiến trúc, nhãn tiền, shock, hard case, C2ST và manifest/split |
| [Dữ liệu đánh giá](07_bo_danh_gia.md) | UAT, benchmark T1/partial/T6/T10, kiểm duyệt và provenance v4 |
| [Tài liệu tham khảo](08_tai_lieu_tham_khao.md) | Nguồn thống kê/phương pháp; không nhân bản các bảng kết quả |

Để vận hành Workspace, đọc [dịch vụ](../../agent1_service/README.md), [adaptive](../../agent1/adaptive/README.md) và dùng dữ liệu doanh nghiệp đã nạp. Để tái lập nghiên cứu, khôi phục đúng raw/Parquet và mã theo hash trước khi chạy runner. Không tự tạo lại vào prefix frozen.

Cách chấm chất lượng nằm ở [Evaluation](../03_Evaluation/README.md), giới hạn bằng chứng ở [nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md). Synthetic qua kiểm nội bộ chưa chứng minh đại diện SME Việt Nam hoặc đủ điều kiện pilot thật.
