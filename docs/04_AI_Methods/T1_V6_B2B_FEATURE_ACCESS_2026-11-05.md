# Feature T1 v6: doanh nghiệp B2B thực sự lấy được dữ liệu nào?

> **Cách đọc sau gộp 06/11/2026:** đây là audit khả năng lấy đầu vào ở bước trước P0–P4 ngày 05/11. Các câu “hướng trước mắt/chưa nối” giữ nghĩa tại thời điểm audit; kết quả ngành + ledger sau đó đọc ở protocol/báo cáo practical. Tách việc adapter đã dùng trong nghiên cứu khỏi khả năng dữ liệu thật đã được nối vào dịch vụ.

**Ngày 05/11/2026. Rà soát khả năng tiếp cận đầu vào và sửa adapter ngành;
không train hoặc thay model v6.**

**Kết quả tiếp nối cùng ngày:** [P0–P4 đã được chạy](../03_Evaluation/T1_V6_PRACTICAL_FEATURES_2026-11-05.md),
gồm ngành và 15 feature hành vi ledger, ablation và bốn fresh World.
Các thiếu hụt baseline/service trong audit này không tự biến mất sau lần
thử synthetic đó.

**Có đầu vào chưa thực tế.** Năm feature khảo sát tín dụng vừa xây không có
nguồn thực tế được kết nối; ngày biết ngành bằng ngày hóa đơn đầu tiên cũng
chỉ là giả định. Đã loại khảo sát khỏi whitelist của adapter dùng dữ liệu
thực, đồng thời yêu cầu ngành có nguồn và ngày được biết thật. Báo cáo khảo
sát cũ được giữ để tái lập nghiên cứu, không phải cam kết đầu vào triển khai.

Đã rà **64 feature snapshot v6, 7 feature tuần và 19 feature nghiên cứu**.
Danh mục từng feature, nguồn cần có và quyết định nằm trong
[feature_access.csv](../../outputs/analysis/t1_feature_access_20261105/feature_access.csv).
Một feature tính được từ sổ doanh nghiệp không có nghĩa dự án đã nhập đủ
dữ liệu để tính nó chính xác.

## 1. Những gì doanh nghiệp bán có thể biết

| Nhóm | Khả năng lấy dữ liệu thực | Điều kiện / sửa cách hiểu |
|---|---|---|
| Hóa đơn, hạn thanh toán, số tiền và tuổi nợ | Từ hóa đơn và hợp đồng của chính doanh nghiệp | Hạn thanh toán có thể thiếu trên XML. Không suy ra hạn thỏa thuận chỉ từ ngày lập hóa đơn |
| `c_delay_*`, `c_n_hist`, `c_pay_30d`, nhịp trả tiền | Từ các khoản khách đã trả **cho chính người bán này** | Cần phân bổ tiền vào hóa đơn được đối soát, có ngày biết; không phải lịch sử khách trả mọi nhà cung cấp |
| `c_open_*`, tỷ trọng quá hạn và dư nợ | Từ sổ phải thu của người bán | Không phải toàn bộ công nợ, tổng tài sản hoặc thanh khoản của khách |
| `f_n_hist`, `f_delay_mean`, `f_resid_*` | Từ lịch sử thu tiền của chính người bán | Là thống kê nội bộ, không phải số liệu toàn ngành hoặc macro cần mua ngoài |
| Thu từng phần, số lần nhận tiền, số ngày từ lần nhận gần nhất | Có từ thu tiền và đối soát của người bán | Biết giao dịch vào tài khoản chưa đồng nghĩa biết chắc nó trả cho hóa đơn nào |
| Credit note/điều chỉnh | Có nếu doanh nghiệp ghi nhận và nhập đủ chứng từ | Cần phiên bản/ngày biết của điều chỉnh; chưa nhập không đồng nghĩa không có |
| Lời hứa trả tiền | Có nếu bộ phận thu nợ ghi trong CRM/nhật ký | `made_date`, ngày hẹn và nội dung phải có thật; không bắt buộc mọi khách đều có lời hứa |
| `c_promise_rel`, `c_promise_n` | Chỉ tính khi có kết quả lời hứa đã được đối chiếu | Không dùng `kept` do generator hoặc người nhập tự khẳng định làm sự thật đã xác minh |
| Lịch sử Write-off | Có thể có trong sổ/quyết định nội bộ | Là việc **người bán đã xóa khoản phải thu của mình**, không phải biết khách default ở mọi ngân hàng |
| Ngành người bán | Có thể lấy khi onboarding hoặc từ hồ sơ của chính doanh nghiệp | Ghi nguồn, ngày biết và phiên bản phân loại |
| Ngành người mua | Có điều kiện: customer master, khách cung cấp, hồ sơ tra cứu đã xác minh | Không tự biết từ MST, tên khách hoặc ngày hóa đơn đầu tiên; thiếu thì unknown |
| Tháng, tuổi hóa đơn, lịch tuần/Tết | Có thể tính từ ngày và lịch | Ngày Tết và quyết định nghỉ cụ thể khác nhau; lịch nghỉ chưa công bố phải là giả định, không dùng bản tương lai như đã biết |

