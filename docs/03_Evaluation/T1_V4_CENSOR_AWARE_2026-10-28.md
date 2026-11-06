# T1 v4: đánh giá lại với nhãn kiểm duyệt (28/10/2026)

## Giao thức và dữ liệu

Đánh giá **model v4 đã khóa**, chỉ trên hai World validation và hai World test
trong [cohort v4](../../data/synthetic/v4_shortpay_4shock_20261028_cohort.json).
Không fit, hiệu chỉnh hoặc chọn lại model bằng test. Mã đánh giá
[`evaluate_t1_censor_aware.py`](../../analysis/evaluate_t1_censor_aware.py)
kiểm SHA-256 của cohort/model, manifest và Parquet từng World, cùng hash mã
train trước khi chạy. Kết quả gốc là
[`results.json`](../../outputs/data/v4_shortpay_4shock_20261028/censor_aware_evaluation_20261028/results.json)
và [bảng calibration 10 bin](../../outputs/data/v4_shortpay_4shock_20261028/censor_aware_evaluation_20261028/reliability_bins.csv).

Cắt snapshot từ 01/07/2024 theo stride 28 ngày đến trước cuối dữ liệu ít nhất
120 ngày. Mỗi hàng validation/test có **tối thiểu 128 ngày theo dõi**. Hóa đơn
chưa trả trong 28/91 ngày có nhãn 0 ở đúng mốc đó, kể cả khi ngày trả đủ sau
này chưa biết. Một hóa đơn có thể xuất hiện ở nhiều snapshot; các con số dưới
đây là **theo snapshot**, không phải các hóa đơn độc lập.

Với xác suất trả đủ ở ngày 28 và 91, báo cáo tỷ lệ thực tế, xác suất trung
bình, Brier, log loss, AUC và ECE với 10 bin cố định. Brier tham chiếu là mô
hình hằng bằng đúng tỷ lệ thực tế của World đó, chỉ để đặt thang đo, không phải
baseline được huấn luyện độc lập. Với Q10/Q50/Q90 **nhỏ hơn 120**, kiểm tỷ lệ
trả đủ thực tế trước ngày phân vị dự báo trên tất cả hàng có đủ follow-up.
Pinball từ ngày trả chính xác chỉ báo riêng cho các hàng trả đủ trong 120 ngày;
đây là tập chọn lọc, không đo pinball của toàn cohort. Q90 bằng 120 được coi
là **chạm trần**, không coi là ngày trả đủ dự báo chính xác.

## Xác suất trả đủ 4 và 13 tuần

| World | Snapshot | 4 tuần thực / dự báo | Brier 4 tuần | ECE 4 tuần | 13 tuần thực / dự báo | Brier 13 tuần | ECE 13 tuần |
|---|---:|---:|---:|---:|---:|---:|---:|
| validation 000 | 70.203 | 28,6% / 28,2% | 0,130 | 0,007 | 52,8% / 52,0% | 0,151 | 0,017 |
| validation 001 | 64.646 | 33,2% / 32,8% | 0,142 | 0,007 | 60,4% / 59,0% | 0,145 | 0,020 |
| test 000 | 39.961 | 34,6% / 35,0% | 0,134 | 0,011 | 61,1% / 61,5% | 0,125 | 0,020 |
| test 001 | 78.376 | 30,3% / 26,9% | 0,132 | 0,034 | 57,9% / 52,1% | 0,148 | 0,062 |

AUC theo World khoảng **0,857–0,880** ở 4 tuần và **0,859–0,887** ở 13 tuần.
Brier thấp hơn tham chiếu hằng của từng World (4 tuần: 0,204–0,226; 13 tuần:
0,238–0,249). Điều này cho thấy khả năng phân biệt và độ chính xác xác suất
có ích **trên synthetic**, nhưng chưa đồng đều: ở `test_001`, T1 dự báo thấp
hơn thực tế **3,4 điểm phần trăm** tại 4 tuần và **5,8 điểm phần trăm** tại
13 tuần. Bảng 10 bin cho thấy sai lệch 13 tuần chủ yếu ở các bin xác suất
trung bình đến cao, không chỉ ở một bin hiếm.

## Q10/Q50/Q90 và lỗi coverage cũ

