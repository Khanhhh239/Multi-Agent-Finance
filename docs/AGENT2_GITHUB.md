# Agent 2 Sang — bản nguồn ngày 23/10/2026

Mã nguồn của workspace `agent22` được đồng bộ vào nhánh **`agent2-Sang`**. [README](../README.md) ghi phạm vi nghiệp vụ; [RELEASES.md](../RELEASES.md) hướng dẫn cài sạch, backup, nâng cấp và khôi phục bằng runtime phù hợp.

## Nội dung cập nhật

- Bộ luật, đồ thị quan hệ, ngưỡng động, nguồn thuế/tiền mặt và công cụ đồng bộ.
- ReviewStore, quản lý hồ sơ/yêu cầu tài liệu, lịch công việc, thông báo giả lập và cổng kết luận chung web/CLI.
- Sao lưu/khôi phục, tác vụ backup, quản lý phiên bản và gói phát hành có checksum.
- Giao diện bằng chứng, P2, điều hướng và thư viện Cytoscape được ghim phiên bản kèm giấy phép.
- Huấn luyện IF theo cửa sổ thời gian, kiểm toán model/phạm vi dữ liệu, so sánh shadow, kiểm tra phép gộp và quy trình rà độc lập.
- Test Python/JavaScript, schema, mẫu cấu hình và báo cáo kiểm chứng đến ngày 23/10.

Trạng thái sửa lỗi UI nằm tại [browser_acceptance_status_20261021.md](../reports/browser_acceptance_status_20261021.md). Báo cáo giữ riêng kết quả kiểm thử tự động, thao tác browser và các mục nghiệm thu còn chờ.

Phần ML mới được mô tả tại [tương thích nguồn/model](../reports/model_source_sync_20261022.md), [discovery shadow](../reports/ml_if_discovery_shadow_20261022.md) và [rà sơ bộ của trợ lý](../reports/ml_assistant_review_20261023.md). Các nhận định của trợ lý chưa thay cho kết luận độc lập của người rà; kết quả lợi ích ML và phút rà thực tế vẫn chờ xác nhận.

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

Kiểm chứng ngày 23/10: **154 ca Python đạt** thuộc 12 module test ML mới và liên quan, chạy trên bản nguồn chuẩn bị đưa lên Git với fixture tổng hợp. Không chạy lại toàn bộ suite web/backup hoặc đánh giá lại dataset phát triển trong lần đồng bộ này. Log được giữ cục bộ tại `.runtime/github_update_20261023_ml_tests.log`.

Kiểm chứng trước đó, ngày 21/10: 663 ca Python đạt trong lượt kiểm tra toàn bộ; 34 ca web/P2/backup được chạy lại sau khi tách fixture và đều đạt. Ba bộ JavaScript đạt 22 + 14 + 12 kiểm tra. Log được giữ cục bộ trong `.runtime/github_update_20261021_*`.

## Phạm vi lưu trên Git

Bản nguồn gồm Python/PowerShell, HTML/CSS/JavaScript, tài liệu, schema, cấu hình mẫu, CSV chỉ chứa header và các báo cáo/JSON tổng hợp. Thư viện browser trong `review_ui/vendor/` có manifest SHA256 và giấy phép đi kèm.

Dataset, model, SQLite, runtime, wheelhouse/gói cài đặt, ảnh/trace browser và kết quả chi tiết từng dòng được giữ cục bộ. Một số liên kết từ biên bản tới artifact đó chỉ có nội dung trong môi trường đã chạy; đọc phạm vi và kết luận trực tiếp trong từng báo cáo. Mẫu cấu hình thông báo lấy thông tin xác thực từ biến môi trường.

Với các đợt rà ML mới, Git lưu báo cáo Markdown và JSON tổng hợp/kiểm chứng; các bộ evidence, dossier JSON theo phiếu, mapping private và gói reviewer đầy đủ vẫn nằm trong môi trường cục bộ. Có thể tạo lại bằng công cụ và ví dụ tương ứng khi có nguồn phù hợp.
