# REPORT — R1, backend validation theo CR-006

- spec_version: 2.1; ngày 10/11/2026 (Asia/Saigon).
- Task được giao: kiểm tra backend quyền DN, trường/kiểu/trùng/liên kết, lỗi rõ dòng/trường/cách sửa, hạn chế phân tích khi thiếu nguồn.
- Phần được giao: **READY_FOR_REVIEW**. Toàn bộ milestone R1: **PARTIAL**, không ghi DONE hay duyệt production.
- Base commit: `f203b39828f567171916b5b4744728ed4b63d17f`, working tree chưa commit. Giữ các thay đổi dọn/contract trước; không reset, merge hoặc push trong task này.
- Người thực hiện kỹ thuật: Codex. Người duyệt thật: chưa được chỉ định.
- Source/fixture/spec hash và phạm vi thay đổi: `artifact_manifest.json`, `preservation.json`, `spec_hash_changes.json`; input schema vẫn 1.0.0, package/validator/report 1.1.0.

## Kết quả

Đã mở route **POST /api/v1/companies/{company_id}/imports/validate** trên backend Agent2 hiện có, chỉ kiểm bundle JSON. Backend kiểm credential, expiry, tenant, membership active, permission data.import đúng DN **trước đọc/parse body**. Thay đổi/thu hồi membership có hiệu lực ở request tiếp theo. Role director không tự tạo quyền DN khác hay thay permission. Credential/policy mặc định không được tạo; không có QA bypass. Host/Origin được giới hạn loopback, credential/đối tượng DN khác không phản chiếu trong phản hồi lỗi.

Portal mới ở base commit có cổng mở khóa chung, nhưng chưa cung cấp identity/membership theo DN cho Agent2. Không tự xem cổng mở khóa là quyền nhập mọi DN. `auth.py` là adapter quyền phía backend từ policy file tin cậy có hash credential, actor/tenant, role/membership/permissions, hạn dùng; chưa thay thế hoặc tích hợp hệ thống identity thật của platform. Không thêm màn đăng nhập hoặc tài khoản/password store độc lập. Hỏng policy đóng quyền 503, thiếu/sai/hết hạn credential 401, sai membership/phạm vi 403. Policy đọc lại mỗi request; thời điểm thu hồi sau khi request đã được cấp quyền không tạo một cơ chế commit vì route chưa lưu dữ liệu.

Các trường/cột bắt buộc, kiểu số nguyên VND, mã và revision trùng, danh mục DN và liên kết cùng DN/revision dùng một schema core + profile Agent2. Lỗi required/nested reference đã chỉ đúng đường dẫn, bảng, dòng đếm từ 1, trường và cách sửa. Thiếu/blank/sai định dạng company_id là lỗi dữ liệu 422; ID DN hợp lệ ngoài quyền vẫn bị chặn 403 trước schema. JSON cú pháp sai có json_line/json_column riêng; không giả chúng thành dòng giao dịch. Mã/thông tin khách hàng không bị chép vào lỗi schema.

Số âm điều chỉnh hợp lệ và hai payment khác ID cùng hóa đơn/trả vượt vẫn được giữ. JSON khóa lặp, NaN/Infinity, body nén/sai Content-Type và kích thước vượt 10 MB/50.000 bản ghi bị từ chối. Không silently drop dữ liệu. API không đọc CSV/Excel trực tiếp, không lưu snapshot, gọi ML hoặc chuyển hàng đợi.

Report có analysis_limits theo DN và từng giao dịch bị ảnh hưởng: thiếu lịch sử tài khoản đúng NCC, chưa có chứng từ gốc đã xác minh, thiếu allocation hóa đơn, chưa có dấu vết approved. Có một file không phủ cho toàn bộ DN; source simulated/export không tự thành original verified. Revision document mới chưa xác minh không bị che bởi trạng thái verified cũ. Liên kết chứng từ hóa đơn được truy qua allocation; coverage chỉ nói có căn cứ liên quan trong bundle, không tự là đủ checklist nghiệp vụ hoặc kết luận giao dịch hợp lệ. Không suy min-history/ML ready từ số dòng.

## Path thực và trách nhiệm

