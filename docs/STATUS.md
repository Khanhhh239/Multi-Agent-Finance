# Trạng thái dự án

Cập nhật **29/10/2026**: [nghiệm thu app tích hợp](reports/app/release_acceptance_20261029.md) đạt **39 mẫu / 73 giao dịch P2 / 17 luồng lịch sử**, Chrome desktop/360×800/390×844, mất kết nối và restart. Sửa ba lỗi mạng/phiên/hộp thông báo; **81 kiểm tra browser, 173 test Python, 104 kiểm tra JavaScript, 68 kiểm tra API/dữ liệu/bằng chứng** đạt. Workspace ghi thử riêng; mọi danh tính, kết luận và phút nhập đều mô phỏng, không gửi thật.

Bản tích hợp **28/10/2026** đã chạy trên **41.082 giao dịch**, nạp và đọc đủ **1.211 hồ sơ**, đạt **42 kiểm tra HTTP**, **208 test Python** và **92 kiểm tra JavaScript** ở lượt đó. Chấm luật/queue mới; IF chỉ chấm 11.811 dòng evaluation bằng model/ngưỡng v4 ngày 24/10, không huấn luyện lại. Hai mươi cấu hình discovery có guard đều giữ baseline và ngân sách. Lượt 29/10 đã bổ sung nghiệm thu browser trên nguồn tích hợp này; điểm chậm ở nguồn hỗ trợ hồ sơ vẫn là việc tối ưu riêng.

Đã bổ sung **audit tồn đọng/SLA**: tái hiện đúng bốn baseline, chạy **22 cấu hình offline và 63 test đạt**. Đồng hồ tái rà cũ gộp thời gian trước khi đủ điều kiện; đuôi chờ đủ điều kiện là 20/26 ngày ở mức thấp. Giả định tồn đầu kỳ và trần phút là các yếu tố chính trong mô phỏng; chưa đổi chính sách.

## Đã có

| Phần | Trạng thái |
| --- | --- |
| Nghiệm thu app 29/10 | Đủ 39 mẫu/17 luồng; thông báo lỗi tiếng Việt, giữ bản nháp khi lỗi mạng, nạp lại phiên sau restart mà không tự lặp POST; lỗi thông báo hiện trong hộp thoại và nút thử lại không bị khóa. 174 job giả lập, 522 mốc lịch sử, không trùng và giữ ngân sách; 32 tệp detector copy vào QA giữ hash. |
| Bản tích hợp 28/10 | Workspace mới `reports/integrated_rehearsal_20261028_v2/`: luật → graph/A5 → queue → IF shadow có guard → app hai cấp → thông báo giả lập. Kiểm tra đủ 1.211 detail bằng bốn tiến trình SQLite chỉ đọc, có hash từng phản hồi; luồng nghiệp vụ chạy HTTP trên cùng database test mới. Snapshot cũ giữ nguyên. |
| Phân tích tồn/SLA 28/10 | Workspace `reports/baseline_sla_20261028/`: tách tồn tại cutoff đầu kỳ, ngày đủ điều kiện từng lượt, giới hạn suất/phút, nợ SLA cũ và việc chờ chứng từ. FIFO/EDF có giữ suất bắt buộc chưa giảm đuôi chờ; không đề xuất đổi mặc định từ kết quả này. |
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

Biên bản chính: [tồn đọng/SLA](reports/operations/baseline_sla_20261028.md), [tích hợp 28/10](reports/app/integrated_rehearsal_20261028.md), [đối chứng năm luật](reports/rules/rule_branch_controls_20261027.md), [thông báo](reports/app/notification_roles_20261027.md), [giao diện hai cấp](reports/app/browser_workflow_20261027.md), [guard IF](reports/ml/if_delay_guard_20261027.md), [ma trận luật](reports/rules/rule_test_matrix_20261027.md), [RR09 và ML v4](../reports/rr09_ml_completion_20261024.md), [phân quyền](../reports/review_roles_20261024.md). Thí nghiệm guard 27/10 dùng baseline 24/10; bản tích hợp 28/10 đã chấm lại luật và queue, giữ riêng cả hai đợt.

## Còn mở

| Việc | Giới hạn hiện tại |
| --- | --- |
| Nguồn doanh nghiệp thật | F1/C4/E2/F2/F3/F4 đã có đối chứng mô phỏng; chưa được nghiệm thu trên nguồn SME thật. |
| Thời điểm biết chứng từ | Bốn cờ khả dụng bằng chứng vẫn chưa đủ căn cứ trên 41.082 dòng nguồn; feature tương ứng được che, không suy là không có chứng từ. |
| Năng lực và thời gian chờ | 21/27 ngày là đồng hồ tái rà cũ; audit đo max chờ đủ điều kiện 20/26 ngày, thuộc mức thấp. 32 lượt cao nhất được chọn ngay ngày đủ điều kiện. Trong 995 lượt chọn vào ngày sau SLA, 969 đã mang nợ trước đầu ngày đủ điều kiện; đây chưa phải SLA hoàn thành thật. Tồn đầu kỳ/lịch/phút xử lý thực tế cần được xác nhận trước khi chốt công suất. |
| Lợi ích ML | Chưa có phút thực tế hoặc kết luận độc lập. Gói 74 phiếu v4 có **0 lượt rà**, thuộc nhánh trước guard; không tự chuyển kết luận sang nghiên cứu mới. Gói 128 phiếu thuộc đợt cũ hơn. |
| Hiệu năng nguồn hỗ trợ | Probe detail chỉ đọc có profiler mất 3,441 giây, chủ yếu ở `review_support.case_support` quét/giải mã lặp nguồn. Chưa phải P95 hoặc SLA; cần tối ưu có đối chiếu đầy đủ phản hồi và công ty/cutoff. |
| Phạm vi browser mở rộng | Lượt 29/10 đã đạt 39 mẫu/17 luồng trên Chrome desktop và viewport 360/390. Chưa nghiệm thu trình duyệt khác hoặc điện thoại vật lý. |
| Email/Zalo | Chưa xác nhận gửi–nhận thật. |
| Tài khoản | Chưa tạo tài khoản/đăng nhập theo yêu cầu người dùng; quyền và điểm tích hợp đã chuẩn bị. |

Phân quyền không tự tạo kết quả rà độc lập. IF vẫn ở **shadow**, lợi ích vận hành chưa được chứng minh. Xem [readiness sau guard](../reports/if_delay_guard_20261027/readiness.json), [trạng thái gói rà cũ](../reports/review_roles_20261024/ml_role_validation/review_status.json) và [nghiệm thu nguồn thật](../reports/rule_source_acceptance.md).

## Ưu tiên tiếp theo

Bản tích hợp, nghiệm thu Chrome và audit tồn/SLA đã đạt phạm vi mô phỏng. Trước khi đổi ngân sách cần version hóa metric chờ và nhập đúng trạng thái đầu kỳ; chưa có bằng chứng nên đổi bộ chọn mặc định. Tiếp tục tối ưu nguồn hỗ trợ hồ sơ và hoàn thiện bằng chứng theo thời gian. Gửi–nhận thật chờ tài khoản/kênh; đăng nhập/tài khoản vẫn để sau theo lựa chọn của người dùng. Chi tiết trong [backlog](BACKLOG.md).
