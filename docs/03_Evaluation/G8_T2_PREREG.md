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
_Điền sau khi chạy._
