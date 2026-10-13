# Gate PLAN_00 — 11/10/2026

## Quyết định hiện hành — PASS kỹ thuật

**PLAN_00 DONE trong phạm vi `technical-functional-v1`.** Người dùng đã chọn thu hẹp scope để tiếp tục PLAN_01. [Decision record](plan00/technical_scope_decision.md) quy định phạm vi và DQ-01–05 chuyển sang nghiệm thu PLAN_05–06. Những ghi nhận BLOCKED bên dưới là lịch sử trước quyết định này, không là trạng thái bàn giao hiện tại.

| Task | Quyết định trong scope mới | Bằng chứng |
|---|---|---|
| T01/02/03 | DONE | Scope/field matrix, inventory, coverage, schema/manifest v1 đã có |
| T04 | DONE kỹ thuật | Guideline/schema/5 examples, generator ground truth; human adjudication chuyển DQ-02, không đổi label status |
| T05 | DONE kỹ thuật | 30 file project-generated/10 logical documents; real pilot chuyển DQ-01 |
| T06 | DONE cho fixture project | Groups/splits/known variants đã kiểm; real accuracy freeze chuyển DQ-03/04 |
| T07/08 | DONE | Metric definitions, dataset card và hồ sơ bàn giao; accuracy targets TBD có gate/owner |

Kiểm chứng lại sau quyết định, cwd `D:\financial`:

```powershell
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\prepare_plan00_dataset.py --verify-only
```

Kết quả: **PASS: 1183 sources hashed; 30 synthetic fixtures; geometry/native-scan types; split leakage and known variants checked**. Command verify-only không rebuild hoặc sửa manifests/annotations. JSON Schema validation trước đó được giữ trong `plan00/validation_summary.json`; config/runtime/hash trong `plan00/build_summary.json`.

PLAN_01 nhận scope mới, annotation/manifest schema v1, fixture `functional_set_v1`, metric definitions và giới hạn DQ-01–05. **Cập nhật sau bàn giao:** PLAN_01 đã hoàn thành nền móng theo [gate_01](gate_01.md); trạng thái runtime/contracts xem gate riêng này. FATURA là bộ bổ sung, không bắt buộc cho gate kỹ thuật; terms/human review chưa hoàn tất, accuracy eligibility vẫn false. MC-OCR tiếp tục QUARANTINE cho pipeline mới. Không train OCR, không chạy model, không nghiệm thu accuracy thực tế.

## Lịch sử gate trước khi thu hẹp phạm vi

**Quyết định: BLOCKED một phần; chưa DONE.** Đã hoàn thành phạm vi, kiểm kê, hợp đồng annotation/manifest, fixture chức năng và metric definitions. Chưa có dữ liệu hóa đơn thuế Việt Nam thực tế/người review độc lập, nên chưa đạt gate đầy đủ theo PLAN_00.

Người dùng xác nhận chưa có bộ dữ liệu này và yêu cầu link để tự tải. Đã chuẩn bị [nguồn tải và vị trí đặt dữ liệu](plan00/data_sources_and_downloads.md); không phát sinh đăng ký/gửi thông tin thay người dùng.

**Cập nhật sau tải 11/10/2026:** đã nhận FATURA2 v2, checksum chính thức/ZIP CRC và 50.004 file giải nén đều PASS. Có 10.000 invoice instances tổng hợp, 20.000 JPG và 30.000 JSON; không có PDF/hóa đơn thuế Việt Nam thực tế. Chưa import hoặc train; cần mapping tọa độ/annotation, template-disjoint splits và kiểm điều kiện dùng. [Báo cáo chi tiết](plan00/fatura_download_check.md).

**Cập nhật mới nhất — hoàn thành bước 1–4:** [mapping và QA FATURA](plan00/fatura_preparation_report.md) đã tạo 20.000 annotation/manifest rows, chia 30 dev/10 calibration/10 test templates, chọn 50 pilot dev-only và rà trực quan bằng AI. Có 41 curated visual checks và schema/checksum reports. Đây là import annotation vào dataset cục bộ, chưa nối CFR runtime/chạy model. Mapping và split FATURA không còn là việc chưa thực hiện; independent human review, terms, PDF/invoice Việt Nam vẫn thiếu. Giữ gate BLOCKED một phần.

## Bằng chứng từng task

