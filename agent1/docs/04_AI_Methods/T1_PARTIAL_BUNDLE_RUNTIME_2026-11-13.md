# T1 + partial: catalog global, học tiếp và chọn bundle

Hợp đồng Workspace đối chiếu 14/11/2026. Bundle doanh nghiệp là `t1-partial-bundle-v2`; nhãn `cash-calendar-full-settlement-v2`; adapter tiền `settlement-partial-cash-v2`; luật fit prior `partial-empirical-prior-v3`. T1 mô hình hóa **tất toán bằng tiền**; partial là thành phần học riêng được chọn và lưu cùng T1.

## Catalog và feature

[t1_catalog.py](../../agent1/adaptive/t1_catalog.py) nạp G0 dự phòng, global Neural/LightGBM/XGBoost và các nhánh học tiếp tương ứng. G0 giữ cấu trúc Neural 75% + customer 25% bằng các thành phần đúng nhãn tiền. Không có catalog ensemble local học từ đầu hoặc pool top-3 giữa các thuật toán local.

Manifest mặc định là `outputs/t1/settlement_partial_catalog_v3_20261114/catalog.json`, có thể cấu hình bằng `AGENT1_T1_GLOBAL_CATALOG`. Loader kiểm schema, đúng thứ tự 18 feature, contract, hash model/replay/prior và ngày sẵn sàng. Global gốc không bị sửa khi học local.

Schema `t1-landmark-18-v2` ở [landmark_features.py](../../agent1/adaptive/landmark_features.py) gồm sáu nhóm: giá trị/điều khoản, tuổi hóa đơn, trạng thái thu tiền, lịch sử khách, lịch sử doanh nghiệp và công nợ hiện tại. Không dùng latent truth, ngày trả tương lai hay bộ 64/93 feature của các prototype v6 cũ.

Catalog v3 giữ model/replay của v2 và thay riêng prior partial; catalog cha/hash được kiểm trước khi dùng incumbent tương thích. V2 có thể đọc cho serving/lịch sử nhưng không dùng prior đó khởi tạo lượt học mới. G0 trước sửa nhãn cash-calendar bị cách ly, không đổi tên contract để tái sử dụng trọng số sai target. Catalog nguồn hiện là synthetic; đổi prior/catalog cần đánh giá chất lượng riêng.

## Snapshot, outcome và coverage

[t1_data.py](../../agent1/adaptive/t1_data.py) dựng landmark và feature bằng dữ liệu biết tại origin. Receipt có cả ngày tiền thực thu và ngày biết; không kéo event về lần partial trước đó chỉ do thứ tự posting. Hóa đơn đóng do giảm trừ/xóa nợ khác hóa đơn trả đủ tiền.

Outcome kết thúc ở `min(label_end, origin + 91 ngày)`, độc lập ngày nhận bằng chứng. Receipt/chứng từ có ngày kinh tế trong cửa sổ được xét khi `known_at <= label_end`. Thay đổi claim/khách, hủy/thay thế, write-off hoặc sửa/xóa receipt làm target cố định không còn so sánh được thì loại snapshot; kiểm cả chuỗi điều chỉnh rồi hoàn nguyên. Thay đổi sau outcome horizon không loại mẫu trưởng thành chỉ vì xảy ra trước knowledge cutoff. Bổ sung nguồn mà không đổi claim/khách/tham chiếu không tự làm mất mẫu.

`payment_coverage` là xác nhận phạm vi người cung cấp dữ liệu đã kiểm:

```json
{"start_date":"2025-01-01","end_date":"2025-03-31","known_at":"2025-03-31","complete":true}
```

Có thể giới hạn `invoice_ids`/`customer_ids`. Chỉ ghép khoảng đầy đủ đã biết trước label cutoff; dừng follow-up ở ngày thiếu đầu tiên. Không xác nhận thì follow-up bằng 0. Chỉ tuần đủ 7 ngày tạo risk row/nhãn; snapshot theo dõi ngắn vẫn đóng góp tuần đủ, không gán âm cho tương lai. Validation/audit cần đủ 91 ngày cho mỗi khoản chấm.

