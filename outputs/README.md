# Cách đọc `outputs/` (kiểm tra 27/10/2026)

Thư mục này chứa **bằng chứng của nhiều lần chạy**, không phải một bảng kết quả
duy nhất. Đọc ngày, cohort, `measurement_version` và giao thức trước khi so hai
file. CSV/JSON ghi kết quả của một lần chạy; sự tồn tại của file không chứng minh
hiệu quả trên doanh nghiệp Việt Nam thật.

| Cần biết | Nguồn đọc trước | Giới hạn |
|---|---|---|
| Cổng nghiệm thu sản phẩm | `implementation/gates.csv`, rồi [bảng diễn giải](../docs/03_Evaluation/GATES_CURRENT.md) và CSV trong cột `evidence` | G11 nằm ngoài phạm vi **giai đoạn chỉ synthetic**; pilot thật vẫn NO-GO và vẫn cần chuyên gia xác minh G11. |
| Bộ train synthetic cuối | `data/v3_final_20261027/scenario_protocol.json`, `readiness.json`, `train.json`, `evaluation.csv`, `run_summary.json`, `model.txt`; [cohort khóa split](../data/synthetic/v3_final_20261027_cohort.json) | Chỉ cohort này là bộ cuối 8 World. GO kỹ thuật cho train synthetic không đổi cổng sản phẩm và không chứng minh phân phối SME Việt Nam. |
| Các cohort ứng viên và phản thực | `data/v3_candidate*`, `data/v3_heldout_pilot_20261026/`, `data/release_gate_audit_20261026/`, các CSV kiểm toán ở `data/` | Kết quả theo phiên bản/seed trước bộ cuối; `readiness.json` PASS riêng lẻ không có nghĩa đã train hoặc phát hành. Xem [báo cáo 18–23](../docs/02_Data/README.md). |
| Kết quả mô hình cũ và ablation | `t1/`, `t2_t3/`, `t4/`, `t6/`, `t7/`, `t8/`, `t9/`, `e2e/`, `g13/`, `tgt2/`, `berka/`, `sprint5/`, `rules/`, `wp0/` | Những thư mục này thuộc nhiều giao thức và tập test khác nhau. Không trộn vào `v3_final_20261027` hoặc dùng test để chọn lại mô hình. |
| Dịch vụ và pilot | `service/`, `pilot/` | `service/docker_check.json` là lần kiểm ngày 20/10, Docker không khởi động. `pilot/privacy_t9_parity.csv` đo ẩn danh trên synthetic; `pilot/pilot_metrics.csv` **chưa có**, nên chưa có kết quả pilot thật. |

## Bản lưu và ảnh chụp lịch sử

- `*.legacy_expand.csv` là 181 bản sao trước khi sửa `expand`, có SHA-256 trong
  `implementation/legacy_expand_backups.json`. Kiểm tra ngày 27/10: đủ 181 file,
  tất cả hash khớp; 110 file hiện vẫn trùng byte với bản đang dùng, 71 file đã
  khác. Giữ chúng để đối chiếu giao thức, không tự chọn bản nào có điểm đẹp hơn.
- `implementation/run_status.json` ghi cả các lần thất bại hoặc gián đoạn.
  `implementation/test_summary.csv` và hai JUnit XML ghi **316 ca của lần chạy
  cũ**, không phải số test của mã đang chỉnh. `implementation/report_reproducibility.json`
  là phép kiểm ngày 20/10; `implementation/publish_manifest.json` là ảnh chụp
  công bố cũ. Hai file này còn nhắc `docs/RESULTS_TABLES.md` đã được bỏ vì trùng
  với báo cáo Evaluation, nên không dùng chúng để khẳng định working tree hiện tại
  đã qua kiểm tái lập hoặc đã được công bố.
- Một số `run_summary.json` lưu đường dẫn tuyệt đối của máy lúc chạy. Khi mở ở
  workspace khác, tìm file theo đường dẫn tương đối trong repo và kiểm hash;
  không chạy lại trực tiếp đường dẫn tuyệt đối cũ.

File `data/v3_final_20261027/model.txt` là artifact mô hình của bộ synthetic
cuối, không phải model đang được phép triển khai cho doanh nghiệp thật.
Các Parquet của cohort `v3_final_20261027` được lưu bằng Git LFS; khi clone cần
`git lfs pull` để có nội dung bảng. Các World thử nghiệm và dữ liệu nguồn thô
không đi cùng artifact cuối; đọc manifest và hash trước khi dùng kết quả lịch sử.
