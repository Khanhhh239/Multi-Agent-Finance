# Agent1 — Không gian dòng tiền cho doanh nghiệp

## T1 global → local và cập nhật định kỳ

Luồng `/v1` hiện dùng [bundle T1 + partial v2](../docs/04_AI_Methods/T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md):
Neural/LightGBM/XGBoost global và các bản học tiếp, không còn ensemble học từ
đầu bằng local/Workspace. Gói global cấu hình bằng `AGENT1_T1_GLOBAL_CATALOG`;
export các artifact hiện có bằng `scripts/package_t1_global_catalog.py`.

`POST /v1/training` hoặc `/v1/t1/updates` tạo chu kỳ, mặc định cách 28 ngày,
cửa sổ 730 ngày. `GET /v1/t1/updates` trả trạng thái, quyết định và challenger.
Chỉ đổi model khi qua audit hợp lệ; incumbent quá mới thì lưu dự báo ghép cặp
và chờ đủ 91 ngày để chấm. Bản local cũ không còn được kích hoạt trong luồng mới.
Partial được học/lưu riêng trong cùng bundle; validation, audit và T6 dùng
cùng adapter. T6 mô phỏng nhiều lần thu trên dư nợ còn lại. Contract global
và phạm vi thanh toán được kiểm trước khi dựng nhãn. SHAP nhận đúng T1 đang
dùng. Đường env research allowlist cũ không
override `/v1/predict` nữa. Các API nghiên cứu legacy được ghi riêng bên dưới.

Job để scheduler gọi theo nguồn dữ liệu đã xác nhận đầy đủ:
`python -m agent1_service.jobs.t1_update --firm SME --state PATH --payments-complete`.
Đặt `PYTHONPATH` tới thư mục `agent1`; không cần web server đang chạy. Chưa tự
cài scheduler hoặc chạy cập nhật trên kho doanh nghiệp nào trong lượt sửa mã.

## Luồng doanh nghiệp (cập nhật T1 ngày 13/11/2026)

[Bắt đầu từ README](../README.md) · [Bàn giao kỹ thuật](../docs/HANDOFF.md) · [Sổ tay PDF](../docs/06_Pilot/pdf/So-tay-Agent1.pdf).

Định hướng: một khung thích nghi cho từng doanh nghiệp, chọn phương pháp bằng lịch sử
của chính doanh nghiệp. Dữ liệu tổng hợp chỉ thử phần mềm. Mã nằm ở
`agent1/adaptive/`, `agent1_service/workspace/` và `agent1_service/ui/workspace/`.
Không thay các thí nghiệm hoặc kết luận NO_GO của bộ nghiên cứu cũ.

