# T1 → T6: đánh giá hướng thống nhất dự báo quá trình thu tiền

**Ngày 03/11/2026. Trạng thái: đề xuất kiến trúc và kiểm tra khả thi trên dữ liệu đã lưu.**
Chưa train mô hình chuyển trạng thái mới, chưa chạy benchmark T6 cho mô hình đó,
chưa chứng minh cải thiện và không thay cổng sản phẩm. V4/v5/v6 được giữ nguyên.

**Nối tiếp ngày 04/11/2026:** đã triển khai và hậu kiểm v1, sau đó sửa và
kiểm chứng [v2/r3](../03_Evaluation/UNIFIED_COLLECTION_V2_2026-11-04.md).
V2 sửa các lỗi adapter nhưng chưa đạt điều kiện thay v6. Phần bên dưới giữ
nguyên trạng thái đề xuất/audit tại ngày 03/11.
Unified v1 đã được gỡ theo yêu cầu chủ dự án ngày 04/11; đọc báo cáo v2/r3
để xem phương pháp, sửa lỗi và benchmark còn được giữ.

**Quyết định đề xuất.** Phát triển một mô hình xác suất cho quá trình thu tiền
của từng hóa đơn theo tuần; T6 lấy mẫu các khoản thu liên tiếp trong 13 tuần.
Kế thừa LightGBM đa lớp và đặc trưng as-of của v6, đổi nhãn sang kết quả tiền
thu cùng trạng thái cuối tuần. T2 không còn một lượt lấy mẫu riêng trong luồng
này; chức năng write-off là một phần của quá trình chung. Cash head kỳ vọng
riêng không được dùng làm phân phối thay thế. Đây là một hướng nghiên cứu duy
nhất, với điều kiện phải qua thử nghiệm trước khi thay mô hình hiện tại.

**1. Bằng chứng mới: sai khác giữa tất toán và tiền thực nhận có thể đo được.**

Đã đối chiếu 65.221 anchor hóa đơn trong sáu World đánh giá đã lưu của v6.
Với từng anchor, lấy tiền thực nhận từ `payments.parquet`. Đối chứng dùng dư
nợ tại cutoff, đưa toàn bộ khoản này vào **ngày tất toán thật** nếu tất toán
trong kỳ. Đây là phép đo cấu trúc khi biết ngày thật, không phải dự báo mới.

WAPE dưới đây cộng các hóa đơn theo công ty tại cuối chân trời, sau đó lấy
tổng sai số tuyệt đối chia tổng tiền thực thu của các anchor:

| Nhóm theo thí nghiệm v6 | 4 tuần | 13 tuần |
|---|---:|---:|
| Validation | 5,40% | 2,64% |
| Test cũ | 4,74% | 2,10% |
| Fresh test của v6 | 3,95% | 2,54% |

Sai số trên tiền thu từng tuần của công ty lớn hơn: khoảng 4,53–5,72% trong
4 tuần, 5,68–6,87% trong 13 tuần. Khoảng 4,90–6,44% tiền nhận trong các kỳ
được nhận trước tất toán hoặc từ hóa đơn chưa tất toán trong kỳ.

Nguồn: [bảng theo World](../../outputs/analysis/t1_t6_direction_review_20261103/oracle_full_settlement_audit_by_world.csv),
[bảng gộp](../../outputs/analysis/t1_t6_direction_review_20261103/oracle_full_settlement_audit_summary.csv).
Tổng tiền thực thu của cả 12 cặp World/chân trời khớp chính xác `cash_comparison.csv`
của v6. Xem [verification.json](../../outputs/analysis/t1_t6_direction_review_20261103/verification.json).

Giới hạn diễn giải: đối chứng còn chịu tác động của credit note tương lai và
các khoản recovery trước write-off, ngoài tác động trả từng phần. Đây không
phải cận dưới toán học của sai số dự báo. Không cộng/trừ các WAPE này với
WAPE v5/v6 để suy ra mức cải thiện có thể đạt. Các anchor không bao gồm toàn
bộ doanh thu mới, dòng chi và số dư của doanh nghiệp; đây chưa phải đo T6.

**2. Dữ liệu đủ để thử nghiệm có kiểm soát, nhưng không hỗ trợ chia lớp tùy ý.**

Ở tuần đầu của 200.000 anchor fit v6: 176.263 không có tiền về, 21.189 nhận
toàn bộ dư nợ và 2.548 nhận một phần. Có 770 kết thúc write-off, không có
credit-note-only. Tuần không có tiền về bao gồm cả các tuần kết thúc write-off.

Để tránh đánh giá thiếu nguồn nhãn, đã đếm thêm các cặp hóa đơn–tuần duy nhất
có thể đi tới trong 13 tuần từ **chính 200.000 anchor fit đó**, dừng sau sự kiện
kết thúc. Không thêm công ty, origin hoặc hóa đơn phát sinh sau origin:

