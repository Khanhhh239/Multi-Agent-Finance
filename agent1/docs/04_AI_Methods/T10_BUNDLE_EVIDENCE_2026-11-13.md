# Bước 7 — T10 giải thích bundle T1 + adapter partial + T6 đã lưu

**Bắt đầu: 13/11/2026; cập nhật: 14/11/2026.** Đây là hợp đồng mã phục vụ và kiểm thử chức
năng, chưa phải nghiệm thu độ chính xác dải tiền, doanh nghiệp thật hoặc tác
động của hoạt động thu nợ. Phần T10 trong tài liệu T0–T9–T10 ngày 11/11 đã
được đồng bộ theo hợp đồng này.

## Bốn đích giải thích

| Câu hỏi | Đích và bằng chứng engine | Giới hạn |
|---|---|---|
| Vì sao xác suất tất toán như vậy? | Grouped SHAP của T1 đang phục vụ, đích `payment_probability_4w`; baseline + đóng góp nhóm cộng khớp xác suất 4 tuần | Không tự trở thành SHAP tiền thu hoặc hiệu quả liên hệ |
| Vì sao dự thu tiền vào tuần này? | `receipt_explanation.weeks`: dư nợ đầu kỳ vọng, xác suất/hazard tất toán, tiền từ tất toán, tiền partial, dư nợ cuối kỳ vọng và các trạng thái partial | Đây là phân rã đầu ra T1 + adapter; chưa tính attribution feature lên tiền |
| Vì sao số dư kỳ vọng thấp? | `cash_decomposition`: số dư đầu + lũy kế thu − lũy kế chi; truy xuống toàn bộ hóa đơn, khách, T5, hoạt động | Cộng khớp kỳ vọng, không phải phân rã P10 hoặc xác suất thiếu tiền |
| Nếu khách trả chậm hoặc dời chi? | T6 phát lại baseline rồi kịch bản với cùng bundle, dữ liệu, budget và nguồn ngẫu nhiên; so kỳ vọng, P10/P50/P90, xác suất thiếu từng tuần/cả kỳ | Độ nhạy theo giả định trong mô hình; chưa chứng minh tác động can thiệp |

SHAP giữ sáu nhóm landmark của phiên bản đang dùng. Schema 18 feature gồm
giá trị/điều khoản, tuổi hóa đơn, trạng thái thu, lịch sử khách, lịch sử doanh
nghiệp và công nợ hiện tại. Reference và các đóng góp được lưu khi tạo forecast;
T10 mở lại các giá trị đã lưu. Giới hạn 0–30 hóa đơn chỉ giới hạn chi phí SHAP,
không cắt bằng chứng tiền hoặc danh mục T6.

## Adapter xuất số có cấu trúc ngay khi tính kỳ vọng

`expected_cash_components` là một phép tính chung cho tiền kỳ vọng và bằng
chứng T10; `expected_cash` chỉ đọc trường `cash` của kết quả đó.

Với tuần `w`, trạng thái `s` là chưa/đã có tiền thu; `D_s` là **dư nợ kỳ vọng
vô điều kiện** trong trạng thái đó. T1 cho hazard tất toán `h_w`; profile partial
cho `q_cell = P(partial | chưa tất toán tuần này, trạng thái)` và phân phối tỷ
lệ `R_cell` trên dư nợ còn lại:

```text
E[thu tất toán tuần w] = Σ_s D_s × h_w
E[thu partial tuần w] = Σ_s D_s × (1 − h_w) × q_cell × E[R_cell]
E[thu tuần w] = E[thu tất toán] + E[thu partial]
E[dư nợ cuối tuần] = E[dư nợ đầu tuần] − E[thu tuần]
```

Không nhân xác suất tất toán thêm lần nữa vào các số tiền trên. Dư nợ đầu đã
trừ tiền thật và giảm trừ phi tiền tệ hợp lệ; không cộng các khoản đó thành thu
tương lai. Tail có thể đã thu partial nhưng vẫn chưa tất toán.