`payments_complete=true` lưu xác nhận cùng ngày thực ghi nhận trong kho. Xác nhận mới không chứng minh đã biết coverage ở các ngày fit quá khứ; thiếu bằng chứng lịch sử giữ G0/incumbent và chờ nhãn.

## Adapter tất toán và thu một phần

Với PMF tất toán `p`, hazard tuần k là `h = p[k] / sum(p[k:])`. Khi còn dư nợ:

| Nhánh | Xác suất | Tiền thu |
|---|---|---|
| Tất toán | `h` | Toàn bộ dư nợ của đường |
| Partial | `(1-h) × q` | Tỷ lệ R trong (0,1) của dư nợ còn lại |
| Chưa trả | `(1-h) × (1-q)` | 0 |

[cash_adapter.py](../../agent1/adaptive/cash_adapter.py) fit q và phân phối thực nghiệm có trọng số của R. Tuần tất toán không vào tập partial. Có sáu ô: chưa/đã nhận tiền × ba nhóm tuổi so với hạn (≤0, 1–90, ≥91 ngày); partial lần đầu chuyển ngay sang trạng thái đã nhận tiền.

Local khử tuần trùng invoice/end-date, giảm trọng số theo thời gian và điều chuẩn về prior global theo số mẫu hiệu dụng. Strength mặc định 30, tối đa 256 quantile thực nghiệm mỗi ô. Không có dữ liệu cho ô thì q=0. Placeholder 50% của ô q=0 chỉ để lưu định dạng, không tham gia khối lượng tỷ lệ. Prior rỗng điều chuẩn incidence local về 0, phân phối tỷ lệ chỉ từ event thật.

`expected_cash_components`/`expected_cash` và `iter_cash_paths`/`sample_cash` dùng cùng chuyển trạng thái; thu nhiều lần, giảm dư nợ sau mỗi khoản, dừng sau tất toán. Tail vẫn có thể nhận partial. Profile/hash/fit date đi cùng T1 trong bundle; không override partial theo cohort ở production.

## Học tiếp và chọn cấu hình

| Policy mặc định | Giá trị |
|---|---|
| Chu kỳ / cửa sổ local tối đa | 28 / 730 ngày |
| Snapshot stride / origin học mới nhất | 28 ngày / T−7 |
| Half-life / replay | 180 ngày / 30% tổng trọng số |
| Risk row tối đa | 12.000 |
| Validation / audit | T−210, T−182 / T−91 |
| Mẫu tối thiểu | Fit 60 snapshot và 20 hóa đơn; validation/audit mỗi phần 20 snapshot |
| Guard | Gain cash13 ≥0,0001; IBS ≤ baseline ×1,02 +0,0001 |

Giá trị và grid riêng từng họ nằm trong [UpdatePolicy/GRIDS](../../agent1/adaptive/t1_update.py). Đây là cấu hình ban đầu có version, chưa chứng minh tối ưu cho mọi doanh nghiệp. Mỗi chu kỳ bắt đầu lại từ global gốc, không nối tiếp vô hạn phần dữ liệu mới.

1. Fit ba họ từ global trên cùng snapshot/risk/replay/trọng số; fit partial một lần bằng quá khứ trước validation.
2. Chấm tất cả T1 hợp lệ, kể cả incumbent đã sẵn sàng ở origin, trên cùng partial validation. Chọn bằng cash13 với guard IBS; alpha chỉ trộn với global cùng họ.
3. Khóa một cấu hình rồi mới đọc audit. So candidate T1 + partial với **bundle incumbent thực tế**, không thử người thứ hai sau khi thấy audit.
4. Audit đạt mới refit cấu hình đã khóa và partial từ global trên cửa sổ đến T. Audit trượt không refit hoặc tạo challenger thay thế để thử tiếp.
5. Nếu incumbent quá mới để audit hồi cứu hợp lệ, giữ incumbent và lưu challenger cùng cặp dự báo thực tại origin.

