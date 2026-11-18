# Luồng bundle trên Portal, phiếu rà và công việc — CR-061/062

Trạng thái: **READY_FOR_REVIEW kỹ thuật, shadow tại doanh nghiệp**.
Production/toàn R6 và full HE theo bundle tiếp tục BLOCKED.

Luồng đã nối:

`Snapshot → feature PIT → các nhánh khả dụng → selected arm/fallback đã ghim →
gộp vụ → policy/ngân sách cấp vụ → queue shadow → review packet → báo cáo`.

Tái sử dụng detector, validation và CaseQueueStore từ CR-060. Không fit trong
request, không tự chọn model mới nhất, không đổi trọng số/ngưỡng live. B=3 case
trong fixture là kiểm thử cơ chế; không đổi phép so5 giao dịch/phương án/DN.

## Khởi chạy và theo dõi

Mở Agent2 trong Portal. Node đã cấu hình release service dùng màn **Vụ cần rà**
làm trang chính (`/agent2/` hoặc `/agent2/pipeline-workspace#company=C001`). Người
có membership và quyền dữ liệu tại DN chọn snapshot rồi bấm **Chạy phân tích**.
Kết quả vẫn là hàng đợi shadow. Backend lấy bundle staging đã duyệt, cutoff từ snapshot,
pin một lần và giữ xuyên suốt. Kế toán không cần quyền chỉnh cấu hình; chuẩn bị/
duyệt/kích hoạt/rollback bundle vẫn qua API director và gate cũ.

Browser lưu mã run đang gửi trong sessionStorage theo actor/context/DN/snapshot/
bundle. Mất phản hồi sau backend commit thì nút thử lại dùng đúng mã run, không
tạo lượt logic mới. Lượt chưa xong hiển thị pending và có nút tiếp tục; checkpoint
execution/queue receipt giữ cùng snapshot/run/bundle dù active pointer đã đổi.
Không nhận model, score, policy, role hoặc ngưỡng từ body của thao tác chạy.

Sau nhập → kiểm tra → xác nhận lưu, bấm **Tiếp tục đến vụ cần rà** để chuyển đúng
DN/snapshot vào màn chung. Thanh điều hướng trên màn **Vụ cần rà** cũng nối trực tiếp
tới **Xác minh nhãn** (`/agent2/label-verification#company=...`) và **Train HE nhiều batch**
(`/agent2/batch-training#company=...`) kèm liên kết quay lại **Vụ cần rà** giữ nguyên ngữ cảnh
doanh nghiệp. Phần **Hàng đợi chờ xét (Backlog shadow)** hiển thị các vụ tạm hoãn do hết
ngân sách kỳ hiện tại (`budget_deferred`) hoặc dưới ngưỡng tiếp nhận (`below_threshold`,
không tự hết hạn) và cho phép bấm **Xét lại vụ chờ sang kỳ mới** để tiếp nhận các vụ đủ
điều kiện vào kỳ ngân sách tiếp theo kèm packet phiếu rà tương ứng. Snapshot chưa có
source profile đầy đủ vẫn xuất hiện
với lý do không chạy được; không chuyển ngầm sang P1. Nếu chưa có bundle staging
tương thích, người quản lý phải chuẩn bị/kiểm định/duyệt cấu hình trước.

Phạm vi luật lấy từ analysis đã lưu: profile nguồn đầy đủ là 35 luật, từng luật
thiếu nguồn vẫn unavailable. Packet cũ chưa có metadata phạm vi không được tự
gán 35 luật. Màn **Công việc và lượt HE cũ** giữ dữ liệu HE lịch sử; phép so sánh
P1/ML cũ được ghi rõ không đại diện baseline 35 luật, không đổi tên kết quả cũ.

## Phiếu và nguồn bằng chứng

- Chỉ quyết định selected/mandatory_route trong queue mới tạo phiếu. Các vụ
  đã gửi không tự có phiếu trùng khi đổi phiên bản/rerun. Deferred, thiếu nguồn
  và below-threshold vẫn có thống kê riêng, không đôn cho đủ budget.
- Packet `bundle-review-packet/1.0.0` bất biến ở kho release AES-GCM. ID phiếu
  gắn tenant/DN/pin/case; packet gắn source checksum, cutoff và bộ ba snapshot/
  run/bundle. Packet được commit cùng observation, retry không tái dựng bằng
  cấu hình mới. Lượt cũ thiếu packet không tự được gán packet từ latest config.
- Hiển thị ứng viên và giao dịch lịch sử riêng. Source records chỉ được lấy từ
  snapshot đã khóa và đúng thời điểm; master context dùng lịch sử trước giao dịch.
  Nguồn mơ hồ ghi thiếu, không tự đoán phiên bản. Case financial coalescing cũng
  loại nguồn sau as_of; filter này không thay byte snapshot hoặc feature contract.
