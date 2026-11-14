# Nguồn thật và điều kiện sử dụng

Hiện chưa có dữ liệu raw trong `data/`; `data/raw/` là thư mục làm việc trống được `agent1/paths.py` tự tạo (kiểm 14/11/2026). Các nguồn bên dưới là nguồn từng khảo sát/thử nghiệm, không phải danh mục đầu vào sẵn chạy. Bộ nạp nằm ở [real_loaders.py](../../agent1/data/real_loaders.py), công cụ lấy nguồn ở [crawl.py](../../scripts/crawl.py). Chạy lại cần file gốc, giấy phép, ngày tải/vintage và hash đúng phiên bản; không suy từ số dòng báo cáo cũ rằng cache còn tồn tại.

## Nguồn từng dùng

| Nguồn | Vai trò | Giới hạn quan trọng |
|---|---|---|
| BPI Challenge 2019 | Thử thời điểm thanh toán trên sự kiện P2P | Phải trả của tập đoàn; `Clear Invoice` là sự kiện quy trình; thiếu due date thật, không phải AR SME Việt Nam |
| Customer Invoices/HighRadius, bản sao cộng đồng | AR giống ERP, thử T1 và cấu trúc hành vi | Nguồn gốc/giấy phép chưa rõ; `clear_date` là ngày ghi sổ; tập open bị chia theo thời gian; không có nhãn vỡ nợ/sao kê |
| SBA 7(a) FOIA | Xác suất xóa nợ/hiệu chỉnh sự kiện hiếm | Khoản vay Mỹ khác hóa đơn B2B; xử lý nhãn và thời gian theo dõi riêng |
| Berka PKDD'99 | Chuỗi tiền thật, độ phủ và phát hiện thay đổi | Ngân hàng Séc thập niên 1990, nhiều tài khoản cá nhân; không học hành vi hóa đơn |
| Online Retail II | Doanh thu tuần, thử mô hình T4 | Giao dịch bán lẻ/bán buôn Anh; không có lịch thanh toán công nợ |
| UK Payment Practices | Tham chiếu họ phân phối trễ | Thống kê DN lớn bên trả, không phải lịch trả cấp hóa đơn; không dùng làm đích Việt Nam |
| OxCGRT Việt Nam | Nguồn chính sách COVID cho đường sốc | Chỉ số chính sách khác tác động kinh tế/thanh toán; metadata công bố cần kiểm khi dùng làm feature |
| WDI Việt Nam | Lãi suất và bối cảnh vĩ mô | Chỉ số năm, revision/vintage khác nhau; không là quan sát thanh toán |

Phân biệt các nguồn chính thức, dữ liệu công khai có điều khoản và bản sao cộng đồng. Kết quả phương pháp trên một nguồn không nâng độ tin cậy của nguồn khác hoặc của bộ synthetic. Liên kết thống kê/phương pháp nằm ở [tài liệu tham khảo](08_tai_lieu_tham_khao.md).

## Nguồn đã loại hoặc hoãn

| Nhóm | Quyết định nghiên cứu và điều kiện xem lại |
|---|---|
| Bộ AR cộng đồng không xác minh (Global B2B Payment, AR Payment Delay, IBM mirror, Payment Date) | Chưa đưa vào nguồn chính; cần kiểm nguồn gốc, license, censoring và dấu hiệu sinh bằng trọng số cố định |
| Home Credit, M5 | Cần đăng nhập/chấp nhận điều khoản và kiểm mức phù hợp; không phải đầu vào hiện có |
| Freddie Mac, Bondora | Cấu trúc khoản vay khác AR; chỉ thử chuyển trạng thái khi có dữ liệu/điều khoản phù hợp |
| Payment Times Reports Úc | Cần kiểm điều khoản và lấy nguồn trước; vai trò thống kê tương tự UK PPR |
| SEC, Companies House | Có thể tham chiếu BCTC/đuôi shock; cần quy trình truy cập hợp lệ, mapping và ngày công bố |
| UNU-WIDER SME Việt Nam, World Bank Enterprise Surveys | Cần quyền truy cập, xác nhận biến bán chịu và phạm vi năm/ngành |
| Olist, OCEL mô phỏng | Khác bài toán hoặc là mô phỏng; kiểm giấy phép trước dùng; không nâng thành ledger SME Việt Nam |
| Xero, Coface | Chỉ tham chiếu phương pháp/độ nhạy; Xero có chọn lọc hóa đơn đã trả, khảo sát Coface không thay nhãn AR Việt Nam |

Đây là quyết định trong khảo sát trước, không xác nhận điều khoản/trạng thái tải hiện nay. Nguồn chỉ chứa hóa đơn đã đóng hoặc loại trả cực chậm không đủ để tạo nhãn kiểm duyệt hợp lệ. Không điều chỉnh đuôi Việt Nam chỉ để giống ERP nước ngoài.

## Đối chiếu BCTC niêm yết

[vn_listed_inputs.json](vn_listed_inputs.json) là đầu vào còn dùng bởi [run_vn_listed_check.py](../../scripts/run_vn_listed_check.py). Giữ số liệu và xuất xứ ở JSON thay vì chép lại thành bảng thứ hai. Đây là ba DN-kỳ, chưa có người chép số độc lập thứ hai; PDF gốc cần khôi phục trước khi xác minh lại.

| DN-kỳ | Nguồn và trang đã dùng | Giới hạn |
|---|---|---|
| SMC 2024 | [BCTC hợp nhất](https://smc.vn/wp-content/uploads/2025/05/BCTC-HOP-NHAT-SAU-KIEM-TOAN-2024-ENG.pdf), PDF 7/9/11; [đính chính](https://smc.vn/dinh-chinh-bao-cao-tai-chinh-nam-2024/) | Trường hợp công nợ đặc biệt, không đại diện ngành thép |
| TCM 2022 | [BCTC kiểm toán](https://www.thanhcong.com.vn/wp-content/uploads/2023/03/20230324-TCM-BCTC-hop-nhat-nam-2022-da-kiem-toan_VN.pdf), PDF 7/9/10 | Không gắn số 2022 thành 2024 |
| NTP 2024 | [Báo cáo thường niên](https://admin.nhuatienphong.vn/img/posts/1_f2284364f5cd0dd5e057ecb4e3e165f0BCTN%202024.pdf), PDF 59–60 | Mẫu riêng, không thay tên thành BMP |

```text
DSO proxy = 365 × phải thu khách hàng ngắn hạn bình quân / doanh thu thuần
DPO proxy = 365 × phải trả người bán ngắn hạn bình quân / giá vốn
```

Phải thu dùng số gộp trước dự phòng; không gồm mọi khoản cho vay/tạm ứng. Giá vốn khác giá trị mua chịu. Khác biệt VAT, mùa vụ, bán thu ngay, xóa nợ và số dư chỉ ở hai thời điểm hạn chế khả năng so với World. Một doanh nghiệp mỗi ngành và khác năm không đủ để đặt dung sai hoặc bootstrap CI đại diện SME; các điểm này không dùng chỉnh máy phát.
