# Kiểm tra giao diện Sổ Son — 11/11/2026

Phạm vi: chỉnh trình bày trên nhánh `platform-Khanh`, dựa trên 14 bảng concept, 6 tấm tranh địa danh và `Yêu cầu.pdf`. Chưa commit/push. Không sửa API, quy tắc kế toán, database hoặc cơ chế xác thực.

## Thay đổi

- Dùng chung đỏ son, nền kem, Be Vietnam Pro và Noto Serif hỗ trợ tiếng Việt; font chạy nội bộ, không cần CDN.
- Tái sử dụng tranh từ ZIP người dùng, chia cảnh bằng CSS. Tổng quan portal không có tranh hoặc hero; tên doanh nghiệp lấy từ hồ sơ.
- Một sidebar của portal; điều hướng trong agent được thu thành hàng ngang khi nhúng.
- A1: thu gọn hướng dẫn mở đầu; giữ nguyên các nút, bộ lọc, ngày chốt và số tuần dự báo.
- A2: danh sách hồ sơ dạng bảng; mở hồ sơ giữ luồng admit, API, điều hướng chi tiết và kết luận cũ. Khi xem chi tiết, danh sách bên trái thu gọn; các cột đầy đủ vẫn có ở hàng đợi.
- A3: theme chung nạp sau CSS sản phẩm; sửa khoảng trống sidebar và chồng lấn header khi nhúng.
- A4: tên Hỏi Đáp, gợi ý bên phải, giữ phần trả lời và Kiểm tra nguồn.
- Nạp chung: giữ khóa mật khẩu/FaceID, hàng chờ, ghép cột và ghi dữ liệu; không thay cơ chế phân phối.

## Đã kiểm tra

| Khu vực | Cách kiểm tra | Kết quả và giới hạn |
| --- | --- | --- |
| Portal | Tổng quan, hồ sơ, nạp bị khóa, 4 agent; desktop 1440 và mobile 390 | Không có lỗi JavaScript; không tràn ngang các trang chung |
| Nạp chung sau mở khóa | Chỉ giả lập trạng thái API trong trình duyệt kiểm thử | Xem bố cục; không mở khóa thật, không nạp/ghi dữ liệu sản xuất |
| A1 | Tổng quan, dự báo, dữ liệu, phiên bản, hướng dẫn | Giữ ô ngày chốt và nhận 24 tuần; chưa chạy huấn luyện/dự báo mới |
| A2 | 3 cửa sổ điều hướng, Dữ liệu & ML, Phiếu rà ML, nhập dữ liệu | Các trang đang được backend phục vụ mở được |
| A2 hồ sơ | Packet bằng chứng đóng băng của repo, intercept trình duyệt, không admit thật | 5 tab chi tiết mở được; thử lỗi 503 có thông báo; không gửi kết luận |
| A3 | 13 route trên fixture server có sẵn của repo | Không có lỗi tải trang/JavaScript trong fixture |
| A3 regression | `node scripts/ui-check.mjs` | Qua lọc, phân trang, focus dialog, lỗi lưu giữ nội dung, chống trả lời trễ, wizard 5 bước, 320–1440px, dark mode và reduced motion |
| A2 regression | `node --test tests/review_navigation_ui.test.js tests/review_evidence_ui.test.js tests/review_reliability_ui.test.js tests/review_business_ui.test.js` | Qua kiểm tra điều hướng, bằng chứng, phản hồi lỗi và luồng duyệt |
| A4 | Gửi câu hỏi doanh thu Q3/2026 tới backend đang chạy, mở nguồn | Đã trả lời; 65 chỉ tiêu; mobile không tràn ngang |
| Theme | `python design/sync.py --check`, kiểm tra cú pháp JS và `git diff --check` | Đồng bộ CSS/JS/font giữa các agent |

## Vấn đề hiện hữu chưa giải quyết bằng chỉnh giao diện

- **A3 trên web thật** vẫn báo xung đột liên kết hồ sơ: workspace khớp mã số thuế đang mang cờ `simulated`. Bridge từ chối liên kết theo logic hiện hành. Không đổi cờ dữ liệu hay bỏ kiểm tra backend. 13 màn fixture không đồng nghĩa A3 thật đã chạy nghiệp vụ thành công.
- **Đối chứng P2** đang bị tắt trong cấu hình backend hiện tại và trả 404; không bật tính năng bằng thay CSS.
- Hàng đợi A2 hiện trống và A1 chưa lập dự báo mới; không tự chèn con số/biểu đồ giả để giống hình concept.
- Ảnh concept là định hướng bố cục, không phải cam kết sao chép dữ liệu hoặc chức năng chưa có trong backend.

## Nguồn và chỉnh tiếp

Theme gốc: `design/platform-theme.css`, hành vi trình bày: `design/platform-theme.js`; chạy `python design/sync.py` sau khi sửa. Font Noto Serif có giấy phép tại `design/fonts/NotoSerif-OFL.txt`.

Đã tham khảo [taste-skill](https://github.com/Leonxlnx/taste-skill) và [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill), áp dụng nguyên tắc typography, bảng dữ liệu, khoảng cách và kiểm tra trình duyệt theo yêu cầu PDF của người dùng.

Ảnh kiểm tra trên máy: `C:/Users/Admin/Downloads/SoSon-Figma-Review-v2/qa-final/`. Đây là bằng chứng kiểm tra local, không được đẩy lên Git.
