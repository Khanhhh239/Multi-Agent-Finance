# So sánh model riêng cho doanh nghiệp — 04/11/2026

**Bổ sung 06/11:** CLI và web cùng khóa chính xác tập bằng chứng/phiếu đã chọn; tệp thêm ngoài manifest, kể cả trong thư mục con, bị từ chối trước khi lưu. Đã thử lại trường hợp 12 → 13 trên bản sao gói hiện hành; dữ liệu gốc giữ nguyên. [Chi tiết và kiểm thử](ml_review_packet_lock_20261106.md).

**Bổ sung 05/11:** có thể rà trực tiếp 12 phiếu trên `/ml-reviews`, ghi căn cứ/hành động và đo thời gian, rồi xuất CSV cho luồng tổng hợp bên dưới. [Hướng dẫn web](ml_review_web_20261105.md). Phần mô tả CLI ở báo cáo này giữ để đối chiếu lượt đã khóa.

**Đã chạy so sánh kỹ thuật cho C001 và C002 trên dữ liệu demo mô phỏng. Chưa kết luận model nào hữu ích nhất:** chưa có phiếu rà của người dùng hoặc thời gian kiểm tra thực tế. CatBoost bị loại vì thiếu nhãn train đã xác minh phù hợp.

## Dữ liệu và ngân sách cố định

Nguồn là tập giao dịch nhập CSV/Excel trong `.runtime/data_import_demo_20261104/review.sqlite3`, snapshot 003; mỗi công ty 30 giao dịch và 194 feature. Kết nối SQLite chỉ đọc, không thay dữ liệu, nhãn, phiên bản đang dùng, hàng đợi hoặc kết luận nghiệp vụ. C001 vẫn dùng Isolation Forest, C002 vẫn dùng ECOD như trước lượt so sánh.

| Phần dữ liệu | Khoảng thời gian, giờ Việt Nam | Số dòng mỗi công ty |
| --- | --- | ---: |
| Train | Từ 01/01/2024 00:00 đến trước 19/01/2024 12:00 | 18 |
| Calibration | Từ 19/01/2024 12:00 đến trước 25/01/2024 12:00 | 6 |
| Evaluation | Từ 25/01/2024 12:00 đến trước 31/01/2024 00:00 | 6 |

Ngày **05/11/2026**, người dùng xác nhận: **“Chạy thử C001/C002: tối đa 5 giao dịch cho mỗi model, mỗi doanh nghiệp”**. Cấu hình này trùng với lượt thử kỹ thuật đã chạy ngày 04/11, nên tiếp tục dùng gói `run_02`. Đã đối chiếu đủ **24/24 tệp theo manifest**, mỗi danh sách có đúng 5 giao dịch; revision dữ liệu và model đang dùng của cả hai công ty vẫn khớp. Không cần huấn luyện lại để ghi nhận lựa chọn này. Biên nhận riêng: `.runtime/company_ml_comparison_20261104/selection_confirmed_20261105.json`; gói kết quả đã khóa giữ nguyên.

Đây là ngân sách số giao dịch cho kiểm thử demo. Mỗi danh sách lấy top 5 trong đúng 6 dòng evaluation, cùng revision và tập ID; khi bằng điểm dùng thứ tự SHA256 của seed/công ty/mã giao dịch đã cố định trước khi chạy. Ngân sách hồ sơ/ngày hoặc phút rà cho dữ liệu thực vẫn cần được chọn khi triển khai thử thực tế.

Model và bộ chuẩn hóa ML chỉ fit trên 18 dòng train. Ngưỡng tham chiếu lấy từ calibration với tỷ lệ 10%, quantile `higher`, điều kiện vượt ngưỡng là `score > threshold`. Không dùng nhãn evaluation để huấn luyện hoặc chọn ngưỡng. Điểm số của các thuật toán không nằm trên cùng thang đo nên không so trị số trực tiếp giữa model.

## Kết quả kỹ thuật

