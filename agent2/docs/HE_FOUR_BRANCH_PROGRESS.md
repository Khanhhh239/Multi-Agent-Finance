# Portal và bốn nhánh HE — CR-041

Cập nhật 13/11/2026. **READY_FOR_REVIEW cho các profile HE giới hạn; toàn bộ
CR-041 vẫn IN_PROGRESS.** Chưa tự duyệt DONE R0–R6 hoặc production.

CR-042 đã bổ sung [nguồn demo P1](../examples/he4_p1/README.md) với snapshot mới
8 bản ghi/DN: hóa đơn, phân bổ và coverage/manifest; giữ một ca thiếu lịch sử.
13 focused HE + 53 P1 regression, 2 browser import checks đạt; native HTTP thực
C001/C002 mỗi DN 5/5 phép tính P1 khớp. Không thay kết quả lịch sử của bộ 5 dòng
cũ bằng kết quả này; chưa bấm chạy bốn nhánh trên live cho bộ 8 dòng mới. Xem
[evidence CR-042](../../Agent2_Spec_v2_1/evidence/HE/p1_sources_20261113/REPORT.md).

## Đã hoàn thiện kỹ thuật

- Adapter snapshot kiểm checksum/quyền, chọn nguồn theo thời điểm từng giao dịch.
  P1 dùng liên kết giao dịch–phân bổ–hóa đơn và phạm vi lịch sử thực; thiếu nguồn
  trả unavailable, không thành 0. Giữ điều chỉnh âm và kiểm nhóm đồng thời riêng.
  Không cắt nguồn để vừa circuit.
- RobustZ đọc model đã fit riêng DN; kiểm hash payload, runtime, contract 33
  feature, preprocessing, kỳ dữ liệu và receipt fit trước deserialize. Circuit
  dùng hai feature đã chọn. Chấm không fit; thiếu model là unavailable riêng
  nhánh, vẫn giữ mọi giao dịch và các nhánh khác.
- Đồ thị dùng master nhìn thấy tại thời điểm phân tích và chuẩn hóa của engine
  đang giữ. Worker tính links/reachability. Bank/phone mạnh; address/tax chỉ bối
  cảnh. Hợp đồng nguồn hiện chưa có entity-link events.
- Coordinator lưu plan, context và signed envelope trước gửi; ghim model/key
  epoch/build/implementation. Restart DN xác thực lại cả run cha và ML con,
  không tạo child mới, không lưu token. Worker chết có thể tính lại cùng bản mã;
  chỉ commit một kết quả, không hứa exactly-once native compute.
- Khóa Concrete thật được AES-GCM bọc bằng khóa dẫn xuất từ Windows DPAPI.
  Helper Linux nhận bí mật qua stdin. Provision riêng; chấm không tạo/đổi khóa.
  Checkpoint và kết quả giải mã được lưu sealed tại DN.
- Worker HE4 nhận yêu cầu trong TTL tối đa 300 giây. Phép tính đã được nhận có
  thể hoàn tất sau mốc đó. Resume cần chữ ký mới bọc nguyên envelope đã nhận,
  kiểm lại grant/scope/hash. Không nhận mới envelope hết hạn. Worker Mahalanobis
  cũ giữ nguyên sáu module, TTL và replay.
- Portal sở hữu WSL supervisor, kiểm khóa và signed readiness, dừng đúng process
  group; không nhận/dừng tiến trình lạ theo cổng. Tắt giữ model/khóa/phiên.
  Lỗi chuẩn bị thư mục worker đưa claim về retryable, không để running vĩnh viễn.
- Nhập CSV/Excel/JSON và tải mẫu mô phỏng; kiểm cột/ID/kiểu/liên kết/nguồn, báo
  sheet/dòng/trường. ID Excel phải Text để giữ số 0 đầu; tiền lớn phải Text để
  tránh làm tròn; công thức bị từ chối. Ngày mơ hồ phải chọn DMY/MDY. Đổi
  tệp/mapping phải kiểm tra lại; commit giữ idempotency và snapshot bất biến.
- Luồng nhập ở chế độ HE chuyển sang Chạy phân tích mã hóa. Mỗi giao dịch có
  trạng thái/lý do thiếu riêng cho bốn nhánh; không tự tạo điểm ensemble hoặc
  xác suất sai phạm.
- Cấu hình quản lý tách riêng: nháp → offline fit → kích hoạt. Backend kiểm
  director/model.fit, receipt/revision và model/contract; chặn đổi model khi DN
  còn run chưa xong. Binding đổi nguyên tử cùng mutex admission, có lịch sử và
  đọc lại sau restart. Fit gián đoạn hiện interrupted, cần thao tác chuẩn bị lại.
  Không tự cấp quyền cho người dùng.
- Phiếu server có căn cứ từ snapshot và tài liệu bổ sung, ba kết quả nghiệp vụ,
  căn cứ/hành động và đánh giá hữu ích độc lập. Kho AES-GCM append-only,
  revision/idempotency, thời gian kết nối server, lọc chưa rà/đã rà/kết quả và
  báo cáo JSON. Phiếu thể hiện tiền/ngày/nguồn/bút toán trước JSON kỹ thuật.
  Phản hồi chưa thành nhãn train đã xác minh.
- Lịch sử run theo tenant/company/actor, ẩn ML child cả khi cha chết trước lưu
  ID con. Giữ quyền xem kết quả/phiếu cũ. Đổi dữ liệu sau worker phục hồi sẽ
  kiểm lại readiness, không giữ nút chạy bị khóa bởi trạng thái cũ.

## Bằng chứng đã chạy

