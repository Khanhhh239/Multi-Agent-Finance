# Các phép đo bổ sung: chu kỳ SBA, chuyển chế độ và chính sách thu nợ

Chạy riêng từng lệnh; không dùng kết quả test để chọn lại ngưỡng hay giả định.

## T9 trong sốc cung ứng 2022

`scripts/run_t9_supply_shock.py` học khách giao dịch từ nguồn năm 2020,
isotonic trên nguồn năm 2021, giữ tau=.9. Cách lần test đầu tháng 6/2022
trên 120 ngày. Chạy riêng R1/R2/Hybrid qua cùng chuỗi giao dịch, giữ trạng
thái phân bổ giữa các pha; sau đó chấm trước sốc (01/06–02/10/2022), trong
sốc (03/10–27/11) và sau sốc (28/11–31/03/2023). Thời gian này khớp cấu
hình `hc_supply_shock_v2`; không dùng mô hình 2023/calibration 2024 để
chấm ngược năm 2022. Nhóm thép bị tác động và nhóm ngành khác được chấm
riêng, bootstrap 300 lần theo công ty; không coi các pha là công ty độc lập.
Đây là một thế giới tổng hợp/seed, không xác nhận tác động thực tế. Lượt này
không thay kết quả G15 gốc hoặc dùng để chọn lại ngưỡng phân bổ.

## Domain randomization cùng số công ty và hoá đơn

`scripts/build_dr_comparison.py` sinh một thế giới ×400 DN và 20 thế giới
×20 DN. `scripts/run_dr_comparison.py` khớp số hoá đơn từng cặp công ty
trước khi tính đặc trưng; hai nhánh cùng tối đa 40k snapshot, 300 vòng.
Nguồn chốt 2024-07-01 cho ba miền tổng hợp; nguồn chốt riêng 2019-10-01
cho CustomerInvoices, không huấn luyện nguồn tương lai để chấm dữ liệu thật.
Mỗi nhánh có đủ 400 DN. Dữ liệu thật chỉ có bốn cụm công ty nên CI cần được
hiểu trong phạm vi mẫu nhỏ này, không đại diện SME Việt Nam.

Lượt đầu bị ngắt trong lúc chuẩn bị nguồn 2019. Cache đã hoàn tất chỉ được
chuyển khi hash toàn bộ phụ thuộc và manifest khớp bản gốc lưu riêng;
protocol ghi hash các cache được dùng lại. Lượt tiếp theo lưu snapshot theo
từng mảnh, kiểm hash khi phục hồi. Kiểm thử ngắt giữa chừng đối chiếu với
lượt liền mạch xác nhận cùng kết quả. Ba miền tổng hợp không đạt mức giảm
pinball 5%; dữ liệu thật vượt mức đó trong CI cặp theo công ty. Kết quả
chi tiết lấy từ `outputs/t1/DR/decisions.csv`; không tự áp dụng DR và không
suy ra độ bất định giữa nhiều seed sinh nguồn từ một thiết kế seed.

## Chu kỳ tại ngày phê duyệt SBA

`scripts/run_sba_macro.py` đối chiếu cùng LightGBM/isotonic có và không có
tỷ lệ charge-off của cohort phê duyệt trong [T−2 năm, T−1 năm), quy mô cohort
và cờ thiếu lịch sử. Thông tin charge-off chỉ vào đặc trưng sau ngày xảy ra
cộng 90 ngày. Đây là giả định độ trễ công bố, chưa có dữ liệu vintage SBA.
Mẫu số dùng mọi ngày phê duyệt hợp lệ; không lọc bằng trạng thái khoản vay
cuối kỳ. Không dùng tỷ lệ charge-off cùng năm hoặc nhãn ba năm của cohort
cũ chưa chín. Lãi suất ban đầu vốn đã có trong hai nhánh.

Train FY≤2013, calibration FY2014, test FY2018–2022; nhãn ba năm đã chín
trước test. Chạy drop/keep/censor EXEMPT, báo cáo theo kỳ hạn và FY. CI Brier
lấy mẫu theo proxy tên/địa chỉ người vay, không phải định danh doanh nghiệp
được xác nhận. Số liệu lấy từ `outputs/t2_t3/sba_macro_*.csv`.

## T7 điều khiển T6

`scripts/run_regime_cash.py` huấn luyện nguồn trước cửa sổ hiệu chỉnh nguồn;
quan sát hiệu chỉnh cuối cách test ít nhất 120 ngày. CUSUM chọn ngưỡng từ
lưới định trước trên nguồn với mọi alarm hiệu chỉnh được đếm là báo giả.
Nếu không ngưỡng nào đạt ≤0,5/DN-năm thì tắt controller ở cửa sổ đó.
Không nới ngưỡng bằng kết quả khủng hoảng đích.

