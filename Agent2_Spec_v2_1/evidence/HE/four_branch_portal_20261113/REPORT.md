# CR-041 — Portal và bốn nhánh HE

13/11/2026 — **READY_FOR_REVIEW cho bốn profile HE giới hạn; toàn bộ CR-041
vẫn IN_PROGRESS. Đã deploy local, chưa cloud public/production.**

## Evidence hiện hành

- `native_regression_current.json`: 748 backend pass.
- `he_tests_current.json`: full HE 243 pass trước các sửa cuối.
- `he_tests_focused_final.json`: 19 focused pass sau sửa cuối, overlap full HE;
  không diễn giải thành một full suite mới.
- `portal_four_native.json`: Portal fixture, hai worker thật, khóa Concrete/DPAPI
  và signed preflight thật; C001/C002 mỗi DN đủ 5 dòng, bốn trạng thái nhánh,
  phiếu và reload cùng run. Không thay live trong phép thử này.
- `real_key_restart.json`: Concrete thật qua helper processes, DPAPI và context
  reopen; ciphertext được dùng lại, decrypt đúng 579, context DN khác bị chặn.
- `worker_hard_crash_current.json`: SIGKILL giữa native compute, qua TTL admission,
  fresh resume cùng envelope/context; một logical job, hai attempt, một cache.
- `node_hard_crash_current.json`: Windows TerminateProcess giữa native compute;
  xác thực lại rồi tiếp tục cùng envelope/context/ML child. Graph/statistics/ML
  có kết quả; P1 thiếu coverage là unavailable.
- `native_p1_optimized.json`, `native_graph_optimized.json`: đúng build tối ưu,
  native parity 2/2 và 1/1. `http_optimized_current.json`: signed HTTP P1 2/2
  và graph 1/1, committed ciphertext retrieval; graph khoảng 412 giây.
- `tabular_browser.json`: 4 checks nhập CSV/Excel. `settings_browser.json`: 4
  checks cấu hình/quyền/fit/kích hoạt/reload; circuit metadata giả trong fixture
  cấu hình, model fit thật. `analysis_browser_current.json`: 21 checks, gồm
  nguồn/bút toán đọc được, phiếu server/lọc/reload/outage, không JS error.
- Portal auth chạy lại 22/22 sau sửa launcher/send; có console test, không có
  JSON riêng để cộng vào một formal full run mới.
- `deployment_local.json`: backup/restart, four_encrypted_branches đã nạp,
  worker 8868/8869 khỏe; giữ model/snapshot/key/policy và committed records cũ.
- `live_portal_authenticated.json`: người dùng tự đăng nhập trong cửa sổ kiểm
  thử; C001/C002 mỗi DN đủ 5 kết quả và 5 phiếu, reload cùng run, không JS
  error. Không xuất mật khẩu hoặc ghi kết luận nghiệp vụ. `live-C001.png`,
  `live-C002.png` là ảnh kết quả sau reload (ảnh chụp trước lúc phiếu tải xong).
- `live_job_counts.json`: đúng một parent hoàn tất và sáu yêu cầu Concrete/DN;
  reload không sinh parent mới. Graph/thống kê/ML khả dụng, P1 thiếu nguồn và
  coverage ở dữ liệu demo nên unavailable. Không coi đây là P1 HE đã chấm đủ
  nguồn trên live; parity P1 đủ đầu vào có proof HTTP/native riêng ở trên.

HTTP/hard-crash fixture riêng mock supervisor preflight để cô lập kiểm tra;
fixture Portal native kiểm preflight thật. Bằng chứng mô phỏng không thành
người thật đã rà, accuracy, SLA hoặc duyệt DONE R0–R6.

## Evidence prototype trước adapter — giữ làm lịch sử

[Bản mô tả thay đổi, giới hạn, lỗi đã bắt và việc còn thiếu](../../../../agent2/docs/HE_FOUR_BRANCH_PROGRESS.md).

Các JSON cạnh báo cáo là report kỹ thuật, không phải dữ liệu/khóa doanh nghiệp.
Không đưa tệp private, evaluation key lớn hoặc bản mã thử vào evidence/Git.

- `he_tests.json`: full 218 pass, không skip/fail/error, trước khi thêm 8 test
  service/vault/input. 7 test HE4 reference/blob và 9 test review đã nằm trong 218.
- `native_regression.json`: 742 pass, không skip/fail/error.
- `browser_summary.json`: 19 checks Portal fixture; không thay dịch vụ live.
- `native_statistics.json`, `http_statistics.json`: actual FHE, đối chiếu thống
  kê qua tiến trình riêng và HTTP có chữ ký/streaming/cache.
- `native_p1.json`, `native_graph.json`: actual FHE của circuit nibble đã đối
  chiếu; chưa phải chứng minh adapter nguồn hoặc Portal bốn nhánh end-to-end.
- `optimized_*_build.json`: compile/simulation của circuit tối ưu; **chưa có
  native parity hoặc nghiệm thu HTTP của đúng các build này**.

Focused hiện tại 15 HE4 tests pass (overlap 7 trong full HE, thêm 8); review store
7/API 2 được chạy lại pass sau sửa cuối. Đây là output đã quan sát trực tiếp;
không có JSON full-suite mới 226 và không diễn giải thành full 226 đã chạy.

Thử nghiệm đầu: key đồ thị byte 4,62 GB bị chặn, đồ thị nibble đầu sai logic
reachability, HTTP đầu bị SESSION_POLICY_CONFLICT ở ca thứ hai. Đã sửa nguyên
nhân và chạy lại các ca được đánh dấu pass trong report; không xóa failure để
coi mọi bản build đều đạt. Lỗi boolean và session không được sửa bằng cách nới
replay/TTL hoặc trả điểm tính rõ thay thế.

Không có người thật rà các phiếu, chưa chứng minh accuracy, lợi ích ML tăng thêm
hoặc SLA. Nhận định chưa deploy/dừng worker trong report prototype là lịch sử.
Hiện local chạy thêm HE4 8869, giữ ML 8868. Chưa toàn catalog HE/33 feature,
IF–ECOD–LOF–AE, policy hàng đợi hoặc danh tính từng người rà.
