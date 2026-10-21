# Dữ liệu mô phỏng nguồn ERP–HR–chi tiền, 17/10/2026

Đã tạo **62.182 giao dịch**, ba seed khác nhau, mỗi bộ gồm tám công ty thuộc năm ngành, giai đoạn 2024–2025. Bộ chính ở [data/synthetic_sources_20261017_v2](../data/synthetic_sources_20261017_v2), kết quả ở [summary.json](synthetic_sources_20261017_v2/summary.json). Hai bộ đã chấm bằng cấu hình luật hiện tại; bộ thứ ba giữ lại chưa chấm. Đây là nguồn mô phỏng để diễn tập tích hợp và kiểm soát lịch sử; cổng nguồn thật vẫn `awaiting_real_data`, 0 đơn vị được reviewer độc lập kết luận, tiêu chí nghiệm thu thật vẫn `not_frozen`.

## Quy mô và vai trò

| Bộ | Seed | Giao dịch | Vai trò | Hồ sơ sau chấm | Đơn vị trong phiếu |
| --- | ---: | ---: | --- | ---: | ---: |
| 001 | 2026101701 | 20.559 | Reporting | 256 | 1.104 |
| 003 | 2026101702 | 20.523 | Reporting | 307 | 1.104 |
| 005 | 2026101703 | 21.100 | Holdout chưa chấm | — | 1.104 |

Mỗi bộ có 12.000 nghiệp vụ nền ngẫu nhiên, cộng bảng lương và tiền thuê theo tháng, các tình huống kiểm soát có chủ đích. Quy mô giao dịch, số nhân viên/NCC, mức lương, tiền thuê và biên độ số tiền khác nhau giữa các công ty. Có khối lượng theo ngành, tăng hoạt động cuối năm, giảm tháng 2, giao dịch cuối tuần và ghi sổ theo lô cùng timestamp. Tên được ghép ngẫu nhiên; mã ngân hàng `SIM_BKxx` là giả lập; số tài khoản giữ số 0 đầu. Các phân bố là giả định thiết kế, chưa được hiệu chỉnh từ SME thực tế.

Sổ cái có chứng từ nhiều dòng và cân Nợ/Có từng chứng từ; nguồn có lịch sử ghi nhận, phê duyệt, thu hồi, nghỉ việc/tái tuyển, bảng lương cuối kỳ, tiền thu từng phần và kế hoạch thu nợ. Template TT133/TT200 và VAT minh họa được kế thừa cho giai đoạn 2024–2025; bộ dữ liệu không xác nhận tuân thủ pháp luật hoặc thực hành kế toán hiện hành.

## Nguồn và tình huống

Mỗi bộ có đầy đủ file/schema/checksum cho F1/C4/E2/F2/F3/F4. [Inventory 001](synthetic_sources_20261017_v2/sme_fraud_001/source_inventory.json), [thống kê 001](synthetic_sources_20261017_v2/sme_fraud_001/diagnostics.json), [mapping 001](synthetic_sources_20261017_v2/sme_fraud_001/mapping_contract.json).

| Rule | Tình huống được sinh có chủ đích |
| --- | --- |
| F1 | Điều chỉnh thủ công trọng yếu sát khóa sổ; tự động; dưới trọng yếu; nhập từ trước; audit đến muộn; bản chính sách thay thế bị thu hồi nhưng chính sách gốc còn hiệu lực |
| C4 | Thao tác trong kỳ nghỉ; được phép làm việc; đúng biên kết thúc nghỉ; nguồn đến muộn; thu hồi trước/sau thao tác |
| E2 | Lương cho thời gian sau nghỉ việc; quyết toán cuối; truy lĩnh; tái tuyển; thiếu hồ sơ lương; thông tin nghỉ việc đến muộn |
| F2 | Bỏ quy trình trái quyền; override hợp lệ; quy trình đã hoàn tất; thiếu/chưa biết chính sách; sự kiện đã hủy |
| F3 | Thiếu số trong dải đã khóa; số hủy có chứng cứ; thiếu coverage hủy; bản hủy đến sau cutoff; trùng số của hai chứng từ; dải liên tục |
| F4 | Nợ quá hạn chưa thu; thu đủ/một phần; kế hoạch được duyệt; thiếu coverage; phân bổ vượt tiền thu; chưa đến hạn; tiền thu đến sau cutoff |

