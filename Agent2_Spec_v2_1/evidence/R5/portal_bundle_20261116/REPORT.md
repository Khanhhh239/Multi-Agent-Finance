# CR-062 — Portal chung và giao việc từ vụ

- spec_version:2.1; ngày16/11/2026; thực hiện:Codex.
- Trạng thái: **READY_FOR_REVIEW kỹ thuật cho Portal shadow**. Toàn R5,
  production và full cloud HE theo bundle chưa nghiệm thu.
- Base commit:`f203b39828f567171916b5b4744728ed4b63d17f`; uncommitted.
  Workspace có nhiều thay đổi trước task; không reset phần agent khác.
  `manifest.json` ghi SHA-256 nguồn/evidence theo phạm vi này, không đại diện
  cho toàn bộ dirty tree. Nguồn giao việc/phụ thuộc: TASK.md.
- Giữ OPEN D-04/05/06/07/09/17/18/19 và các quyết định policy/quality liên quan;
  không tự đặt SLA, trọng số, budget hoặc mandatory routing sản xuất.

## Kết quả

Portal node có release service dùng **Vụ cần rà** làm điểm vào chính. Người dùng
chọn DN/snapshot → **Chạy phân tích** → vụ từ queue shadow → ghi kết quả → giao
task từ chính vụ. Cấu hình vẫn qua lifecycle/director API riêng. Không tạo
pipeline chấm riêng cho UI: dùng nguyên CR-061, snapshot/feature/model/bundle
đã ghim và cơ chế gộp vụ trước ngân sách hiện hữu.

Phạm vi 35 luật lấy từ analysis/packet đã lưu, không từ chuỗi quảng cáo UI.
Snapshot thiếu nguồn vẫn unavailable; packet cũ thiếu phạm vi không được tự gắn
35 luật. Snapshot chưa có hợp đồng nguồn đủ được liệt kê nhưng khóa chạy, nói
rõ lý do; không chuyển sang engine P1 thay thế. Phép so sánh HE P1/ML cũ giữ
lịch sử, ghi rõ không đại diện 35 luật. Đây chưa phải một benchmark35 mới hoặc
bằng chứng ML hiệu quả hơn luật.

Import tiếp tục validate/preview/confirm snapshot cũ; nút sau lưu chuyển đúng
DN/snapshot tới màn chung. Portal nhớ page/DN/run theo actor/context hiện hành,
kiểm quyền lại server; không đổi legacy herun thành bundle run. Link từ task
trở lại đúng vụ nguồn. Kết quả/API/JSON/CSV giữ triple snapshot/run/bundle.

Task dùng RemediationStore/ActionTask hiện hữu, thêm source_binding optional
do server đọc immutable packet: snapshot/run/bundle/pin/review/canonical-case/
as_of. Bản ghi task cũ và schema DB v2 giữ nguyên. Task case key=review_id,
canonical case nằm trong binding. Revision, receipt, audit, đổi người phụ trách
và report giữ binding. API kế toán không nhận binding/case/score/model tự khai.
Người dùng chọn bộ phận và hạn tường minh; UI không tự đặt SLA. Retry mất phản
hồi và hai tab cùng loại việc đang mở không tạo trùng. Kiểm current auth trong
transaction trước commit; thu hồi quyền làm rollback cả task/receipt.

Task/report không xác nhận danh tính cá nhân Portal dùng chung, tự đóng vụ,
verified fraud hay nhãn train. Lifecycle nộp/xác minh/hoàn tất dùng phần xử lý
công việc hiện hữu; attachment phiếu không tự thành chứng từ verified hoàn tất
task. CSV giữ một dòng/vụ, thêm task IDs/status/bộ phận/hạn, không nhân số tiền.

## Đường dẫn thay đổi

| Nguồn | Mục đích |
|---|---|
| `bundle_reviews.py`, `bundle_workspace_api.py` | Summary baseline đã ghim, task wrapper theo packet, DTO/report/task counts và kiểm quyền |
| `remediation_store.py`, `remediation.schema.json` | Source binding optional, audit/receipt/revision, recheck trước commit, chống dedup nhầm nguồn |
| `review_server.py`, `workbench.py`, `portal/agent2_bridge.py` | Entry/settings chung, inject kho task và exact route allowlist |
| `web/bundle-workspace.html/js`, `web/pipeline-releases.css` | DN/snapshot/run, baseline/giới hạn, form giao việc, task retry/reload và nav desktop/mobile |
| `web/index.html`, `web/workbench.js` | Import chuyển đúng nguồn vào bundle, không chạy P1 thay thế |
| `web/workspace.html/js`, `portal/static/app.js` | Nhãn lịch sử P1, link nguồn task, Portal nhớ DN/run và migration preference cũ |
| `tests_he/test_bundle_workspace.py`, `scripts/check_bundle_workspace_ui.py` | Kiểm thử task/source/RBAC và luồng thật qua Portal/Chrome |
| `agent2/docs/BUNDLE_ORCHESTRATOR.md`, bốn spec CR-062 | Hướng dẫn, contract và phạm vi nghiệm thu |

