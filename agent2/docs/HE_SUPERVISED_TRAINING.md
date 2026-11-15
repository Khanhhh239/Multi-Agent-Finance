# Prototype huấn luyện có nhãn trên dữ liệu mã hóa

Đã bổ sung [snapshot → dữ liệu train](HE_TRAINING_SNAPSHOT_ADAPTER.md): đọc kho
snapshot chỉ đọc, ánh xạ hai feature binary đã có, preview/pin provenance trước
khi mã hóa. Giới hạn 4 dòng/2 biến giữ nguyên; chưa phải train toàn bộ 33 feature.

15/11/2026. Nhánh thử nghiệm riêng theo chỉ đạo mới của người dùng; không thay
ML không nhãn, 35 luật, model đang ghim hoặc Portal live.

## Luồng đã xây

1. Node doanh nghiệp giữ nguồn rõ, ánh xạ mã giao dịch và khóa bí mật. Mã hóa
   ma trận train theo hợp đồng số học cố định.
2. Upload bản mã X. Worker gửi biên nhận ký, khóa checksum bản mã/build/key epoch.
   Upload chưa tạo job train.
3. Người có quyền xác minh điền nhãn tại doanh nghiệp. Người có quyền model.fit
   xác nhận train. Nhãn y và trọng số khởi tạo đều được mã hóa bằng cùng context;
   consent ký ràng buộc đúng dataset, biên nhận, revision nhãn và số bước train.
4. Worker chạy SGD trên ciphertext X, y và weights. Trọng số đầu ra mã hóa được
   đưa vào bước tiếp theo; worker không giải mã ở giữa các bước.
5. Doanh nghiệp nhận model mã hóa, kiểm chữ ký/context, giải mã bằng khóa đã lưu
   và đối chiếu chính xác với phương trình SGD lượng tử hóa tính riêng tại DN.
6. Model là candidate. Phải có thao tác phê duyệt riêng mới dùng được hàm chấm
   shadow local. Chưa đưa vào MethodStore/catalog hay hàng đợi nghiệp vụ.

Nhãn mục tiêu: `verified-fraud/1.0.0`, gồm `verified_fraud` và
`verified_non_fraud`. Không lấy cảnh báo luật, điểm ML hoặc kết quả “có vấn đề
cần xử lý” làm nhãn gian lận. Nhãn null/chưa đủ căn cứ không được train.
File nhãn có tenant/company/dataset/receipt binding; dòng được ghép theo ID,
không dựa vào thứ tự tệp người rà gửi. Kết quả đọc lại không yêu cầu xác minh
nhãn mới: kiểm consent/HMAC của lần xác minh đã lưu.

## Thuật toán và giới hạn

Profile `experimental-quantized-logistic-sgd-2d/0.1.0` là circuit SGD logistic
nhị phân tự xây bằng Concrete FHE 2.11.0. **Không phải adapter
Concrete ML SGDClassifier** và không dùng `.fit` rõ rồi mã hóa model.

- Một batch 4 dòng, 2 biến mã nguyên trong `{-1,0,1}`; không ép 33 feature vào
  profile này hoặc tự học preprocessing trên dữ liệu doanh nghiệp ở cloud rõ.
- Hệ số mã nguyên `[-2,2]`, scale2; intercept `[-4,4]`, scale2. Sigmoid LUT công
  khai lượng tử về 5 mức `0..4`. Learning rate1, batch size4, tối đa4 bước.
- LUT là hàm sigmoid trên miền công khai, không chứa dữ liệu/nhãn/model khách.
- Toàn bộ X/y/weights là input encrypted. Output là encrypted weights; chương
  trình composable cho phép tiếp tục bước mới không giải mã.
- Đối chiếu với phương trình lượng tử hóa; không tuyên bố tương đương model
  logistic float đầy đủ, hội tụ, xác suất hiệu chỉnh hoặc accuracy gian lận.
- Giá trị/model ngoài miền, số dòng khác4, số biến khác2: từ chối. Không cắt
  dòng/cột, không ép nhãn chưa xác minh thành0, không fallback tính rõ tại worker.

## Lưu trữ và quyền

Node-signing và state-wrapping keys dùng Windows DPAPI current-user. Context
Concrete thật lưu AES-GCM sealed dưới khóa bọc này; helper Linux chỉ nhận khóa
bọc qua stdin. Không truyền khóa bí mật bằng argv, token hoặc request cloud.

