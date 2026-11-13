# Hướng dẫn đọc `scripts/`

Các script ở đây gồm công cụ vận hành Workspace, pipeline dữ liệu synthetic, phép kiểm, thí nghiệm cũ và công cụ điều phối. **Tên `run_*.py` không đồng nghĩa với kết quả hiện hành.** Bộ train synthetic v4 là `data/synthetic/v4_shortpay_4shock_20261028_cohort.json`, artifact ở `outputs/data/v4_shortpay_4shock_20261028/`; đọc [báo cáo 25](../docs/02_Data/25_V4_SHORTPAY_4SHOCK_RETRAIN_2026-10-28.md). Bộ `v3_final_20261027` và các báo cáo riêng của v3 đã xóa. `infer_t1_final.py` xuất dự báo as-of cho hóa đơn còn mở từ artifact đã train; chẩn đoán v4 có script và đường dẫn trong báo cáo 25.

| Nhóm | File tiêu biểu | Vai trò và phạm vi |
| --- | --- | --- |
| Workspace và demo | `start-business.ps1`, `business/`, `pilot/check_portal_workspace_ui.py` | Khởi động dịch vụ, sinh/kiểm demo, dựng sổ tay và kiểm tra UI. Các file `business/rehearse_web.py` và `.cjs` phối hợp chạy máy chủ tạm và kiểm tra trình duyệt, không phải bản trùng. |
| Bộ train synthetic | `build_v4_shortpay_4shock.py`, `build_final_train.py`, `train_manifest.py`, `world_registry.py`, `audit_train_readiness.py` | Runner v4 và pipeline v3 lịch sử: sinh/kiểm manifest, khóa vai trò train/validation/test, train T1 và đánh giá. `world_registry.py` cần `--cohort` để chỉ kiểm cohort được chọn; mặc định quét cả các World lịch sử. |
| Kiểm toán quá trình phát triển dữ liệu | `audit_existing_world_metrics.py`, `audit_lifecycle_fix.py`, `audit_candidate_release_gates.py`, `audit_hard_case_fidelity.py`, `run_release_seed_counterfactual.py` | Bằng chứng cho các phiên bản ứng viên; không tự chứng minh độ sát dữ liệu doanh nghiệp thật. |
| Thu thập và dựng dữ liệu cũ | `crawl.py`, `build_worlds.py`, `build_big.py`, `build_hard_cases.py`, `build_multiworld.py`, `validate_worlds.py` | Tái lập các world `src/tgt/big/hc` và đối chiếu nguồn; các tên này không phải cohort cuối. `validate_worlds.py` mặc định kiểm `src,tgt,sens_uk,sens_coface`. |
| Thử nghiệm mô hình và đối chứng | `run_t1.py`, `run_t2_t3.py`, `run_t4.py`, `run_t6.py`, `run_t9.py`, `run_e2e.py`, `run_*baseline*.py`, các script `compare_*`, `sprint1/`, `sprint4/`, `sprint5/` | Mã tạo các kết quả lịch sử trong `outputs/`; kiểm protocol, dữ liệu và `measurement_version` của từng lượt trước khi trích dẫn. |
| Báo cáo và cổng | `make_report.py`, `evaluate_gates.py`, `implementation_status.py`, `analyze_results.py`, `verify_report_repeat.py` | Tổng hợp CSV/bằng chứng đã có. Đây không phải bước chạy lại toàn bộ thí nghiệm. `G11` của synthetic-only là `out_of_scope`; pilot thật vẫn cần G11. |
| Công cụ điều phối | `run_plan.py`, `dev.ps1`, `sprint5/wait_ram_then.sh` | Điều phối các phép thử nhiều giờ và có thể ghi đè kết quả. `run_plan.py` mặc định chạy chuỗi lịch sử lớn, **không phải** pipeline v3 cuối. Chỉ dùng với danh sách `--jobs` được chọn rõ. Các launcher và hàng đợi cũ đã dọn ngày 06/11/2026. |
| Kiểm tra pilot trên synthetic | `pilot/privacy_t9_parity.py` | So sánh T9 trước/sau xử lý riêng tư trên dữ liệu synthetic; không phải số đo pilot doanh nghiệp thật. |
| Bảo trì bản sao | `manage_duplicates.ps1`, `restore_cleanup_duplicates.ps1`, `restore_benchrec_archive.ps1` | Quản lý hardlink và khôi phục dữ liệu theo manifest. Dùng chung `archive_common.psm1` để kiểm đường dẫn và SHA-256. |

