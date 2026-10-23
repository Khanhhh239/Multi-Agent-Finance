# G13 với nhãn mềm T9 trên bộ đích mới `tgt5`: đăng ký trước (23/10/2026, agent1-Khanh)

> Commit **trước khi** sinh `tgt5` và chạy `scripts/sprint5/g13_e2e_t9.py` với `G13_WORLD=tgt5`. Mục 1–4 không đổi sau khi xem kết quả.

## 1. Căn cứ
- Ablation (`G13_E2E_T9V2_PREREG.md` mục 6): giữ nhãn T9 v2, điền nhãn **thật** vào phần thiếu ⇒ báo giả G13 từ 2,71 về 0,87. **Độ phủ nhãn là đòn bẩy.**
- Nhãn mềm (`agent1/models/t9_soft_labels.py`): với giao dịch đã biết khách (độ tin cậy ≥ ngưỡng) mà còn tiền dư sau các liên kết T9, phân bổ phần dư cho hoá đơn **chưa có nhãn** của khách đó
  theo thứ tự hạn sớm nhất, bỏ qua hoá đơn đã đóng trong sổ cái (as-of). Nhãn là ngày giao dịch.
- Đo **chỉ trên nguồn** (DN giữ lại, 2024H1, `outputs/t9/soft/source_soft_labels.csv`, 11.536 hoá đơn đã trả):

| Ngưỡng tin cậy khách | Độ phủ T9 → T9 + mềm | Số nhãn mềm | Sai ≤ 3 / 7 / 14 ngày | MAE ngày |
|---|---|---|---|---|
| 0,5 | 74,6% → 91,6% | 1.958 | 53,6% / 57,5% / 65,5% | 13,5 |
| **0,8** | 74,6% → **90,9%** | 1.885 | 55,5% / **59,4%** / 67,6% | 12,7 |
| 0,95 | 74,6% → 89,8% | 1.751 | 55,4% / 59,8% / 67,7% | 12,7 |

  Nhãn mềm **hai mặt**: trung vị sai 0–1 ngày nhưng khoảng 1/3 nhãn sai hơn 14 ngày.
- **Quy tắc chọn ngưỡng (đăng ký trước, từ bảng trên):** độ phủ lớn nhất với tỉ lệ sai ≤ 7 ngày ≥ 0,59 ⇒ **ngưỡng 0,8**.

## 2. Thiết kế
- Thế giới **`tgt5`**: cấu hình y hệt `tgt` (`data/synthetic/tgt/config.json`), seed **9505**, **30 công ty**, sinh sau khi commit tài liệu này, niêm phong. Chưa từng dùng cho bất cứ phép đo nào.
- Ba nhánh E2E (cùng quy trình `run_t6.main`, cùng chính sách G13 **đóng băng**: MC-copula-t, isotonic học trên `src`, τ = 0,30, k = 1):
  1. `T9 v2` — đối chứng (cấu hình đã chọn trên nguồn).
  2. **`T9 v2 + nhãn mềm`** (ngưỡng 0,8) — nhánh **chính**.
  3. `nhãn thật` — cận trên.
- CI: bootstrap theo công ty 200 lần.

## 3. Tiêu chí (cổng G13 không đổi)
Nhánh chính đạt nếu: sự kiện > 0, phát hiện ≥ 4 tuần ≥ 0,70, độ sớm trung vị ≥ 4 tuần, báo giả ≤ 1,0/công ty-năm (điểm ước lượng). Dòng cổng `G13_tgt5`.

## 4. Kỳ vọng và cách đọc (viết trước)
- Nếu độ phủ là đòn bẩy và sai số nhãn mềm chấp nhận được: báo giả nhánh chính < `T9 v2` rõ rệt (tiến về `nhãn thật`).
- Nếu báo giả **không** giảm hoặc tăng dù độ phủ 90%: phần nhãn mềm sai quá 14 ngày (~1/3) làm hỏng lợi ích; kết luận độ phủ chỉ có ích khi nhãn đủ chính xác.
- Nhãn mềm chỉ dùng để huấn luyện/ngữ cảnh T1; **không** tính vào precision/recall của G15.
- Giới hạn: một bộ đích (30 công ty); `tgt5` không có bản XML (hoá đơn quan sát lấy từ bảng gốc, như `tgt3`).

## 5. Kết quả
_Điền sau khi chạy._
