# Danh sách mở nhanh — chưa nghiệm thu browser

39 mục riêng biệt = 32 tình huống P2 + 7 hồ sơ 001/003. 20 tình huống P2 thuộc bộ 27 mẫu cũ được dùng chung, không đếm thêm.

Mọi trạng thái khởi tạo là `pending_browser`; kết quả khớp tự động/API không được điền thành đạt browser.

| Mẫu | Thuộc 27 mẫu | Trọng tâm |
|---|---|---|
| [P2_FULL_BELOW](http://127.0.0.1:8771/p2-controls#control=FULL_BELOW) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_FULL_EQUAL](http://127.0.0.1:8771/p2-controls#control=FULL_EQUAL) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_FULL_ABOVE](http://127.0.0.1:8771/p2-controls#control=FULL_ABOVE) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_OLD_BELOW](http://127.0.0.1:8771/p2-controls#control=OLD_BELOW) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_OLD_EQUAL](http://127.0.0.1:8771/p2-controls#control=OLD_EQUAL) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_FULL_BANK](http://127.0.0.1:8771/p2-controls#control=FULL_BANK) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_NO_INVOICE](http://127.0.0.1:8771/p2-controls#control=NO_INVOICE) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_NO_DATE](http://127.0.0.1:8771/p2-controls#control=NO_DATE) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_NO_GROSS](http://127.0.0.1:8771/p2-controls#control=NO_GROSS) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_NO_IDENTITY](http://127.0.0.1:8771/p2-controls#control=NO_IDENTITY) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_FUTURE_INVOICE](http://127.0.0.1:8771/p2-controls#control=FUTURE_INVOICE) | yes | Phân biệt chi 11:00 với hóa đơn biết lúc 12:00; không dùng dữ kiện biết sau để xác nhận quá khứ. |
| [P2_INSTALL_CASH](http://127.0.0.1:8771/p2-controls#control=INSTALL_CASH) | yes | Khoản chi từng đợt so với tổng nghĩa vụ hóa đơn; không cộng nhầm hoặc coi metadata là bản gốc. |
| [P2_INSTALL_SMALL](http://127.0.0.1:8771/p2-controls#control=INSTALL_SMALL) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_INSTALL_MIXED](http://127.0.0.1:8771/p2-controls#control=INSTALL_MIXED) | yes | Tách tiền mặt/ngân hàng; căn cứ ngoại lệ A1/A5 và phê duyệt đúng phạm vi. |
| [P2_INSTALL_SAME_TIME](http://127.0.0.1:8771/p2-controls#control=INSTALL_SAME_TIME) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_INSTALL_GAP](http://127.0.0.1:8771/p2-controls#control=INSTALL_GAP) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_REFUND_FULL](http://127.0.0.1:8771/p2-controls#control=REFUND_FULL) | yes | Chi gốc và hoàn đủ cùng hiển thị; hoàn không tự xóa hit hoặc đóng hồ sơ gốc. |
| [P2_REFUND_PART](http://127.0.0.1:8771/p2-controls#control=REFUND_PART) | yes | Phân biệt số chi, số hoàn và số còn lại; giữ bằng chứng lịch sử. |
| [P2_REFUND_BANK](http://127.0.0.1:8771/p2-controls#control=REFUND_BANK) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_REVERSAL_JOURNAL](http://127.0.0.1:8771/p2-controls#control=REVERSAL_JOURNAL) | yes | Đảo bút toán không tự chứng minh đã nhận lại tiền. |
| [P2_RECEIPT_UNLINKED](http://127.0.0.1:8771/p2-controls#control=RECEIPT_UNLINKED) | yes | Không có P2 không đồng nghĩa hợp lệ; nêu lý do và tài liệu cần đối chiếu. |
| [P2_REFUND_MULTI](http://127.0.0.1:8771/p2-controls#control=REFUND_MULTI) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_RECUR_SMALL](http://127.0.0.1:8771/p2-controls#control=RECUR_SMALL) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_RECUR_BANK](http://127.0.0.1:8771/p2-controls#control=RECUR_BANK) | no | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_RECUR_CASH](http://127.0.0.1:8771/p2-controls#control=RECUR_CASH) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_RECUR_GAP](http://127.0.0.1:8771/p2-controls#control=RECUR_GAP) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_RECUR_A5](http://127.0.0.1:8771/p2-controls#control=RECUR_A5) | yes | Căn cứ định kỳ và ngoại lệ A5; không suy tín hiệu thống kê thành sai phạm. |
| [P2_LIMIT_VERIFIED](http://127.0.0.1:8771/p2-controls#control=LIMIT_VERIFIED) | yes | Giữ 14 điểm/cao với mức vượt 1 VND theo snapshot; RR09 vẫn chờ chủ kiểm soát. |
| [P2_LIMIT_UNVERIFIED](http://127.0.0.1:8771/p2-controls#control=LIMIT_UNVERIFIED) | yes | Đọc toàn bộ giao dịch, chứng từ, căn cứ điểm/không có P2 và tuyến hàng đợi; không suy thành hợp lệ. |
| [P2_LIMIT_FUTURE](http://127.0.0.1:8771/p2-controls#control=LIMIT_FUTURE) | yes | Xác minh hạn mức sau thời điểm chi không được trình bày như đã có lúc chi. |
| [P2_LIMIT_EXPIRED](http://127.0.0.1:8771/p2-controls#control=LIMIT_EXPIRED) | yes | Hiệu lực hạn mức tại thời điểm chi và tài liệu gia hạn nếu có. |
| [P2_LIMIT_FOREIGN](http://127.0.0.1:8771/p2-controls#control=LIMIT_FOREIGN) | yes | Cả giao dịch và sổ đều thể hiện VND chưa xác minh; không ngầm coi đã quy đổi. |
| [A5_001_TX_3103d5f23fde8b1a6f](http://127.0.0.1:8771/#scenario=001&case=RC_18adf5be97ee0e84) | yes | Hiển thị đủ căn cứ C4/E2/F1 và đóng góp A5 3 điểm, thống kê và nguồn; chưa kết luận gian lận. |
| [A5_001_TX_ac2d5e5d289dc9227b](http://127.0.0.1:8771/#scenario=001&case=RC_963dc712d016c11d) | yes | Hiển thị đủ căn cứ C4/E2/F1 và đóng góp A5 3 điểm, thống kê và nguồn; chưa kết luận gian lận. |
| [A5_001_cold_information_request](http://127.0.0.1:8771/#scenario=001&case=IR_30749635120c8936) | yes | Hiển thị thiếu mẫu, số mẫu thực tế và căn cứ độc lập; thiếu mẫu không đồng nghĩa hợp lệ. |
| [A5_001_cold_operational](http://127.0.0.1:8771/#scenario=001&case=RC_035196cd1b97a1e1) | yes | Hiển thị thiếu mẫu, số mẫu thực tế và căn cứ độc lập; thiếu mẫu không đồng nghĩa hợp lệ. |
| [A5_003_TX_60bac87c93f578f6c3](http://127.0.0.1:8771/#scenario=003&case=RC_b929346759d67338) | yes | Hiển thị đủ căn cứ C4/E2/F1 và đóng góp A5 3 điểm, thống kê và nguồn; chưa kết luận gian lận. |
| [A5_003_cold_information_request](http://127.0.0.1:8771/#scenario=003&case=IR_c39bd6eef7d31a7c) | yes | Hiển thị thiếu mẫu, số mẫu thực tế và căn cứ độc lập; thiếu mẫu không đồng nghĩa hợp lệ. |
| [A5_003_cold_operational](http://127.0.0.1:8771/#scenario=003&case=RC_d3c7009ff2ea6dbf) | yes | Hiển thị thiếu mẫu, số mẫu thực tế và căn cứ độc lập; thiếu mẫu không đồng nghĩa hợp lệ. Thẻ A4 có window_days=null phải dựng được. |
