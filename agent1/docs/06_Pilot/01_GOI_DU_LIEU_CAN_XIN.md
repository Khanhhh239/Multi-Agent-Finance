# Dữ liệu cần chuẩn bị cho Agent 1

Danh sách đầu vào để chuẩn bị pilot; chưa là lời mời hoặc cam kết triển khai. Phải chốt quyền sử dụng, phạm vi và điều kiện [nghiệm thu](../03_Evaluation/03_cong_nghiem_thu.md) trước khi nhận dữ liệu thật.

## Chốt phạm vi trước khi xuất

Chọn doanh nghiệp, tài khoản ngân hàng VND, ngày chốt, số dư đầu và mức tiền tối thiểu. Dùng mã khách/chứng từ/bí danh tài khoản nhất quán giữa các bảng. Ghi thời điểm thực sự biết thông tin (`known_at`); file xuất hôm nay không chứng minh mọi phiên bản đã có ở các ngày quá khứ.

CSV UTF-8/XLSX hoặc XML hóa đơn được hỗ trợ theo [schema dịch vụ](../../agent1_service/README.md#hợp-đồng-đầu-vào-sme). Giới hạn Workspace hiện tại: 5 MB/file, 50.000 dòng; chọn rõ ngày/số và sheet. Không làm mất số 0 đầu, không có dòng tổng cộng, tiền VND nguyên. Thiếu trường bắt buộc phải sửa ở bản xem trước.

| Bảng | Nội dung cần có | Vai trò |
|---|---|---|
| Hóa đơn và vòng đời | ID ổn định, khách, ngày lập/hạn, số tiền, ngày biết; chứng từ điều chỉnh/thay thế/hủy và liên kết nguồn khi có | Công nợ hiệu lực tại ngày chốt; XML thiếu hạn không được tự suy hạn |
| Dòng ngân hàng | ID, tài khoản, ngày, chiều thu/chi, tiền; nội dung/người chuyển/mã khách/phân loại nếu có | Tiền thực; không đồng nhất với phân bổ công nợ |
| Thanh toán đã phân bổ | ID payment, hóa đơn, ngày, tiền, bank ID nếu có, ngày biết | Các lần thu từng phần/tất toán; một khoản cho nhiều hóa đơn tách dòng |
| Kỳ sao kê và số dư | Tài khoản, kỳ, số dư đầu/cuối, ngày biết | Đối chiếu số dư và xác định tuần quan sát được |
| Nghĩa vụ T5 | Mỗi lần đến hạn có ID, ngày, tiền, loại, ngày biết và nguồn/phê duyệt khi cần | Lương/thuê/vay/thuế đã biết; không coi là toàn bộ chi tương lai |
| Thực trả/nhận T5 | ID settlement, nghĩa vụ, bank, ngày, tiền, ngày biết | Tính phần còn lại; hoàn VAT đã duyệt là dòng thu riêng |
| Hành động/lời hứa | ID sự kiện/hóa đơn, ngày, loại, ngày biết; ngày hứa khi có | Bằng chứng xử lý và danh sách ưu tiên; không cam kết làm tăng độ chính xác |

## Lịch sử và độ đầy đủ

Nên chuẩn bị lịch sử công nợ và sao kê cùng kỳ, gồm cả hóa đơn chưa trả, credit/write-off và thay đổi phiên bản. Không chỉ xuất hóa đơn đã tất toán. Độ dài lịch sử tự nó chưa đủ để học tiếp; T1 còn kiểm số mẫu, coverage và nhãn trưởng thành 91 ngày. Thiếu điều kiện thì giữ global/incumbent, không tạo nhãn thay thế.

Nhánh hoạt động cần lịch sử sao kê liên tục, đúng tài khoản và đủ điều kiện kiểm định. Bộ chọn hiện yêu cầu ít nhất 104 tuần và ba gốc validation cùng audit; mỗi đoạn fit cần ít nhất 52 tuần. Dự báo cũng kiểm lại tối thiểu 52 tuần lịch sử, nhưng riêng điều kiện này không đủ để chọn learner. Hóa đơn mới tương lai mặc định không bật. Đánh giá kế hoạch 13 tuần phải chờ đủ thực tế tương ứng; chương trình quan sát tám tuần chưa chấm trọn mọi kế hoạch 13 tuần.

Kế toán xác nhận riêng phạm vi thanh toán đã đủ đến cutoff và tuần lịch chi đã rà soát. Có một khoản chi không có nghĩa cả tuần đầy đủ; chưa có sao kê không phải thu/chi bằng 0. Số dư đầu + thu − chi phải khớp số dư cuối trên cùng tài khoản.

## Tiếp nhận và cập nhật

Kiểm quyền sử dụng và [bảo vệ dữ liệu](02_CAM_KET_BAO_MAT.md), dùng kho riêng. Nạp theo thứ tự trong [sổ tay](SO_TAY_AGENT1.md), giữ ID ổn định cho kỳ tiếp theo. T9 chỉ giảm công nợ sau duyệt; ca thiếu bằng chứng để chờ xác minh. Không cần mật khẩu/OTP ngân hàng hoặc quyền tự chuyển tiền.

Khóa dự báo trước khi biết kết quả và cập nhật thực thu/thực chi theo kỳ đã thống nhất. Biểu mẫu, quan sát người dùng và tiêu chí quyết định tập trung trong [bộ pilot](../../pilot/BO_PILOT_SME.md).