| Task | Trạng thái | Artifact và bằng chứng | Phần còn thiếu |
|---|---|---|---|
| P00-T01 | DONE | [Scope/field matrix](plan00/scope_capture_mvp.md) | Supported formats là scope đích, chưa claim đã implement |
| P00-T02 | DONE | [Inventory](plan00/inventory.md), runtime probe và existing manifests | Model load/GPU smoke để PLAN_03 |
| P00-T03 | DONE | [Coverage](plan00/coverage_matrix.csv), local catalog/manifests: bộ trước + FATURA riêng | Real invoice coverage = 0 được khai báo |
| P00-T04 | PARTIAL | Guideline/schema v1, 20.000 FATURA annotations, [50 AI visual reviews](plan00/fatura_pilot_review_summary.json) | Annotator B và adjudication vẫn pending |
| P00-T05 | PARTIAL theo scope gốc; pilot FATURA đã xong | 30 project fixtures + FATURA pilot 50 logical docs/25 dev templates | Không có 30 tài liệu thực tế/PDF theo scope; generated data không thay real accuracy set |
| P00-T06 | FATURA kỹ thuật PASS; tổng thể PARTIAL | 30/10/10 template splits, source variants cùng family; exact hash cross-split = 0 | FATURA terms/label review và near-template audit; MC-OCR 8 cross-split groups/244 candidates vẫn pending |
| P00-T07 | DONE | [14 metric definitions](plan00/acceptance_matrix.csv) | Target accuracy/SLO TBD trước PLAN_05–06; auto acceptance tắt |
| P00-T08 | DONE về đóng gói | [Dataset card](plan00/dataset_card.md), hashes trong [build summary](plan00/build_summary.json), gate này | Gate chung còn BLOCKED, không là release certification |

## Input và phiên bản

- NEW_PLAN và PLAN_00 hiện hữu; scope OCR/PDF-first.
- Config `agent3_tax_compliance/configs/datasets/plan00_v1.json`; generator `scripts/prepare_plan00_dataset.py`.
- Runtime probe Python 3.10.5; PyMuPDF 1.28.2/Pillow 12.3.0. Không cài hoặc nâng cấp dependency.
- Full-image legacy manifests 922 dev + 231 test; source/annotation vẫn ở vị trí cũ.
- Config/generator/font/manifest/split hashes trong build summary; không giả version code là Git commit vì workspace không có repository Git ở root.

## Commands và kết quả

Cwd: `D:\financial`.

```powershell
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\prepare_plan00_dataset.py
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\prepare_plan00_dataset.py --verify-only
```

Build/verify kiểm 1.183 source rows: 1.153 existing receipts + 30 synthetic files. Kiểm source hash, unique IDs, schema structure/status/value, bbox bounds/page range, native text vs scan PDF, trỏ evidence đúng text tiếng Việt, mọi trang cùng document, duplicate/template group ở cùng split, known resize/rotate detector, manifest/split hashes.

Đã validate bằng JSON Schema Draft 2020-12: 30 annotation files và 1.183 manifest rows. Acceptance CSV có 14 metrics, 9 columns nhất quán. Kiểm thêm negative schema examples để chặn OBSERVED/null, unreadable không evidence/reason và QUARANTINE nhưng accuracy_eligible=true. Kết quả kiểm chứng lưu ở `plan00/validation_summary.json`.

Đã xem ảnh `syn-09-image.png`: nhãn giả lập và nội dung tiếng Việt hiển thị được, không bị chồng vùng trên mẫu này. Đây là visual smoke một mẫu, không thay annotator B hoặc đánh giá toàn dataset. Không chạy OCR/benchmark/model inference; không có số accuracy production.

## Chưa đạt và điều kiện gỡ

| Blocker | Điều kiện gỡ | Việc độc lập đã làm |
|---|---|---|
| FATURA đã chuẩn bị, chưa đủ điều kiện accuracy release/scope gốc | Terms/independent labels review và dữ liệu PDF/invoice Việt Nam | Mapping 10.000 instances, 20.000 variant annotations, split 30/10/10 và pilot 50 đã có [bằng chứng](plan00/fatura_preparation_report.md) |
| Chưa có reviewer độc lập | Chỉ định người đối chiếu 5 ví dụ, phân xử critical labels trước freeze real test | Guideline, examples và disagreement CSV sẵn sàng |
| MC-OCR permission record chưa thấy | Có bằng chứng đăng ký/điều kiện dùng tương ứng; giữ source terms | Chỉ inventory/hash, QUARANTINE bộ mới |
| Legacy split rò rỉ và thiếu template audit | Gom exact/near duplicates và vendor/template groups, chia từ data được phép; đánh dấu lịch sử exposure | Báo cáo 31 exact groups, 8 cross-split và 244 candidates, không chỉnh benchmark cũ |

## Bàn giao

Scope, schemas, synthetic fixtures và metric definitions đủ cho **chuẩn bị độc lập** contracts PLAN_01. Chưa tự chuyển PLAN_01 IN_PROGRESS: gate đầy đủ PLAN_00 vẫn thiếu real data/second review. Có thể thu hẹp scope chính thức thành synthetic-functional-only khi có quyết định rõ, nhưng không đổi definition of done hoặc tuyên bố real invoice accuracy ngầm.

Raw/model/env/database cũ giữ nguyên. Dữ liệu thật không được copy vào fixture CI; local manifests và incoming có ignore rules riêng. Không deploy hoặc gửi thông tin ra ngoài.