| Kiểm tra | Kết quả |
|---|---|
| Backend đầy đủ | 748 pass, không fail/error/skip |
| Full HE trước các sửa cuối | 243 pass, không fail/error/skip |
| HE focused sau sửa cuối | 19 pass: coordinator 5, worker security 7, history 2, config API 2, journal 3 |
| Portal auth chạy lại sau sửa launcher/send | 22 pass |
| Browser nhập CSV/Excel | 4 checks pass |
| Browser cấu hình/quyền | 4 checks pass; model thật, circuit metadata giả trong fixture này |
| Browser phân tích/phiếu/lọc/reload/outage | Report hiện hành tại evidence, không JS error khi đạt |
| Portal + WSL + C001/C002 native | 4 checks pass; mỗi DN đủ 5 dòng, bốn trạng thái nhánh, phiếu và reload cùng run; preflight thật |
| Helper restart + Concrete thật + DPAPI | pass, dùng lại encrypted request, decrypt 579; C002 không mở context C001 |
| Worker SIGKILL giữa compute, TTL đã qua | pass, một logical job/hai attempt, giữ envelope/context/committed ciphertext |
| DN TerminateProcess giữa compute | pass, giữ envelope/private context/ML child; graph/statistics/ML có kết quả, P1 thiếu coverage đúng nguồn |
| P1/graph tối ưu native process | 2/2 và 1/1 parity |
| P1 tối ưu signed HTTP | 2/2 parity, khoảng 207/264 giây gồm helper/transfer |
| Graph tối ưu signed HTTP | 1/1 parity, khoảng 412 giây gồm helper/transfer; vượt TTL admission vẫn hoàn tất |

19 focused có overlap với 243; không cộng thành một full suite mới.
Các proof HTTP/hard-crash riêng mock supervisor preflight để cô lập mục tiêu;
fixture Portal native kiểm preflight thật. Đây là dữ liệu mô phỏng, không phải
người thật rà, accuracy, giá trị ML tăng thêm hoặc SLA.

[Báo cáo và JSON công khai](../../Agent2_Spec_v2_1/evidence/HE/four_branch_portal_20261113/REPORT.md).
Giữ report prototype trước đó làm lịch sử. Khóa/context/bản mã lớn chỉ ở runtime,
không đưa vào evidence/Git.

## Giới hạn và phần còn thiếu

- Profile P1 tối đa 4 số nguồn mỗi tổng, signed int64 đầu vào/int128 tính;
  graph tối đa 4 đối tượng; RobustZ hai biến lượng tử 1/1024; ML Mahalanobis
  hai feature. Chưa toàn catalog luật, E3 SequenceMatcher, IF/ECOD/LOF/AE hoặc
  chấm đủ 33 feature bằng HE. Thiếu/vượt miền trả unavailable, không tự cắt nguồn.
- Chưa có trọng số, ngân sách, grouping/mandatory routing hoặc tiêu chí release
  nghiệp vụ được duyệt. Policy giữ null; chưa tự đưa vào hàng đợi nghiệp vụ.
  Danh sách phiếu theo run là công cụ rà, không phải tuyến xử lý đã duyệt.
- Portal vẫn dùng danh tính workspace chia sẻ, chưa xác minh từng người rà.
  Cần quyền theo DN và model.fit do người vận hành cấp; ứng dụng không tự nâng.
- Worker ciphertext-only đang ở WSL loopback, **chưa deploy cloud public**.
  Chưa TLS/public gateway/OS sandbox/KMS/HA, rotation/cross-machine recovery
  hoặc chứng minh tính đúng của worker ác ý. Chữ ký/hash không thay thế bằng
  chứng đúng phép tính.
- Chưa dữ liệu thật/nhãn xác minh/đối chiếu cùng ngân sách để chứng minh giá trị
  nghiệp vụ. Không tự duyệt các quyết định/mốc phụ thuộc thay người duyệt.

## Bản local hiện hành

Đã backup và restart Portal 8800, Agent2 8766; worker ML 8868 và HE4 8869 sẵn
sàng. Chế độ four_encrypted_branches đã nạp. Kho snapshot/model và DPAPI cũ giữ
nguyên; thêm model RobustZ/6 context Concrete cho C001/C002 mô phỏng, kho job mới.
Các model/snapshot/key cũ và committed worker records đã được đối chiếu với backup.

Backup private trước setup/restart ở thư mục deployment và
.runtime/backups/he4-local-20261113. Password file được sao lưu bổ sung sau
restart; startup không sửa file/mật khẩu/quyền. Không rollback replay DB về bản
cũ sau khi có yêu cầu mới.

Đã nghiệm thu authenticated trên Portal local sau khi người dùng đăng nhập:
C001/C002 mỗi DN 5 kết quả, mở 5 phiếu, reload giữ cùng run, không lỗi JS. Kho
job có đúng một parent hoàn tất/DN và sáu yêu cầu Concrete/DN; reload không tạo
run mới. Graph/thống kê/ML có kết quả; P1 thiếu nguồn/coverage được giữ unavailable.
Không ghi kết luận nghiệp vụ hoặc tạo nhãn train. Chi tiết trong
live_portal_authenticated.json, live_job_counts.json và deployment_local.json
tại evidence. Nghiệm thu kỹ thuật không thay xác nhận nghiệp vụ của người thật.

[Hướng dẫn sử dụng](HE_FOUR_BRANCH_GUIDE.md). Từ root:
agent1/.venv/Scripts/python.exe portal/server.py --start-agent2; hoặc Bật Agent2
trong Portal. Không chạy thêm process vào cùng cổng/kho.

Môi trường: Debian WSL, Python 3.12.16, Concrete 2.11.0, TenSEAL 0.3.18,
Torch 2.5.1 CPU; venv Windows/Linux riêng.
