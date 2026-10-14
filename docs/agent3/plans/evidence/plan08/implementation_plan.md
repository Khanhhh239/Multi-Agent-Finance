# Kế hoạch thực hiện PLAN_08 — 15/10/2026

Phạm vi được yêu cầu: engine thật và kiểm thử kỹ phần kỹ thuật; không tự phê duyệt các rule DRAFT của PLAN_07. OCR V2/PLAN_06 và nghiệm thu pháp lý/mapping vẫn mở.

1. **Chốt money boundary trước:** pin ZEN 0.53.0 trong venv ứng dụng, chạy lại spike; chọn Decimal phía adapter và chỉ truyền boolean/null đã kiểm kiểu sang ZEN. Reject float, số quá dài, scale không hỗ trợ và context sai revision. Kiểm thử độc lập với precision Decimal toàn cục.
2. **Hợp đồng và models:** model package pin hash/version/legal basis, explicit hit policy và no-hit ERROR. Ba họ model: nội dung, VAT, non-cash; mô hình thực tế giữ DRAFT. Đường approved chỉ dùng fixture tổng hợp. Payment proof là sidecar tin cậy có scope/revision, không suy từ chữ TM/CK trên hóa đơn.
3. **Adapter và trace:** chạy ZEN trong process có deadline/memory limit; lưu raw JSON trace nguyên vẹn, normalized conditions ghi ADAPTER và chính sách tính, engine matched row có nguồn riêng. Không dựng condition trace giả từ row hit.
4. **Executor và persistence:** chỉ ELIGIBLE, kiểm lại pinned planning snapshot; mọi unit chạy độc lập; retry hữu hạn theo key, lưu mọi attempt và chọn terminal duy nhất. Migration riêng cho artifacts/attempts append-only; API có auth/scope, idempotency và replay.
5. **Aggregator:** đếm units và distinct rules riêng; reject duplicate/stale/unexpected/non-eligible/malformed outcomes. Unknown/discovery/missing/operational blockers chặn FULL/PASS; FAIL không che review/errors. Contract error trả processing ERROR/verdict null.
6. **Kiểm chứng:** real-engine truth tables; Decimal boundaries và randomized oracle; timeout/crash/no-hit/malformed; multi-unit retry; exhaustive aggregate matrix; SQLite/audit/tenant/API/replay; chạy hồi quy capture/planning. Ghi lệnh, số test thực chạy, hashes và giới hạn, rồi commit/push.

Điều kiện bàn giao kỹ thuật: các invariant và ca lỗi trên qua test với engine thật, không có fallback PASS. Điều kiện bật pháp lý: rule/model/mapping được duyệt theo nguồn thực; chưa được thỏa chỉ bằng unit tests.
