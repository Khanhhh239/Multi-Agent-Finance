# Tiến độ spec v2.1

CR-062 (16/11/2026): **READY_FOR_REVIEW kỹ thuật, Portal shadow**.
Portal entry dùng luồng bundle chung; nhập/preview/lưu chuyển đúng snapshot,
phạm vi 35 luật từ analysis đã lưu và giới hạn nguồn rõ. Giao task ngay trong vụ
có bộ phận/hạn xử lý và source_binding server; retry không tạo trùng, không sinh
nhãn/đóng vụ. 149 regression tests và 12 nhóm Portal/Chrome đã chạy; xem
evidence/R5/portal_bundle_20261116/REPORT.md. Production/full HE/R5 toàn bộ
chưa nghiệm thu; không restart/deploy live hoặc push.

CR-061 (16/11/2026): **READY_FOR_REVIEW kỹ thuật, shadow tại DN**.
Nối operator chọn snapshot/chạy bundle → queue → packet phiếu → feedback/report.
Giữ snapshot/run/bundle xuyên suốt, candidate/evidence riêng, review CAS/lease/
attachment và DTO kế toán; không nhãn gian lận tự sinh hoặc plaintext fallback
cho yêu cầu HE. Kiểm thử và giới hạn: evidence/R6/bundle_orchestrator_20261116/REPORT.md.
Chưa full HE bundle/production, chưa restart/deploy live hoặc DONE R0–R6.

CR-060 (16/11/2026): **READY_FOR_REVIEW kỹ thuật; production BLOCKED**.
Tiếp tục handoff release/rollback: ghim validation/model/reference/calibration/
fallback và case policy thành bundle1.1; chạy thật tại DN đến queue shadow qua
checkpoint+receipt, giữ quota khi retry/rollback. Không giả HE hoặc phê duyệt
quality; chưa toàn R6/full pipeline HE. Báo cáo và kết quả kiểm thử riêng:
evidence/R6/linked_shadow_20261116/REPORT.md. Không sửa Portal/key/model live.

CR-059 (16/11/2026): **READY_FOR_REVIEW kỹ thuật — production BLOCKED**.
Đã xây bundle/kho metadata được bảo vệ, gate detector smoke, approval staging,
CAS/idempotency, pin mỗi lượt, rollback/audit và UI director Portal.100 test và8
nhóm browser/API qua; chặn API tạo vụ active khi bật release service, bảo toàn
DB/quota/task/nhãn và giao nhận cũ. Xem evidence/R6/REPORT.md và
agent2/docs/PIPELINE_RELEASE.md. Đây là phần release infrastructure/staging,
chưa nghiệm thu toàn R6: chưa full executor HE/ensemble/queue theo bundle,
quality gates/owner decisions chưa đóng, monitoring drift/fallback/backlog/review
chưa đủ. Không deploy/restart live hoặc tự chuyển R0–R6 sang DONE.

CR-058 (15/11/2026): **READY_FOR_REVIEW kỹ thuật** — kiểm tra lại Portal/shadow,
đối chiếu PDF/spec;115 test riêng biệt và9 nhóm browser/API đạt. Thêm benchmark
chung đúng snapshot/cutoff, policy thử5 giao dịch; giữ missing/model/label rõ.
Chưa validated ensemble, active case/budget/delivery hoặc release gate; xem
../reports/pipeline_recheck_20261115.md. Không tự chuyển R0–R6 sang DONE.

CR-057 (15/11/2026): **READY_FOR_REVIEW kỹ thuật** — train nhiều batch bản mã,
trọng số giữ qua batch/epoch, holdout riêng; giới hạn build4 updates được giữ.
C001/C002 mỗi DN8 train/4 evaluation, native4 cập nhật khớp oracle; C001 khôi phục
SIGKILL từ checkpoint1, không đổi job/key/build. Xem ../reports/he_training_batches_20261115.md.
Chỉ mô phỏng/operator CLI, chưa Portal live, accuracy/production hoặc DONE R0–R6.

