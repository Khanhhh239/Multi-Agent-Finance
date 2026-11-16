# CR-061 — điều phối bundle đến phiếu rà và báo cáo

- spec_version: 2.1; ngày: 16/11/2026; thực hiện: Codex.
- Trạng thái: **READY_FOR_REVIEW kỹ thuật cho shadow tại doanh nghiệp**.
  Toàn R6, production và full HE theo bundle: **BLOCKED**.
- Base commit: `f203b39828f567171916b5b4744728ed4b63d17f`; thay đổi chưa commit.
  Workspace có nhiều thay đổi có sẵn; không reset hoặc ghi đè phần agent khác.
  `manifest.json` ghi SHA-256 các nguồn và bằng chứng liên quan, không phải hash
  đại diện cho toàn bộ dirty tree.
- Nguồn giao việc: TASK.md trong thư mục này. Tái sử dụng CR-059/060, snapshot,
  validation/method store, case coalescing, queue và ReviewStore hiện hữu.
- Không chốt D-04/05/06/07/09/17/18/19; không tự đặt chất lượng, ngân sách sản xuất,
  trọng số hoặc mandatory routing. B=3 vụ trong fixture không thay phép so sánh
  5 giao dịch/phương án/DN đã thống nhất trước đây.

## Kết quả

Luồng thực thi tại DN: snapshot bất biến → feature point-in-time → các nhánh
khả dụng → selected arm/fallback ghim trong bundle → gộp vụ → policy/ngân sách
cấp vụ → hàng đợi shadow → packet phiếu bất biến → phản hồi → báo cáo JSON/CSV.
Bundle không fit lại model trong request và không tự dùng model latest.

`snapshot_id`, `run_id`, `bundle_id` giữ xuyên suốt observation, packet, response
ghi phiếu và báo cáo. Ứng viên tách khỏi giao dịch lịch sử làm bằng chứng. Chỉ
selected/mandatory_route tạo phiếu; không tạo thêm phiếu cho already_notified.
Queue receipt/checkpoint giữ nguyên quota và kết quả khi crash/retry. Packet
commit cùng observation; không dựng lại phiếu của lượt cũ bằng cấu hình mới.

Người dùng có quyền dữ liệu được chạy snapshot bằng bundle staging đã duyệt và
rà phiếu trong DN; không được sửa config/model/score/policy bằng body request.
Quản lý vẫn dùng release gate/director API riêng. Phản hồi dùng kho mã hóa riêng,
company-shared owner, CAS revision và audit actor. Không đổi kho phiếu HE cá nhân.
Upload PDF/ảnh chưa được xác minh và không sửa snapshot/feature đã dùng để chấm.
Timer ghi thời gian kết nối phía server; feedback không tự thành nhãn train.

Case financial coalescing loại bản ghi sau cutoff, kể cả giao dịch không nằm
trong tập ứng viên nhưng cùng hóa đơn. Source master hiển thị theo thời điểm
giao dịch; nguồn mơ hồ không được tự đoán phiên bản. Tiền signed VND giữ chính
xác qua JSON/CSV, thiếu dữ liệu vẫn null; không cộng tổng tổn thất qua các vụ.

## Đường dẫn thay đổi

| Nguồn | Kết quả |
|---|---|
| `agent2/sme_fraud/bundle_reviews.py` | Packet nguồn bất biến, business DTO, company review namespace, submit/resume và JSON/CSV |
| `agent2/sme_fraud/bundle_workspace_api.py` | API business theo DN/run, review membership/evidence và current auth |
| `agent2/sme_fraud/pipeline_release.py`, `pipeline_release_store.py` | Packet/observation atomic, khóa review namespace riêng, chặn yêu cầu cloud chưa tương thích |
| `agent2/sme_fraud/release_shadow_plan.py` | Lọc lịch sử cấp vụ theo cutoff trước coalescing |
| `agent2/sme_fraud/review_store.py` | Kiểm lại quyền trong transaction save/upload, tương thích caller HE cũ |
| `review_server.py`, `workbench.py`, `pipeline_release_api.py` | Đăng ký API/assets và execution mode rõ ràng |
| `web/bundle-workspace.html`, `web/bundle-workspace.js` | Chọn snapshot/chạy/resume, chứng từ, ghi phiếu, reload/export/mobile |
| `web/workspace.html`, `web/workspace.js`, `web/pipeline-releases.js`, `portal/agent2_bridge.py` | Link đúng DN/run và Portal allowlist chính xác |
| `agent2/tests_he/test_bundle_workspace.py`, `agent2/scripts/check_bundle_workspace_ui.py` | Regression và Portal/Chrome cô lập |
| `agent2/docs/BUNDLE_ORCHESTRATOR.md`, bốn spec file CR-061 | Hướng dẫn, contracts, quyết định và phạm vi nghiệm thu |

## Bằng chứng chạy thực tế

Mọi dữ liệu ở đây là mô phỏng. Portal/Agent2/Chrome dùng tiến trình cô lập,
không restart hoặc deploy Portal live, không dùng mật khẩu thật trong lịch sử.

