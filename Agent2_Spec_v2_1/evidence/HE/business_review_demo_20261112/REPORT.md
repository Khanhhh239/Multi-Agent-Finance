# CR-039 — Phiếu rà nghiệp vụ thử C001/C002

**Đã chuẩn bị, READY_FOR_REVIEW phần luồng thử. Chưa có người thật rà: 0/10 phiếu.** Không xác nhận hiệu quả nghiệp vụ hoặc tự tạo kết luận/hữu ích/thời gian thực tế.

Mở [10 phiếu trống](packet/BAT_DAU_RÀ_NGHIỆP_VỤ.html). Đây là **tệp HTML offline riêng tại DN, chưa tích hợp vào Portal**. [Hướng dẫn và ví dụ cách ghi](../../../../agent2/docs/HE_BUSINESS_REVIEW_DEMO.md). [Packet](packet/packet.json), [tổng hợp ban đầu](packet/summary.empty.json), [ảnh màn hình trống](browser/01-blank.png).

## Đã xây

- Mỗi DN 5 phiếu theo thứ tự T0 → T2 → T4 → T1 → T3, dùng đúng snapshot/model/first HE trial của báo cáo so sánh CR-038. Không fit, chạy chấm mới, sửa feature hoặc thay thứ tự sau xem kết quả rà.
- Mỗi phiếu có câu hỏi cần giải quyết, lý do ưu tiên tương đối, số tiền/ngày, các bản ghi kế toán/hóa đơn/phân bổ/NCC/nhân viên liên quan và tài liệu cần yêu cầu. Dùng nguồn từ frame evidence đã biết tại cutoff mỗi giao dịch; không tự ghép nguồn biết muộn. Bản ghi có checksum; nguồn mô phỏng luôn được phân biệt với chứng từ gốc đã xác minh.
- Bộ hiện có 0 approval và 0 supporting_document, nên phiếu nêu rõ thiếu nguồn, không suy có phê duyệt hoặc đủ hồ sơ. Chưa có tài liệu để kết luận là hợp lệ hoặc sai phạm chỉ từ số tiền/điểm.
- Ba kết quả Có vấn đề cần xử lý / Không phát hiện vấn đề / Chưa đủ căn cứ. Giải thích/căn cứ/hành động rõ, hữu ích Có/Không/Chưa đánh giá tách riêng. Chọn hữu ích cần hành động; Chưa đủ căn cứ cần nêu tài liệu thiếu và bước tiếp. Kết luận cần khai báo đối chiếu và nguồn tham chiếu, nhưng bản thử không xác minh khai báo đó.
- Đồng hồ active time trình duyệt tạm dừng khi ẩn thẻ, đổi phiếu hoặc tải lại. Tên người rà và thời gian đều tự khai/chưa xác minh; không gọi là thời gian thực tế đã được máy chủ xác nhận. LocalStorage chỉ hỗ trợ thử luồng, xuất JSON để giữ bản sao; không giới thiệu là kho audit production.
- Lưu/sửa tạo revision, không đè bản cũ. Ghi phiếu khác không xóa phiếu không liên quan. Bộ tổng hợp merge exact duplicates, từ chối nội dung xung đột cùng case/revision, mất lịch sử revision, case khác packet, dẫn nguồn ngoài manifest/của DN khác, cờ giả thời gian server hoặc nhãn train.
- Thống kê tách chưa rà/chưa đủ căn cứ/chưa đánh giá lợi ích; không đổi unknown thành 0%. Tỷ lệ hữu ích chỉ theo khai báo Có+Không; nếu chưa có thì null. Không có baseline luật cùng ngân sách nên lợi ích tăng thêm của ML là null. Mọi đầu ra có business_effectiveness_verified=false, training_eligible=false và không đề xuất mở rộng feature.

Tệp HTML chứa cả hai DN mô phỏng và không thực thi phân quyền Portal. Không cần tài khoản mới hoặc token; không thêm endpoint, quyền hoặc đụng tới phiên người dùng hiện tại. Đánh giá thật cần luồng được phân quyền/lưu phía server, tài liệu gốc và người có thẩm quyền; không lấy kiểm thử prototype làm nghiệm thu R4.

## Kiểm chứng

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Validator/tổng hợp phản hồi | 13 tests pass | [Log](focused_tests.log), [execution](focused_execution.json) |
| Chrome headless, tệp thật | 10 checks pass, không lỗi JS | [Browser summary](browser/summary.json) |
| CLI nhận feedback trống | 0 người rà, trạng thái awaiting_human_review; unknown giữ null | [CLI summary](empty_cli/summary.json) |
| Builder trên nguồn hiện có | 3 checks đạt: không deserialize model, khóa model/feature/snapshot đúng, DB không đổi | [Builder validation](builder_validation.json) |

Browser test nhập các câu có chữ FIXTURE trong context tách biệt; kiểm lưu, bắt buộc hành động, hữu ích độc lập với kết quả, cửa sổ cũ lưu C002 vẫn giữ C001, reload/đồng hồ dừng, sửa revision 2 và export giữ ba revisions/hai phiếu. File export fixture chỉ ở thư mục tạm và tự dọn. **Không trộn các kết quả đó vào packet dành người dùng hoặc thống kê người thật.** 13 unit tests bao gồm giữ nguồn tương lai không hợp lệ ngay cả khi tính lại checksum, không nâng mô phỏng thành original verified và merge không mất phiếu.

Packet builder đọc metadata model và snapshot; không deserialize model hoặc cần khóa HE để tạo phiếu. Không đổi đường chạy Portal/native/model, không chạy lại toàn bộ HE/native regression và không cộng 13 tests vào kết quả full suite cũ. Các kiểm tra hiện chỉ nghiệm thu phần thêm mới.

## Phần còn lại

Người hiểu nghiệp vụ cần thực hiện lượt rà; dữ liệu mô phỏng chỉ kiểm luồng. Giữ hai feature hiện tại. HE-AC-01 về worker chết giữa compute vẫn OPEN. Chưa có bằng chứng doanh nghiệp thật, đối chứng luật cùng kỳ/ngân sách, precision/recall, thời gian rà đã xác minh hoặc phê duyệt mở rộng. R0–R6 và quyết định sản phẩm giữ nguyên, không tự ký DONE.