CR-056 (15/11/2026): **READY_FOR_REVIEW kỹ thuật** — danh sách xác minh nhãn
snapshot/phiên bản trên web, null giữ trống, căn cứ và audit theo tài khoản;
lock/reopen/retry không mất nhãn cũ. Xem ../reports/label_verification_20261115.md.
Chỉ nghiệm thu mô phỏng/cô lập; chưa live rollout, consent từ bộ nhãn khóa hoặc
xác minh danh tính từng người. Không tự chuyển gate R0–R6 sang DONE.

CR-055 (15/11/2026): **READY_FOR_REVIEW kỹ thuật** — snapshot→HE training input
read-only, binary pair hiện có, pin nguồn/selection/cutoff/mapping trước encrypt.
28 test +2 DN native encryption/upload đạt; template nhãn null, 0 job train.
Giữ core33/engine và live; chưa train batch lớn/Portal. Xem
../reports/he_training_snapshot_adapter_20261115.md.

CR-054 (15/11/2026): **READY_FOR_REVIEW prototype kỹ thuật** — branch train có
nhãn encrypted, consent và nhận/phê duyệt model shadow; 4 dòng/2 biến, không
chuyển phiếu rà thành nhãn fraud. Dữ liệu/nhãn nghiệm thu là mô phỏng, không
thay Portal/model/key/luật hiện hữu hoặc chốt gate. Nguồn và kết quả kiểm chứng:
../reports/he_supervised_training_20261115.md.

CR-053 (14/11/2026): **FIXED / READY_FOR_REVIEW kỹ thuật** — reload Portal giữ
C002, màn hình, snapshot và as_of; quyền mới được kiểm trước restore. Routing17,
workspace12 và auth22 đạt; live asset5/5 khớp source/no-store, không restart hoặc
đổi model/key/quyền/DB. Xem ../reports/portal_company_routing_20261114.md; chưa
đăng nhập live nghiệm thu người dùng, không tự chuyển gate R0–R6 thành DONE.

CR-052 (14/11/2026): **ACTIVATED demo local / READY_FOR_REVIEW kỹ thuật** —
đã fit offline và ghim C001 IF/C002 ECOD +RobustZ đúng bridge contract, nguồn
mô phỏng 32train/8reference/5eval mỗi DN; 5/5 dòng ML/thống kê khả dụng. 84 test
đạt, setup4 chạy lại sau idempotent activation đạt, Chrome4 dùng model pins thật
và snapshot copy đạt. Giữ4 model/14 snapshot cũ và6 file quyền/config/HE/key;
không nâng quyền Portal, không HE mới/accuracy/full R2. Evidence R2/rule_bridge_models_20261114.

CR-051 (14/11/2026): **READY_FOR_REVIEW kỹ thuật local** — mixed/all-future
candidate không làm hỏng batch nguồn đầy đủ. Giữ đủ dòng, unavailable/null và
lý do; eligible-only feature/model, không giả core result khi thiếu nguồn nhìn
thấy. 61 backend/API, 17 HE liên quan, 10 bước UI đạt; ECOD/RobustZ thật giữ
nguyên điểm 4 dòng hợp lệ trong batch5. Feature/model contract không đổi,
chưa deploy live. Xem reports/rule_cutoff_fix_20261114.md và evidence R2.

CR-050 (14/11/2026): **READY_FOR_REVIEW kỹ thuật local** — đủ 35 luật qua
profile nguồn đầy đủ vào upload/preview/commit/analyze/UI, không chỉ chạy demo
offline. 120 gói C001/C002 và 140 đối chiếu trúng/control đạt, UI 6 bước đạt;
số test hồi quy cuối ở tests.json. Bảo toàn thiếu nguồn, phân biệt source/row,
scope D/F4 và quyền xem chi tiết. Không đặt 70–80%, đổi kernel/model/HE/queue
hoặc live. Canonical sparse vẫn bốn adapter; profile mới chưa bridge ML/HE35.
[Bằng chứng](evidence/R2/full_rule_pipeline_20261114/REPORT.md).

