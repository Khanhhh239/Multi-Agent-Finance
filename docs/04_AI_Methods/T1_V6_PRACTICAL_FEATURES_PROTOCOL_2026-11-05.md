# V6: protocol feature ngành và biến động ledger (P0–P4)

**Ngày 05/11/2026. Protocol của lần thử mới; khóa trước khi fit và đọc
outcome fresh. Các test v6 cũ đã được xem trước đó.**

Mã riêng ở [`experiments/t1_v6_practical/`](../../experiments/t1_v6_practical/).
Artifact và protocol đã khóa ở
[`outputs/data/t1_v6_practical_20261105_r2/`](../../outputs/data/t1_v6_practical_20261105_r2/).
Đây là thử nghiệm synthetic về giá trị tăng thêm của feature. Không kích
hoạt model dịch vụ, không thay cash head hoặc trạng thái cổng sản phẩm.

## P0. Đầu vào có thể triển khai

Giữ đúng 14 one-hot ngành mua/bán, gồm unknown cho mỗi bên. Không đưa năm
`macro_credit_*` vào bất kỳ nhánh model nào. Ngành cần bản ghi có nguồn,
`known_at` và tenant. Không dùng ngày thành lập hoặc ngày hóa đơn đầu tiên
để gán lùi ngày biết ngành; cập nhật biết sau không đổi snapshot cũ.

[`PracticalFeatureBuilder`](../../experiments/t1_v6_practical/ledger.py)
yêu cầu danh sách tenant được phép từ caller. Từ chối bảng hoặc khóa dự
báo ngoài danh sách, cột ngoài schema, sự kiện trùng ID hoặc sai thứ tự
thời gian. Bảng ngành dùng khóa `(firm_id, customer_id)` ở bên mua. Caller
phải lấy danh sách quyền từ lớp xác thực; module không tự cấp quyền.

Không có dữ liệu SME thật được nối cho lần thử này. Để chạy ablation trên
cohort synthetic, tạo **lớp ERP quan sát mới**, có thiết kế được khóa:

- Ngành người mua: 75% khách có phân loại, chọn cố định bằng hash ID và
  World, độc lập với kết quả trả tiền/default. Bản customer master xuất cuối
  quý sau khi khách đã xuất hiện, tiếp nhận sau đó 14 ngày.
- Ngành người bán: hồ sơ onboarding được tiếp nhận ở bản xuất quý đầu.
- Hóa đơn và bút toán thu tiền/credit: tiếp nhận sau ngày nghiệp vụ 1 ngày;
  quyết định Write-off tiếp nhận sau 7 ngày. Có bản xác nhận coverage
  ledger từng ngày, tiếp nhận trễ 1 ngày.
- Dùng `ledger_invoice_id` và `ledger_post_date`, giữ lỗi phân bổ của
  ledger. Không dùng `invoice_id` liên kết tiền thật hoặc `pay_date_true`
  để tạo feature hành vi.

Các ngày này là ngày biết **trong mô phỏng mới**, không phải hồ sơ KYC đã
tồn tại trong World cũ. Chưa có bằng chứng các mức thiếu/trễ đại diện SME
Việt Nam. Khi chạy thật, adapter đòi nguồn và thời điểm thực do doanh
nghiệp cung cấp. Bộ 64 feature v6 gốc vẫn giữ giả định quan sát synthetic
cũ; thử nghiệm này không tự chứng minh toàn bộ baseline đã production-ready.

## P1. Mười lăm feature hành vi thanh toán

| Feature | Định nghĩa |
|---|---|
| `b_c_delay_mean_28d` | Trễ dương trung bình của hóa đơn được ledger ghi nhận tất toán trong 28 ngày, kẹp 0–240 ngày |
| `b_c_delay_delta_28d` | Chênh lệch trễ trung bình giữa hai cửa sổ 28 ngày liên tiếp |
| `b_c_settled_n_28d` | Số hóa đơn đã được ghi nhận tất toán trong cửa sổ hiện tại |
| `b_c_collection_ratio_28d` | Thu ròng mới được biết / (dư nợ đầu cửa sổ + hóa đơn mới được biết trong cửa sổ) |
| `b_c_collection_ratio_delta_28d` | Thay đổi tỷ lệ thu giữa hai cửa sổ 28 ngày |
| `b_c_overdue_share` | Dư nợ quá hạn / tổng dư nợ ledger còn mở của khách |
| `b_c_overdue_share_delta_28d` | Thay đổi tỷ trọng quá hạn so với snapshot 28 ngày trước |
| `b_c_partial_share` | Dư nợ còn lại của hóa đơn có thu từng phần / tổng dư nợ mở |
| `b_c_partial_share_delta_28d` | Thay đổi tỷ trọng trên so với snapshot 28 ngày trước |
| `b_i_receipt_frac_28d` | Thu ròng mới được biết của hóa đơn / mệnh giá hóa đơn |
| `b_c_days_since_receipt` | Ngày từ lần ghi nhận khoản thu dương gần nhất |
| `b_c_open_balance_change_28d` | Thay đổi dư nợ mở / dư nợ mở ở snapshot 28 ngày trước |
| `b_ledger_history_days` | Độ dài lịch sử được khai báo đầy đủ đến cutoff |
| `b_ledger_report_age_days` | Tuổi bản coverage ledger mới nhất tính từ ngày dữ liệu được bao phủ |
| `b_ledger_missing` | Thiếu coverage, coverage quá 7 ngày hoặc hóa đơn chưa được quan sát hợp lệ |

