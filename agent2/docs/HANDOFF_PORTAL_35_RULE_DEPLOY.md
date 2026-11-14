# Bàn giao Antigravity: cập nhật Portal để dùng pipeline 35 luật

Ngày 14/11/2026 · workspace `D:\agent22` · phạm vi: triển khai local và nghiệm thu,
không viết lại thuật toán hoặc triển khai cloud public.

## Bối cảnh và mục tiêu

Agent2 được xây lại theo spec v2.1. Bản code hiện tại đã nối 35 luật giữ lại qua
nhập → kiểm tra → xác nhận lưu snapshot → phân tích → xem kết quả, bằng profile
`agent2-rule-snapshot/1.0.0`. Mã này đã qua 140 ca trúng/đối chứng trên 120 gói
C001/C002, 255 kiểm thử hồi quy và 6 bước UI trên server kiểm thử riêng.

**Chưa deploy bản này lên Portal live.** Nhiệm vụ là nạp đúng code mới vào dịch
vụ local hiện có và nghiệm thu qua đăng nhập Portal, bảo toàn dữ liệu/model/khóa
và job phân tích cũ. Không cần xây lại 35 luật hoặc chạy lại fit model.

Luật chỉ là một thành phần, không cấu hình tỷ trọng 70–80%. Profile nguồn đầy
đủ mới chạy tại node DN theo lựa chọn của người dùng; không gửi dữ liệu rõ lên
cloud. Canonical cũ vẫn bốn adapter P1/E3/B5/E4; profile mới chưa có bridge ML33
feature hoặc HE35. Không đổi nhãn này để báo hoàn thành bốn nhánh.

## Điểm vào và tệp liên quan

- Portal `http://127.0.0.1:8800/#agent2`; Agent2 DN cổng 8766.
- Worker CKKS 8868; worker Concrete 8869 qua WSL Debian, do Portal quản lý.
- `portal/config.local.json` là nguồn cấu hình thực tế. Đọc lại trước thao tác;
  không dùng config.example hoặc các hướng dẫn platform cũ để ghi đè.
- Pipeline: `agent2/sme_fraud/rule_snapshot.py`, `rule_snapshot.schema.json`,
  `imports.py`, `import_files.py`, `snapshot_analysis.py`, `rule_evaluation.py`.
- API/UI: `agent2/sme_fraud/analysis_api.py`, `web/workbench.js`.
- Proxy allowlist: `portal/agent2_bridge.py`; quản lý process ở
  `portal/server.py`, `portal/agent2_runtime.py`, `portal/agent2_he4_runtime.py`.
- API catalogue quản lý: `GET /api/v1/companies/{company}/rules/catalogue`.
  Proxy Portal thêm prefix `/agent2`. Technical/catalogue vẫn phải kiểm quyền.

## Trạng thái phải bảo toàn

Các đường dẫn dưới được đối chiếu config ngày 14/11; cần resolve lại từ config
nếu đã có người khác thay đổi. Không in nội dung khóa/token vào log hoặc chat.

| Nhóm | Vị trí hiện tại |
|---|---|
| Đăng nhập, hồ sơ workspace và config Portal | `portal/workspace/`, `portal/config.local.json` |
| Snapshot, model, auth, bindings, khóa DPAPI và state CKKS | `agent2/.runtime/he-company-demo/enterprise/` |
| Bindings phân tích local được Portal chọn | `agent2/.runtime/he-company-demo/activation_20261112/local-analysis-bindings.json` |
| Config/bundle/state worker CKKS | `agent2/.runtime/he-company-demo/worker/` |
| Config/build/helper/jobs enterprise và worker Concrete | `agent2/.runtime/he-four-managed-v1/`; đọc thêm đường dẫn Linux được config tham chiếu |

Model DB là `enterprise/models.sqlite3`, snapshot DB là
`enterprise/snapshots.sqlite3` trong he-company-demo. Khóa bọc
`state-wrapping.dpapi.json` và khóa ký `node-signing.dpapi.json` phải giữ nguyên.
DPAPI gắn với tài khoản Windows; chạy lại bằng đúng tài khoản, không tạo khóa
thay thế khi lỗi giải mã. Giữ cả worker replay/cache và enterprise job/context.

## Trình tự thực hiện

1. Kiểm kê config, PID/command/cwd và ownership từng dịch vụ; đọc trạng thái job
   trước khi dừng. Ghi snapshot ID, model/artifact ID/hash, job ID/trạng thái và
   kết quả đã hoàn tất làm mốc so sánh. Không lấy port mở làm bằng chứng đúng code.
2. Không nhận lượt mới trong cửa sổ cập nhật; để job đang tính hoàn tất hoặc dùng
   cơ chế dừng/checkpoint hiện có. Dừng đúng Agent2 và worker do Portal sở hữu;
   không kill process chỉ theo port hoặc tên python. Không dừng Agent1/3/4.
