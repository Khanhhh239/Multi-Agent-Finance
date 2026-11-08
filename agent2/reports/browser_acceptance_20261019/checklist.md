# Checklist nghiệm thu trình duyệt

Trạng thái khởi tạo: **chưa thực hiện trên browser**. Mọi mục bên dưới còn chờ; HTTP, unit test hoặc dựng HTML bằng DOM giả không đóng được mục nghiệm thu trực quan.

Mở [bản nghiệm thu riêng](http://127.0.0.1:8771/) và [32 đối chứng P2](http://127.0.0.1:8771/p2-controls). [39 đường dẫn mẫu](samples.md); điền kết quả vào `sample_results.csv`. Bộ 27 mẫu ban đầu gồm 20 P2 trong bộ 32 và 7 hồ sơ 001/003. Không tính thành 59 mẫu độc lập.

Ghi người rà, thời gian, phiên bản browser, điều quan sát được và mã bằng chứng. Trợ lý dùng tên `ASSISTANT_BROWSER_SIM`; kết luận thử phải ghi `SIM_BROWSER_UAT`, không nhận là nghiệm thu kế toán độc lập. Người kế toán ký phiếu riêng sau khi tự rà.

## A. Đọc từng mẫu

Với đủ 32 P2, chọn lần lượt **mọi giao dịch** (tổng 73, gồm 23 dòng của RECUR_A5), đọc Giao dịch / Chứng từ / Hàng đợi / Lịch sử. Đánh giá trên ba trục: giải thích có hiểu được không, còn thiếu chứng từ nào, mức ưu tiên có căn cứ không. Phần kỳ vọng đã công bố là tài liệu đối chiếu; đây không phải đánh giá mù hay đo precision.

Với 7 hồ sơ 001/003, đọc Tổng quan / Giao dịch / Bằng chứng / Bổ sung tài liệu / Lịch sử. Kiểm tra A4 null, nguồn C4/E2/F1, 3 A5 mới có điểm và 4 hồ sơ thiếu mẫu. Mở sơ đồ bằng chứng và mạng lưới, kéo/thu phóng/chọn nút hoặc cạnh, đọc thông tin trả về; đóng/mở lại không giữ nhầm sơ đồ hồ sơ trước. Không suy thiếu mẫu, không có P2 hoặc đã nhận tài liệu thành hợp lệ.

RR09 giữ nguyên 14 điểm/cao cho LIMIT_VERIFIED; chỉ ghi nhận quyết định nghiệp vụ còn chờ, không tự thêm dung sai. LIMIT_FOREIGN phải nhất quán “VND chưa xác minh” ở cả giao dịch và sổ.

## B. Luồng thao tác và lỗi

Mỗi dòng cần ghi `chưa rà / đạt / lỗi / chặn bởi chính sách`, bằng chứng và người rà. Các điều mong đợi sau đây là tiêu chí, chưa phải kết quả quan sát.

| Mã | Thao tác | Điều mong đợi | Kết quả khởi tạo |
|---|---|---|---|
| WF01 | Mở danh sách, tìm mã, đổi bộ/lọc/trang, xóa tìm kiếm | Dữ liệu và chi tiết đúng bộ, không giữ nhầm hồ sơ; hiểu khác biệt ưu tiên hôm nay với toàn bộ | Chưa rà |
| WF02 | Mở cả 39 liên kết, đổi giao dịch P2 | Đúng mẫu và đủ 73 giao dịch; không tạo hồ sơ giả cho dòng không có P2 | Chưa rà |
| WF03 | Mở/đóng sơ đồ, kéo, zoom, chọn nút/cạnh | Sơ đồ có kích thước đọc được, hiện thông tin, không lẫn công ty/hồ sơ | Chưa rà |
| WF04 | Tạo yêu cầu thiếu trường; sau đó tạo hợp lệ với hạn tương lai | Lỗi rõ ràng; tạo hợp lệ có người phụ trách, hạn, lý do và lịch sử; điểm giữ nguyên | Chưa rà |
| WF05 | Khi yêu cầu còn mở, thử kết luận cuối | Bị chặn có lý do; không thêm kết luận cuối vào lịch sử | Chưa rà |
| WF06 | Khi còn mở, lưu “Cần bổ sung bằng chứng” | Lưu được, hồ sơ tiếp tục mở, không coi là giao dịch hợp lệ | Chưa rà |
| WF07 | Chọn nhận tài liệu không có mã; rồi nhận với mã SIM | Không nhận thiếu tham chiếu; nhận hợp lệ chuyển “Đã nhận · chờ rà lại” | Chưa rà |
| WF08 | Thử kết luận cuối sau nhận nhưng trước rà lại | Vẫn bị chặn; nhận không đồng nghĩa đã đối chiếu | Chưa rà |
| WF09 | Rà lại tất cả yêu cầu hiện hành rồi lưu kết luận SIM có lý do | Chỉ cho kết luận khi không còn open/received; giữ đủ lịch sử | Chưa rà |
| WF10 | Tải lại trang sau tạo/nhận/rà/kết luận và mở lại đúng hồ sơ | Dữ liệu đã lưu còn đủ, không tạo bản ghi trùng, thể hiện đúng trạng thái | Chưa rà |
| WF11 | Hai tab cùng hồ sơ, tab A lưu rồi tab B lưu bản cũ | Tab B báo xung đột, không ghi đè im lặng; tải lại rồi đối chiếu | Chưa rà |
| WF12 | Hủy có lý do / yêu cầu bổ sung tiếp / đổi người hoặc hạn | Luồng trạng thái đúng, giữ lịch sử cũ; hạn không tự đổi điểm rủi ro | Chưa rà |
| WF13 | Mã hồ sơ không tồn tại, tìm không có kết quả, làm mới | Hiện lỗi hoặc trạng thái rỗng dễ hiểu, tiếp tục mở hồ sơ khác được | Chưa rà |
| WF14 | Lưu ghi chú P2 thiếu người/lý do; lưu hợp lệ rồi tải lại | Kiểm tra trường bắt buộc, lưu đúng tình huống và còn lịch sử; không phải kết luận vận hành | Chưa rà |
| WF15 | Lọc P2, xuất CSV; thử hai tab P2 ghi bản cũ | CSV khớp bộ lọc; xung đột được báo và không ghi đè lịch sử | Chưa rà |
| WF16 | Xem trang ở cửa sổ rộng và hẹp | Đọc được trường/nhãn, tab, sơ đồ và nút; không bị che phần kết luận hoặc thông báo lỗi | Chưa rà |
| WF17 | Mở Thông báo; nếu chạy xem trước thì chỉ dry-run | Nhãn giả lập rõ, không có người nhận hay gửi ra ngoài | Chưa rà |

Luồng WF04–WF12 làm trên [hồ sơ 001](http://127.0.0.1:8771/#scenario=001&case=IR_30749635120c8936) của bản riêng. Hồ sơ đã có một yêu cầu mô phỏng nhận nhưng chưa rà; muốn kết luận phải xử lý tất cả yêu cầu hiện hành, không chỉ yêu cầu mới. Tài liệu tham chiếu SIM chỉ để thử thao tác, không chứng minh nội dung tài liệu đã được xác minh.

## C. Ghi lỗi và rà lại

`issue_log.csv` ghi bước tái hiện, mong đợi/thực tế, mức ảnh hưởng, mẫu liên quan, tham chiếu bằng chứng, thay đổi và kết quả rà lại. Không biến các phát hiện RR cũ thành lỗi tái hiện trên browser khi chưa quan sát được.

Nghiệm thu kỹ thuật kết thúc khi đủ 39 mục và WF01–WF17 được rà, lỗi cản trở đã sửa và kiểm tra lại, không có nhầm bằng chứng/đơn vị hoặc vượt cổng kết luận, hash nguồn khóa còn nguyên. Nghiệm thu kế toán độc lập cần người có nghiệp vụ ký riêng; RR09 còn chờ phải được ghi ngoại lệ rõ ràng.
