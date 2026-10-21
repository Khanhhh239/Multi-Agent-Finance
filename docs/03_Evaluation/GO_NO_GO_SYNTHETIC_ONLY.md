# Go / No-go khi CHỈ có dữ liệu tổng hợp (agent1-Khanh, 21/10/2026)

> Bối cảnh: chưa có dữ liệu doanh nghiệp Việt Nam thật. Tài liệu này chốt **luồng kỹ thuật** và **luật an toàn khi chạy**,
> không chốt "mô hình chính xác X% với doanh nghiệp thật". Số trên dữ liệu tổng hợp chỉ chứng minh luồng chạy đúng và học được
> giả định chúng ta đặt vào; không chứng minh giả định đúng.

## 1. Đã chứng minh được / chưa chứng minh được

| Khẳng định | Mức bằng chứng | Nguồn |
|---|---|---|
| Luồng chạy end-to-end, tái lập, không rò rỉ nhãn | **Chứng minh** (kiểm thử + giao thức chọn trên nguồn) | pytest, `outputs/e2e/` |
| Mô hình không thua mốc B1d trên dữ liệu AR thật (không phải VN) | **Chứng minh có giới hạn**: Customer Invoices +14,4% [11,7; 17,4]; BPI +6,5% [2,1; 11,0]; mô hình thuần DH-GBM thua B1d 62,5% trên BPI | `outputs/t1/real_v2/` |
| Khoảng dự báo đúng độ phủ | **Chưa**: G3 trượt (cov80 0,867 / 0,844, khoảng hơi rộng) | `outputs/t1/G3/` |
| Cảnh báo thiếu hụt tiền dùng được | **Chờ**: G13 v2 đang chạy; tgt chỉ 16 sự kiện | `G13_ALERT_POLICY.md` |
| Dữ liệu tổng hợp giống SME VN | **Không kiểm chứng được**: bộ thật tham chiếu 6 công ty, CI AUC rộng 0,3–0,6 | `docs/02_Data/10_realism_v2.md` |
| Hoạt động tốt với doanh nghiệp VN thật | **Không chứng minh** | — |

## 2. Quy tắc "luôn an toàn" (thiết kế để đúng ngay cả khi giả định tổng hợp sai)

1. **Neo mốc đơn giản.** Dự báo ngày thanh toán = BLEND(DH-GBM, B1d) với w chọn trên cửa sổ hiệu chỉnh của CHÍNH doanh nghiệp đó.
   Nếu w tối ưu = 0 thì dùng thẳng B1d. (Lý do: mô hình thuần thua B1d 62,5% trên BPI; BLEND chỉ nhờ neo mà không thua.)
2. **Cổng thoái lui theo doanh nghiệp.** Mỗi tuần so pinball của BLEND với B1d trên các hoá đơn đã đáo hạn trong 8 tuần gần nhất.
   Nếu BLEND thua B1d > 5% trong 4 tuần liên tiếp ⇒ tự động chuyển sang B1d cho doanh nghiệp đó và ghi cảnh báo.
3. **Khoảng dự báo hiệu chỉnh tại chỗ.** Không dùng qhat của nguồn; CQR hiệu chỉnh trên ≥ 3 tháng đã đáo hạn của doanh nghiệp.
   Chỉ công bố khoảng khi độ phủ hiệu chỉnh nằm trong 75–85%; nếu không, hiển thị "chưa đủ dữ liệu" thay vì một khoảng sai.
4. **Doanh nghiệp mới (lịch sử < 6 tháng):** chỉ B1d + khoảng rộng đã hiệu chỉnh trên nguồn; không BLEND.
5. **Mọi cảnh báo tiền thiếu hụt có người duyệt** cho đến khi có tối thiểu 2 mùa dữ liệu thật.

## 3. Các bậc triển khai (mỗi bậc có điều kiện lên bậc, đo bằng dữ liệu của chính doanh nghiệp)

| Bậc | Việc | Điều kiện lên bậc kế |
|---|---|---|
| 0. Bóng | Chạy song song, chỉ ghi dự báo, không ai hành động | ≥ 8 tuần; BLEND không thua B1d (CI trên của cải thiện ≥ 0); độ phủ hiệu chỉnh 75–85% |
| 1. Gợi ý | Hiển thị dự báo và khoảng cho kế toán, ghi nhận có/không làm theo | ≥ 1 quý; sai số tuyệt đối thanh toán tuần 1–4 giảm so với B1d trên dữ liệu thật |
| 2. Cảnh báo có duyệt | Cảnh báo thiếu hụt 13 tuần, người duyệt | Phát hiện ≥ 4 tuần trước ≥ 70% sự kiện thật, báo giả ≤ 1/năm; cần ≥ 5 sự kiện thật |
| 3. Tự động | Chưa cân nhắc | Cần pilot thật ≥ 2 mùa |