`c_tenure_days` hiện tính từ hóa đơn đầu tiên **trong lịch sử đã trả đủ mà
builder nhìn thấy**; không phải số năm hoạt động của công ty khách hoặc
ngày thành lập. `c_days_since_last_pay` trong nhóm lịch sử là ngày từ lần
trả đủ cuối; khác với `i_days_since_receipt` của hóa đơn đang mở. Không mở
rộng ý nghĩa các biến này thành thông tin tài chính bên mua mà người bán
không nắm được.

Với dữ liệu thật, định danh khách thường là MST và có thể lặp giữa nhiều
người bán. Builder v6 nghiên cứu đang group nhiều thống kê theo
`customer_id`; ID synthetic được đặt trong namespace của người bán. Khi
dùng ID thật phải tách bảng theo tenant hoặc namespace bằng
`(firm_id, customer_id)`, kể cả bảng lời hứa. Không gom lịch sử của các
người bán khác chỉ vì trùng MST. Adapter ngành mới đã chặn việc lấy chéo
thông tin giữa tenant.

## 2. Những đầu vào chưa thể coi là sẵn có

**Loại năm feature khảo sát khỏi đầu vào thực tế hiện tại:**
`macro_credit_restricted_share`, `macro_credit_delta`,
`macro_credit_age_days`, `macro_credit_missing`,
`macro_credit_delta_missing`.

Chưa có nhà cung cấp, file lịch sử công bố hoặc connector cho chính chuỗi
khảo sát đã mô phỏng. Một SME không mặc nhiên có panel 128 đơn vị để đo
hạn chế tín dụng toàn nền kinh tế. Không tạo bản khảo sát từ config shock
rồi coi đó là dữ liệu doanh nghiệp thu được. Các cờ missing của một nguồn
chưa tồn tại cũng không tạo ra nguồn thông tin kinh tế.