CR-049 (14/11/2026): **READY_FOR_REVIEW kỹ thuật, baseline HE còn PARTIAL** —
ML CKKS chấm mới hai DN trên snapshot 1.2, giữ model/33 feature; sai lệch lớn
nhất khoảng 0.000051, có đổi thứ tự trong dung sai nhưng không đổi tập chọn.
2/2 ca P1 Concrete native khớp. So baseline local P1/E3/B5/E4: 3/5, kết hợp
thêm T04/T02 thành 5/5 mỗi DN. 299 HE và 82 focused đạt; selection subset 10 đạt.
E3/B5/E4 chưa HE, 31 luật chưa nối snapshot; không coi là full HE/accuracy
hoặc đổi live. [Bằng chứng](evidence/R2/expanded_baseline_he_20261114/REPORT.md).

CR-048 (14/11/2026): **READY_FOR_REVIEW kỹ thuật local** — nối B5/E4 qua nguồn
point-in-time, snapshot bất biến và API phân tích có xác thực. Input 1.2.0
opt-in thêm hai trường NCC, giữ schema/default 1.0/1.1 và dữ liệu cũ. 20/20
parity và 4/4 thiếu nguồn đạt trên C001/C002; 303 focused/regression pass.
P1/E3/B5/E4 là bốn evaluator khi đủ nguồn, 31 còn lại chưa nối. Master-quality
0 điểm giao dịch và alias B5/E4 không cộng hai lần. Không HE mới/deploy/fit,
queue hoặc duyệt toàn R2. [Bằng chứng](evidence/R2/vendor_identity_snapshot_20261114/REPORT.md).

CR-047 (14/11/2026): **READY_FOR_REVIEW kỹ thuật local**, theo lựa chọn của
người dùng: đủ 35 luật chạy/đối chiếu ở node DN trước, sinh nguồn test; HE sau.
120 gói mô phỏng C001/C002 cho 140 kiểm tra trúng/đối chứng và 70 thiếu nguồn;
đối chiếu engine giữ lại, D theo tập/cutoff, E4 alias B5 không cộng lần hai.
53 focused/regression tests đạt. Có [hướng dẫn](../agent2/docs/NATIVE_RULE_NODE.md)
và [bằng chứng](evidence/R2/native_rules_node_20261114/REPORT.md).
Đây là source profile native riêng, chưa nối 33 luật còn lại vào snapshot 1.1.0
hoặc HE/Portal. Native âm/late-posted bị từ chối tường minh; canonical P1 có
dấu giữ nguyên. Không fit, đổi trọng số/queue, deploy hoặc nghiệm thu nghiệp vụ.

CR-046 (14/11/2026): **READY_FOR_REVIEW cho kiểm kê, không phải mở rộng luật** —
[bảng 35 luật](../reports/rule_coverage_status_20261114.md) tách source map,
gap schema/import, evaluator snapshot và HE. Đủ 35 khai báo nguồn, chỉ P1/E3
có evaluator snapshot và chỉ P1 nối HE. Replay local C001/C002 bằng nguồn mô
phỏng công khai kiểm trạng thái đủ 35 luật trên 8 giao dịch/DN; không dùng
không áp dụng như đã kiểm thử thành công, không suy thiếu dữ liệu thành 0.
Không truy cập DB live/khóa, fit, gọi worker, thay schema hoặc restart Portal.

CR-045 (14/11/2026): **READY_FOR_REVIEW kỹ thuật, chưa có bằng chứng hiệu quả** —
so lựa chọn trên cùng run/kỳ C001/C002 đã lưu, B=5 tối đa mỗi phương án/DN,
chính sách người dùng chọn là luật trước rồi ML bù chỗ trống. Plan bất biến,
ghim nguồn/model context; phản hồi chỉ đổi chỉ số, không đổi tập chọn. P1 có
3 cảnh báo/DN; kết hợp thêm T04/T02 thành 5/DN, không thay khoản luật. Thiếu
phản hồi giữ null, tách không áp dụng/thiếu nguồn/no-hit P1; chưa accuracy
hoặc đổi hàng đợi. Xem [bằng chứng](evidence/R2/selection_comparison_20261114/REPORT.md).

