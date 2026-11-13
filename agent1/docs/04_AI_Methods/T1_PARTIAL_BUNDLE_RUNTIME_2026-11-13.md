# Runtime T1 + partial adapter → T6, phiên bản 2

Hợp đồng này thay phần adapter, lựa chọn model và T6 trong các quyết định trước.
T1 dự báo **tất toán bằng tiền**. Partial là thành phần học độc lập, được lưu và
chọn cùng T1 trong bundle doanh nghiệp `t1-partial-bundle-v2`.

## Dữ liệu và nhãn

`t1_data.landmarks` dựng trạng thái công nợ và 18 feature bằng dữ liệu biết tại
origin. Tiền có cả `payment_date` và `known_at`; cash-full là ngày thực thu đầu
tiên đủ claim, dùng các receipt đã biết trước label cutoff. Không dùng thứ tự
posting để chuyển event về một lần trả partial trước đó.

Điều chỉnh hợp lệ trước origin đi vào dư nợ. Thay đổi claim/khách, hủy, thay thế,
xóa nợ hoặc sửa/xóa tiền cũ làm mất tính so sánh của target cố định thì snapshot
bị loại; không tạo event thu tiền từ đóng nợ phi tiền mặt. Một sửa claim rồi
hoàn nguyên cũng không được coi là claim ổn định chỉ vì hai endpoint bằng nhau.

Phạm vi thanh toán nằm trong `payment_coverage`:

```json
{"start_date":"2025-01-01","end_date":"2025-03-31","known_at":"2025-03-31","complete":true}
```

Có thể giới hạn bằng `invoice_ids` hoặc `customer_ids`. Chỉ ghép những khoảng
đầy đủ đã biết trước label cutoff; dừng follow-up ngay ở ngày thiếu phạm vi
đầu tiên. Không có xác nhận thì follow-up bằng 0. Chỉ tuần đủ 7 ngày mới tạo
nhãn âm/dương. Validation/audit cần đủ 91 ngày cho mỗi khoản được chấm.

Chu kỳ nhận `payments_complete=true` lưu xác nhận có ngày thực ghi nhận trong
`company_payment_coverage`, cùng giao dịch với quyết định và artifact. Xác nhận
mới không chứng minh rằng phạm vi đó đã được biết ở các mốc fit quá khứ. Lịch
sử thiếu xác nhận tại các mốc cần thiết giữ G0/incumbent và chờ đủ bằng chứng.

## Adapter dùng chung

`cash_adapter.py` nhận PMF tất toán của mọi T1 hợp lệ, gồm G0, Neural, LightGBM,
XGBoost và các nhánh học tiếp. Với khoản còn nợ ở tuần k:

- `h = p[k] / sum(p[k:])`: xác suất tất toán có điều kiện từ T1.
- Xác suất partial là `(1-h) × q`; không trả là `(1-h) × (1-q)`.
- Tất toán thu toàn bộ dư nợ của đường; partial thu tỷ lệ trong (0,1) của dư nợ.

Nhánh partial học `q` và phân phối thực nghiệm có trọng số của tỷ lệ partial.
Tuần có tất toán không được đưa vào tập học partial. Có sáu nhóm: chưa/đã nhận
tiền và ba khoảng tuổi so với điều khoản. Chuyển nhóm sau lần partial đầu tiên,
kể cả hóa đơn chưa từng thu tại origin. Feature và giới hạn tuổi/điều khoản
giống nhau trong bảng validation và dữ liệu phục vụ.

Local dùng trọng số giảm theo thời gian, khử các tuần trùng invoice/end-date,
và điều chuẩn về prior global theo số mẫu hiệu dụng. `partial_prior_strength`
mặc định 30, được version hóa cùng policy; tối đa 256 quantile thực nghiệm cho
mỗi nhóm. Không có dữ liệu global/local cho một nhóm thì xác suất partial là 0.

`expected_cash` tính kỳ vọng từ đúng các chuyển trạng thái này; `sample_cash`
mô phỏng nhiều lần thu, giảm dư nợ sau mỗi lần, dừng khi tất toán. Tổng thu mỗi
đường không vượt dư nợ đầu kỳ. Dải và xác suất thiếu tiền T6 dùng các đường này.
Kịch bản chậm thu dịch cả dòng partial và dòng tất toán một lần.

## Catalog và contract global

Manifest mới: `outputs/t1/settlement_partial_catalog_v2_20261113/catalog.json`.
Loader kiểm contract `cash-calendar-full-settlement-v2`, schema, hash từng model,
replay, prior partial và ngày sẵn sàng. Có thể cấu hình bằng
`AGENT1_T1_GLOBAL_CATALOG`; đóng gói bằng `scripts/package_t1_global_catalog.py`.

