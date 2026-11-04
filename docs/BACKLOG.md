# Việc cần làm

Cập nhật tổng hợp **29/10/2026**. Danh sách này thay cho các bản tổng kết tiến độ cũ; [trạng thái đã kiểm chứng](STATUS.md) ghi rõ phần đã hoàn thành.

## Đã hoàn thành ngày 29/10/2026

- [Nghiệm thu app trước phát hành](reports/app/release_acceptance_20261029.md): đủ 39 mẫu/73 giao dịch P2/17 luồng lịch sử trên nguồn tích hợp, Chrome desktop/360/390, mất kết nối và restart. 81 kiểm tra browser, 173 test Python, 104 kiểm tra JavaScript, 68 kiểm tra API/dữ liệu/bằng chứng đạt.
- Sửa lỗi mạng tiếng Anh, khôi phục phiên cũ sau restart, nút thông báo bị khóa và lỗi bị che sau hộp thoại. Không tự gửi lại POST; giữ nguyên nguồn/model/detector, workspace test riêng, thông báo và số phút đều mô phỏng.

## Đã hoàn thành ngày 28/10/2026

- [Phân tích tồn đầu kỳ/công suất/SLA](reports/operations/baseline_sla_20261028.md): 22 cấu hình offline, tái hiện đúng bốn baseline, 63 test đạt. Tách đồng hồ tái rà cũ khỏi ngày đủ điều kiện, nợ SLA cũ, giới hạn suất/phút và công việc chờ chứng từ; chưa đổi chính sách. Đuôi chờ đủ điều kiện 20/26 ngày, mức cao nhất không chờ thêm ngày trong mô phỏng.
- [Bản tích hợp mới](reports/app/integrated_rehearsal_20261028.md): 41.082 giao dịch, luật/queue chấm mới, IF evaluation bằng model/ngưỡng đã khóa, 20 cấu hình discovery có guard, app và thông báo giả lập trong workspace riêng. Giữ 2.425 lượt baseline và 40 chứng từ IF ở cấu hình chính, không vượt ngân sách hoặc gây trễ thêm.
- Đọc đủ 1.211 detail và lưu hash từng phản hồi; 42 kiểm tra HTTP tích hợp, 208 test Python, 92 kiểm tra JavaScript đạt. Không thay nguồn, model, tài khoản thật hoặc snapshot cũ. Chưa xác nhận browser của lượt mới vì công cụ timeout.
- Profile chỉ đọc xác định nguồn hỗ trợ hồ sơ đang quét/giải mã lặp nhiều dòng; chưa sửa lõi để tối ưu trong lượt tích hợp này.

## Đã hoàn thành ngày 27/10/2026

- [Ma trận 35 mã luật](reports/rules/rule_test_matrix_20261027.md): bảy nhóm tình huống, 228 ô kiểm chứng và 17 ô không áp dụng có lý do. Bộ hồi quy 607 test đạt, gồm 169 test mới.
- Kiểm tra đường đi điểm → ưu tiên → hàng đợi → SLA, hồ sơ thiếu dữ liệu, hạn công suất và các tín hiệu chỉ làm ngữ cảnh/master. Chưa thay thế nghiệm thu browser.
- Sửa A6 đọc hoá đơn tương lai và T1/T2 dùng hồ sơ xoá nợ chưa có căn cứ khả dụng tại cutoff; giữ nguyên model, trọng số và ngưỡng.
- [Guard trì hoãn IF](reports/ml/if_delay_guard_20261027.md): giới hạn 0 ngày trễ thêm so với baseline, giảm quota IF theo sức chứa. Replay 20 cấu hình; cấu hình chính giữ 40 chứng từ IF và loại phần trễ baseline 26 ngày. 144 test liên quan đạt; IF tiếp tục shadow.
- [Giao diện nghiệp vụ hai cấp](reports/app/browser_workflow_20261027.md): đã sửa và chạy Chrome desktop/360px/390px; xem bằng chứng → kế toán viên gửi → kế toán trưởng/giám đốc chốt hoặc trả lại, bổ sung/gửi lại. 21 kiểm tra browser, 78 test máy chủ và 80 kiểm tra JavaScript đạt; danh tính và số phút đều mô phỏng.
- [Thông báo theo vai trò](reports/app/notification_roles_20261027.md): đã chốt sự kiện/người nhận, chống trùng, nhắc quá hạn và lịch sử gửi; 140 test Python, 92 kiểm tra JavaScript và 11 kiểm tra Chrome đạt. Không gửi thật.
- [Bộ dữ liệu C4/E2/F2/F3/F4](reports/rules/rule_branch_controls_20261027.md): 98 biến thể/2 seed, 206 giao dịch, 196/196 ca khớp; 708 test hồi quy đạt. Có ma trận chi tiết, CSV/cache, điểm/hard trigger/queue/SLA và 120 hồ sơ test đọc được trong app. Nghiệm thu nguồn thật vẫn mở.

