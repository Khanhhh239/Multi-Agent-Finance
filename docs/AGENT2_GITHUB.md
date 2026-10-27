# Agent 2 Sang — bản nguồn ngày 27/10/2026

Nhánh **`agent2-Sang`** chứa mã nguồn được đồng bộ từ workspace `agent22`. Bắt đầu từ [trạng thái dự án](STATUS.md), [backlog](BACKLOG.md) và [hướng dẫn phát triển](DEVELOPMENT.md). Tài liệu nghiệp vụ, ML, app và vận hành nằm trong [mục lục báo cáo](reports/README.md).

## Nội dung mới

- Sửa bằng chứng theo cutoff, định danh liên hệ và quan hệ nhân viên/công ty; cập nhật feature contract v4, 194 feature.
- Phân tầng ưu tiên RR09, thêm nguồn đối chứng và ma trận test luật.
- Quy trình kế toán viên rà, kế toán trưởng/giám đốc khác người chốt hoặc trả lại; kiểm soát công ty, phiên bản hồ sơ và nhật ký.
- Thông báo theo vai trò, chống trùng, nhắc hạn và lịch sử gửi; ví dụ cấu hình vẫn dùng mô phỏng/template.
- Guard giới hạn trì hoãn baseline trong thử nghiệm IF, cùng báo cáo kiểm chứng.
- Sắp xếp lại tài liệu trong `docs/`; các đường dẫn cũ được chuyển hoặc giữ file chỉ dẫn theo thay đổi của workspace.

Các kết quả nghiệp vụ chi tiết và giới hạn nghiệm thu được giữ trong từng báo cáo. IF tiếp tục chạy shadow; tài khoản thật, gửi–nhận thông báo thật và rà ML độc lập vẫn theo trạng thái trong tài liệu dự án.

## Cài từ mã nguồn và kiểm thử

Profile web/backup đã kiểm chứng dùng CPython 3.12 trên Windows x64:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-review-lock.txt
$env:PYTHONPATH = "$PWD;$PWD/tests"
New-Item -ItemType Directory -Force .runtime | Out-Null
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Với Node.js đã cài, chạy các bộ VM/DOM:

```powershell
Get-ChildItem tests -Filter '*.test.js' | ForEach-Object {
    node $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Kiểm thử lỗi: $($_.Name)" }
}
```

Kiểm chứng trên bản nguồn chuẩn bị đưa lên Git ngày 27/10: **1273 ca Python đạt**, 0 lỗi/failure/skip; **92 kiểm tra JavaScript đạt** trong 7 bộ. Bộ Python chạy với profile `requirements-review-lock.txt`.

Log của lần đồng bộ được giữ cục bộ trong `.runtime/github_update_20261027_*`. Các kiểm tra JavaScript là VM/DOM; lần đồng bộ Git này không chạy lại nghiệm thu Chrome. Bộ kiểm thử sử dụng fixture tổng hợp và thư mục tạm riêng, không cần mang dataset phát triển lên Git.

`requirements.txt` mô tả phụ thuộc tổng quát. `requirements-lock.txt` giữ profile benchmark/model lịch sử; không dùng thay profile web/backup khi cần mở model hoặc backup đã khóa hợp đồng runtime. Xem [hướng dẫn phát hành](../RELEASES.md) và ví dụ tương ứng trước khi sử dụng artifact.

## Demo chỉ từ bản nguồn

Lệnh `.runtime/review_roles_20261024/serve.py` trong README dành cho workspace phát triển có sẵn snapshot và database. Để thử giao diện với fixture và danh tính mô phỏng từ bản Git mới, sau khi cài thư viện và đặt `PYTHONPATH` như trên:

```powershell
.\.venv\Scripts\python.exe -B tests/review_browser_fixture.py `
    --workspace .runtime/browser_workflow_20261027/github_demo
```

Mở các địa chỉ loopback mà launcher in ra cho kế toán viên, kế toán trưởng, giám đốc và người xem. Đây là môi trường QA với dữ liệu tổng hợp, danh tính cố định và thông báo giả lập. Các kết quả thao tác không thay cho rà độc lập trên nguồn thật.

## Phạm vi lưu trên Git

Bản nguồn gồm Python/PowerShell, UI, test/fixture, tài liệu, schema, cấu hình mẫu, CSV chỉ chứa header, báo cáo Markdown và JSON tổng hợp/kiểm chứng. Thư viện browser và fixture JSON được giữ đúng byte theo manifest/checksum.

Dataset/cache, model, SQLite, môi trường Python, wheelhouse, gói cài đặt, ảnh/trace browser, mapping private và JSON bằng chứng chi tiết theo phiếu được giữ cục bộ. Một số liên kết trong báo cáo tới artifact này chỉ dùng được tại môi trường đã chạy; mã và ví dụ đi kèm mô tả cách sinh lại vào thư mục mới. Script dọn tài liệu được lưu như mã nguồn và không được chạy trong lần đồng bộ này.