## Những chỗ dễ dùng nhầm

T6 hiện tại với partial và doanh nghiệp mới:
`business/evaluate_t6_new_company.py` có ba pha `lock`, `predict`, `score`,
dùng catalog và runtime đang phục vụ, không kích hoạt tenant. Kiểm tra tích
hợp toy mới: `business/verify_t6_new_company.py`. Xem
[hợp đồng và cách chạy](../docs/04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md).
Các backtest Workspace/global cũ dưới đây là phép đo lịch sử, không thay thế
quy trình khóa và chấm bundle partial hiện tại.

Backtest T6 global và Workspace theo phạm vi tiền (13/11/2026):

```powershell
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/backtest_t6_global.py
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/verify_t6_global.py
```

Chạy từ thư mục gốc workspace. Runner giữ nguồn/đầu vào/global release trong
snapshot riêng, học Workspace tại từng ngày chốt và chấm riêng thu công nợ mở
với số dư ngân hàng. Nhánh dự báo thu hóa đơn mới bị tắt theo yêu cầu. Các
stress là fixture phản thực tế từ cùng danh mục Đại Phát, không phải doanh
nghiệp hoặc holdout độc lập. Kết quả ở
`outputs/t6/global_scope_no_new_credit_20261113/REPORT.md` (tính từ `agent1/`).
Không ghi đè dữ liệu demo, không kích hoạt tenant và không đổi gate pilot.

