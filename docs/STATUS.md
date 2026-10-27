# Trạng thái dự án

Cập nhật **27/10/2026**: đã bổ sung bộ đối chứng C4/E2/F2/F3/F4 với **206 giao dịch, 196/196 ca khớp và 708/708 test hồi quy đạt**. Guard trì hoãn IF, giao diện hai cấp và thông báo đã có biên bản kiểm chứng riêng. Model vẫn tham chiếu ngày **24/10/2026**; các đợt này không huấn luyện hoặc chấm lại model.

## Đã có

| Phần | Trạng thái |
| --- | --- |
| Luật và hàng đợi | Có rules + graph + A5, kiểm soát ngân sách và SLA. RR09 đã phân tầng ưu tiên theo mức vượt; giữ riêng điểm phát hiện và mức ưu tiên xử lý. |
| Ma trận kiểm thử luật | Đã đối chiếu 35 mã theo bảy nhóm tình huống: 228 ô có test đạt, 17 ô không áp dụng có lý do; kiểm tra cả ưu tiên, hàng đợi và SLA. Thêm 169 test mới, bộ hồi quy tổng 607 test đạt. |
| Đối chứng C4/E2/F2/F3/F4 | Năm luật đã có đủ bảy nhóm trước đó. Nay có 98 biến thể/2 seed, 196 ca khớp gồm 10 nguồn sai bị từ chối đúng; xuất CSV/cache riêng, kiểm tra điểm/hard trigger/queue/SLA và nạp app. Hồi quy mới 708 test đạt, gồm 101 test bổ sung. |
| Các lỗi gần nhất | Đã sửa B4 dùng bằng chứng tương lai để giảm cảnh báo, B2 giữ nhân viên ở công ty cũ, feature đọc dữ kiện sau cutoff, định danh rỗng và quan hệ master cũ. |
| Bản sửa ngày 27/10 | A6 loại hoá đơn có ngày phát hành/quan sát rõ ràng sau cutoff. T1/T2 chỉ dùng hồ sơ xoá nợ có căn cứ thời gian/phạm vi để miễn cảnh báo; header không có mốc thời gian cần bản writeoff nguồn đúng phạm vi đã biết. |
| ML | Feature contract v4, 194 feature; model mới tương thích và đã replay shadow. Train 2024, calibration nửa đầu 2025, evaluation nửa cuối 2025. |
| Giới hạn trì hoãn IF | Đã replay 20 cấu hình, giữ 0 ngày trễ thêm so với lịch baseline. Cấu hình chính giữ 2.425 lượt baseline và 40 chứng từ IF, 0 vượt ngân sách/mất suất bắt buộc. Quota IF giảm khi cần; thời gian chờ IF có thể tăng. |
| Rà hai cấp | Kế toán viên gửi kết quả; kế toán trưởng hoặc giám đốc khác người chốt/trả lại. Có kiểm soát công ty, phiên bản hồ sơ và nhật ký. |
| Giao diện nghiệp vụ | Đã kiểm tra bằng chứng → gửi → chốt/trả → bổ sung/gửi lại trên Chrome desktop, 360×800 và 390×844. Hiện lý do trả lại, căn cứ chốt, lịch sử và lỗi ngay tại biểu mẫu; nhánh thiếu bằng chứng vẫn cho rà bổ sung. |
| Thông báo theo vai trò | Đã hoàn thiện 10 loại sự kiện, người nhận theo công ty/vai trò, chống trùng, nhắc quá hạn và lịch sử gửi. 140 test Python, 92 kiểm tra JavaScript và 11 kiểm tra Chrome đạt; toàn bộ gửi thử là mô phỏng/mock. |
| Vận hành | Có backup/restore, quy trình phát hành, outbox và adapter thông báo. Gửi thông báo vẫn giả lập. |

Biên bản chính: [đối chứng năm luật](reports/rules/rule_branch_controls_20261027.md), [thông báo](reports/app/notification_roles_20261027.md), [giao diện hai cấp](reports/app/browser_workflow_20261027.md), [guard IF](reports/ml/if_delay_guard_20261027.md), [ma trận luật](reports/rules/rule_test_matrix_20261027.md), [RR09 và ML v4](../reports/rr09_ml_completion_20261024.md), [phân quyền](../reports/review_roles_20261024.md). Snapshot cũ giữ nguyên; thí nghiệm guard dùng đúng baseline ngày 24/10 để đo riêng tác động thay lịch.

## Còn mở

| Việc | Giới hạn hiện tại |
| --- | --- |
| Nguồn doanh nghiệp thật | F1/C4/E2/F2/F3/F4 đã có đối chứng mô phỏng; chưa được nghiệm thu trên nguồn SME thật. |
| Thời điểm biết chứng từ | Bốn cờ khả dụng bằng chứng vẫn chưa đủ căn cứ trên 41.082 dòng nguồn; feature tương ứng được che, không suy là không có chứng từ. |
| Năng lực và thời gian chờ | Guard chỉ chặn phần trễ IF gây thêm. Baseline trong mô phỏng vẫn có thời gian chờ tối đa 21/27 ngày và một số SLA lịch sử quá hạn; IF có thể chờ lâu hơn. |
| Lợi ích ML | Chưa có phút thực tế hoặc kết luận độc lập. Gói 74 phiếu v4 có **0 lượt rà**, thuộc nhánh trước guard; không tự chuyển kết luận sang nghiên cứu mới. Gói 128 phiếu thuộc đợt cũ hơn. |
| Phạm vi browser mở rộng | Luồng hai cấp và viewport hẹp đã được kiểm chứng bằng browser. Chưa chạy lại toàn bộ 39 mẫu/17 luồng lịch sử hoặc nghiệm thu trình duyệt khác/điện thoại thật. |
| Email/Zalo | Chưa xác nhận gửi–nhận thật. |
| Tài khoản | Chưa tạo tài khoản/đăng nhập theo yêu cầu người dùng; quyền và điểm tích hợp đã chuẩn bị. |

Phân quyền không tự tạo kết quả rà độc lập. IF vẫn ở **shadow**, lợi ích vận hành chưa được chứng minh. Xem [readiness sau guard](../reports/if_delay_guard_20261027/readiness.json), [trạng thái gói rà cũ](../reports/review_roles_20261024/ml_role_validation/review_status.json) và [nghiệm thu nguồn thật](../reports/rule_source_acceptance.md).

## Ưu tiên tiếp theo

Thông báo đã hoàn thiện phần kỹ thuật/mô phỏng; gửi–nhận thật chờ tài khoản và cấu hình kênh. Tiếp theo mở rộng nghiệm thu browser trước phát hành và hoàn thiện nguồn bằng chứng theo thời gian. Đăng nhập/tài khoản vẫn để sau theo lựa chọn của người dùng; theo dõi riêng thời hạn thử nghiệm ML. Chi tiết trong [backlog](BACKLOG.md).
