# Bài toán, người dùng và giả thuyết giá trị

## Bài toán

Chủ doanh nghiệp và kế toán của doanh nghiệp bán chịu cần biết tuần nào tiền có thể xuống dưới mức an toàn, khoản thu/chi nào tạo ra rủi ro và điều gì xảy ra khi khách trả chậm. Dữ liệu hóa đơn, thanh toán và sao kê có thể thiếu, ghi nhận muộn hoặc chưa khớp nhau; ngày đến hạn chưa phải ngày tiền thực về.

Workspace lập dự báo theo tuần trong **1–52 tuần, mặc định 13 tuần**. Phần giải thích xác suất tất toán T1 dùng mốc **4 tuần**, độc lập với kỳ kế hoạch dòng tiền. Chân trời có thể chọn trên giao diện chưa đồng nghĩa mọi chân trời đã đạt chất lượng dự báo.

## Người dùng và nỗi đau

| Vai trò | Nhu cầu |
|---|---|
| Chủ doanh nghiệp | Kiểm tra đệm tiền, tuần cần chuẩn bị vốn và kịch bản khách lớn chậm |
| Kế toán/kế toán trưởng | Nạp sổ, kiểm lỗi, đối soát sao kê, theo dõi công nợ và nghĩa vụ còn phải trả |
| Người phụ trách thu hồi | Biết khoản nào được ưu tiên, vì sao và lịch sử liên hệ/lời hứa |
| Người kiểm tra nội bộ | Truy lại dữ liệu, quyết định đối soát và phiên bản tạo dự báo |

Ngân hàng hoặc đối tác phần mềm kế toán là đối tượng thương mại tiềm năng; luồng thẩm định tín dụng hay chia sẻ dự báo cho ngân hàng chưa phải chức năng mặc định của Workspace.

## Câu hỏi nghiệp vụ

| Mã | Câu hỏi | Đầu ra và giới hạn |
|---|---|---|
| N1 | Tuần nào có thể thiếu tiền? | Kỳ vọng, P10/P50/P90 và xác suất dưới ngưỡng; xem cả phạm vi chi và trạng thái hiệu chỉnh |
| N2 | Nên xem khoản thu nào trước? | Hàng đợi theo chính sách dư nợ/nguy cơ/tích hai yếu tố, có giải thích; chưa đo tác động liên hệ |
| N3 | Còn bao nhiêu công nợ có rủi ro? | Công nợ theo ngày chốt và thông tin rủi ro có hỗ trợ; chưa cam kết xác suất không bao giờ trả hoặc dự phòng pháp lý |
| N4 | Nếu khách chậm hoặc dời chi thì sao? | Chạy lại T6 từ kế hoạch đã lưu, so kỳ vọng, phân vị và xác suất thiếu tiền |
| N5 | Vì sao có kết quả này? | SHAP T1, bằng chứng tất toán/partial và phân rã kế toán theo đúng snapshot |
| N6 | Có khớp sổ và sao kê không? | Kiểm dữ liệu, lịch sử nạp, đề xuất đối soát có người duyệt và khả năng đảo quyết định |
| N7 | Dữ liệu/mô hình còn phù hợp không? | Kiểm định theo ngày chốt, phiên bản và lịch cập nhật; T7 nghiên cứu chưa tương đương cảnh báo Zalo đang chạy |

## Bằng chứng và giới hạn

Khảo sát Atradius Việt Nam 2025 là nguồn tham chiếu ban đầu về bán chịu, kỳ hạn, quá hạn và nợ xấu. Phạm vi khảo sát ba ngành và các tỷ lệ tổng hợp không xác nhận hành vi của từng hóa đơn hoặc toàn bộ SME Việt Nam. Nguồn, mục đích dùng và giới hạn nằm ở [tài liệu tham khảo dữ liệu](../02_Data/08_tai_lieu_tham_khao.md).

Các bộ AR/P2P, khoản vay và dòng tiền nước ngoài chỉ kiểm tra từng phần phương pháp. Kết quả trên World synthetic chỉ phản ánh các giả định đã sinh. Số giờ tiết kiệm, DSO giảm, tỷ lệ đối soát hay hiệu quả thu hồi trên doanh nghiệp thật phải có phép đo riêng; không lấy số của pipeline tháng 10 làm kết quả Workspace hiện tại. Xem [cổng nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md).

## Giả thuyết cần kiểm chứng

| Giả thuyết | Phép đo cần có |
|---|---|
| Dự báo hành vi hữu ích hơn lịch đến hạn/trung vị khách | Backtest theo thời gian, cùng dữ liệu và phạm vi thu chi |
| Cảnh báo giúp chuẩn bị vốn sớm | Lead time, báo giả và hành động thực tế trên doanh nghiệp |
| Danh sách ưu tiên tiết kiệm công sức | Thời gian xử lý và kết quả thu hồi với thiết kế đối chứng |
| Giải thích tăng mức sử dụng | UAT khả năng hiểu, mức quay lại và lỗi diễn giải |
| Nạp/đối soát giảm thao tác thủ công | Thời gian nạp, lỗi, số quyết định phải sửa và tỷ lệ ghép chính xác |

Các mức giảm sai số 30%, giảm DSO 3 ngày hoặc khớp tự động 90% từng nêu là mục tiêu giả định, chưa phải cam kết hiện hành. Tiêu chí sử dụng cụ thể nằm trong [yêu cầu và phạm vi](06_yeu_cau_va_pham_vi.md).
