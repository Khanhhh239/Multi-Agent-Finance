# Gate PLAN_09 — compliance integration

Ngày: **15/10/2026**. **PASS tích hợp kỹ thuật; nghiệm thu M2 pháp lý/dữ liệu thật còn PENDING.** [Validation](plan09/validation_summary.json): **310/310 Python tests**, syntax/DOM checks và 6 nhóm kiểm tra Chrome desktop/mobile PASS; không có page errors.

[Kế hoạch thực hiện](plan09/implementation_plan.md) · [Demo/API/UI](plan09/demo_runbook.md) · [Phục hồi](plan09/recovery.md) · [Báo cáo nghiệm thu](plan09/compliance_mvp_report.md) · [Release manifest](plan09/release_capture_compliance_v1.json).

| Task | Trạng thái |
|---|---|
| T01 | Orchestrator theo revision, snapshots, idempotency/resume và re-evaluate với public ID mới |
| T02 | Evaluation API, signed cursor cho rule-results/attempts, detail/export/replay và lịch sử revision |
| T03 | Template Việt cố định, verdict lấy aggregate, selected legal refs và evidence links; contract error không diễn giải thành kết luận thuế |
| T04 | UI chất lượng dữ liệu tách compliance; sources/citations, counts, attempts, dirty-draft guard, revision change và capture export độc lập |
| T05 | Acceptance tổng hợp và regression; actual native ZEN, SQLite/API và Chrome desktop/mobile |
| T06 | **PENDING** — chưa có approved real rules/mappings và expected legal labels/frozen legal set độc lập; public smoke không thay legal accuracy |
| T07 | Demo/offline templates và recovery runbook; không cần LLM, không sửa raw/outcome để retry |
| T08 | Manifest kỹ thuật có hash/version; **M2 legal release chưa chốt** |

Lệnh tái hiện:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\check_compliance_browser.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_plan09.py
```

Migration 009 thêm evaluation requests/reports, giữ dữ liệu/stage artifacts cũ. UI mở bằng `OPEN_AGENT3.cmd` sau khi khởi động lại server. Kiểm tra là thao tác người dùng trên revision đã lưu; chưa tự chạy compliance khi upload. Report lịch sử immutable, current-head flag nằm ngoài report; API mới không ghi đè hoặc thay key outcome gốc.

Smoke bổ sung trên **1 trang PDF CyberBill công khai**, router/OCR PP-OCRv6 + VietOCR thật: COMPLETED, REVIEW, coverage NONE, 0 unit chạy luật và replay verified. Thời gian lượt đo khoảng **374 giây**, gồm OCR, không phải SLA hoặc legal accuracy. [Metadata và giới hạn](plan09/public_smoke.json); không đưa nội dung chứng từ thật vào Git.

Giới hạn: synchronous MVP API; lịch sử mỗi revision hiện tối đa 20 evaluations; chưa scheduler tự resume compliance; OCR accuracy/calibration/legal review và non-cash proof ingestion/matching chưa được nghiệm thu. Mọi report hiện `technical_only=true`, rules/models catalog vẫn DRAFT. Không có phát hành rule thuế thực tế chỉ vì unit/browser test qua.

Bàn giao PLAN_10–11 có thể tiếp tục mở rộng nguồn trên nền kỹ thuật; PLAN_12 là nhánh tùy chọn cho explanation, PLAN_14 nhận manifest để hardening. Các gate còn mở không được đánh dấu DONE.