- Output release-gate, artifact/model/inference v3 và báo cáo riêng của v3 đã xóa ngày 06/11/2026. `infer_t1_final.py` vẫn có mặc định v3 đã nghỉ dùng; nếu dùng với v4 phải truyền đủ `--cohort data/synthetic/v4_shortpay_4shock_20261028_cohort.json`, `--model-dir outputs/data/v4_shortpay_4shock_20261028` và `--output-dir <thư-mục-output-mới>`, cùng ngày `--as-of` phù hợp. Không chạy lệnh inference v3 mặc định hoặc hướng dẫn kiểm toán v3 lịch sử để kiểm chứng v4.
- Ngày 06/11/2026 đã xóa 16 launcher/hàng đợi cũ: sáu file điều phối ở gốc `scripts/`, bảy chuỗi G13, launcher fullweek và hai helper chờ tiến trình. Danh mục đường dẫn và SHA-256 ở [hồ sơ dọn](../outputs/maintenance/scripts_launcher_cleanup_20261106.json). Các tên này trong nhật ký hoặc manifest publish cũ chỉ còn là dấu vết lịch sử. `sprint5/wait_ram_then.sh` vẫn giữ vì còn được tham chiếu trong prereg Sprint 6.
- Việc xóa script Python ngày 11/11/2026 làm thay đổi hash tổng mã nguồn mà `code_provenance()` tính trên `agent1/` và `scripts/`. Manifest dữ liệu và bằng chứng cũ giữ nguyên hash lúc tạo; chúng không chứng nhận cây mã sau khi dọn. Muốn tái lập đúng hash cũ cần checkout phiên bản Git tương ứng; không thay hash trong manifest cũ để vượt kiểm tra nguồn của v4/v5.
- Nhật ký Sprint 1 còn nhắc `sprint5/queue_rest.sh` và `sprint5/queue_rest2.sh`; hai file đó không còn trong repo. Đây là dấu vết của hàng đợi lịch sử, không phải lệnh tái lập sẵn có.
- Nhiều script cũ cần raw `customer_invoices`, BPI, SBA hoặc Parquet `src/tgt`; hiện `data/raw/` chỉ có WDI và OxCGRT. Kết quả lưu sẵn trong `outputs/` không cho thấy các script đó chạy được với bản workspace hiện tại.
- `crawl.py` tải Customer Invoices từ URL công khai. Nếu URL lỗi và bạn có file hợp lệ, truyền `--customer-invoices-file <đường-dẫn>`; không còn dự phòng bằng đường dẫn của máy tác giả cũ.
- Môi trường `.venv/` đã được tạo lại và có `Scripts/python.exe` tại lần kiểm ngày 01/11/2026. Khi thiết lập workspace mới, làm theo [README gốc](../README.md#cài-đặt-và-kiểm-tra-trên-windows); riêng v6 có bộ phiên bản package khóa trong `experiments/t1_competing_v6/requirements.txt`.
- Lần kiểm này chạy được các test T1 và ngày nghiệp vụ; test dịch vụ chưa thu thập được do thiếu `fastapi` và `rapidfuzz`. Các phụ thuộc đó được khai báo qua [requirements-service.txt](../requirements-service.txt), cần cài trước khi chạy test dịch vụ.
- Các thư mục `__pycache__`/file `.pyc` chỉ là cache Python, bị Git bỏ qua và không phải mã nguồn hay bằng chứng. Có thể xóa và Python sẽ tự sinh lại khi chạy.

## Dọn và gộp ngày 11/11/2026

Đã bỏ ba script không có mã hiện hành gọi và chỉ dùng cho lần chạy cũ:

| File đã xóa | Lý do |
| --- | --- |
| `archive_t6.py` | Chỉ sao lưu kết quả T6 có `measurement_version` v4; kết quả hiện tại là v5 fullweek và bản lưu v4 đã tồn tại. |
| `diagnose_t1_caps.py` | Cố định đường dẫn cohort, mô hình và inference v3 đã xóa. |
| `sprint1/diag_real.py` | Cố định hai cache snapshot CI/BPI theo hash cũ; cả hai cache không còn tồn tại. |

Bốn công cụ quản lý bản sao đã gộp thành `manage_duplicates.ps1`. Khi đọc lệnh cũ trong hồ sơ bảo trì, đổi tên script và thêm `-Dataset` theo bảng dưới; giữ các tham số còn lại.

| Script cũ | Lệnh thay thế |
| --- | --- |
| `manage_t0_duplicates.ps1` | `.\scripts\manage_duplicates.ps1 -Dataset T0` |
| `manage_unified_v2_duplicates.ps1` | `.\scripts\manage_duplicates.ps1 -Dataset UnifiedV2` |
| `manage_research_duplicates.ps1` | `.\scripts\manage_duplicates.ps1 -Dataset Research` |
| `manage_small_duplicates.ps1` | `.\scripts\manage_duplicates.ps1 -Dataset Small` |

Mặc định `-Action Verify` chỉ đọc và đối chiếu manifest, kích thước, SHA-256. `Research` nhận `-Stage 8/9/10`; `Small` nhận `-Stage 11/12/13/14`; hai nhóm còn lại chỉ dùng `All`. `-RelativePath` phải khớp chính xác một mục. `Compact` tạo hardlink, `Restore` tạo bản sao độc lập và phục hồi thời gian/thuộc tính gốc; cả hai giữ kiểm tra trước khi ghi, backup và rollback khi lỗi.

```powershell
.\scripts\manage_duplicates.ps1 -Dataset Research -Stage 8
.\scripts\manage_duplicates.ps1 -Dataset Small -Action Compact -WhatIf
.\scripts\manage_duplicates.ps1 -Dataset UnifiedV2 -Action Restore -WhatIf
```

Các manifest và lệnh ghi trong `outputs/maintenance/` là hồ sơ lịch sử, được giữ nguyên. Script nghiên cứu còn được pipeline, test hoặc giao thức tái lập sử dụng vẫn được giữ.

Kiểm tra chỉ đọc ngày 11/11/2026: cặp đầu tiên của `UnifiedV2` khớp manifest; cặp đầu tiên của `T0`, `Research` và `Small` thiếu file nguồn được giữ lại. Công cụ từ chối thao tác khi thiếu/sai file; không dùng các manifest này để khôi phục trước khi bổ sung đúng nguồn. Kiểm thử thao tác dùng dữ liệu tạm trong `tests/test_maintenance_scripts.py`, gồm `Verify`, `WhatIf`, hardlink, khôi phục, rollback và bảo toàn timestamp UTC.

## Bản sao T0 đã dọn

Đợt [dọn lưu trữ 31/10/2026](../outputs/maintenance/cleanup_2026-10-31.md) bỏ các payload trùng byte ở chín thư mục chạy thử T0, giữ đủ ba bộ `offline-v2/v3/v4-2026-10-21-final` và giữ các báo cáo, manifest, kết quả riêng. Khi cần mở lại một lần chạy thử theo đúng đường dẫn cũ, dùng `restore_cleanup_duplicates.ps1`; script kiểm SHA-256 trước khi sao chép và từ chối ghi đè dữ liệu khác.

```powershell
.\scripts\restore_cleanup_duplicates.ps1 -VerifyOnly
.\scripts\restore_cleanup_duplicates.ps1 -Run offline-v2-2026-10-21-initial
```

Bỏ `-Run` để khôi phục tất cả 538 bản sao; dùng `-WhatIf` để chỉ xem các đường dẫn sẽ được khôi phục.