| Doanh nghiệp | Model | Vượt ngưỡng calibration / 6 | Chọn để rà / ngân sách | Train + score, giây |
| --- | --- | ---: | ---: | ---: |
| C001 | Isolation Forest | 0 | 5 / 5 | 0,120 |
| C001 | Autoencoder | 6 | 5 / 5 | 0,065 |
| C001 | ECOD | 0 | 5 / 5 | 0,006 |
| C001 | LOF novelty | 6 | 5 / 5 | 1,446 |
| C002 | Isolation Forest | 0 | 5 / 5 | 0,154 |
| C002 | Autoencoder | 6 | 5 / 5 | 0,057 |
| C002 | ECOD | 0 | 5 / 5 | 0,006 |
| C002 | LOF novelty | 6 | 5 / 5 | 0,016 |

Tất cả bốn adapter chạy bằng code thật, có artifact riêng và đã nạp lại để đối chiếu điểm. Autoencoder hội tụ trong lượt này. Các số giây là một lượt train/chấm, bao gồm ảnh hưởng khởi động thư viện; **không phải phút kiểm tra của kế toán** hoặc benchmark tốc độ ổn định.

Top 5 là danh sách lấy mẫu để so sánh trên cùng sức chứa, có thể bao gồm giao dịch dưới ngưỡng. Không đổi các giao dịch đó thành cảnh báo vượt ngưỡng hoặc chuyển vào hàng đợi nghiệp vụ. Chênh lệch 0/6 và 6/6 không chứng minh model nào tốt hơn; dữ liệu demo rất nhỏ, có tính tuần tự và thiếu nhiều nguồn bằng chứng. Chưa có nhãn evaluation đã xác minh để báo precision/recall gian lận.

CatBoost không được fit hoặc chấm:

- C001: **0/18** dòng train có nhãn đã xác minh, đã biết trước cuối kỳ train.
- C002: **1/18** dòng train có nhãn mô phỏng đã xác minh phù hợp thời điểm; không đủ toàn bộ train và hai lớp.

Runner chỉ cho CatBoost chạy khi mọi dòng train có nhãn qua cổng CSV đã xác minh, đủ hai lớp 0/1, người rà/căn cứ/thời điểm hợp lệ và thời điểm biết nhãn trước ranh giới train. Không đọc `labels.csv`, `splits.csv`, oracle hoặc biến điểm luật/kết quả hữu ích thành nhãn train.

## Ghi nhận cảnh báo hữu ích và phút kiểm tra

Đã khóa **40 vị trí rà** (2 doanh nghiệp × 4 model × 5 giao dịch), gộp thành **12 giao dịch duy nhất** cần rà. Giao dịch trùng giữa các model dùng chung phiếu để giảm công sức và giữ kết luận nhất quán.

Phiếu tại `.runtime/company_ml_comparison_20261104/run_02/human_reviews.csv` đang để trống kết quả: **0/12 đã rà**. Các trường lợi ích ở mức ngân sách và tổng phút đầy đủ hiện là `null`, không giả định bằng 0. Không có model thắng được tự chọn/kích hoạt.

Người rà dùng dữ kiện trong `public/evidence/`; tên model, điểm, thứ hạng và tập chọn nằm ở `private/` để người rà có thể làm việc mù. Dữ kiện hiện chỉ là giao dịch nhập, chưa có chứng từ gốc đi kèm; cần bổ sung tham chiếu hoặc ghi chưa đủ căn cứ.

Mỗi phiếu có mã ràng buộc doanh nghiệp/giao dịch/hash bằng chứng và các ô:

| Trường | Cách ghi |
| --- | --- |
| `useful` | `yes`: có hành động nghiệp vụ cụ thể, có căn cứ; `no`: đã đủ căn cứ và không cần hành động; `unknown`: chưa đủ tài liệu |
| `business_action` | Hành động cụ thể, bắt buộc khi `useful=yes`. Yêu cầu chứng từ chung chung chưa chứng minh lợi ích |
| `rationale`, `evidence_refs` | Lý do và tham chiếu chứng từ/dữ kiện đã đối chiếu |
| `active_review_minutes` | Phút kiểm tra thực tế, loại thời gian nghỉ; số dương, tối đa 1.440 |
| `timing_method` | `stopwatch` hoặc `contemporaneous_log`; không dùng phút phỏng đoán hoặc thời gian model chạy |
| `reviewer_id`, `reviewed_at`, `human_verified` | Người rà, thời điểm ISO có múi giờ sau khi khóa phép so sánh và xác nhận `1` |

