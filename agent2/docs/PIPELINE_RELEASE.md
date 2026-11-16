# Phát hành và rollback theo bundle — CR-059

## Bổ sung CR-060: validation → bundle → hàng đợi shadow

Profile mới `snapshot_case_shadow/1.0.0`, bundle `pipeline-release-bundle/1.1.0`
đã nối study, normalization/reference, calibration artifact, phương án detector,
fallback khai báo, gộp vụ, threshold, case budget/mandatory và backlog policy vào
cùng bundle bất biến. Profile detector-only 1.0 vẫn được đọc theo contract riêng.
Đây là **shadow tại doanh nghiệp**, chưa là full HE hoặc production.

Gói `release-shadow-plan/1.0.0` được tạo tại producer validation tin cậy bằng
`release_shadow_plan.make_package(...)`. Hàm nhận plan/splits/model/reference,
chạy lại `run_validation_study`, khóa source runtime trước/sau; case policy,
ngưỡng ứng viên ML và thứ tự fallback phải được truyền tường minh. Không tự lấy
policy mới nhất, không nâng benchmark5 giao dịch thành ngân sách5 vụ. Registry
kiểm lại snapshot/checksum/cutoff, model/feature/reference/calibrator/study hash.
Gói thiếu runtime provenance cần chạy validation lại, không chép hash runtime mới
vào báo cáo cũ để hợp thức hóa. Gói này không chứa secret key hoặc quyền.

