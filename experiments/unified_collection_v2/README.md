# Unified collection v2 — sửa hợp đồng tiền và kiểm chứng trên nguồn

Phiên bản độc lập ngày 04/11/2026. V1 đã được gỡ theo yêu cầu chủ dự án;
v2 chứa đầy đủ core, calibration, scoring và copula cần dùng, không import
bản cũ. Giữ nguyên weights/kết quả v2 và v4/v5/v6; không đổi model dịch vụ
hoặc cổng sản phẩm.

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_unified_collection_v2.py tests/test_unified_collection_core.py tests/test_unified_collection_artifacts.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py tests/test_t6.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m experiments.unified_collection_v2.run --stage saved
```

Stage: `prepare`, `cache`, `train`, `select`, `benchmark`, `source`, `fresh`,
`all`, `saved`. `saved` kiểm snapshot mã và hash artifact của benchmark đã
lưu, không train hoặc chạy test lại. Với output r3 đã hoàn thành, `all` cũng
chỉ kiểm/đọc kết quả cũ nếu source hiện tại đã được tách khỏi v1. Thay source
sau khóa cần output mới để fit; không cập nhật hash cũ để ép chạy tiếp.
Output lịch sử: `outputs/data/unified_collection_v2_20261104_r3/`.

Fixture kế toán khoảng 99 KB tại `fixtures/accounting_regression/` giữ hai
ca hồi quy cần thiết; không còn cần bộ World v1. Snapshot trong artifact v2
chỉ là bằng chứng mã của lần đo cũ, không phải module được import khi chạy.

R2 bổ sung thay thế đúng nghĩa vụ supplier/capex có `known_at`, tránh cộng
trùng với cash scenario lịch sử. Giữ artifact r1, tái sử dụng cache nhãn đã
kiểm hash và refit weights. R1 dừng trước source selection và test mới;
không đổi ngân sách, seed hoặc tiêu chí lựa chọn/đánh giá.

R3 sửa thứ tự thời gian của source selection so với ngày đóng nhãn của v6:
source selection 01/07 và 07/10/2024, follow-up kết thúc 06/01/2025; test
chỉ từ 06/01 và 07/07/2025. Origin tháng 7 còn kiểm tuần cuối quý có ngày
rút vốn ở giữa tuần. R2 chỉ là chẩn đoán hồi cứu, không có test mới. R3 giữ
nguyên weights collection theo hash, fit lại lựa chọn calibration trên
nguồn đúng mốc; giữ các ngưỡng và ba ngân sách, không nới cổng để qua.

Các sửa chính:

- RNG có tên độc lập theo thành phần, công ty/origin và MC replicate; doanh
  thu mới dùng cùng mẫu giữa hai comparator, độc lập với collection.
- AR-applied giảm dư nợ; ngân hàng nhận net sau phí. Tỷ lệ phí dự báo chỉ
  từ bank history tại cutoff. Oracle kiểm phí thật chỉ là kiểm kế toán.
- Sổ ngân hàng chạy 91 ngày; owner draw đúng ngày cuối quý. Thu tuần được
  phân bổ bằng profile ngày của các tuần thu đã quan sát, không dồn hết
  vào cuối tuần. Tham số draw suy từ lịch sử, có khoảng cap và cờ chưa định
  danh khi không có lần rút trong lịch sử.
- Target giữ `operating_bank_account`: AR, vay, chuyển nội bộ, nộp tiền,
  thu khác/unclassified, chi và draw. Phi AR và supplier/capex lấy block
  13 tuần từ tối đa 730 ngày lịch sử, giữ các nhóm riêng. Đây là giả định
  scenario từ lịch sử, chưa chứng minh biết trước các khoản thu bất thường.
- T4 train và suy luận cùng tuần Thứ Ba–Thứ Hai; hóa đơn ngày cutoff ở
  lịch sử, không đếm lại vào tương lai. Kernel tiền hóa đơn mới dùng các
  khoản thu từng phần đã quan sát của cohort đủ follow-up.
- T5 suy lịch chi định kỳ từ quá khứ; chỉ dùng obligation tương lai có
  `known_at <= cutoff`. Không coi `known_in_advance` thiếu ngày biết là
  quyền đọc các số tiền tương lai trong synthetic.
- Giữ model chuyển tiếp chung của v1, 77 feature và lớp 0/full chính xác;
  không thêm head. Learning curve 20k/50k/200k anchor, cùng 160 vòng, mẫu
  quota công ty lồng nhau. Calibration theo tuần 1, 2–4, 5–13 có guard tiền
  và Brier; chọn budget/rho bằng CRPS AR tích lũy trên công ty nguồn riêng.
- Ma trận feature được dựng theo batch trước predict; đo RSS và ba MC
  replicate thay vì suy peak RAM từ kích thước một batch.

`protocol.json` là đăng ký trước fit. Fit dùng bốn World train, cùng partition
v6. Nhãn fit 13 tuần kết thúc trước origin calibration-fit 02/10/2023. Source
selection dùng 01/07 và 07/10/2024, trên nhóm calibration-select tách khỏi
fit/calibration-fit; cả v6 và v2 đã có weights trước các origin này. T4 chỉ
fit đến 06/01/2025, trước các origin chấm bank. Các World đã xem không dùng
chọn tham số. Hậu kiểm kế toán trên hai ca v1 chỉ kiểm thứ tự sự kiện/bridge.

Nếu source AR CRPS xấu hơn v6 quá 2% hoặc ngân sách 1.000×2.000 không qua
latency/RSS, dừng trước test mới. Nếu qua, mở bốn World mới, tám công ty/World,
hai origin, ba lần 1.000 đường; pool 3.000 đường để chấm, giữ bảng từng seed.
Ngưỡng T6 giữ CRPS giảm 5%, Brier, coverage/width và interval score. Bốn
World vẫn ít cho bất định giữa các đường kinh tế và chưa thay dữ liệu thật.

Chấm AR-applied riêng bằng CRPS của 13 phân phối thu tích lũy, chuẩn hóa
theo tổng dư origin; chấm số dư ngân hàng riêng theo chi forecast biết tại
cutoff. Coverage AR có atom nên không tự áp ngưỡng trên 90% như biến liên tục.
Replay lớp thật trên nguồn đo lỗi rời rạc hóa tích lũy; residual cùng không
thu chỉ tính trên các hàng hóa đơn còn mở, có kiểm tương quan tuần liền kề.
Không tự thêm latent AR(1) hoặc dùng shock truth làm feature.

Giới hạn giữ lại để báo: không học credit-only nếu nguồn không có nhãn;
đại diện trong lớp vẫn hữu hạn; bất định T4 và scenario phi AR phụ thuộc
history; draw cap chưa định danh hoàn toàn; benchmark RSS là mẫu mỗi 50 ms.
Không dùng việc sửa adapter để tuyên bố kiến trúc đã thắng v6 trước khi đo.