| Path | Thay đổi |
|---|---|
| agent2/sme_fraud/auth.py | Backend policy adapter, hash credential, membership/permission, expiry/revocation |
| agent2/sme_fraud/validation_api.py | HTTP validate, kiểm quyền trước read, giới hạn transport, HTTP status và phản hồi |
| agent2/sme_fraud/imports.py | Report 1.1.0, trường lỗi cụ thể, coverage/analysis_limits theo giao dịch và revision |
| agent2/sme_fraud/review_server.py | Nối route, --auth-file/AGENT2_AUTH_FILE, health R1 validation_only; API cũ vẫn 410 |
| agent2/sme_fraud/core_manifest.py | Cập nhật metadata trạng thái, không thay thuật toán |
| shared/finance_input/src/finance_input/validation.py | Lỗi schema cụ thể/dedupe, phân biệt lỗi dữ liệu với sai quyền, table/row/field/action |
| shared/finance_input/src/finance_input/json_io.py | JSON strict, không khóa lặp hoặc hằng số không hữu hạn |
| agent2/tests/test_validation_backend.py | 31 test mới, HTTP thực và guard không đọc body, giới hạn nguồn |
| agent2/tests/test_input_contract.py | Giữ 32 test; đổi kỳ vọng lỗi cụ thể cho trường thiếu/sai kiểu |
| agent2/docs/BACKEND_VALIDATION.md | API, cấu hình quyền, mẫu lỗi và giới hạn tích hợp |

`module_map.csv` mở rộng mapping R0 trong đúng phạm vi CR-006. Không thay code Portal/Agent1/3/4. Ghi chú Agent2 trong README gốc được cập nhật để tránh hướng dẫn nhầm luồng cũ.

## Kiểm thử và bằng chứng

Từ `D:/agent22/agent2`, đặt PYTHONPATH=.;tests:

```powershell
& .venv/Scripts/python.exe -X utf8 -u -B -m unittest discover -s tests -v
& .venv/Scripts/python.exe -X utf8 -u -B -m unittest test_input_contract test_validation_backend test_transition_server -v
& .venv/Scripts/python.exe -m pip check
```

- **426 tests pass**, exit 0, skip 0, khoảng 200 giây: `native_tests.json/log`. Baseline trước task là 395; thêm 31 test, không giảm test cũ.
- **66 focused tests pass**, exit 0, skip 0: `focused_tests.json/log`, có từng testcase và kết quả máy. Kiểm lại trạng thái cuối sau khi bổ sung chẩn đoán company_id blank/sai định dạng trong lúc full suite đã khởi động. Không thay thuật toán sau full run.
- HTTP cổng tạm với credential/policy throw-away: valid **200**, thiếu record_id ở dòng 12 **422**, request sang C002 **403**; phản hồi thực lưu `http_examples.json`. Không cần người dùng tự tạo account/credential để chạy tests.
- Guard đọc body: Unauthorized/foreign-company/duplicate-Authorization không được gọi rfile.read; test dùng reader phát lỗi nếu bị chạm. Revocation được thử giữa hai HTTP request. Ngoài scope trả counts/capabilities/analysis_limits rỗng.
- Hash 56 tệp Python trong manifest R0 vẫn nguyên; test số học/rules/features/graph/ML cũ qua. `preservation.json` xác nhận parser tiền upstream giữ nguyên hash và diff Portal/Agent1/3/4 rỗng.
- `pip check` exit 0: `dependency_check.json`. Thư viện finance-input-contracts đã cài bản editable 1.1.0; dependency tính toán không đổi.
- Spec checksum được cập nhật có giữ hash cũ/mới; không giả hash nguồn ban đầu.

## Acceptance R1 và giới hạn

`acceptance.json` ghi pass cho R1-01/R1-05 tại contract/validate boundary; R1-02/03/04/06/07 vẫn blocked cho điều kiện toàn mốc. Phần validate của R1-07 đã kiểm được, nhưng user DN A gọi upload/preview/commit/snapshot B chưa thể nghiệm thu vì các API đó chưa có. Không gắn PASS giả cho toàn bộ R1 hoặc sửa stage runner để vượt gate.

Chưa làm: identity/membership Portal chung, multipart CSV/Excel và ánh xạ dòng gốc, preview hash/context lock, snapshot bất biến/atomic commit/idempotency, feature bridge và replay nhóm đồng thời. Validation report không là commit token. Các API ghi/chấm/hồ sơ cũ tiếp tục 410. Health pipeline_ready=false, active_delivery=false.

D-02 posted/D-16 VND giữ profile thử; D-03 min-history, D-04 trọng số, D-14 checklist không tự chốt. D-10/D-18/D-19 vẫn chặn dữ liệu thật/production. Việc tiếp nối trong R1 là luồng nhập/preview/snapshot với identity và file adapter; chưa chuyển R2.