Định nghĩa cash13/IBS và giới hạn chấm nằm ở [metric kỹ thuật](../03_Evaluation/01_metric_ky_thuat.md).

## Challenger và audit ngoài mẫu

Challenger lưu artifact, policy/guard, PMF, lịch tiền, hash partial, claim và hóa đơn của cả hai bundle. Sau 91 ngày, chấm **một challenger FIFO** đã đủ coverage/outcome. Không tính lại lịch tiền bằng adapter mới; không chấm dự báo tạo hồi cứu sau origin như dự báo prospective. Incumbent đã thay thì cặp đối chiếu bị stale.

Promotion dùng đúng artifact đã chấm, không refit ngầm sau audit. `promotion_audit` giải thích phiên bản đang phục vụ; `candidate_update_audit` giải thích ứng viên chu kỳ mới. Giữ `prospective_audit_id` xuyên metadata/decision/report. API đọc bản cũ có thể khôi phục liên kết chứng cứ từ challenger khớp, không ghi đè artifact.

## Ngày, registry và giao dịch

| Mốc/định danh | Ý nghĩa |
|---|---|
| `update_asof` | Cutoff dữ liệu của chu kỳ |
| `asof` / ready date | Ngày lựa chọn bundle phục vụ sẵn sàng; giữ T1 không làm mới mốc này |
| `t1_parameter_asof` | Ngày tham số T1 thực sự được học; global giữ `available_asof`, incumbent giữ mốc cũ |
| `partial.fitted_through` | Mốc fit partial độc lập |
| Risk/operating `fitted_through`, `ready_on` | Hai mốc riêng để kiểm thành phần thực sự dùng khi forecast |
| `company_bundle_version` / `model_version` | ID registry / định danh tham số T1 + partial |

Thiếu ngày trong artifact cũ dùng cận trên bảo thủ theo contract, không lấy ngày ready làm ngày dữ liệu. `/v1/predict` chụp dataset, coverage và bundle trong cùng giao dịch đọc. Manifest/report/registry/decision cùng mang metadata chu kỳ đã hoàn thiện trước khi xuất báo cáo mã hóa.

Không xóa registry active hoặc được forecast tham chiếu. Guard tra provenance/replay cho forecast cũ thiếu ID; xóa phiên bản trong lúc mô phỏng khiến commit forecast bị chặn thay vì lưu tham chiếu hỏng.

`serving_mode` phản ánh tham số thực tế: `global_fallback`, `global_selected`, `company_adapted`, hoặc `saved_model` khi thiếu bằng chứng. Có registry riêng chưa đồng nghĩa đã học local; alpha local=0 vẫn là T1 global, còn partial học local có thể làm bundle thích nghi.

## API và cập nhật định kỳ

`POST /v1/training` và `POST /v1/t1/updates` dùng cùng chu kỳ, trả job 202; `GET /v1/t1/updates` và `GET /v1/workspace` trả metadata trạng thái/lịch. `force=true` không bỏ audit/guard. Trùng job bị chặn; dữ liệu/active đổi trong lúc train khiến CAS từ chối kích hoạt kết quả cũ.

`next_due`, `matures_on=origin+91 ngày`, trạng thái thiếu nhãn/coverage hoặc stale hiển thị riêng; trạng thái không gửi snapshot/artifact. Scheduler bên ngoài gọi `python -m agent1_service.jobs.t1_update`; code không tự cài scheduler. Chỉ khai `--payments-complete` khi đã xác nhận thực tế. API/worker/job dùng chung [methods.train](../../agent1/adaptive/methods.py), cập nhật risk/operating kể cả khi giữ T1; operating thiếu lịch sử hợp lệ bị bỏ khỏi bundle mới.

Qua audit backend tự kích hoạt phiên bản được chấp nhận; chọn bản đã lưu là thao tác quay lại. Không tự thay tenant khi đổi catalog/prior. Các giới hạn nghiệm thu và quy trình kiểm nằm ở [Evaluation](../03_Evaluation/03_cong_nghiem_thu.md).
