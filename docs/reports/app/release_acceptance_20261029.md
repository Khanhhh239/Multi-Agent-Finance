# Nghiệm thu kỹ thuật bản app tích hợp — 29/10/2026

**Kết quả: đạt trong phạm vi mô phỏng đã kiểm tra.** Chạy lại đủ **39 mẫu / 73 giao dịch P2 / 17 luồng lịch sử**, Chrome desktop, viewport thực **360×800 và 390×844**, lỗi kết nối và khởi động lại. Sửa và kiểm tra lại ba lỗi giao diện phát hiện trong đợt này. Có **81 kiểm tra browser**, **173 test Python**, **104 kiểm tra JavaScript** và **68 kiểm tra API/dữ liệu/bằng chứng** đạt. Các nhóm kiểm tra có phần giao nhau, không cộng thành số tình huống độc lập.

Đây là nghiệm thu kỹ thuật do trợ lý thực hiện. Danh tính, quyết định, chứng từ tham chiếu và số phút nhập đều **mô phỏng**; **0 người rà độc lập, không có phút xử lý thực tế**, **0 tài khoản thật**, **0 thông báo ra ngoài**. Chưa thay thế nghiệm thu kế toán hoặc chứng minh lợi ích ML.

## Bản được kiểm tra

- Mã app hiện tại, gồm các bản sửa trong lượt này; nguồn là bản tích hợp `reports/integrated_rehearsal_20261028_v2/source/` và kết quả detector đã khóa cùng đợt.
- Database và các bản sao snapshot vận hành mới tại `.runtime/release_acceptance_20261029/workspace/`; **1.211 hồ sơ**, hai bộ 001/003, tám công ty. Không dùng database demo hoặc database tích hợp cũ để ghi thử.
- Bộ P2 lịch sử gồm 32 tình huống/73 giao dịch được đọc từ bộ đối chứng đã khóa; ghi chú UAT vào database mới. Đây là đối chứng hiển thị của snapshot P2 lịch sử, không được coi là lần chấm lại luật mới.
- Năm server chỉ bind loopback: 8841 kế toán viên, 8842 kế toán trưởng, 8843 giám đốc, 8844 chỉ đọc, 8845 kế toán viên giới hạn C001. Ba vai trò đầu được cấp phạm vi tám công ty **chỉ trong fixture QA** để đi đủ mẫu lịch sử; 8845 dùng kiểm tra từ chối truy cập hồ sơ công ty khác.
- Đồng hồ nghiệp vụ cố định `2026-10-29T10:00:00+07:00`. P2 UAT giữ đồng hồ ghi chú của dịch vụ riêng. Không diễn giải thời gian này thành công rà thật.
- IF giữ nguyên shadow; không huấn luyện, chấm lại train/calibration, đổi model, luật, ngân sách hoặc SLA.

## Ba lỗi đã sửa và tái kiểm tra

| Mã | Tái hiện trước sửa | Hành vi sau sửa / bằng chứng |
| --- | --- | --- |
| APP01 | Dừng server rồi gửi kết quả: hiện `Failed to fetch`; P2 cũng dùng lỗi mạng thô. | Thông báo tiếng Việt, giữ bản nháp, không tự gửi lại. Thử offline ở cả hai biểu mẫu, nối lại và gửi chủ động thành công. `browser/offline_before_fix.jpg`, `offline_fixed.json`. |
| APP02 | Restart đổi CSRF. Nút tải lại hồ sơ chỉ đọc lại case; bước admit vẫn dùng token cũ nên không mở lại được hồ sơ. | Khi nhận đúng lỗi phiên, chỉ nạp metadata bằng GET; không tự lặp POST. Nút tải lại luồng duyệt nạp metadata trước khi mở case. Browser đã thử bản nháp → phiên mới → gửi lại thành công, cùng nhánh P2. `restart_stale_session_before_fix.txt`, `restart_refreshed.txt`. |
| APP03 | Mất kết nối khi chạy giả lập thông báo: nút bị khóa sau lỗi, lỗi nằm ngoài hộp thoại đang mở. | Nút được mở lại trong `finally`; lỗi được hiện/focus ngay trong hộp thoại. Thử offline ở 360px, restart, nạp lại phiên và chạy lại thành công. `notifications_offline_before_fix.txt`, `notifications_offline_fixed_360.jpg`. |

Tệp sửa: `review_ui/app.js`, `review_ui/p2_controls.js`. Thêm 11 hồi quy lỗi mạng/phiên và một hồi quy hộp thông báo; bộ JavaScript cuối gồm 104 kiểm tra. Lỗi từ chối quyền vẫn được giữ nguyên, không bị tự nạp phiên hoặc tự thử lại.