Đăng ký qua `ReleaseService.register_plan` ở backend tin cậy hoặc CLI
`scripts/register_shadow_release_plan.py`:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/register_shadow_release_plan.py --package D:/private-agent2/release-plan.json --auth-file D:/private-agent2/auth.json --company C001 --release-config D:/private-agent2/release-runtime.json --snapshot-db D:/private-agent2/snapshots.sqlite3 --model-db D:/private-agent2/models.sqlite3 --request-id register-c001-study-v1
```

Token đã cấp đặt trong biến môi trường `AGENT2_CLI_TOKEN`, không đặt ở argv hoặc
ghi vào gói. CLI cần director đúng DN và protected key hiện có; chỉ ghi registry,
không duyệt hay đổi active pointer. Gói/báo cáo là nguồn tin cậy tại DN, không mở
HTTP upload JSON metric/policy/model. Browser chỉ gửi `plan_id` của artifact đã
đăng ký trong POST prepare; không nhận thêm body config để vượt gate.

Trên màn hình phát hành, chọn **Gói validation và chính sách đã đăng ký** trước
khi tạo bundle. Mặc định detector-only, không tự chọn plan mới nhất. Chạy staging
sẽ phân tích snapshot thật, dùng đúng phương án/reference đã ghim, gộp vụ rồi xét
policy vào namespace `shadow`; gate preview chỉ xem trước, không giữ ngân sách.
Kết quả có bundle/run/snapshot/as_of, study hash, fallback và quyết định từng vụ.

Checkpoint execution bất biến được commit **trước** queue reservation. Mã queue
receipt gắn pin, dữ liệu request lấy từ checkpoint khi tiếp tục. Crash sau queue
commit nhưng trước lưu observation không làm tính lại bằng bundle mới hoặc cấp
quota lần nữa. Kỳ ngân sách tính từ cutoff và calendar policy, không chứa bundle
ID/run ID. Đổi loại kỳ cần kế hoạch migration riêng và bị chặn tại switch.
Case đã gửi có cùng nguồn/candidates không được gửi lại chỉ vì release đổi điểm.

Reference/selection/calibrator đến sau thời điểm giao dịch làm dòng đó unavailable;
không dùng fallback để lách cutoff. Fallback phải đúng subset đã khai báo, đủ
nguồn và reference; nhánh ngoài khả năng executor không được giả điểm. Calibrator
ngoài phương án chọn không được tham gia case scoring. Điểm chung vẫn là rank/
priority; xác suất hiệu chuẩn thử nghiệm, nếu có, được ghi riêng.

Monitoring mới đo fallback count/denominator/rate, case counts, deferred, budget
và thời gian xử lý queue theo observation/bundle/DN. Kết quả rà, phút rà, drift
và thời gian chờ chưa có provenance vẫn null; không tự train/activate.

Giới hạn: chấm các model MethodStore không nhãn và rules ở node DN; chưa gọi
supervised-shadow hay worker HE trong profile này. Không gán full-HE cho ECOD,
không gửi raw lên cloud và không tạo plaintext fallback cho đường HE hiện hữu.
Case policy thử chưa được quality study chứng minh tối ưu; kế hoạch so5 giao
dịch không phê duyệt policy ngân sách cấp vụ. D-09 và các owner decisions vẫn
chặn production. Không restart/deploy Portal live hoặc sửa key/model/phiên live.
Nghiệm thu bổ sung: `evidence/R6/linked_shadow_20261116/REPORT.md`.

Nội dung tiếp theo mô tả profile detector-only1.0 của CR-059; profile case shadow
và bundle1.1 mở rộng được mô tả trong CR-060 ở trên.

Trạng thái: **READY_FOR_REVIEW kỹ thuật; production BLOCKED**. Đây là kho release
và executor staging chạy tại doanh nghiệp. Chưa phát hành toàn bộ pipeline HE,
ensemble, cấp ngân sách và giao vụ. Không thay đổi Portal live trong lượt này.

## Đã nối

- Bundle `pipeline-release-bundle/1.0.0` bất biến, có tenant/DN, nguồn qualification,
  người tạo, thời gian và ID theo hash. Mỗi thành phần là artifact có checksum hoặc
  khai báo `unused` có lý do. Schema: `sme_fraud/pipeline_release.schema.json`.
- Ghim rules, đồ thị, hợp đồng feature, preprocess, model/reference từ MethodStore,
  code, schema, thư viện và package hợp đồng đầu vào. Native engine thực sự dùng
  `DEFAULT_CONFIG`; bundle chụp đúng cấu hình này, không giả định nguồn có `config`.
- Các vị trí normalization/calibration/ensemble/fallback/grouping/threshold/budget/
  mandatory/backlog/document-policy/HE được khai báo rõ phạm vi chưa dùng. Không
  tự lấy “latest”, tự fit, đặt tỷ trọng hoặc biến rank thành xác suất gian lận.
- Các gate lưu expected/observed/status/evidence/approver; smoke gọi engine thật
  và đối chiếu đủ định danh/revision, giữ `unavailable`. D-09 và các quyết định
  active còn mở tiếp tục chặn production; nhãn hoặc mẫu số chưa có trả `null`.
- Duyệt staging riêng, gắn đúng bundle/gate/lane, hạn kỹ thuật 24 giờ. Báo cáo gate
  cũ không bị sửa thành pass; approval là đối tượng độc lập có audit. Đây không
  phải phê duyệt chất lượng hay thay quyết định D-17/D-19.
- Con trỏ staging/production độc lập theo DN, CAS `expected_revision`, idempotency
  bền vững. Hai người kích hoạt đồng thời chỉ một yêu cầu thành công. Mất phản hồi
  trả đúng phiếu cũ; không tăng revision lần nữa.
- Mỗi lượt staging ghi pin trước chấm; đổi active giữa lượt không đổi model/bundle.
  Lượt chưa hoàn tất có thể tiếp tục đúng mã sau restart; lượt đã xong trả kết quả
  cũ. Hai tiến trình có thể tính lặp trước commit nhưng chỉ lưu một kết quả logic;
  không tuyên bố native compute exactly-once.
- Rollback chỉ tới bundle đã dùng trong cùng lane, phải còn tương thích, không bị
  thu hồi và có gate/approval hiệu lực. Đổi code/runtime không được tự chạy bundle
  cũ: cần deploy build tương thích và qualification/phê duyệt lại. Không hạ schema,
  đổi khóa, reset quota, phục hồi đè DB hoặc gửi lại hồ sơ đã giao.
- Kho release AES-GCM riêng, AAD ràng buộc scope/loại/ID; checksum khi đọc, append-only
  objects/audit/receipts/pins. Khóa lưu trữ nằm tại DN, không nằm trong bundle/HTTP.
- Trên node đã bật release service, API queue `evaluate` và `reevaluate-backlog`
  tạo vụ active bị chặn. Shadow được giữ; đọc hồ sơ, phản hồi/khắc phục và recover
  giao nhận đã lưu tiếp tục qua cơ chế hiện hữu. Không gán ngược bundle cho dữ liệu
  cũ. Harness/CLI R3 độc lập chưa phải môi trường production được phê duyệt.

## Sử dụng và vận hành

Trong Portal: **Cấu hình phân tích → Phát hành và rollback**
(`/agent2/pipeline-releases#company=C001`). Chỉ director đúng doanh nghiệp đọc/ghi
API quản trị; quyền được kiểm lại phía server. Danh tính Portal hiện vẫn là tài
khoản workspace chung, không chứng minh người rà hoặc người duyệt độc lập.

1. Chọn snapshot đã lưu, đặt tên rồi tạo bundle.
2. Chọn bundle/lane và kiểm gate. Có thể xem diff với phiên bản đang dùng.
3. Ghi lý do, duyệt staging rồi kích hoạt theo revision đang xem.
4. Chạy staging; kết quả luôn có bundle/run/snapshot/as_of. Reload để xem lại hoặc
   tiếp tục lượt chưa xong. Chọn bundle cũ đã dùng và còn đủ gate để rollback.

