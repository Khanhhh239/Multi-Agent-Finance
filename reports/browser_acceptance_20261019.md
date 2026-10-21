# Nghiệm thu browser — 19/10/2026

Lần tiếp tục **20/10/2026**: đã khởi chạy lại web và kiểm tra sẵn sàng, nhưng vẫn chưa có trình duyệt kết nối; xem [biên bản mới](browser_acceptance_20261020.md). Các kết quả browser trong phiếu này tiếp tục để chờ, không tự chuyển thành đạt.

**Đang chờ trình duyệt kết nối; chưa nghiệm thu trực quan.** Người dùng chọn kết nối trình duyệt để trợ lý rà trực tiếp. Inventory công cụ trả `apps=[]`, `browsers=[]`; thử mở `iab` và `chrome` đều báo `Browser is not available`. Không thay bằng headless/fake DOM rồi ghi đạt browser.

Đã chuẩn bị [bản demo riêng tại cổng 8771](http://127.0.0.1:8771/), tích hợp [đối chứng P2](http://127.0.0.1:8771/p2-controls). [Cách chạy lại](../examples/browser_acceptance/README.md). Dữ liệu phục hồi nằm ở `.runtime/browser_acceptance_20261019/demo`, journal P2 mới ở `.runtime/browser_acceptance_20261019/p2_uat.sqlite3`. Các thao tác thử sau này chỉ tác động bản riêng. Thông báo dry-run, không có người nhận hoặc worker tự gửi.

## Phạm vi và phiếu

- [39 mục mở nhanh](browser_acceptance_20261019/samples.md): đủ 32 tình huống P2/73 giao dịch và 7 hồ sơ 001/003. Bộ 27 mẫu cũ có 20 P2 đã nằm trong bộ 32, không cộng thành 59 mục riêng biệt.
- [Phiếu kết quả từng mẫu](browser_acceptance_20261019/sample_results.csv), có ba trục giải thích/chứng từ còn thiếu/ưu tiên. **39/39 còn `pending_browser`**; các trường kết quả, người rà và bằng chứng chưa điền.
- [Checklist WF01–WF17](browser_acceptance_20261019/checklist.md), gồm đồ thị, bộ lọc, tạo → nhận → rà lại → kết luận, chặn kết luận khi chưa đủ tài liệu, tải lại, hai tab xung đột, lỗi nhập, xuất CSV và cửa sổ hẹp. **17/17 chưa rà**.
- [Nhật ký lỗi](browser_acceptance_20261019/issue_log.csv) mới có tiêu đề, chưa có phát hiện browser. Không có lỗi mới được tuyên bố đã sửa. RR01–RR03 và các phát hiện cũ cần quan sát lại, không tự chuyển thành đạt.
- [Hash phiên bản UI/server được đưa vào rà](browser_acceptance_20261019/ui_under_review.json).

## Kiểm tra sẵn sàng kỹ thuật

[HTTP preflight](browser_acceptance_20261019/http_preflight.json) xác nhận cả 39 endpoint chi tiết và 9 tài nguyên giao diện trả thành công; đủ 584 + 627 = 1.211 hồ sơ, 32 P2/73 giao dịch. Các trường hợp đối chứng khớp kỳ vọng kỹ thuật công bố, chưa phải nghiệm thu người dùng. Hash 1.209 tệp khóa không đổi; 005 chỉ băm opaque, không parse/nạp/chấm hoặc dùng oracle.

Không đổi code sản phẩm, rule/điểm/ngưỡng/model hoặc nguồn đã khóa trong bước chuẩn bị. Không chạy lại toàn bộ 646 kiểm thử cũ vì chưa sửa sản phẩm. Preflight chỉ đọc HTTP, không xác minh bố cục, sự kiện click, tương tác Cytoscape hay khả năng người dùng hiểu bằng chứng.

Nghiệm thu browser và kế toán độc lập đều chưa hoàn tất. RR09 về mức vượt 1 VND vẫn chờ chủ kiểm soát, giữ nguyên cấu hình. Khi có browser, thực hiện checklist trên bản riêng, lưu bằng chứng, sửa lỗi tái hiện được và rà lại trước khi cập nhật trạng thái.
