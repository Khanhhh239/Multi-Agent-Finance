# Nguồn công khai: dùng và không dùng

Chi tiết kiểm chứng từng nguồn nằm ở [Phần 6](../07_tai_lieu_tham_khao/DIGITAL_ACCOUNTING_PART6_AGENT2_DATA_SOURCES.md) (đã đọc nguồn gốc phần lớn). Bảng dưới là kết luận.

## 1. Đã dùng

| Nguồn | Mô tả | Dùng cho | Hạn chế |
|---|---|---|---|
| **ACFE 2024** [Đ] | 1.921 vụ, 138 quốc gia; tỷ lệ loại gian lận theo quy mô, cấp người thực hiện, thông đồng, che giấu, thời gian kéo dài, tổn thất | Hiệu chỉnh bộ sinh (tệp 07) | Là vụ đã phát hiện; không cho tần suất theo giao dịch |
| **Vụ án và bài báo Việt Nam** [Đ/T] | Sebang, Bảo Định, kế toán trưởng TP.HCM, DTC, Khải Đệ, trường học, VINACO... | Đặt tên và mô tả kịch bản | Không suy ra tần suất |
| **Atradius 2025, thanh toán B2B Việt Nam** [T] | 65% doanh số bán chịu, kỳ hạn 45 ngày, 58% trả đúng hạn, 39% trả trễ, 3% nợ xấu | Hành vi trả tiền của khách trong quy trình nền | Số liệu khảo sát; xem DATA_V4.md |
| **Sổ cái tổng hợp DFKI** (Gronewald và cộng sự, Data in Brief) [Đ cho trang Zenodo] | `journal_entries_4203.csv` 31,1 MB, CC BY 4.0, [Zenodo 10.5281/zenodo.22014653](https://zenodo.org/records/22014653) | Kiểm tra độc lập các mô hình không nhãn trên bút toán | Bất thường chèn nằm đúng trong danh sách của chính các luật JET: vòng tròn |
| **ERP Fraud Data** (Tritscher và cộng sự 2022, Würzburg) [Đ] | 12 kịch bản gian lận trên SAP mô phỏng (ERPsim); 190 MB; đã trích các tệp CSV chính vào `external/` | Đối chiếu ngoài gần lĩnh vực nhất (mua hàng, bán hàng) | Công ty sản xuất mô phỏng; 5 người chơi, không có nhà cung cấp ma, nhân sự ma, chi phí khống; giấy phép chưa xác nhận |

Kết quả trên hai bộ ngoài (không giám sát, AP): ERP Fraud Data, ba phép thử trong `results/v3/external_erp.json`: ECOD 0,495 / 0,059 / 0,147, Isolation Forest 0,459 / 0,050 / 0,117, autoencoder 0,144 / 0,147 / 0,212 — **không phương pháp nào thắng ổn định**; DFKI: JET một mình AP 0,083, ECOD 0,097, autoencoder 0,122 [M]. Chi tiết: `results/v3/external_*.json`.

## 2. Chưa dùng nhưng nên dùng (việc còn lại)

| Nguồn | Mục đích | Giấy phép, lưu ý |
|---|---|---|
| BPI Challenge 2019 (mua hàng và thanh toán; 728,6 MB; 76.349 chứng từ) | Nền thật để đếm cảnh báo trên 1.000 giao dịch của các luật mua hàng | CC BY 4.0 |
| BPI Challenge 2020 (chi phí công tác, đại học Hà Lan) | Nền thật cho luật chi phí nhân viên | **CC BY-NC 4.0: chỉ phi thương mại** |
| Chi trả nhà cung cấp của thành phố Chicago, Checkbook NYC | Nền thật lớn về số tiền tròn, tập trung nhà cung cấp, thanh toán trùng | Máy chủ từ chối truy cập tự động lúc kiểm tra; chưa xem được cột và giấy phép |

Vì không có nhãn, kết quả từ các nền này **chỉ là khối lượng cảnh báo**, không phải độ chính xác.

## 3. Cố ý không dùng

| Nguồn | Lý do (đã kiểm chứng ở Phần 6) |
|---|---|
| PaySim | Gian lận chuyển tiền của người dùng cuối; không có nhà cung cấp, phê duyệt, lương |
| BankSim | Bộ tĩnh, không phải công cụ sinh hành vi sát ngưỡng như mô tả |
| IBM AMLSim, SAML-D | Rửa tiền; không có mẫu sát ngưỡng hay chia nhỏ hóa đơn nội bộ |
| Bank Account Fraud (BAF) | Gian lận người xin mở tài khoản; chỉ để thử mất cân bằng lớp và trôi dữ liệu |
| Elliptic | Giao dịch Bitcoin bất hợp pháp; chỉ để thử lớp đồ thị |
| ICIJ Offshore Leaks | Đồ thị thật của pháp nhân ngoài khơi; chỉ để thử truy vấn đồ thị; có mặt trong dữ liệu không có nghĩa là vi phạm |
| Công cụ sinh sổ cái mã nguồn mở cá nhân | Không kiểm chứng được giấy phép và mức duy trì (một kho trả 404) |
| Bộ dữ liệu tổng hợp do bạn bạn làm (v2) | Có lỗi (tệp 03); thay bằng v3 và v4 |