| World | Q10 dưới trần: tỷ lệ thực tế trước Q10 | Q50 dưới trần: tỷ lệ thực tế trước Q50 | Q90 dưới trần: tỷ lệ thực tế trước Q90 | Phần snapshot có Q90 dưới trần | Coverage Q10–Q90 trên phần Q90 dưới trần |
|---|---:|---:|---:|---:|---:|
| validation 000 | 7,6% | 56,4% | 89,7% | 17,4% | 82,3% |
| validation 001 | 8,1% | 55,8% | 89,6% | 25,5% | 82,4% |
| test 000 | 7,2% | 53,9% | 88,8% | 36,4% | 81,2% |
| test 001 | 9,1% | 60,8% | 91,9% | 17,7% | 84,9% |

Mốc danh nghĩa lần lượt là **10%, 50%, 90%**. Q10 trên các hàng còn dưới
trần có xu hướng hơi sớm; Q50 có xu hướng muộn, rõ nhất ở `test_001`.
Q90 gần 90% **chỉ ở phần 17–36% snapshot có Q90 dưới trần**. Coverage 81–85%
cũng chỉ áp dụng cho phần đó; không suy rộng thành coverage 80% của toàn bộ
cohort. Các hàng Q90 chạm trần cần chân trời theo dõi và model dài hơn để
đánh giá Q90 thật.

Phép đo cũ trong [`evaluation.csv`](../../outputs/data/v4_shortpay_4shock_20261028/evaluation.csv)
kẹp cả `remaining=inf` hoặc thời gian trả sau ngày 120 thành 120. Khi Q90 cũng
bằng 120, hàng chưa trả có thể được tính là “được phủ”. Chạy lại đúng công thức
cũ tái tạo coverage **90,8% / 89,4% / 89,0% / 89,8%**. Số hàng được tính phủ
chỉ vì phép kẹp, theo thứ tự bốn World, là **29.094 / 21.695 / 13.210 /
28.836**. Nếu hiểu khoảng số `[Q10, min(Q90,120)]` theo nghĩa đen, chỉ
**49,4% / 55,9% / 55,9% / 53,0%** snapshot có sự kiện trả đủ trong khoảng
ấy trước ngày 120. Tỷ lệ này là **mức phủ của khoảng số đã bị chặn**, không
phải calibration của Q90 dài hạn. Vì vậy `cov80` cũ không được dùng để kết
luận model quá rộng hoặc đạt chuẩn.

Pinball và MAE cũ cũng dùng nhãn thời gian bị kẹp ở 120, nên chỉ phản ánh
**mục tiêu thời gian đã cắt ngắn**, không phải sai số ngày trả đủ chưa bị cắt.
Bản mới lưu pinball trên các hàng đã trả đủ trong 120 ngày để kiểm tra có điều
kiện; không dùng nó như điểm số chung cho toàn cohort.

## Kết luận và việc còn thiếu

T1 v4 có tín hiệu dự báo xác suất 4/13 tuần trên synthetic, nhưng calibration
13 tuần ở một World test còn lệch đáng kể; Q50 cũng có sai lệch theo hướng
muộn. **Chưa thể kết luận Q90 trên toàn bộ hóa đơn đạt hay không**, vì phần
lớn Q90 vượt 120 ngày. Chưa thay thuật toán hay chỉnh model theo test dựa
trên lần đánh giá này.

[Chẩn đoán 365 ngày tiếp theo](T1_V4_PAYMENT_SURVIVAL_DIAGNOSTIC_2026-10-28.md)
đo phân phối trả đủ thực tế, survival curve và điểm bắt đầu lệch của hazard
ngoại suy trên một snapshot đầu tiên cho mỗi hóa đơn.

Cần đánh giá thêm với chân trời nhãn dài hơn và định nghĩa rõ khoản không bao
giờ trả đủ/write-off. Nếu muốn khoảng Q10–Q90 dài hạn, cần metric survival
xử lý kiểm duyệt và các World có đủ thời gian theo dõi; không kẹp `inf` thành
ngày trả. Bốn World và snapshot lặp chưa cho khoảng tin cậy độc lập, và toàn
bộ nhãn ở đây là synthetic, chưa xác nhận trên ledger SME Việt Nam.

Chạy lại trong môi trường dự án:

```powershell
python analysis/evaluate_t1_censor_aware.py
```