- Bản ghi mô phỏng, source export và tài liệu bổ sung phân biệt rõ. Export không
  đồng nghĩa original verified. Tài liệu bổ sung giữ known_after_analysis và không
  sửa feature/bằng chứng dùng để chấm trong quá khứ.
- Phiếu hỏi điều cần làm rõ, lý do rà, cần đối chiếu gì và bước tiếp theo. Người
  rà chọn Có vấn đề cần xử lý / Không phát hiện vấn đề / Chưa đủ căn cứ, kèm
  giải thích, căn cứ và hành động. Kết luận xác định cần evidence IDs hợp lệ và
  xác nhận đã kiểm; thiếu thì ghi rõ tài liệu còn thiếu/hành động yêu cầu bổ sung.

Phản hồi tái sử dụng ReviewStore với **kho riêng và namespace company-shared**.
Member được cấp quyền trong DN xem được kết quả của nhau; revision/CAS và actor
audit tránh ghi đè. Không đổi namespace/khóa hoặc migrate các phiếu HE cá nhân cũ.
Khóa review derive từ khóa bảo vệ release bằng HKDF riêng, chỉ trong RAM tại DN;
file review nằm cạnh kho release, tên `<release-stem>-reviews.sqlite3`.

Đồng hồ đo connected active time phía server, không nhận số phút tự khai từ client.
Restart/mất kết nối mất lease chưa lưu; số giây đã lưu giữ nguyên. Save retry sau
mất phản hồi trả revision đã lưu dù lease cũ không còn. Bổ sung PDF/PNG/JPEG theo
giới hạn ReviewStore2MB/10 tệp; không tự gắn verified cho nội dung upload.

## Giao việc ngay trong vụ

Mở vụ → phần **Giao việc từ vụ này** → chọn loại công việc, ghi nội dung/việc
phải làm/lý do, chọn bộ phận và hạn xử lý theo giờ Việt Nam → **Giao việc**.
Không có hạn mặc định hoặc tự đặt SLA. Phân công là vai trò/bộ phận, chưa xác
minh danh tính cá nhân trong Portal dùng chung.

Task dùng RemediationStore/ActionTask hiện hữu, thêm source_binding optional do
server đọc packet: snapshot/run/bundle/pin/review/canonical-case/as_of. Client
không được tự gửi binding hoặc đổi case/model. Task case key là review_id, giữ
canonical case trong binding; receipt, revision và audit giữ nguyên nguồn qua
restart/chuyển người phụ trách. Mất phản hồi dùng lại request_id; cùng loại việc
đang mở trên phiếu được chống trùng. Nguồn đã có khác binding bị chặn thay vì gán lại.

Danh sách và JSON/CSV report của vụ có task, trạng thái, bộ phận, hạn; tiền vẫn
một dòng/vụ trong CSV để tránh nhân số tiền theo số task. Từ màn công việc chung
có link **Mở vụ nguồn** về đúng bundle run. Lifecycle nộp kết quả/xác minh/hoàn tất
vẫn dùng phần xử lý công việc hiện hữu. Tài liệu đính kèm phiếu không tự được
xác minh hoặc trở thành chứng từ hoàn tất task. Tạo/hoàn tất task không tự đóng
vụ, xác nhận gian lận hoặc tạo nhãn huấn luyện.

## Báo cáo nghiệp vụ và phân quyền

Report `bundle-workspace-report/1.0.0` có snapshot_id/run_id/bundle_id/as_of,
report_sha256, queue counts, giới hạn theo nhánh, packet/phiếu và review revisions.
DTO nghiệp vụ dùng allowlist; không gửi thuật toán, trọng số, rule coverage,
raw score, feature/model config hoặc xác suất hiệu chuẩn xuống tài khoản kế toán.
Người dùng thấy nguồn và hành động; quản lý xem chi tiết kỹ thuật ở release UI.

Thống kê: số vụ được xét/tiếp nhận/deferred/trùng, số phiếu chưa/đã rà, kết quả
khai báo, hữu ích tự đánh giá và thời gian kết nối đã lưu. `declared_issue_fraction`
chỉ là tỷ lệ kết luận Có vấn đề trong phiếu đã có kết luận xác định; không phải
precision gian lận. Nhãn chưa xác minh không thành nhãn train, accuracy/verified
fraud precision vẫn null. Dữ liệu mô phỏng không chứng minh hiệu quả thật.

Số tiền related/discrepancy/loss/recovered giữ riêng, unknown=null. CSV một dòng
trên vụ, không tự cộng tổng tiền qua các vụ có thể chung nghĩa vụ. Tiền signed VND
giữ số nguyên chính xác kể cả vượt JS-safe integer; nội dung tự nhập có công thức
CSV được escape. JSON/CSV luôn giữ cùng bộ ba mã truy vết và source cutoff.

## API