| Nguồn hỗ trợ nhãn | Số lượng |
|---|---:|
| Công ty trong bốn World fit | 128 |
| Cặp hóa đơn–tuần còn mở duy nhất | 950.148 |
| Tuần không có khoản thu | 849.234 |
| Tuần nhận toàn bộ dư nợ đầu tuần | 88.495 |
| Tuần nhận một phần | 12.419 |
| Hóa đơn có ít nhất một tuần nhận một phần | 11.066 |

Nguồn: [nhãn tuần đầu](../../outputs/analysis/t1_t6_direction_review_20261103/train_one_week_label_support.csv),
[hỗ trợ nhãn 13 tuần](../../outputs/analysis/t1_t6_direction_review_20261103/train_reachable_13w_label_support.csv).
Các cặp tuần vẫn phụ thuộc theo hóa đơn, khách, công ty và World; 950.148
không phải số quan sát độc lập. Việc đếm này chưa dựng feature cho quá trình mới.

Kết luận: có cơ sở thử một phân phối tỷ lệ thu với số nhóm vừa phải. Phải giữ
khối xác suất riêng cho 0 và tất toán; không làm tròn tất toán thành gần 100%
rồi để một số dư nhỏ tồn tại mãi. Không coi độ chính xác phân loại cao nhờ
đa số tuần bằng 0 là thành công. Không suy diễn rủi ro credit-note-only đã
được học khi dữ liệu không có nhãn đó.

**3. Hợp đồng của mô hình và T6 phải thống nhất từ đầu.**

Mục tiêu là phân phối chung:

```text
P(tỷ lệ tiền thực thu tuần tới, trạng thái cuối tuần
  | thông tin biết tại origin, trạng thái đường mô phỏng, tuần dự báo)
```

Mỗi bước: lấy mẫu một kết quả chung, cộng tiền thực thu, cập nhật số còn có
thể thu và trạng thái đóng, rồi chuyển sang tuần sau. Khoản giảm trừ do credit
note hoặc write-off không được cộng vào tiền mặt. Những trường hợp thay đổi
dư nợ phi tiền tệ phải có quy tắc nhãn và cập nhật kế toán rõ ràng; không chỉ
lấy `dư nợ tuần sau = dư nợ tuần trước − tiền thu` cho mọi trường hợp.
Không tạo thêm lượt lấy mẫu T2, hoặc cộng tiền cash head lên tiền đã mô phỏng.

Để tránh đòi hỏi mô phỏng toàn bộ sổ kế toán tương lai, giữ đặc trưng bối cảnh
khách/công ty tại origin; chỉ cập nhật lịch và trạng thái hóa đơn đã định nghĩa.
Train cũng phải dùng cùng cách giữ bối cảnh tại origin. Lịch sử thanh toán thật
sau origin chỉ được dùng để dựng trạng thái đầu vào khi học chuyển tiếp và
nhãn; khi dự báo, thay hoàn toàn bằng trạng thái do đường mô phỏng tạo ra.
Không đọc snapshot thật tuần tương lai để chạy dự báo 13 tuần từ origin.

Phải học và xuất xác suất gốc của các kết quả. Oversampling hay class weight
không được để lại phân phối sai tỷ lệ mà không có hiệu chỉnh trên nguồn.
Các mức tỷ lệ và cách lấy mẫu trong nhóm cần được khóa trên train/calibration;
đo sai số do rời rạc hóa trước khi diễn giải lợi ích của mô hình.

T6 tiếp tục chịu trách nhiệm tạo phụ thuộc giữa các hóa đơn. Tuy nhiên, copula
hiện tại lấy một tuần tất toán cho mỗi hóa đơn; nó không tự trở thành bộ lấy
mẫu chuyển trạng thái 13 bước. Bộ mới phải bảo toàn xác suất có điều kiện của
mỗi bước, có quy tắc sắp kết quả theo lượng tiền thu, và kiểm mức độ cùng trễ
giữa khách/tuần. Dùng chung một latent factor suốt kỳ mà không xét điều kiện
trên lịch sử mô phỏng có thể làm sai các xác suất đã hiệu chỉnh. Đây là phần
phải kiểm chứng của cùng thiết kế, không phải tính năng đã có sẵn trong T6.

Write-off là trạng thái kết thúc theo contract synthetic đang có. Từ đó không
suy ra đã học được xác suất “không bao giờ trả” hoặc tiền thu hồi sau write-off.

**4. Ba rủi ro có thể làm phương pháp không thành công.**

