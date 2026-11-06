# Agent 1 — Trợ lý dòng tiền

Dự án nghiên cứu dự báo thu tiền và số dư 13 tuần, gồm máy phát dữ liệu SME Việt Nam,
mô hình T1–T10, đối soát ngân hàng, thí nghiệm thích nghi miền và dịch vụ local.
**Chưa hoàn thành toàn bộ kế hoạch 01–08; trạng thái nghiệm thu hiện tại là NO_GO.**

Đọc [tiến độ triển khai](docs/05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md) để biết phần đã đo và phần còn thiếu;
[cổng hiện hành](docs/03_Evaluation/GATES_CURRENT.md) để xem điều kiện nghiệm thu;
[kết quả hiện có](docs/03_Evaluation/04_ket_qua_hien_co.md) và
[kết quả chưa đạt](docs/03_Evaluation/KET_QUA_CHUA_DAT.md) để xem bằng chứng từ CSV.
Các tài liệu lịch sử không thay các bảng hiện hành này.

## Cài đặt và kiểm tra trên Windows

Python 3.12, PowerShell, tại thư mục dự án:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONUTF8='1'
$env:AGENT1_THREADS='4'
$env:OMP_NUM_THREADS='4'
$env:OPENBLAS_NUM_THREADS='1'
.\.venv\Scripts\python.exe -m pytest tests -q --junitxml=outputs/implementation/tests.xml
.\.venv\Scripts\python.exe -m ruff check agent1 agent1_service scripts tests --select E9,F63,F7,F82
```

`requirements.txt` khoá phụ thuộc trực tiếp; `requirements-lock.txt` ghi môi trường đầy đủ.
Chronos/PyTorch là nhánh tuỳ chọn trong `requirements-forecast.txt`; kết quả nếu đã hoàn tất nằm ở `outputs/t6/chronos/`.
Giảm số luồng khi máy dùng chung; các thí nghiệm lớn cần kiểm tra RAM và dung lượng trước khi chạy.

## Chạy thí nghiệm

Đợt chạy lại fullweek ngày 21/10/2026 là hồ sơ lịch sử; giao thức và
đăng ký P4/G3 đã gộp tại
[phương pháp T1](docs/04_AI_Methods/02_t1_hazard_thoi_diem_tra.md#fullweek-20261021).
Không coi chuỗi điều phối 18 job cũ là lệnh khởi chạy hiện tại. `C-v2` có
giao thức thật mới; `C` chỉ dùng kiểm toán v1. Một số đầu vào cũ đã xóa;
kiểm [tồn kho dữ liệu](docs/02_Data/README.md) và protocol trước khi chạy job.

```powershell
.\.venv\Scripts\python.exe scripts/run_plan.py --jobs tests,report --fail-fast
.\.venv\Scripts\python.exe scripts/run_plan.py --jobs T8-reliability,T3-T1,DA-paired --fail-fast
.\.venv\Scripts\python.exe scripts/run_plan.py --jobs SBA-macro,regime-cash,collection-policy,policy-comparisons --fail-fast
.\.venv\Scripts\python.exe scripts/run_plan.py --jobs rules-business-cases,obligation-cases --fail-fast
```

Danh sách job ở `scripts/run_plan.py`. Lệnh không có `--jobs` chạy cả chuỗi lớn,
có thể mất nhiều giờ; tuning và scaling tốn đáng kể tài nguyên. Mỗi job ghi trạng thái,
exit code, hash mã và nhật ký trong `outputs/implementation/`.
Smoke E2E lưu riêng; kết quả đầy đủ nằm trong `outputs/e2e/e2e_metrics.csv`.
Không dùng dữ liệu kiểm tra miền đích để chọn tham số hoặc chính sách onboarding.
Các phép đo bổ sung và giới hạn đã gộp tại
[SBA](docs/04_AI_Methods/03_t2_t3_t8_xac_suat_hoa_don.md#sba-macro),
[DR/IW](docs/04_AI_Methods/05_domain_adaptation.md#ablation-dr-iw),
[T7/T9/chính sách](docs/04_AI_Methods/07_t7_t9_t10.md),
[copula và đối chứng T6](docs/04_AI_Methods/06_t6_monte_carlo_conformal.md),
[lịch nghĩa vụ từ hồ sơ](docs/04_AI_Methods/04_t4_t5_thu_moi_va_chi.md#nghia-vu-bo-sung) và
[đối chiếu BCTC niêm yết](docs/02_Data/09_vn_listed_spot_check.md).

Khi cần dựng dữ liệu mới, xem [tồn kho và thiết kế dữ liệu](docs/02_Data/README.md), [data card lịch sử](docs/DATA_CARD.md) và các script
`crawl.py`, `build_worlds.py`, `build_multiworld.py`, `build_big.py`.
Không tự chấp nhận điều khoản Kaggle hoặc điền danh tính SEC; hai nguồn này đang được tạm bỏ.
Không ghi đè bộ dữ liệu hiện có bằng cấu hình khác.

## Dịch vụ local

Xem [hướng dẫn dịch vụ](agent1_service/README.md) cho nhập XML/CSV/Excel, token,
dashboard, registry mô hình và giám sát. Lệnh khởi động sau khi đã có thế giới `tgt`:

```powershell
$env:AGENT1_DEMO_DIR='data/synthetic/tgt'
.\.venv\Scripts\python.exe -m agent1_service.seed_demo
.\.venv\Scripts\python.exe -m uvicorn agent1_service.main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`, dùng token trong `.state/api-token.txt`.
Dữ liệu và registry được mã hoá trong SQLite; không chia sẻ token hoặc thư mục `.state`.
Mặc định dự báo trả `409 NO_GO`; chế độ nghiên cứu local cần cấu hình rõ trong hướng dẫn dịch vụ.
Docker cần daemon hoạt động. Kiểm tra local không thay UAT của người dùng hoặc pilot doanh nghiệp thật.

## Cấu trúc và tái lập báo cáo

| Thư mục | Nội dung |
|---|---|
| `agent1/data`, `agent1/synth` | Nạp dữ liệu, hợp đồng, máy phát và tình huống khó |
| `agent1/models`, `agent1/eval` | Đặc trưng as-of, mô hình, chỉ số và bootstrap theo công ty |
| `agent1/rules` | Quy tắc có phiên bản, nguồn và trạng thái xác minh |
| `agent1_service`, `agent1/jobs` | API/UI local, lưu trữ, retrain và giám sát |
| `scripts`, `tests` | Các giao thức thực nghiệm và kiểm thử |
| `outputs` | CSV kết quả, metadata, hình và nhật ký |
| `docs/05_Coding_Agent_Plan` | Phạm vi WP, nhật ký/quyết định lịch sử và tiến độ sinh từ hồ sơ |

Sau khi các job kết thúc, chạy `python scripts/make_report.py` để sinh lại tài liệu từ CSV.
Số ca kiểm thử đọc từ `outputs/implementation/test_summary.csv`; không giữ số đếm thủ công trong README.
Không commit dữ liệu thô, parquet tổng hợp, cache hoặc bí mật. Kết quả tổng hợp chưa chứng minh hiệu quả trên DN thật.