CR-044 (13/11/2026): **READY_FOR_REVIEW cho luồng kỹ thuật cốt lõi** — nối
không gian làm việc theo doanh nghiệp từ nhập CSV/Excel/JSON, snapshot và
phân tích tới phiếu rà lưu server, tài liệu bổ sung, lịch sử và báo cáo.
Giữ đúng nguồn/lượt chạy, phân quyền cấu hình, xử lý gửi lại khi mất phản hồi
và tạo lượt mới sau lỗi terminal. Sửa diễn giải trục đồ thị, bố cục điện thoại
và quá nhiều yêu cầu resume khi đang chờ quyền. Bằng chứng cùng giới hạn tại
[workspace core](evidence/R5/workspace_core_20261113/REPORT.md). Không tự duyệt
toàn spec, hiệu quả nghiệp vụ hoặc policy hàng đợi.

CR-043 (13/11/2026): **READY_FOR_REVIEW cho kiểm thử kỹ thuật; chưa nghiệm thu nghiệp vụ** — nghiệm thu P1 trên Portal với hai snapshot 8 dòng mới. C001 (`herun_a41f1c89c0b04bb9bd85021731bdaf7f`) và C002 (`herun_83f30523ede5495a97a9957a07a000dc`, nối run mới vì `herun_1df14750934b4adba8469f6fbba1290d` đã `HE4_EXPIRED`) đều đã hoàn tất HE (12/12 phép tính `done`, `generation=1`) và đối chiếu đủ 8 dòng/8 phiếu (`all_rows_match: true`), mở căn cứ, kiểm ảnh và reload cùng run (`portal_timeout_unchanged: true`, `login_count: 2`, `browser_errors: []`). Sửa phiếu thiếu căn cứ riêng của P1 và lỗi phản hồi tải nền Portal xóa phiên đăng nhập mới. 21 focused review/source, 9 comparison/evidence (có giao), 16 browser SSO, hai ca race đăng nhập/đăng xuất và kiểm tra công cụ mở lại run đạt. Bốn GET dùng sai đường dẫn DN đều 404. Không ghi kết luận nghiệp vụ, nhãn train hoặc đổi model/khóa/quyền/policy. Xem [đối chiếu Portal P1](evidence/HE/p1_portal_recheck_20261113/REPORT.md).

CR-042 (13/11/2026): **READY_FOR_REVIEW** — bổ sung nguồn demo P1 theo yêu cầu.
C001/C002 có snapshot mới 8 bản ghi, hóa đơn/phân bổ/coverage kèm manifest;
giữ ca thiếu lịch sử unavailable. Đối chiếu thủ công/engine/reference đạt,
13 focused HE + 53 P1 regression + 2 browser import checks đạt. Native HTTP
C001/C002 mỗi DN 5/5 phép tính P1 đạt, gồm riêng/nhóm đồng thời và lịch sử có
điều chỉnh âm. Không đổi model/khóa/quyền/ngân sách/hàng đợi. Xem
[bằng chứng nguồn P1](evidence/HE/p1_sources_20261113/REPORT.md).

CR-041 (13/11/2026): **IN_PROGRESS cho toàn bộ spec; READY_FOR_REVIEW cho bốn
profile HE giới hạn.** Đã nối snapshot point-in-time, coordinator, DPAPI/helper
Concrete thật, WSL lifecycle, CSV/Excel, cấu hình theo quyền và phiếu server.
Portal native C001/C002 mỗi DN 5 dòng, worker/DN hard crash và HTTP P1/graph tối
ưu đạt. Đã backup và bật local Portal 8800/Agent2 8766/worker 8868+8869; nghiệm thu
live sau khi người dùng đăng nhập đạt: mỗi DN 5 dòng/5 phiếu, reload cùng run,
không JS error, đúng một parent/DN. Không tự duyệt toàn catalog HE,
routing/policy, danh tính từng người, cloud public hoặc production. Xem
[trạng thái và phần còn thiếu](../agent2/docs/HE_FOUR_BRANCH_PROGRESS.md).

