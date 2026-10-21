# Nghiệm thu trình duyệt — tiếp tục ngày 20/10/2026

**Chưa thực hiện được nghiệm thu trực quan: công cụ chưa có trình duyệt kết nối.** Hai lần kiểm tra inventory đều trả `apps=[]`, `browsers=[]`; thử mở bản nghiệm thu bằng `iab` và `chrome` lần lượt báo `Browser is not available: iab` và `Browser is not available: chrome`. Không có thao tác bấm, ảnh chụp hoặc kết quả browser để ghi đạt. Đây là hạn chế kết nối công cụ, chưa phải lỗi được tái hiện của sản phẩm.

Đã khởi chạy lại [bản web riêng](http://127.0.0.1:8771/) và [đối chứng P2](http://127.0.0.1:8771/p2-controls), dùng dữ liệu ở `.runtime/browser_acceptance_20261019/demo` và journal `.runtime/browser_acceptance_20261019/p2_uat.sqlite3`. Không ghi kết luận thử, không chạy worker gửi thông báo; thông báo ở chế độ dry-run. Không sửa code sản phẩm trong lần tiếp tục này.

## Kiểm tra sẵn sàng, không thay thế nghiệm thu

Kiểm tra HTTP ngày **20/10/2026 lúc 08:09 giờ Việt Nam** xác nhận:

- Đủ **39 endpoint chi tiết**: 32 tình huống P2/73 giao dịch và 7 hồ sơ 001/003.
- Đủ **1.211 hồ sơ**: 584 của 001, 627 của 003; 9 trang/tài nguyên web trả thành công.
- Hash **1.209 tệp nguồn/kết quả đã khóa không đổi**. Với 005 chỉ băm opaque qua đối chiếu baseline, không parse/nạp/chấm hoặc dùng oracle.
- **39/39 mẫu vẫn `pending_browser`; 17/17 luồng chưa rà trực quan.** Nghiệm thu kế toán độc lập cũng chưa hoàn tất.

[HTTP readiness](browser_acceptance_20261020/http_preflight.json), [kết nối và hash phiên bản đang chờ rà](browser_acceptance_20261020/connection_and_readiness.json), [bản phiếu mẫu riêng cho lần tiếp tục](browser_acceptance_20261020/sample_results.csv).

Đối chiếu bản chụp code trong bộ phiếu 19/10 có **một tệp khác hash**: `sme_fraud/p2_controls_web.py`. Hash hiện tại của toàn bộ các tệp được lưu trong biên bản mới; chưa suy ra đây là lỗi UI. Khi trình duyệt được kết nối, nghiệm thu trên phiên bản thực sự đang chạy và lưu lại mọi thay đổi tiếp theo.

## Phần còn lại

Khi có trình duyệt kết nối, thực hiện [checklist WF01–WF17](browser_acceptance_20261019/checklist.md) và [39 đường dẫn mẫu](browser_acceptance_20261019/samples.md). Với P2 phải đọc đủ 73 giao dịch, không chỉ mở thẻ tổng hợp. Ghi kết quả, bằng chứng và lỗi tái hiện; sửa lỗi cản trở rồi kiểm tra lại. Thao tác thử dùng `ASSISTANT_BROWSER_SIM` / `SIM_BROWSER_UAT` trên bản riêng. RR09 giữ nguyên chính sách đang có cho đến khi được phê duyệt.

Phiếu và bằng chứng 19/10 được giữ nguyên. HTTP, kiểm thử engine hoặc DOM giả không được dùng để đóng mục nghiệm thu browser. Không có phát hiện browser mới hoặc lỗi browser mới được tuyên bố đã sửa trong lần này.

## Kiểm tra lại sau xác nhận kết nối

Người dùng đã báo “đã kết nối”. Công cụ vẫn trả `apps=[]`, `browsers=[]`; mở Chrome báo `Browser is not available: chrome`. Đã reset phiên điều khiển và lấy inventory mới, kết quả tiếp tục rỗng. Chưa thể xác định cách kết nối phía người dùng; đã hỏi thao tác kết nối và trình duyệt đang dùng để xử lý đúng nguyên nhân. Không có thao tác browser mới, không đổi kết quả 39 mẫu/17 luồng và không ghi kết luận nghiệp vụ.

Người dùng sau đó xác nhận đang mở Chrome tại `http://127.0.0.1:8765/`. Kiểm tra chỉ đọc `/api/health` và `/api/meta` xác nhận cổng 8765 là `sme-case-review`, QA, dry-run, **không tích hợp P2**; cổng 8771 là `BROWSER_ACCEPTANCE_20261019`, QA, dry-run, **có tích hợp P2**. Không thực hiện thao tác ghi tại cổng 8765. Thử bind đúng URL người dùng cung cấp qua công cụ Chrome vẫn báo `Browser is not available: chrome`.

Đã tra [hướng dẫn chính thức về browser extension](https://learn.chatgpt.com/docs/chrome-extension): mở URL trong Chrome riêng chưa đủ để công cụ nhận được browser. Người dùng cần kiểm tra Chrome trong Settings → Computer Use, trạng thái Manage sau khi cài extension đúng profile, và chọn Chrome/tab từ menu `@` trong chat. Địa chỉ dùng nghiệm thu là **8771**, không đổi máy chủ 8765 để ép trùng bản thử.