Độ trễ là từ hạn thanh toán đến **thời điểm ledger được biết đã tất toán**,
khác với ngày tiền về thật. Bút toán thu/credit có số tiền có dấu để biểu
diễn đảo/hủy bằng sự kiện mới. Hóa đơn bị đảo mở lại không được coi là đã
tất toán trong snapshot hiện tại. Không sửa ngược snapshot trước ngày
biết bút toán đảo hoặc phân bổ muộn.

Các tỷ lệ không có mẫu số hợp lệ là missing. Không có nguồn hoặc thiếu
coverage không được chuyển thành đã quan sát thu tiền bằng 0. Cửa sổ 28
ngày cần đủ lịch sử tương ứng; delta hai cửa sổ cần 56 ngày. Hóa đơn cũ hơn
coverage khai báo chưa có số dư đầu kỳ xác minh được để dựng lại sẽ giữ
missing. Không tự giả định một số dư đầu kỳ bằng 0.
Nếu khách có hóa đơn cũ chưa được coverage bao phủ, cả các tổng hợp hành vi
khách trên hóa đơn mới cũng giữ missing. Thiếu hạn thanh toán của hóa đơn
còn mở làm tỷ trọng quá hạn và delta tương ứng missing, không gán bằng 0.

## P2. Ablation chính và chọn trên nguồn

| Nhánh | Feature snapshot | Có thêm 7 feature tuần |
|---|---:|---:|
| V6 gốc | 64 | Có |
| V6 + ngành | 78 | Có |
| V6 + hành vi | 79 | Có |
| V6 + cả hai | 93 | Có |

Giữ đúng 200.000 dòng fit trong cache v6, thứ tự hàng, seed, 160 vòng và
cấu hình LightGBM. Risk set 53 tuần giữ nguyên: chỉ hàng còn mở đầu tuần,
đủ theo dõi hết tuần và dừng ở mọi cause đóng. Identity calibration cho
cả bốn nhánh. Feature mới đóng băng tại cutoff, không cập nhật khi đi qua
53 tuần tương lai.

Refit baseline phải tái lập hazard v6, sai khác tối đa 1e-8 trên mẫu cố định
128 anchor nguồn qua đủ 53 tuần; ghi thêm kiểm hash model. Không thay file
model gốc nếu refit khác.

Tập chọn gồm anchor đầu tiên mỗi hóa đơn từ 01/07–16/12/2024 trên **8 công
ty đã được giữ ngoài fit ở mỗi World nguồn**. Không đưa các công ty này
vào fit. Đây là chọn trên công ty nguồn và thời gian muộn hơn, không phải
leave-one-World-out hoặc một test độc lập mới. Không dùng `test_000`,
validation/test cũ hoặc hai fresh World cũ để chọn.

Chấm 28/91/365 ngày, Brier joint và riêng Paid/Write-off, ECE Paid và gap
CIF. Tập chọn đủ follow-up 365 ngày nên không cần IPCW cho cohort này.
Quy tắc chọn đã khóa:

1. Trung bình Brier joint 365 và Brier Write-off 365 theo **trọng số World
   bằng nhau** đều phải thấp hơn V6 gốc.
2. Brier Paid 28/91 không xấu hơn 2% tương đối ở bất kỳ World nguồn nào.
3. Trong các nhánh đủ điều kiện, chọn Brier joint 365 nhỏ nhất; nếu bằng
   nhau ưu tiên ít feature hơn, rồi tên nhánh. Không nhánh nào qua thì giữ V6.

Ngưỡng ECE Paid ≤ 0,05 và |gap Write-off 365| ≤ 3 điểm % được báo như tiêu
chí nghiên cứu cuối cùng; không thay ngưỡng theo kết quả fresh. Việc một
ứng viên được chọn trên nguồn không có nghĩa đã qua tiêu chí cuối hoặc
cổng phát hành.

## P3. Support và thí nghiệm bổ sung dữ liệu riêng

Đo missingness và tỷ lệ giá trị hữu hạn ngoài min/max fit của toàn bộ 93
feature snapshot trên tập chọn nguồn. Không coi min/max đơn biến là chứng
minh overlap đa biến hoặc conditional invariance.

