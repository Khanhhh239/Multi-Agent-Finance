# Bàn giao Antigravity: mở rộng HE theo từng nhóm luật

Ngày 14/11/2026 · workspace `D:\agent22` · nhiệm vụ xây/kiểm chứng tăng dần,
không phải biên bản đã triển khai HE đủ 35 luật.

## Bối cảnh và mục tiêu

35 luật giữ lại đã nối vào profile nguồn đầy đủ `agent2-rule-snapshot/1.0.0`
và chạy tại node doanh nghiệp. Nguồn thiếu giữ unavailable, kết quả D/F4 theo
tập/nguồn và master/context không tự thành điểm giao dịch. Phần đó không đồng
nghĩa 35 luật đã có circuit HE.

Mục tiêu HE: DN kiểm nguồn/quyền/thời điểm, chuẩn hóa và mã hóa đầu vào; worker
chỉ tính trên bản mã và trả bản mã; DN giải mã và hiển thị. Dữ liệu rõ, model
rõ và khóa giải mã ở DN. Từng rule/profile phải khai rõ phần chuẩn bị tại DN
và phép tính thực sự được outsource. Nếu yêu cầu tính quyết định trên HE thì
không tính matched/điểm ở DN rồi mã hóa kết quả đó để gọi là HE.

Điểm luật vẫn là tín hiệu cần rà, không là xác suất gian lận. Không đặt tỷ
trọng 70–80%, tổng hợp điểm hoặc routing nghiệp vụ mới trong nhiệm vụ này.

## Phạm vi HE đã có, cần giữ tương thích

| Thành phần | Đã có | Giới hạn hiện tại |
|---|---|---|
| P1 Concrete | Sum/so sánh thanh toán, các predicate và số tiền đầu ra trên bản mã | Tối đa 4 source amounts mỗi tổng prior/current/caps; signed int64 input, word int128 tính |
| Graph Concrete | So thuộc tính, links và strong reachability trên token đã mã hóa | Tối đa 4 đối tượng; bank/phone mạnh, address/tax chỉ context; chưa phải circuit cho toàn bộ B/A3 |
| RobustZ Concrete | Abs/clip/tổng sau preprocess theo model đã fit | Hai biến, lượng tử 1/1024; chưa toàn bộ thống kê/catalog D |
| ML CKKS | Mahalanobis model đã fit riêng DN, encrypt/compute/decrypt | Hai feature đã chọn; chưa HE33 hoặc HE IF/ECOD/LOF/AE |

Nguồn hiện có chủ yếu qua adapter canonical; nối profile nguồn đầy đủ mới cần
kiểm lại provenance/semantics, không tái sử dụng điểm của snapshot khác.
Cloud worker đang là WSL/loopback thử nghiệm; chưa triển khai cloud public.

Đọc trước:
- `agent2/docs/FULL_RULE_PIPELINE.md`, `NATIVE_RULE_NODE.md`, `RULE_PARITY.md`.
- `agent2/docs/HE_FOUR_BRANCH_PROGRESS.md`, `HE_WORKER_RECOVERY.md`,
  `HE_KEYS_AND_SESSIONS.md`, `EXPANDED_BASELINE_HE.md`.
- `agent2/experiments/he4/{snapshot_adapter,inputs,circuits,build}.py`.
- `agent2/experiments/he4/{coordinator,client_transport,service,public_worker}.py`.
- `agent2/experiments/he4/{windows_bridge,enterprise_helper,vault,bundle}.py`.
- `agent2/sme_fraud/{rule_snapshot,native_rule_node,rules,noise_policy}.py`.

## Lộ trình đề xuất, không coi là danh sách đã hỗ trợ

| Lát cắt | Việc làm | Điều kiện mới được công nhận |
|---|---|---|
| 1. P1 trên nguồn đầy đủ | Adapter cùng snapshot/as_of/ứng viên → circuit P1 hiện có, giữ quy tắc có dấu/đồng thời/coverage | Đối chiếu engine đúng profile, đầy đủ nguồn và miền circuit; không gom sẵn tổng để né giới hạn 4 |
| 2. Một luật số/thời gian | Lập feasibility cho A4 hoặc C3, chọn một rule đơn vị để triển khai trước | Bao gồm đúng điều kiện áp dụng, ngoại lệ và scoring_role của engine; không chỉ so một ngưỡng rồi gọi là cả luật |
| 3. Định danh | Nghiên cứu tái sử dụng encrypted equality cho B1, rồi B5/E4 theo policy tương ứng | Đủ thuộc tính/bank identity, known masks, alias/context và phạm vi master; không suy kết quả luật từ việc graph circuit đã tồn tại |
| 4. Cửa sổ/nhóm/quan hệ | A1/A2/A3 và các luật lịch sử/HR/approval còn lại, theo nguồn thật | Không bỏ nhóm đồng thời, lịch sử/thay thế cạnh hoặc ngoại lệ để vừa circuit |
| 5. Các phép khó còn lại | E3 SequenceMatcher, D1–D6 và toàn bộ mã chưa triển khai | Có thiết kế số học/thuật toán, miền dữ liệu và chi phí khả thi; nếu chưa đạt ghi unavailable/unsupported trung thực |

