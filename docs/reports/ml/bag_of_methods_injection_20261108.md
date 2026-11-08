# Túi phương pháp chọn theo tiêm gian lận — 08/11/2026

Tầng **ML theo doanh nghiệp** (vẫn ở chế độ shadow) có thêm một lựa chọn: *Túi phương pháp (chọn theo tiêm gian lận)*. Luật cứng, luật xác suất (ngưỡng động P99, Benford) và đồ thị quan hệ **giữ nguyên**; không có hồ sơ nào được mở hay đóng bởi phần này.

## 1. Vấn đề

Một công ty nhỏ có nhiều giao dịch nhưng gần như **không có nhãn gian lận đã xác nhận** (thường 0 đến vài vụ). Muốn chọn mô hình tốt nhất cho công ty thì phải có thước đo, mà thước đo cần chính các vụ gian lận đã biết. Huấn luyện trên dữ liệu tổng hợp hoàn toàn thì khách không tin và hiệu quả giảm khi gặp dữ liệu mới. Dòng "chưa phát hiện" cũng không có nghĩa là sạch.

## 2. Ý tưởng

Không cần nhãn để học **"bình thường của công ty này"**. Nên:

1. Huấn luyện nhiều bộ phát hiện **không cần nhãn** trên 70% đầu của kỳ train của chính công ty.
2. Lấy các dòng thật của 30% sau, **bẻ đặc trưng theo cách một kiểu gian lận sẽ làm** (10 họ, mỗi họ 3 mức che giấu: lộ liễu, vừa, tinh vi), tạo bản sao tiêm.
3. Đo mỗi phương pháp hay tổ hợp có kéo các bản sao tiêm **lên cao hơn các dòng thật của chính công ty** ở một tỷ lệ cảnh báo cố định (5%) hay không.
4. Giữ ứng viên tốt nhất; so với đường cơ sở (trung bình hạng của mọi phương pháp), chỉ thay khi hơn từ 0,02.
5. Báo ước lượng trung thực cho **họ gian lận chưa từng thấy**: chọn trên các họ còn lại rồi đo trên họ bị giữ lại (giữ-lại-một-họ lồng nhau).

## 3. Các thành phần

| Phương pháp | Học gì từ sổ công ty |
|---|---|
| ECOD, Isolation Forest, LOF, Autoencoder | phân bố đặc trưng của công ty (đã có sẵn) |
| z bền vững (median/MAD) | mức bình thường của từng đặc trưng; tổng 5 độ lệch lớn nhất |
| Vượt ngưỡng phân vị 1 và 99 | giống luật ngưỡng động P99 nhưng làm điểm liên tục theo mức vượt |
| Mahalanobis co rút | độ bất thường **kết hợp** của nhiều đặc trưng |
| Đoán trường bị che (tự giám sát) | đoán 12 cột biến động nhất từ các cột còn lại; độ ngạc nhiên là sai số chuẩn hóa |

Ghép: trung bình hoặc tối đa của điểm trên **thang xác suất đuôi** (mỗi phương pháp được quy về −log của xác suất đuôi trên các dòng thật của kỳ validation, nên so sánh được). Ứng viên gồm từng phương pháp, trung bình mọi phương pháp (đường cơ sở), tối đa mọi phương pháp, trung bình và tối đa của ba phương pháp tốt nhất.

Mười họ tiêm: số tiền vọt lên, chia nhỏ sát hạn mức, thanh toán trùng, tự lập tự duyệt, lập ngoài giờ hoặc cuối tuần, nhà cung cấp liên quan nhân viên, nhà cung cấp mới khoản lớn, thiếu chứng từ, lương không chấm công, tạm ứng quá hạn. Họ nào thiếu cột đặc trưng hoặc thiếu dòng phù hợp thì bị bỏ qua và ghi vào chẩn đoán.

Thước đo chọn: nửa là trung bình recall các họ, nửa là trung bình của hai họ yếu nhất, để một kiểu dễ không che điểm mù.

## 4. Kiểm chứng (dữ liệu tổng hợp, nhãn thật chỉ dùng để đo)

Sáu công ty trong hai thế giới sinh bằng bộ sinh của chính kho này (seed khác nhau, mỗi công ty khoảng 6.000 dòng train, 4.000 dòng kiểm tra, 16 đến 29 dòng gian lận thật trong phần kiểm tra). Huấn luyện trên 60% đầu theo thời gian, mọi dòng gian lận trong phần train coi như bình thường. Recall khi mỗi tuần mỗi công ty chỉ được 3 cảnh báo:

