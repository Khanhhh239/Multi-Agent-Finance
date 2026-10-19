# Hợp đồng dữ liệu và nhãn T1

Trang này chỉ ghi hợp đồng dữ liệu và nhãn cho **T1 — dự báo thời điểm thanh toán hóa đơn**, gồm dữ liệu nguồn đang audit và đầu vào của phần dự báo thời điểm trả trong pipeline notebook lịch sử. Đây không phải hợp đồng dữ liệu chung cho toàn bộ T0–T13; schema, nhãn và phạm vi quan sát của các task khác cần được định nghĩa riêng.

Mapping thực tế phải được kiểm tra trong code; thay đổi định nghĩa T1 phải cập nhật cả trang này và phần xử lý liên quan.

Bộ notebook cũ hiện nằm tại `reference_notebooks/` và chỉ dùng tham khảo. Schema và bộ lọc lịch sử dưới đây không mặc định là thiết kế của code T1 mới, vốn chưa được triển khai.

## Hai lớp dữ liệu khác nhau

| Lớp | Nguồn xác định | Ý nghĩa |
|---|---|---|
| Raw và audit Séc | [Hướng dẫn T1](../../data/T1/README.md), [script audit](../../scripts/data_audit/audit_czech_t1_datasets.py) | Giữ field/nguồn và flag chất lượng. Chưa phải input huấn luyện đã xử lý dedup và nhãn. |
| Input notebook lịch sử | [Notebook 01](../../reference_notebooks/01_data_preparation_eda.ipynb), [survival helper](../../reference_notebooks/survival_utils.py) | Schema hóa đơn phải thu, bảng sạch và rolling snapshot. Chưa có adapter từ audit Séc sang schema này. |

## Field đầu vào nghiệp vụ

Các field phục vụ T1 trong pipeline lịch sử; không phải schema chung cho mọi task hay bộ validator đã triển khai cho mọi nguồn:

| Field | Ngữ nghĩa phải xác định |
|---|---|
| `invoice_id` | Khóa hóa đơn ổn định trong phạm vi nguồn/doanh nghiệp; không lấy mỗi dòng ngân sách hoặc dòng hàng làm hóa đơn mới. |
| `customer_id` | Bên có nghĩa vụ thanh toán. Với dữ liệu mua hàng công, đó là buyer, không phải supplier. |
| `issue_date` | Ngày phát hành theo nguồn. Mapping lịch sử dùng `posting_date`; phải xác minh ý nghĩa, không tự đồng nhất mọi ngày ghi sổ với ngày phát hành. |
| `due_date` | Ngày đến hạn; ghi rõ cách xử lý thiếu, ngày bất hợp lý và điều khoản thanh toán. |
| `paid_date` | Ngày sự kiện được chọn làm nhãn: lần đầu, tất toán hay ghi nhận thanh toán. Không tự suy ra ngày tiền khả dụng trên sao kê. |
| `amount` và `currency` | Phân biệt mệnh giá hóa đơn, số dư mở và số thực trả; quy đổi cần quy tắc/tỷ giá/thời điểm. |
| `payment_terms` | Số ngày điều khoản có ý nghĩa nghiệp vụ; mã điều khoản cần mapping. Không mặc định loại điều khoản 0 ngày chỉ vì helper lịch sử lọc `> 0`. |
| `is_open` | Trạng thái tại thời điểm quan sát xác định được, không lấy trạng thái cuối dữ liệu làm trạng thái ở mọi cutoff. |

Input gốc notebook 01 gồm các tên như `invoice_id`, `cust_number`, `posting_date`, `due_in_date`, `clear_date`, `total_open_amount`, `invoice_currency`, `cust_payment_terms`, `isOpen`. Chi tiết mapping và biến dẫn xuất phải đọc trong notebook; bảng trên không chứng minh hai bộ Séc thay trực tiếp được input gốc.

## Nhãn và thời điểm biết thông tin

- Từ lúc phát hành: `days_to_payment = paid_date - issue_date`; chậm hạn: `days_late = paid_date - due_date`. Nếu dùng ngày tiếp nhận làm mốc, đặt tên/benchmark riêng, không trộn với tuổi từ ngày phát hành.
- Tại cutoff `T`: hóa đơn phải tồn tại và còn nghĩa vụ thanh toán tại `T`; thời gian còn lại tính từ `T`. Lịch sử khách hàng và aggregate chỉ dùng thông tin đã biết ở `T`.
- Survival cần mốc kết thúc quan sát từ metadata nguồn. Missing paid date chưa đủ để gán `event=0`; cần chứng minh hóa đơn nằm trong tập có thể quan sát, vẫn chưa trả tới cuối quan sát. Censoring không đồng nghĩa default.
- Phân biệt ngày nghiệp vụ với ngày công bố/nhập dữ liệu. Chỉ dùng dữ liệu trước cutoff nếu thực sự có sẵn; nếu giả định quyền truy cập ERP nội bộ, ghi rõ giả định.
- Chia train/calibration/test theo thời gian và tách fit, hiệu chỉnh, đánh giá. Thanh toán tương lai được dùng tạo nhãn trong cửa sổ quan sát, không dùng làm feature tại `T`.

## Trước khi dùng nguồn Séc để train

Chốt đơn vị quan sát và xử lý trùng/conflict; xác định loại chứng từ, vai trò buyer/seller, tiền tệ, mốc ngày trả và thời điểm quan sát. Công bố rõ cohort chỉ có hóa đơn quan sát được thanh toán hay có cả hóa đơn chưa trả. Audit gate không thay các quyết định này.

Các điểm cần sửa của pipeline lịch sử nằm tại [đề xuất dataset T1](../../research/notes/t1_dataset_recommendation.md); field audit BPI/DC tại [ghi chú đối chiếu](../../research/notes/t1_bpi_dc_field_audit.md). Thống kê chất lượng được duy trì tại [báo cáo audit toàn bộ](../../research/notes/t1_czech_full_dataset_audit.md).