Thứ tự sau lát cắt 1 là đề xuất kỹ thuật cần chốt qua feasibility và đối chiếu
engine. Không cam kết toàn 35 luật HE khả thi trên cấu hình hiện tại hoặc dùng
thuật toán gần đúng khác rồi giữ tên luật cũ. Các mã không nhắc trong bảng vẫn
phải có trong inventory 35 luật, không bị bỏ quên.

## Hợp đồng cần chốt cho mỗi rule/profile

Lập bảng có rule ID, evaluator/oracle cụ thể, source/coverage và cutoff,
candidate/history scope, input shape/miền số, đơn vị/timezone, private/public
fields, phép chuẩn bị tại DN, phép tính HE, output shape/score/exceptions,
build/key versions và lý do unavailable. Ghim hash engine/policy dùng đối chiếu.

Chuẩn bị nguồn tại DN được kiểm schema/quyền/checksum, lọc point-in-time,
chuẩn hóa/encode/mã hóa. Với P1, đưa từng source amount/loại điều chỉnh vào
circuit; không truyền tổng đã rút gọn thay nguồn bị bỏ. Với graph, đưa thuộc
tính/token đã mã hóa; không đưa cạnh/cụm đã quyết định tại DN để giả cloud tính.
Tách rõ kiểm nguồn trước tính với kết quả business predicate của circuit.

Bank token phải có semantics đúng engine; mã định danh/hash làm kênh kỹ thuật
không là predictor. Token/hash, known/active masks và policy input nhạy cảm phải
được mã hóa theo profile. Public build/rule ID, shape, số request, timing có thể
lộ metadata; ghi threat boundary và padding nếu cần, không hứa HE giấu mọi thứ.
Không coi mã hash rõ của bank/phone có miền dễ đoán là đã bảo mật dữ liệu.

Integer money so exact, giữ dấu/zero, kiểm range/overflow trước encrypt. Phép
float/lượng tử phải khai scale, rounding, error budget trước khi đo; ca sát
ngưỡng không được lặng lẽ đổi matched. Không tự làm tròn để đạt parity.
Không dùng missing=0; mask/padding 0 nội bộ phải phân biệt với giá trị 0 có nguồn.

Vượt số source rows/nodes/range: unavailable rõ. Muốn batching/chunking phải
chứng minh giữ tổng, cặp cross-chunk, reachability toàn cụm và grouping; chưa
có chứng minh thì không lấy 4 bản ghi đầu hoặc cắt dữ liệu cho circuit chạy.
Giữ các giới hạn signed/late-source của native oracle; nếu oracle không hỗ trợ
miền nào thì ghi rõ, không tạo số kỳ vọng giả bằng cách sửa ngày/abs nguồn.

## Triển khai kỹ thuật

1. Chốt inventory 35 luật: local evaluator, HE input adapter, circuit, HTTP,
   coordinator, UI và evidence ở từng mức. Đăng ký tên không là implemented.
2. Xây một lát cắt trong sandbox C001/C002. Phiên bản hóa input/output/build
   và worker allowlist. Coordinator hiện ghim ba Concrete profile; không thêm
   tùy ý circuit/path nhận từ browser hoặc sửa config v1 không migration.
3. Ghim snapshot/checksum/as_of, rule/policy/bridge/build, grant/scope, key epoch
   và model nếu có. Lưu plan/envelope/context trước gửi; không sửa yêu cầu cũ
   khi code/build đổi. Model/key/build sai phải unavailable/rejected rõ.
4. Provision khóa/build mới là thao tác quản trị riêng theo DN nếu cần; không
   ghi đè khóa cũ hoặc tự keygen trong lượt chấm. Giữ epoch cũ để đọc/decrypt
   kết quả cũ. Helper Windows/WSL và DPAPI phải restart được đúng user/state.