Có **38 biến thể × 2 lần × 8 công ty = 608 đơn vị kiểm soát mỗi bộ**. Các tham số số tiền, nhân sự, chứng từ và thời điểm được lấy ngẫu nhiên trong điều kiện của biến thể. Nhãn này mô tả điều kiện nguồn, không gán kết luận gian lận cho nghiệp vụ nền.

Mỗi bộ còn có 16 thử thách bị từ chối: boolean `2`, enum sai, số âm/NaN, ngày không tồn tại, thiếu múi giờ, định dạng VND sai và các nghĩa chưa hỗ trợ. 16 khoản thu sau cutoff được cách ly khỏi transactions; nguồn phân bổ tương lai vẫn giữ để kiểm tra as-of. Bản ghi hoàn/hủy/đảo và nhiều tài khoản đồng thời chỉ là thử thách ở tầng nguồn thô, chưa có đối chứng nghiệp vụ đủ để tuyên bố hỗ trợ.

Mapping ERP minh họa đối chiếu từng giao dịch qua timestamp UTC, tiền VND có dấu phân nhóm, maker/checker, mã công ty và ngân hàng–tài khoản. HR/công nợ được sinh trực tiếp theo schema hiện tại; chưa có adapter ERP/HR của nhà cung cấp thực hoặc người chủ nguồn ký coverage.

## Khóa dữ liệu và đánh giá

[Kế hoạch](synthetic_sources_20261017_v2/evaluation_plan.json) khóa seed, vai trò, kịch bản, cấu hình luật, cách lấy mẫu và tiêu chí trước dự đoán. Oracle và registry được lưu trước khi dựng feature/chấm. Phiếu gồm toàn bộ đơn vị kiểm soát định trước và tối đa 20 đơn vị nền lấy theo hash cho mỗi công ty/rule/loại đơn vị; không chọn theo hit/điểm. Chọn đơn vị kiểm soát dùng ID của cohort đã khai báo, không dùng giá trị kỳ vọng để thay đổi phân bố chọn.

`review_packet.csv` không chứa prediction, điểm, nhãn hay tên kịch bản; các ô reviewer/kết luận còn trống. Oracle nằm riêng trong `sealed_truth`; đây là tách thư mục/commitment cho quy trình nội bộ, không phải kho mã hóa hoặc kiểm soát truy cập. Người chấm mù chỉ nhận gói nguồn/phiếu, không nhận thư mục oracle hoặc prediction. Sau khi khóa hash score/hit/queue/prediction, mới đối chiếu kỳ vọng tự khai báo. Ba seed dùng chung họ bộ sinh và đặc tả; không phải ba mẫu thực địa độc lập.

Hai bộ reporting có **1.216/1.216 kết quả khớp oracle**: 384 điều kiện hiện diện, 640 điều kiện vắng mặt và 192 trường hợp chưa đủ dữ kiện. Kết quả unknown cũng phải khớp; không loại chúng khỏi điều kiện đóng. [So sánh từng đơn vị 001](synthetic_sources_20261017_v2/sme_fraud_001/control_comparison.json), [metrics 003](synthetic_sources_20261017_v2/sme_fraud_003/control_metrics.json). Không tính precision gian lận hoặc precision reviewer từ các số này. Nghiệp vụ nền chưa có nhãn được giữ là chưa biết, không bị ép thành âm tính.

