# Hướng dẫn đọc `scripts/`

Các script ở đây gồm pipeline dữ liệu synthetic cuối, phép kiểm, thí nghiệm cũ và công cụ điều phối. **Tên `run_*.py` không đồng nghĩa với kết quả hiện hành.** Đọc `data/synthetic/v3_final_20261027_cohort.json`, `outputs/data/v3_final_20261027/` và báo cáo `docs/02_Data/23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md` khi cần xác định bộ train synthetic cuối.

| Nhóm | File tiêu biểu | Vai trò và phạm vi |
| --- | --- | --- |
| Bộ train synthetic cuối | `build_final_train.py`, `train_manifest.py`, `world_registry.py`, `audit_train_readiness.py` | Sinh/kiểm manifest, khóa vai trò train/validation/test, train T1 và đánh giá. `world_registry.py` cần `--cohort` để chỉ kiểm bộ cuối; mặc định quét cả các world lịch sử. |
| Kiểm toán quá trình phát triển dữ liệu | `audit_existing_world_metrics.py`, `audit_lifecycle_fix.py`, `audit_candidate_release_gates.py`, `audit_hard_case_fidelity.py`, `run_release_seed_counterfactual.py` | Bằng chứng cho các phiên bản ứng viên; không tự chứng minh độ sát dữ liệu doanh nghiệp thật. |
| Thu thập và dựng dữ liệu cũ | `crawl.py`, `build_worlds.py`, `build_big.py`, `build_hard_cases.py`, `build_multiworld.py`, `validate_worlds.py` | Tái lập các world `src/tgt/big/hc` và đối chiếu nguồn; các tên này không phải cohort cuối. `validate_worlds.py` mặc định kiểm `src,tgt,sens_uk,sens_coface`. |
| Thử nghiệm mô hình và đối chứng | `run_t1.py`, `run_t2_t3.py`, `run_t4.py`, `run_t6.py`, `run_t9.py`, `run_e2e.py`, `run_*baseline*.py`, các script `compare_*`, `sprint1/`, `sprint4/`, `sprint5/` | Mã tạo các kết quả lịch sử trong `outputs/`; kiểm protocol, dữ liệu và `measurement_version` của từng lượt trước khi trích dẫn. |
| Báo cáo và cổng | `make_report.py`, `evaluate_gates.py`, `implementation_status.py`, `analyze_results.py`, `verify_report_repeat.py` | Tổng hợp CSV/bằng chứng đã có. Đây không phải bước chạy lại toàn bộ thí nghiệm. `G11` của synthetic-only là `out_of_scope`; pilot thật vẫn cần G11. |
| Công cụ điều phối | `run_plan.py`, `dev.ps1`, `run_*.ps1`, `run_*.sh`, các chuỗi `sprint5/*.sh` | Điều phối các phép thử nhiều giờ và có thể ghi đè kết quả. `run_plan.py` mặc định chạy chuỗi lịch sử lớn, **không phải** pipeline v3 cuối. Chỉ dùng với danh sách `--jobs` được chọn rõ. |
| Nghiên cứu cục bộ | `data_audit/*.py` | Sáu script nghiên cứu nguồn T1; `.gitignore` hiện loại cả thư mục và test tương ứng. Có thể chạy ở máy này nhưng chưa được bảo đảm hiện diện trong clone khác. |
| Kiểm tra pilot trên synthetic | `pilot/privacy_t9_parity.py` | So sánh T9 trước/sau xử lý riêng tư trên dữ liệu synthetic; không phải số đo pilot doanh nghiệp thật. |

## Những chỗ dễ dùng nhầm

- Các chuỗi `sprint5/g13_*_chain.sh` và `sprint5/run_after_sprint6.sh` dùng `sprint5/wait_ram_then.sh` để chờ RAM trên Windows/Git Bash. Bước này đã được khôi phục; các chuỗi vẫn là kịch bản tái lập lịch sử và cần dữ liệu, môi trường Python tương ứng. Chúng nay dừng khi một bước chạy lỗi, nhưng vẫn cần kiểm log và kết quả trước khi trích dẫn.
- Bước kiểm tra tiến trình khác trong `sprint5/other_agent_busy.ps1` cần quyền đọc Win32_Process. Trong môi trường kiểm kê hiện tại, truy vấn CIM trả `Access denied`; chuỗi liên quan dừng với mã 2 thay vì ngầm coi tiến trình khác đã xong.
- Nhật ký Sprint 1 còn nhắc `sprint5/queue_rest.sh` và `sprint5/queue_rest2.sh`; hai file đó không còn trong repo. Đây là dấu vết của hàng đợi lịch sử, không phải lệnh tái lập sẵn có.
- Nhiều script cũ cần raw `customer_invoices`, BPI, SBA hoặc Parquet `src/tgt`; hiện `data/raw/` chỉ có WDI và OxCGRT. Kết quả lưu sẵn trong `outputs/` không cho thấy các script đó chạy được với bản workspace hiện tại.
- `crawl.py` tải Customer Invoices từ URL công khai. Nếu URL lỗi và bạn có file hợp lệ, truyền `--customer-invoices-file <đường-dẫn>`; không còn dự phòng bằng đường dẫn của máy tác giả cũ.
- `.venv/` ở workspace này có thư viện nhưng thiếu `.venv/Scripts/python.exe`. Các script PowerShell/Shell dùng đường dẫn đó sẽ dừng cho tới khi môi trường Python được tạo lại. Chưa chạy lại toàn bộ mô hình hoặc bộ test trong đợt kiểm kê này.
- Các thư mục `__pycache__`/file `.pyc` chỉ là cache Python, bị Git bỏ qua và không phải mã nguồn hay bằng chứng. Có thể xóa và Python sẽ tự sinh lại khi chạy.
