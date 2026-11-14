# Chiến lược dữ liệu và hợp đồng Workspace

## Ba tầng bằng chứng

| Tầng | Vai trò | Giới hạn kết luận |
|---|---|---|
| Dữ liệu thật tương tự | AR/P2P, khoản vay hoặc chuỗi tiền nước ngoài để thử từng năng lực | Không đại diện giao dịch SME Việt Nam |
| Thống kê/nguồn công bố | Đặt tham số hoặc đối chiếu độc lập cho máy phát | Khớp một tỷ lệ chưa xác nhận cấu trúc thanh toán |
| Synthetic có nhãn | Tạo World, shock và tình huống khó để kiểm hợp đồng/mô hình | Chỉ kiểm trong giả định mô phỏng |

Khảo sát trước đây chưa tìm được bộ hóa đơn–thanh toán SME Việt Nam công khai phù hợp. Đây là giới hạn của đợt khảo sát. Hiệu quả thật cần ledger độc lập của đối tác có quyền sử dụng và đánh giá riêng. Tồn kho file nằm trong [README](README.md); danh sách nguồn từng thử không đồng nghĩa raw còn trên đĩa.

## Dữ liệu ứng dụng

Hợp đồng chính: [adaptive/data.py](../../agent1/adaptive/data.py). Bảng dưới nêu trường chính; các trường tùy chọn, alias và quy tắc bắt buộc lấy từ `SCHEMAS`, `REQUIRED` và validator, không tự suy schema từ tài liệu cũ.

| Bảng | Định danh | Trường chính và vai trò |
|---|---|---|
| `invoices` | `invoice_id` | `customer_id`, `issue_date`, `due_date`, `amount`; thông tin kế toán/vòng đời khi có |
| `payments` | `payment_id` | `invoice_id`, `payment_date`, `amount`, `bank_id` khi liên kết sao kê |
| `bank` | `bank_id` | `account`, `date`, `direction`, `amount`, nội dung/đối tác |
| `statements` | `statement_id` | `account`, `start_date`, `end_date`, số dư đầu/cuối |
| `outflows` | `expense_id` | `date`, `amount`, `category`, `known_at`; các lần đến hạn T5, không là bảng chi dự kiến tổng quát |
| `expense_payments` | `settlement_id` | `expense_id`, `bank_id`, `payment_date`, `amount`, `known_at`; phần nghĩa vụ đã thực trả/nhận |
| `actions` | `event_id` | `invoice_id`, `date`, `kind`, `promise_date` nếu có, ngày biết |
| `invoice_events` | `event_id` | `invoice_id`, `event_type`, `event_date`, `known_at`; sự kiện vòng đời chứng từ |

Nạp qua CSV/Excel/XML → ghép cột và định dạng → xem trước → xác nhận lưu. Ngày tiền thực tế và `known_at` phục vụ hai đồng hồ khác nhau. VND phải chính xác theo đơn vị nguyên; số Excel quá lớn phải được đưa dưới dạng Text phù hợp. Cùng `payment_id` và cùng nội dung không tạo thêm lần thu.

T9 tạo đề xuất và ghi sổ quyết định sau duyệt; nhãn `auto` không tự ghi thanh toán. Sửa nguồn/đảo quyết định phải giữ lịch sử và kiểm lại công nợ. Lịch T5 và `expense_payments` tách nghĩa vụ khỏi thực trả; không tự xem khoản đã quá hạn là đã trả.

## Dữ liệu theo ngày chốt và nhãn

1. Đầu vào chỉ chứa phiên bản và giao dịch đã biết tại cutoff. Có ngày giao dịch cũ chưa đủ nếu bằng chứng chỉ được nhận sau cutoff.
2. Lịch sử huấn luyện T1 dựng từ quan sát hợp lệ; tách outcome horizon khỏi knowledge cutoff, kiểm cả điều chỉnh và hoàn nguyên.
3. Xác nhận phạm vi thanh toán là dữ liệu người dùng cung cấp. Thiếu phạm vi thì censor phần chưa quan sát, không biến “chưa thấy tiền” thành nhãn âm đã hoàn chỉnh.
4. Hóa đơn đóng do giảm trừ/xóa nợ khác hóa đơn đã thu tiền đủ. Tất toán T1 khác tiền partial; validation/audit/forecast dùng cùng adapter để tránh đổi nghĩa đầu ra.
5. Forecast lưu snapshot, bundle và bằng chứng. Nạp dữ liệu hoặc đổi active sau đó không sửa kế hoạch cũ; replay kiểm đúng hash/source/runtime.

Chi tiết: [T1 + partial](../04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md), [T6](../04_AI_Methods/T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md), [T10](../04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md).

## Phân biệt với dữ liệu nghiên cứu

World dùng schema riêng: `amount_gross`, `paid_date_true`, `bank_txns`, `txn_id`, `promises`, `daily_cash` cùng nhãn ẩn. Không nhập các cột sự thật tương lai thành feature ứng dụng. [ledger_bridge.py](../../agent1/adaptive/ledger_bridge.py) chuyển ledger nghiên cứu sang ngữ nghĩa Workspace; [contracts.py](../../agent1/data/contracts.py) kiểm dữ liệu World.

Nguồn thật có thể dùng thử phương pháp hoặc kiểm độc lập. Nguồn đã hiệu chỉnh máy phát không còn là bằng chứng độc lập cho cùng đại lượng. Chia train/validation/test theo thời gian và World; số hóa đơn lớn không thay số doanh nghiệp/World độc lập.