Đã tham chiếu nhánh [agent1-Thắng](https://github.com/Khanhhh239/Multi-Agent-Finance/tree/agent1-Th%E1%BA%AFng),
commit `89c144ba3b3d2e7d79d8cb70dc7baf99dc319268`: giữ hợp đồng ngày biết thông tin,
nhãn thanh toán, censoring và không suy missing = unpaid. Đây là lớp triển khai mới
trên workspace Agent1 hiện tại; **không phải tuyên bố đã merge toàn bộ T0 của nhánh đó**.

### Chạy trên Windows

```powershell
# Tại gốc dự án; Python 3.12
py -3.12 -m venv .venv  # chỉ khi chưa có
.\.venv\Scripts\python.exe -m pip install -r requirements-service.txt
.\scripts\start-business.ps1
```

Mở `http://127.0.0.1:8011/workspace` (trang `/` cũng mở giao diện mới).
Khóa truy cập tự tạo ở `.state-business-keys/api-token.txt`; dán vào nút **Kết nối**.
Không gửi khóa trong URL, Git, ảnh hoặc báo cáo. Khóa chỉ giữ trong bộ nhớ trình duyệt;
tải lại trang cần kết nối lại. `-Company TEN_DN -Port 8012` đổi mã/cổng của triển khai.
Mỗi triển khai phục vụ **một doanh nghiệp**; dùng thư mục dữ liệu, khóa và tiến trình
riêng cho doanh nghiệp khác. Không đổi `Company` để giả lập SaaS nhiều tenant trên cùng kho.

Docker: `docker compose -f compose.business.yaml up --build -d`.
Compose này bắt đầu từ kho rỗng, không seed synthetic; volume dữ liệu và khóa riêng,
cổng chỉ bind loopback. Khóa ở `/keys/api-token.txt` trong container. Tắt bằng
`docker compose -f compose.business.yaml down` (không thêm `-v` nếu muốn giữ dữ liệu).
Docker cần daemon hoạt động; kiểm thử Python local không thay cho kiểm thử container.

### Hai giai đoạn sử dụng

1. **Thiết lập:** nạp hóa đơn, thanh toán và lịch chi; kiểm tra ghép cột, xác nhận
   dữ liệu thu đầy đủ đến ngày chốt, rồi chạy kiểm định T1 global → local.
2. **Vận hành:** dự báo 1–52 tuần (mặc định 13), xem khoản cần chú ý và tuần thiếu
   tiền, thử kịch bản, xuất Excel. Nạp dữ liệu mới theo kỳ; job cập nhật mặc định
   cách 28 ngày và chỉ thay model khi qua audit hợp lệ.

Thiếu lịch sử thì giữ global G0 hoặc model hiện tại. Không tự tạo nhãn hoặc dữ liệu
để đạt ngưỡng. Model local cũ không còn được kích hoạt; phiên bản mới và dự báo cũ
vẫn được lưu để truy vết. Dữ liệu thay đổi sau khi học sẽ hiện cảnh báo cần xem xét.

### Hợp đồng đầu vào SME

CSV UTF-8 hoặc XLSX, cho chọn sheet (mặc định sheet đầu), và XML hóa đơn điện tử phiên bản 2.0.0/2.0.1/2.1.0; ≤5 MB/file, ≤50.000 dòng, ZIP XLSX giải nén ≤30 MB.
Worker học local giới hạn 50.000 hóa đơn. Mã là chuỗi ổn định; giữ số 0 đầu bằng kiểu
Text trong Excel. File không được có dòng tổng cộng. Tên cột Việt/Anh tự nhận diện;
người dùng có thể ghép lại trước khi lưu.

| Bảng | Trường bắt buộc | Trường bổ sung |
|---|---|---|
| `invoices` | `invoice_id`, `customer_id`, `issue_date`, `due_date`, `amount` | `known_at`, `currency` (VND) |
| `invoice_events` | `event_id`, `invoice_id`, `event_type=cancel`, `event_date`, `known_at` | — |
| `payments` | `payment_id`, `invoice_id`, `payment_date`, `amount` | `known_at, bank_id` |
| `bank` | `bank_id, account, date, direction, amount` | `known_at, component` |
| `statements` | `statement_id, account, start_date, end_date, opening_balance, closing_balance` | `known_at` |
| `actions` | `event_id, invoice_id, date, kind` | `known_at, promise_date` |
| `outflows` | `expense_id`, `date`, `amount`, `category`, `known_at` | — |
| `expense_payments` | `settlement_id`, `expense_id`, `bank_id`, `payment_date`, `amount`, `known_at` | Thanh toán thực tế của nghĩa vụ T5, kể cả nhận hoàn |

- Chọn rõ ngày `dd/mm/yyyy`, `yyyy-mm-dd` hoặc `dd-mm-yy`; ngày Excel bản địa được đọc trực tiếp.
- Chọn số Việt Nam `1.500.000,00` hoặc số thuần `1500000`; không đoán dấu phân cách.
- Chỉ nhận VND nguyên đồng, lưu và đối chiếu bằng số nguyên, không làm tròn. Ô Excel số thực có phần lẻ hoặc vượt giới hạn nguyên chính xác bị chặn; số lớn nên để kiểu Text. Không tự quy đổi FX hoặc xử lý hoàn/thu thừa.
- Hóa đơn có thông tin kế toán cần đủ `seller_mst, buyer_mst, symbol, invoice_no, amount_net, vat`; dùng chung `validate_invoices`, đối chiếu XML/ERP và bộ xử lý vòng đời của ingest cũ. Bảng đơn giản vẫn dùng được nhưng hiện cảnh báo chưa kiểm tra đầy đủ T0, không được làm gốc chứng từ điều chỉnh/thay thế.
- Thay thế: `adjustment_type=replacement`; điều chỉnh: `adjustment_type=adjustment` với chênh lệch có dấu ở `amount_net, vat, amount`. Tham chiếu bằng `adjusts_invoice_id` hoặc đủ `adjusts_symbol, adjusts_invoice_no, adjusts_issue_date`. Hủy bằng `invoice_events`. Bộ kiểm tra chặn chuỗi thiếu gốc/vòng, chứng từ đã hết hiệu lực và tổng thu vượt công nợ hiệu lực. Khoản thu đi theo chuỗi thay thế, không nhân đôi.
- XML dùng ngày/số chuẩn của XML; chọn ngày biết dữ liệu riêng trước khi xem trước. Không suy hạn thanh toán khi XML thiếu trường đó. Nguồn, dòng và SHA-256 được giữ cho chứng từ đầy đủ.
- `known_at` (nhận cả tên cột `available_on`) là ngày thông tin sẵn có, không phải ngày tải lên. Khi thiếu trên hóa đơn đơn giản/
  thanh toán, giả định bằng ngày nghiệp vụ và hiện cảnh báo; chứng từ kế toán đầy đủ thiếu ngày này dùng ngày nạp, tránh suy đã biết từ ngày lập. Kiểm định dựa vào ngày biết dữ liệu đó.
  Lịch chi bắt buộc có `known_at` vì ngày chi có thể ở tương lai.
- Một khoản chuyển khoản phân bổ nhiều hóa đơn phải tách thành dòng với mã thanh toán riêng.
  Một hóa đơn trả nhiều lần giữ đủ các phần. Tổng thu không vượt giá trị hóa đơn.
- Nhập hóa đơn trước thanh toán. Dòng lỗi chặn **cả lần lưu**; không âm thầm bỏ lỗi.
- Cùng ID là phiên bản sửa: ngày ghi nhận phải mới hơn; hóa đơn đổi nội dung cần tăng `record_version`. Phiên bản cũ của các bảng được giữ để dựng lại theo ngày biết dữ liệu, không dùng bản sửa đến muộn cho gốc lịch sử. Chứng từ kế toán và sự kiện hủy không bị xóa vật lý qua workspace. Xem trước nêu số dòng bị cập nhật;
  nếu dữ liệu đổi giữa xem trước và lưu, trả 409 để tránh ghi đè.
- Mỗi lần lưu tạo snapshot bất biến và hash dữ liệu. Xóa bản ghi nhập nhầm tạo snapshot mới,
  không xóa lịch sử kiểm toán. Cần xóa thanh toán liên quan trước khi xóa hóa đơn.
- Nếu đã cấu hình danh mục ngân hàng được duyệt (cùng `AGENT1_BANK_ACCOUNTS_FILE` của luồng cũ), workspace kiểm tra doanh nghiệp, bằng chứng/hash và tài khoản VND ở cả xem trước/lưu. Phạm vi dự báo giữ toàn bộ tài khoản được duyệt, kể cả tài khoản chưa tải sao kê. Khi chưa có danh mục, bản xem trước cảnh báo chưa xác nhận phạm vi đầy đủ.
- Mẫu có tiền tố `DEMO_`; worker chỉ học trên bộ mẫu trong kho `DEMO_` khởi động với `-DemoTraining`.
  Xem sáu bảng thực hành tại [Đại Phát](../pilot/demo_dai_phat).
- Phải xác nhận đã có đầy đủ các khoản thu đến ngày chốt trước **cả học và dự báo**.
  Đây là xác nhận của người cung cấp dữ liệu, không phải kiểm toán sao kê tự động.

### T1 phục vụ và giao thức chọn phiên bản

Catalog hiện tại ở `agent1/adaptive/t1_catalog.py`: G0 Neural 75% + customer 25%,
ba global Neural/LightGBM/XGBoost và ba nhánh học tiếp tương ứng. Không còn các
cây/Neural local train từ đầu hoặc pool top-3 trong T1 phục vụ. Các họ dùng chung
18 feature, snapshot, nhãn và trọng số; learning rate/budget riêng cho mỗi họ.

Mỗi chu kỳ bắt đầu từ global gốc trên cửa sổ local trượt tối đa 730 ngày, trọng số
half-life 180 ngày, replay 30%. Dùng snapshot gần đây với tuần đã quan sát đủ;
không gán nhãn âm cho phần chưa theo dõi. Validation gồm T−210/T−182, audit
T−91→T; chọn bằng cash13 với guard IBS. Chỉ refit cấu hình đã khóa. Không chấm
ngược incumbent trên origin trước khi phiên bản đó sẵn sàng.

Khi incumbent quá mới, giữ nó và lưu cặp dự báo challenger/incumbent. Sau 91 ngày,
chấm một challenger đủ nhãn theo FIFO với policy đã khóa; chỉ đổi sang đúng
artifact đã được chấm. Đủ điều kiện cập nhật không có nghĩa chắc chắn thay model.
Mọi kết quả vẫn mang `pilot_ready=false` đến khi có kiểm định triển khai riêng.

Xem đầy đủ cửa sổ, guard, schema, API và job tại
[hợp đồng T1 hiện tại](../docs/04_AI_Methods/T1_GLOBAL_LOCAL_RUNTIME_2026-11-13.md).
API công khai chỉ trả metadata/chất lượng; không trả estimator, trọng số hoặc
bảng dự báo từng hóa đơn dùng audit. Bag learner chuỗi tiền là thành phần riêng.

### API cho Agent4

Kế toán tạo và lưu bằng `POST /v1/predict`. Agent4 dùng token chỉ đọc để lấy `GET /v1/forecasts` và `GET /v1/forecasts/{id}`.

```json
{
  "cutoff": "2026-11-05",
  "opening_balance": 250000000,
  "horizon_weeks": 13,
  "cash_floor": 200000000,
  "confirmed_weeks": [1, 2, 3],
  "payments_complete": true,
  "delay_days": 0,
  "expense_multiplier": 1
}
```

Trả `weeks` (thu, chi, số dư, P10/P90), `collections`, `alerts`, `model_version`,
`dataset_hash`, `stale_model`, `assumptions`, `scenario`, `pilot_ready`.
Không gửi giao dịch hay nhắc nợ. Ngày dự báo không được trước ngày chốt của phiên bản học.
Kịch bản chậm thu làm tròn lên số tuần, hệ số chi nhân lịch chi đã biết.

Mỗi dòng `collections` có `payment_explanation` cho đúng xác suất tất toán 4 tuần
sau pooling/kịch bản, độc lập với kỳ dự báo tiền. T1 landmark 18 feature dùng
`landmark-grouped-exact-reference-v2`: sáu nhóm giá trị/điều khoản, tuổi hóa đơn,
trạng thái thu tiền, lịch sử khách, lịch sử doanh nghiệp và công nợ hiện tại.
Không dùng bộ giải thích năm feature tại ngày phát hành của Workspace cũ.

SHAP liệt kê đủ liên minh của các nhóm đang có ảnh hưởng, chạy qua chính phân
phối đang phục vụ. `baseline_probability + sum(factors[].contribution)` khớp
xác suất, `contribution_pp` dùng điểm phần trăm. Đây là đóng góp theo nhóm,
không phải bằng chứng nhân quả. UI giữ thông tin nhóm và cảnh báo thiếu đối
chứng khi quần thể nhỏ; mô hình không hỗ trợ trả `status=unavailable`.

Mẫu nền gồm công nợ đủ điều kiện tại cutoff, toàn bộ hoặc lấy mẫu phân tầng khi
lớn. Lưu hash, thành viên, trọng số, đầu vào đã chuẩn bị và kiểm tra độ nhạy tại
`explanation_references`. Lời giải thích lưu cùng `model_version` và `dataset_hash`;
GET không tính lại bằng dữ liệu hoặc model mới. Kế hoạch cũ giữ bản gốc.

Hộp giải thích, lý do ưu tiên và phân rã tiền dùng theme Sổ Son. Giải thích T1
độc lập với chính sách xếp hạng và chưa tự giải thích toàn bộ số dư T6.

Giải thích xếp hạng mới dùng protocol `collection-ranking-v2`: `collection_ranking`
ở cấp kế hoạch ghi chính sách thực tế, công thức, đơn vị điểm, nguồn chọn chính sách,
số khoản đủ điều kiện/hiển thị và số khoản loại theo xóa nợ hoặc liên hệ/tạm bỏ qua
chưa đủ 7 ngày. Mỗi dòng có `collection_rank`, `priority_score`,
`priority_score_unit`, `priority_policy` và `ranking_explanation`.
Ba chính sách vẫn là dư nợ, `1 - triage_probability_4w` và tích của hai yếu tố.
Không đổi quy tắc cộng điểm: tranh chấp/lời hứa/ngày quá hạn chỉ được giải thích
như ngữ cảnh xử lý; cùng điểm giữ thứ tự snapshot. So sánh khoản kế tiếp dựa trên
toàn bộ danh sách đủ điều kiện, kể cả khoản thứ 31 ngoài giới hạn hiển thị 30.

`ranking_explanation.probability_source` của dự báo mới là `active_t1`, cùng
model, pooling và kịch bản với xác suất T1 hiển thị. Không fit một customer T1
riêng để xếp hạng. Khi chính sách dùng xác suất, `probability_explanation` giải
thích đúng nguồn đó và mang cùng phiên bản T1. `displayed_model_version` và
`dataset_hash` cho phép đối chiếu; GET không tính lại. Bản kế hoạch lịch sử giữ
nguồn xác suất đã ghi tại thời điểm tạo.
Điểm là giá trị phân luồng công nợ, không phải tổn thất hoặc hiệu quả thu nợ nhân quả.

V2 giữ dư nợ VND nguyên và tính điểm bằng Decimal từ biểu diễn thập phân của
xác suất, để hai khoản lệch 1 VND không bị coi là bằng điểm khi số tiền lớn.
So sánh điểm, thứ tự và nhóm bằng điểm đều dùng giá trị chưa làm tròn. Trong
JSON, dư nợ/điểm VND nguyên vượt `2^53−1` và điểm VND có phần lẻ được ghi bằng
chuỗi thập phân; xác suất vẫn là số ước lượng. UI định dạng trực tiếp chuỗi tiền,
không đổi qua Number; hiển thị tối đa hai chữ số thập phân. Excel giữ số tiền/điểm
vượt 15 chữ số có nghĩa dưới dạng ô văn bản để không làm mất chữ số. Giá trị
VND lớn trong bảng yếu tố SHAP cũng dùng chuỗi thập phân. Kế hoạch cũ giữ bản
lưu ban đầu; tạo dự báo mới để dùng cách tính V2.

Hàng đợi trống được phân biệt với hết công nợ: nếu còn hóa đơn mở nhưng đều
bị tạm loại theo quy tắc, UI nêu số khoản mở và số khoản hoãn liên hệ; kế hoạch
cũ thiếu số liệu phạm vi dùng thông báo trung tính.

Phân rã T6 được lưu trong `cash_decomposition`, protocol `cash-decomposition-v2`,
target `expected_balance`, đơn vị VND. `invoices[].expected_by_week` dùng đúng
ma trận phân bổ tiền sau xử lý trả từng phần, kịch bản chậm thu và gộp phần
ngoài kỳ; không nhân lại với `payment_probability_4w`. `customers` cộng theo
khách từ toàn bộ hóa đơn mở sau loại xóa nợ, không dùng danh sách ưu tiên 30
khoản và không loại khoản đang hoãn liên hệ. `expected_after_horizon` là dư
nợ chưa dự thu trong kỳ, không phải dự báo xóa nợ hoặc cam kết sẽ thu sau kỳ.

`weeks` phân rã thu thành `ar_in`, `cash_sale_in`, `new_credit_in`; chi thành
`scheduled_out` và `variable_cost_topup`. Phần chi biến đổi bổ sung đã trừ
nghĩa vụ biến đổi có lịch để tránh tính hai lần. Mỗi tuần lưu số dư đầu,
thay đổi và số dư cuối. Runtime kiểm tra tổng thu/chi/số dư khớp đường kỳ vọng
đang phục vụ. `outflows` giữ mã, ngày, ngày biết, loại, số tiền gốc và sau hệ số
kịch bản. Các dòng ngoài kỳ hoặc chỉ biết sau cutoff không được đưa vào.

`risk_focus` lấy tuần cảnh báo đầu tiên (số dư kỳ vọng dưới ngưỡng hoặc tỷ lệ
đường mô phỏng dưới ngưỡng ≥25%); nếu không có cảnh báo lấy tuần có số dư kỳ
vọng thấp nhất. Lưu lũy kế thu/chi, mức thiếu kỳ vọng, khách có dư nợ chưa dự
thu lớn nhất và khoản chi lớn đã biết. Cảnh báo chỉ do mô phỏng được ghi
`simulation_only`, không quy thành thiếu trên đường kỳ vọng. Lịch chi chưa
biết vẫn được báo thiếu phạm vi.

T10 cho bundle partial/T6 mới dùng `t10.identity`, `t10.partial_profile` và
`invoices[].receipt_explanation`: phân rã từng tuần thành tất toán + partial,
lưu dư nợ đầu/cuối kỳ vọng, hazard, q, phân phối tỷ lệ, số tuần hỗ trợ và prior.
SHAP T1 giữ đích xác suất tất toán 4 tuần; không coi là SHAP tiền thu.

Forecast và replay snapshot (dữ liệu theo cutoff, artifact thực tế T1/partial,
tham số T6, hash) được ghi cùng giao dịch. Source engine và runtime được giữ
theo hash; GET/Excel không nạp model active mới. Kịch bản kiểm đúng phiên bản,
phát lại baseline, rồi chạy T6 với cùng nguồn ngẫu nhiên theo hóa đơn/hoạt động.
Trả kỳ vọng, P10/P50/P90, xác suất thiếu tiền từng tuần/cả kỳ và các chênh lệch.
Sai engine/runtime trả 409; cần môi trường đúng bản đã lưu. Phân vị kịch bản là
MC thô, không tự áp dải đã nới cho giả định chưa kiểm chứng. Không diễn giải
độ nhạy thành tác động chắc chắn của việc liên hệ thu nợ.

Bộ sinh `timing_comparison`, UI và hai sheet chỉ dịch kỳ vọng đã xóa. Excel
thêm `Bằng chứng partial theo tuần`, `Profile partial và hỗ trợ`, `Phiên bản T10`;
phân rã toàn danh mục có lọc/phân trang. [Hợp đồng T10 và bước 7](../docs/04_AI_Methods/T10_BUNDLE_EVIDENCE_2026-11-13.md).

| Endpoint | Mục đích |
|---|---|
| `GET /v1/workspace` | Hồ sơ định dạng (`company_profile`), số lượng dữ liệu, tiến độ job, báo cáo phiên bản, trạng thái stale |
| `GET /v1/templates/{kind}` | Tải mẫu CSV theo định dạng hồ sơ; khi chạy độc lập có thể chọn `date_format`, `number_format` qua query |
| `POST /v1/imports/preview` | Multipart file, kind, mapping JSON, date_format, number_format |
| `POST /v1/imports/{id}/commit` | Lưu snapshot đã kiểm tra |
| `DELETE /v1/records/{kind}/{id}` | Xóa bản ghi khỏi snapshot hiện tại |
| `POST /v1/training` | `{asof, payments_complete}` → 202 job ID; poll workspace |
| `POST /v1/models/{id}/activate` | Chọn bản mới hoặc quay về bản cũ |
| `POST /v1/predict` | Kế toán tạo dự báo và snapshot T10 đã lưu |
| `GET /v1/forecasts/{id}/explanations` | Đọc bằng chứng đúng forecast đã lưu |
| `POST /v1/forecasts/{id}/scenarios` | `{customer_id, customer_delay_weeks, expense_id, expense_delay_weeks}`; chạy T6 theo snapshot với nguồn ngẫu nhiên chung |
| `GET /v1/forecasts/{id}/scenarios/{scenario_id}` | Đọc kết quả kịch bản đã lưu |
| `GET /v1/forecasts/{id}/xlsx` | Tải Excel của dự báo đã lưu |
| `POST /v1/portal-connect/tickets` | Token kế toán và `{company}` → mã kết nối dùng một lần, hết hạn sau 60 giây |
| `POST /v1/portal-connect/redeem` | `{ticket}` → khóa truy cập và mã doanh nghiệp; chỉ đổi được một lần |

Khi portal khởi động Agent 1, `AGENT1_COMPANY_PROFILE_FILE` trỏ tới hồ sơ riêng chỉ chứa `code`, `date_format` (`dmy` hoặc `iso`) và `number_format` (`vi-VN` hoặc `plain`). Mã phải khớp doanh nghiệp của token. Agent 1 đọc lại hồ sơ khi tải workspace, tạo mẫu và nhập tệp; các ô định dạng trong giao diện lấy từ cấu hình chung. Hồ sơ đổi sau bước xem trước thì phải kiểm tra tệp lại trước khi ghi. Khi chạy độc lập không đặt biến này, Agent 1 vẫn cho chọn định dạng từng tệp như trước.

Portal dùng `POST /api/agents/agent1/connect-link` để mở tab riêng. API kế toán cấp mã ngẫu nhiên lưu tạm trong bộ nhớ của tiến trình; URL chuyển tab chỉ chứa mã này trong fragment. Agent 1 xóa fragment trước khi đổi mã qua POST cùng origin. Khóa truy cập giữ trong bộ nhớ JavaScript, không lưu vào URL hay trình duyệt. Mã hết hạn, đã đổi hoặc mất sau khi Agent 1 khởi động lại đều yêu cầu mở tab mới từ portal; truy cập trực tiếp vẫn dùng hộp kết nối thủ công. Tải lại tab riêng cũng cần kết nối lại.

Job chạy riêng qua executor một worker; request vẫn trả ngay. Khởi động lại máy chủ
đánh dấu job dở dang là lỗi có thể chạy lại, không giả báo hoàn thành. Xóa toàn DN qua
API cũ bị chặn khi worker đang chạy. Không chạy nhiều process uvicorn trên cùng kho:
mutex hàng chờ là trong tiến trình. Tác vụ lớn cần ít nhất 3 GiB RAM hệ thống trống
trước khi chạy. Worker tách tiến trình có giới hạn RSS mặc định 2 GiB và không có
giới hạn tổng thời gian. Chưa hỗ trợ khôi phục checkpoint khi mất điện.

### Bảo mật và giới hạn triển khai

SQLite mã hóa từng payload bằng Fernet; khóa nằm ngoài thư mục dữ liệu. Snapshot, preview,
phiên bản và forecast đều được mã hóa. Không tải mô hình từ file người dùng. Artifact pickle
chỉ do worker nội bộ tạo, lưu trong bản ghi xác thực mã hóa; phụ thuộc phiên bản thư viện
đã khóa và cần quản trị backup/di trú. Không cung cấp endpoint tải artifact ra trình duyệt.

HTML/JS chỉ là ứng dụng khách; trọng số nằm phía Python. Người quản trị máy chủ vẫn có thể
xem code/khóa. Cần TLS, quản lý danh tính, phân quyền, quota/rate limit, giám sát và chính sách
lưu trữ khi triển khai ra Internet. Phiên bản này là **dịch vụ local một doanh nghiệp**,
chưa là SaaS nhiều doanh nghiệp có SSO/RBAC. Snapshot/preview được giữ lại, chưa có TTL tự dọn.
Không tự gửi dữ liệu tới nhà cung cấp AI, CDN, font bên ngoài hay analytics.

Phạm vi chính là công nợ mở và lịch chi đã biết. Phần hoạt động và hóa đơn bán chịu mới
chỉ được cộng khi có dữ liệu, phiên bản đủ điều kiện và đã chọn phạm vi này; tối đa 13 tuần
đầu. Lịch chi chưa nạp vẫn cần rà soát, kể cả khi dự báo trả giá trị chi bằng 0.
Chưa xử lý FX, tín dụng ngân hàng, hoàn tiền và lịch trả góp chi tiết. P10/P90 là dải mô
phỏng; độ phủ dòng tiền chưa có bằng chứng trên SME thật. Brier 4 tuần đo xác suất tất toán.

### Giao diện và nguồn mở

Thiết kế riêng dạng sổ điều hành: màu giấy/đen xanh, serif hỗ trợ tiếng Việt, bảng công nợ,
quy trình ghép cột, trạng thái trống, phiên bản có rollback, biểu đồ tương tác và xuất Excel.
Không cần npm để chạy. Tài nguyên được vendored tại `ui/workspace/vendor`, gồm giấy phép:

- [Tabler Icons v3.31.0](https://github.com/tabler/tabler-icons/tree/v3.31.0): SVG, MIT.
- [uPlot v1.6.32](https://github.com/leeoniya/uPlot/tree/1.6.32): biểu đồ, MIT.
- [Lora / Google Fonts](https://github.com/google/fonts/tree/main/ofl/lora): font, SIL OFL.

Đã kiểm nguồn ngày 05/11/2026. Không sao chép cả template dashboard hay branding bên thứ ba.
Font/icon/chart nằm local; license kèm theo. Kiểm tra `node --check agent1_service/ui/workspace/app.js`
và `.\.venv\Scripts\python.exe -m pytest tests/adaptive -q` trước khi thay luồng.
Kiểm thử fixture chỉ chứng minh code hoạt động; không là phép chọn phương pháp cho khách.

## Dịch vụ nghiên cứu cũ — legacy

Phần dưới phục vụ tái lập nghiên cứu trước định hướng doanh nghiệp. Dashboard cũ tại
`/research`; `/forecast` cũ giữ cổng NO_GO. Không dùng seed_demo để khởi tạo khách hàng thật.

## Chạy Python

Tại thư mục dự án, cài `requirements.txt`, sau đó:

```powershell
$env:PYTHONUTF8='1'
$env:AGENT1_THREADS='4'
$env:OMP_NUM_THREADS='4'
$env:AGENT1_DEMO_DIR='data/synthetic/tgt'
.\.venv\Scripts\python.exe -m agent1_service.seed_demo
.\.venv\Scripts\python.exe -m uvicorn agent1_service.main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000/research`. Khoá truy cập tự tạo ở `.state-keys/api-token.txt`;
nhập khoá vào ô dashboard hoặc gửi header `Authorization: Bearer ...`.
Không đưa khoá vào URL, Git hoặc ảnh chụp màn hình.

Mặc định `/forecast` trả `409 NO_GO`. Dữ liệu, lời hứa, xác thực và giao diện vẫn hoạt động.
Khi kiểm tra nội bộ trên tổng hợp, có thể cấu hình `AGENT1_RESEARCH_MODE=1`
trước khi khởi động. Kết quả vẫn mang nhãn nghiên cứu và chưa đủ điều kiện pilot.

## Docker

Khi Docker engine hoạt động: `docker compose up --build -d`.
Compose nạp công ty F000 từ thế giới `tgt` vào SQLite mã hoá trên volume riêng,
chỉ mở cổng trên loopback. Đọc token bằng lệnh `docker compose exec agent1 cat /keys/api-token.txt`.
Lần kiểm hiện tại trên Windows chưa xây/chạy container do Docker daemon không hoạt động;
đã kiểm dịch vụ bằng TestClient và Python local.

## API

`GET /health`, `POST /ingest`, `POST /forecast`, `POST /whatif`, `POST /promises`,
`GET /alerts`, `GET /data`, `DELETE /data`, `GET /models`, `GET /monitoring`. Ngoài health và trang đăng nhập,
các API đều yêu cầu token. Máy chủ gắn một DN; payload mang mã DN khác bị từ chối.

Importer CSV/Excel dùng ánh xạ cấu hình cho năm mẫu ngân hàng; mẫu kiểm thử không
thay cho chứng nhận hỗ trợ mọi phiên bản xuất của ngân hàng. XML hỗ trợ namespace,
kiểm phiên bản và nhận diện tham chiếu thay thế; nghiệp vụ điều chỉnh/huỷ thật cần được nghiệm thu thêm.

### Nhập hóa đơn T0

Mọi hóa đơn qua JSON, XML và Excel ERP đều cần đủ trường chuẩn để kiểm MST,
tiền trước thuế, VAT, tổng tiền, ký hiệu, số, ngày và tiền tệ. File ERP thiếu
các trường này bị từ chối; hệ thống không tự đoán VAT hoặc MST. Cùng một hóa
đơn từ XML và ERP được đối chiếu bằng `(seller_mst, symbol, invoice_no)` và
ngày/số tiền trước khi gộp thành một bản ghi. Khác biệt hoặc tham chiếu không
rõ được trả lỗi 422 và không ghi lô nhập.

Tiền nguồn nhận chuỗi thập phân hoặc số nguyên JSON; JSON float bị từ chối.
T0 lưu `amount_net_minor`, `vat_minor`, `amount_gross_minor` là số nguyên theo
VND/JPY (0 chữ số thập phân) hoặc USD/EUR/CNY (2 chữ số); các trường tiền gốc
được chuẩn hóa thành chuỗi. Sai độ chính xác tiền tệ, NaN/Infinity và lệch
giữa hai nguồn bị chặn bằng phép so số nguyên. Chỉ góc nhìn đưa vào mô hình
mới chuyển thành số thực. Mô hình hiện tính bằng VND; hóa đơn hoặc sao kê
ngoại tệ được nhập T0 nhưng bị chặn khi dự báo/huấn luyện cho đến khi có
quy đổi tỷ giá có nguồn.

Mỗi hóa đơn và sự kiện hủy có `available_on` là ngày dữ liệu đã sẵn cho hệ
thống (mặc định ngày nhập theo giờ Việt Nam). `ingested_on` ghi ngày API thực
sự nhận bản ghi. Khi nhập lại dữ liệu lịch sử, cần khai báo `available_on`
theo chứng cứ nguồn; API chưa tự xác thực chứng cứ ngày lịch sử. Ngày này
không được trước ngày lập hóa đơn/sự kiện.
`record_version` là số nguyên dương cho phiên bản dữ liệu hóa đơn, mặc định 1;
bản sửa cùng nguồn phải tăng số phiên bản. Lịch sử phiên bản được giữ trong
kho mã hóa và dự báo/huấn luyện tại ngày cắt chỉ thấy phiên bản đã nhận đến
ngày đó. Trường `document_version` của XML là phiên bản định dạng XML, khác
với `record_version`.

Nhập lại cùng nguồn và `record_version` so sánh toàn bộ nội dung nghiệp vụ đã
chuẩn hóa, gồm khách hàng, hạn trả, credit note và tham chiếu chứng từ. Retry
giống nhau không tạo revision; sửa nội dung phải tăng `record_version`, nếu
không API trả 422. Kho giữ `source_payloads` riêng cho XML/ERP để việc gộp nguồn
không làm sai phép so sánh. Tên file, dòng nguồn, hash file và ngày nhập lại
không làm thay đổi nội dung nghiệp vụ hay viết lại availability của bản cũ.
Kho cũ đã gộp nhiều nguồn nhưng thiếu nội dung riêng để đối chiếu phải nhập
phiên bản mới; hệ thống không đoán rằng payload cũ và mới giống nhau.

Các trường ngày nhập qua JSON, XML/ERP và `/promises` được chuẩn hóa về ngày
Việt Nam `YYYY-MM-DD`, kể cả nguồn có timestamp/offset. Ngày bắt buộc thiếu hoặc
không hợp lệ bị từ chối trước khi lưu. Bản đọc lời hứa cũ có timestamp cũng
được chuẩn hóa mà không sửa bản nguồn hoặc lịch sử trong kho mã hóa.

`/ingest/file` nhận `available_on` và `record_version` trong form. CSV và
Excel bị từ chối nếu header trống/trùng hoặc dòng CSV sai số cột; JSON API
chặn khóa trùng và số NaN/Infinity. Lỗi file 422 chứa tên file, số dòng
(nếu xác định được), SHA-256 và lý do. File lỗi không ghi vào bảng nghiệp vụ;
thông tin lỗi và dòng nguồn (khi đọc được) được giữ mã hóa trong
`ingest_quarantine` để kiểm tra lại. Mỗi bản ghi nhập thành công có
`source_file`, `source_row`, `source_sha256`.

### Sao kê ngân hàng

File CSV/Excel ngân hàng phải có cả cột ghi có và ghi nợ, cùng form field
`statement` dạng JSON. Ví dụ:

```json
{"account_id":"001","currency":"VND","period_start":"2024-03-01","period_end":"2024-03-31","opening_balance":"1000","closing_balance":"1080","total_credits":"100","total_debits":"20"}
```

Trước khi nhập sao kê, người vận hành tạo danh mục tài khoản **từ xác nhận hoặc
bản xuất cổng ngân hàng**, kiểm duyệt và lưu riêng tại
`<AGENT1_STATE_DIR>-keys/bank-accounts.json` (hoặc đường dẫn
`AGENT1_BANK_ACCOUNTS_FILE`). File bằng chứng gốc đặt cạnh danh mục. Ví dụ:

```json
{"firm_id":"F000","source_type":"bank_confirmation","evidence_file":"confirmation.pdf","evidence_sha256":"<SHA-256 của confirmation.pdf>","reviewed_by":"Người kiểm duyệt","reviewed_on":"2026-10-27","accounts":[{"bank":"vcb","account_id":"001","currency":"VND"},{"bank":"bidv","account_id":"002","currency":"VND"}]}
```

Phải thay chuỗi SHA-256 minh họa bằng hash thật của file bằng chứng. Danh mục
phải liệt kê toàn bộ tài khoản liên quan trong kỳ; mã tài khoản phải duy nhất
trong một DN. API nạp sao kê không có quyền tạo hoặc sửa danh mục này. Khi
thiếu danh mục/bằng chứng hoặc hash không khớp, file sao kê bị từ chối. Trường
`expected_accounts` trong metadata file là tùy chọn; nếu có thì phải khớp
**toàn bộ** danh mục đã duyệt, không thể dùng nó để rút bớt tài khoản.

T0 kiểm từng giao dịch nằm trong kỳ, tổng hai chiều khớp metadata, phương
trình số dư và sự nối tiếp ngày/số dư giữa các kỳ của cùng tài khoản. Mỗi
giao dịch (kể cả ghi nợ) được giữ trong `bank_entries`; chỉ giao dịch ghi có
được đưa vào `bank_txns` cho mô hình. `GET /bank/coverage` báo tài khoản hoặc
đoạn kỳ còn thiếu so với danh mục đã duyệt; các sao kê cũ chưa gắn bằng chứng
duyệt được báo là chưa tin cậy và cần nhập lại. Khi đã có sao kê
kiểm chứng, dự báo và huấn luyện chỉ dùng giao dịch thuộc sao kê đó và chặn
nếu phạm vi đến ngày cắt chưa đủ. `available_on` của file (mặc định ngày
nhập) cũng áp cho kỳ và giao dịch; nhập lịch sử phải khai báo ngày sao kê đã
sẵn có, không trước ngày cuối kỳ. Hash và xác nhận của người kiểm duyệt giúp
đối chiếu với nguồn tách biệt, nhưng phần mềm không tự xác thực ngân hàng phát
hành file hay chứng minh hồ sơ nguồn đã liệt kê đủ tài khoản. Đường nhập giao dịch
JSON cũ vẫn phục vụ nghiên cứu nhưng không xác nhận phạm vi sao kê.

XML `TCHDon=1` được hiểu là thay thế; `TCHDon=2` là khoản điều chỉnh **có dấu**.
Tham chiếu phải xác định duy nhất hóa đơn đã nhập. Dự báo và huấn luyện dùng
giá trị công nợ có hiệu lực tại ngày cắt, không cộng riêng hóa đơn bị thay thế
hoặc bản điều chỉnh. Sự kiện hủy đã xác nhận được nhập qua `/ingest` với
`table="invoice_events"` và bản ghi gồm `event_id`, `invoice_id`,
`event_type="cancel"`, `event_date`. Ví dụ:

```json
{"table":"invoice_events","records":[{"event_id":"cancel-001","invoice_id":"INV-001","event_type":"cancel","event_date":"2024-02-01"}]}
```

Các loại XML nhiều hóa đơn liên quan hoặc chiết khấu thương mại chưa được ánh
xạ an toàn sẽ bị từ chối. Thông báo hủy XML riêng của cơ quan thuế cần mẫu
thực tế để bổ sung parser; hiện cần nhập sự kiện hủy đã xác nhận như trên.

<a id="t5-ledger"></a>

## T5: nghĩa vụ, thanh toán và phần còn lại — 11/11/2026

**Nhận diện và nạp bổ sung — 12/11/2026:** mỗi dòng vẫn là một lần đến hạn,
không phải mẫu tự lặp. Thêm ba cột tùy chọn đi cùng nhau: `obligation_ref`
(mã hợp đồng hoặc khoản cố định, có thể ghép từ `contract_id`/`fixed_cost_id`),
`payment_period` (`YYYY-MM`, `YYYY-Q1`…`YYYY-Q4` hoặc `YYYY`) và
`installment_no` (số nguyên dương). Định danh nghiệp vụ gồm mã này **và loại
nghĩa vụ, kỳ, đợt**; gốc và lãi cùng hợp đồng là hai khoản riêng. Đợt đến hạn
khác với số lần thực trả. Kỳ không tự suy từ ngày trả: dời tiền thuê tháng 11
sang tháng 12 vẫn giữ kỳ `2026-11`.

```csv
expense_id,obligation_ref,category,payment_period,installment_no,date,amount,known_at
THUE-202611,HD-THUE-01,rent,2026-11,1,2026-11-30,10000000,2026-11-01
THUE-202612,HD-THUE-01,rent,2026-12,1,2026-12-31,10000000,2026-11-01
```

Trước khi lưu, Workspace phân loại và phân trang toàn bộ các dòng **thêm
mới / sửa / trùng giữ nguyên / cần kiểm tra**, cho lọc kết quả và xem trước–sau
của từng bản sửa. File bổ sung không xóa các dòng vắng mặt. Mã khác nhưng
khớp định danh nghiệp vụ được đối chiếu về mã lần đến hạn đã có, giữ liên kết
sao kê. Màn hình chỉ rõ mã được giữ: dùng mã này trong `expense_payments` và
`replaces_expense_id`; không tạo bí danh thanh toán mới từ mã nạp nhầm.
Nạp lại nội dung không đổi không tăng nghĩa vụ hay sửa ngày biết ban đầu.
Bản sửa nội dung cần `known_at` mới hơn, giữ snapshot trước đó. Một mã đã
đủ định danh không được dùng sang hợp đồng/loại/kỳ/đợt khác; kỳ mới cần mã
mới. Các nội dung xung đột trong cùng file hoặc lỗi bất kỳ chặn cả lần lưu.
Khi dữ liệu đổi sau bước kiểm tra, phải xem trước lại.

Dữ liệu cũ thiếu toàn bộ ba cột vẫn hoạt động và có nhãn **cần bổ sung định
danh**. Bổ sung theo cùng `expense_id` với ngày ghi nhận mới hơn; lịch sử cũ
không bị sửa. Nếu file sau bỏ cả ba cột của khoản đã được định danh, hệ thống
giữ định danh hiện có. Không được bỏ một phần hoặc đổi định danh qua sửa
nguồn. Với khoản chưa bổ sung định danh, việc chống trùng vẫn dựa vào mã lần
đến hạn; hệ thống không tự gộp chỉ vì cùng số tiền và ngày trả.

Workspace dùng cùng bảng `outflows` cho mỗi lần đến hạn. `expense_id` có thể
ghép từ cột `obligation_id`; `date` có thể ghép từ `due_date`. Cùng mã được sửa
bằng ngày ghi nhận mới hơn; phiên bản cũ vẫn phục vụ dự báo tại ngày trước đó.
Không tạo mã mới cho cùng một lần đến hạn chỉ để sửa số tiền hoặc ngày trả.

Các trường tùy chọn: `status` (`open`/`cancelled`), `forecast_date` (ngày dự kiến
trả/nhận phần còn lại, từ ngày đến hạn), `source`, `verified` (`true`/`false`),
`refund_approved_at`, `business_day` (`none`/`following`/`preceding`) và
`replaces_expense_id`. `verified` xác nhận hồ sơ do doanh nghiệp cung cấp;
không xác nhận registry luật đã được chuyên gia kiểm tra.

Loại mở rộng gồm `pit_withholding`, `foreign_contractor_tax`, `salary_bonus`,
`rent_contract`, `loan_interest`, `loan_principal`, `cit_final` và `vat_refund`.
Các loại này cần `source` và `verified=true`. Số tiền và hạn lấy từ hồ sơ đã
xác nhận, không tự tính nghĩa vụ thuế. `cit_final` là số quyết toán còn phải
nộp sau khi trừ tạm nộp; bộ sinh lịch nhận riêng `cit_by_year={2024: ...}`.

Nạp sao kê trước, rồi nạp bảng **Thanh toán nghĩa vụ T5** (`expense_payments`):

```csv
settlement_id,expense_id,bank_id,payment_date,amount,known_at
TRA-001,THUE-202602,BANK-CHI-001,2026-02-09,4000000,2026-02-09
```

Một dòng sao kê có thể trả nhiều nghĩa vụ nhưng tổng phân bổ không vượt tiền
sao kê; tổng thanh toán mỗi nghĩa vụ không vượt số tiền nghĩa vụ. Ngày và chiều
phải khớp sao kê. Trả từng phần/trả sớm chỉ làm giảm số còn phải chi; giao dịch
đã xảy ra thuộc số dư đầu, không bị trừ lại trong dự báo. Tiền hoàn cần sao kê
chiều thu, nhóm `other`, `cash_flow_class=non_ar`, và ngày nhận từ ngày quyết
định trở đi. Chi cố định không được gắn vào nhóm sao kê `variable_cost`.

Khoản chi đến/quá hạn chưa trả được giữ và đưa sang ngày làm việc kế tiếp;
doanh nghiệp có thể nhập `forecast_date` mới. Khoản hoàn chưa có quyết định
không vào dự thu. Khoản hoàn quá ngày dự kiến nhận cần ngày dự kiến mới,
không tự chuyển sang ngày mai. Hủy phần còn lại bằng `status=cancelled`;
các khoản đã thanh toán và lịch sử ghi nhận vẫn được giữ.

Đổi lịch thuê cũ sang hồ sơ hợp đồng hoặc chia `loan_service` thành gốc/lãi:
các mã mới khai `replaces_expense_id` trỏ đến mã cũ. Mã cũ được loại khỏi dự
chi từ ngày biết bản thay thế. Không cho thay mã đã có thanh toán; trường
hợp đó cần giữ cùng mã và sửa hồ sơ/phân bổ tương ứng.

Có một khoản chi trong tuần chỉ cho trạng thái `scheduled_unconfirmed`.
Chỉ các tuần người dùng xác nhận đã rà soát đủ mới nhận `scheduled` hoặc
`confirmed_zero`; mọi tuần chưa xác nhận đều tiếp tục cảnh báo thiếu lịch.
Dự báo lưu `t5` (nghĩa vụ, thanh toán, phần còn lại), dòng thu hoàn
`obligation_in`, phân rã thu/chi và Excel tương ứng. Giao thức dải tiền mới
`cash-v3-t5-ledger` không dùng các kế hoạch cũ để hiệu chỉnh dải.

Kiểm thử: `tests/adaptive/test_t5_runtime.py`, `tests/test_obligations.py`,
`tests/test_t0_t5.py` và các kiểm thử Workspace. Đây là kiểm chứng kỹ thuật;
không đổi giá trị hay trạng thái xác minh của các quy tắc pháp lý lịch sử.

## Giới hạn hiện tại

Engine local dùng lịch sử đối soát đã xác nhận và mô hình riêng DN đã chọn;
chưa chọn model thì dùng B1d. Endpoint dự báo không tự huấn luyện.
Chưa thay thế mô hình tiền huấn luyện/fine-tune của thí nghiệm T6; lịch chi chưa có
`known_at` được dự báo từ lịch sử. E2E thực nghiệm ghi rõ giới hạn này và không mở cổng pilot.
Theo dõi cổng tại `docs/03_Evaluation/GATES_CURRENT.md`.

<a id="luong-t0-t9-thong-nhat"></a>

## Luồng T0–T9 thống nhất, cập nhật 06/11/2026

Luồng runtime duy nhất của API là **T0 Khánh → T9 từ lõi Thắng → snapshot
quan sát → train/dự báo/giám sát → T10 và Agent 4**. T0 vẫn đọc XML/ERP/sao kê,
kiểm chứng từ và giữ nguồn. Package `agent1/reconciliation/_thang/` giữ nguyên
tám module phụ thuộc từ commit `89c144ba3b3d2e7d79d8cb70dc7baf99dc319268`;
`provenance.json` ghi hash từng file. Runtime chỉ gọi `constrained.allocate`
và `ledger.replay`; các matcher cũ còn trong dependency không phải lựa chọn
runtime. Các thí nghiệm T9 cũ giữ làm hồ sơ/đối chứng, không tự chuyển thành
phân bổ đã xác nhận.

`constrained_flow` dùng tiền nguyên VND, phân biệt doanh nghiệp/khách hàng,
không ép FIFO khi nhiều nghiệm. Giới hạn mặc định: tuổi hóa đơn 3.650 ngày,
component mỗi phía tối đa 12, subset amount-only tối đa 3; vượt giới hạn hoặc
thiếu bằng chứng chuyển duyệt. Không suy accuracy từ nghiệm duy nhất. Chưa có
phí/tỷ giá được xác minh thì không tự bù chênh lệch để khớp. Các khả năng FX
của upstream không đồng nghĩa dịch vụ/mô hình hiện hỗ trợ ngoại tệ.

**Các thao tác trên dashboard:** nhập dữ liệu → chọn ngày hiện tại → tìm đề
xuất → đối chiếu chứng từ → xác nhận → xem công nợ/dự báo. Giao dịch mơ hồ
có thể nhập phân bổ thủ công với mã giao dịch, mã hóa đơn, tiền nguyên và
nguồn bằng chứng. Mỗi giao dịch chỉ được phân bổ cho một khách; tiền thừa
giữ chưa phân bổ. Có thể đảo quyết định, hoặc ghi/đảo quyết định write-off
toàn bộ dư nợ còn lại. Chưa hỗ trợ write-off từng phần hoặc thu hồi sau
write-off; cần đảo quyết định trước khi sửa các phân bổ liên quan.

| API có bearer token | Chức năng |
|---|---|
| `POST /reconciliation/run` | `{cutoff}` tạo đề xuất; chưa làm giảm công nợ |
| `POST /reconciliation/accept` | `{idempotency_key, reviewed_by, proposal_id}` xác nhận đề xuất hiện hành; hoặc `allocations=[{txn_id,invoice_id,amount_minor}]` cùng `note` cho phân bổ thủ công |
| `POST /reconciliation/reverse` | `{idempotency_key,decision_id,reviewed_by,note}` đảo phân bổ hoặc write-off |
| `POST /reconciliation/writeoffs` | `{idempotency_key,invoice_id,effective_on,reviewed_by,source_ref}` ghi write-off phần dư |
| `GET /snapshot?cutoff=YYYY-MM-DD` | Công nợ, thu tiền đã xác nhận, trạng thái đóng, `contract_version` và hash snapshot |
| `GET /reconciliation/history?cutoff=YYYY-MM-DD` | Quyết định và write-off; vẫn đọc được để đảo quyết định khi chứng từ T0 đã đổi làm snapshot không hợp lệ |
| `POST /models/deactivate` | Bỏ chọn model cũ, giữ artifact để kiểm toán; cho phép dùng baseline nghiên cứu |

Mỗi yêu cầu ghi có idempotency key: retry nguyên nội dung không ghi lần hai;
đổi nội dung phải dùng key mới. Lệnh và bằng chứng lưu mã hóa cùng Store,
không dùng SQLite plaintext của upstream. Xác nhận chỉ commit **sổ nội bộ**,
không ghi ERP, chuyển tiền hay xác minh hộ tính xác thực của file ngân hàng.
Write-off và credit note không tạo cash. Đảo phân bổ không đảo giao dịch bank.

**Hợp đồng thời gian và nguồn (`agent1-observed-cash-v2`).** Hóa đơn giữ
`available_on` và lịch sử revision của T0. Giao dịch JSON mới có availability,
tiền minor và không được ghi đè cùng `txn_id` với nội dung khác. Nguồn cũ
thiếu availability chỉ có fallback ngày nghiệp vụ cho nghiên cứu; không đủ
để tuyên bố backtest vận hành. Các lệnh duyệt/đảo/write-off luôn nhận ngày
hiện tại theo Việt Nam từ máy chủ; API không cho caller lùi ngày biết quyết
định. Đề xuất cũ hoặc đã thay dữ liệu phải chạy lại. Bank value date và ngày
biết phân bổ được giữ riêng: xác nhận tháng 9 không xuất hiện trong snapshot
tháng 7. Chứng từ chưa nhập đủ không được coi là chưa từng có sự kiện.

Khách hàng, lời hứa và lịch chi giữ cả bản hiện hành lẫn lịch sử mã hóa theo
ID và `available_on`/`known_at`. Snapshot chọn nguyên phiên bản đã biết tại
cutoff. Bản sửa phải có ngày biết mới hơn bản cũ; cùng ngày khác nội dung
bị từ chối vì hợp đồng hiện có độ phân giải theo ngày. Retry nguyên nội dung
không thêm phiên bản. Với kho cũ, bản còn lại được giữ trước lần sửa đầu;
không thể khôi phục các bản đã bị ghi đè trước khi có lịch sử.

Khi nguồn có cả `available_on` và `known_at`, chọn phiên bản hóa đơn, áp dụng
sự kiện hủy, snapshot giao dịch và nhãn giảm trừ đều dùng ngày muộn hơn.
Nhập lại sự kiện hủy giữ nguyên nội dung và ngày biết không thêm sự kiện;
ID nội bộ và ngày nạp lại không làm retry thành xung đột. Thay nội dung hoặc
ngày biết của sự kiện đã lưu vẫn bị từ chối.
Retry giao dịch không được đổi ngày biết,
remittance hoặc tài khoản/kỳ sao kê rồi báo thành công nhưng bỏ qua thay đổi.

Sau revision, phân bổ đã duyệt được đối chiếu lại với khách hàng, ngày lập
hóa đơn, loại khoản thu và số tiền nguồn. Khoản thu trước ngày lập hóa đơn
theo bản sửa hoặc thuộc khách khác làm snapshot/dự báo trả 422. Bản sửa T0
vẫn được giữ làm nguồn; cần kiểm tra nguồn và đảo quyết định xung đột trước
khi tiếp tục. Endpoint lịch sử và đảo quyết định vẫn hoạt động khi snapshot
bị chặn. Đây là kiểm tra sửa dữ liệu; chưa hỗ trợ nghiệp vụ chuyển công nợ.
Sửa tên cùng `customer_id` không tạo chuyển khách.

Write-off lưu `invoice_context` gồm ID hóa đơn/khách, MST người bán/mua, ký
hiệu/số, ngày lập và tiền tệ. Snapshot kiểm lại phạm vi và dư nợ; đổi khách
hoặc chứng từ không tự mang write-off cũ sang bản mới. Quyết định cũ thiếu
phạm vi chỉ được dựng lại từ lịch sử T0 tại ngày duyệt; thiếu lịch sử hoặc
đổi phạm vi cùng ngày không xác định được thứ tự thì báo cần đảo và duyệt
lại, không suy phạm vi từ khách hàng hiện tại. Không sửa
event cũ. Thay hạn trả đơn thuần không làm đổi phạm vi quyết định xóa nợ.

`last_cash_date` giữ ngày thu tiền cuối, `closed_date` giữ ngày hết công nợ.
Credit note đến sau hoặc cùng ngày khoản thu cuối làm hết dư nợ được ghi
`closure_type=credit_note`, không tạo `paid_date_est`. Nếu thu đủ phần còn
lại sau credit note, ngày thu đó có thể là ngày trả đủ phần tiền còn lại.
Một revision giảm giá trị hóa đơn sau khoản thu không được lùi ngày tất toán;
khi thiếu ngày nghiệp vụ riêng của revision, dùng ngày biết bản sửa và ghi
`closure_type=adjustment`. `outcome_known_at` tính cả ngày biết chứng từ giảm trừ.

`ObservedSnapshotBuilder` dựng lại view tại từng cutoff cho T1/T2/T3/T8;
chỉ ghép kết quả tương lai khi tạo **nhãn** tại `label_end`. Khoản tiền đã
về trước origin nhưng được nhận diện muộn không bị biến thành tiền tương
lai; các hàng đó bị loại khỏi risk set huấn luyện, kể cả khoản thu một phần
và cả nhãn đã trả/chưa trả. Nếu phân bổ đã được biết tại cutoff thì dư nợ
vẫn trừ đúng khoản thu đó. Không dùng kết quả duyệt sau cutoff để sửa ngược
feature. Cùng bộ dựng mẫu này phục vụ cả train và validation. Credit note
trong cửa sổ nhãn kết thúc thời gian theo dõi số tiền ban đầu, kể cả thu một
phần rồi giảm trừ phần còn lại. Chứng từ giảm trừ có ngày nghiệp vụ trước
origin nhưng được biết sau origin không trở thành nhãn thu tiền tương lai.
Hóa đơn đổi khách giữa origin và label_end không dùng để học lịch sử khách cũ.
Hóa đơn đổi giá trị gốc giữa hai mốc cũng bị loại khỏi các origin có số tiền
khác kết quả cuối; chưa suy nhãn cho số tiền cũ từ trạng thái số tiền mới.
Hóa đơn hủy/thay thế không còn endpoint
ở label_end bị loại thay vì coi là chưa trả. Chưa có nhãn đủ chín/hợp lệ
thì retrain trả lỗi rõ ràng; dữ liệu vừa tải không tự tạo được một lịch sử
phê duyệt hoặc một backtest độc lập.

Tập hóa đơn mở từ ledger được áp dụng trước khi tính các đặc trưng tổng hợp
khách hàng/công ty. Hóa đơn đóng bằng tiền thu cộng giảm trừ không làm tăng
số hóa đơn mở của hóa đơn khác; dư nợ VND còn đúng 1 đồng vẫn được giữ.

T4 dùng hóa đơn đã quan sát tại cùng cutoff cho doanh thu mới; T5 lọc theo
ngày biết lịch chi; T6 dùng dư nợ đã trừ thanh toán/credit và cùng lịch sử
thu tiền. Tiền đã về trước cutoff không cộng lại vào tiền tương lai; số dư
đầu kỳ vẫn là số dư ngân hàng người dùng cung cấp. Khi không còn hóa đơn
mở, T6 vẫn chạy phần số dư/thu mới/chi. T10 và Agent 4 đọc `/forecast`,
`/snapshot`, `/alerts`; forecast có `data_contract`, `data_snapshot` và
`model_version` để truy vết. Đây là giao diện tích hợp, chưa có thay đổi
mã của Agent 4 trong repo này.

Hai phase tách riêng: job retrain tạo ứng viên, người vận hành chọn phiên bản,
rồi `/forecast` chỉ suy luận từ phiên bản đó hoặc B1d. Đường runtime không
fit T1/T4 hay dựng tập train. Nếu chưa có artifact T4 thì chưa tính thu từ
hóa đơn mới (`new_revenue_included=false`); giao diện hiển thị giới hạn đó.
Registry/API hiện mới có T1, chưa có đường chọn artifact T4 cho dịch vụ;
T4 fit trong các thí nghiệm offline vẫn được giữ.

**Chuyển dữ liệu cũ:** giữ nguyên dữ liệu T0, không tự nhập các liên kết T9
thí nghiệm thành nhãn. Chạy đối soát và duyệt lại từ bằng chứng. Model registry
kiểm thêm hash của pipeline mới: model cũ có chữ ký khác bị từ chối; dùng
nút baseline hoặc `/models/deactivate`, sau đó chỉ retrain/kích hoạt khi đủ
lịch sử hợp lệ. Bộ ứng viên V6 93 feature vẫn là nghiên cứu riêng; thay
nguồn T9 không tự chứng minh nó tương thích hoặc kích hoạt nó.

Kiểm chứng kỹ thuật không thay G15/G13, UAT hoặc pilot thật. Không dùng dữ
liệu synthetic để tự chọn một model thắng rồi bật triển khai; fixture chỉ
kiểm bảo toàn tiền, trạng thái, idempotency và chống rò rỉ thời gian.

Bằng chứng kỹ thuật của đợt tích hợp: [JUnit hồi quy](../outputs/implementation/t9_canonical_runtime_tests.xml)
và [metadata kiểm chứng](../outputs/implementation/t9_canonical_runtime_verification.json).
Kiểm tra cú pháp/định danh DOM đã qua; kiểm tra trực quan trên Chrome chưa
hoàn thành vì computer-use không xác định được URL đủ chắc chắn và đã dừng.

## Phiên bản mô hình và giám sát local

Dựng lại bộ mẫu từ kho đã nạp bằng cùng builder mà job train sử dụng:

```powershell
.\.venv\Scripts\python.exe -m agent1.jobs.retrain --firm F000 --reason manual --cutoff 2026-11-06 --state .state --prepare-only --dataset-output outputs/data/observed_t1_20261106
```

Lệnh này tạo `train.parquet.enc`, `validation.parquet.enc` và `dataset.json`
ghi hash, số hàng, khoảng nhãn, missing windows và chữ ký mã. Parquet được
mã hóa bằng khóa của kho nguồn. Không fit hoặc kích hoạt model, không ghi
ngược dữ liệu T0/T9, không ghi đè thư mục dataset đã tồn tại. Nếu thiếu kho
nguồn thì dừng, không tự tạo dữ liệu hoặc lịch sử duyệt. `trainable=false`
nghĩa bộ mẫu chưa đủ nhãn để train; phải bổ sung dữ liệu có chứng cứ.

```powershell
.\.venv\Scripts\python.exe -m agent1.jobs.retrain --firm F000 --reason psi --cutoff 2024-07-01
.\.venv\Scripts\python.exe -m agent1_service.jobs.weekly --firm F000 --cutoff 2024-10-01
```

Retrain tạo ứng viên T1 từ nhãn ledger đã xác nhận, giữ nhãn train trước cutoff ít nhất
120 ngày. Validation chấm xác suất thu đủ tiền tại 7/28/56/91 ngày, gồm cả hóa
đơn đã trả và chưa trả có đủ thời gian theo dõi từng mốc. Model và B1d được
chấm trên cùng các hàng; báo Brier, Brier có trọng số dư nợ, số hàng trả/chưa
trả và số hàng thiếu theo dõi. Không đủ theo dõi thì điểm là `null`; không
gán nhóm này là chưa trả. Pinball/coverage trên nhóm đã trả chỉ còn là chẩn
đoán phụ. Kết quả có điều kiện trên nhóm đủ theo dõi; giảm trừ có thể gây
kiểm duyệt có thông tin, chưa chứng minh hiệu quả toàn bộ danh mục hay GO.
Thêm `--activate` để chọn ứng viên cho **nghiên cứu local**.
Dịch vụ chỉ dùng phiên bản có cutoff phù hợp và hash mã/mô hình còn khớp.
Mô hình dạng text LightGBM, metadata và mẫu tham chiếu được mã hoá trong SQLite;
API danh sách không trả mô hình hoặc mẫu đặc trưng. Xoá DN xoá cả registry.

Nhập số dư qua `/ingest` với `table="cash_balances"`, mỗi bản ghi có `date`, `balance`.
Tác vụ weekly tính PSI và độ phủ trên số dư thực tế đúng cuối tuần đã tới hạn;
thiếu số dư được báo thiếu bằng chứng. Ngưỡng PSI >0,1 hoặc bốn lượt độ phủ liên tiếp
ngoài [0,7;0,9] yêu cầu xem xét retrain. Tác vụ này chưa tự tạo lịch trên hệ điều hành.
Dashboard hiển thị báo cáo đã lưu, phiên bản và cảnh báo local.


## Vận hành pilot SME

### T6 và ứng viên T1 landmark 18 feature

`POST /v1/predict` nhận `simulation_paths` (100–10000, mặc định 1000),
`shap_limit` (0–30, mặc định 30), và `simulation_seed` (mặc định 7). Toàn bộ
công nợ hợp lệ vẫn tham gia dự báo. Danh sách thu hồi vẫn tối đa 30 dòng;
những dòng ngoài giới hạn SHAP mang trạng thái `deferred`. Giới hạn này áp
dụng cả giải thích xác suất T1 và xác suất xếp hạng nếu policy dùng xác suất.
`compute_budget` trong kế hoạch lưu cấu hình thực tế. Tăng đường mô phỏng
chỉ thay độ chính xác số của dải/xác suất mô phỏng; kỳ vọng tiền tính giải tích.

`/v1/predict` nạp catalog global bằng `AGENT1_T1_GLOBAL_CATALOG` và bundle đã
được chọn cho doanh nghiệp. Hai biến research allowlist cũ không còn override
T1 phục vụ. Loader kiểm hash và ngày sẵn sàng; catalog hiện là artifact synthetic,
chưa thay cổng pilot thật. Chi tiết T1 ở hợp đồng hiện tại phía trên.

Xem [bộ pilot](../pilot/BO_PILOT_SME.md) và [sổ nghiệm thu](../pilot/quyet_dinh.md). Mỗi DN dùng tiến trình, thư mục CSDL, khóa mã hóa và token riêng. Đặt các token đọc riêng biệt bằng `AGENT1_AGENT4_TOKEN`, `AGENT1_VIEWER_TOKEN`; không tái sử dụng giữa các DN hoặc với token quản trị. Thu hồi bằng cách xóa/đổi biến và khởi động lại. Quyền đọc chỉ mở danh sách và bản dự báo đã lưu. Kế toán giữ quyền nhập, chạy, kích hoạt và đối chiếu.

Đối soát: `GET /v1/reconciliation`, `POST /v1/allocations`. Tra kết quả với `GET /v1/forecasts/{id}/actuals?asof=YYYY-MM-DD`; thêm `payments_complete=true` chỉ khi đã kiểm tra đủ thu đến ngày chấm để lấy precision–coverage danh sách thu nợ. Đầu ra có sai số bằng VND, độ phủ, độ rộng, báo giả/bỏ sót, hash dữ liệu thực tế. Ngày tạo sau ngày chốt đánh dấu hồi cứu. Công nợ trả từng phần chỉ có mô hình tiền riêng khi có ≥20 lịch sử tương đồng; dải mô phỏng gốc chưa được hiệu chỉnh.

Với sao kê đã đối soát liên tục ≥104 tuần, so mốc cùng kỳ 52 tuần với GBM cho hai nhóm bán thu ngay/chi biến đổi. Chọn `try_deep_cash` để xét Chronos local (thư mục `AGENT1_CHRONOS_DIR`) và GRU Gaussian tự hồi quy khi đủ 156 tuần; `AGENT1_DL_DEVICE=cpu` mặc định. Ba gốc hiệu chỉnh 13 tuần và một kỳ kiểm tra độc lập; phải chọn `include_operating` mới đưa dự báo này vào kế hoạch. Với hóa đơn bán chịu sắp phát hành, chỉ cộng dòng thu riêng khi có đủ hóa đơn trưởng thành liên kết sao kê và ứng viên vượt mốc không cộng ở kỳ kiểm tra. Nếu thiếu bằng chứng, giao diện ghi phần này chưa được tính.

Sao lưu: `python -m agent1_service.workspace.recovery backup DATA/agent1.db BACKUP/agent1.db --key-file KEYS/encryption.key`. Khôi phục: đổi lệnh thành `restore BACKUP/agent1.db NEW/agent1.db` với cùng khóa. Đích phải mới. Chép khóa mã hóa và khóa bí danh vào kho khóa riêng; cấp token mới khi phục hồi. So hash kế hoạch cũ trên bản khôi phục trước khi dùng. Thống nhất hạn lưu trước pilot: giữ snapshot/model/forecast đang được dẫn chứng tới khi nghiệm thu; có thể xóa toàn bộ DN theo thủ tục quản trị đã có sau khi hết hạn. Xóa bản ghi làm việc không xóa lịch sử hoặc các bản sao; người giữ bản sao chịu trách nhiệm xóa bản sao/khóa đến hạn.

Tác vụ ≥10.000 hóa đơn hoặc bật DL dòng tiền chạy trong tiến trình tách biệt, chỉ nhận khi có ≥3 GiB RAM trống. Không giới hạn tổng thời gian huấn luyện; biến cũ `AGENT1_TRAIN_SECONDS` không còn được sử dụng. Giữ giới hạn 2.048 MiB RSS (`AGENT1_TRAIN_MIB`) và cập nhật tiến độ mỗi 15 giây; ép chạy tách biệt cho tác vụ nhỏ bằng `AGENT1_ISOLATE_TRAINING=1`. Có thể xóa phiên bản chưa dùng qua trang kiểm định; phiên bản đang phục vụ hoặc đã có kế hoạch tham chiếu bị khóa.
