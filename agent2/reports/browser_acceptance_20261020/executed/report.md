# Nghiệm thu Chrome thực tế — 20/10/2026

**Giao diện 39 mẫu: 37 PASS, 2 FAIL. Luồng chức năng: 12 PASS, 4 FAIL, 1 BLOCKED (WF16: chưa quan sát được màn hình hẹp). Có 4 lỗi đang mở; chưa đủ điều kiện ký nghiệm thu cuối.**

Người rà: `ASSISTANT_BROWSER_SIM`, thao tác trực tiếp trên Chrome qua extension (browser 3). Thời gian từng mẫu ghi trong CSV; lượt lưu P2 cuối khoảng 09:11 giờ Việt Nam ngày 20/10/2026. Chưa thu thập số phiên bản Chrome. Nhãn “32/32 khớp tự động”, HTTP readiness và kiểm thử engine không được dùng để tự gán PASS.

## Phạm vi và môi trường

- Đã mở/quan sát địa chỉ người dùng yêu cầu ở **8765**. Đây là demo cũ, không có bộ P2 tích hợp. Không thực hiện thao tác ghi tại cổng này.
- Rà 39 mẫu và thao tác ghi trên [bản nghiệm thu riêng 8771](http://127.0.0.1:8771/) và [P2 riêng](http://127.0.0.1:8771/p2-controls), instance `BROWSER_ACCEPTANCE_20261019`. SQLite và journal nằm ở `.runtime/browser_acceptance_20261019/`.
- 32 tình huống P2, chọn đủ **73/73 giao dịch**; đọc giao dịch, chứng từ/liên kết, hàng đợi và lịch sử. Với 7 hồ sơ 001/003, mỗi hồ sơ đọc 5 phần và mở mạng lưới. Bộ 27 mẫu cũ là tập con của 39, không cộng thành 66 mẫu.
- Kết quả mẫu đánh giá nội dung hiển thị và giải thích trên màn hình rộng. URL/tải lại được đánh giá riêng ở WF02/WF10 và có lỗi, dù nội dung 7 hồ sơ dựng được.
- Đã lưu trực tiếp **32/32 ghi chú UAT P2: 30 Đạt, 2 Cần sửa**. Journal có 33 sự kiện vì FULL_BELOW lưu hai lần trong phép thử xung đột; không phải hai tình huống khác nhau.
- Khung thực tế quan sát: **1280×495** và **1440×900**. Override 390×844 không đổi kích thước đọc được. Người dùng đã báo thu hẹp, nhưng các tab điều khiển vẫn trả 1280/1440 px. **WF16 chưa được kiểm chứng ở màn hình hẹp**, không suy đây là lỗi responsive của sản phẩm. Đã yêu cầu reset override; lần gọi cuối không xác nhận được do tab gốc không còn sẵn sàng. Tab mới vẫn đo được 1280×495.

## Kết quả từng mẫu

[CSV đủ 39 dòng, gồm độ rõ ràng/bằng chứng/ưu tiên](../sample_results.csv). PASS trong bảng không chứng nhận giao dịch hợp lệ, gian lận, chất lượng trên dữ liệu thật hoặc nghiệm thu kế toán độc lập.

| Mẫu | Nội dung UI | Điều quan sát trực tiếp | Bằng chứng |
|---|---|---|---|
| P2_FULL_BELOW | PASS | Dưới mốc 5 triệu; không phát sinh P2, không mở hồ sơ giả; nhãn không có P2 không chứng nhận hợp lệ. | [Nội dung](evidence/P2_FULL_BELOW.json) · [Ảnh](evidence/P2_FULL_BELOW.jpg) |
| P2_FULL_EQUAL | PASS | Đúng mốc 5 triệu; P2 8 điểm, ưu tiên trung bình; yêu cầu đối chiếu chứng từ/VAT, không kết luận quyền khấu trừ. | [Nội dung](evidence/P2_FULL_EQUAL.json) · [Ảnh](evidence/P2_FULL_EQUAL.jpg) |
| P2_FULL_ABOVE | PASS | Trên mốc snapshot; P2 8 điểm, có căn cứ tổng hóa đơn và hàng đợi rà nghiệp vụ. | [Nội dung](evidence/P2_FULL_ABOVE.json) · [Ảnh](evidence/P2_FULL_ABOVE.jpg) |
| P2_OLD_BELOW | PASS | Ngày giao dịch dùng mốc lịch sử 20 triệu; dưới mốc không phát sinh P2. | [Nội dung](evidence/P2_OLD_BELOW.json) · [Ảnh](evidence/P2_OLD_BELOW.jpg) |
| P2_OLD_EQUAL | PASS | Đúng mốc lịch sử 20 triệu; P2 8 điểm, không áp mốc mới hồi tố. | [Nội dung](evidence/P2_OLD_EQUAL.json) · [Ảnh](evidence/P2_OLD_EQUAL.jpg) |
| P2_FULL_BANK | PASS | Trả qua ngân hàng; không tạo P2 chi tiền mặt hoặc hồ sơ giả. | [Nội dung](evidence/P2_FULL_BANK.json) · [Ảnh](evidence/P2_FULL_BANK.jpg) |
| P2_NO_INVOICE | PASS | Thiếu thông tin hóa đơn; P2 0 điểm, yêu cầu bổ sung bằng chứng mức thấp, không tự coi là rủi ro đã xác minh. | [Nội dung](evidence/P2_NO_INVOICE.json) · [Ảnh](evidence/P2_NO_INVOICE.jpg) |
| P2_NO_DATE | PASS | Chỉ rõ thiếu ngày hóa đơn; 0 điểm và tuyến bổ sung dữ kiện. | [Nội dung](evidence/P2_NO_DATE.json) · [Ảnh](evidence/P2_NO_DATE.jpg) |
| P2_NO_GROSS | FAIL | BUG01: Giao dịch & P2 ghi giá trị hóa đơn Chưa có thông tin và thiếu tổng tiền; Chứng từ & liên kết lại ghi Giá trị hóa đơn 0 ₫. Mong đợi giữ trạng thái chưa có thông tin, không thay null bằng số 0. | [Nội dung](evidence/P2_NO_GROSS.json) · [Ảnh](evidence/P2_NO_GROSS.jpg) |
| P2_NO_IDENTITY | PASS | Chỉ rõ thiếu mã/số hóa đơn; 0 điểm và yêu cầu bổ sung, có căn cứ trường thiếu. | [Nội dung](evidence/P2_NO_IDENTITY.json) · [Ảnh](evidence/P2_NO_IDENTITY.jpg) |
| P2_FUTURE_INVOICE | PASS | Hóa đơn chỉ có lúc 12h sau khoản chi 11h; được giải thích theo thời điểm biết, giữ 0 điểm thiếu bằng chứng. | [Nội dung](evidence/P2_FUTURE_INVOICE.json) · [Ảnh](evidence/P2_FUTURE_INVOICE.jpg) |
| P2_INSTALL_CASH | PASS | Đã chọn cả 2 đợt; phân biệt khoản trả từng đợt và tổng hóa đơn 12 triệu; mỗi dòng P2 8, điểm hồ sơ không cộng cơ học. | [Nội dung](evidence/P2_INSTALL_CASH.json) · [Ảnh](evidence/P2_INSTALL_CASH.jpg) |
| P2_INSTALL_SMALL | PASS | Đã chọn 2 đợt; tổng hóa đơn dưới mốc, không sinh P2 giả. | [Nội dung](evidence/P2_INSTALL_SMALL.json) · [Ảnh](evidence/P2_INSTALL_SMALL.jpg) |
| P2_INSTALL_MIXED | PASS | Đã chọn 2 đợt; dòng ngân hàng không P2, tiền mặt 1 triệu trên hóa đơn 20 triệu có P2 8; ngoại lệ A1 không tự miễn P2. | [Nội dung](evidence/P2_INSTALL_MIXED.json) · [Ảnh](evidence/P2_INSTALL_MIXED.jpg) |
| P2_INSTALL_SAME_TIME | PASS | Đã chọn 2 khoản cùng thời điểm; giữ riêng giao dịch và cùng hóa đơn, không mất dòng trong hàng đợi. | [Nội dung](evidence/P2_INSTALL_SAME_TIME.json) · [Ảnh](evidence/P2_INSTALL_SAME_TIME.jpg) |
| P2_INSTALL_GAP | PASS | Đã chọn 2 đợt; có tổng tiền nhưng thiếu ngày phát hành, vẫn 0 điểm thiếu bằng chứng. | [Nội dung](evidence/P2_INSTALL_GAP.json) · [Ảnh](evidence/P2_INSTALL_GAP.jpg) |
| P2_REFUND_FULL | PASS | Đã chọn chi gốc và hoàn đủ; liên kết và số ròng 0 rõ, hồ sơ chi gốc vẫn còn để rà. | [Nội dung](evidence/P2_REFUND_FULL.json) · [Ảnh](evidence/P2_REFUND_FULL.jpg) |
| P2_REFUND_PART | PASS | Đã chọn chi và hoàn một phần; số hoàn/số còn lại hiển thị, không tự đóng hồ sơ gốc. | [Nội dung](evidence/P2_REFUND_PART.json) · [Ảnh](evidence/P2_REFUND_PART.jpg) |
| P2_REFUND_BANK | PASS | Đã chọn chi và hoàn qua ngân hàng; không tạo P2 chi tiền mặt giả. | [Nội dung](evidence/P2_REFUND_BANK.json) · [Ảnh](evidence/P2_REFUND_BANK.jpg) |
| P2_REVERSAL_JOURNAL | PASS | Đã chọn chi và bút toán đảo; giải thích đảo sổ không đồng nghĩa đã thu hồi tiền, giữ bằng chứng gốc. | [Nội dung](evidence/P2_REVERSAL_JOURNAL.json) · [Ảnh](evidence/P2_REVERSAL_JOURNAL.jpg) |
| P2_RECEIPT_UNLINKED | PASS | Thu tiền chưa nối nguồn gốc được giải thích là khoản thu, không phải chi; cần đối chiếu liên kết, không tạo P2 giả. | [Nội dung](evidence/P2_RECEIPT_UNLINKED.json) · [Ảnh](evidence/P2_RECEIPT_UNLINKED.jpg) |
| P2_REFUND_MULTI | PASS | Đã chọn cả 3 giao dịch; hai lần hoàn riêng và tổng/số ròng rõ, bằng chứng chi gốc vẫn giữ. | [Nội dung](evidence/P2_REFUND_MULTI.json) · [Ảnh](evidence/P2_REFUND_MULTI.jpg) |
| P2_RECUR_SMALL | PASS | Đã chọn 3 kỳ tiền mặt nhỏ; dưới mốc không P2; lịch định kỳ không được trình bày là xác nhận hóa đơn. | [Nội dung](evidence/P2_RECUR_SMALL.json) · [Ảnh](evidence/P2_RECUR_SMALL.jpg) |
| P2_RECUR_BANK | PASS | Đã chọn 3 kỳ trả ngân hàng; không sinh P2 chi tiền mặt. | [Nội dung](evidence/P2_RECUR_BANK.json) · [Ảnh](evidence/P2_RECUR_BANK.jpg) |
| P2_RECUR_CASH | PASS | Đã chọn 3 kỳ; lịch đã duyệt không miễn P2 đối chiếu VAT; mỗi kỳ 8 điểm, ngữ cảnh điểm hồ sơ được giải thích. | [Nội dung](evidence/P2_RECUR_CASH.json) · [Ảnh](evidence/P2_RECUR_CASH.jpg) |
| P2_RECUR_GAP | PASS | Đã chọn 3 kỳ; hợp đồng định kỳ không thay thế hóa đơn thiếu; 0 điểm và yêu cầu chứng từ cụ thể. | [Nội dung](evidence/P2_RECUR_GAP.json) · [Ảnh](evidence/P2_RECUR_GAP.jpg) |
| P2_RECUR_A5 | FAIL | Đã chọn đủ 23 giao dịch. Dòng cuối A5 22/20 mẫu, ngưỡng 1 triệu, ngoại lệ lịch duyệt 3 triệu/as-of đúng. BUG01: dòng lịch sử AUDIT_0000 thiếu hóa đơn nhưng giải thích tổng hóa đơn đang có 0 ₫; mong đợi ghi chưa có thông tin. | [Nội dung](evidence/P2_RECUR_A5.json) · [Ảnh](evidence/P2_RECUR_A5.jpg) |
| P2_LIMIT_VERIFIED | PASS | Vượt hạn mức đã xác minh 2 triệu đúng 1 VND vẫn 14 điểm/Cao theo snapshot; RR09 chưa có phê duyệt, chỉ nghiệm thu hiện trạng kỹ thuật. | [Nội dung](evidence/P2_LIMIT_VERIFIED.json) · [Ảnh](evidence/P2_LIMIT_VERIFIED.jpg) |
| P2_LIMIT_UNVERIFIED | PASS | Chỉ có con số hạn mức, chưa xác minh; không nâng thành vi phạm đã xác minh, 0 điểm thiếu bằng chứng. | [Nội dung](evidence/P2_LIMIT_UNVERIFIED.json) · [Ảnh](evidence/P2_LIMIT_UNVERIFIED.jpg) |
| P2_LIMIT_FUTURE | PASS | Xác minh hạn mức sau thời điểm chi không dùng hồi tố; 0 điểm thiếu bằng chứng. | [Nội dung](evidence/P2_LIMIT_FUTURE.json) · [Ảnh](evidence/P2_LIMIT_FUTURE.jpg) |
| P2_LIMIT_EXPIRED | PASS | Hạn mức hết hiệu lực tại lúc chi không được coi đang hiệu lực; 0 điểm thiếu bằng chứng. | [Nội dung](evidence/P2_LIMIT_EXPIRED.json) · [Ảnh](evidence/P2_LIMIT_EXPIRED.jpg) |
| P2_LIMIT_FOREIGN | PASS | Nguồn USD và số VND chưa xác minh được phân biệt trong giao dịch và chứng từ; không so sánh ngoại tệ như VND đã xác minh. | [Nội dung](evidence/P2_LIMIT_FOREIGN.json) · [Ảnh](evidence/P2_LIMIT_FOREIGN.jpg) |
| A5_001_TX_3103d5f23fde8b1a6f | PASS | Đọc đủ 5 phần và mở mạng lưới 13 nút. C4 hiện nguồn nghỉ phép/thao tác; A5 dòng tiền 102.187.000 so với 69.986.200, 44/20 mẫu. Điểm C cao nhất 8 + A5 3 = 11, không cộng thêm C1 cơ học. | [Nội dung](evidence/CASE_RC_18adf5be97ee0e84.json) · [Ảnh](evidence/CASE_RC_18adf5be97ee0e84.jpg) |
| A5_001_TX_ac2d5e5d289dc9227b | PASS | Đọc đủ 5 phần và mở mạng lưới 8 nút. F1 hiện nguồn bút toán thủ công, lịch khóa sổ và trọng yếu/as-of. A5 chi phí ghi Nợ 56.693.000 so với 18.709.907,68, 52/20 mẫu; phân biệt trích trước với đã chi tiền. | [Nội dung](evidence/CASE_RC_963dc712d016c11d.json) · [Ảnh](evidence/CASE_RC_963dc712d016c11d.jpg) |
| A5_001_cold_information_request | PASS | Đọc đủ 5 phần và mở mạng lưới 8 nút. P2 thiếu bằng chứng, 0 điểm; A5 0/20 mẫu ghi rõ chưa đánh giá. Luồng tài liệu và kết luận SIM được thử riêng tại hồ sơ này; trạng thái cuối Chờ bổ sung, giữ đủ lịch sử. | [Nội dung](evidence/CASE_IR_30749635120c8936.json) · [Ảnh](evidence/CASE_IR_30749635120c8936.jpg) |
| A5_001_cold_operational | PASS | Đọc đủ 5 phần và mở mạng lưới 13 nút. C4 có nguồn nghỉ phép/thao tác; A5 dòng tiền 19/20 mẫu ghi rõ chưa có ngưỡng, không suy ra hợp lệ. | [Nội dung](evidence/CASE_RC_035196cd1b97a1e1.json) · [Ảnh](evidence/CASE_RC_035196cd1b97a1e1.jpg) |
| A5_003_TX_60bac87c93f578f6c3 | PASS | Đọc đủ 5 phần và mở mạng lưới 12 nút. E2 hiện nguồn chấm dứt hợp đồng và kỳ lương/dịch vụ sau nghỉ việc. A5 dòng tiền 31.815.000 so với 30.625.000, 168/20 mẫu. | [Nội dung](evidence/CASE_RC_b929346759d67338.json) · [Ảnh](evidence/CASE_RC_b929346759d67338.jpg) |
| A5_003_cold_information_request | PASS | Đọc đủ 5 phần và mở mạng lưới 8 nút. P2 0 điểm thiếu thông tin hóa đơn; A5 chi phí 0/20 mẫu ghi rõ thiếu mẫu. Yêu cầu tài liệu mô phỏng hiện hữu vẫn được giữ. | [Nội dung](evidence/CASE_IR_c39bd6eef7d31a7c.json) · [Ảnh](evidence/CASE_IR_c39bd6eef7d31a7c.jpg) |
| A5_003_cold_operational | PASS | Đọc đủ 5 phần và mở mạng lưới 8 nút. A4 window_days=null dựng được thẻ: kỳ 2024-01, 3 lần, liên kết 2 giao dịch ngữ cảnh. A5 chi phí 19/20 mẫu không có ngưỡng; kiểm tra kéo/zoom/chọn nút/cạnh. | [Nội dung](evidence/CASE_RC_d3c7009ff2ea6dbf.json) · [Ảnh](evidence/CASE_RC_d3c7009ff2ea6dbf.jpg) |

## Kết quả 17 luồng

[CSV kết quả luồng](workflow_results.csv). Các nhánh validation/xung đột đã được bấm gửi/lưu thực tế. WF10 lưu bền vững khi mở đúng URL PASS, nhưng mở lại hồ sơ vừa chọn trong UI FAIL.

| Luồng | Kết quả | Quan sát | Bằng chứng chính |
|---|---|---|---|
| WF01 · Danh sách, bộ dữ liệu, bộ lọc, phân trang | **PASS** | Đổi 001/003, tìm mã, lọc C003 + A4 được 31 hồ sơ; sang trang 21–40/627 rồi quay lại. Ưu tiên hôm nay 40 hồ sơ (5/công ty), bỏ chọn về 627. Lỗi đồng bộ URL được ghi riêng tại WF02/WF10. | [Nội dung](evidence/WF01_company_rule_filter.md) · [Ảnh](evidence/WF01_company_rule_filter.jpg) |
| WF02 · Mở mẫu và đổi giao dịch P2 | **FAIL** | Đã mở/đọc 39 mẫu qua UI và chọn đủ 73 giao dịch P2, không tạo hồ sơ giả cho dòng không P2. Đổi liên kết hash trong cùng tab không đổi chi tiết; chọn hồ sơ trong UI không cập nhật URL. Không xác nhận 39 liên kết đều hoạt động đúng. | [URL/chi tiết](evidence/BUG02_hash_navigation.json) |
| WF03 · Đồ thị, thu phóng, kéo, nút/cạnh | **PASS** | Mở/đóng mạng lưới cả 7 hồ sơ, mốc as-of và số nút đổi đúng hồ sơ. Đã bấm zoom ±/đặt lại sơ đồ hồ sơ; chọn nút giao dịch, nút nhân viên và cạnh SĐT thấy dữ kiện; kéo nút và kéo nền thấy vị trí đổi trên ảnh trước/sau. | [Trước kéo](evidence/WF03_drag_before.jpg) · [Sau kéo](evidence/WF03_drag_after.jpg) · [Sau dịch nền](evidence/WF03_pan_after.jpg) |
| WF04 · Tạo yêu cầu thiếu trường và hợp lệ | **PASS** | Form trống bị validation trình duyệt. Tạo DR_8de1b0933e214bff9b370f45fbc8d212 với owner SIM, hạn 21/10/2026 14:00 và lý do; hiện lịch sử, điểm vẫn 0. | [Nội dung](evidence/WF04_empty_create.md) · [Ảnh](evidence/WF04_empty_create.jpg) |
| WF05 · Chặn kết luận cuối khi còn yêu cầu mở | **PASS** | Thử Hợp lệ / báo động giả; bị chặn với thông báo còn yêu cầu mở/đã nhận, không thêm kết luận cuối. | [Nội dung](evidence/WF05_final_blocked_open.md) · [Ảnh](evidence/WF05_final_blocked_open.jpg) |
| WF06 · Lưu cần bổ sung khi yêu cầu còn mở | **PASS** | Lưu Cần bổ sung bằng chứng với lý do SIM; lịch sử có một phản hồi, hồ sơ Chờ bổ sung và 0 điểm. | [Nội dung](evidence/WF06_information_gap_saved.md) · [Ảnh](evidence/WF06_information_gap_saved.jpg) |
| WF07 · Nhận tài liệu có kiểm tra tham chiếu | **PASS** | Nhận không có mã bị báo Cần 1–20 tham chiếu chứng từ đã nhận. Sau nhập SIM_BROWSER_DOC_20261020, chuyển Đã nhận/chờ rà lại; tải lại vẫn có mã. | [Nội dung](evidence/WF07_missing_reference_actual.md) · [Ảnh](evidence/WF07_missing_reference_actual.jpg) |
| WF08 · Chặn kết luận sau nhận nhưng chưa rà | **PASS** | Thử kết luận cuối khi các yêu cầu đã nhận chưa rà; cổng tiếp tục chặn, không thêm kết luận cuối. | [Nội dung](evidence/WF08_final_blocked_received.md) · [Ảnh](evidence/WF08_final_blocked_received.jpg) |
| WF09 · Rà hết yêu cầu rồi kết luận mô phỏng | **PASS** | Rà yêu cầu đã nhận cũ, hủy có lý do yêu cầu thử mới; khi không còn open/received mới lưu được Xác nhận nghi vấn SIM. Sau thử xung đột, ghi lại Cần bổ sung; lịch sử giữ đủ 3 phản hồi. | [Nội dung](evidence/WF09_all_requests_resolved.md) · [Ảnh](evidence/WF09_all_requests_resolved.jpg) |
| WF10 · Tải lại và mở lại đúng hồ sơ | **FAIL** | Tải lại đúng URL hồ sơ thử sau tạo/nhận/rà/kết luận giữ đủ dữ liệu, không nhân bản. Tuy nhiên sau chọn A4 trong UI, URL còn IR cũ: tải lại đổi từ RC_d3c7009ff2ea6dbf sang IR_c39bd6eef7d31a7c. | [Nội dung](evidence/WF10_reload_after_create.md) · [Ảnh](evidence/WF10_reload_after_create.jpg) |
| WF11 · Hai tab lưu kết luận cũ | **PASS** | A lưu trước; B lưu phiên bản cũ bị báo Hồ sơ vừa có kết luận mới. Tải lại hồ sơ trước khi lưu. Không có phản hồi B trong lịch sử. | [Nội dung](evidence/WF11_feedback_conflict.md) · [Ảnh](evidence/WF11_feedback_conflict.jpg) |
| WF12 · Phân công, hạn, mở lại, hủy yêu cầu | **PASS** | Đổi owner sang SIM_BROWSER_OWNER_B và hạn 22/10 15:00; nhận rồi yêu cầu bổ sung tiếp giữ mã đã nhận; hủy có lý do giữ lịch sử. Điểm vẫn 0. | [Nội dung](evidence/WF12_assignment.md) · [Ảnh](evidence/WF12_assignment.jpg) |
| WF13 · Tìm rỗng, mã không tồn tại, hồi phục | **FAIL** | Tìm rỗng có thông báo tiếng Việt; làm mới/xóa tìm kiếm hồi phục. Mã hồ sơ không tồn tại hiển thị lỗi tiếng Anh thô có dấu nháy Unknown case; vẫn mở lại hồ sơ C4 qua danh sách được. | [Nội dung](evidence/WF13_empty_search.md) · [Ảnh](evidence/WF13_empty_search.jpg) |
| WF14 · Validation và lưu nhật ký P2 | **PASS** | Thiếu người/lý do bị validation bắt buộc; lưu FULL_BELOW có lý do SIM rồi tải lại còn lịch sử. Sau rà toàn bộ, đã lưu 32/32 tình huống, 30 Đạt và 2 Cần sửa; không ghi nhận là kế toán độc lập. | [Nội dung](evidence/WF14_missing_reason.md) · [Ảnh](evidence/WF14_missing_reason.jpg) |
| WF15 · Lọc P2, CSV, xung đột hai tab | **PASS** | Lọc Hạn mức nội bộ được 5 mẫu, bấm tải CSV thực tế và kiểm tra đủ 5 dòng đúng nhóm. Tab A lưu, B phiên bản cũ bị báo xung đột, không ghi đè. | [Nội dung](evidence/WF15_filtered_limits.md) · [Ảnh](evidence/WF15_filtered_limits.jpg) |
| WF16 · Màn hình rộng và hẹp | **BLOCKED** | Đã xem thực tế 1280×495 và 1440×900. Yêu cầu override 390×844 không đổi kích thước đọc được. Người dùng báo đã thu hẹp hai lần, nhưng các tab kiểm soát vẫn báo 1280/1440 px. Phần hẹp chưa có bằng chứng, chưa PASS, chưa xác định lỗi responsive của sản phẩm. | [Tệp](evidence/WF16_viewport_attempts.json) |
| WF17 · Thông báo Email/Zalo OA giả lập | **FAIL** | Mở hộp thông báo, nhãn GIẢ LẬP rõ; bấm Chạy luồng giả lập. 48 tác vụ có trạng thái simulated/dry_run, 0 live, 0 sent. Link trong cả Email/Zalo trỏ 8765 thay vì bản nghiệm thu 8771: sai cấu hình URL, chưa đạt luồng mở hồ sơ từ thông báo. | [Nội dung](evidence/WF17_dry_run.md) · [Ảnh](evidence/WF17_dry_run.jpg) |

## Lỗi có thể tái hiện, chưa sửa trong đợt này

### BUG01 — Thiếu tổng hóa đơn bị hiển thị là 0 đồng

- Mức ảnh hưởng: **medium**; trạng thái **OPEN**; mẫu/luồng: P2_NO_GROSS;P2_RECUR_A5, WF02.
- Bước tái hiện: 1. Mở /p2-controls và chọn NO_GROSS. 2. Đọc Giao dịch & P2. 3. Chuyển Chứng từ & liên kết. Nhánh thứ hai: chọn RECUR_A5, giao dịch AUDIT_0000.
- Mong đợi: Tổng hóa đơn chưa có thông tin phải được ghi rõ là thiếu/chưa có; không dùng 0 đồng làm căn cứ giải thích dưới ngưỡng.
- Thực tế: NO_GROSS: tab giao dịch ghi Chưa có thông tin nhưng tab chứng từ ghi 0 ₫. RECUR_A5/AUDIT_0000: ngày hóa đơn chưa có, câu giải thích ghi tổng hóa đơn đang có 0 ₫.
- Ảnh hưởng: Có thể khiến người đọc hiểu thiếu giá trị là hóa đơn giá trị 0. Điểm engine quan sát không đổi.
- Bằng chứng: [BUG01_NO_GROSS_document](evidence/BUG01_NO_GROSS_document.md) · [ảnh](evidence/BUG01_NO_GROSS_document.jpg); [BUG01_RECUR_A5_missing_zero_visible](evidence/BUG01_RECUR_A5_missing_zero_visible.md) · [ảnh](evidence/BUG01_RECUR_A5_missing_zero_visible.jpg); [P2_NO_GROSS.json](evidence/P2_NO_GROSS.json); [P2_RECUR_A5.json](evidence/P2_RECUR_A5.json).
- Kiểm tra sau sửa: **chưa thực hiện**, vì chưa sửa code/cấu hình sản phẩm trong đợt ghi nhận này.

### BUG02 — URL và hồ sơ đang mở không đồng bộ

- Mức ảnh hưởng: **high**; trạng thái **OPEN**; mẫu/luồng: 7 hồ sơ 001/003; tái hiện ở RC_d3c7009ff2ea6dbf và IR_c39bd6eef7d31a7c, WF02;WF10.
- Bước tái hiện: 1. Mở liên kết 003/IR_c39bd6eef7d31a7c. 2. Qua danh sách chọn RC_d3c7009ff2ea6dbf. 3. Kiểm tra URL vẫn là IR. 4. Tải lại. Nhánh khác: đổi hash sang hồ sơ khác trong cùng tab rồi đọc chi tiết.
- Mong đợi: Chọn hồ sơ cập nhật URL; thay hash mở đúng hồ sơ; tải lại giữ đúng hồ sơ vừa chọn.
- Thực tế: Hồ sơ A4 được mở nhưng URL vẫn IR. Tải lại chuyển từ A4 sang IR. Đổi hash trong cùng tab cũng không đổi chi tiết cho tới tải lại.
- Ảnh hưởng: Liên kết chia sẻ và tải lại có thể đưa người rà về hồ sơ khác với hồ sơ vừa đọc.
- Bằng chứng: [BUG02_hash_navigation.json](evidence/BUG02_hash_navigation.json); [BUG02_hash_navigation](evidence/BUG02_hash_navigation.md) · [ảnh](evidence/BUG02_hash_navigation.jpg); [BUG02_before_reload](evidence/BUG02_before_reload.md) · [ảnh](evidence/BUG02_before_reload.jpg); [BUG02_after_reload](evidence/BUG02_after_reload.md) · [ảnh](evidence/BUG02_after_reload.jpg); [BUG02_reload.json](evidence/BUG02_reload.json).
- Kiểm tra sau sửa: **chưa thực hiện**, vì chưa sửa code/cấu hình sản phẩm trong đợt ghi nhận này.

### BUG03 — Lỗi mã hồ sơ không tồn tại hiển thị tiếng Anh thô

- Mức ảnh hưởng: **low**; trạng thái **OPEN**; mẫu/luồng: SIM_CASE_DOES_NOT_EXIST, WF13.
- Bước tái hiện: 1. Mở tab mới /#scenario=001&case=SIM_CASE_DOES_NOT_EXIST. 2. Chờ tải. 3. Đọc thông báo. 4. Chọn một hồ sơ có thật để kiểm tra hồi phục.
- Mong đợi: Thông báo tiếng Việt dễ hiểu, ví dụ Không tìm thấy hồ sơ, kèm cách tiếp tục chọn hồ sơ hoặc làm mới.
- Thực tế: Thông báo chứa Unknown case bằng tiếng Anh kèm dấu nháy của lỗi nội bộ. Hồi phục bằng chọn hồ sơ khác vẫn hoạt động.
- Ảnh hưởng: Khó hiểu với người dùng kế toán; không quan sát thấy trang bị kẹt vĩnh viễn.
- Bằng chứng: [WF13_unknown_id](evidence/WF13_unknown_id.md) · [ảnh](evidence/WF13_unknown_id.jpg); [WF13_recovered](evidence/WF13_recovered.md) · [ảnh](evidence/WF13_recovered.jpg).
- Kiểm tra sau sửa: **chưa thực hiện**, vì chưa sửa code/cấu hình sản phẩm trong đợt ghi nhận này.

### BUG04 — Link thông báo của bản 8771 trỏ sang cổng 8765

- Mức ảnh hưởng: **medium_config**; trạng thái **OPEN**; mẫu/luồng: Thông báo dry-run 001, WF17.
- Bước tái hiện: 1. Mở bản nghiệm thu 8771. 2. Mở Thông báo. 3. Bấm Chạy luồng giả lập. 4. Đọc URL trong thông báo ưu tiên cao và tuần của Email/Zalo OA.
- Mong đợi: URL mở đúng instance/dataset đang chạy ở 8771 trong bản nghiệm thu.
- Thực tế: URL được dựng từ http://127.0.0.1:8765/. Cổng 8765 là demo khác, không có bộ P2 tích hợp.
- Ảnh hưởng: Thông báo có thể đưa người dùng sang dữ liệu/instance khác. Đây là lỗi cấu hình bản thử; trạng thái giả lập vẫn đúng.
- Bằng chứng: [WF17_dry_run](evidence/WF17_dry_run.md) · [ảnh](evidence/WF17_dry_run.jpg); [Đối chiếu SQLite](verification.json).
- Đối chiếu cấu hình: examples/browser_acceptance/run_demo.py không truyền case_url; sme_fraud/notifications.py mặc định case_url=http://127.0.0.1:8765/. Chưa sửa trong đợt nghiệm thu.
- Kiểm tra sau sửa: **chưa thực hiện**, vì chưa sửa code/cấu hình sản phẩm trong đợt ghi nhận này.

## Trạng thái sau thử và đối chiếu bổ trợ

- Hồ sơ thử `001/IR_30749635120c8936`: cuối cùng **Chờ bổ sung**, 0 điểm. Giữ 3 phản hồi SIM: cần bổ sung → xác nhận nghi vấn mô phỏng → cần bổ sung. Yêu cầu cũ đã rà; yêu cầu mới thử đã hủy có lý do. Mã SIM chỉ kiểm tra thao tác, không chứng minh tài liệu đã được xác minh.
- Thông báo: đã bấm chạy dry-run thực tế. SQLite ghi **48 tác vụ simulated**: 16 ưu tiên cao + 8 tuần cho mỗi kênh Email/Zalo; **0 tác vụ live, 0 sent**. Không cấu hình người nhận hoặc chạy worker gửi thật. Link sai cổng được giữ là BUG04.
- [Đối chiếu chỉ đọc](verification.json): **1.209/1.209 tệp khóa giữ nguyên**; 005 chỉ băm SHA256 opaque, không parse/nạp/chấm/oracle. **16 tệp UI/runtime** trùng hash trước khi rà Chrome. Tổng hồ sơ bản thử vẫn 001=584, 003=627.
- HTTP readiness, code và SQLite chỉ bổ trợ tính toàn vẹn/đối chiếu. Kết quả thao tác lấy từ ảnh và nội dung đọc trực tiếp trong Chrome. Không sửa code sản phẩm và không chạy lại toàn bộ test suite khi chưa có thay đổi code.
- Một số lần chụp toàn trang bị timeout hoặc cho ảnh nhỏ; đã tách lỗi công cụ khỏi lỗi sản phẩm, bổ sung ảnh viewport và nội dung DOM trực tiếp. RECUR_A5 có JSON đủ 23 lần chọn, ảnh riêng của nhánh lỗi và ảnh kết quả UAT cuối.

## Việc cần đóng trước nghiệm thu cuối

1. Sửa BUG02 đồng bộ URL/hồ sơ; kiểm tra lại đổi hồ sơ, đổi bộ, hash và tải lại trên cùng tab.
2. Sửa BUG01 giữ trạng thái thiếu số tiền; rà lại NO_GROSS và 22 dòng lịch sử RECUR_A5, bảo đảm rules/điểm không tự đổi.
3. Sửa thông báo Unknown case và cấu hình case_url của bản 8771; kiểm tra lại nhánh lỗi và link dry-run.
4. Hoàn tất phần màn hình hẹp WF16 khi công cụ quan sát được kích thước thực tế: form tài liệu/kết luận, bảng/nhãn, đồ thị và thông báo lỗi. Hiện phần này chưa PASS.
5. Kế toán độc lập tự rà và ký riêng. RR09 vượt 1 VND vẫn 14 điểm/Cao theo snapshot; chủ kiểm soát chưa chỉ định và tham số phân tầng chưa được phê duyệt. PASS kỹ thuật LIMIT_VERIFIED không phải phê duyệt chính sách.

## Ảnh kết quả đã lưu

![32 ghi chú P2 đã lưu, 2 mẫu cần sửa](evidence/P2_final_review_results.jpg)

![Nhật ký SIM giữ đủ lịch sử và trạng thái chờ bổ sung](evidence/WF_final_sim_journal.jpg)
