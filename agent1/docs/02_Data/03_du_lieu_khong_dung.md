# 3. Dữ liệu đã khảo sát nhưng KHÔNG dùng (hoặc chưa dùng) và lý do

Phân tích sơ để người sau không phải khảo sát lại. Cột "Quyết định": **Loại** = không dùng; **Hoãn** = có giá trị
nhưng cần đăng nhập/điều khoản/công sức, xếp vào kế hoạch.

| Nguồn | Là gì | Quyết định | Lý do | Nếu dùng sau, làm gì |
|---|---|---|---|---|
| **Global B2B Payment (tharishreddy22, 4,5 triệu dòng)** | Bộ Kaggle mô tả là tổng hợp, train 2019–2023/test 2024–2025 | **Loại** | Không truy cập được để xác minh; mô tả (khối lượng phẳng, cuối tuần = ngày thường, tỷ lệ trạng thái 68/17/10/5 tròn số) là chữ ký của bộ sinh bằng trọng số cố định; dùng sẽ làm mô hình học luật của người sinh, không học hành vi | Chạy `scripts/realism_audit.py`; nếu qua kiểm tra mới dùng thử nghiệm quy mô lớn (tốc độ), không dùng hiệu chỉnh |
| **AR & Payment Delay Analysis (sonalisingh1411)** | Bộ Kaggle phân tích trễ thanh toán | **Loại** | Không có thông tin nguồn gốc/giấy phép; chưa kiểm tra được | Chạy realism_audit trước |
| **Home Credit `installments_payments`** | Lịch sử trả góp thật (ngày phải trả/ngày trả, số tiền phải trả/đã trả) | **Hoãn (ưu tiên cao)** | Cần đăng nhập Kaggle + chấp nhận luật cuộc thi; điều khoản dùng ngoài cuộc thi cần đọc. Cấu trúc gần AR nhất (trả một phần) → hữu ích cho T3 và T1 | Tải thủ công; map `DAYS_INSTALMENT→due`, `DAYS_ENTRY_PAYMENT→paid`; thêm vào `real_loaders.py` |
| **M5 (Walmart)** | Chuẩn dự báo phân vị | **Hoãn** | Kaggle login; là chuẩn để so với kết quả công bố, không phải dòng tiền | Chạy đúng quy trình T4 trên M5 để chứng minh quy trình tái lập kết quả thắng cuộc (WSPL) |
| **Freddie Mac SF Loan-Level** | 55 triệu thế chấp, chuyển trạng thái trễ→chữa lành→vỡ nợ | **Hoãn** | Cần đăng ký; thế chấp ≠ B2B; dung lượng lớn | Dùng thử mô hình chữa lành/chuyển trạng thái ở quy mô lớn |
| **Payment Times Reports (Úc)** | Thống kê DN lớn trả DN nhỏ | **Hoãn** | Phải chấp nhận Terms of Use → không tự động hoá; giá trị tương tự UK PPR | Tải tay, đối chiếu chéo họ phân phối trễ |
| **SEC Financial Statement Data Sets** | XBRL báo cáo tài chính Mỹ theo quý | **Hoãn** | Bắt buộc User-Agent có tên tổ chức + email *của chính bạn* (chính sách truy cập SEC); mục đích: ước lượng bậc tự do Student-t của sốc dòng tiền (Q2/2020) | Tải 2020q1–q3, lọc báo cáo lưu chuyển tiền tệ, ước lượng df; thay giả định df=4 |
| **UNU-WIDER Viet Nam SME Survey** | Vi dữ liệu SME VN 2005–2015 (ngành chế biến, 9 tỉnh) | **Hoãn (giá trị cao)** | Điền biểu mẫu; chưa xác nhận có biến bán chịu; kết thúc 2015 | Dùng để lấy phân bố quy mô doanh thu/chi phí/nợ của SME VN cho máy phát |
| **World Bank Enterprise Surveys VN** | Biến `fin18` tỷ trọng bán chịu, `fin8`, `k3f` | **Hoãn** | Cần đăng ký; chưa xác nhận wave VN có biến | Đối chiếu 65% bán chịu của Atradius |
| **Báo cáo tài chính niêm yết VN** (UBCKNN, vnstock) | DSO, DPO theo ngành | **Hoãn** | Điều khoản crawl chưa đọc; DN niêm yết lớn hơn SME rất nhiều | Tính DSO/DPO theo ngành để kiểm tra độc lập máy phát (không dùng để chỉnh) |
| **Olist (Brazil)** | 100k đơn hàng thương mại điện tử | **Loại** | CC BY-NC-SA 4.0 (phi thương mại, chia sẻ tương tự) — không dùng cho sản phẩm thương mại; không phải công nợ B2B | — |
| **OCEL 2.0 P2P/O2C mô phỏng** | Nhật ký hướng đối tượng mô phỏng SAP | **Loại (làm mẫu cấu trúc)** | Là mô phỏng, giấy phép chưa xác nhận (Zenodo lỗi lúc kiểm tra) | Chỉ tham khảo cấu trúc sự kiện |
| **Bondora (P2P Estonia)** | Khoản vay, lịch trả, sự kiện đòi nợ | **Hoãn** | Trang gốc "đang cải tạo"; điều khoản chưa kiểm tra; cho vay tiêu dùng | Thử mô hình chữa lành nếu cần dữ liệu thêm |
| **Companies House (Anh)** | BCTC điện tử công ty Anh | **Hoãn** | 500 MB/tháng; điều khoản tái sử dụng chưa xác nhận | Phân phối tiền/phải thu/phải trả của công ty nhỏ |
| **Finance Factoring – IBM Late Payment Histories** | Lịch sử trễ của IBM | **Loại** | Kaggle cộng đồng, chưa kiểm cột, nguồn gốc không rõ; nhiều bài báo đã dùng nhưng không tái lập được | Audit trước |
| **Payment Date Dataset (rajattomar132)** | Tương tự Customer Invoices | **Loại** | Trùng vai trò, độ tin cậy C | — |
| **Xero Small Business Insights** | Chỉ số trễ SME 5 nước | **Loại (làm tham chiếu)** | Không có file tải; **chỉ tính hoá đơn đã trả đủ và loại hoá đơn >1 năm → cận dưới** (thiên lệch người sống sót) | Dẫn để minh hoạ vì sao cần phân tích sống sót |
| **Coface Asia Payment Survey 2025** | Trễ trung bình 65 ngày; 40% có trễ >180 ngày | **Dùng làm tham số nhạy cảm**, không làm đích | Không có VN; khảo sát nhận thức | Đã dùng để đặt đuôi trễ "coface" ở `sens_coface` |

## Vì sao có bộ "ngó có vẻ hợp" mà vẫn loại

Ba dấu hiệu làm một bộ AR bị loại khỏi hiệu chỉnh/huấn luyện chính:
1. **Không xác minh được nguồn gốc** (dữ liệu có thể là sinh với quy tắc cố định).
2. **Không có thông tin kiểm duyệt đúng** (chỉ có hoá đơn đã đóng → thiên lệch người sống sót).
3. **Độ trễ không phù hợp VN** (ví dụ 99% hoá đơn trễ ≤30 ngày).

Một dữ liệu bị loại khỏi hiệu chỉnh vẫn có thể dùng để **thử quy trình** nếu ghi rõ là tầng 1 (như Customer Invoices).
