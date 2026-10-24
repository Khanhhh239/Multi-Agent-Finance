# G13 với hàng chờ duyệt thông minh (mũi B1): đăng ký trước (24/10/2026, agent1-Khanh)

> Commit **trước khi** sinh `tgt6` và chạy các nhánh E2E. Mục 1–4 không đổi sau khi xem kết quả.

## 1. Căn cứ (chỉ nguồn)
- Nhãn mềm giúp nhưng chưa vững: G13 đạt `tgt5` (0,77) nhưng trượt `tgt3` (1,81) (`G13_SOFT_LABELS_PREREG.md` mục 6).
- Trong vận hành thật, độ phủ nhãn đến từ **máy + kế toán duyệt hàng chờ**. Mô phỏng `agent1/models/t9_review_queue.py`: hàng chờ = tiền vào T9 chưa phân bổ hết;
  mỗi tuần mỗi doanh nghiệp duyệt tối đa b giao dịch; người duyệt **hoàn hảo** (lấy liên kết đúng từ bảng thanh toán) ⇒ kết quả là **cận trên** cho người thật.
- Đo trên DN nguồn giữ lại 2024H1 (`outputs/t9/review/source_review.csv`), luồng T9 v2 → duyệt → nhãn mềm (ngưỡng 0,8):

| Chính sách | b | Lượt duyệt thực/DN/tuần | Hàng chờ được duyệt | Độ phủ hoá đơn đã trả | MAE nhãn (ngày) |
|---|---|---|---|---|---|
| không duyệt | 0 | 0 | 0% | 90,9% | 2,51 |
| ngẫu nhiên | 2 / 5 | 1,6 / 2,8 | 49% / 83% | 92,0% / 94,7% | 1,08 / 0,40 |
| **leftover** (tiền chưa giải thích lớn nhất trước) | **2 / 5** | 1,6 / 2,8 | 49% / 83% | **93,0% / 95,2%** | **0,65 / 0,26** |

- **Chọn chính sách `leftover`** (thắng ngẫu nhiên ở mọi mức có giới hạn; quy tắc: độ phủ cao nhất ở b = 5, hoà thì MAE thấp hơn).

## 2. Thiết kế
- **`tgt6`**: cấu hình y hệt `tgt`, seed **6606**, **30 công ty**, sinh sau khi commit tài liệu này, niêm phong.
- Nhánh trên `tgt6` (chính sách G13 **đóng băng**: MC-copula-t, isotonic học trên `src`, τ = 0,30, k = 1):
  `T9 v2 + nhãn mềm` (b = 0, đối chứng) · `+ duyệt 2/tuần` · **`+ duyệt 5/tuần` (chính)** · `nhãn thật` (cận trên).
- **Lặp lại** trên `tgt3` (không niêm phong): `+ duyệt 5/tuần` (các nhánh khác đã có).
- CI: bootstrap theo công ty 200 lần.

## 3. Tiêu chí
- Cổng `G13_tgt6` (nhánh chính b = 5): sự kiện > 0, phát hiện ≥ 4 tuần ≥ 0,70, độ sớm ≥ 4 tuần, báo giả ≤ 1,0 (điểm ước lượng).
- **"Vững"** (theo quy tắc dừng của chiến lược): đạt ở **cả** `tgt6` **và** lặp lại `tgt3`. Nếu không, dừng tối ưu G13 trên dữ liệu sinh.
- Báo cáo thêm: lượt duyệt thực tế/DN/tuần ở mỗi nhánh (chi phí vận hành).

## 4. Kỳ vọng và cách đọc (viết trước)
- Nếu duyệt 5/tuần đạt cả hai thế giới: luồng sản phẩm "máy + ~3 lượt duyệt/DN/tuần" đủ cho cảnh báo; khuyến nghị đưa vào bậc 0 chạy bóng.
- Nếu chỉ đạt `tgt6`: như nhãn mềm — cải thiện thật nhưng chưa vững.
- Nếu không đạt cả hai dù độ phủ ~95% và MAE ~0,3 ngày: phần báo giả còn lại không do nhãn mà do mô hình/thế giới (khi đó so với nhánh nhãn thật để tách).
- Giới hạn: người duyệt hoàn hảo (người thật sẽ sai, chậm); `tgt6` không có XML (như `tgt3`, `tgt5`).

## 5. Kết quả
Chạy 24/10/2026 (`outputs/g13/e2e_tgt6/alert_policy_tgt6.csv`, `outputs/g13/e2e_tgt3/alert_policy_tgt3.csv`; đăng ký trước commit `faa93e0` lúc 14:52, `tgt6` sinh sau đó).

**`tgt6` (niêm phong, 30 công ty, 31 sự kiện):**

| Nhánh | Hàng chờ được duyệt | Phát hiện | Báo giả/công ty-năm [CI] | Brier |
|---|---|---|---|---|
| T9 v2 + nhãn mềm (b = 0) | 0% | 0,839 | 1,204 [0,74; 1,74] | 0,087 |
| + duyệt 2/tuần | 51% | 0,806 | 1,070 [0,70; 1,51] | 0,086 |
| **+ duyệt 5/tuần (chính)** | **83%** | **0,806** | **0,970 [0,64; 1,31]** | 0,085 |
| Nhãn thật (cận trên) | — | 0,806 | 0,937 [0,50; 1,47] | 0,085 |

**Lặp lại `tgt3` (46 sự kiện):** duyệt 5/tuần (89% hàng chờ) ⇒ báo giả **1,371 [0,84; 2,08]**; so với chỉ nhãn mềm 1,806, T9 v2 2,709, nhãn thật 0,903.

**Kết quả theo tiêu chí đăng ký trước:** `G13_tgt6` **đạt sát ngưỡng** (0,970 ≤ 1; CI trên 1,31). Lặp lại `tgt3` **trượt** (1,371). ⇒ **Không vững** ⇒ áp **quy tắc dừng**: dừng tối ưu G13 trên dữ liệu sinh.

**Đọc kết quả:**
- Hàng chờ duyệt giúp đều đặn ở cả hai thế giới: so với chỉ nhãn mềm, báo giả giảm 19% (`tgt6`) và 24% (`tgt3`). Trên `tgt6`, duyệt 5/tuần gần như bằng nhãn thật (0,970 so với 0,937).
- **Phát hiện quan trọng mới:** ngay cả với **nhãn thật**, báo giả là 0,94 (`tgt6`), 0,90 (`tgt3`) — sát ngưỡng 1,0. Ở các thế giới này, **mô hình dự báo dòng tiền tự nó chỉ vừa đủ** cho tiêu chí G13. Phần còn lại không còn là chuyện nhãn.
  (Các thế giới khác với nhãn thật: `tgt` 0,57, `tgt2` 0,75, `tgt5` 0,33.) ⇒ Trên dữ liệu sinh, trần của G13 khoảng 0,3–0,9 tuỳ thế giới; tiêu chí ≤ 1,0 nằm ở mép trần.
- Trên `tgt3`, khoảng cách còn lại so với nhãn thật (1,37 so với 0,90) **có thể** do 11% hàng chờ chưa duyệt và nhãn mềm sai — giả thuyết, chưa tách bằng ablation.
- **Ý nghĩa sản phẩm:** với ~3 lượt duyệt/doanh nghiệp/tuần (người duyệt hoàn hảo), cảnh báo đạt mức gần nhãn thật trên một thế giới và cải thiện rõ trên thế giới kia. Đây là thiết kế đáng mang vào chạy bóng; câu trả lời cuối phải đến từ dữ liệu thật.
