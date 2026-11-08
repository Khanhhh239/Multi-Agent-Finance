# Agent 2 Sang — bản nguồn ngày 07/11/2026

Nhánh làm việc là **`agent2-Sang`** trong repo Multi-Agent-Finance. Bắt đầu từ [trạng thái dự án](STATUS.md), [hướng dẫn phát triển](DEVELOPMENT.md) và [báo cáo hợp nhất phiên local](reports/app/unified_local_20261107.md).

## Nội dung cập nhật

- Nhập CSV/Excel theo doanh nghiệp, kiểm tra lỗi theo dòng/cột, xem bản chuẩn hóa và tạo 194 feature trước khi xác nhận lưu, chuyển sang chọn ML đúng công ty.
- Isolation Forest, Autoencoder, ECOD, LOF và CatBoost có nhãn xác minh; điều kiện dùng CatBoost theo đúng kỳ train, kiểm tương thích model trước khi giữ/chấm.
- So sánh cùng kỳ/cùng ngân sách, phiếu rà trên web với căn cứ/hành động, đồng hồ máy chủ, lưu nháp và tổng hợp theo quyền/phạm vi.
- Bổ sung nhãn giữ nhãn không liên quan, xem trước xung đột, quyết định giữ/sửa kèm lý do/xác nhận và lịch sử trước/sau.
- Khóa chính xác tập bằng chứng theo manifest/model/dòng chọn; tệp thừa, thiếu hoặc thay đổi trong lúc đọc bị chặn.
- Một phiên local ở **8765** cho hàng đợi, nhập dữ liệu, chọn ML và phiếu rà. Profile khởi động lưu riêng tại máy; có kiểm tra và chuyển nguyên tử phần ML vào database hồ sơ đang dùng.

Các tính năng ML tiếp tục ở shadow. Phiên local đã cấu hình dùng danh tính quản lý **mô phỏng** do máy chủ cấp; không tự tạo tài khoản đăng nhập thật hoặc nghiệm thu độc lập.

## Workspace đang dùng và bản Git

Lệnh `python -B start_review.py` trong README dành cho workspace đã có dữ liệu và `.runtime/review/server_8765.config.json`. Profile, database, artifact, gói phiếu đã khóa và các đường dẫn môi trường cụ thể của máy này không được đưa lên Git. Khi chỉ clone mã nguồn, dùng fixture tổng hợp bên dưới hoặc tự cung cấp nguồn/schema và cấu hình triển khai phù hợp.

Không có 1.146 hồ sơ hoặc gói 12 phiếu của workspace phát triển trong bản clone. Các con số trong biên bản là kết quả đối chiếu local; mã và test đi kèm có thể sinh dữ liệu mô phỏng mới vào thư mục riêng.

## Cài và chạy từ mã nguồn

Profile đã kiểm chứng dùng CPython 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-review-lock.txt -r requirements-data-import.txt
# Tùy chọn, chỉ cần khi thử CatBoost:
.\.venv\Scripts\python.exe -m pip install -r requirements-company-ml.txt
$env:PYTHONPATH = "$PWD;$PWD/tests"
$env:PYTHONDONTWRITEBYTECODE = '1'
```

Tạo demo mới từ fixture tổng hợp. Đoạn này dừng nếu thư mục đã tồn tại để giữ nguyên công việc trước:

```powershell
@'
from pathlib import Path
from test_data_import import import_fixture, upload_rows, csv_bytes, xlsx_bytes
root = Path('.runtime/github_demo_20261107')
if root.exists():
    raise FileExistsError('Chọn thư mục demo mới; không ghi đè dữ liệu cũ.')
root.mkdir(parents=True)
store, _ = import_fixture(root)
store.prepare()
for company in ('C001', 'C002'):
    rows = upload_rows(company, count=30)
    (root / f'SIMULATED_{company}.csv').write_bytes(csv_bytes(rows))
    (root / f'SIMULATED_{company}.xlsx').write_bytes(xlsx_bytes(rows))
'@ | .\.venv\Scripts\python.exe -B -

.\.venv\Scripts\python.exe -B -m sme_fraud.review_server `
    --data-root .runtime/github_demo_20261107/data `
    --reports-root .runtime/github_demo_20261107/reports `
    --database .runtime/github_demo_20261107/review.sqlite3 `
    --port 8765 --qa --demo-ml-manager
```

Mở `http://127.0.0.1:8765/data-import`, chọn C001/C002 và tệp mẫu tương ứng. Có thể kiểm tra, xác nhận nhập rồi đánh giá/kích hoạt/chấm model. Demo mới chưa có model được kích hoạt hoặc gói phiếu đã khóa; dùng [runner so sánh](reports/ml/company_ml_comparison_20261104.md) để sinh gói khi đã có dữ liệu phù hợp. Cờ `--demo-ml-manager` chỉ hoạt động cùng `--qa`; bản chạy thông thường vẫn cần danh tính được máy chủ xác thực.

## Kiểm thử

Để chạy đầy đủ bộ kiểm thử bên dưới, cài cả `requirements-company-ml.txt`; các ca kiểm điều kiện train CatBoost dùng profile có thư viện này. Ứng dụng vẫn hỗ trợ bốn thuật toán còn lại khi không cài CatBoost.

```powershell
.\.venv\Scripts\python.exe -B -m unittest test_unified_local test_ml_review_packets test_company_ml_labels test_ml_review_web test_ml_review_api test_company_ml_readiness test_company_ml_comparison test_data_import test_company_ml test_company_ml_web test_review test_review_roles test_review_workflow test_feature_model_sync test_shadow_scoring test_review_backup -q
$uiTests = Get-ChildItem tests -Filter '*test.js' | Select-Object -ExpandProperty FullName
node --test $uiTests
```

Lượt hợp nhất local đạt **211 test Python**, **146 kiểm tra JavaScript**, **30/30 kiểm tra Playwright**. Các bộ JavaScript cũ có script tự báo số kiểm tra chi tiết bên trong; Node báo 92 test entry. Phạm vi và bằng chứng nằm trong [biên bản hợp nhất](reports/app/unified_local_20261107.md); kiểm thử trình duyệt live cần đúng workspace đã sinh, không chạy test có ghi dữ liệu lên phiên dùng chính.

Lần đồng bộ Git **07/11/2026** đã chạy lại **211 test Python thuộc 16 module, 146 kiểm tra JavaScript** trên chính bản nguồn chuẩn bị công bố, không lỗi hoặc skip. Thử thêm demo mới chỉ từ bản Git đạt **9 kiểm tra** về route/quyền, preview 194 feature và lưu CSV/XLSX cho C001/C002. Đây là bộ hồi quy liên quan; chưa chạy lại toàn bộ suite hoặc Playwright trong lượt đồng bộ này. Log chỉ giữ local tại `.runtime/github_update_20261107_*` trong bản clone dùng để công bố.

## Phạm vi đưa lên Git

Có mã Python/PowerShell, UI, test/fixture tổng hợp, schema, cấu hình mẫu, CSV chỉ có header, Markdown và JSON tổng hợp đã chọn. Giữ nguyên thư viện browser/license theo manifest.

Không đưa dataset/cache, model đã fit, SQLite, môi trường Python, wheel, thông tin xác thực, cấu hình máy, kết quả người rà hoặc bằng chứng chi tiết riêng tư lên Git. Các liên kết tới `.runtime` trong biên bản là bằng chứng local và không có sẵn sau khi clone.
