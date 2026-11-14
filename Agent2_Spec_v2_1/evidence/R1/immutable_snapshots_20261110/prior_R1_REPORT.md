# REPORT — R1, phần hợp đồng đầu vào

**Cập nhật CR-006:** đã bổ sung [API kiểm tra backend theo quyền DN](backend_validation_20261110/REPORT.md) với validator/report 1.1.0. Báo cáo dưới đây giữ bằng chứng của phần hợp đồng CR-005; các câu "chưa có API validate" mô tả trạng thái tại lần đó. R1 vẫn PARTIAL vì preview/commit/snapshot/feature replay và identity Portal chưa nối.

- spec_version: 2.1; CR-005, ngày 10/11/2026.
- milestone status: **PARTIAL**. Phần hợp đồng/validator local: **READY_FOR_REVIEW**, chưa duyệt DONE hoặc release.
- Người thực hiện kỹ thuật: Codex; người duyệt nghiệp vụ/triển khai: chưa được chỉ định.
- Local base commit: `3cae5a3bba535694235179651b2e5daee8237656`, working tree có thay đổi chưa commit từ lần dọn R0. Không reset/clean/merge hay push.
- Git được đọc: remote `Khanhhh239/Multi-Agent-Finance`, platform `140a741e7290e70a783496e56e9ef48268a00f5d`. Ref các nhánh riêng lưu trong `remote_heads.txt`; file/hash tại `git_audit.json` và `shared/finance_input/UPSTREAM.json`.
- Nguồn/spec/fixture hashes: `import_contract.json`, `fixture_manifest.json`, `artifact_manifest.json` và SHA256SUMS của spec. Không coi bộ hash cập nhật là hash nguồn ban đầu.

## Phạm vi và kết quả

Người dùng giao chốt hợp đồng dữ liệu đầu vào, đối chiếu Git agent khác để tái sử dụng, giữ số âm điều chỉnh. Đã đọc validator/import mới trên remote platform của Agent1, CFR/provenance/auth/repository của Agent3, ledger/build của Agent4 và Portal. Nhánh local được giữ nguyên; không merge code platform mới đè reset Agent2.

Tái sử dụng nguyên mã `agent1/agent1_service/ingest/money.py`, SHA256 `b6e16fb7721d5325e50dc5dfd9fa1afcfe1dde9907abb97aa8ceae73bee4d5c4`. Bộ xử lý này đã hỗ trợ tiền chính xác và dấu âm; không mô tả lỗi parser cũ thành lỗi remote mới. Profile Agent1 vẫn có điều kiện số tiền dương trừ điều chỉnh hóa đơn và kiểm tra thu vượt; ngày được chuẩn hóa về ngày VN, không giữ giờ. Không áp nguyên profile đó cho Agent2. Agent3 cung cấp mẫu thiết kế tenant/revision/provenance và phân biệt thiếu/xác minh, nhưng CFR không phải hợp đồng toàn sổ chi. Ledger Agent4 là simulator. Portal chưa có validator domain chung và route Agent2 cũ đang đóng.

Đã xây package riêng `shared/finance_input` với JSON Schema 1.0.0, kiểu nguyên VND, kiểm scope/identity/revision/time, dependency jsonschema; Agent2 dùng profile `agent2/sme_fraud/imports.py` theo mapping R0. Không kéo theo pandas/FastAPI/Pydantic hoặc app của agent khác. Chưa migrate các agent khác sang package này.

Gói gồm doanh nghiệp, giao dịch, NCC, hóa đơn, allocation nhiều–nhiều, nhân viên, phê duyệt, chứng từ và lịch sử ngân hàng NCC tùy chọn. Mọi dòng có tenant, công ty, ID, revision, observed_at, effective_at, nguồn. Sửa thông tin tạo revision; điều chỉnh nghiệp vụ giữ số tiền có dấu/lý do/tham chiếu bản gốc. Không nhập float hay tự gán thời điểm nguồn. Tham chiếu sai tenant/DN/revision bị từ chối. Chấp nhận khoản trả vượt và hai payment khác ID cùng nghĩa vụ để detector xử lý sau; không xóa dòng rủi ro ở lớp nhập.

Thiếu nguồn bổ sung tạo warning/capability unavailable, không chặn toàn bộ nguồn đang có. Chứng từ có nguồn simulated/export/original, hash, verification riêng; có original/hash không tự là verified. Quyền evidence.verify và căn cứ/thời điểm là điều kiện profile local; API xác thực/chính sách kiểm chứng nguồn thật chưa nối.

Hướng dẫn và mapping: `agent2/docs/INPUT_DATA_CONTRACT.md`. Fixture hoàn toàn mô phỏng: `agent2/tests/fixtures/input_contract_v1.json`.

## Thay đổi và kiểm chứng

