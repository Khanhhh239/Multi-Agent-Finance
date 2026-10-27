# Mục lục dự án

Đọc [trạng thái](STATUS.md) và [việc cần làm](BACKLOG.md) trước. Các báo cáo theo ngày ghi kết quả tại thời điểm thực hiện, có thể khác bản hiện tại.

## Tài liệu làm việc

| Nhóm | Điểm bắt đầu |
| --- | --- |
| Tổng quan | [README dự án](../README.md), [trạng thái](STATUS.md), [backlog](BACKLOG.md) |
| Phát triển | [Chạy app và kiểm thử](DEVELOPMENT.md) |
| Sản phẩm | [Yêu cầu sản phẩm](product/requirements.md), [roadmap tham chiếu](product/roadmap_reference.md) |
| Luật | [Đặc tả đang được bộ audit sử dụng](../rule_class_1.md), [nghiên cứu tham chiếu](product/rule_research.md) |
| Báo cáo | [Mục lục theo chủ đề](reports/README.md) |
| Dữ liệu mô phỏng | [Cấu trúc dữ liệu và benchmark lịch sử](development/synthetic_data.md) |
| Vận hành | [Cài đặt/nâng cấp/khôi phục](../RELEASES.md), [backup](../examples/review_backup/README.md), [phân quyền](../examples/review_roles/README.md) |
| Lịch sử dọn dự án | [Các thay đổi ngày 27/10/2026](history/cleanup_20261027.md) |

## Thư mục và cách lưu file mới

| Thư mục | Nội dung |
| --- | --- |
| `sme_fraud/` | Mã Python và các schema đi cùng module |
| `review_ui/` | HTML, CSS, JavaScript và thư viện giao diện |
| `tests/` | Kiểm thử; dữ liệu nhỏ để kiểm thử đặt trong `tests/fixtures/` |
| `examples/` | Cấu hình mẫu và hướng dẫn chạy từng chức năng |
| `docs/product/` | Yêu cầu và kế hoạch sản phẩm tham chiếu |
| `docs/reports/` | Báo cáo diễn giải, chia nhóm luật, ML, app, vận hành và lịch sử |
| `docs/development/` | Tài liệu kỹ thuật về dữ liệu/benchmark |
| `reports/` | Đầu ra máy, model, snapshot, gói rà và bằng chứng đã khoá |
| `data/` | Nguồn và cache; không dùng làm chỗ lưu tài liệu |
| `.runtime/` | Phụ thuộc, database, log và script cục bộ |
| `.publish/`, `outputs/`, `.archive/` | Bản cài thử, gói xuất và dữ liệu lưu trữ |

Báo cáo mới viết vào đúng nhóm trong `docs/reports/`, rồi thêm liên kết ở mục lục nhóm. Kết quả chạy mới dùng một thư mục riêng trong `reports/`; ghi rõ nguồn, cấu hình, phiên bản và cửa sổ thời gian. Không ghi đè snapshot cũ để thay kết quả.

Cập nhật tiến độ ở `docs/STATUS.md` và `docs/BACKLOG.md`, tránh tạo thêm nhiều file “status” theo ngày. Chỉ giữ báo cáo riêng khi có quyết định, phát hiện hoặc bằng chứng cần tra lại. Log thử tạm và file bytecode thuộc `.runtime/` hoặc thư mục cache.

Một số báo cáo diễn giải vẫn nằm ở `reports/` vì đường dẫn/hash của chúng đã được bộ kiểm chứng hoặc bộ đóng gói sử dụng. Mục lục theo chủ đề đã liên kết tới các file đó; không cần di chuyển thủ công.
