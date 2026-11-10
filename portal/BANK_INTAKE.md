# Sao kê dùng chung

Chọn hồ sơ doanh nghiệp, mở khóa **Nạp dữ liệu**, chọn mỗi sao kê CSV UTF-8 hoặc XLSX một lần và bấm ghi khi cả hai agent báo sẵn sàng. Với XLSX, dùng trang tính đầu tiên, tiêu đề ở dòng đầu có nội dung và số tài khoản, mã giao dịch ở dạng văn bản. [Mẫu mô phỏng hai giao dịch](static/samples/sao-ke-chung.csv).

| Trường | Yêu cầu |
| --- | --- |
| `bank_id` | Mã giao dịch ổn định và duy nhất trong công ty. Nếu ngân hàng tái sử dụng mã giữa nhiều tài khoản, ghép mã tài khoản với mã giao dịch và dùng nhất quán với sổ tiền khách trả. |
| `account` | Tài khoản của doanh nghiệp. Giữ nguyên số 0 đầu. |
| `date` | `YYYY-MM-DD`, `DD/MM/YYYY` hoặc ô ngày Excel. |
| `direction`, `amount` | `in` / `out` hoặc `Thu` / `Chi`, số tiền dương bằng VND. Có thể dùng cặp `debit`, `credit` (Ghi Nợ, Ghi Có) thay thế. |
| `description`, `counterparty_account`, `counterparty_name` | Nên có để A3 nhận biết giao dịch đối ứng và hóa đơn liên quan. |
| `known_at`, `component`, `currency` | Không bắt buộc. Mặc định ngày giao dịch, `other`, VND. |

Portal chuyển phần giao dịch và thời điểm ghi nhận sang A1, chuyển chiều Ghi Nợ/Ghi Có cùng nội dung và đối tác sang A3. Mỗi công ty lưu một bản tệp gốc theo SHA-256. Khi một agent đã ghi nhưng agent kia lỗi, kiểm tra lại và ghi tiếp từ cùng hàng chờ. A3 không cộng lại giao dịch chung có cùng mã và nội dung. Không nạp chồng sao kê chung lên sao kê theo mẫu thuế cũ của cùng kỳ nếu chưa đối chiếu, vì tệp cũ có thể không có mã để đối chiếu tự động.

Các tệp còn lại vẫn theo nghiệp vụ hiện tại. Sổ hóa đơn bán, phân bổ tiền khách trả, lịch chi, số dư kỳ và nhật ký thu nợ đi A1. Sổ giao dịch có định khoản và thông tin phê duyệt đi A2. XML/ZIP hóa đơn và bảng kê cổng thuế đi A3. Kho sổ cái của A4 vẫn do cấu hình máy chủ quản lý. Mẫu hai dòng chỉ dùng thử luồng sao kê, không thay thế bộ MPX10 đã chuẩn bị cho từng kho.
