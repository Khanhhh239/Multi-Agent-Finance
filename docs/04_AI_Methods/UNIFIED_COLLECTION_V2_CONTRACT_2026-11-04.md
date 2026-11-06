# Unified collection v2: contract sửa sau hậu kiểm

**Ngày 04/11/2026. Trạng thái: contract v2/r3; tham số fit đã khóa từ r2,
lựa chọn nguồn theo mốc sửa ở r3, khóa trước test mới.**
V1 đã được gỡ theo yêu cầu chủ dự án ngày 04/11; các sửa lỗi và giới hạn
được ghi trong báo cáo v2 bên dưới. Core cần dùng đã được chuyển vào v2.
Mã và cách chạy: [unified_collection_v2](../../experiments/unified_collection_v2/README.md).
Thông số chính xác: [protocol.json](../../experiments/unified_collection_v2/protocol.json).
Đặc tả không phải bằng chứng đạt cổng; kết quả phải đối chiếu artifact sau chạy.

Kết quả sau chạy: [Evaluation v2/r3](../03_Evaluation/UNIFIED_COLLECTION_V2_2026-11-04.md).

**Phạm vi tiền.** Giữ số dư tài khoản ngân hàng vận hành. Thu phi AR có đủ
các nhóm financing, internal transfer, cash deposit, other external và
unclassified. Chúng không được nhập thành doanh thu mới. Input forecast
đều được lọc tại cutoff; truth được đọc bởi hàm riêng khi chấm.

```text
AR mở = AR-applied + credit + write-off + AR còn lại
AR vào ngân hàng = AR-applied − phí
bank hôm nay = bank hôm trước + AR net + thu mới net + thu phi AR − chi − draw
```

Kế toán cập nhật từng ngày. Draw diễn ra đúng cuối ngày cuối quý; các khoản
thu/chi sau ngày đó vẫn ảnh hưởng số dư cuối tuần. Profile phân bổ thu trong
tuần và tỷ lệ phí chỉ dùng lịch sử. Việc chia ngày là một giả định được khóa,
không dùng ngày giao dịch thật trong tương lai để dự báo. T4 dùng tuần
`(origin, origin+7]` từ Thứ Ba đến Thứ Hai, phù hợp origin Thứ Hai.

**Các phần dùng chung.** Hai comparator nhận cùng T4/T5, profile ngày,
scenario phi AR, sampler draw và phí. Dùng stream RNG có tên tách biệt;
chỉ cố ý chia sẻ randomness của các thành phần giữ nguyên giữa comparator.
Phi AR/supplier/capex dùng block lịch sử 13 tuần; khoản chi định kỳ dựa
lịch sử, obligation tương lai cần ngày biết. Không đọc undated future actuals.

**Mô hình.** Giữ một LightGBM chung cash/credit/trạng thái và feature origin
của v1; chỉ cập nhật lịch và state invoice trong rollout. Thử ba ngân sách
20.000, 50.000, 200.000 anchor, cùng 160 vòng và quota công ty lồng nhau.
Calibration riêng các dải tuần 1, 2–4, 5–13, chọn bằng nguồn với guard
cash bias và Brier 0/full. Không oversampling/class weight hoặc cash head/T2.

Fit vẫn là công ty fit trong bốn World train v6. Nhãn fit kết thúc trước
02/10/2023; ngày này dùng cho các công ty calibration-fit riêng. Chọn mô hình
bằng AR CRPS ở 01/07 và 07/10/2024 trên công ty calibration-select; không dùng
World holdout cũ. Hai origin này không trước mốc đóng nhãn train v6 01/07/2024.
Nhãn lựa chọn nguồn kết thúc 06/01/2025. Rho trong `[0,0]`, `[0,15;0,15]`,
`[0,30;0,15]` cũng chọn trên nguồn. T4 học đến 06/01/2025; chỉ chấm số dư
bank từ ngày này trở đi. Các tham số đã chọn phải có thể biết tại origin.

**Điểm và dừng.** Chấm phân phối AR-applied tích lũy riêng với scale tổng
dư tại origin; số dư bank riêng với scale chi forecast tại origin. Calibration
được chấm cả trên state thật và các đường tự sinh. Replay lớp thật đo riêng
discretization; thống kê cùng không thu chỉ gồm invoice-week đang mở.

Trước test mới, source AR không được xấu hơn v6 quá 2%; benchmark ba seed,
1.000 đường × 2.000 hóa đơn cần mỗi lần dưới 120 giây, RSS tăng được lấy mẫu
không quá 2.000 MiB. Dừng nếu không qua; không đổi tiêu chí theo holdout.
Nếu qua, test bốn World mới, seed 106110501–106110504, tám công ty/World,
origin 06/01 và 07/07/2025. Origin thứ hai có cuối quý nằm trong tuần, nhằm
kiểm thứ tự các dòng tiền sau draw. Các template/scenario khóa trong protocol.

Mỗi comparator chạy ba MC seed, mỗi seed 1.000 đường; pool để chấm và giữ
điểm từng seed. Tiêu chí T6: CRPS giảm 5% mỗi World; Brier không xấu hơn 2%
với fallback gần 0; coverage 70–90%; interval score không xấu hơn 2%; AR CRPS
không xấu hơn ở từng World. ACI tắt. Không thay cổng sản phẩm/model dịch vụ.

V1/v4/v5/v6 và dữ liệu cũ được kiểm hash trước/sau. Mọi artifact mới ghi
exclusive trong output v2. Test chỉ mở sau lựa chọn trên nguồn; test đã xem
không còn được coi là dữ liệu xác nhận mới cho lần thử tiếp.

Revision r3 giữ weights collection và cache fit/calibration-fit đã train ở
r2 theo hash, dựng lại cache calibration-select theo mốc mới. R1/r2 được
giữ như hồ sơ triển khai/hồi cứu và chưa tạo World test. Không dùng điểm
hồi cứu r2 để tuyên bố source gate của r3 đạt hoặc trượt. Chương trình kiểm
timeline trước khi khóa và từ chối origin chọn nguồn trước ngày train v6.