AI chỉ cập nhật tới READY_FOR_REVIEW. DONE cần người duyệt thực, tên/ngày và evidence; checker không xác thực danh tính người duyệt. Dùng quyền repo/CI để thực thi kiểm soát.

**Hiện hành: HE-AC-01 FIXED_READY_FOR_REVIEW theo CR-040** — managed request còn TTL/state đã khôi phục hard crash 2/2 trên model C001/C002; 202 HE/742 native/14 browser pass. Các dòng OPEN/0-of-2 bên dưới là lịch sử trước sửa. Không mở lại failed/expired/legacy cũ hoặc tự duyệt production/R0–R6. [Báo cáo](evidence/HE/worker_recovery_20261112/REPORT.md).

| Mốc | Trạng thái | Người phụ trách | Bị chặn bởi | Evidence | Người duyệt | Ngày duyệt |
|---|---|---|---|---|---|---|
| R0 | READY_FOR_REVIEW | Codex thực hiện kỹ thuật; nhóm chưa chỉ định người duyệt | Cần người duyệt thực xác nhận; CR-005 giao riêng phần hợp đồng R1 local, không duyệt production | [Báo cáo và evidence](evidence/R0/REPORT.md) | — | — |
| R1 | READY_FOR_REVIEW | Codex thực hiện CR-005…011 | BR-07/08 đã sửa: formal 527 tests/7 mandatory IDs pass, checker exit 0, bộ rà 8/8 và 528 giá trị khớp. Chờ reviewer thật; fixture mô phỏng không duyệt dữ liệu thật/production. CR-012 giao riêng bước chuẩn đầu ra R2, không tự duyệt DONE R1 | [Báo cáo hiện hành](evidence/R1/REPORT.md), [Sửa thiếu nguồn BR-08 + gate mới](evidence/R1/prior_history_fix_20261111/REPORT.md), [Sửa quyền đọc BR-07](evidence/R1/verification_read_fix_20261111/REPORT.md) | — | — |
| R2 | PARTIAL | Codex thực hiện CR-012…027 | Bốn nhánh HTTP/UI READY_FOR_REVIEW: 742 backend pass, chỉ đọc model ghim đúng DN; thiếu/sai phiên bản unavailable. Kernel/33 feature/model giữ nguyên; canonical chỉ P1/E3, tổng incomplete/null. Còn evaluator khác/benchmark/active/UI quản lý, D-03/04/09 và full gate | [Bốn nhánh](evidence/R5/four_branch_20261112/REPORT.md), [Tổng quan](evidence/R2/REPORT.md) | — | — |
| R3 | NOT_STARTED | Chưa gán | Phần phụ thuộc R2; decision theo phạm vi | evidence/R3/REPORT.md — chưa có | — | — |
| R4 | NOT_STARTED | Chưa gán | R1 contract/snapshot cho đối chiếu+hồ sơ; R3 cho tích hợp task/report | evidence/R4/REPORT.md — chưa có | — | — |
| R5 | PARTIAL | Codex thực hiện CR-024…027 được giao riêng | UI bốn nhánh + Portal READY_FOR_REVIEW: 742 backend, 11 Portal, 14 demo, 16 SSO browser, 19 local browser pass. Cập nhật riêng Agent2, giữ snapshot; live chưa ghim model. BR-026-01 policy P1 còn mở, 02/03 cải thiện trình bày chờ rà. Còn tài khoản theo người/hai UI/config lifecycle/phụ thuộc/full gate; chưa production | [Bốn nhánh](evidence/R5/four_branch_20261112/REPORT.md), [Business review](evidence/R5/business_review_20261112_final/REPORT.md), [Portal auth](evidence/R5/portal_auth_20261112/REPORT.md) | — | — |
| R6 | NOT_STARTED | Chưa gán | Phần phụ thuộc R5; decision theo phạm vi | evidence/R6/REPORT.md — chưa có | — | — |

CR-028/029 — hướng cloud ciphertext-only và lựa chọn inference: [thử nghiệm HE độc lập](evidence/HE/inference_20261112/REPORT.md) READY_FOR_REVIEW, 33 HE + 742 backend pass. Fit tại DN, model/feature mã hóa, worker subprocess không có khóa giải mã. Chưa cloud deployment/web hoặc adapter bốn nhánh/33 feature, không đổi trạng thái các mốc R0–R6 hay D-11/D-12 sản phẩm.

