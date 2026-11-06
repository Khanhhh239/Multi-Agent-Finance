# Multi-Agent Finance — Agent 2 (Sang)

Nhánh làm việc: **`agent2-Sang`**. Đồng bộ mã nguồn ngày **07/11/2026**. Xem [hướng dẫn bản nguồn trên Git](docs/AGENT2_GITHUB.md), [trạng thái dự án](docs/STATUS.md) và [hướng dẫn phát triển](docs/DEVELOPMENT.md).

## Sổ Soát — trợ lý rà soát giao dịch SME

Ứng dụng kết hợp luật nghiệp vụ, đồ thị quan hệ và Isolation Forest để lập hàng đợi hồ sơ cần rà. Workspace hiện dùng dữ liệu mô phỏng; IF tiếp tục chạy shadow.

## Bắt đầu tại đây

| Bạn cần | Tài liệu |
| --- | --- |
| Biết phần nào đã xong, phần nào còn thiếu | [Trạng thái dự án](docs/STATUS.md) |
| Chọn công việc tiếp theo | [Danh sách việc cần làm](docs/BACKLOG.md) |
| Tìm tài liệu và hiểu cấu trúc thư mục | [Mục lục dự án](docs/README.md) |
| Chạy app, kiểm thử hoặc phát triển | [Hướng dẫn phát triển](docs/DEVELOPMENT.md) |
| Cập nhật dữ liệu và cố định ML cho từng doanh nghiệp | [Dữ liệu & ML](examples/company_ml/README.md) |
| Nhập CSV/Excel, kiểm tra lỗi và tạo feature trước khi chọn ML | [Hướng dẫn nhập dữ liệu](docs/reports/ml/data_import_20261104.md) |
| So sánh model cùng kỳ, cùng ngân sách và ghi nhận phút rà | [Đánh giá model theo doanh nghiệp](docs/reports/ml/company_ml_comparison_20261104.md) |
| Rà cảnh báo trên web, lưu căn cứ/hành động và đo thời gian | [Phiếu rà ML](docs/reports/ml/ml_review_web_20261105.md) |
| Tra báo cáo chi tiết | [Mục lục báo cáo theo chủ đề](docs/reports/README.md) |
| Cài đặt, nâng cấp hoặc khôi phục | [Hướng dẫn phát hành](RELEASES.md) |

## Mở bản demo hiện tại

Từ thư mục dự án, dùng môi trường Python đã cài các thư viện của dự án:

```powershell
python -B start_review.py
```

Mở **http://127.0.0.1:8765/**. Phiên local đã gộp hồ sơ hiện có, nhập CSV/Excel, ML theo doanh nghiệp và phiếu rà. Menu bên trái dẫn đến từng chức năng trên cùng cổng; dữ liệu/model/nhãn đang dùng và 12 phiếu rà được giữ nguyên. Cấu hình máy này nằm tại `.runtime/review/server_8765.config.json`, được launcher tự đọc để dùng đúng database, môi trường thư viện và quyền quản lý demo. [Chi tiết chuyển và kiểm thử](docs/reports/app/unified_local_20261107.md), [hướng dẫn phát triển](docs/DEVELOPMENT.md).

Nếu mới clone mã nguồn và chưa có dữ liệu/profile local, làm theo [hướng dẫn tạo demo từ bản Git](docs/AGENT2_GITHUB.md).

Phiên 8765 hiện là **mô phỏng local**, có danh tính quản lý cố định do máy chủ cấu hình cho các chức năng ML. Cờ này chỉ hoạt động cùng `--qa`; bản chạy thông thường vẫn cần tích hợp đăng nhập và cấp quyền. Luồng **kế toán viên rà → kế toán trưởng hoặc giám đốc chốt** và đăng nhập thật là phần tích hợp riêng; thông báo vẫn ở chế độ giả lập.

## Cấu trúc chính

```text
sme_fraud/    Mã Python: luật, feature, ML, API và vận hành
review_ui/    Giao diện web
tests/        Kiểm thử và fixture
examples/     Cấu hình mẫu, schema nguồn và hướng dẫn từng chức năng
docs/         Trạng thái, việc cần làm và tài liệu theo chủ đề
reports/      Snapshot kết quả, model, phiếu rà và bằng chứng kiểm chứng
data/         Nguồn dữ liệu và cache
.runtime/     Môi trường, database và script chạy cục bộ
```

Các đường dẫn snapshot đang được app/kiểm thử sử dụng được giữ nguyên. Quy ước lưu tài liệu mới nằm trong [mục lục dự án](docs/README.md).