Fixture QA cũng được chỉnh URL thông báo riêng cho từng cổng vai trò. Ban đầu cả năm cổng dùng cấu hình URL 8841; đây là sai cấu hình fixture, không phải lỗi thay đổi nội dung outbox. Bản xem trước đã mở đúng cổng của người đang xem; payload đã mô phỏng và lịch sử cũ được giữ.

## Ma trận 17 luồng lịch sử

| Luồng | Kết quả | Quan sát / bằng chứng |
| --- | --- | --- |
| WF01 — danh sách, bộ dữ liệu, lọc, phân trang | PASS | Đổi 001/003, lọc C003+A4 còn 31; trang 21–40; 40 suất ngày trước thao tác đóng hồ sơ. Bộ 003 còn 626 đang mở sau một kết luận đóng mô phỏng, không mất hồ sơ nguồn. `WF01_filters.json`, `checks.json`. |
| WF02 — mở mẫu, đổi giao dịch P2 | PASS | Đủ 39 mẫu, chọn riêng đủ 73 giao dịch P2; URL phản ánh đúng mẫu/giao dịch, không mở hồ sơ giả cho dòng không P2. `sample_results.json`, từng tệp `P2_*.json`. |
| WF03 — mạng lưới, zoom, nút/cạnh, kéo | PASS | Mở mạng lưới ở cả bảy hồ sơ lịch sử; thử zoom/reset, chọn nút giao dịch và cạnh Người lập, kéo nút và kéo nền, có ảnh trước/sau. `graph_*.jpg`, bảy tệp `A5_*.json`. |
| WF04 — tạo yêu cầu thiếu trường/hợp lệ | PASS | Validation bắt trường thiếu; tạo yêu cầu với chủ trì/hạn/lý do, người thực hiện lấy từ principal mô phỏng. `WF04_created.txt`. |
| WF05 — chặn chốt khi yêu cầu mở | PASS | Kế toán trưởng thử chốt hợp lệ, bị chặn; không có kết luận cuối được ghi. `WF05_open_gate.txt`. |
| WF06 — cần bổ sung khi còn yêu cầu | PASS | Kế toán viên gửi, kế toán trưởng kiểm tra kết quả thiếu bằng chứng; hồ sơ tiếp tục mở và cho rà bổ sung. `checks.json`, trạng thái API cuối của nhánh gap. |
| WF07 — nhận tài liệu và kiểm tra mã | PASS | Không có tham chiếu bị từ chối; mã SIM được giữ sau tải lại. `checks.json`, `state_information_request_events.json`. |
| WF08 — chặn sau nhận nhưng chưa rà | PASS | Đã nhận tài liệu chưa làm mất cổng chặn kết luận. `WF08_received_gate.txt`. |
| WF09 — xử lý yêu cầu rồi chốt hai cấp | PASS | Yêu cầu thứ nhất hủy có lý do; yêu cầu thứ hai nhận rồi rà lại; giám đốc khác người rà chốt mô phỏng, hồ sơ đóng và chỉ đọc. `WF09_requests_resolved.txt`, `WF09_final.txt`. |
| WF10 — reload, mở lại, back/forward | PASS | Case/P2 giữ URL và dữ liệu; back/forward khôi phục đúng lựa chọn; kết luận cuối giữ sau reload/restart. `final_case_replay.json`, `checks.json`, `restart_persistence.json`. |
| WF11 — hai tab cùng ghi bản cũ | PASS | Tab cũ bị từ chối sau trả/gửi lại; lý do stale không được ghi vào journal. Tải lại hồ sơ phục hồi biểu mẫu. `WF11_stale.txt`, `final_api_checks.json`. |
| WF12 — đổi phân công/hạn, mở lại, hủy | PASS | Chủ trì B, hạn mới; mở lại vẫn giữ mã chứng từ đã nhận; hủy có lý do và giữ lịch sử. `state_information_request_events.json`. |
| WF13 — tìm rỗng, mã sai, hồi phục | PASS | Thông báo tiếng Việt; mã sai không giữ bằng chứng hồ sơ cũ; mở hồ sơ hợp lệ được. `WF13_unknown.txt`, `checks.json`. |
| WF14 — validation/lưu UAT P2 | PASS | Bắt thiếu kết quả/người/lý do; đủ 32/32 ghi chú mô phỏng trên bản sau sửa. Không tính thành nghiệm thu kế toán. `final_api_checks.json`. |
| WF15 — lọc/xuất CSV/xung đột P2 | PASS | Tải CSV thực qua Chrome, đúng năm mẫu hạn mức; ghi chú stale bị từ chối. `WF15_limits_export.csv`, `WF15_stale.txt`. |
| WF16 — desktop và màn hình nhỏ | PASS | Đọc trực tiếp DOM xác nhận 360×800 và 390×844, không tràn ngang trang; gửi ở 360, chốt ở 390, kiểm tra P2, yêu cầu tài liệu, thông báo. `checks.json`, ảnh `*_360.jpg`/`*_390.jpg`. |
| WF17 — Email/Zalo giả lập | PASS | 174 job giả lập, 522 mốc lịch sử; lần preview lặp không thêm job/lần gửi/sự kiện. Giới hạn năm hồ sơ/công ty/ngày; link mở đúng case và cổng vai trò. Không gọi gửi thật. `notification_checks.json`, `final_api_checks.json`, `WF17_current_origin.txt`. |