3. Tạo backup private có timestamp ngoài vùng public/Git. SQLite dùng backup API
   nhất quán hoặc sao lưu sau khi đã đóng writer; không chỉ copy file .sqlite3
   đang ghi và bỏ WAL. Backup config, bindings, model/snapshot/job stores, khóa,
   state/cache/build cần để tiếp tục yêu cầu. Giữ quyền truy cập file private.
4. Ghi manifest/hash bản backup và kiểm khả năng mở bản sao. Xác định code/config
   rollback có thật; nếu không có bản code đang deploy thì báo giới hạn đó, không
   gọi bản sao source hiện tại là bản cũ đã được chứng minh rollback. Không dùng
   git reset/clean hoặc checkout toàn repo: workspace có nhiều thay đổi chưa commit.
5. Nạp code mới. Chỉ restart Portal nếu cần nạp proxy/allowlist; kiểm hành vi
   cleanup của server trước để không kéo theo agent khác. Bật Agent2 bằng lifecycle
   hiện có, không chạy thêm standalone node/worker với cùng state_dir.
6. Kiểm health và preflight đúng khóa/model/worker, sau đó đăng nhập Portal bằng
   luồng hiện có. Nếu cần người dùng đăng nhập thì để họ nhập trên trình duyệt;
   không bypass auth, lấy mật khẩu từ chat hoặc ghi token vào evidence.
7. Nghiệm thu cả luồng mới và luồng cũ theo bảng dưới. Nếu lỗi, ưu tiên rollback
   code/config, giữ nguyên state đang lưu. Không tự restore DB cũ sau khi đã có
   dữ liệu/job mới vì sẽ làm mất phát sinh; phải có phương án đối chiếu trước.

Restart Portal có thể làm mất phiên **đăng nhập trình duyệt** và cần đăng nhập
lại. Việc phải giữ là **job/context/model/key và kết quả phân tích**, không hứa
giữ nguyên cookie đăng nhập. Hai loại “phiên” này khác nhau.

## Tiêu chí nghiệm thu

- Đăng nhập → mở Agent2 từ Portal; các agent khác vẫn giữ trạng thái trước đó.
- Nhập JSON từ `agent2/examples/full_rules/`, kiểm tra, lưu và bấm **Xem 35 luật
  tại node doanh nghiệp**. Xem đúng DN, snapshot/as_of, lý do/căn cứ/hành động.
- C001/C002 có ca tín hiệu và đối chứng; ca coverage unknown giữ unavailable,
  không chuyển thành no-hit/0. D/F4 hiển thị theo nhóm/nguồn, không điểm giao dịch.
- Tài khoản không có quyền quản lý không mở catalogue/technical; không cấp thêm
  quyền để làm test qua. Dùng test principal riêng nếu cần, không mở quyền live.
- Snapshot và artifact cũ giữ định danh/checksum nội dung; model không fit lại;
  khóa giữ nguyên. SQLite header/hash toàn file có thể đổi khi mở, nên đối chiếu
  dữ liệu bất biến/metadata chứ không chỉ checksum vật lý toàn DB.
- Một kết quả HE cũ đọc lại được sau restart, cùng job ID/model/key. Job còn hợp
  lệ tiếp tục bằng cơ chế resume hiện có, không tạo yêu cầu mới để che mất state.
  Job hết hạn vẫn báo hết hạn, không mở lại bằng cách đổi TTL/nonce.
- C001 không đọc được dữ liệu C002 ngoài quyền; không có plaintext fallback lên
  cloud, không sửa worker bundle/model/feature contract để né preflight.
- Không tự gán kết luận gian lận, accuracy, trọng số hoặc nối queue nghiệp vụ.

## Đầu ra Antigravity cần bàn giao

Báo cáo ngắn gồm: backup ở đâu; dịch vụ/PID nào đã restart; code/version đã nạp;
bảng nghiệm thu pass/fail; ID/hash bất biến trước/sau; lỗi còn lại và cách rollback.
Không đưa DB, khóa, config private hoặc token lên Git. Nếu người khác đang sửa
cùng các tệp trên thì thống nhất quyền sửa trước; phạm vi mặc định là vận hành,
không đổi engine/feature/model. Không push Git khi chưa được yêu cầu.

Tài liệu đối chiếu:
[pipeline và schema](FULL_RULE_PIPELINE.md),
[bằng chứng CR-050](../../Agent2_Spec_v2_1/evidence/R2/full_rule_pipeline_20261114/REPORT.md),
[lifecycle worker](HE_MANAGED_WORKER.md), [mẫu nhập](../examples/full_rules/README.md).