Chưa rà thì để trống toàn bộ các ô kết quả. Công cụ tổng hợp từ chối phiếu sai công ty/hash, trùng mã, thiếu căn cứ, số phút không hợp lệ hoặc thời điểm không phù hợp. Gói nguồn/model/điểm/bằng chứng được đối chiếu checksum trước tổng hợp.

Kết quả được báo riêng từng công ty/model: đã rà/chưa rà, hữu ích, chưa đủ căn cứ, tỷ lệ hữu ích trong phần kết luận được, phút đã đo và tổng phút cho đầy đủ ngân sách khi đã đủ phiếu. `unknown` không bị biến thành `no`. Thời gian gán cho mỗi danh sách model được tính theo các giao dịch của danh sách; tổng công sức thực tế chỉ tính một lần cho mỗi giao dịch duy nhất. Phiếu chỉ xác nhận hữu ích, không trở thành nhãn gian lận hoặc phê duyệt chọn model.

## Chạy lại và tổng hợp phiếu

Mã tái sử dụng: `sme_fraud/company_ml_comparison.py`. Dùng môi trường review/Company ML đã cài, chạy tại thư mục gốc:

```powershell
python -B -m sme_fraud.company_ml_comparison run `
  --database .runtime/data_import_demo_20261104/review.sqlite3 `
  --output .runtime/company_ml_comparison_20261104/new_run `
  --companies C001 C002 --scenario 003 `
  --train-start 2024-01-01T00:00:00+07:00 `
  --train-end 2024-01-19T12:00:00+07:00 `
  --calibration-end 2024-01-25T12:00:00+07:00 `
  --evaluation-end 2024-01-31T00:00:00+07:00 `
  --review-count 5 --calibration-rate 0.1 --source-kind synthetic_demo
```

Giữ nguyên gói đã khóa. Sau khi người rà điền phiếu, tổng hợp vào thư mục mới:

```powershell
python -B -m sme_fraud.company_ml_comparison collect `
  --comparison .runtime/company_ml_comparison_20261104/run_02 `
  --reviews .runtime/company_ml_comparison_20261104/run_02/human_reviews.csv `
  --output .runtime/company_ml_comparison_20261104/human_results_01
```

Tổng hợp phiếu trống đã được chạy riêng tại `awaiting_reviews_02/review_results.json` và trả đúng 0 phiếu, chưa có lợi ích/phút đầy đủ. Chưa đưa kết quả này vào màn hình web; thao tác nhập liệu/chọn ML hiện hữu vẫn giữ nguyên.

Bằng chứng cục bộ của lượt đối chiếu: `run_02/manifest.json`, `run_02/private/comparison.json`, `run_02/private/predictions.csv`, `run_02/private/selection.csv`, `run_02/private/models/`, `run_02/public/evidence/`. Manifest khóa checksum, cửa sổ, revision từng công ty, hợp đồng feature, mã nguồn, môi trường và artifact; phép so sánh hủy nếu revision/model nguồn đổi khi đang chạy.

Kiểm thử mới gồm 11 trường hợp: cùng tập train/calibration/evaluation và ngân sách, không ghi source DB, nhãn thiếu/trễ/một lớp, thực thi CatBoost khi đủ điều kiện trên fixture mô phỏng, tái hiện thứ tự khi bằng điểm, xung đột snapshot, phiếu trống/thiếu/sai/trùng/bằng chứng đổi, tách `unknown` và tính công sức giao dịch duy nhất. Kết quả mô phỏng trong test không được nhập vào phiếu của lượt đánh giá này.

Hồi quy cuối: **136 test Python đạt**, bao gồm 11 test mới và các bộ Company ML/API, nhập dữ liệu, review, phân quyền, workflow, hợp đồng feature, shadow và backup/restore. Nhật ký: `.runtime/company_ml_comparison_tests.log`, `.runtime/company_ml_comparison_regression.log`. Không có thay đổi giao diện trong lượt này; bằng chứng Playwright của màn hình nhập/chọn ML nằm ở biên bản trước.