Sau `/api/v1/companies/{DN}/pipeline-workspace`:

| Route | Chức năng |
|---|---|
| `GET /` hoặc `GET /runs` | Snapshot được đọc, phiên bản sẵn sàng, `execution_modes` khả dụng và các lượt completed/pending |
| `POST /runs` | Body `run_id` + `snapshot_id` (+ `execution_mode`); chạy/tiếp tục bundle staging đã duyệt |
| `GET /backlog` | Danh sách và thống kê vụ chờ (`backlog_waiting`) trong hàng đợi shadow, đã ẩn trường thuật toán/điểm ML theo RULE-UI-01 |
| `POST /backlog/reevaluate` | Body `target_period_key` + `request_id`; xét lại vụ chờ sang kỳ ngân sách mới bằng `case_policy` ghim trên bundle staging hiện hành, tạo lượt rà shadow cho các vụ vừa được tiếp nhận |
| `GET /runs/{run}` | Báo cáo nghiệp vụ và phiếu từ observation đã hoàn tất |
| `GET /runs/{run}/report[.csv]` | Xuất JSON hoặc CSV nghiệp vụ |
| `POST /runs/{run}/reviews/{review}/start` | Lease đồng hồ |
| `POST .../heartbeat` | Cập nhật thời gian kết nối |
| `POST .../save` | CAS expected_revision + request_id + feedback + lease |
| `POST .../attachments` / `GET .../attachments/{id}` | Tài liệu bổ sung trong đúng phiếu |
| `GET .../reviews/{review}/tasks` | Công việc có đúng source binding và danh sách bộ phận |
| `POST .../reviews/{review}/tasks` | Giao việc từ packet; body task_type/title/what_to_do/reason/assignee_key/due_at/request_id |

Mỗi route kiểm membership scope, current auth và packet binding ở backend; không
dựa vào dropdown/nút ẩn. Review ID của DN/run khác, evidence ngoài packet và
field tự khai model/score/policy bị từ chối. Review upload/save kiểm lại quyền
trong transaction trước commit. Người dùng không được tự tạo phiếu từ điểm nhập tay.

## Ràng buộc HE

Mặc định bundle chạy `enterprise_local_only` (`he_execution=false`) tại doanh nghiệp
và không gửi dữ liệu rõ lên cloud. Khi chuẩn bị bundle với
`execution_mode=cloud_ciphertext_only`, `BundleHE` (`bundle-he4-native/1.0.0`) ghim
build (`rules`, `c3`, `graph`), cấu hình worker, binding doanh nghiệp và các epoch
khóa đã cấp vào slot `he` của bundle:

- Cloud worker chỉ nhận bản mã và evaluation key công khai cho các mạch hỗ trợ
  hiện có (`P1`, `C3`, `B1`, `B5/E4`) trên snapshot nguồn 35 luật.
- 30 luật còn lại và nhánh thống kê/ML theo contract 33 feature trả `unavailable`
  (`complete_catalogue=false`, `native_33_feature_he_unsupported`); không lấy điểm
  ECOD/RobustZ local để giả làm kết quả HE.
- Giải mã, áp chính sách đã ghim, gộp vụ, cấp ngân sách, ghi hàng đợi shadow,
  tạo packet phiếu rà, xử lý task và xuất báo cáo vẫn chạy tại node doanh nghiệp.
- Nếu node chưa cấu hình `BundleHE` hoặc bundle đang kích hoạt là bản local không
  ghim slot `he`, yêu cầu `cloud_ciphertext_only` bị từ chối bằng
  `PIPELINE_HE_UNAVAILABLE` **trước** khi tạo job hay gọi bộ chấm rõ.

Chi tiết cấu hình, giao nhận/khôi phục và phạm vi HE theo bundle xem tại
`agent2/docs/BUNDLE_HE.md` và bằng chứng nghiệm thu tại
`Agent2_Spec_v2_1/evidence/R6/bundle_he_20261118/REPORT.md`. Production gate,
quyết định chất lượng và các yêu cầu chưa chốt vẫn bị chặn. Không restart/deploy
Portal live hoặc đổi model/key/phiên/quyền live.

## Kiểm thử

`tests_he/test_bundle_workspace.py`: luồng thật, provenance, source after-cutoff,
privacy/accountant, save/lease/CAS, cross-company/run, evidence/attachment scope,
restart/retry, crash boundary, CSV integer/injection và không plaintext fallback.
`scripts/check_bundle_workspace_ui.py`: Portal/Chrome cô lập C001/C002, operator
khởi chạy, mất phản hồi, phiếu/bổ sung tài liệu, reload/export và mobile/routing.
Evidence: `Agent2_Spec_v2_1/evidence/R6/bundle_orchestrator_20261116/REPORT.md`.
Portal/task: `Agent2_Spec_v2_1/evidence/R5/portal_bundle_20261116/REPORT.md`.