| Phương pháp | Recall trung bình sáu công ty | Số công ty mà túi thắng |
|---|---:|---:|
| Isolation Forest | 11,4% | 6 trên 6 |
| ECOD | 28,6% | 6 trên 6 |
| LOF | 48,7% | 6 trên 6 |
| Autoencoder (đối thủ mạnh nhất) | 57,4% | 6 trên 6 |
| **Túi phương pháp** | **71,1%** | |

Precision ở 3 cảnh báo mỗi tuần khoảng 12%. Kịch bản lặp lại: `scripts/validate_bag_injection.py`.

## 5. Giới hạn, cần đọc trước khi dùng con số

- **Số trên đây lạc quan.** Bộ sinh và mười họ tiêm cùng mô tả những kiểu gian lận tương tự (thanh toán trùng, nhà cung cấp ma, chia nhỏ...), nên túi được chọn đúng loại mà bài thi chứa. Trên dữ liệu thật con số có thể thấp hơn nhiều; đó là điều thí điểm phải đo.
- Mỗi công ty chỉ có 16 đến 29 dòng gian lận thật để đo, nên mỗi dòng đổi khoảng 4 điểm phần trăm; chưa có khoảng tin cậy.
- Mẫu tiêm là kiểu **đã biết**, viết trong không gian đặc trưng; không cho biết mô hình bắt được kiểu chưa có trong thư viện. Ước lượng giữ-lại-một-họ giúp nhưng không thay được.
- Sổ thật có thể đã chứa gian lận chưa phát hiện và được coi là bình thường.
- Tiêm ở mức đặc trưng yếu hơn tiêm ở mức sổ cái; bước nâng cấp là tiêm vào sổ cái rồi tính lại đặc trưng.
- Công ty dưới 60 dòng train bị từ chối; dưới 300 dòng độ tin cậy ghi "thấp", dưới 1.500 ghi "trung bình".
- Họ yếu được hiển thị trên trang. Ví dụ trên workspace demo lớn, họ "lập ngoài giờ" chỉ 3%, "tự duyệt" 13%, "số tiền vọt lên" 17%.
- Điểm là **mức bất thường theo xác suất đuôi**, không phải xác suất gian lận.

## 6. Cách dùng

1. Trang `/company-ml`: cập nhật dữ liệu, chọn *Túi phương pháp (chọn theo tiêm gian lận)*, chọn kỳ train và calibration, huấn luyện. Bản ghi phiên bản có mục `diagnostics` (ứng viên được chọn, recall theo họ và theo mức, ước lượng họ chưa thấy, họ bị bỏ qua, giới hạn); trang hiện tóm tắt và ba họ yếu nhất.
2. Các bước xác nhận phiên bản, chạy chấm và lịch sử cấu hình dùng nguyên khung hiện có.
3. Demo lớn có đặc trưng thật: `python -B scripts/make_company_ml_big_demo.py --root .runtime/demo_big` (bộ demo sẵn có dùng đặc trưng ngẫu nhiên, nên không có ý nghĩa với thuật toán này).

## 7. Mã và kiểm thử

| Tệp | Nội dung |
|---|---|
| `sme_fraud/bag_of_methods.py` | các phương pháp, bộ tiêm, thang xác suất đuôi, chọn và chẩn đoán |
| `sme_fraud/ml_estimators.py` | thêm thuật toán `bag_injection`; `fit(x, y, columns)` |
| `sme_fraud/company_ml.py`, `company_ml_comparison.py` | truyền tên cột chỉ cho thuật toán mới; lưu `diagnostics` |
| `review_ui/company_ml.js` | ghi chú tóm tắt trong bảng phiên bản |
| `tests/test_bag_of_methods.py` (7 bài) | chọn xác định, từ chối dữ liệu quá ít, bỏ qua họ thiếu cột, bản sao tiêm bất thường hơn dòng thật, thang đuôi |
| `tests/test_company_ml.py` | bài nối dây: nhận tên cột và lưu chẩn đoán |

Trong nhóm kiểm thử ML và nhập dữ liệu còn đúng 7 bài lỗi, trùng với 7 bài đã lỗi ở bản gốc do chưa cài CatBoost; 27 kiểm thử giao diện của trang đều qua.
