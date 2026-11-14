# Bổ sung nguồn P1 — 13/11/2026

**READY_FOR_REVIEW: nguồn/reference và HE native đạt.** Không tự duyệt
nghiệp vụ, accuracy hoặc các mốc R0–R6.

Người dùng giao bổ sung hóa đơn, phân bổ thanh toán, phạm vi lịch sử và thử ca
chưa vượt/đã vượt/điều chỉnh âm/đồng thời, giữ ca thiếu nguồn unavailable.

## Bộ dữ liệu và kiểm tra nguồn

- [Hướng dẫn và tệp demo](../../../../agent2/examples/he4_p1/README.md): mỗi DN
  một tệp JSON, 8 giao dịch, 3 hóa đơn, 8 phân bổ và 6 coverage/manifest. Giữ
  khoản trả trước và bút toán điều chỉnh; không cắt lịch sử cho vừa circuit.
- C001 và C002 dùng cùng mã giao dịch nhưng tách theo DN. Tiền C002 bằng ba
  lần C001, trạng thái/điểm riêng luật giữ nguyên. Expected outcomes nằm ngoài
  source và feature; nguồn luôn có is_simulated=true.
- C001: 6 + 3 = 9/10 chưa vượt; 9 + 3 = 12/10 vượt 2; điều chỉnh −4 đúng
  khoản gốc làm lịch sử còn 8, trả thêm 1 thành 9/10; hai khoản 4 cùng lúc,
  từng khoản 4/6 không trúng nhưng nhóm 8/6 vượt 2, điểm nhóm 20 riêng.
- Ca T08 có hóa đơn và phân bổ thật trong gói mô phỏng, nhưng không có coverage
  cho nghĩa vụ P1_I_GAP: unavailable, score/matched null, không gửi P1 HE.
- Kết quả riêng từng DN: evaluated_hit=1, evaluated_no_hit=5,
  not_applicable=1, unavailable=1. P1_T04 là điều chỉnh, không xem là khoản trả
  mới; tác dụng điều chỉnh được kiểm ở P1_T05.
- Manifest kiểm ID/revision/count/checksum đúng phạm vi nguồn mô phỏng. Không
  coi checksum là bằng chứng sổ sách của DN thật đã đầy đủ.

## Evidence đã quan sát

| Bằng chứng | Kết quả |
|---|---|
| focused_he_tests.json | 13 pass: 7 ca mới + 6 adapter hiện có; gồm vượt 4 nguồn không cắt/gộp |
| p1_regression.json | 53 pass P1 evaluator/input/native timing |
| import_browser.json | C001/C002 nhập JSON → preview → xác nhận → lưu đạt; không JS error; fixture riêng |
| C001_engine.json, C002_engine.json | Tính thủ công/reference circuit/engine P1 hiện có khớp toàn bộ 8 dòng |
| source_preparation.json | Tệp/checksum và hai snapshot mới đã lưu vào local demo |
| C001_native_http.json | 5/5 đầu vào P1 mã hóa khớp kết quả thủ công/engine/reference |
| C002_native_http.json | 5/5 đầu vào P1 mã hóa khớp, scope/key riêng C002, số tiền gấp ba |

Reference circuit là phép tính rõ để đối chiếu, không phải native HE proof.
Native HTTP dùng source snapshot mới, adapter đầy đủ, khóa Concrete thật đã
được DPAPI bảo vệ trong fixture; không lấy expected outcome làm đầu vào cloud.
Worker riêng, không thay worker hoặc model/key của bản live.

Năm đầu vào mã hóa/DN tương ứng T02, T03, T05 và hai phép tính riêng/nhóm của
T06/T07. Hai thành viên đồng thời có đầu vào số giống nhau nên dùng chung kết
quả tính trong fixture này, không cộng điểm hai lần. T01 là khoản neo lịch sử,
được kiểm trong source/engine/reference; không có phép chấm HE riêng T01 trong
phép thử mới. T04 not_applicable và T08 unavailable không gửi P1 HE.

Response có chữ ký/scope/hash được kiểm trước giải mã; fresh result retrieval
trả lại đúng committed ciphertext. Đây là Concrete thực, không simulation hoặc
thay kết quả bằng chấm rõ. Supervisor preflight bị mock riêng trong fixture để
cô lập P1; CryptoBridge vẫn mở khóa DPAPI/context Concrete thật và kiểm build.
Không gọi đây là nghiệm thu toàn luồng Portal live cho bộ mới. Hai worker thử
đã dừng theo ownership sau khi hoàn tất, giữ worker live đang chạy.

Mỗi phép thử mất khoảng 286–365 giây gồm helper, truyền nhận và tính HE trên
máy hiện tại. Đây chưa phải SLA; chấm cả tệp qua bốn nhánh có thể lâu hơn và
cần tiếp tục cùng yêu cầu nếu phiên đăng nhập hết hạn.

## Bản local

Đã thêm snapshot bằng luồng upload/preview/commit với actor kỹ thuật
p1-demo-setup-operator, không tạo phiên Portal giả hoặc đổi quyền người dùng:

- C001: snp_25b7fd36815346619377fd430b9002fc.
- C002: snp_2b8bce04da224fc2aa71f94a496ccfed.

Đã online-backup kho snapshot trước thêm tại runtime riêng. Đối chiếu đủ 5
snapshot cũ còn nguyên, chỉ thêm 2 snapshot. Giữ model, khóa, cấu hình, các lần
chạy và phiếu cũ; không restart Portal, không tạo nhãn hoặc ghi hàng đợi.

Nghiệm thu giao diện nhập ở fixture không đồng nghĩa đã bấm chạy bốn nhánh
cho bộ 8 dòng trên Portal live. Bộ 5 dòng cũ và nghiệm thu live trước đó được
giữ làm lịch sử. Phép thử này tập trung nguồn và P1; profile/catalog HE và các
quyết định nghiệp vụ khác giữ giới hạn như CR-041.