Khi crisis, dùng mô hình nguồn với EWM 30 ngày/phần dư 7 ngày và ACI gamma
gấp ba. Sai số chân trời k chỉ cập nhật sau k tuần đã quan sát. Hai nhánh
dùng cùng luồng ngẫu nhiên và cohort. Lịch thu lý tưởng, doanh thu phân vị
lịch sử, ngân sách nguồn 20k/300 vòng: đây là phép đo riêng, không thay E2E
nhãn T9. Phần dư riêng khách được trừ sốc từ những khách còn lại; bảng này
là chẩn đoán, không thay kiểm G14. Kết quả: `outputs/t7/regime_cash/`.

## P0/P1/P2

`scripts/run_collection_policy.py` chạy 14 DN×52 tuần với q=.3/.5/.7 định
trước. P0 không gọi; P1 chọn khoản mở lớn nhất; P2 xếp top-50 theo tiền×xác
suất trễ rồi chọn delta xác suất thiếu hụt bằng Monte Carlo CRN. Chỉ dùng
quá khứ tại thời điểm chọn. Một hoá đơn/DN/tuần, phản hồi dùng hash chung
theo hoá đơn/tuần để các nhánh cùng nguồn ngẫu nhiên.

Phản hồi chỉ dời khoản thu đã tồn tại sau tuần đầu về cuối tuần đầu, bảo
toàn tổng tiền; không tạo tiền từ nợ không có thu hồi. Chi phí và lịch rút
vốn giữ nguyên. DSO dùng AR trung bình tuần trên doanh số tín dụng/ngày
cùng mẫu số. Đây là mô phỏng phản hồi giả định từ lịch thu lý tưởng; chưa
định giá chi phí gọi, chưa có sai số T9, nhiều seed phản hồi hay hiệu ứng
nhân quả. Không diễn giải là ROI đo thật. CI theo DN nằm ở
`outputs/t6/collection_policy/metrics.csv`; chạy
`scripts/compare_collection_policy.py` để so P2/P1, không chọn q từ test.

Lượt v1 bị vô hiệu hoá vì P1 còn chọn số dư giảm trừ của hoá đơn đã tất
toán (56 lượt). V2 loại khoản đã tất toán theo thông tin biết tại cutoff,
đo lại cả bảy nhánh và DSO. Kết quả cũ giữ ở
`outputs/t6/collection_policy_v1_credit_residual_legacy/`.

## Copula hai nhân tố

`scripts/run_copula_hierarchy.py` chọn rho danh mục trong {0,.15,.3} và rho
khách trong {0,.1,.25} bằng IS80 nguồn. Mô hình nguồn chốt nhãn cuối 2022;
hiệu chỉnh bốn DN×13 tuần đầu 2023, kết quả chân trời cuối trong tháng 6/2023,
cách test 2024-07 hơn 120 ngày. Chọn riêng một nhân tố và lưới chung; mốc
rho=.15 vẫn chạy. df=4, 512 đường, lịch thu lý tưởng, doanh thu phân vị lịch
sử, khoảng thô không ACI. Không suy ra chất lượng E2E T9 từ phép đo này.

Tuần không có AR vẫn có số dư, doanh thu mới, chi và rút vốn nên phải chấm.
`scripts/complete_copula_cohort.py` sửa lượt v1 bằng cùng mô hình đã đóng
băng và seed tuần: giữ dự báo có AR, đối chiếu replay, bổ sung đúng 14 tuần
rỗng. Hiệu chỉnh nguồn v1 đã đủ mọi tuần; không chọn lại tham số từ đích.
Mã chỉ chấp nhận đúng phiên bản/hash đã biết, kiểm input/model và cohort
14×52×3×13. Protocol giữ hash/provenance cả lượt gốc và phần bổ sung.
Lệnh đầy đủ vẫn chạy được; lệnh bổ sung dùng riêng cho v1 đã lưu.

## IW dự đoán ngoài công ty

`scripts/run_iw_oof.py` đối chiếu pooled, IW dự đoán trên mẫu đã học và IW
với bốn fold giữ lại nguyên DN trong từng miền. Chỉ dùng snapshot trước
2024-07-01; nhãn miền không phải kết quả thanh toán. Cùng 40k nguồn/tối đa
40k đích, M6, 300 vòng và trọng số đích của DA-paired. Bộ phân loại miền
200 vòng và clip xác suất/trọng số giữ như thí nghiệm gốc.

Đây là ablation thăm dò sau khi chẩn đoán trọng số cũ gần như đồng nhất;
không phải lần xác nhận cuối trên miền đích chưa từng được xem. OOF ngăn
dự đoán lại công ty trong fold đã học, nhưng không bảo đảm hai phân phối
chồng lấn hoặc tỷ lệ mật độ đã được hiệu chỉnh. Báo cáo AUC ngoài công ty,
ESS và CI pinball trong `outputs/t1/IW_oof/`; không đổi kết luận DA4 gốc
hoặc đưa vào chính sách onboarding bằng kết quả test này.
