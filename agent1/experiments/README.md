# Bản đồ thí nghiệm Agent 1

Đây là mã nghiên cứu có caller/test riêng, không là danh mục model đang phục vụ `/v1`. [Pipeline hiện tại](../docs/04_AI_Methods/01_pipeline_he_thong.md) dùng catalog global và bundle T1 + partial; xem [compact](t1_compact/README.md) cho helper còn liên quan nguồn đóng gói.

## Các nhánh nghiên cứu riêng

| Thư mục | Hợp đồng/giới hạn còn cần biết |
|---|---|
| `t1_competing_v5/` | Risk set paid/write-off/open, 53 tuần; `core.py` dựng sự kiện/censoring/incidence. Không dùng nhãn tương lai làm feature |
| `t1_competing_v6/` | Mở rộng v5, có prepare/train/calibrate/fresh/evaluate/infer; đọc `run.py` và requirements riêng. Không thay model dịch vụ |
| `t1_credit_context/` | Survey/macro/KYC ở bộ nghiên cứu là giả định mô phỏng. `practical.py` chỉ nhận industry có nguồn và ngày biết; tách tenant, không truy cập registry ngoài |
| `t1_v6_practical/` | So các nhóm industry/ledger trong môi trường nghiên cứu. `ledger.py` yêu cầu quyền tenant, ledger append-only, coverage và `known_at`; thiếu/stale không là 0. `sidecars.py`/`design.py` tạo quan sát synthetic, không phải hồ sơ SME |
| `unified_collection_v2/` | Mô hình chuyển tiếp thu tiền và kiểm kế toán riêng. AR-applied khác bank net sau phí; T4/T5/scenario có giả định riêng, không thay cho adapter partial hiện tại |

## Trước khi chạy lại

Đọc `run.py`, schema và protocol của đúng phiên bản. Chạy module từ thư mục `agent1/` với môi trường/import tương ứng, chọn thư mục output mới và khóa cấu hình trước fit. Các mặc định có thể trỏ artifact đã dọn. `saved` hoặc verifier lịch sử chỉ chạy được khi đủ payload/source khớp; không đổi hash để vượt kiểm tra.

Nhiều output v4/v5/v6/practical/unified đã được dọn. `data/` không có raw/Parquet; chỉ giữ 10 template config/manifest và 3 JSON cohort/design/calibration mà bộ dựng compact còn đọc. Metadata các holdout/thử nghiệm cũ đã bỏ; recipe/design còn giữ không phục hồi phép đo cũ. Một số World mới phục vụ compact nằm trong `outputs/t1/`, cần kiểm riêng manifest/payload. [Tồn kho](../docs/02_Data/README.md) và [outputs](../outputs/README.md) mô tả ranh giới này.

Không dùng lại test/World đã xem để chọn mô hình rồi gọi đó là holdout mới. Các nguồn cùng simulator không là các doanh nghiệp thật độc lập. Thay luật nhãn, mốc thời gian hoặc nguồn phải khai báo nghiên cứu mới. Chất lượng và nghiệm thu theo [Evaluation](../docs/03_Evaluation/README.md).