PMI không phải dữ liệu hoàn toàn không thể tiếp cận: có thông cáo công
khai, còn chuỗi lịch sử đầy đủ và sub-index có thể cần subscription/license.
Khả năng đọc một thông cáo không đồng nghĩa đã có quyền sử dụng một feed
đầy đủ cho sản phẩm. Dù có feed, vẫn cần chứng minh liên hệ với shock của
generator trước khi dùng để kiểm chất lượng synthetic. [S&P Global, FAQ về dữ liệu PMI](https://www.spglobal.com/market-intelligence/en/solutions/products/resources/pmi-faq).

Không mặc định có API tra cứu ngành hàng loạt, lịch sử phân loại tại từng
cutoff hoặc ngành kinh doanh thực tế chỉ từ đăng ký doanh nghiệp. Adapter
hiện yêu cầu **bản ghi đã được cung cấp/xác minh**, không tự thực hiện tra
cứu. Hồ sơ có nhiều
ngành phải được ánh xạ có căn cứ sang sáu nhóm nghiên cứu; chưa xác định
được thì unknown. Ngành doanh nghiệp cũng không tự đồng nhất với mặt hàng
của từng hóa đơn.

Các biến `common_factor`, `credit_crunch`, exposure,
`customers.default_date`, `shock_truth` và lịch episode trong config vẫn
không phải đầu vào doanh nghiệp quan sát trực tiếp. Không dùng chúng để
lấp dữ liệu bị thiếu. Hệ thống cũng không giả định người bán được biết
số dư tài khoản, hồ sơ tín dụng ngân hàng hoặc sổ mua hàng của khách nếu
khách chưa cung cấp một nguồn riêng.

## 3. Ba khoảng cách giữa dữ liệu synthetic và luồng thật hiện tại

**Thanh toán và thời điểm biết.** V6 nghiên cứu dùng `paid_date_true`,
`pay_date_true` và liên kết đúng giữa tiền với hóa đơn. Sự kiện khách trả
tiền cho người bán có thể quan sát được, nhưng liên kết chính xác này
không tự có ngoài thực tế. Dự án có
[`build_bank_labels`](../../agent1/models/reconciliation_pipeline.py) dựng
`paid_date_est` từ các khoản phân bổ đã đối soát. Cần thêm kỷ luật thời điểm
biết phân bổ: một liên kết được xác nhận tháng 9 không được dùng như đã
biết ở cutoff tháng 7 chỉ vì tiền vào ngân hàng tháng 7. SnapshotBuilder
v6 hiện lọc theo ngày sự kiện, chưa có đầy đủ knowledge timestamp cho mọi
bản ghi. Chưa sửa toàn bộ adapter tiền trong lần này; không gọi v6 hiện
tại là đã sẵn sàng dữ liệu vận hành.

**Write-off.** Sáu feature là `c_closed_n_asof`, `c_writeoff_n_asof`,
`c_writeoff_rate_eb_v6`, `c_writeoff_180d_n`,
`f_writeoff_rate_asof`, `f_writeoff_180d_rate`.
[`train_candidate`](../../agent1/jobs/retrain.py) và
[`nightly.run`](../../agent1_service/jobs/nightly.py) đang đặt
`writeoff_date = NaT`; chưa nối luồng quyết định xóa nợ vào builder. Vì
vậy chúng **có thể lấy từ doanh nghiệp nhưng chưa được nhập đầy đủ trong
luồng thật hiện tại**. Không biến NaT do thiếu nhập liệu thành khẳng định
khách chưa từng bị xóa nợ, cũng không thay bằng cờ bad debt cuối World.

**Lời hứa và ngành.** Luồng retrain thật đã đặt `kept = NaN` khi chưa có
kết quả đối chiếu, thay vì tin kết quả nhập tay. Ngành người mua chưa có
trong parser XML hóa đơn đang dùng. Adapter ngành mới chỉ xử lý các bản
ghi thực được cung cấp; chưa có dữ liệu KYC thật được nối trong lần này.

## 4. Đã sửa prototype thế nào?

Điểm vào mới:
[`practical_context_features`](../../experiments/t1_credit_context/practical.py).
Whitelist chỉ có **14 chỉ báo ngành mua/bán**, gồm unknown cho mỗi bên.
Không nhận tham số khảo sát giả lập; không đọc World, config hoặc invoice
để đoán ngày biết ngành.

Mỗi quan sát ngành cần `firm_id`, `industry`, `known_at`, `source_kind`,
`source_ref`; bên mua cần thêm `customer_id`. `known_at` là thời điểm
người bán thực sự có phiên bản phân loại đó, không phải ngày thành lập
khách hoặc ngày hiệu lực được ghi lùi trên hồ sơ. Truy xuất hôm nay không
tự làm thông tin khả dụng ở các snapshot cũ.

Adapter hỗ trợ bản cập nhật ngành theo thời điểm biết, kiểm nguồn, cô lập
tenant và giữ thứ tự hàng. Không có bản ghi, chưa tới ngày biết hoặc chưa
ánh xạ ngành thì unknown. Metadata nguồn tạo khả năng truy vết; bản thân
module không xác minh hộ tính đúng của hồ sơ hoặc tự cấp quyền truy cập.
Đây là adapter đầu vào đã kiểm thử, chưa được nối vào model/dịch vụ.

**Hướng trước mắt điều chỉnh thành thử ngành từ dữ liệu được cung cấp
thật**, với đối chứng v6 và v6 + ngành. Chỉ thực hiện khi có bản ghi nguồn
hợp lệ. Khảo sát tín dụng giữ ở nhánh mô phỏng để nghiên cứu giả định giá
trị thông tin; hoãn nhánh macro trong kế hoạch ablation thực tế. Không
train thêm trên ngành hoàn hảo của World rồi gọi là đã kiểm tính khả thi
B2B. Chưa có dữ liệu ngành thì hai nhóm đều unknown, không tạo phân loại
giả để lấp trống.

## Tái lập và kiểm tra

```powershell
.\.venv\Scripts\python.exe -B -m analysis.audit_t1_feature_access --output outputs/analysis/t1_feature_access_rerun
.\.venv\Scripts\python.exe -B -m pytest tests/test_t1_practical_context.py tests/test_t1_credit_context.py tests/test_t1_v6_diagnosis.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py -q -p no:cacheprovider
```

**45 kiểm thử qua**, gồm 10 trường hợp mới về nguồn thật/thiếu dữ liệu,
ngày biết thực, ngành thay đổi, cô lập tenant và từ chối nguồn synthetic.
**129 file lịch sử giữ nguyên hash**; model v6 không đổi, không fit hoặc
hiệu chỉnh. [Summary audit](../../outputs/analysis/t1_feature_access_20261105/summary.json)
ghi rõ đây là kiểm yêu cầu nguồn, chưa xác nhận dữ liệu ERP/CRM đã kết nối.
