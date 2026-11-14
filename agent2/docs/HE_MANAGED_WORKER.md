# Bật/tắt Agent2 kèm worker — CR-037

**CR-040:** đã bổ sung [khôi phục worker chết giữa phép tính](HE_WORKER_RECOVERY.md) cho managed request có hash binding, còn nguyên state và chưa hết TTL. Không đổi khóa/model hoặc nonce; trạng thái thất bại cũ/legacy không tự mở lại.

Người dùng tiếp tục làm việc trong Portal. **Bật Agent2** sẽ bật worker bản mã, xác minh kết nối/khóa, rồi mới mở node phân tích. **Tắt Agent2** dừng node trước và worker do Portal đó tạo sau; không xóa model, khóa, snapshot hoặc kho phiên.

Nếu worker mất kết nối, Portal hiện thông báo ngắn và nút **Kết nối lại phân tích**. Trong màn hình phân tích cũng có **Kết nối lại**. Nút này bật lại worker, kiểm khóa rồi tiếp tục job/phiếu cũ; không đổi model, fit lại hoặc tạo mã yêu cầu khác. Đăng nhập/quyền hiện tại vẫn được kiểm. Kết quả completed có thể đọc lại dù worker đang tắt, vì được lưu mã hóa tại DN.

## Kiểm tra trước khi chấm

1. Portal xác minh worker bundle đúng allowlist/checksum và cùng phiên bản code hiện tại. Không chạy từ cây code doanh nghiệp hoặc một gói có thêm file lạ.
2. Preflight chạy bằng Python của Agent2 tại DN, mở hai khóa DPAPI theo tài khoản Windows hiện tại. Khóa hoặc cấu hình sai thì chưa bật dịch vụ; không tự tạo khóa thay thế. Node tiếp tục kiểm khóa bọc khớp kho phiên trước khi mở health/API.
3. Node gửi challenge ngẫu nhiên có thời hạn, ký bằng khóa provisioning. Worker kiểm grant tenant/DN/khóa node, rồi ký phản hồi. Node xác minh đúng public key worker được ghim, đúng challenge/scope/expiry. Chỉ kiểm cổng mở hoặc đọc health không được coi là đủ.
4. Catalog chỉ bật lượt phân tích mới khi model phù hợp **và** worker đã được xác minh. Job processor kiểm lại worker trước khi export/gửi khi chưa có ciphertext kết quả. Mất mạng ở giữa tạo trạng thái chờ thử lại và giữ yêu cầu/checkpoint; có ciphertext đã lưu thì giải mã tiếp không cần mạng.

RPC readiness không tạo HE context/session/job, không đọc model hoặc gửi dữ liệu/feature rõ. Chữ ký xác nhận danh tính và binding, không chứng minh worker ác ý tính đúng hoặc attestation của máy.

## Cấu hình phía người vận hành

Khi đã bật HE bằng hai biến `AGENT2_HE_NODE_CONFIG` và `AGENT2_HE_BINDINGS`, thêm `he_worker` dưới `agents.agent2` trong file Portal local:

```json
{
  "he_worker": {
    "bundle": "agent2/.runtime/he-company-demo/worker/bundle",
    "config": "agent2/.runtime/he-company-demo/worker/service.json",
    "port": 8868
  }
}
```

Đường dẫn là cấu hình server, không nhận từ browser. Port phải khớp worker_url trong node config; node dùng config 1.2.0/DPAPI, pins đúng tenant/DN và cùng DB snapshot của màn hình nhập. Mọi scope được ghim phải có worker grant phù hợp. Dùng [bộ C001/C002](HE_COMPANY_DEMO.md) đã chuẩn bị để demo.

Không bật worker thủ công song song với chế độ này. Nếu cổng worker có tiến trình ngoài Portal đang nghe, Portal báo lỗi, **không tự nhận quản lý hoặc dừng tiến trình đó**. Nếu worker do Portal tạo bị dừng/crash, bấm kết nối lại; Portal chỉ thay worker, giữ node, khóa/phiên và đăng nhập Portal. Thay cấu hình khi worker đang được quản lý cần tắt Agent2 trước, không âm thầm đổi identity.