| Lệnh/nhóm kiểm tra | Kỳ vọng | Quan sát | Kết quả |
|---|---|---|---|
| CMD-01: runner hồi quy, 14 modules | Không failure/error/skip | 146 tests, 0 failure, 0 error, 0 skip; 225.500s | pass |
| CMD-02: Portal/Chrome C001/C002 | Người dùng khởi chạy, xem nguồn, ghi phiếu, reload/export, mobile/routing | 8 nhóm pass; báo cáo browser-report.json | pass |
| Lost-response C001 | Retry đúng run sau backend commit, không thêm quota/run/observation | Browser assertion một logical run; submit/retry thật qua Portal | pass |
| Future payment PIT | Dòng không phải ứng viên đến sau cutoff không tăng tổng đã trả hoặc vào evidence | Test future_non_candidate_payment_not_counted_as_case_history pass | pass |
| Packet/crash/restart/CAS | Một packet, không gửi trùng/ghi đè, scope/current auth đúng | Tests packet crash, retry restart, stale revision, revoke rollback pass | pass |
| HE fail-closed | Yêu cầu cloud không gọi bộ chấm rõ hoặc tạo pin | Spy executor/pin assertion pass; không có HE mới được chạy ở lượt này | pass kỹ thuật, HE end-to-end blocked |
| Tiền/CSV và nhãn | Signed integer/null, chống formula injection, feedback không thành nhãn | Tests báo cáo, evidence/outcome và attachment pass | pass |

CMD-01, từ repo root, `PYTHONPATH=D:\agent22\shared\finance_input\src`:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_bundle_workspace --suite test_pipeline_release --suite test_release_shadow_plan --suite test_validation_study --suite test_case_queue --suite test_remediation --suite test_he4_config_api --suite test_portal_auth --suite test_workspace_api --suite test_pipeline_benchmark --suite test_batch_training_portal --suite test_review_store --suite test_review_api --suite test_review_rule_evidence --report .runtime/release-acceptance-20261116/bundle-orchestrator-final.json
```

CMD-02, cùng PYTHONPATH:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/check_bundle_workspace_ui.py --output .runtime/release-acceptance-20261116/bundle-review-browser-checksum
```

Hai lệnh exit 0. Chi tiết từng testcase nằm trong `regression.json` và
`browser-report.json`. C001/C002 mỗi DN có 3 phiếu được tiếp nhận trong fixture;
mỗi DN lưu thử 1 phiếu Chưa đủ căn cứ, hai phiếu còn lại chưa rà. Thời gian là số
giây server thực sự đo, có thể làm tròn 0 trong thử nhanh; không phải thời gian
nghiệp vụ do chuyên viên thực hiện. C001 có attachment mô phỏng chưa xác minh.
Kiểm tra checksum file tải phát hiện JS parse/stringify đổi `0.0` thành `0`;
đã sửa JSON/CSV download giữ nguyên byte server và hủy kết quả tải khi đổi scope.
Browser kiểm hash report tải về bằng canonical backend cho cả C001/C002.
`C001-business-report.*`, `C002-business-report.*` giữ triple và trạng thái nguồn;
`verified_fraud_precision=null`, `training_eligible=false`. Screenshot desktop/mobile
đã được xem lại, không tràn ngang. Không có mật khẩu/khóa/DB riêng trong evidence.

## Giới hạn và phần chưa làm

1. Executor bundle mới là **enterprise_local_only, he_execution=false**. Không
   gửi dữ liệu rõ lên cloud. Yêu cầu cloud_ciphertext_only bị từ chối trước tạo
   pin hoặc gọi local score; capability từng nhánh cloud trả unavailable. Chưa
   dispatch bundle sang worker HE thật. ECOD validation local không phải HE.
   Đường HE hiện hữu độc lập không bị thay TTL/replay/key/build.
2. Chưa đủ bằng chứng toàn R1–R5, quality study thực tế, ngân sách cấp vụ được
   duyệt sản xuất, monitoring/trigger và release active. Không đánh đồng focused
   regression với nghiệm thu toàn R6. `acceptance.json` giữ 6 mandatory R6 blocked.
3. Đây là hàng đợi shadow và phản hồi khai báo; không chứng minh độ chính xác
   phát hiện gian lận hoặc giá trị nghiệp vụ trên dữ liệu thật.
4. Portal có thể dùng danh tính workspace chia sẻ; actor audit được kiểm quyền
   server nhưng chưa chứng minh danh tính cá nhân chuyên viên rà.
5. Chưa deploy/restart live, commit hoặc push GitHub; không đổi model/khóa/phiên/
   membership live. Khi triển khai cần nạp route/assets/backend mới theo quy trình
   backup/release riêng.

## Kết thúc

CR-061 sẵn sàng rà kỹ thuật phần local shadow. Dừng task ở đây; reviewer có quyền
quyết định nghiệm thu sau khi xem evidence và các giới hạn. Không ghi DONE R6.