- Sai số tự tích lũy: tuần trước lấy mẫu sai sẽ thay dư nợ và lịch sử dùng cho
  tuần sau. Điểm dự báo một tuần tốt chưa đủ. Phải chấm các đường 13 tuần chạy
  bằng trạng thái tự sinh. Rủi ro tương tự của việc học với lịch sử thật nhưng
  suy luận bằng lịch sử tự sinh được nêu trong [Bengio et al., 2015](https://proceedings.neurips.cc/paper_files/paper/2015/hash/e995f98d56967d946471af29d7bf99f1-Abstract.html).
  Việc áp dụng cảnh báo đó cho thiết kế LightGBM này là suy luận kỹ thuật,
  không phải kết quả thực nghiệm của mô hình mới.
- Sai cấu trúc phụ thuộc: tiền kỳ vọng đúng vẫn có thể cho xác suất thiếu tiền
  sai nếu nhiều hóa đơn thực tế cùng trễ. Chấm cả các tuần shock và nhóm khách
  chiếm tỷ trọng tiền lớn; không chỉ chấm trung bình toàn tập.
- Chi phí chạy: 1.000 đường × 2.000 hóa đơn × 13 tuần là 26 triệu hàng dự báo
  nếu chạy ngây thơ. Đo tham chiếu model v6 hiện có: trung vị 1,79 giây cho
  100.000 hàng trên bốn thread. Ngoại suy tuyến tính khoảng 465 giây cho 26 triệu
  hàng, chưa có cập nhật feature. Đây không phải latency model mới: bỏ qua
  đóng sớm, gộp trạng thái/cache và sự khác biệt số lớp. Ma trận float32 của
  riêng một bước 2 triệu hàng × 71 feature khoảng 542 MiB. Cần batch, dừng
  đường đã đóng và dùng lại kết quả cho trạng thái trùng; đo lại trên prototype.

Nguồn thời gian: [prediction_throughput_reference.json](../../outputs/analysis/t1_t6_direction_review_20261103/prediction_throughput_reference.json).

**5. Đánh giá khả năng thành công và điều kiện đầu tư tiếp.**

Khả thi xây dựng prototype trên synthetic: có cơ sở tốt, do đã có nhãn giao
dịch, feature as-of và nền LightGBM. Khả năng cải thiện T6: hợp lý nhưng chưa
chứng minh; đánh giá kỹ thuật hiện tại là trung bình, không có cơ sở gán một
tỷ lệ thành công như 80–90%. Mức sai khác cấu trúc chỉ vài phần trăm, nên sai
số mô hình mới có thể triệt tiêu toàn bộ lợi ích. Khả năng dùng trên ledger
SME thật chưa đánh giá được bằng cohort synthetic này.

Chuỗi công việc duy nhất: khóa contract và protocol → dựng nhãn → fit một
prototype → chạy các đường 13 tuần → chấm dòng thu và T6 → quyết định thay thế.
Trong so sánh đầu tiên, giữ cùng T4/T5, tập hóa đơn, ngày cắt và ngân sách mô
phỏng để đo đúng thay đổi của quá trình thu tiền; đánh giá lại ACI riêng sau đó.
V6 với cách dồn tiền tất toán là đối chứng cố định, không phải một hướng phát
triển song song.

Ngưỡng dưới đây là **đề xuất cần khóa trước thử nghiệm**, không phải cổng dự án:

1. CRPS chuẩn hóa, lấy trung bình của 13 phân phối số dư cuối tuần, giảm ít nhất
   5% so với đối chứng; báo riêng từng World, công ty và khoảng tin cậy. CRPS
   ở đây chấm từng biên tuần; Brier thiếu tiền bên dưới chấm sự kiện của cả đường.
   Thang chuẩn hóa
   dùng thông tin biết tại cutoff, không dùng số dư tương lai. Brier thiếu tiền
   4 và 13 tuần không xấu quá 2% tương đối; có ngưỡng tuyệt đối khóa trước nếu
   Brier đối chứng gần 0. Khoảng P10–P90 cần độ phủ và độ rộng hợp lý; không
   chỉ nới khoảng để tăng coverage. Cơ sở dùng điểm phân phối và interval score:
   [Gneiting & Raftery, 2007](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf).
2. Bảo toàn tiền, không thu quá số có thể thu, không ghi credit/write-off thành
   tiền mặt, không dùng dữ liệu tương lai trong rollout; đo trên từng tuần.
3. Báo latency thực tế tại số đường/số hóa đơn đã khóa. Ngân sách dự kiến
   1.000 đường và tối đa 2.000 hóa đơn phải được kiểm trước khi train mở rộng;
   không dùng throughput của v6 làm cam kết hiệu năng của mô hình mới.

Các World validation/test/fresh của v6 đã được xem; trong nghiên cứu mới chúng
chỉ là dữ liệu chẩn đoán. Test cuối phải là các World/seed mới khóa trước khi
fit, dùng một lần; việc thay seed vẫn chưa chứng minh khái quát sang máy phát
khác hoặc dữ liệu thật. Bootstrap theo công ty trong World chỉ đo bất định
giữa công ty của World đó, không thay được bất định giữa các đường kinh tế.

Nếu prototype không qua điều kiện, kết luận là chưa có bằng chứng thay v6;
không tiếp tục thêm head hoặc ghép nhiều mô hình chỉ để tăng điểm đã xem.

**Tái lập phần audit.**

```powershell
.\.venv\Scripts\python.exe -B -m analysis.review_t1_t6_direction
# Tùy chọn đo lại throughput tham chiếu, kết quả phụ thuộc máy:
.\.venv\Scripts\python.exe -B -m analysis.review_t1_t6_direction --benchmark
```

Mã: [analysis/review_t1_t6_direction.py](../../analysis/review_t1_t6_direction.py).
Audit đọc artifact cũ và ghi riêng vào `outputs/analysis/t1_t6_direction_review_20261103/`.