Worker có circuit công khai, evaluation keys, ciphertext, SQLite job/checkpoint
và khóa ký riêng của worker. Bundle allowlist không có enterprise.py/helper.py,
sealed context doanh nghiệp, nguồn rõ, nhãn rõ hoặc model đã giải mã.

CLI dùng FileAuthorizer riêng: `data.import`, `evidence.verify`, `model.fit`.
Kiểm lại context trước/sau helper và HTTP. Không cấp quyền Portal, không dùng
mật khẩu Portal làm token, không tự chuyển phiếu rà hiện có thành nhãn train.
Prototype hiện yêu cầu cùng actor xác minh các dòng; chưa có UI nhiều người
duyệt hoặc cơ chế xác minh danh tính cá nhân từ Portal workspace dùng chung.

Server ký biên nhận; chữ ký không chứng minh cloud ác ý đã train đúng. Đối chiếu
rõ và bản mã trong prototype là kiểm chứng kỹ thuật. Tách process/bundle không
phải sandbox hệ điều hành trước tiến trình độc hại cùng tài khoản.

## Chạy demo HE thật

Cần Windows DPAPI và WSL Debian với runtime Concrete opt-in hiện có. Không cài
thêm Concrete ML hoặc thay venv phục vụ HE/Portal live. Dùng thư mục output mới:

```powershell
wsl.exe -d Debian --cd /mnt/d/agent22/agent2 --exec /home/sang/.local/share/agent2/he4/bin/python -m experiments.he_training.build --output /mnt/d/agent22/.runtime/he-training-new/build
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_encrypted_training.py --build .runtime/he-training-new/build --output .runtime/he-training-new/demo
```

Demo dùng C001/C002 và nhãn **synthetic_expected**, không có nhãn gian lận thật.
Build compile bằng miền mẫu công khai, không sử dụng dữ liệu khách. Worker HTTP
loopback chạy riêng, tự dừng khi xong; chưa deploy cloud public/TLS/multi-key.

Kiểm thử lifecycle dùng byte giả để kiểm consent/checkpoint, không thay thế HE:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_encrypted_training --report .runtime/training-tests.json
```

## Thao tác operator từng bước

Dùng config riêng theo `examples/encrypted_training/config.example.json`.
Quản trị cấp policy/token và public worker key qua kênh tin cậy; không copy
config live vào Git. Mỗi lệnh yêu cầu đường dẫn output mới:

```powershell
# Cấu hình/token là tệp private tại doanh nghiệp; không đặt token trên command line.
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py prepare --config CONFIG --token-file TOKEN_FILE --data DATASET --output OUT1
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py upload --config CONFIG --token-file TOKEN_FILE --output OUT2
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py review-template --config CONFIG --token-file TOKEN_FILE --output LABEL_TEMPLATE
# Người rà điền LABEL_TEMPLATE bằng căn cứ đã xác minh rồi mới xác nhận:
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py confirm --config CONFIG --token-file TOKEN_FILE --labels REVIEWED_LABEL_FILE --output OUT3
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py run --config CONFIG --token-file TOKEN_FILE --output OUT4
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py receive --config CONFIG --token-file TOKEN_FILE --output OUT5
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py approve --config CONFIG --token-file TOKEN_FILE --reason-file REASON_FILE --output OUT6
```

Các lệnh ở trên chạy từ repo root. CONFIG/TOKEN_FILE/DATASET/OUT là ký hiệu,
cần thay bằng đường dẫn private thực tế. Chưa có màn hình Portal cho luồng này.

Worker giữ checkpoint sau mỗi bước. Retry cùng consent/job trả cùng kết quả;
restart tiếp tục từ trọng số mã hóa đã commit, không cam kết exactly-once native
compute nếu crash trước commit. Thay nguồn/nhãn/config cần phiên mới; giữ lịch sử
phiên cũ. Native nghiệm thu restart sau hoàn tất được báo riêng với unit test
ngắt giữa checkpoint; không gọi là đã test SIGKILL giữa phép tính native.

## Phạm vi nghiệm thu

Xem [báo cáo](../../reports/he_supervised_training_20261115.md). Khóa/context
và evaluation keys lớn; báo rõ chi phí tạo context, truyền và train. Không suy
SLA từ hai lượt mô phỏng. Phê duyệt hiện chỉ cho shadow, không active sản xuất,
không thay trọng số/queue hoặc kết luận gian lận thật. Không thay gate R0–R6.