Backend HE đã cấu hình sẽ tự suy ra subkey release từ **job-store MAC key** bằng
HKDF salt `agent2-pipeline-release-v1`, info `enterprise-release-storage`.
Kho mới là `pipeline-releases.sqlite3` cạnh kho job, không ghi vào DB job/model.
Chưa cấu hình khóa thì API trả 503, không tự tạo khóa plaintext.

Vận hành độc lập có thể dùng `--release-config` / `AGENT2_RELEASE_CONFIG`:

```json
{
  "version": "pipeline-release-runtime/1.0.0",
  "release_db": "D:/private-agent2/pipeline-releases.sqlite3",
  "node_state_key_file": "D:/private-agent2/existing-protected-state-key.json"
}
```

Đường dẫn chỉ ở cấu hình server. Loader dùng protected-key provider hiện có,
derive job MAC subkey trước rồi derive release subkey, tương thích cách nhúng
Portal. Không tạo/đổi khóa live hoặc fallback khi DPAPI không mở được. Backup DB
release cùng cơ chế backup nhất quán của DN và giữ protected key tương ứng; không
copy kho đang ghi rồi giả định đã có backup phục hồi được. Mất khóa thì fail closed.

API director, không nhận arbitrary config/model/code/metric/pass flag:

| Route sau `/api/v1/companies/{DN}/pipeline-releases` | Chức năng |
|---|---|
| `GET /` | Bundle, gate, approval, con trỏ, lịch sử, lượt đã lưu/chờ |
| `POST /prepare` | Chụp snapshot + model pins tin cậy phía server |
| `POST /qualify` | Gate do backend tính |
| `POST /approve` | Duyệt technical staging đúng bundle/gate |
| `POST /switch` | `activate` hoặc `rollback`, CAS và lý do bắt buộc |
| `POST /revoke` | Thu hồi đối tượng, lưu lý do/audit |
| `POST /diff` | So thành phần hai bundle cùng scope |
| `POST /runs` | Chạy/tiếp tục theo `run_id` ổn định, nguồn/cutoff đã ghim |
| `GET /objects/{id}` | Đọc bundle/gate/approval/event/pin/kết quả trong DN |

Prepare/qualify/approve/switch dùng `Idempotency-Key`. Muốn qualification mới sau
thay đổi hoặc hết hạn phải dùng yêu cầu mới; màn hình giữ key khi mất phản hồi và
tạo key mới sau khi đã nhận thành công gate/approval. HTTP body là schema allowlist.

## Monitoring và giới hạn còn phải làm

Đã đo runtime và độ khả dụng từng nhánh theo DN/bundle/run, giữ numerator/denominator.
Thiếu nhánh kích hoạt yêu cầu điều tra nguồn/model; không tự train hay activate.
Fallback, backlog, thời gian rà, precision và drift chưa nối đúng provenance thì
để null kèm lý do. Đây **chưa phải** đủ monitoring R6-04.

Để phát hành toàn bộ pipeline còn cần:

1. Executor bundle cho HE/ensemble/case-budget/delivery, model train mã hóa đã duyệt,
   toàn bộ config lifecycle và job migration tương ứng; hiện executor là
   `snapshot_detector_shadow/1.0.0`, không phải wrapper HE hoặc supervised-shadow.
2. Nối artifact policy/validation/calibration/quality study từ các module khác bằng
   contract được duyệt. Không nhận “pass” hoặc ngưỡng tự khai từ browser.
3. Owner đóng D-04/05/06/07/09/17/18/19 và duyệt ngưỡng, dữ liệu, quyền phát hành;
   bộ này chưa có cơ chế tự đóng các quyết định đó bằng một config JSON.
4. Monitoring drift/fallback/backlog/review được quy về bundle và kiểm trigger;
   nghiệm thu toàn bộ R1–R5, delivery replay/rollback end-to-end và HE thật.
5. Backup/restart/deploy có kế hoạch riêng. Chưa restart Portal live, chưa đổi DB,
   khóa, model, phiên, mật khẩu hoặc quyền live; chưa push GitHub trong tác vụ này.

## Kiểm thử lại

Từ root repo, dùng venv Agent2 và đặt `PYTHONPATH=shared/finance_input/src`:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_pipeline_release --report .runtime/release-tests.json
agent2/.venv/Scripts/python.exe agent2/scripts/check_pipeline_release_ui.py --output .runtime/release-browser-new
agent2/.venv/Scripts/python.exe agent2/scripts/run_pipeline_release_acceptance.py --test-report .runtime/release-tests.json --output .runtime/release-demo-new
```

Thư mục output UI/demo phải mới để giữ chứng cứ cũ. Các fixture và nhãn nếu có
đều mô phỏng; không phải đánh giá phát hiện gian lận trên doanh nghiệp thật.