CR-030 — [registry export vào HE thử nghiệm](evidence/HE/registry_export_20261112/REPORT.md) READY_FOR_REVIEW: 66 HE + 742 backend pass, đọc MethodStore/snapshot mode=ro, full contract 33 cột và hai feature model, metadata/provenance checked trước deserialize, không fit khi export; demo hai DN/10 dòng pass, DB giữ nguyên. Chưa UI/cloud deployment/adapter IF–ECOD–LOF–AE hoặc production; không đổi trạng thái mốc R0–R6.

CR-031 — [hai dịch vụ node DN và worker ciphertext](evidence/HE/services_20261112/REPORT.md) READY_FOR_REVIEW: 93 HE/service + 742 regression pass; demo 16 checks/two processes/10 dòng/parity pass. Bundle worker không source DN; node giữ raw/model/HE key và decrypt, worker chỉ public policy/ciphertext. Loopback, chưa cloud public/TLS production/OS sandbox hoặc node key recovery sau restart; Portal và trạng thái R0–R6 giữ nguyên.

CR-032 — [job HE bền vững và recovery](evidence/HE/job_lifecycle_20261112/REPORT.md) READY_FOR_REVIEW: 116 HE + 742 regression pass, 23 focused/16 demo checks pass. Submit/status/result/resume, DB idempotency/checkpoint/result mã hóa ở DN, không token; crash/network/received-before-decrypt recovery không compute trùng. Chưa Portal UI/cloud public/KMS/HA/production; cần DB/key/build tương thích, R0–R6 giữ nguyên.

CR-033 — [khóa DN được Windows DPAPI bảo vệ](evidence/HE/key_protection_20261112/REPORT.md) READY_FOR_REVIEW: 131 HE pass (gồm 15 ca khóa), 16 demo restart checks pass dưới config 1.2.0 strict. Bọc state key và node signing key theo tài khoản Windows; chuyển hex giữ cùng khóa/DB/idempotency, không tự chuyển live. 17 source nghiệp vụ giữ nguyên so CR-032; không chạy lại bộ 742 trong lượt này. Chưa cross-machine recovery/KMS/rotation/Portal/cloud public/production; R0–R6 giữ nguyên.

CR-034 — [UI chọn DN/dữ liệu và chạy HE](evidence/HE/web_analysis_20261112/REPORT.md) READY_FOR_REVIEW: 145 HE + 742 regression pass; 14 focused API và 17 browser checks pass. Dùng Portal session, ghim model tại DN, catalog checksum/scope, cutoff snapshot cố định và phiếu chống trùng trước POST; reload/outage giữ cùng run ID. Node nhúng opt-in cùng auth/DB, worker ciphertext-only; chưa đổi/restart live, queue/bốn nhánh HE/cloud public/production. R0–R6 giữ nguyên.

CR-035 — [bộ C001/C002 lưu bền vững](evidence/HE/company_preparation_20261112/REPORT.md) READY_FOR_REVIEW: hai model fit riêng (32 fit + 8 tham chiếu/DN), 5 dòng đánh giá/DN, DPAPI/ACL và 4 snapshot. 5 focused tests pass; 38 checks trên bộ thật và 38 checks mở lại process mới pass, giữ job ID và parity, không fit lại. 17 core sources không đổi; không chạy lại toàn bộ 145/742 vì chỉ thêm prepare/check opt-in. Chưa bật HE/đổi quyền/config live, không accuracy claim/full gate; R0–R6 giữ nguyên.

CR-036 — [bật bộ HE trên Portal 8800](evidence/HE/portal_activation_20261112/REPORT.md) READY_FOR_REVIEW: dịch vụ đang chạy, cấu hình có backup, mật khẩu/DB cũ/keys/model và Agent1 giữ nguyên. Checker 1.1: 7 focused pass, 40 packet checks pass khi web/worker live đang chạy; khóa record thay SQLite header và state riêng. **Người dùng đã đăng nhập; 7 bước authenticated UI live pass**, mỗi DN đủ 5 điểm và reload giữ cùng run ID/kết quả, không JS error. Không bypass/đặt lại mật khẩu hoặc tự ký DONE/full gate. R0–R6 giữ nguyên.

