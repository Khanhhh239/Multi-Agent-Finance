# G8 — T2 (SBA 7(a), dữ liệu thật): hiệu chỉnh lại hằng năm bằng nhóm khoản vay đã chín nhãn (đăng ký trước, 22/10/2026, agent1-Khanh)

> Commit **trước khi** chạy `scripts/sprint5/t2_rolling_recal.py`. Mục 1–4 không đổi sau khi xem kết quả.

## 1. Căn cứ
Cổng G8 (loại EXEMPT, kỳ hạn ≤ 120 tháng): PR-AUC ≥ 2×tỉ lệ gốc, ECE ≤ 0,02, tỉ lệ (tiền vỡ nợ dự báo / thực tế) ∈ [0,8; 1,25].
Hiện tại (`LightGBM + isotonic (FY2014)`): PR-AUC gấp 5,8 lần ✓, ECE 0,022 ✗, tỉ lệ **0,63** ✗.
Mô hình học FY2010–2013, hiệu chỉnh một lần trên FY2014 (vỡ nợ 1,5%), kiểm FY2018–2022 (vỡ nợ 1,3–2,3%, riêng FY2022 6,2%):
**trôi tỉ lệ gốc theo thời gian**, không phải thiếu năng lực xếp hạng. Một mô hình triển khai thật sẽ hiệu chỉnh lại khi có nhãn mới.

## 2. Phương pháp (suy ra từ thời điểm nhãn chín, không chỉnh theo bộ kiểm)
Nhãn là "bị xoá nợ trong 3 năm". Khoản vay duyệt năm f−4 có nhãn đầy đủ vào cuối năm f−1 ⇒ **đã biết trước năm f**.
Với mỗi năm kiểm f ∈ {2018…2022}: hiệu chỉnh trên nhóm **FY f−4** (2014…2018), áp lên FY f.
Mô hình LightGBM **không đổi** (huấn luyện FY ≤ 2013, dừng sớm trên FY2014).

| Biến thể | Hiệu chỉnh |
|---|---|
| **A (chính, dùng cho cổng)** | isotonic trên nhóm f−4 (cùng loại hiệu chỉnh của dòng cổng hiện tại) |
| B (báo cáo) | dịch hệ số chặn logit sao cho trung bình dự báo = tỉ lệ vỡ nợ thực của nhóm f−4 |
| C (đối chứng) | cấu hình hiện tại: isotonic FY2014 một lần |

## 3. Đánh giá
Gộp FY2018–2022, kỳ hạn ≤ 120 tháng, loại EXEMPT (đúng định nghĩa cổng). Báo cáo thêm: (i) bỏ FY2022, (ii) từng năm.
**Cảnh báo dữ liệu biết trước:** FY2022 có tỉ lệ vỡ nợ 6,2% (FY2021: 1,6%) — nghi nhãn chưa chín (chỉ khoản đã vỡ được quan sát). Không loại khỏi kết quả chính.

## 4. Tiêu chí
Biến thể A đạt cả ba điều kiện G8 trên tập gộp. Bộ kiểm FY2018–2022 **đã được nhìn ở lần chạy G8 trước** (không còn bộ kiểm sạch trên dữ liệu thật này);
quy tắc f−4 xuất phát từ logic nhãn chín, đã chốt trước khi chạy, nhưng đây không phải bộ niêm phong như `tgt2`/`tgt3`.

## 5. Kết quả
Chạy 22/10/2026 (`outputs/sprint5/t2_rolling_recal.csv`, `sba-rolling-recal-f-minus-4-v1`). Kỳ hạn ≤ 120 tháng, loại EXEMPT.

| Phạm vi | Biến thể | ECE | Tỉ lệ tiền vỡ nợ dự báo/thực tế | Đạt G8 |
|---|---|---|---|---|
| **Gộp FY2018–2022 (cổng)** | **A isotonic f−4 (chính)** | **0,021** | **0,741** | **KHÔNG** |
| | B dịch hệ số chặn | 0,019 | 0,734 | không |
| | C hiện tại (isotonic FY2014) | 0,022 | 0,630 | không |
| Gộp FY2018–2021 | A / B / C | 0,018 / 0,016 / 0,019 | 0,973 / 0,987 / 0,853 | cả ba đạt |
| FY2022 riêng | A / B / C | 0,056 / 0,059 / 0,061 | 0,247 / 0,194 / 0,152 | không |

**Kết luận: G8 theo định nghĩa hiện tại VẪN TRƯỢT.** Hiệu chỉnh lại hằng năm cải thiện tỉ lệ 0,63 → 0,74 và ECE 0,022 → 0,021 nhưng không đủ.

**Đính chính mục 3:** tôi viết "nghi nhãn FY2022 chưa chín". **Sai.** Dữ liệu trích xuất tới 07/2026 (xoá nợ muộn nhất 2026-07-01), nên cửa sổ 3 năm của FY2022 đã khép.
Tỉ lệ vỡ nợ FY2022 = 6,2% (7,7% ở kỳ hạn ≤ 120 tháng) là **thật**, gấp 4–5 lần FY2018–2021 (1,3–2,3%): một thay đổi chế độ.
Không mô hình nào học từ FY ≤ 2013 (hay hiệu chỉnh bằng nhóm chín f−4) thấy trước được. Hiệu chỉnh lại chậm 4 năm nghĩa là luôn chậm một chế độ.

**Điều thực sự đúng:** FY2018–2021 (chế độ ổn định) đạt ở cả ba biến thể, kể cả cấu hình cũ ⇒ **lần này không có bằng chứng quy tắc f−4 tốt hơn** khi chế độ ổn định; nó chỉ giảm bớt thiếu sót khi chế độ đổi.
Không chuyển cổng thành "đạt" bằng cách bỏ FY2022: đó là loại bỏ dữ liệu bất lợi sau khi xem kết quả. Quyết định có nên đổi định nghĩa cổng (ví dụ yêu cầu mô hình cảnh báo khi trôi tỉ lệ gốc thay vì đòi tỉ lệ 0,8–1,25) thuộc chủ dự án.
**Hướng đúng cho T2:** phát hiện trôi tỉ lệ gốc theo nhóm (giống G14) và hiển thị "mô hình đang dự báo thấp" thay vì cam kết hiệu chỉnh.
