# HE đã bật trên Portal 8800 — CR-036

**CR-037:** Portal đã có [quản lý worker cùng nút Bật/Tắt Agent2 và kết nối lại](HE_MANAGED_WORKER.md). Hướng dẫn bật worker thủ công bên dưới là lịch sử CR-036; với cấu hình he_worker, dùng nút Portal và không bật worker thứ hai.

**Portal hiện dùng bộ thử C001/C002 đã chuẩn bị.** Mở [Portal](http://127.0.0.1:8800/#agent2), đăng nhập bằng mật khẩu hiện tại, bấm **Chạy phân tích bảo mật** trong Agent2. Trên màn hình mới: chọn C001 hoặc C002 → chọn bản dữ liệu **5 bản ghi** → **Chạy phân tích**. Đường dẫn trực tiếp sau đăng nhập: [Phân tích bảo mật](http://127.0.0.1:8800/agent2/encrypted-analysis).

Không chọn bản 40 bản ghi lịch sử làm dữ liệu đánh giá. Nhãn dữ liệu mô phỏng, nguồn và mã lần chạy giúp phân biệt kết quả. Model đã fit và khóa đã được nối; người dùng không nhập model/khóa. Chưa có hàng đợi hoặc kết luận sai phạm tự động.

## Trạng thái đã bật

| Dịch vụ | Địa chỉ | Vai trò |
|---|---|---|
| Portal | `http://127.0.0.1:8800` | Đăng nhập hiện có và proxy Agent2 cùng origin |
| Agent2 tại DN | `http://127.0.0.1:8766` | Model/feature/khóa/giải mã; dùng phiên Portal |
| Worker bản mã | `http://127.0.0.1:8868` | Bundle riêng, chỉ tính/trả ciphertext |

Agent2 dùng `agent2/.runtime/he-company-demo/enterprise/snapshots.sqlite3`, `models.sqlite3`, `node.json` và `he-ui-bindings.json`. Membership demo chỉ `data.import` cho C001/C002, không cấp fit/verify/director. Cấu hình bốn nhánh local được để rỗng trong không gian demo để không dùng nhầm artifact HE như model local.

Mật khẩu, hồ sơ doanh nghiệp chung, file quyền cũ, DB snapshot/model cũ và các khóa/model của bộ thử được giữ nguyên. Không đặt lại mật khẩu, không thay bằng credential demo, không lưu token vào báo cáo. Restart Portal làm hết các phiên cũ; người dùng tự đăng nhập lại. **Người dùng đã đăng nhập bằng mật khẩu hiện tại; kiểm tra trên Portal thật qua đủ 7 bước:** C001/C002 mỗi bên có 5 điểm đã giải mã, tải lại vẫn giữ cùng run ID/kết quả, không có lỗi JavaScript. Đây là nghiệm thu kỹ thuật của luồng demo, chưa đánh giá độ chính xác nghiệp vụ hoặc nghiệm thu production.

Agent1 vẫn chạy cùng tiến trình/cổng 8011, không restart. Vì Portal đã được restart, tiến trình Agent1 từ Portal cũ được nhận diện đang chạy nhưng Portal mới không sở hữu nó; không tự giành quyền hoặc restart Agent1. Agent3/4 không được bật thêm.

## Bản sao cấu hình và dữ liệu cũ

Thư mục vận hành riêng:

```text
agent2/.runtime/he-company-demo/activation_20261112/
  portal-config-before.json       cấu hình Portal trước khi bật
  portal-config-after.json        cấu hình demo đã áp dụng
  before.json                    hash các tệp cần bảo toàn
  activation-verification.json    kiểm tra bảo toàn và API guard
  running.json                   địa chỉ/PID dịch vụ đã bật
  checker-migration.json         chuyển manifest bộ thử 1.0 → 1.1
  live-ui-status.json            trạng thái kiểm giao diện sau người dùng đăng nhập
```

Các file này ở thư mục private/Git ignore; không đưa log, profile trình duyệt, cấu hình vận hành hoặc khóa lên Git. Cấu hình `portal/config.local.json` chỉ đổi phần Agent2 sang bộ thử và hai biến môi trường HE. Workspace Portal/mật khẩu/cấu hình các agent khác không đổi. Nếu cần quay lại, dừng Agent2 qua Portal, khôi phục `portal-config-before.json` vào `portal/config.local.json`, rồi restart Portal/Agent2. Không chép đè DB cũ bằng DB demo hoặc xóa khóa; worker demo là tiến trình riêng và cần được dừng đúng PID/command đã ghi khi không còn sử dụng.

## Nếu khởi động lại máy hoặc đóng worker

Khóa/model vẫn lưu trên đĩa, nhưng bước này chưa cài Windows Service hoặc lịch tự chạy. Người vận hành cần bật lại worker trước khi chấm, từ thư mục bundle:

```powershell
cd D:/agent22/agent2/.runtime/he-company-demo/worker/bundle
& D:/agent22/agent2/.venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.worker_server --config D:/agent22/agent2/.runtime/he-company-demo/worker/service.json --port 8868
```

Sau đó khởi động Portal theo [hướng dẫn đăng nhập](PORTAL_AUTH.md), bật Agent2 bằng Portal; file cấu hình demo đã được giữ lại. Không mở thêm worker nếu 8868 đang có dịch vụ này chạy; không chạy standalone enterprise_server cùng state_dir của Agent2 web. Nếu mất kết nối, giao diện tiếp tục dùng cùng phiếu/yêu cầu, không tự fit hoặc chấm plaintext.

## Sửa bộ kiểm tra khi bật web

Checker `he-prepared-demo/1.1.0` khóa **checksum từng snapshot bất biến** và artifact model qua metadata/hash/provenance. Không khóa byte của toàn tệp SQLite, vì PRAGMA/schema/WAL có thể đổi header khi mở DB dù nội dung snapshot giữ nguyên. Bộ hiện có đã được kiểm đủ bốn snapshot/nguồn và binding lịch sử model trước khi nâng metadata; không refit hoặc đổi khóa. Manifest cũ có bản sao riêng.

Checker cũng dùng `enterprise/check-state` và `worker/check-state` riêng, worker tạm ở port trống. Nó không mở lại state_dir đang bị web node khóa hoặc đụng bảng job của worker live. Khi kết thúc, chỉ dừng cây tiến trình worker tạm do chính checker tạo. Có thể kiểm lại trong khi Portal chạy:

```powershell
cd D:/agent22/agent2
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.prepared_demo check --output-dir .runtime/he-company-demo
```

Đây vẫn là Mahalanobis hai feature/5 dòng thử mỗi DN, loopback và mô phỏng; không production/cloud public/bốn nhánh HE/đánh giá độ chính xác. [Báo cáo bật Portal và trạng thái nghiệm thu](../../Agent2_Spec_v2_1/evidence/HE/portal_activation_20261112/REPORT.md).
