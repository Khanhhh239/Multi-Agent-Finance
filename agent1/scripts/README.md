# Công cụ Agent 1

Đọc [pipeline hiện tại](../docs/04_AI_Methods/01_pipeline_he_thong.md) trước khi chọn runner. Tên `run_*.py` không có nghĩa đó là đường phục vụ `/v1`.

| Nhóm | Công cụ | Phạm vi |
|---|---|---|
| Vận hành Workspace | `start-business.ps1`, module `agent1_service.jobs.t1_update` | Khởi động/kho riêng; job gọi cùng `methods.train` như API/worker, không tự cài scheduler |
| Đóng gói catalog | `package_t1_global_catalog.py` | Xuất catalog/model/prior/replay theo contract; kiểm manifest và hash, không tự kích hoạt tenant |
| Demo và hướng dẫn | `business/make_large_demo.py`, `package_pilot.py`, `build_handbook.py`, `print_handbook.cjs` | Sinh/đóng gói dữ liệu synthetic và tài liệu từ Markdown; thao tác ghi cần thư mục/nguồn đúng |
| Kiểm T6 hiện tại | `business/evaluate_t6_new_company.py`, `verify_t6_new_company.py` | Lock → predict → score với bundle/adapter hiện tại; toy chỉ kiểm chức năng |
| Kiểm API/UI | `business/verify_t1_partial_bundle.py`, `verify_t10_bundle.py`, `pilot/check_portal_workspace_ui.py`, `business/rehearse_web.py` và `.cjs` | Mỗi công cụ có môi trường/fixture riêng; đọc tham số trước khi nối dịch vụ |
| Dữ liệu synthetic | `build_v4_shortpay_4shock.py`, `train_manifest.py`, `world_registry.py`, `audit_train_readiness.py` | Recipe/provenance/cohort; kiểm tồn kho trước khi train, không sinh đè World frozen |
| Nghiên cứu cũ | `run_t*.py`, `compare_*`, `sprint*/`, `business/backtest_*`, `run_plan.py` | Có thể train nhiều giờ/ghi đè output; hợp đồng khác runtime hiện tại |
| Tổng hợp báo cáo cũ | `make_report.py`, `evaluate_gates.py`, `implementation_status.py`, `verify_report_repeat.py` | Có thể nhắc/sinh báo cáo Markdown đã xóa; không là phép nghiệm thu hiện tại |
| Bảo trì bản sao | `manage_duplicates.ps1`, `restore_cleanup_duplicates.ps1`, `restore_benchrec_archive.ps1`, `archive_common.psm1` | Verify/hash/mapping và phục hồi/hardlink; phải có payload nguồn phù hợp |

## Trước khi chạy

Chạy từ root/import path mà script thực sự yêu cầu; README gốc dùng gốc repository chung, nhiều runner nghiên cứu giả định cwd `agent1/`. Kiểm `--help` và mã thay vì chép lệnh từ nhật ký cũ. Môi trường ở gốc có `.venv/Scripts/python.exe`.

`data/` hiện không có raw/Parquet; `data/synthetic/` giữ 10 template config/manifest và 3 JSON cohort/design/calibration cho bộ dựng compact. Metadata của các bộ thử nghiệm đã nghỉ dùng đã bỏ. World mới dưới `outputs/t1/` là bộ khác, cần manifest riêng. [Data](../docs/02_Data/README.md) và [outputs](../outputs/README.md) ghi ranh giới; mặc định inference/benchmark v3/v4/v6 có thể trỏ file không còn. Phải có đúng payload/source/runtime để tái lập; không đổi hash để vượt kiểm tra.

Backtest T6 global/Workspace cũ không thay lock → predict → score của partial runtime. Các verifier snapshot cũ có thể thiếu source/plan sau dọn output; chạy nghiên cứu mới phải dùng thư mục mới. Không lấy các bảng lưu sẵn để xác nhận mã hiện tại đã chạy.

## Bảo trì và dựng tài liệu

`manage_duplicates.ps1` có `-Dataset T0/UnifiedV2/Research/Small`; mặc định `-Action Verify` chỉ đọc. `Research` dùng stage 8–10, `Small` 11–14. `Compact` tạo hardlink, `Restore` tạo bản sao độc lập. Kiểm `-WhatIf`, mapping và hash trước thao tác; manifest thiếu payload không thể tự khôi phục nguồn.

Nguồn sổ tay là [SO_TAY_AGENT1.md](../docs/06_Pilot/SO_TAY_AGENT1.md); giữ marker `PUBLIC_GUIDE` mà builder đọc. Nguồn ZIP Đại Phát là [hướng dẫn đầu vào](../docs/06_Pilot/DEMO_INPUT_TRAIN_DAIPHAT.md); gói pilot đọc file trong [pilot](../pilot/README.md). HTML/PDF/ZIP có sẵn chưa chắc đồng bộ; dựng và kiểm đầu ra trước khi phát hành. Dọn Markdown không tự chạy các builder hoặc ghi lại gói demo.

`build_handbook.py` dùng `Markdown` hoặc `markdown-it-py`; hướng dẫn web hiện đã dựng lại từ sổ tay, bỏ ảnh của giao diện cũ. PDF cần dựng riêng. `package_pilot.py` đóng ba Markdown và bốn fixture hiện tại, sinh hai CSV biểu mẫu trống trong ZIP; không cần file kết quả trong checkout. Web/pilot chỉ giữ demo Đại Phát; dữ liệu và bộ dựng Minh An cũ đã bỏ. ZIP Đại Phát đọc hướng dẫn hiện tại khi đóng lại; không lấy bản ZIP cũ làm nguồn dữ liệu chuẩn.
