# G13 trên bộ đích sạch `tgt3` với nhãn T9 v2: đăng ký trước (22/10/2026, agent1-Khanh)

> Commit **trước khi** chạy `scripts/sprint5/g13_e2e_t9.py`. Mục 1–4 không đổi sau khi xem kết quả.

## 1. Câu hỏi
`G13_ALERT_POLICY.md` mục 5 cho thấy: cùng thế giới `tgt`, cùng chính sách đóng băng, nhãn T9 ước lượng cho báo giả 2,08/công ty-năm, nhãn thật cho 0,57.
**Nếu T9 v2 (precision 0,962, sai số ngày trả 0,82 ngày trên `tgt3`) làm nhãn, G13 có đạt trên một bộ đích chưa từng dùng cho G13 không?**

## 2. Thiết kế
- Thế giới: **`tgt3`** (30 công ty, niêm phong; dùng cho T9 v2 nhưng **chưa từng** chạy T6/E2E hay G13).
- Ba nhánh, cùng đầu vào, cùng quy trình `run_t6.main` (T1 học trên `src` + tinh chỉnh 12 tháng, mô phỏng copula-t, 52 tuần từ 2024-07-01):
  1. **`T9 v2`** (cấu hình đã chọn trên nguồn: `outputs/t9/v2/choice.json`) — nhánh **chính**.
  2. `T9 sprint3` (cấu hình cũ: không giới hạn tổ hợp, nhánh hazard bật).
  3. `nhãn thật` (oracle, cận trên).
- Nhãn từng nhánh: liên kết T9 → `build_bank_labels` → ngày trả ước lượng (không dùng `paid_date_true`); lời hứa qua `observed_promises` từ liên kết ước lượng.
- Chính sách cảnh báo: **đóng băng** (`outputs/g13/policy_choice.json`: MC-copula-t, isotonic học trên `src`, τ = 0,30, k = 1). Không chọn lại gì.
- CI: bootstrap theo công ty 200 lần.

## 3. Tiêu chí (cổng G13 không đổi)
Nhánh chính `T9 v2` đạt nếu: sự kiện > 0, phát hiện ≥ 4 tuần ≥ 0,70, độ sớm trung vị ≥ 4 tuần, báo giả ≤ 1,0/công ty-năm (điểm ước lượng).
Dòng cổng `G13_tgt3`. Dòng `G13` (tgt, E2E nhãn T9 cũ) giữ nguyên để kiểm toán.

## 4. Kỳ vọng và cách đọc (viết trước)
Nếu giả thuyết "G13 phụ thuộc chất lượng T9" đúng: báo giả `T9 v2` < `T9 sprint3`, và cả hai ≥ `nhãn thật`. Nếu `T9 v2` ≈ `T9 sprint3`, nhiễu nhãn không phải đòn bẩy chính.
Giới hạn biết trước: `tgt3` không có bản XML ⇒ hoá đơn quan sát lấy từ bảng hoá đơn gốc (cùng trường quan sát được như bản XML), không qua bước đọc XML.

## 5. Kết quả
_Điền sau khi chạy._
