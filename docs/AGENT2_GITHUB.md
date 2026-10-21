# Agent 2 Sang — bản nguồn ngày 21/10/2026

Mã nguồn của workspace `agent22` được đồng bộ vào nhánh **`agent2-Sang`**. [README](../README.md) ghi phạm vi nghiệp vụ; [RELEASES.md](../RELEASES.md) hướng dẫn cài sạch, backup, nâng cấp và khôi phục bằng runtime phù hợp.

## Nội dung cập nhật

- Bộ luật, đồ thị quan hệ, ngưỡng động, nguồn thuế/tiền mặt và công cụ đồng bộ.
- ReviewStore, quản lý hồ sơ/yêu cầu tài liệu, lịch công việc, thông báo giả lập và cổng kết luận chung web/CLI.
- Sao lưu/khôi phục, tác vụ backup, quản lý phiên bản và gói phát hành có checksum.
- Giao diện bằng chứng, P2, điều hướng và thư viện Cytoscape được ghim phiên bản kèm giấy phép.
- Test Python/JavaScript, schema, mẫu cấu hình và báo cáo kiểm chứng đến ngày 21/10.

Trạng thái sửa lỗi UI nằm tại [browser_acceptance_status_20261021.md](../reports/browser_acceptance_status_20261021.md). Báo cáo giữ riêng kết quả kiểm thử tự động, thao tác browser và các mục nghiệm thu còn chờ.

## Cài từ mã nguồn và kiểm thử

Profile web/backup đã kiểm chứng dùng **CPython 3.12, Windows x64**:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-review-lock.txt
New-Item -ItemType Directory -Force .runtime | Out-Null
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Với Node.js đã cài, chạy các kiểm tra VM/DOM riêng:

Các kiểm tra dùng fixture mô phỏng cố định tại `tests/fixtures/` (32 tình huống/73 giao dịch), có SHA256 của nguồn; không cần dataset gốc để chạy các kiểm tra này.

```powershell
node tests/review_evidence_ui.test.js
node tests/review_workflow_ui.test.js
node tests/review_navigation_ui.test.js
```

`requirements.txt` mô tả phụ thuộc tổng quát; `requirements-lock.txt` giữ profile benchmark lịch sử. Không thay hai profile này cho nhau khi cần mở model/backup đã khóa hợp đồng runtime. Xem README và từng ví dụ trong `examples/` để sinh dữ liệu và mở demo bằng thư mục đầu ra mới.

Các test web/backup tự tạo bộ đối chứng P2 khai báo sẵn trong thư mục tạm riêng; không cần mở dataset của máy phát triển và không thay cấu hình mặc định của ứng dụng.

Kiểm chứng bản cập nhật: 663 ca Python đạt trong lượt kiểm tra toàn bộ; 34 ca web/P2/backup được chạy lại sau khi tách fixture và đều đạt. Ba bộ JavaScript đạt 22 + 14 + 12 kiểm tra. Log được giữ cục bộ trong `.runtime/github_update_20261021_*`.

## Phạm vi lưu trên Git

Bản nguồn gồm Python/PowerShell, HTML/CSS/JavaScript, tài liệu, schema, cấu hình mẫu, CSV chỉ chứa header và các báo cáo/JSON tổng hợp. Thư viện browser trong `review_ui/vendor/` có manifest SHA256 và giấy phép đi kèm.

Dataset, model, SQLite, runtime, wheelhouse/gói cài đặt, ảnh/trace browser và kết quả chi tiết từng dòng được giữ cục bộ. Một số liên kết từ biên bản tới artifact đó chỉ có nội dung trong môi trường đã chạy; đọc phạm vi và kết luận trực tiếp trong từng báo cáo. Mẫu cấu hình thông báo lấy thông tin xác thực từ biến môi trường.