5. HTTP trả ciphertext; DN recheck auth và binding trước decrypt/công bố.
   Worker bundle không có DB nguồn, model rõ, khóa giải mã hoặc code enterprise.
6. Chỉ sau parity/security/recovery mới nối Portal ở chế độ rõ ràng, có backup
   riêng. Mỗi giao dịch giữ đủ trạng thái từng luật/nhánh; thiếu một luật không
   xóa dòng hoặc gắn kết quả partial thành full-HE/full-catalog.

Giữ semantics admission TTL HE4: tối đa 300s để nhận mới; request đã được nhận
có thể hoàn tất sau đó, resume bằng wrapper/chữ ký mới ràng buộc envelope cũ.
Không mở lại envelope mới đã hết hạn, tạo nonce mới cho cùng yêu cầu hoặc thay
TTL/replay của worker Mahalanobis cũ để né phép tính chậm.

## Nghiệm thu bắt buộc cho từng lát cắt

- Ba mức riêng: plain reference circuit; native Concrete/CKKS thật; HTTP worker
  thật và coordinator. Test mock không được ghi là proof FHE end-to-end.
- Cùng snapshot/source/as_of/policy so với engine tại DN. Đối chiếu matched,
  applicability, availability, tiền/điểm, ngoại lệ/suppression và scope. Kết quả
  source-level D/F4 không gán lại thành điểm từng giao dịch. B5/E4 không cộng đôi.
- Ca trúng, chưa trúng, sát ngưỡng, zero, signed adjustment, đồng thời, lịch sử
  thiếu, nguồn đến muộn, revision thay thế và ngoài miền input. Ghi rõ ca không
  áp dụng; không loại chúng khỏi mẫu số để báo mọi ca đều pass.
- C001/C002 có ID giống nhau; kiểm wrong scope/key/build, corrupt ciphertext,
  replay và mismatch request hash bị chặn. Không chia sẻ secret key giữa DN.
- HTTP mất kết nối; worker SIGKILL giữa compute; node DN crash sau persist trước
  gửi, sau gửi trước nhận, sau nhận trước commit/decrypt; job dài vượt TTL.
  Resume cùng logical ID/envelope/context/key/build, chỉ một kết quả commit;
  phép tính native có thể chạy lại trên cùng bản mã, không hứa exactly-once compute.
- Đọc lại kết quả completed sau restart; artifact/ciphertext/khóa cũ không đổi.
  Request hết hạn/mất state/corrupt state phải báo đúng, không hồi sinh terminal
  failure bằng việc đổi nonce hoặc khôi phục replay DB cũ.
- Ghi compile/keygen/encrypt/upload/queue/compute/download/decrypt riêng, peak
  RAM, số byte ciphertext/evaluation keys và thời gian retry. Với float ghi
  sai số/max error/ranking theo ngưỡng chốt trước; với tiền/matched yêu cầu exact
  trong miền đã cam kết. Báo cả thất bại và ca chưa chạy; chưa coi là SLA.
- Kiểm worker file/network/log không nhận plaintext/model/secret key. Hash/chữ
  ký bảo vệ binding không tự chứng minh worker ác ý tính đúng; ghi giới hạn này.
- Chạy hồi quy luật, HE lifecycle/security và Portal bị tác động. Không phá luồng
  cũ đang chạy hoặc dừng agent khác trong lúc benchmark.

## Đầu ra cần bàn giao

Inventory đủ 35 mã; thiết kế và code của lát cắt mới; contract/build manifest;
bộ source test có checksum và expected tách khỏi input; báo cáo parity từng ca,
nguồn/engine/model/key/build pins, chi phí và recovery matrix; hướng dẫn vận hành
và rollback. Bằng chứng public đã loại credential/key/context private.

Trạng thái mỗi lát cắt tách thành thiết kế / plain parity / native HE / HTTP /
recovery / Portal, không dùng một PASS chung che phần chưa triển khai. Ưu tiên
hoàn tất lát cắt P1 nguồn đầy đủ trước rồi mới mở nhóm tiếp theo.

Không triển khai public cloud, đổi khóa/model live, restart live hoặc push Git
trong nhiệm vụ xây circuit nếu chưa được giao triển khai riêng. Cloud public
còn cần threat model, TLS/gateway/access policy và vận hành riêng; localhost
native HE pass không thay nghiệm thu đó. Nếu phải đổi spec/contract, tuân quy
trình Agent2_Spec_v2_1, không tự duyệt toàn R2/production.