## Lỗi kết nối, restart và tính toàn vẹn

Server QA được dừng/mở lại nhiều lần có chủ đích. Bản nháp chỉ được giữ khi biểu mẫu hiện tại còn mở; chọn nút có nhãn bỏ nội dung chưa gửi hoặc tải lại toàn trang vẫn bỏ bản nháp theo hành vi đã công bố. Không có cơ chế lưu nháp xuyên đóng tab được tuyên bố ở đây.

Một checkpoint restart đối chiếu toàn bộ dòng của sáu bảng: **12 sự kiện duyệt, 8 sự kiện tài liệu, 174 outbox job, 374 sự kiện gửi, 40 phân bổ thông báo, 1 admission**, tất cả giữ nguyên ngay sau startup. Các job đang chờ được hoàn tất khi chạy giả lập chủ động sau đó; lịch sử cuối là 522 mốc. Luồng responsive tạo thêm ba sự kiện duyệt, tổng cuối **15**. Không suy 374→522 thành gửi trùng.

API cuối kiểm tra thêm từ chối quyền: kế toán viên không chốt; kế toán trưởng không gửi bước đầu; anonymous không ghi hoặc đọc đích nhận thông báo; principal C001 không mở case C002. Chuỗi hash workflow/delivery, SQLite integrity và foreign keys đạt. Đây không phải kiểm toán bảo mật toàn hệ thống hoặc nghiệm thu đăng nhập thật.

**32 tệp detector được copy vào workspace QA giữ hash như baseline.** Kiểm tra bảo toàn tệp trước/sau nằm trong `protected_verification.json`; các thay đổi được phép chỉ gồm UI, test/fixture QA và tài liệu tiến độ. Model, nguồn, detector và báo cáo đã khóa giữ nguyên.

## Bằng chứng và giới hạn

[Artifact máy](../../../reports/release_acceptance_20261029/): `summary.json` và `workflow_results.csv` là kết quả tổng hợp; `commitment.json` khóa các tệp báo cáo và mã liên quan. `browser/checks.raw.json` giữ cả các lần assertion sai do đọc quá sớm/khác câu chữ; `checks.json` lấy lần xác nhận cuối của mỗi mã. Ba lỗi sản phẩm có bằng chứng trước/sau riêng ở trên.

Trong lần đầu, lệnh viewport tác động tab khác với tab đang đọc; đo được 1280px nên không tính là nghiệm thu hẹp. Dùng tab test riêng rồi áp kích thước đã đo đúng 360/390; lưu cả lần thử trong `viewport_attempts.json`. Sau kiểm tra đã reset viewport và đóng các tab phụ. Console không ghi lỗi JavaScript ở tab kết quả; thư viện đồ thị có cảnh báo custom wheel sensitivity, thao tác zoom/kéo đã được thử.

Chưa nghiệm thu Safari/Firefox, điện thoại vật lý, gửi–nhận Email/Zalo thật hoặc luồng đăng nhập thật. Những phần này không được đánh dấu hoàn thành. Lợi ích IF và thời điểm biết chứng từ vẫn là các việc mở riêng; lần này không dùng UAT mô phỏng để đóng chúng.

Fixture có thể mở lại bằng `python -X utf8 -B tests/release_acceptance_fixture.py serve` với môi trường Python của dự án. `prepare` chỉ tạo workspace mới, từ chối ghi đè workspace đã tồn tại. Không dùng fixture cấp danh tính mô phỏng làm máy chủ phát hành cho người dùng thật.