Ví dụ kiểm thử riêng: dư nợ còn **60 triệu**, xác suất tất toán tuần 1 là
0,2; nếu chưa tất toán, q = 0,6 và tỷ lệ partial trung bình 0,4. Engine tính
**12 triệu tất toán + 11,52 triệu partial = 23,52 triệu dự thu**, còn kỳ vọng
36,48 triệu. Đây là fixture kiểm công thức, không phải số đo doanh nghiệp.
Giao diện chỉ định dạng các trường số engine đã lưu.

`t10.partial_profile` giữ đủ 6 ô theo quá hạn (≤0, 1–90, ≥91 ngày) và trạng
thái đã có tiền; mỗi ô có q, toàn bộ atom/trọng số tỷ lệ, trung bình tỷ lệ do
engine tính, số tuần, tuần hiệu dụng và số tuần partial nếu artifact có ghi.
Giữ `fitted_through`, hash prior, strength và label contract. Thiếu số hỗ trợ
thì hiển thị “Chưa ghi”, không tự gán bằng chứng local hoặc độ tin cậy.

## Forecast, artifact và phiên bản bất biến

Khi `/v1/predict` hoàn tất kiểm phân rã và hiệu chỉnh dải (nếu đủ điều kiện),
ghi **cùng giao dịch**:

- `company_predictions`: toàn bộ kết quả, SHAP, reference, adapter evidence,
  giả định, đích, phiên bản và trạng thái dải.
- `company_forecast_replays`: snapshot dữ liệu theo ngày chốt, artifact thực
  tế của bundle (cả model/anchor/partial/hoạt động), hash artifact, tham số T6,
  hash forecast và hash snapshot. Không chỉ giữ tên model đang active.
- `company_forecast_engines`: bản source Python chính xác một lần theo hash
  source của package engine và phiên bản thư viện/Python cần dùng.
- `company_forecast_index`: chỉ mục lịch sử.

`t10.identity` lưu phiên bản/hash T1, adapter, partial và T6. Manifest nguồn
học/ready date của bundle được giữ riêng trong `t10.provenance`. Artifact
pickle và source archive là bản ghi nội bộ mã hóa, không nhận từ HTTP và
không được gửi ra endpoint giải thích.

GET forecast/giải thích và export **không đọc model/dataset đang active**.
Đổi active hoặc thêm giao dịch thật không sửa lời giải thích của forecast cũ.
Kịch bản kiểm hash forecast/snapshot/artifact, phiên bản engine/runtime và
phát lại baseline khớp tiền, median, phân vị và xác suất trước khi so.

Nếu source/runtime đã đổi, kịch bản trả 409 thay vì âm thầm dùng engine mới.
Source và phiên bản runtime cũ vẫn được giữ để phục hồi môi trường đúng bản;
chưa có bộ tự triển khai nhiều môi trường engine lịch sử. Đọc các bằng chứng
đã lưu vẫn hoạt động. Forecast trước hợp đồng này thiếu snapshot cần lập mới,
không tự tái dựng bằng phiên bản hôm nay.

## Kịch bản đầy đủ và nguồn ngẫu nhiên chung

```http
GET /v1/forecasts/{id}/explanations
POST /v1/forecasts/{id}/scenarios
{"customer_id":"A","customer_delay_weeks":2,
 "expense_id":"RENT","expense_delay_weeks":1}
GET /v1/forecasts/{id}/scenarios
GET /v1/forecasts/{id}/scenarios/{scenario_id}
```

Chậm thu thêm 0–13 tuần; `customer_id=null` áp toàn bộ khách. Dời chi thêm
0–52 tuần và phải chỉ rõ khoản chi đã thuộc forecast. Tất cả thay đổi tương
đối so với forecast đang mở, kể cả forecast đó đã có giả định dời thu/chi.
Không sửa dữ liệu kế toán, không train và không tra catalog/model hiện tại.

Mỗi lần chạy lấy lại cùng seed, số đường, thứ tự hóa đơn, nguồn rút tất toán,
partial, tỷ lệ và residual hoạt động. Dời thu áp sau khi sinh cả chuỗi tiền;
không chia danh mục thành hai nhóm trước khi rút RNG. Cách chia cũ đã được
gỡ vì có thể đổi cả lần rút của những hóa đơn không bị tác động.

