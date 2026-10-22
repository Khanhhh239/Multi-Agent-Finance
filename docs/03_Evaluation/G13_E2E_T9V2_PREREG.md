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
Chạy 22/10/2026 (`outputs/g13/e2e_tgt3/alert_policy_tgt3.csv`, `g13-e2e-t9v2-tgt3-v1`), chính sách đóng băng, 46 sự kiện thiếu tiền, 30 công ty, CI bootstrap theo công ty:

| Nhánh | Hoá đơn đã trả có nhãn | Sai số ngày (có nhãn) | Phát hiện ≥4 tuần [CI] | Độ sớm | Báo giả/công ty-năm [CI] | Brier 13 tuần |
|---|---|---|---|---|---|---|
| **T9 v2 (chính)** | 59,5% | 0,71 | 0,848 [0,74; 0,96] | 10,5 | **2,709 [1,97; 3,45]** | 0,181 |
| T9 sprint3 | 69,8% | 2,64 | 0,826 [0,73; 0,95] | 10,8 | 2,408 [1,71; 3,18] | 0,147 |
| Nhãn thật (cận trên) | 100% | 0 | 0,804 [0,70; 0,92] | 8,1 | **0,903 [0,53; 1,30]** | 0,115 |

**Cổng `G13_tgt3` (nhánh chính T9 v2): TRƯỢT** (báo giả 2,709 > 1; CI dưới 1,97 cũng > 1). Phát hiện và độ sớm đạt.

**Đọc kết quả (phải ghi cả chỗ kỳ vọng ghi trước bị lệch):**
- Mục 4 viết trước: "nếu T9 v2 ≈ T9 sprint3 thì nhiễu nhãn không phải đòn bẩy chính". T9 v2 **không** cải thiện (2,71 so với 2,41; hơi tệ hơn).
  Nhưng nhánh nhãn thật cho 0,90 ⇒ **nhãn ước lượng vẫn là nguyên nhân chính gây báo giả**, chỉ là T9 v2 không sửa được nó.
  Nghĩa là câu "nhiễu nhãn không phải đòn bẩy" của tôi hẹp hơn dữ liệu: đòn bẩy là **chất lượng nhãn theo nghĩa độ phủ**, không phải độ chính xác từng nhãn.
- **Báo giả tăng đúng theo thứ tự thiếu nhãn:** 100% → 0,90; 69,8% → 2,41; 59,5% → 2,71. T9 v2 đổi 10 điểm độ phủ lấy độ chính xác ngày (2,64 → 0,71 ngày), và độ chính xác đó **không** bù lại.
  Cách giải thích hợp lý: hoá đơn đã trả mà không có nhãn bị T1 coi là còn mở, nên dự báo trễ và nguy cơ thiếu hụt bị đánh cao. **Đây là giả thuyết nhất quán với 3 điểm, chưa kiểm trực tiếp** (cần ablation: gán nhãn thật cho một phần hoá đơn).
- T9 v2 được chọn trên nguồn với ràng buộc precision ≥ 0,975 (đúng đăng ký của G15), còn G13 cần **recall**. Hai cổng kéo hai hướng ngược nhau với cùng một bộ ghép.
- Vì vậy G15 (F1 ≥ 0,8) và G13 (báo giả ≤ 1) cùng đòi một việc: **tăng độ phủ nhãn mà giữ precision**. Đòn bẩy ngoài mô hình: số hoá đơn trong nội dung chuyển khoản.
