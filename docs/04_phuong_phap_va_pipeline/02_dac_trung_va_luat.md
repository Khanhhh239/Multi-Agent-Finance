# Đặc trưng và luật

## 1. Nguyên tắc nhân quả
Mọi đặc trưng tính trong **một lượt theo thời gian**: dòng chỉ thấy các dòng đăng sổ **trước** nó; các dòng cùng thời điểm được cập nhật sau khi chấm. Kiểm thử: `test_engineered_features_are_causal`, `test_memory_features_match_bruteforce_and_are_causal`. Danh mục chủ chỉ dùng khi `recorded_at` không sau thời điểm đăng sổ.

## 2. Bốn nhóm đặc trưng

| Nhóm | Số cột | Nội dung | Mã |
|---|---:|---|---|
| Gốc của bạn bạn | 190 | Mã hóa loại nghiệp vụ, cặp tài khoản; giờ, thứ, tháng; số tiền theo lịch sử công ty theo loại nghiệp vụ; số chứng từ; tự duyệt; đã xác minh nhận hàng | `sme_fraud/features.py` |
| Baseline thực thể (`ENGINEERED`) | 31 | Giá so với trung vị các lần mua gần nhất của nhà cung cấp; z-score giá; dịch chuyển ba lần mua gần nhất; lương so với mức thường lệ của nhân viên (tách tháng thưởng); số tiền so với việc người lập thường làm; gần trùng 30 ngày (khác số hóa đơn); tập trung cặp người lập, người duyệt; tự duyệt tiền mặt sát hạn mức; ngày nằm ngủ của nhà cung cấp; tháng cuối, trước Tết | `agent2/feats.py` |
| Dấu hiệu đỏ v4 (`V4_FEATURES`) | 15 | Xem mục 3 | `agent2/feats_v4.py` |
| Luật | khoảng 34 cột `hit_*` cộng 3 điểm | Điểm từng luật và điểm tổng | `sme_fraud/rules.py` qua `data.rule_frame` |

## 3. Mười lăm dấu hiệu đỏ v4

Mỗi dấu hiệu là một cờ kiểm toán nghiệp vụ, tính từ thông tin có tại thời điểm đăng sổ.

| Đặc trưng | Ý nghĩa | Nhắm kịch bản |
|---|---|---|
| `receipt_payer_mismatch` | Tài khoản người trả trên sao kê khác khách hàng mà phiếu thu áp dụng | receivable_lapping |
| `receipt_days_late` | Số ngày trễ so với hạn của hóa đơn | lapping, lập hóa đơn khống |
| `collector_late_trend_90d` | Độ trễ trung bình các phiếu thu do cùng người phụ trách trong 90 ngày | lapping |
| `payee_not_on_master` | Thanh toán cho tài khoản không có trong danh mục và không có thay đổi đã ghi | altered_payee, shell_vendor |
| `payroll_after_leave` | Lương đăng sau ngày ghi nhận nghỉ việc | terminated_still_paid |
| `payroll_off_calendar` | Lương đăng cách ngày trả lương công bố hơn 3 ngày | off_cycle_payroll, fake_bonus_list |
| `payroll_rows_same_month` | Số dòng lương trước đó của cùng nhân viên trong tháng | off_cycle_payroll |
| `writeoff_overdue_days` | Tuổi quá hạn của hóa đơn mở lâu nhất của khách khi xóa nợ (0 nếu không có) | lapping, xóa nợ khống |
| `refund_to_foreign_account` | Hoàn tiền cho tài khoản không phải của khách | false_refund |
| `return_vs_recent_sales` | Giá trị trả hàng chia doanh số 60 ngày gần nhất của khách | false_refund |
| `writeoff_vs_cogs_90d` | Hủy hàng chia giá vốn 90 ngày | inventory_theft, skimming |
| `creator_writeoffs_90d` | Số lần hủy hàng của cùng người lập trong 90 ngày | inventory_theft |
| `offquarter_writeoff` | Hủy hàng không vào ngày kiểm kê cuối quý | inventory_theft |
| `customer_amount_logz` | Số tiền hóa đơn bán so với lịch sử của chính khách | phantom sales (khi dùng lại) |
| `self_approved_advance_ratio` | Tạm ứng tự duyệt chia hạn mức duyệt | owner_override_transfer |