Bộ 005 có nguồn, cache feature và phiếu nguồn, **không có score/hit/queue/prediction**, không nạp SQLite và không chạy model. Việc duy trì holdout cần hạn chế người xem oracle cho đến khi khóa đợt chấm tiếp theo. Đợt này không fit/chấm IF, đổi điểm/ngưỡng/hard trigger hoặc đổi chính sách queue mặc định.

## Lịch sử, công suất và bảo vệ baseline

Hai SQLite mới nạp và replay thành công, chưa có admission/feedback của người dùng. [Diễn tập R6](synthetic_sources_20261017_v2/sme_fraud_001/migration_rehearsal.json) chạy trên bản sao riêng: đảo thứ tự nguồn, đổi ID tương đương một-một, giữ phản hồi/phân công/lượt đã nhận và nguyên chuỗi hash audit; đổi bằng chứng sang ID mới không nhận lại phản hồi hoặc lượt cũ. `SIM_REHEARSAL_BOT` là máy tạo sự kiện thử, không được tính là reviewer độc lập. Snapshot/audit vận hành thật chưa được migration.

Đã tính 20 tổ hợp tải từ hai queue đã khóa: nghiên cứu 1/45, 3/135, 5/225 và UI 5/120, 10/240 hồ sơ/phút mỗi công ty/ngày; hai lịch mọi ngày và T2–T6 không suy diễn ngày lễ. [Tải 001](synthetic_sources_20261017_v2/sme_fraud_001/workload.json). Có tồn cuối kỳ và thời gian giải phóng tồn. Cách xếp hạng lúc mở và công sức ở snapshot cuối vẫn là giả định của simulator hiện tại; chưa đo công sức người thật hoặc SLA khi hồ sơ đang chờ tăng ưu tiên.

252 file baseline được đối chiếu hash giữ nguyên, bao gồm nguồn/model/snapshot được bảo vệ từ các lượt trước. Bản sinh đầu có mirror tài khoản thừa của nhân viên thêm mới; đã sửa bộ sinh, thêm guard và xuất v2 cùng seed/kịch bản/cấu hình. [Lý do giữ lại bản đầu](synthetic_sources_20261017/SUPERSEDED.md). Phiên bản chính là v2.

**Kiểm tra mã cuối: 425/425 test và 7/7 probe readiness đạt**, gồm 13 test mới cho nguồn mô phỏng. [Log hồi quy](../.runtime/synthetic_sources_20261017/tests_v2_final.log), [log probe](../.runtime/synthetic_sources_20261017/readiness_probes.log). [Đối chiếu artifact độc lập](../.runtime/synthetic_sources_20261017/verification_v2.json) kiểm tra checksum, 190 feature hữu hạn/giao dịch, liên kết tài khoản đúng master, cân sổ, phiếu không lộ nhãn, oracle, holdout và SQLite; không chạy lại detector/model. Hai SQLite reporting còn 0 lượt nhận và chưa có feedback.

## Dùng lại

Chạy từ thư mục gốc, chọn đường dẫn đầu ra mới khi sinh lại:

```powershell
python -B -m sme_fraud.run_synthetic_readiness --data-root data/synthetic_sources_new --output reports/synthetic_sources_new
```

Mở hai snapshot reporting trong UI với database riêng:

```powershell
python -B -m sme_fraud.review_server --data-root data/synthetic_sources_20261017_v2 --reports-root reports/synthetic_sources_20261017_v2 --database .runtime/review/synthetic_sources_v2.sqlite3
```

Không đưa holdout 005 vào UI cho đến khi chủ động mở đợt chấm mới. Với nghiệm thu thật, vẫn cần chủ nguồn ký mapping/coverage, khóa tiêu chí trước review, người rà soát và phân xử độc lập, dữ liệu mới và diễn tập migration trên đúng phiên bản lịch sử. Có thể tiếp tục sửa truy vết export/replay sự kiện và review bản thử A4 bằng dữ liệu hiện có; không thêm ngoại lệ thiếu hồ sơ nghĩa vụ chi để giảm cảnh báo.
