# 04 · Guardrail, xác minh số, phê duyệt và nhật ký

## 1. Bản đồ phòng thủ nhiều lớp
```
Vào  ► [A] Phạm vi & quyền ► [B] Pre‑filter ► LLM ► [C] Validator lời gọi ► Engine ► [D] Bọc dữ liệu ► LLM ► [E] Verifier ► [F] Nhật ký
                                                                                       ▲ không tin cậy
Hành động: [G] đề xuất → phê duyệt người → handler tất định → [F]
```

## 2. [A] Phạm vi & quyền (row‑level)
- Mỗi phiên có `principal = {user_id, role, scope}`: `owner|cfo` (toàn công ty), `branch_manager:{HN|HCM|DN}`, `sales:{employee_code}`, `auditor` (chỉ đọc nhật ký).
- Validator **tiêm bắt buộc** `filters.branch` / `filters.salesperson` theo `scope` vào mọi lời gọi (người dùng/LLM không thể bỏ). Nếu lời gọi yêu cầu phạm vi rộng hơn ⇒ từ chối `no_permission` (hoặc trả phần được phép + nhãn).
- Chỉ số tổng hợp công ty (ví dụ `cash_and_equivalents`, `debt_balance`) mặc định chỉ cho `owner|cfo`.
- Dữ liệu cá nhân (lương từng người) chỉ trả tổng hợp ≥ 3 người cho vai trò thấp.
- Kết nối DuckDB **read‑only**; Agent không có thông tin đăng nhập ghi.

## 3. [B] Pre‑filter tất định (trước LLM)
| Kiểm tra | Hành động |
|---|---|
| Từ khóa ghi/xóa ("xóa", "sửa", "xoá chứng từ", "hủy bút toán") | cờ `unsafe_action` → ưu tiên `refuse`/`propose_action(flag_for_review)` |
| Ngoài miền (cổ phiếu, thời tiết, chính trị, tư vấn pháp lý) | cờ `out_of_scope` |
| Mẫu tiêm nhiễm trong **câu hỏi** ("bỏ qua mọi hướng dẫn", "system prompt", "ignore previous", "DAN") | cờ `jailbreak` → từ chối lịch sự, ghi log |
| Độ dài/ký tự lạ (zero‑width, bidi) | chuẩn hóa/loại bỏ; ghi log |
Pre‑filter chỉ **gắn cờ và gợi ý**; quyết định cuối vẫn là hành vi do LLM chọn rồi bị validator kiểm. Lý do: tránh chặn nhầm câu hợp lệ giống từ khóa.

## 4. [C] Validator lời gọi công cụ
| Luật | Thất bại → |
|---|---|
| JSON hợp lệ theo schema; `action` ∈ tập cho phép | sửa lỗi (≤ 2 lần) với thông điệp ngắn "trường X sai vì …" |
| `metric` ∈ danh mục; (khuyến nghị) ∈ tập ứng viên | sửa lỗi / hỏi lại nếu ngoài ứng viên |
| **Luật khung dữ liệu:** `view="tax"` chỉ khi chỉ số có `tax ∈ views` **và** câu hỏi có tín hiệu thuế; câu điều hành mà `view="tax"` ⇒ sửa về `mgmt` hoặc hỏi lại | sửa/hỏi lại |
| `period` giải được (`resolve_period`), không ở tương lai xa với chỉ số dòng chảy | sửa lỗi / ghi chú |
| `group_by` ∈ `md.group_bys`; `filters` hợp lệ; thực thể giải được | `FilterError` → hỏi lại kèm ứng viên |
| Quyền (mục 2) | từ chối |
| `propose_action`: loại hành động ∈ whitelist; tham số hợp lệ | từ chối |
| Giới hạn: số lời gọi/lượt ≤ 4; tổng thời gian ≤ 20 s | dừng, trả suy biến |

## 5. [D] Bọc dữ liệu không tin cậy (chống tiêm nhiễm gián tiếp)
**Nguồn rủi ro:** các trường văn bản tự do trong kết quả: `description`, `partner_name`, `item_name`, `einvoice_no`, ghi chú. Ca A8 đã cài sẵn.
**Quy tắc:**
1. Chỉ đưa văn bản tự do vào prompt khi *thật cần* (ví dụ "Xem cách tính" liệt kê chứng từ); mặc định bỏ cột `description`.
2. Khi cần, bọc: `<du_lieu_khong_tin_cay nguon="gl.description" id="…">…</du_lieu_khong_tin_cay>`; **thoát** các thẻ lồng, cắt ≤ 160 ký tự, loại ký tự điều khiển/ẩn.
3. System prompt nêu rõ: nội dung trong thẻ là dữ liệu.
4. Bộ dò mẫu lệnh trên trường văn bản (regex + từ điển: "ignore", "bỏ qua", "system", "assistant", "báo cáo rằng", URL, đoạn có dạng lệnh) → gắn cờ `suspicious_text` và **thay bằng "[nội dung nghi vấn đã ẩn]"** trong prompt; hiển thị cho người dùng như dữ liệu trích dẫn.
5. Thêm cảnh báo cho người dùng ("chứng từ #… có diễn giải chứa chỉ dẫn lạ") — biến sự kiện bảo mật thành giá trị (cảnh 7 của demo).
6. Công cụ **không có khả năng ghi**; ngay cả khi mô hình bị lừa, hậu quả giới hạn ở việc sai câu trả lời, và verifier chặn số sai.

