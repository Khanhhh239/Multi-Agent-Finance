# Chốt T1 cho T6 và SHAP · 12/11/2026

**Chọn ensemble Landmark 18 feature, Neural 75% + lịch sử khách 25%, làm cấu hình
T1 tổng quát cho nhánh nghiên cứu T6/SHAP.** Giữ T1 Workspace làm ứng viên học
riêng tại doanh nghiệp. Chỉ ưu tiên bản local khi validation theo thời gian tại
doanh nghiệp chứng minh lỗi thu 13 tuần tốt hơn bản tổng quát và đạt ngân sách
SHAP. Không cố định Histogram cho mọi doanh nghiệp, không đặt sẵn tỷ trọng
World/local, không mặc định dữ liệu local luôn tốt hơn dữ liệu World.

Đây là lựa chọn kỹ thuật từ bằng chứng hiện có, **chưa chứng minh có một model
tốt nhất cho mọi doanh nghiệp**. Artifact vẫn thuộc nghiên cứu synthetic;
quyết định này không tự thay model đang hoạt động trong dịch vụ hoặc trạng thái
[cổng pilot](GATES_CURRENT.md). Cơ chế tự động chọn giữa World/local bằng lỗi
thu 13 tuần chưa được triển khai trong lần này.

## Cấu hình được chọn

| Thành phần | Quyết định |
|---|---|
| Artifact | `outputs/t1/landmark18_survival_cash_20261112/artifact` |
| Schema | `t1-landmark-18-v2`: 18 feature trạng thái, sáu nhóm nghiệp vụ |
| Thành viên | Neural 0,75; mốc lịch sử khách 0,25 |
| Calibration | Identity sau pooling |
| Đầu ra T1 | Phân phối tất toán bằng tiền trong 13 tuần và khối lượng chưa tất toán |
| Đầu vào T6 | Phân phối trên, dư nợ tại ngày chốt, cùng xử lý thu từng phần của T6 |
| Đích SHAP | Xác suất tất toán trong bốn tuần của toàn ensemble |
| Chân trời đã học | 13 tuần; sau đó giữ phần chưa giải quyết, không tự ngoại suy hazard |

Trọng số 75/25 là **Neural/lịch sử khách bên trong model World**. Đây không phải
trọng số giữa model World và model học riêng. Feature, thành viên và trọng số
đã được chọn trên validation của lượt 18 feature trước đó; lần đối chiếu này
không tìm ensemble hoặc tuning mới trên kết quả test.

## Đối chiếu Workspace trên nhiều World

Đã chạy đủ **108 cặp doanh nghiệp/ngày chốt: ba World test, 18 doanh nghiệp,
sáu mốc, 5.486 snapshot hóa đơn chung**. Snapshot của một hóa đơn ở nhiều mốc
không được coi là những hóa đơn độc lập. Mỗi T1 Workspace được học lại bằng
lịch sử của đúng doanh nghiệp, chỉ dùng thông tin biết tại ngày chốt, giữ nguyên
danh mục 16 ứng viên, pool, validation, audit và quy tắc dự phòng.

Các World test không được gộp vào fit model toàn cục. Việc fit local trên quá
khứ của doanh nghiệp test là đánh giá thích nghi theo thời gian, không phải
đánh giá model cố định chưa từng thấy bất kỳ dữ liệu nào của doanh nghiệp đó.
Model toàn cục kế thừa split 14 World: tám train, ba validation, ba test;
76/18/18 doanh nghiệp tương ứng. Workspace giữ feature hiện có: năm feature
tại ngày lập và tuổi nợ khi dự báo; không gọi đó là bản local 18 feature.
Đây là so sánh hai pipeline sử dụng được, khác dữ liệu học và feature, không
phải ablation cô lập tác động của một họ estimator.

Trong 108 lượt, 60 lượt đủ điều kiện học, 48 lượt phải dùng mốc lịch sử vì thiếu
cửa sổ validation/audit; sáu ứng viên bị audit từ chối. Có 52 lượt thực sự dùng
trọng số dương của ứng viên được chọn. Không loại các lượt dự phòng khỏi điểm.

**Bảng quyết định dùng đường phục vụ thực tế của Workspace**, gồm feature theo
ngày biết, giảm trừ đã ghi nhận và phân bổ thu từng phần. Tiền là triệu VND.

| Chỉ số, nhỏ hơn tốt hơn | T1 Workspace | Ensemble 18 feature | Giảm lỗi |
|---|---:|---:|---:|
| Điểm lỗi thu kết hợp, chuẩn hóa theo dư nợ | 0,346842 | 0,336014 | 3,12% |
| MAE thu từng tuần | 332,78 | 324,01 | 2,63% |
| MAE thu lũy kế | 686,83 | 659,38 | 4,00% |
| Brier tất toán bốn tuần | 0,204476 | 0,169575 | 17,07% |
| Brier tất toán 13 tuần | 0,190011 | 0,170605 | 10,21% |

