# T5 và dòng tiền hoạt động

Mã phục vụ: [obligations.py](../../agent1/adaptive/obligations.py), [obligation_imports.py](../../agent1/adaptive/obligation_imports.py), [operating.py](../../agent1/adaptive/operating.py) và [methods.py](../../agent1/adaptive/methods.py). Hợp đồng nạp chi tiết ở [dịch vụ/T5](../../agent1_service/README.md#t5-ledger).

## Nghĩa vụ và phần đã thanh toán

`outflows` là **mỗi lần đến hạn** T5; không phải mẫu tự lặp hoặc bảng chi dự kiến tổng quát. Mỗi khoản có `expense_id`, ngày, số tiền, loại và `known_at`. `expense_payments` nối phần thực trả/nhận với nghĩa vụ và dòng bank.

Định danh nghiệp vụ gồm `obligation_ref` + loại nghĩa vụ + `payment_period` + `installment_no`; ba trường bổ sung phải đi cùng nhau. Dời tiền thuê tháng 11 sang tháng 12 vẫn giữ kỳ tháng 11. Nạp bổ sung phân loại mới/sửa/trùng/xung đột, không xóa dòng vắng mặt và không tạo mã mới cho cùng lần đến hạn. Nội dung không đổi giữ ngày biết; sửa cần ngày biết mới, giữ snapshot cũ. Khoản cũ thiếu định danh tiếp tục dùng ID và được báo cần bổ sung.

```text
Phần còn lại = nghĩa vụ có hiệu lực − thanh toán hợp lệ đã biết
```

Ngày/chiều bank phải khớp, tổng phân bổ bank và tổng trả cho nghĩa vụ không vượt nguồn. Trả từng phần giảm dư còn phải trả; tiền đã xảy ra thuộc số dư đầu, không trừ lại. Chi cố định không gắn vào bank `variable_cost` để tránh fit rồi cộng lại.

Khoản chi đến/quá hạn còn dư được đưa tới ngày làm việc kế tiếp hoặc `forecast_date` hợp lệ do doanh nghiệp nhập. Hủy phần còn lại dùng `status=cancelled`, giữ thanh toán và lịch sử. `replaces_expense_id` thay lịch cũ chưa có thanh toán, không dùng để làm mất liên kết tiền đã trả.

## Hồ sơ mở rộng và khoản thu hoàn

TNCN khấu trừ, thuế nhà thầu, thưởng, thuê hợp đồng, gốc/lãi vay và quyết toán TNDN còn phải nộp dùng hồ sơ có `source` và `verified=true`. Số tiền/hạn do hồ sơ cung cấp; hệ thống không tự suy thuế, gross-up, quyền hưởng thưởng hay số quyết toán đã trừ tạm nộp.

`vat_refund` là dòng **thu nghĩa vụ** riêng (`obligation_in`), cần quyết định hoàn biết trước cutoff. Tiền hoàn thực nhận nối bank chiều thu, không coi là chi âm hoặc AR. Chưa có quyết định thì không dự thu; quá ngày dự kiến nhận cần ngày mới, không tự lùi sang ngày mai. Quy ước ngày làm việc theo trường hồ sơ. `verified` của hồ sơ chưa phải xác nhận registry luật bởi chuyên gia.

Các helper [rules/obligations.py](../../agent1/rules/obligations.py) và [calendar_vn.py](../../agent1/calendar_vn.py) còn phục vụ sinh lịch/kiểm tra lịch sử. Tài liệu này không xác nhận hiệu lực pháp lý của các tỷ lệ/ngưỡng cũ; triển khai thật cần đối chiếu hồ sơ và quy tắc tại kỳ tương ứng.

## Phạm vi lịch chi

| Trạng thái tuần | Cách hiểu |
|---|---|
| `scheduled` | Có khoản và người dùng xác nhận đã rà đủ |
| `scheduled_unconfirmed` | Có khoản, chưa xác nhận đủ lịch |
| `confirmed_zero` | Người dùng đã rà và xác nhận không có khoản |
| `unknown` | Chưa đủ cơ sở kết luận về chi tuần đó |

Có vài khoản trong tuần không chứng minh đã nạp đủ chi. T6 lưu phạm vi cùng kế hoạch và nêu phần chưa xác nhận.

## Ước lượng hoạt động tùy chọn

Khi bật và có learner hợp lệ, hoạt động thêm bán thu ngay và **phần chi biến đổi bổ sung** từ lịch sử sao kê đã đối chiếu. Phải cùng tập tài khoản, đủ lịch sử và fit/ready không sau cutoff. API/worker/job mặc định không bật nhánh thu hóa đơn mới; các mô hình T4/Chronos nghiên cứu không tự trở thành nhánh production.

Learner hoạt động hiện dự báo tối đa **13 tuần** dù kỳ kế hoạch có thể dài tới 52; tuần xa phải đọc đúng phạm vi. Chỉ dự báo AR/T5 khi tắt hoạt động. Bật nhưng không đủ learner/history/scope thì báo lỗi, không tạo số ước lượng giả.

Kỳ vọng hoạt động lấy từ chính hỗn hợp residual hữu hạn dùng trong Monte Carlo, sau chặn âm và trừ lịch chi biến đổi đã biết. Không lấy point estimate thay kỳ vọng. Dời một khoản chi vẫn dùng lịch gốc để tính phần top-up, chỉ chuyển khoản được chọn; không bù lại ở tuần cũ hoặc xóa phần chi khác ở tuần nhận.

`operating.version` băm model, residual, scope và credit nếu có; forecast/T10 lưu cùng identity. Không gộp sai số hiệu chỉnh của các operating khác nhau. Xem [T6](T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md) cho tổng hợp và [Evaluation](../03_Evaluation/01_metric_ky_thuat.md) cho cách chấm.
