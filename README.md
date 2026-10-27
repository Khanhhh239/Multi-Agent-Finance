# Multi-Agent Finance — Agent 2 (Sang)

Nhánh làm việc: **`agent2-Sang`**. Đồng bộ mã nguồn ngày **27/10/2026**. Xem [hướng dẫn bản nguồn trên Git](docs/AGENT2_GITHUB.md), [trạng thái dự án](docs/STATUS.md) và [hướng dẫn phát triển](docs/DEVELOPMENT.md).

## Sổ Soát — trợ lý rà soát giao dịch SME

Ứng dụng kết hợp luật nghiệp vụ, đồ thị quan hệ và Isolation Forest để lập hàng đợi hồ sơ cần rà. Workspace hiện dùng dữ liệu mô phỏng; IF tiếp tục chạy shadow.

## Bắt đầu tại đây

| Bạn cần | Tài liệu |
| --- | --- |
| Biết phần nào đã xong, phần nào còn thiếu | [Trạng thái dự án](docs/STATUS.md) |
| Chọn công việc tiếp theo | [Danh sách việc cần làm](docs/BACKLOG.md) |
| Tìm tài liệu và hiểu cấu trúc thư mục | [Mục lục dự án](docs/README.md) |
| Chạy app, kiểm thử hoặc phát triển | [Hướng dẫn phát triển](docs/DEVELOPMENT.md) |
| Tra báo cáo chi tiết | [Mục lục báo cáo theo chủ đề](docs/reports/README.md) |
| Cài đặt, nâng cấp hoặc khôi phục | [Hướng dẫn phát hành](RELEASES.md) |

## Mở bản demo hiện tại

Từ thư mục dự án, dùng môi trường Python đã cài các thư viện của dự án:

```powershell
python -B .runtime/review_roles_20261024/serve.py
```

Sau khi máy chủ báo sẵn sàng, mở **http://127.0.0.1:8774/**. Bản demo dùng snapshot RR09/ML v4 và bộ đối chứng RR09 riêng. Hướng dẫn chi tiết, đường dẫn Python của máy này và cách chạy từ CLI nằm trong [hướng dẫn phát triển](docs/DEVELOPMENT.md).

Vai trò đã chuẩn bị: **kế toán viên rà → kế toán trưởng hoặc giám đốc chốt**. Tài khoản và đăng nhập sẽ làm sau theo lựa chọn của người dùng; hiện chưa đăng nhập chỉ xem được. Thông báo đang ở chế độ giả lập.

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