So theo từng tuần: kỳ vọng, P10/P50/P90, xác suất dưới cash floor và chênh
lệch từng đại lượng. Xác suất có ít nhất một tuần thiếu tiền lấy sự kiện trên
**cùng đường danh mục**; không nhân các xác suất tuần hoặc cộng P10 hóa đơn.
Lưu sai số chuẩn MC của chênh lệch xác suất cả kỳ từ các cặp chỉ báo.

Thu bị dời ra ngoài kỳ vẫn là dư nợ kỳ vọng. Chi bị dời ra ngoài kỳ được giữ
trong `outflows_pushed_beyond_horizon`, không coi là xóa nghĩa vụ. T5 và phần
hoạt động vẫn đi qua T6, gồm quy tắc top-up chi biến đổi tránh cộng hai lần.

Kịch bản hiển thị **phân vị mô phỏng thô** của baseline/kịch bản và ghi riêng
trạng thái dải đã phục vụ. Không áp dải đã nới theo sai số ngoài mẫu cho kịch
bản chưa kiểm chứng. Kỳ vọng, median và raw quantile của forecast gốc giữ
riêng. Protocol dải tăng thành `settlement-partial-paths-v2`; calibration không
gộp các forecast khác adapter, partial hoặc T6.

## Giao diện, export và code đã gỡ

Workspace có bảng bằng chứng theo hóa đơn/tuần, trạng thái partial, phân phối
tỷ lệ/mức hỗ trợ, tải JSON đã lưu, form kịch bản chạy T6 và mở lại các kịch bản đã lưu. Excel thêm
`Bằng chứng partial theo tuần`, `Profile partial và hỗ trợ`, `Phiên bản T10`.

Đã xóa `_timing_comparison`, bộ sinh ba đường chỉ dịch kỳ vọng, phần UI và
hai sheet `So sánh thời điểm` / `Kịch bản từng tuần` tương ứng. Gỡ cả bộ so sánh kỳ vọng dựa trên biến nhớ `baselineForecast` ở UI; so sánh hiện dùng snapshot. Xóa mô tả cũ
“400 đường, mỗi dư nợ chỉ rút một tuần thu”. Sửa các chỗ gọi và kiểm thử dùng
hợp đồng mới. Báo cáo/source snapshot frozen và pipeline research `/forecast`
còn bên gọi được giữ riêng; chúng không phải T10 của `/v1/predict`.

Không dùng LLM trong luồng này. Bảng và câu diễn đạt lấy trường số đã kiểm;
nếu thêm LLM sau này, LLM chỉ được diễn đạt các kết quả/bằng chứng đó. Luôn
phân biệt quan hệ dự báo với tác động can thiệp, phù hợp lưu ý về xác suất
quan sát/can thiệp trong [Janzing và cộng sự, 2020](https://proceedings.mlr.press/v108/janzing20a.html).

## Kiểm chứng

Các ca chính ở `tests/adaptive/test_t10_bundle.py`: cộng khớp adapter, hỗ trợ
partial, no-op chính xác, khách cụ thể/nhóm chung RNG, dời chi ra ngoài kỳ,
raw/calibrated, sai phiên bản/hash, active model/dataset đổi, grouped SHAP và
phát lại bundle global thật. Browser test mở bằng chứng và chạy kịch bản ở
desktop/mobile. Kết quả cuối và giới hạn được ghi trong thư mục
`outputs/implementation/t10_bundle_20261113/`.

Kết quả chốt **14/11/2026**: 401 ca Python đạt, 3 bỏ qua do thiếu Torch; 31
ca JavaScript đạt, Ruff E9/F không lỗi. Đây là kết quả hợp ca sau cùng từ
lượt chạy rộng và lượt chạy lại 150 ca bị ảnh hưởng, không phải full-suite
thứ hai. [Receipt và ví dụ JSON/Excel](../../outputs/implementation/t10_bundle_20261113/README.md)
ghi cả các lỗi ban đầu và giới hạn của fixture.
