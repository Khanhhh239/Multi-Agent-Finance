# WF02 / WF10 — nghiệm thu sau sửa BUG02 ngày 21/10/2026

**WF02: PASS. WF10: PASS.** Chọn A4 trong giao diện cập nhật URL thành `#scenario=003&case=RC_d3c7009ff2ea6dbf`; tải lại vẫn mở đúng A4, không quay về IR cũ. Đã kiểm tra trực tiếp trên Chrome tại bản nghiệm thu riêng 8771.

## Thay đổi

- `review_ui/app.js`: đồng bộ lựa chọn hồ sơ/bộ dữ liệu với URL; xử lý hash và Back/Forward; nạp đúng bộ ngay từ liên kết đầu vào. Xóa bằng chứng/form cũ trong lúc chuyển hồ sơ và bỏ qua phản hồi tải đã lỗi thời trước khi nhận hồ sơ.
- `review_ui/p2_controls.js`: đồng bộ mẫu/giao dịch P2 theo URL, thẻ, bộ chọn và lịch sử trình duyệt. Liên kết không ghi giao dịch được chuẩn hóa tại chỗ; giao dịch không tồn tại báo lỗi, không âm thầm chọn dòng khác. Khi bộ lọc loại mẫu đang chọn, URL không giữ mẫu cũ; mở liên kết mới xóa bộ lọc cũ để hiển thị đúng mẫu.
- Dùng History API để thao tác UI không tự kích hoạt tải lặp. Sự kiện hash/popstate trùng nhau không nạp/tiếp nhận hồ sơ hai lần. Không đổi rules, điểm hoặc nguồn khóa.

## Kết quả thao tác Chrome

| Kiểm tra | Kết quả / bằng chứng |
|---|---|
| IR cũ → chọn A4 trong danh sách | PASS; [URL và chi tiết](navigation_retest_20261021/WF10_UI_selected_A4.json) |
| Tải lại A4 | PASS; [bằng chứng cuối](navigation_retest_20261021/WF10_final_A4.json), [ảnh](navigation_retest_20261021/WF10_final_A4.jpg) |
| Back/Forward giữa IR và A4 | PASS; [Back](navigation_retest_20261021/WF10_back_IR.json), [Forward](navigation_retest_20261021/WF10_forward_A4.json) |
| Đổi bộ 003 → 001 | PASS; bỏ mã hồ sơ cũ khỏi URL và xóa chi tiết cũ; [bằng chứng](navigation_retest_20261021/WF02_scenario_switch.json) |
| Tải lại dữ liệu tài liệu/kết luận đã có | PASS; [tài liệu](navigation_retest_20261021/WF10_requests_reload.json), [kết luận](navigation_retest_20261021/WF10_feedback_reload.md) |
| 39 liên kết trên cùng các tab | PASS cho 32 P2 + 7 hồ sơ 001/003; [CSV từng mẫu](navigation_retest_20261021/navigation_samples.csv) |
| Đổi giao dịch P2 | Đã chọn đủ 73/73 dòng, đọc lựa chọn thực tế và URL; [tổng hợp](navigation_retest_20261021/p2_navigation_summary.json) |
| Thẻ P2 → chọn dòng → Back/Forward → tải lại | PASS; [các bước](navigation_retest_20261021/p2_workflow_steps.json), [tải lại](navigation_retest_20261021/P2_reload_transaction.json) |
| Mẫu bị bộ lọc loại / giao dịch trong URL không tồn tại | Không giữ form/mã mẫu cũ; Back hoặc chọn thẻ phục hồi đúng; [bằng chứng](navigation_retest_20261021/P2_filter_invalid_recovery.json), [xóa thông báo lỗi cũ](navigation_retest_20261021/P2_recovery_final.json) |

Mỗi dòng CSV có JSON nội dung UI, URL thực tế và ảnh riêng trong thư mục bằng chứng. Đây là kết quả điều hướng/giữ đúng mẫu; không phải nghiệm thu lại toàn bộ nội dung nghiệp vụ của 39 mẫu hoặc 17 luồng.

## Nhật ký và dữ liệu

[Đối chiếu trước](navigation_retest_20261021/journals_before.json) và [sau](navigation_retest_20261021/journals_after.json) bằng SQLite chỉ đọc / SHA256:

- **12 sự kiện yêu cầu tài liệu, 35 ghi chú UAT P2, 3 phản hồi kết luận** giữ nguyên cả số lượng lẫn checksum; không tạo bản ghi trùng do điều hướng hoặc tải lại.
- Hồ sơ vẫn 001=584, 003=627. Thông báo vẫn 48 tác vụ dry-run/simulated; không chạy luồng gửi hoặc tạo kết luận/tài liệu mới trong đợt này.
- **1.209/1.209 tệp nguồn/kết quả khóa giữ nguyên**. 005 chỉ băm SHA256 opaque, không parse/nạp/chấm/oracle. Trong 16 tệp UI/runtime của bản sau BUG01, chỉ `app.js` và `p2_controls.js` thay đổi.
- Kiểm tra 9 đối chứng không có hồ sơ: UI vẫn ghi engine không mở hồ sơ. Các hồ sơ P2 còn lại hiển thị đúng mã hồ sơ đã khóa; không tạo hồ sơ giả khi thử URL.

[Kết quả kiểm thử](navigation_retest_20261021/regression_tests.json): **46 kiểm tra đạt** gồm 22 bằng chứng/renderer, 13 luồng tài liệu/ghi nhận, 11 điều hướng. Các kiểm tra này dùng VM/DOM giả; bằng chứng Chrome ở bảng trên được thu riêng. [Tổng kiểm chứng](navigation_retest_20261021/verification.json).

## Lần lỗi tải được giữ trong biên bản

Có một lượt tải lại mẫu LIMIT_UNVERIFIED gặp `Failed to fetch`. Máy chủ vẫn chạy và health trả OK; đã tải lại đúng URL rồi thử lại thành công mẫu này cùng ba mẫu còn lại. Nguyên nhân lượt lỗi chưa được xác định; không coi đây là bằng chứng đã loại bỏ mọi lỗi kết nối. [Quan sát gốc](navigation_retest_20261021/transport_observation.json).

## Phạm vi hoàn tất

BUG02 liên quan WF02/WF10 đã sửa và kiểm tra lại. [Biên bản FAIL ban đầu](browser_acceptance_20261020/executed/report.md) được giữ nguyên để đối chiếu. BUG03 về câu lỗi Unknown case, BUG04 về URL thông báo, WF16 màn hình hẹp và nghiệm thu kế toán độc lập tiếp tục theo dõi riêng.

![Tải lại vẫn mở đúng hồ sơ A4](navigation_retest_20261021/WF10_final_A4.jpg)