Mặc định không bật HE thì Portal vẫn chạy Agent2 local như trước, không thêm dependency crypto vào Portal. Preflight crypto nằm ở process DN. Worker dùng bundle/cwd/PYTHONPATH riêng và environment allowlist, không nhận Portal bridge secret, credential doanh nghiệp, model/snapshot hoặc khóa giải mã HE.

## Dừng và khôi phục

- Dừng đúng cây tiến trình Popen đã tạo, gồm Windows venv child; không dò port rồi kill bất kỳ tiến trình nào đang dùng port đó.
- Dừng node trước để không nhận/gửi thêm công việc, đợi worker hoàn tất ciphertext đang tính trong giới hạn grace period rồi dừng worker. Không purge DB hoặc backup, không đổi khóa.
- Bật lại mở cùng kho phiên. Job chưa xong chờ xác thực hiện tại và tiếp tục cùng ID, context/nonce đã lưu; hoàn tất thì đọc lại kết quả cũ. Bật/tắt riêng Agent2 không reset phiên Portal.
- Worker chết khi đang tính mà chưa commit được tiếp tục từ đúng request-hash/context/nonce đã lưu theo CR-040; phép toán native có thể chạy lại trên bản mã cũ, chỉ một job logic và một kết quả commit. Hết TTL, mất/corrupt/rollback state, đổi key hoặc legacy nonce không có hash binding vẫn báo failed/expired rõ. Không tạo nonce mới hoặc plaintext fallback để che lỗi; không tự mở lại terminal failure cũ.
- Đóng Portal bình thường dừng các dịch vụ do nó quản lý. Chưa Windows Service/Task Scheduler hoặc bảo đảm tự chạy sau reboot/force-kill Portal. Không quản lý lại các agent khác đang chạy ngoài Portal đó.

## API và UI

`POST /api/agents/agent2/start` và `/stop` tiếp tục là thao tác nút Portal, nay bao gồm dependency worker khi HE được cấu hình. `POST /api/agents/agent2/recover` cần phiên Portal hợp lệ, kiểm Host/Origin/X-Platform như các thao tác hiện có. Không có arbitrary command/proxy/decrypt endpoint. DTO trạng thái chỉ có ready/message/owned/can_recover, không có key/token/path private của worker.

Trong Agent2, phiếu localStorage vẫn được ghi trước POST và ghim owner/company/snapshot/key/job. Kết nối lại giữ phiếu, bỏ các phản hồi poll cũ rồi xác minh lại readiness; không xóa phiếu để chạy lại từ đầu. Người dùng local ngoài Portal chỉ kiểm lại kết nối, không được tự quản lý process worker qua API Portal.

## Kiểm thử

```powershell
cd D:/agent22/agent2
& .venv/Scripts/python.exe -X utf8 -B scripts/test_managed_worker_ui.py --output-dir '<thu-muc-moi>'
& .venv/Scripts/python.exe -X utf8 -B scripts/run_he_tests.py --report '<he-report-moi.json>'
```

Browser test dùng Portal, DN/worker thật và TenSEAL trên dữ liệu mô phỏng, kiểm Bật/Tắt, đọc lại cùng result sau restart, worker outage/reconnect cùng job và không chấm trùng. Unit lifecycle kiểm cả pending restart, wrong key, DPAPI hỏng, cổng ngoài không được kill/adopt và readiness không tạo job. Xem [báo cáo/evidence](../../Agent2_Spec_v2_1/evidence/HE/managed_worker_20261112/REPORT.md).

Vẫn Mahalanobis hai feature trong thử nghiệm loopback Windows, chưa bốn nhánh HE/queue/production/accuracy claim. R0–R6 và gate sản phẩm giữ nguyên.