## Kiểm thử

Mọi fixture là mô phỏng, Portal/Agent2/Chrome trên tiến trình/port tạm. Không dùng
mật khẩu thật từ hội thoại; không restart/deploy Portal live hoặc đổi khóa/model.

| ID | Kỳ vọng | Quan sát | Kết quả |
|---|---|---|---|
| CMD-01 | Regression liên quan không lỗi hoặc skip | 149 tests, 0 failure/error/skip;239.263s | pass |
| CMD-02 | Portal C001/C002 từ chạy đến task/export và import transition | 12 nhóm browser/API pass | pass |
| Task binding | Server giữ đúng source, không nhận binding/case client tự khai | HTTP/direct tests exact triple, cross-company/run và extra fields bị chặn | pass |
| Task restart/CAS | Không đổi nguồn, task duy nhất khi retry, revision sau đổi bộ phận | Tests restart/report/lifecycle pass; C001 mất phản hồi sau commit vẫn1 task | pass |
| Thu hồi quyền | Không commit task khi quyền đổi | Patch revoke trước commit: rollback task/receipt | pass |
| Portal reload | C002 và run không quay về C001 hoặc HE/P1 cũ | Outer iframe + reload giữ C002/bundle/run | pass |
| Import | Upload→preview→save chuyển đúng snapshot | Native source import thật qua Portal; DN/snapshot chọn sẵn ở bundle workspace | pass |
| Report/feedback | Không tự thành verified fraud/label, checksum export đúng | Mỗi DN1 inconclusive,1 task;JSON/CSV giữ triple/hash;training_eligible=false | pass |
| Tương thích HE | Không fallback rõ, không sửa worker/TTL/key | Regression guard HE và API HE cũ pass; không HE mới chạy ở task này | pass guard, full HE blocked |

CMD-01, từ repo root với `PYTHONPATH=D:\agent22\shared\finance_input\src`:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_bundle_workspace --suite test_pipeline_release --suite test_release_shadow_plan --suite test_validation_study --suite test_case_queue --suite test_remediation --suite test_he4_config_api --suite test_portal_auth --suite test_workspace_api --suite test_pipeline_benchmark --suite test_batch_training_portal --suite test_review_store --suite test_review_api --suite test_review_rule_evidence --report .runtime/release-acceptance-20261116/portal-bundle-tasks-regression.json
```

CMD-02, cùng PYTHONPATH:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/check_bundle_workspace_ui.py --output .runtime/release-acceptance-20261116/portal-bundle-tasks-browser-verified
```

Exit0. Log test-by-test:`regression.json`, `browser-report.json`. Hai report
JSON/CSV là dữ liệu mô phỏng, không có khóa/credential/DB. Screenshot desktop/
mobile đã xem lại; nav được bổ sung khoảng cách và wrapping sau visual QA.
Node --check bốn JS và scoped git diff --check qua (Git có warning LF/CRLF).
Lượt focused đầu có1 lỗi assertion bytes/str trong test HTML, đã sửa test;
full regression và browser sau đó qua, không bỏ testcase.

## Giới hạn / nghiệm thu còn lại

- Đây là local enterprise shadow; chưa deploy/restart live hoặc push GitHub.
  Node live cần nạp backend/assets/Portal mới qua backup/release riêng. Bundle
  cũ sai runtime fingerprint phải qua quy trình qualify/approve; không tự đổi pin.
- Full HE bundle chưa có executor: yêu cầu cloud bị chặn/unavailable trước chấm
  rõ, không gửi raw cloud. ECOD local không trở thành model HE vì đổi giao diện.
- Chưa thay comparison P1 bằng benchmark35 mới; main run đã dùng baseline35 thực.
- Chưa đủ toàn bộ R5/R6, nghiệm thu chuyên viên/dữ liệu thật, quality gates và
  release active. Phản hồi mô phỏng không chứng minh độ chính xác gian lận.
- Bộ phận/actor audit không thay xác minh danh tính người rà. Không migrate
  legacy HE review namespace hoặc tự phê duyệt labels/tasks/chứng từ.

## Kết thúc

CR-062 READY_FOR_REVIEW kỹ thuật. Giữ các mục chưa nghiệm thu ở blocked trong
acceptance.json; reviewer người thật quyết định sau review. Không ghi DONE R5.