## Việc tiếp theo

| Thứ tự | Công việc | Điều kiện hoàn thành |
| --- | --- | --- |
| 1 | Chuẩn hóa metric chờ và trạng thái đầu kỳ | Version hóa `eligible_from` cho từng lượt, giữ metric cũ để tái hiện; phân biệt nợ SLA trước kỳ với chờ sau đủ điều kiện. Cần nguồn về trạng thái đã rà/chờ chứng từ/chưa xử lý, lịch làm việc và phút thực tế trước khi chốt ngân sách; không tự đánh dấu tồn đã xong hoặc reset SLA. |
| 2 | Tối ưu nguồn hỗ trợ khi mở hồ sơ | Giảm quét/giải mã lặp trong `review_support.case_support`; đối chiếu phản hồi đầy đủ trên cùng snapshot, giữ đúng company/cutoff và cơ chế làm mới cache. Đo độ trễ không profiler, không dùng một probe để khẳng định P95/SLA. |
| 3 | Mở rộng trình duyệt/thiết bị khi cần phát hành | Đã hoàn tất 39 mẫu/17 luồng trên Chrome desktop và viewport 360/390 ở lượt 29/10. Phần chưa kiểm tra là trình duyệt khác và điện thoại vật lý. |
| 4 | Nghiệm thu gửi–nhận Email/Zalo thật | Phần kỹ thuật đã xong. Thực hiện khi có cấu hình kênh, tài khoản và người nhận thật được chỉ định; ghi nhận chấp nhận, nhận/đọc và lỗi thực tế riêng. |
| 5 | Hoàn thiện nguồn bằng chứng theo thời gian | Có thời điểm quan sát/revision từ hồ sơ có thể kiểm chứng; không đoán ngày để lấp thiếu dữ liệu. |
| 6 | Đánh giá lợi ích ML | Khi có người dùng thật: rà mù, người khác chốt, ghi hành động hữu ích và phút thực tế. Các gói/đợt trước giữ riêng; cần phiếu đúng nhánh và cutoff sau guard. |
| 7 | Nghiệm thu dữ liệu SME thật | Khóa mapping/coverage/tiêu chí, rồi nghiệm thu nguồn và từng rule theo quy trình. |

Luồng đăng nhập và cấp tài khoản thực tế **để sau theo lựa chọn của người dùng**. Khi thực hiện, nối danh tính được xác thực ở máy chủ vào [chính sách vai trò](../examples/review_roles/README.md).

Các bản sửa B4, B2, M01, M02, quan hệ hiện hành M03, phân tầng RR09 và các bản sửa A6/T1/T2 ngày 27/10 đã có biên bản kỹ thuật. Tiếp tục mở rộng ma trận khi có yêu cầu hoặc trường hợp mới; không suy từ ma trận hiện tại rằng mọi tổ hợp dữ liệu đã được kiểm chứng.
