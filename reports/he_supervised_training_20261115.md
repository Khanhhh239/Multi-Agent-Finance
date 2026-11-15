# Prototype train có nhãn trên bản mã — 15/11/2026

**READY_FOR_REVIEW kỹ thuật.** Đã chạy sáu bước trên C001/C002 mô phỏng:
mã hóa/upload dữ liệu → biên nhận → xác minh và mã hóa nhãn/consent → cloud
worker train ciphertext → trả model ciphertext → doanh nghiệp giải mã, đối
chiếu và phê duyệt shadow. Chưa nối Portal hoặc deploy cloud public.

## Mục tiêu và phạm vi

Người dùng đã chọn nhãn **gian lận đã xác minh / đã xác minh không gian lận**.
Nhãn null, inconclusive, confirmed_risk hoặc legitimate của phiếu rà cũ không
tự thành nhãn này. Người xác minh phải có quyền, thời điểm và mã căn cứ; review
được ràng buộc tenant/company/dataset/biên nhận trước khi mã hóa y.

Model thử là **SGD logistic nhị phân lượng tử hóa tự xây bằng Concrete FHE
2.11.0**, không phải adapter Concrete ML SGDClassifier. Có 4 dòng, 2 biến trong
{-1,0,1}, 2 bước train trong nghiệm thu. Chưa hỗ trợ 33 feature hoặc nhập nguyên
snapshot tài chính vào train; không thay model không nhãn đang dùng.

Cloud chạy một circuit SGD update nhận X, y và weights đều encrypted, sau đó
đưa encrypted output weights vào bước tiếp theo. Không decrypt ở worker; không
fit rõ rồi mã hóa model. LUT sigmoid là hàm công khai trên miền số cố định.

## Kết quả kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Phương trình vector so scalar oracle và circuit simulation | 144 ca build qua |
| Consent, nhãn, quyền, scope, checksum, idempotency, checkpoint, approval | 14 unit test qua |
| Native Concrete + HTTP worker riêng + DPAPI doanh nghiệp | 2/2 doanh nghiệp qua |
| C001, hai bước train | Weights khởi tạo [0,0,0] → kết quả [2,0,0], khớp oracle |
| C002, nhãn mô phỏng đảo chiều | Kết quả [-2,0,0], khớp oracle, khác C001 |
| Restart worker sau hoàn tất và mở lại enterprise với khóa thật | Cùng model ciphertext/hash và kết quả giải mã |
| Nhấn upload/confirm/run lại | Cùng biên nhận/job; không train thêm sau hoàn tất |
| Model trước phê duyệt | Không cho chấm shadow |

Đây là kiểm chứng tính toán và luồng, không phải người thật đã xác minh 8 khoản
gian lận/không gian lận. **0 nhãn nghiệp vụ thật**; accuracy/precision/recall
giữ null. Chấm shadow local trả điểm chưa hiệu chỉnh, không kết luận gian lận
hoặc đưa vào hàng đợi.

## Chi phí và giới hạn

Lượt HE HTTP sau chốt ràng buộc nhãn: C001 khoảng **35,75 giây**, C002 khoảng
**30,95 giây** cho 2 update. Chưa gồm toàn bộ mã hóa/đọc khóa/giải mã. Evaluation
keys mỗi DN **1.346.667.680 byte**, private context sealed cũng lớn. Không suy
SLA từ hai lượt mô phỏng. Báo cáo JSON giữ riêng thời gian provision context
lạnh của lượt đầu và lượt cuối tái sử dụng context bất biến.

Bản thử miền số lớn hơn đã dừng sinh khóa khi dùng nhiều RAM; chỉ profile miền
hẹp nêu trên được nghiệm thu HE thật. Không suy profile lớn hơn đã chạy được.

Native restart ở lần này xảy ra **sau hoàn tất**; checkpoint giữa các update có
unit test với byte giả. Chưa nghiệm thu native SIGKILL giữa compute. Không cam
kết exactly-once native computation, tính đúng trước worker ác ý hoặc sandbox
hệ điều hành cho tiến trình cùng tài khoản.

## Mã và cách chạy

- `agent2/experiments/he_training/`: circuit, build, worker/store, enterprise
  crypto helper, consent và CLI operator tách biệt.
- `agent2/scripts/demo_encrypted_training.py`: demo HTTP/native riêng.
- `agent2/scripts/encrypted_training.py`: thao tác prepare/upload/review-template/
  confirm/run/receive/approve/shadow từng bước bằng config/token-file private.
- `agent2/tests_he/test_encrypted_training.py`: kiểm lifecycle; không thay HE thật.

[Hướng dẫn](../agent2/docs/HE_SUPERVISED_TRAINING.md),
[mẫu và cách xác minh nhãn](../agent2/examples/encrypted_training/README.md),
[kết quả JSON](he_supervised_training_20261115.json),
[bằng chứng công khai](../Agent2_Spec_v2_1/evidence/HE/supervised_training_20261115/REPORT.md).

## Bảo toàn

Không sửa Portal, pipeline 35 luật, MethodStore, model/khóa/DB/quyền hoặc tiến
trình live. Worker bundle chỉ có chương trình công khai, evaluation keys và
ciphertext; không có enterprise.py/helper.py, private context, X/y rõ hoặc model
giải mã. Khóa ký riêng của worker phục vụ biên nhận không phải khóa bí mật HE.

Keys, token/config operator, ciphertext và dữ liệu private chỉ ở `.runtime`;
bằng chứng công khai là allowlist báo cáo, unit outcomes và build/source hashes.
Không push Git trong tác vụ này. Không tự chốt DONE R0–R6 hoặc active sản xuất.
