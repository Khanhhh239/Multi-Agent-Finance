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
Chạy 24/10/2026 (`outputs/g13/e2e_tgt5/alert_policy_tgt5.csv`, `g13-e2e-t9v2-tgt5-v1`; đăng ký trước commit `fbe3f62` lúc 10:35 ngày 23/10, `tgt5` sinh sau đó). 30 công ty, 123.928 hoá đơn, **20 sự kiện thiếu tiền**, chính sách đóng băng (τ = 0,30, k = 1), CI bootstrap theo công ty:

| Nhánh | Hoá đơn đã trả có nhãn | Sai số nhãn (MAE ngày) | Phát hiện ≥4 tuần [CI] | Độ sớm | Báo giả/công ty-năm [CI] | Brier 13 tuần |
|---|---|---|---|---|---|---|
| T9 v2 (đối chứng) | 60,6% | 0,81 | 0,90 [0,69; 1,00] | 11,5 | **2,007 [1,24; 2,74]** | 0,138 |
| **T9 v2 + nhãn mềm (chính)** | **94,8%** | 5,64 | **0,90 [0,69; 1,00]** | 8,0 | **0,769 [0,37; 1,17]** | **0,071** |
| Nhãn thật (cận trên) | 100% | 0 | 0,75 [0,59; 1,00] | 5,5 | 0,334 [0,07; 0,67] | 0,070 |

**Cổng `G13_tgt5` (nhánh chính): ĐẠT ở điểm ước lượng** (phát hiện 0,90 ≥ 0,70; độ sớm 8,0 ≥ 4; báo giả 0,769 ≤ 1,0). Đây là lần đầu G13 đạt trên đường ước lượng, trên bộ đích niêm phong chưa từng dùng.

**Chính xác về nhãn mềm trên `tgt5`:** 18.864 hoá đơn được thêm nhãn mềm; trong đó MAE 14,2 ngày, 63% sai ≤ 7 ngày, **27% sai > 14 ngày** (khớp với đo trên nguồn: ~1/3 lệch xa).
Dù vậy báo giả giảm 2,007 → 0,769 và Brier giảm 0,138 → 0,071 (ngang nhãn thật 0,070).

**Đọc kết quả (đối chiếu với mục 4 viết trước):**
- Kỳ vọng "báo giả nhánh chính < T9 v2 rõ rệt" **đúng**. Kịch bản xấu ghi trước ("phần lệch > 14 ngày làm hỏng lợi ích") **không xảy ra**: độ phủ lợi nhiều hơn sai số hại.
- **Giả thuyết cơ chế (chưa kiểm):** T1 có thể cần chủ yếu biết hoá đơn đã được trả (ra khỏi nhóm "còn mở") và thời điểm xấp xỉ; nhãn lệch vài tuần có thể vẫn hữu ích hơn nhãn thiếu. Chưa có ablation tách phần "biết đã trả" khỏi "biết ngày".
- **Giới hạn nên nói to:** (1) chỉ **20 sự kiện**, CI trên của báo giả 1,17 vượt ngưỡng 1,0 ⇒ đạt sát ngưỡng, chưa vững; (2) một bộ đích; (3) phát hiện/độ sớm của nhãn thật thấp hơn (0,75 / 5,5) do ít sự kiện, không nên so với nhánh khác;
  (4) nhánh nhãn mềm đo trên nhãn mềm sinh từ dữ liệu quan sát được, nhưng khoảng 1/3 nhãn mềm sai nhiều: người dùng thật có thể thấy nhãn đó vì chúng là dự đoán, cần đánh dấu "ước lượng" trong sản phẩm.
- Lặp lại trên `tgt3` (không niêm phong, để kiểm tra độ ổn định): xem mục 6 — **kết quả không đạt cổng**.

## 6. Lặp lại trên `tgt3` (24/10/2026; KHÔNG niêm phong: đã dùng cho G13 trước đó, chỉ để kiểm tra độ ổn định; cùng cấu hình, ngưỡng 0,8 đã đóng băng)

| Nhánh (46 sự kiện, 30 công ty) | Hoá đơn đã trả có nhãn | Phát hiện | Báo giả/công ty-năm [CI] | Brier 13 tuần |
|---|---|---|---|---|
| T9 v2 | 59,5% | 0,848 | 2,709 [1,97; 3,45] | 0,181 |
| **T9 v2 + nhãn mềm** | **93,8%** | 0,804 | **1,806 [1,14; 2,54]** | **0,114** |
| Nhãn thật | 100% | 0,804 | 0,903 [0,53; 1,30] | 0,115 |

**Kết quả: nhãn mềm giảm báo giả 33% (2,71 → 1,81) và đưa Brier về mức nhãn thật (0,114 so với 0,115), nhưng báo giả 1,81 VẪN > 1,0 ⇒ KHÔNG đạt G13 trên `tgt3`** (CI dưới 1,14 cũng > 1).

**Tổng hợp hai thế giới (cùng cấu hình đóng băng, không chỉnh gì giữa hai lần):**

| | T9 v2 | + nhãn mềm | Nhãn thật | Mức bù của nhãn mềm |
|---|---|---|---|---|
| `tgt5` (niêm phong, 20 sự kiện) | 2,007 | **0,769** | 0,334 | 1,24 / 1,67 điểm (74%) |
| `tgt3` (46 sự kiện) | 2,709 | **1,806** | 0,903 | 0,90 / 1,81 điểm (50%) |

**Đọc kết quả:**
- Hướng nhất quán ở cả hai thế giới: **độ phủ giúp lớn** (giảm 33–62% báo giả), và Brier ngang nhãn thật. Giả thuyết "độ phủ là đòn bẩy chính" được hai thế giới ủng hộ.
- Nhãn mềm **chưa đủ** để đạt cổng một cách đáng tin: **1/2 thế giới đạt** (`tgt5`, sát ngưỡng với CI trên 1,17; `tgt3` trượt rõ). Phần báo giả còn lại so với nhãn thật (0,9–1,3 điểm trên `tgt3`) có thể do ~1/3 nhãn mềm lệch xa (không kiểm riêng phần này).
- **Kết luận thận trọng:** nhãn mềm là cải thiện thật và đáng đưa vào luồng, nhưng **không** được coi là đã giải G13. G13 vẫn ở trạng thái "chưa đạt một cách vững".
- Hướng nâng tiếp (chưa làm): lọc nhãn mềm theo mức tin cậy riêng (ví dụ chỉ giữ nhãn mềm của khách có lịch sử trả đều), hoặc đánh dấu nhãn mềm là "ước lượng" và để T1 giảm trọng số chúng; cần đăng ký trước và một bộ đích mới.