Điểm lỗi thu kết hợp cho trọng số 0,5 vào tổng lỗi tuyệt đối theo tuần và 0,5 vào
trung bình lỗi tuyệt đối lũy kế, sau chuẩn hóa theo dư nợ mỗi origin. Tổng hợp
cho trọng số bằng nhau giữa World, rồi doanh nghiệp, rồi origin; không chọn
theo MAE số dư ngân hàng đang bị thiếu phạm vi thu/chi.

| World | Workspace | Ensemble 18 feature |
|---|---:|---:|
| `compact_06_test` | 0,325154 | 0,312579 |
| `compact_07_test` | 0,383047 | 0,381358 |
| `compact_13_test` | 0,332326 | 0,314106 |

Ensemble tốt hơn ở **3/3 World, 12/18 doanh nghiệp và 4/6 mốc**. Delta điểm lỗi
`Workspace − ensemble` là 0,010828; CI bootstrap 95% theo doanh nghiệp trong
ba World cố định là **[-0,002525; 0,023986]**, còn chứa 0. Đây là lợi thế điểm
trung bình có giới hạn, không phải bằng chứng thắng có ý nghĩa thống kê ở mọi
miền. Mọi origin của cùng doanh nghiệp được giữ cùng nhau khi bootstrap.

Với protocol World đóng băng ban đầu, điểm lỗi lần lượt là Workspace 0,344595;
ensemble 18 feature 0,334995; ensemble 10 feature 0,341374; Survival 0,360616.
Ba kết quả global đã tái tính khớp lần chấm cũ. Bảng quyết định ở trên dùng
phép chấm serving riêng, không ghi đè các số frozen để giả thành cùng đầu vào.

## Những trường hợp không được bỏ qua

- Trên demo Đại Phát đã xem trước, Workspace thắng rõ về dự thu: MAE tuần
  64,16 triệu, so với 198,75 triệu của bản World 18 feature; MAE lũy kế 299,77
  so với 1.630,46 triệu. Vì vậy không ép thay bản local tốt bằng World trên
  từng doanh nghiệp. Xem [đối chiếu demo](../../outputs/t1/landmark18_survival_cash_20261112/T6_COMPARISON.md).
- Trong `slices.csv` của protocol World, nhóm đã thu một phần có điểm lỗi
  0,434341 với Workspace và 0,447804 với ensemble. Ensemble không thắng mọi
  phân nhóm. Các slice được chuẩn hóa lại trong từng nhóm, không cộng chúng
  để suy ra điểm toàn tập; đây không phải bảng serving chính ở trên.
- Đủ nhiều hóa đơn tổng cộng không bảo đảm đủ validation gần đây. Cũng chưa
  đánh giá một doanh nghiệp hoàn toàn không có lịch sử; nhóm không có tất toán
  khách trong 180 ngày không đồng nghĩa mọi khách trong nhóm đều mới.
- V6/practical 93 feature và AFT không được xếp hạng bằng bảng này: cohort,
  đầu ra, feature hoặc protocol khác, chưa có đối chiếu T6/SHAP cùng điều kiện.
  Không diễn giải việc chọn compact 18 là chứng minh các họ đó kém hơn.

## Hợp đồng phục vụ và SHAP

Audit phát hiện **81/108 context có ít nhất một feature khác** giữa builder
World và `workspace_context`. Khác biệt lịch sử claim/receipt có thể làm xác
suất bốn tuần đổi tối đa 0,315193 trên các dòng đã kiểm. Có 81 dòng đổi trạng
thái được hỗ trợ bởi profile thu từng phần. Phép chấm serving đã dùng đúng
đường chạy thực tế cho cả hai bên; lần này không sửa builder hoặc giả định
feature đã khớp hoàn toàn. Cần giữ sự phân biệt đó khi train/calibrate tiếp.

Ensemble đã chạy qua `forecast()` thật trên ba doanh nghiệp thuộc ba World.
Tiền thu kỳ vọng khớp tổng phân phối và dư nợ; bỏ dữ liệu tương lai không làm
đổi thu, chi, số dư và dải tiền. SHAP cộng lại khớp xác suất. Các kế hoạch dùng
số dư đầu 0 làm fixture kiểm tra kỹ thuật, **không phải backtest sai số số dư
ngân hàng**, và không chứng minh độ phủ khoảng T6 đã đạt 80%.