| Path | Thay đổi |
|---|---|
| shared/finance_input | Package dùng chung, schema, parser trích nguyên mã, provenance nguồn |
| agent2/sme_fraud/imports.py | Profile, báo cáo lỗi/cách sửa, liên kết, signed adjustment, verification và helper as_of |
| agent2/tests/test_input_contract.py | 32 test, nhiều subcase về tiền/time/scope/điều chỉnh/nguồn đến muộn |
| agent2/tests/fixtures/input_contract_v1.json | C001/C002 cùng ID, điều chỉnh âm, hai payment trả vượt cùng invoice |
| agent2/requirements*.txt, README.md, docs/INPUT_DATA_CONTRACT.md | Cách cài/chạy, phiên bản thực đo, ranh giới tích hợp |
| 04, 98, 99, CHANGE_REQUESTS, evidence/R1 | Contract, tiến độ, quyết định kỹ thuật và evidence phần đã làm |

Lệnh native tại `D:/agent22/agent2` với `PYTHONPATH=.;tests`:

```powershell
& .venv/Scripts/python.exe -X utf8 -u -B -m unittest discover -s tests -v
& .venv/Scripts/python.exe -X utf8 -u -B -m unittest test_input_contract -v
& .venv/Scripts/python.exe -m pip check
```

- Full suite: **395 tests, exit 0, skip 0**, khoảng 194,5 giây. `native_tests.json` và `native_tests.log` có command/cwd/log hash.
- Chỉnh chặt phút offset timezone sau full run; kiểm lại **32 contract tests, exit 0**, `contract_tests_final.json/log`. Không đổi thuật toán hoặc feature lõi sau full run.
- Baseline R0: 363 test qua; lần này thêm 32 contract test. `retained_core_audit.json` đối chiếu 56 tệp Python có trong manifest candidate R0: **0 thay đổi**. Không thay hệ số/ngưỡng, fit model hay đánh giá accuracy.
- `pip check`: exit 0, không có dependency hỏng. Agent1/3/4/Portal: `git diff --name-only` rỗng, lưu tại `integration_audit.json`.
- Full wrapper/checker R1 chưa đủ điều kiện READY_FOR_REVIEW; không tạo report native giả gắn các ID API chưa tồn tại. Acceptance ghi rõ pass/blocked theo phạm vi.

## Acceptance R1

| ID | Quan sát | Kết quả |
|---|---|---|
| R1-01 | Hai DN cùng ID không trộn; không dùng vendor C002 để lấp vendor C001; kiểm tại boundary contract | pass (unit boundary) |
| R1-02 | Helper đã loại chứng từ/revision biết muộn khỏi as_of cũ; chưa nối tạo feature | blocked cho acceptance đầy đủ |
| R1-03 | Chưa có preview/commit và khóa hash/context | blocked |
| R1-04 | Chưa có snapshot transaction, chưa thử retry 10 lần | blocked |
| R1-05 | Giữ dấu điều chỉnh hợp lệ, lỗi có lý do/cách sửa; thiếu lịch sử chỉ cảnh báo, không bỏ dòng | pass |
| R1-06 | Helper chọn dữ liệu bất biến theo thứ tự; chưa có replay feature nhóm đồng thời | blocked cho acceptance đầy đủ |
| R1-07 | Deny scope ở thư viện trả counts/capabilities rỗng; chưa có API auth/permission | blocked cho acceptance đầy đủ |

Các kết quả này không thay cho kiểm quyền HTTP, storage concurrency, immutable preview token hoặc dữ liệu thật.

## Quyết định và việc chưa làm

CR-005 giao riêng phần hợp đồng local. D-02 posted và D-16 VND là profile thử; D-01 chưa được giả ghi APPROVED. Không tự chọn DB mới. D-10/D-18/D-19 vẫn chặn nguồn thật/production; D-03/D-04 không bị tự chốt qua capability.

Bundle hiện là tập đóng theo tham chiếu. Nhập tăng dần phải ghép với snapshot nền đúng quyền trước kiểm tra, không xóa dữ liệu cũ không liên quan. AccessScope chỉ là context backend tin cậy; không nhận quyền từ browser, không bảo vệ file I/O trước khi xác thực. Schema/validator không kiểm chứng nội dung file gốc chỉ qua hash. Code chưa cung cấp API, parser CSV/Excel, file row mapping, preview/commit, DB, snapshot bất biến, audit store, feature adapter hay simultaneous replay. Chưa đổi UI, ML, threshold, queue hoặc release.

Kết thúc phần được giao: hợp đồng và validator có thể rà ngay; R1 còn PARTIAL. Việc tiếp nối là API nhập/mapping/preview/commit với quyền và snapshot, rồi nối feature và chạy đủ 7 acceptance R1. Không tự chuyển R2.