Kiểm tra nguồn đã phát hiện catalog v1 còn giữ nhãn trước lần sửa cash calendar.
Không gán lại tên contract cho các trọng số đó. Catalog v2 dùng các artifact đã
sửa nhãn trong `aligned_cashcalendar_20261113`, giữ cấu hình ba họ và cấu trúc
G0 Neural 75%/customer 25% bằng các thành phần đã sửa nhãn. G0 nguyên bản nằm
nguyên trong catalog v1 và được ghi là `quarantined_pre_cash_calendar_target`;
không đưa vào tập T1 hợp lệ. Đây là migration contract, không phải bằng chứng
G0 mới hay adapter mới tốt hơn bản cũ.

Prior partial dùng riêng snapshot global trước 01/07/2024, không dùng local
của doanh nghiệp hoặc outcomes audit/test. Nguồn hiện vẫn là synthetic.
Artifact phiên bản trước không được tái kích hoạt như bundle v2; dự báo lịch
sử và nguồn frozen vẫn giữ để đối chiếu. Cần đánh giá lại pipeline khi đổi
catalog/adapter; điểm cũ không được kế thừa làm bằng chứng chất lượng v2.

## Chọn và lưu cả bundle

1. Fit ba họ T1 từ global gốc, cùng feature/snapshot/risk-row/trọng số/replay;
   LR và ngân sách riêng. Fit partial một lần từ quá khứ trước validation.
2. Tất cả T1, gồm incumbent nếu đã có ở origin, dùng **cùng partial đã fit**
   trên validation. Chọn bằng cash13, có guard IBS cho phân phối tất toán.
3. Khóa một cấu hình trước khi đọc outcomes audit. Audit so candidate T1 +
   partial với **T1 + partial thực tế của incumbent**. Không thử người thứ hai
   sau khi thấy audit; audit trượt không refit và không tạo challenger thay thế.
4. Audit đạt mới refit cả T1 theo cấu hình khóa và partial từ global trên cửa
   sổ local đến T. Ngày sẵn sàng của bundle là ngày quyết định, không bị đổi
   chỉ vì chạy một chu kỳ mà vẫn giữ nguyên incumbent.
5. Incumbent quá mới thì không chấm hồi cứu bằng một proxy G0. Giữ nguyên
   incumbent, fit cấu hình đã khóa thành challenger và lưu cặp dự báo thực sự
   tại origin: PMF, lịch tiền, hash từng partial, claim và danh sách hóa đơn.
   Sau 91 ngày, chấm một challenger FIFO bằng policy đã khóa và lịch tiền đã
   lưu. Thiếu coverage vẫn chờ; không tính lại bằng adapter mới.

Mã phiên bản bundle băm cả T1 và partial. Artifact tenant chứa hai thành phần
học riêng. Khi prospective audit đạt, kích hoạt đúng artifact đã được chấm,
không refit ngầm. Mốc ban đầu vẫn T−210/T−182 cho validation và T−91 cho audit;
730 ngày lịch sử, chu kỳ 28 ngày, origin cuối T−7. Các mốc là cấu hình khởi đầu.

## Dọn mã và kiểm định

Override partial theo cohort trong `adaptive.cash_history`, cột `override_*`/
`partial_override` trong dữ liệu production, và mô phỏng một lần thu toàn bộ
trong T6 đã bị bỏ. Bản sao `experiments/t1_compact/legacy_cash.py` cũng đã
xóa trong lượt hoàn thiện T6; thí nghiệm lịch sử đọc source snapshot frozen
qua `historical_workspace`, runtime không import phần đó.

Chi tiết nghiệm thu chuỗi tiền, kỳ vọng/P50/phân vị, manifest và phép chấm
doanh nghiệp mới ở [hợp đồng T6 cập nhật](T6_PARTIAL_PATHS_PERIODIC_2026-11-13.md).

Kiểm thử hành vi nằm ở `test_cash_adapter.py` và `test_t1_periodic.py`: kỳ vọng
so với Monte Carlo, nhiều lần thu, mở partial lần đầu, censoring, regularization,
cặp adapter riêng, serialization và chu kỳ prospective. Runner
`scripts/business/verify_t1_partial_bundle.py` đánh giá lại selector production
trên một doanh nghiệp synthetic có sẵn, với grid tính toán nhỏ cố định, ghi
`outputs/implementation/t1_partial_bundle_v2_20261113/F013_pipeline_audit.json`.
Đó là kiểm tra tích hợp trên dữ liệu đã từng xem; không phải holdout mới hoặc
nghiệm thu chất lượng doanh nghiệp thật. Không kích hoạt kho tenant hiện có.