SHAP dùng sáu nhóm, 64 coalition, toàn cohort khi tối đa 512 hóa đơn; cohort
lớn hơn dùng 128 mẫu phân tầng có trọng số, cùng ba mẫu kiểm độ nhạy. Trên cả
18 context phục vụ đã đo, p95 cao nhất của ensemble là **0,346 giây/hóa đơn**,
sai số cộng lại nhỏ hơn 1e-10. Mỗi context đo tối đa 20 hóa đơn riêng biệt, trải
theo dư nợ. Model/context đã sẵn sàng; thời gian gồm chuẩn bị feature, không
gồm nạp model hoặc dựng ledger. Một số lượt đo có các worker train chạy cùng;
`uncontended_shap_recheck.json` ghi phép kiểm lại context Workspace chậm nhất.
Lượt kiểm lại độc lập tải train tại `compact_06_test/F014` tái tạo đúng các dự
báo Workspace đã lưu, chênh lệch tối đa bằng 0. SHAP Workspace pool có p95
**1,433 giây**, vượt ngân sách một giây; ensemble 18 feature trong cùng context
đạt **0,291 giây**. Không dùng kết quả đo dưới tải đồng thời để tự kết luận
Workspace vi phạm ngân sách. Cũng không suy ra mọi model local đều chậm.

Nền SHAP là công nợ mở của cùng doanh nghiệp tại ngày chốt. Feature chung cho
cả doanh nghiệp nằm trong mức nền, không thể kết luận nó vô ích chỉ vì đóng
góp trong cohort bằng 0. SHAP giải thích xác suất tất toán, không trực tiếp
giải thích mọi khoản tiền thu từng phần hoặc chứng minh nguyên nhân trả chậm.
T6 dùng phần phân rã tiền thu riêng cho các khoản đó.

Đã sửa nhánh hazard Workspace sang float64 trước cập nhật survival: XGBoost
float32 có thể làm tổng xác suất lệch khoảng 2,84e-7. Thay đổi không tuning
model hoặc ngưỡng. Hồ sơ `precision_amendment.json` giữ protocol trước sửa và
danh sách checkpoint đã qua kiểm tra khối lượng xác suất 1e-12 được giữ lại.

## Phạm vi chốt và cách dùng

1. **Mặc định nghiên cứu tổng quát:** artifact ensemble 18 feature nêu trên,
   được nạp bằng `load_workspace_bundle()` rồi truyền nguyên bundle vào T6.
   SHAP giải thích đúng model/thành viên/trọng số đang dự báo.
2. **Tại doanh nghiệp có dữ liệu:** so sánh bản tổng quát với local trên các
   origin quá khứ có nhãn thu đủ 13 tuần; chỉ thay khi lỗi thu tuần/lũy kế và
   độ ổn định tốt hơn, không chỉ vì Brier bốn tuần hoặc số hóa đơn lớn. Đóng
   băng lựa chọn trước kỳ đánh giá tiếp theo. Không có trọng số World/local
   cố định và chưa triển khai tự động routing trong lần này.
3. **Trạng thái dịch vụ:** giữ nguyên cơ chế kích hoạt hiện tại. Quyết định và
   các lượt `forecast()` nghiên cứu không tự kích hoạt model synthetic cho
   mọi tenant hoặc thay gate pilot.

Các test World đã được dùng trước đó và đều thuộc cùng họ simulator. Ba World,
18 doanh nghiệp và các kiểm tra slice mở rộng bằng chứng vượt một demo, nhưng
không đại diện mọi ngành, doanh nghiệp Việt Nam hoặc khủng hoảng chưa mô phỏng.
Phép chấm giữ cohort hóa đơn đủ 91 ngày theo dõi của protocol fixed-claim;
loại các landmark có thay đổi claim trong follow-up hoặc thu trước origin
nhưng ghi nhận muộn theo quy tắc nguồn. Không suy rộng điểm đó cho mọi trạng
thái kế toán hoặc toàn bộ tiền thu ngoài cohort.
Neural được chọn trong lượt 18 feature vẫn có cảnh báo giới hạn 120 vòng;
không gọi cấu hình này là tối ưu toàn cục hoặc đã kiểm định ngoài miền thật.

Kiểm tra cuối: **58 test đạt**, gồm hợp đồng dữ liệu theo ngày biết, regression
float32/float64, model đơn/ensemble, load/save và SHAP. Các cảnh báo MLP trong
test fixture dùng ngân sách nhỏ được giữ lại; không diễn giải test kỹ thuật
thành bằng chứng chất lượng ngoài các cohort đã chấm.

Bằng chứng gốc tại [`outputs/t1/workspace_worlds_20261112/`](../../outputs/t1/workspace_worlds_20261112/):
`selection_decision.json`, `serving_results.json`, `serving_verification.json`,
`serving_by_firm.csv`, `results.json`, `verification.json`, `workspace_fits.csv`,
`slices.csv`, `world18_serving_shap.json`, `runtime_verification.json`,
`precision_amendment.json` và các checkpoint. Lệnh tái lập đọc tại
[README thí nghiệm](../../experiments/t1_compact/README.md#workspace-comparison-across-the-test-worlds-12-november-2026).