## 4. Kiểm tra độ bền trên dữ liệu tổng hợp (làm hết mức có thể)

Vì không có dữ liệu thật, độ tin cậy duy nhất có thể tăng là **thử trên nhiều thế giới khác giả định của chính chúng ta**:
- `tgt` (14 công ty, đã nhìn nhiều lần) — chỉ để so sánh lịch sử.
- **`tgt2` (40 công ty, niêm phong 21/10/2026)** — đánh giá luồng ĐÃ ĐÓNG BĂNG đúng một lần. Cấm sửa mô hình/ngưỡng sau khi xem.
  Giao thức: cùng `run_t6`/E2E, ngưỡng G13 và hiệu chỉnh isotonic học từ src (không học từ tgt hay tgt2), BLEND w từ cửa sổ hiệu chỉnh.
- `hc_*` (12 hard-case), `dr_*` (20 thế giới ngẫu nhiên hoá), `sens_uk`, `sens_coface` — kiểm tra có luồng nào sụp đổ khi giả định đổi.

**Tiêu chí đăng ký trước cho `tgt2`** (không đổi sau khi xem):
1. BLEND không thua B1d: CI trên của cải thiện pinball ≥ 0.
2. Độ phủ cov80 ∈ [75; 85]% sau hiệu chỉnh theo cửa sổ nguồn; ngoài khoảng ⇒ ghi là trượt, không điều chỉnh.
3. G13: phát hiện ≥ 0,70, độ sớm trung vị ≥ 4 tuần, báo giả ≤ 1,0/công ty-năm với chính sách đã đóng băng.
4. Báo cáo mọi cổng, kể cả cổng trượt.

## 4b. Kết quả trên `tgt2` (chạy đúng một lần, 21/10/2026 23:10)

| Tiêu chí đăng ký trước | Kết quả | Trạng thái |
|---|---|---|
| 1. BLEND không thua B1d | **Chưa đo trên tgt2** (luồng T6 không có BLEND; BLEND chỉ đo trên AR thật CI/BPI — đạt) | chưa đánh giá |
| 2. cov80 ∈ [75; 85]% với hiệu chỉnh cửa sổ nguồn | copula-t: 0,622 (tuần 1–4), 0,721 (tuần 5–13) | **trượt** (khoảng hẹp) |
| 2'. (báo cáo thêm, không đăng ký trước) copula-t + ACI | **0,767 [0,74; 0,80]**, **0,771 [0,74; 0,81]**; trên tgt E2E 0,754 / 0,767 | trong khoảng ở cả hai bộ đích |
| 3. G13 với chính sách đóng băng | phát hiện 0,746 [0,59; 0,84], độ sớm 7 tuần, báo giả 0,75 [0,43; 1,10] | **đạt điểm ước lượng**, CI chạm ngưỡng |

**Hệ quả cho luồng triển khai:** dải tiền mặt công bố phải là **copula-t + ACI** (hiệu chỉnh trực tuyến bằng kết quả đã lộ diện), không phải
copula-t gốc. ACI cần vài tuần lộ diện trước khi tin được độ phủ ⇒ khớp với bậc 0 "bóng" ≥ 8 tuần.
Lưu ý trung thực: 2' không phải tiêu chí đăng ký trước; nó được báo cáo vì nhất quán trên hai bộ đích độc lập (tgt, tgt2).

## 5. Quyết định

- **GO** cho: bậc 0 (bóng) với doanh nghiệp đầu tiên có dữ liệu, kèm quy tắc an toàn ở mục 2.
- **NO-GO** cho: mọi bậc hành động (1–3) cho tới khi có kết quả bậc 0 trên dữ liệu thật.
- **Không được** dùng số trên dữ liệu tổng hợp làm cam kết hiệu năng với khách hàng. Cam kết duy nhất hợp lệ:
  "không tệ hơn mốc đơn giản (B1d) và tự thoái lui nếu tệ hơn".

## 6. Việc còn lại để tăng độ tin cậy mà không cần dữ liệu thật (theo thứ tự)
1. ~~Sinh `tgt2` và chạy luồng đóng băng một lần~~ — xong (mục 4b).
2. ~~Cài đặt cổng thoái lui~~ — xong (`agent1/eval/fallback_gate.py`); còn: chạy thử trên `hc_supply_shock`, `hc_retention`.
3. Tìm thêm bộ AR thật công khai nhiều công ty để thu hẹp CI của kiểm định giống/khác.
