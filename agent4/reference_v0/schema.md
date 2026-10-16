# Canonical schema – sổ cái kế toán (TT133)

Thiết kế theo Star Schema: `gl_entry` là fact ở cấp dòng bút toán; một chứng từ có tối thiểu một dòng Nợ và một dòng Có. `entry_id` định danh dòng, còn `journal_id` gom các dòng cùng chứng từ. Vì vậy kiểm tra cân đối được thực hiện theo `journal_id`: tổng Nợ phải bằng tổng Có.

## Quy ước chung

- Khóa surrogate dùng `BIGINT`; ngày dùng `DATE`, tiền dùng `DECIMAL(18,2)`.
- `debit_amount` và `credit_amount` không âm; mỗi dòng chỉ điền một trong hai cột (CHECK XOR), và mỗi `journal_id` phải có tổng hai phía bằng nhau.
- `account_code` lưu mã TT133 dạng chuỗi để giữ được mã chi tiết; `account_type` là phân nhóm báo cáo, không thay thế số hiệu tài khoản.

## `gl_entry` – fact sổ cái

| Tên cột | Kiểu dữ liệu | PK/FK | Diễn giải |
|---|---|---|---|
| `entry_id` | BIGINT | PK | Định danh duy nhất của dòng bút toán |
| `journal_id` | VARCHAR(40) | | Mã chứng từ; các dòng cùng chứng từ dùng cùng mã |
| `entry_no` | INTEGER | | Thứ tự dòng trong chứng từ |
| `posting_date` | DATE | | Ngày hạch toán |
| `period_key` | INTEGER | FK → `dim_period.period_key` | Kỳ kế toán của ngày hạch toán |
| `account_key` | BIGINT | FK → `dim_account.account_key` | Tài khoản ghi nhận |
| `partner_key` | BIGINT | FK → `dim_partner.partner_key` | Đối tác, có thể NULL |
| `item_key` | BIGINT | FK → `dim_item.item_key` | Sản phẩm/dịch vụ, có thể NULL |
| `description` | VARCHAR(500) | | Diễn giải nghiệp vụ |
| `debit_amount` | DECIMAL(18,2) | | Số tiền ghi Nợ, >= 0 |
| `credit_amount` | DECIMAL(18,2) | | Số tiền ghi Có, >= 0 |
| `currency_code` | CHAR(3) | | Mã tiền tệ, mặc định VND |
| `source_document_type` | VARCHAR(30) | | Loại chứng từ: invoice, receipt, payment... |
| `source_document_no` | VARCHAR(50) | | Số chứng từ nguồn |
| `created_at` | TIMESTAMP | | Thời điểm nạp dữ liệu |

Ràng buộc dòng: `debit_amount >= 0`, `credit_amount >= 0`, `((debit_amount > 0 AND credit_amount = 0) OR (debit_amount = 0 AND credit_amount > 0))`. Ràng buộc kép ở cấp chứng từ: `SUM(debit_amount) = SUM(credit_amount)` theo `journal_id` (kiểm tra bằng query/ETL vì CHECK không dùng được aggregate).

## `dim_account` – danh mục tài khoản TT133, Phụ lục 1

| Tên cột | Kiểu dữ liệu | PK/FK | Diễn giải |
|---|---|---|---|
| `account_key` | BIGINT | PK | Khóa thay thế |
| `account_code` | VARCHAR(10) | UNIQUE | Mã TK, ví dụ 111, 112, 131, 331, 511 |
| `account_name` | VARCHAR(255) | | Tên tài khoản theo TT133 |
| `account_type` | VARCHAR(30) | | Tài sản/Nợ phải trả/Vốn chủ sở hữu/Doanh thu/Chi phí |
| `normal_balance` | CHAR(1) | | Dư thường: D hoặc C |
| `parent_account_code` | VARCHAR(10) | | Tài khoản tổng hợp cha, nếu có |
| `is_postable` | BOOLEAN | | Có cho phép hạch toán trực tiếp không |
| `effective_from` | DATE | | Ngày bắt đầu hiệu lực |
| `effective_to` | DATE | | Ngày kết thúc hiệu lực, có thể NULL |

Danh mục tối thiểu generator dùng: 111, 112, 131, 1331, 138, 141, 152, 153, 154, 156, 211, 214, 331, 3331, 3334, 334, 338, 341, 411, 421, 511, 515, 521, 632, 635, 641, 642, 811, 821, 911.

## `dim_partner` – đối tác

| Tên cột | Kiểu dữ liệu | PK/FK | Diễn giải |
|---|---|---|---|
| `partner_key` | BIGINT | PK | Khóa thay thế |
| `partner_code` | VARCHAR(30) | UNIQUE | Mã đối tác |
| `partner_name` | VARCHAR(255) | | Tên khách hàng/NCC/nhân viên |
| `partner_type` | VARCHAR(20) | | CUSTOMER, VENDOR, EMPLOYEE, OTHER |
| `tax_id` | VARCHAR(20) | | Mã số thuế, nếu có |
| `is_active` | BOOLEAN | | Trạng thái sử dụng |

## `dim_period` – thời gian

| Tên cột | Kiểu dữ liệu | PK/FK | Diễn giải |
|---|---|---|---|
| `period_key` | INTEGER | PK | Khóa dạng YYYYMMDD |
| `calendar_date` | DATE | UNIQUE | Ngày lịch |
| `day_of_month` | SMALLINT | | Ngày trong tháng |
| `month_no` | SMALLINT | | Tháng 1–12 |
| `quarter_no` | SMALLINT | | Quý 1–4 |
| `year_no` | SMALLINT | | Năm |
| `month_start_date` | DATE | | Ngày đầu tháng |
| `month_end_date` | DATE | | Ngày cuối tháng |

## `dim_item` – sản phẩm/dịch vụ

| Tên cột | Kiểu dữ liệu | PK/FK | Diễn giải |
|---|---|---|---|
| `item_key` | BIGINT | PK | Khóa thay thế |
| `item_code` | VARCHAR(40) | UNIQUE | Mã sản phẩm/dịch vụ |
| `item_name` | VARCHAR(255) | | Tên hàng hóa/dịch vụ |
| `item_type` | VARCHAR(20) | | PRODUCT hoặc SERVICE |
| `unit` | VARCHAR(20) | | Đơn vị tính |
| `standard_cost` | DECIMAL(18,2) | | Giá vốn chuẩn tham chiếu |
| `is_active` | BOOLEAN | | Trạng thái sử dụng |