**Cảnh báo:** 15 đặc trưng này do cùng người viết bộ sinh. Chúng là *cờ kiểm toán thật* nhưng việc chúng bắt tốt kịch bản có thể do kịch bản được viết để lộ đúng chúng.

## 4. Luật (34 mã trong `RULE_NAMES`; tài liệu cũ gọi là 31 luật cộng đồ thị)

| Nhóm | Mã | Nội dung |
|---|---|---|
| A. Chia nhỏ và số tiền | A1 đến A6 | Chia nhỏ cùng người nhận trong 3 ngày; cùng người lập hoặc người nhận trong 30 ngày; qua cụm người nhận liên kết; nhiều khoản cận hạn mức; số tiền tròn lệch baseline; thanh toán làm tròn vượt hóa đơn gốc |
| B. Nhà cung cấp | B1 đến B7 | Tài khoản hoặc căn cước trùng nhân viên; thông tin hoặc người đại diện liên kết nhân viên; nhà cung cấp mới nhận khoản lớn đầu tiên; trạng thái người phát hành hóa đơn rủi ro; nhiều nhà cung cấp chung định danh; nhà cung cấp ngủ đông nhận khoản lớn; đổi tài khoản gần ngày thanh toán chưa xác minh |
| C. Quyền và giờ | C1 đến C4 | Lập hoặc duyệt ngoài lịch; tự duyệt vượt quyền; duyệt dưới 60 giây ở cấp cao; thao tác trong kỳ nghỉ phép |
| D. Thống kê chữ số | D1 đến D6 | Benford chữ số đầu và thứ hai, hai chữ số đầu sát hạn mức, đuôi số, MAD, theo phân đoạn (**chỉ chẩn đoán, không cộng điểm cho giao dịch lẻ**) |
| E. Lương và danh tính | E1 đến E4 | Lương không có chấm công; lương sau chấm dứt hợp đồng; tên nhà cung cấp tương tự; nhà cung cấp trùng định danh |
| F. Điều chỉnh | F1 đến F4 | Điều chỉnh tay sát khóa sổ; quản lý ghi đè; khoảng trống hoặc trùng số chứng từ; công nợ kéo dài chưa đối chiếu tiền |
| P, T | P1, T1, T2 | Thanh toán vượt hóa đơn; tạm ứng quá hạn; xóa nợ tạm ứng thiếu hồ sơ |

Chi tiết cơ sở bằng chứng từng luật và điều chỉnh đề xuất: [Phần 8 mục 1](../07_tai_lieu_tham_khao/DIGITAL_ACCOUNTING_PART8_AGENT2_METHODS.md) và `docs/06_ghi_chep_lam_viec/rule_class_1.md`. Mã luật có chế độ đồ thị (`enable_graph`): cạnh tài khoản, điện thoại, địa chỉ, người đại diện dùng chung.

## 5. Các điểm yếu đã biết của bộ đặc trưng
1. 190 đặc trưng gốc chỉ giữ lịch sử mức công ty theo loại nghiệp vụ, nên không thấy gian lận lẫn trong hành vi của một thực thể (đã sửa bằng nhóm baseline thực thể).
2. Các quy trình thu tiền, lương theo lịch, xóa nợ, hủy hàng không có đặc trưng trong 190 cột (đã bổ sung bằng 15 dấu hiệu đỏ).
3. Chưa có đặc trưng đồ thị tổng hợp (số lân cận chung, tổng tiền qua tài khoản chung) cho mô hình học; đồ thị mới chỉ vào qua điểm luật (giả thuyết H12 ở tệp 08).
4. Chưa có dòng hàng hóa đơn nên giá theo mặt hàng chưa kiểm được.