CR-037 — [Bật/Tắt Agent2 cùng worker và kết nối lại](evidence/HE/managed_worker_20261112/REPORT.md) READY_FOR_REVIEW: 159 HE + 742 native pass, 11 browser checks pass; 7 manager/23 durable jobs subsets pass. DPAPI + signed readiness, stop owned trees, reconnect cùng job; live start-stop-start đã qua và giữ key/model/data/Agent1. Không fit/queue/production, chưa OS autostart/force-kill guarantee; Portal restart deploy cần đăng nhập lại, không đặt lại mật khẩu. R0–R6 giữ nguyên.

Nghiệm thu bổ sung CR-037 — [Portal C001/C002](evidence/HE/portal_acceptance_20261112/REPORT.md) **PARTIAL**: 14 browser checks pass trong fixture riêng, không lẫn DN; tắt Portal khi native worker đang tính khôi phục cùng job/5 điểm. Hard crash trước commit trả failed/WORKER_INTERRUPTED, chưa tiếp tục thành công (HE-AC-01 OPEN); không ghi đạt tiêu chí này. Người dùng đã đăng nhập; 12 UI live checks trên 8800 pass, C001/C002 đủ 5 điểm, tắt/bật/reconnect/reload giữ cùng job và kết quả; ngắt live ở phase preparing trước native claim. Không bypass mật khẩu. HE-AC-01 vẫn OPEN cho hard crash giữa native compute. Chỉ thêm kịch bản/evidence, không đổi mã sản phẩm hoặc model/khóa/snapshot.

CR-038 — [bảng đo rõ/HE cùng model và snapshot](evidence/HE/plaintext_comparison_20261112/REPORT.md) READY_FOR_REVIEW: 9 unit tests pass, native 18 worker records (2 warmup + 10 lượt đo + 6 sự cố), không fit hoặc đổi Portal. Sai số tối đa ~1,446e-6, thứ tự khớp mọi lượt, rõ p50 ~0,12 s/HE ~2 s local. Khôi phục 2/2 trước claim, 2/2 đóng có kiểm soát, 0/2 hard crash; chất lượng PARTIAL, HE-AC-01 OPEN. Không suy precision/SLA/cloud production, không tự duyệt R0–R6; 159/742 của CR-037 không chạy lại trong lượt này.

CR-039 — [10 phiếu rà nghiệp vụ mô phỏng](evidence/HE/business_review_demo_20261112/REPORT.md) READY_FOR_REVIEW phần thử luồng: 13 unit/10 browser/3 builder checks pass; tệp offline riêng tại DN, chưa Portal/R4 hoàn chỉnh. Nguồn point-in-time/manifest, kết quả và hữu ích độc lập, revision/merge giữ lịch sử, timer/danh tính tự khai chưa xác minh. 0/10 người thật rà, usefulness/time chưa có là null; không label train/baseline luật/hiệu quả thật. Giữ 2 feature và HE-AC-01 OPEN; không tự chuyển R0–R6/DONE.

CR-040 — [worker chết giữa compute đã khôi phục](evidence/HE/worker_recovery_20261112/REPORT.md) READY_FOR_REVIEW: 202 HE + 742 native + 14 browser pass; 21 recovery tests subset, managed interruption pass, packet check 40 pass. Hash-bound replay + OS state lock + attempt fence, worker schema 2 giữ cache. Model/keys/snapshot/config/Portal session không đổi; đã nâng bundle trên Portal 8800 không restart Portal. C001/C002 hard crash từ 0/2 cũ lên 2/2 mới, đủ 5 điểm/DN, 18 logical jobs không trùng. HE-AC-01 FIXED_READY_FOR_REVIEW với managed request còn TTL/state, không mở lại legacy/terminal; không cam kết exactly-once native compute, không production/DONE R0–R6.