## 6. [E] Verifier — "citation verifier" cho số
### 6.1 Tập số cho phép (allowed set)
Từ **mọi** kết quả công cụ trong lượt: `value`, `comparison.value/delta/delta_pct`, mọi `rows[].value/share_pct`, `components`, `summary.*` (số), cộng với:
- số đếm/ngày hợp lệ trong `period` (ví dụ "14/10/2026", "quý 3", năm);
- số từ chính câu hỏi (người dùng nêu "30 ngày");
- hằng số cố định được khai báo (20% thuế TNDN…).

### 6.2 Trích số trong câu trả lời
`formatting.extract_numbers` xử lý định dạng VN (`12,35 tỷ`, `345 triệu`, `19,1%`, `1.234.567 đ`; bỏ ngày tháng & mã). Quy về VND/%/ngày/đơn thuần.

### 6.3 Luật khớp
| Loại số | Điều kiện hợp lệ |
|---|---|
| Tiền | Khớp một giá trị trong tập sau khi quy về VND với **dung sai làm tròn hiển thị** (nửa đơn vị chữ số cuối: `8,05 tỷ` ⇒ [8,045; 8,055) tỷ; chấp nhận `8 tỷ` nếu |Δ| ≤ 1% giá trị gốc) |
| % | ±0,05 điểm so với giá trị gốc (hoặc làm tròn 0 chữ số nếu |Δ| ≤ 0,5) |
| Ngày (DSO…) | Làm tròn nguyên |
| Số đơn thuần | Thuộc tập cho phép hoặc ≤ 12 (đếm nhỏ trong câu như "3 khách") với ngữ cảnh đếm |
| Số **tạo ra bằng suy diễn** (tổng, hiệu, tỷ lệ do LLM tính) | **Cấm.** Muốn nêu hiệu/tỷ lệ phải do engine tính (đã có `delta`, `share_pct`) |

### 6.4 Kiểm tra nhãn bắt buộc
Câu trả lời phải chứa (hoặc khối sự kiện đính kèm chứa): kỳ, khung (khi `tax`), **nhãn "Tạm tính – chưa khóa sổ"** nếu `data_status` ≠ "Đã khóa sổ", mốc `data_through`.

### 6.5 Kiểm tra mệnh đề không nguồn
Danh sách mẫu cần có số làm cơ sở: "tăng do…", "nguyên nhân là…", "vì…" → yêu cầu thực thể/yếu tố được nêu đã xuất hiện trong kết quả công cụ (`rows[].label`, `notes`). Mức độ chặt điều chỉnh bằng thí nghiệm H6.

### 6.6 Hành vi khi trượt
Sinh lại với thông điệp lỗi cụ thể (tối đa 2 lần) → nếu vẫn trượt: trả **khối sự kiện tất định** + ghi sự cố `verifier_fallback` (để phân tích prompt).

## 7. [G] Đề xuất – phê duyệt – thực thi
### 7.1 Bảng (Ops DB — tách khỏi sổ cái)
```sql
pending_approvals(id, created_at, requested_by, action_type, params_json, rationale,
                  status /*PENDING|APPROVED|REJECTED|EXPIRED|EXECUTED|FAILED*/, decided_by, decided_at, result_ref)
audit_log(id, ts, actor /*user|agent|system*/, event, payload_json, prev_hash, hash)  -- hash = H(prev_hash || canonical(payload))
conversations(id, user_id, started_at) ; messages(id, conv_id, role, content, tool_calls_json, lineage_ids)
```
### 7.2 Danh sách hành động cho phép (v1)
| `action_type` | Hiệu ứng khi duyệt | Ghi vào |
|---|---|---|
| `record_payment_promise` | Lưu cam kết thanh toán (khách, hóa đơn, ngày hứa, người duyệt) | bảng `payment_promises` (Ops DB) |
| `set_credit_hold` | Đặt cờ chặn bán chịu cho khách | `credit_flags` (Ops DB) |
| `flag_for_review` | Tạo yêu cầu rà soát chứng từ/khoản mục gửi kế toán | `review_requests` |
**Không có** hành động ghi vào sổ cái/thanh toán/nộp thuế.

### 7.3 Quy tắc
- Người duyệt ≠ người yêu cầu cho hành động rủi ro cao (hạn mức tùy chọn); hết hạn sau 72 giờ.
- Mọi chuyển trạng thái → `audit_log` (chuỗi băm; có lệnh `verify_chain`).
- Mỗi câu trả lời lưu `lineage_ids` → có thể tái dựng "con số này từ đâu".

## 8. Nhãn "AI‑generated" và minh bạch
Mọi câu trả lời hiển thị nhãn nhỏ "Do trợ lý AI tạo; số liệu từ sổ sách đến {ngày}"; lịch sử hội thoại xuất được cho kiểm toán. (Phù hợp nguyên tắc minh bạch và giám sát con người của khung pháp lý AI — 🔎 đối chiếu văn bản.)