Chỉ kích hoạt augmentation nếu trên 10% giá trị hữu hạn của ít nhất một
trong `c_tenure_days`, `c_n_hist`, `f_n_hist` ở tập chọn nguồn nằm ngoài
range fit. Hai World train mới: mỗi World 20 doanh
nghiệp, lịch sử từ 2019, nhiều episode credit/demand/supply/price trước
cutoff fit. Mỗi World thêm tối đa 50.000 snapshot bằng quota theo công ty;
không lấy mẫu theo outcome. Kế hoạch warm-up 2016 ban đầu bị dừng trước
khi ghi Parquet vì thiếu quy tắc thuế trước 2019. Amendment P3 được lưu
trước mọi fit augmented hoặc sinh fresh; lịch fresh và selector không đổi.
Nhánh hỗ trợ từ 2019 không giải quyết được thiếu support tenure.

Fit riêng V6 gốc và feature set đã chọn ở P2 trên **cùng dữ liệu mở rộng**.
Không thay 200.000 dòng của ablation chính. Augmentation bổ sung cả độ dài
lịch sử quan sát từ các công ty/World mới và chế độ shock, nhưng không kéo
dài warm-up trước 2019. Chọn cuối
cùng vẫn bằng cùng quy tắc nguồn, đối chứng với V6 gốc. Đây là phép thử
bổ sung dữ liệu, không gán toàn bộ chênh lệch của nó cho feature mới.

## P4. Fresh holdout và chống chọn theo test

Chỉ sinh bốn World sau khi `final_selection.lock.json` ghi model/hash đã
chọn. Mỗi World 20 công ty, seed 261105201–261105204, có episode bắt đầu,
kéo dài, cường độ và phạm vi mới đã ghi trong protocol trước fit:

| World | Cơ chế thử chính |
|---|---|
| Fresh 000 | Credit từ 05/2024; demand 06/2024 cho dịch vụ/thực phẩm |
| Fresh 001 | Credit từ 08/2024; demand 09/2024 cho textile/wholesale |
| Fresh 002 | Supply/price từ 04–05/2024; credit từ 10/2024 |
| Fresh 003 | Credit kéo dài từ 06/2024; demand từ 07/2024 |

Đánh giá mọi nhánh đã fit và ứng viên đã khóa; không đổi lựa chọn sau khi
đọc fresh. Dùng cùng protocol anchor và nhãn đến 31/12/2025. Báo riêng
trước/sau onset episode, khách thiếu ngành và hóa đơn có thu từng phần.
Ngày onset chỉ là annotation audit, không vào estimator.

Bootstrap ghép cặp 400 lần theo công ty trong từng World, đối chứng V6
gốc. Khoảng này không bao gồm bất định giữa các nền kinh tế. Bốn World
có lịch episode khác nhau vẫn thuộc một họ generator, không thay thế
kiểm chứng SME thật. Kiểm độ nhạy che toàn bộ ngành chỉ chạy sau khi khóa
ứng viên và chỉ báo mô tả, không chọn lại model.

## Chạy và kiểm tra

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m experiments.t1_v6_practical.run --stage all
.\.venv\Scripts\python.exe -X utf8 -B -m pytest tests/test_t1_v6_practical.py tests/test_t1_practical_context.py tests/test_t1_credit_context.py tests/test_t1_v6_diagnosis.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py -q -p no:cacheprovider
```

Các stage `prepare`, `primary`, `select`, `fresh` cho phép tiếp tục từ
artifact đúng hash. Protocol, mã, nguồn thô, môi trường và dataset được
ghi trước fit. Thí nghiệm khác cần thư mục mới; sửa lỗi hoặc giới hạn kỹ
thuật phải giữ lock/mã cũ và ghi amendment trước bước phụ thuộc. Không
đổi tiêu chí theo fresh. Giữ nguyên báo cáo/kết quả lịch sử, công bố cả
trường hợp không đạt.

Các bản sửa triển khai của lần này được lưu thành amendment có mã nguồn
trước/sau: chặn lịch sử không đủ, chặn hạn thanh toán thiếu, đọc CSV giữ
đúng float và kiểm checksum score. Bản sửa không đổi giá trị nguồn đã dùng
vì các hóa đơn synthetic có đầy đủ lịch sử/ngày hạn; phép kiểm tương đương
và hash được lưu. Riêng P3 có amendment thiết kế về giai đoạn hỗ trợ như
đã nêu; không gọi cấu hình 2019 mới là kế hoạch 2016 ban đầu không đổi.
Lịch fresh và selector không thay đổi. Mã dùng fit chính được lưu trong
`source_primary.zip`, các bản trước amendment được lưu riêng, và
`code.lock.json` là con trỏ tới mã hiện hành; các bản lock cũ vẫn được giữ.
