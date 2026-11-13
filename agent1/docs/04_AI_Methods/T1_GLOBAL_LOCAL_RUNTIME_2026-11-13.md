# T1 hiện tại: global → local và cập nhật theo chu kỳ

> Phần adapter, catalog, lựa chọn bundle và T6 bên dưới đã được thay bởi
> [runtime T1 + partial v2](T1_PARTIAL_BUNDLE_RUNTIME_2026-11-13.md).
> Tài liệu này giữ mô tả phiên bản triển khai trước đó.

Yêu cầu mới nhất thay phần T1 của bản chốt T1–T6–T10 trước đó: **bỏ ensemble học từ đầu bằng local/Workspace khỏi T1 phục vụ**. Không còn chọn RF, ExtraTrees, HistGB, Logistic, Spline hoặc các Neural local từ đầu trong luồng train mới.

## Các model được dùng

- G0 global hiện tại: Neural 75% + customer 25%, giữ làm mốc dự phòng.
- Neural, LightGBM, XGBoost global chưa học tiếp.
- Ba nhánh bắt đầu từ chính global tương ứng và học tiếp bằng dữ liệu doanh nghiệp.
- Alpha trộn với global của chính họ được chọn bằng validation. Không tạo pool top-3 giữa các thuật toán local.

Gói model nằm ở `outputs/t1/global_local_catalog_v1_20261113/catalog.json`. Có thể sao chép cả thư mục sang máy doanh nghiệp và đặt `AGENT1_T1_GLOBAL_CATALOG` trỏ đến manifest. Loader kiểm schema 18 feature, hash metadata/model lồng nhau, replay và ngày sẵn sàng. Global gốc không bị sửa trong quá trình học local.

Gói này xuất từ các artifact nghiên cứu đã có, không phải một lần train global mới. Nguồn hiện là synthetic; global còn giữ contract nhãn nguồn lịch sử, trong khi builder local dùng tiền đã biết theo cash calendar. Không suy kết quả kiểm phần mềm thành chất lượng đã kiểm định trên doanh nghiệp thật.

## Lịch cập nhật mặc định

| Tham số | Giá trị ban đầu |
|---|---|
| Chu kỳ xem xét | 28 ngày; lưu `next_due` trong kho từng doanh nghiệp |
| Lịch sử local | Cửa sổ trượt tối đa 730 ngày trước từng mốc fit/refit |
| Snapshot học | Bước 28 ngày, neo chính xác ở ngày cách label cutoff 7 ngày |
| Trọng số thời gian | Half-life 180 ngày; chuẩn hóa đóng góp theo origin |
| Dữ liệu học | Toàn bộ snapshot đủ điều kiện; tối đa 12.000 dòng risk đã khai triển |
| Replay | 30% tổng khối lượng trọng số |
| Validation | Hai origin T−210 và T−182, chỉ dùng nhãn đã biết trước audit |
| Audit lịch sử | Origin T−91, nhãn đã biết đến T |
| Final refit | Từ global gốc, dữ liệu trong cửa sổ gần nhất đến T; origin mới nhất T−7 |

Đây là cấu hình vận hành có thể thay bằng policy đã version hóa; chưa chứng minh đây là cửa sổ tối ưu cho mọi doanh nghiệp. Tăng/giảm ngân sách cần đánh giá riêng. Không giữ lịch fit cứng T−329.

**Không chỉ lấy phần phát sinh từ lần train trước để nối tiếp vô hạn.** Mỗi chu kỳ khởi tạo lại từ global và dựng lại cửa sổ local gần đây. Cách này tránh cộng lặp nhiều lần cùng lịch sử, vẫn giữ thông tin mùa vụ/hành vi cũ có trọng số giảm. State lưu mốc kỳ trước, kỳ này, khoảng quan sát mới, nguồn dữ liệu và phiên bản đang phục vụ.

## Nhãn gần đây và dữ liệu chưa đủ 13 tuần

Builder chụp feature tại đúng origin, tách ngày tiền thực thu khỏi ngày biết phân bổ. Receipt có ngày tiền trước origin nhưng được nhận diện muộn không trở thành nhãn tiền tương lai. Thay đổi claim/khách, hủy và các ca không còn cùng khoản nợ được loại khỏi target cố định; không coi giảm trừ là thu tiền.

Trong likelihood theo tuần, chỉ tạo risk row cho **tuần đã quan sát đủ** và hóa đơn còn trong risk set. Snapshot mới chỉ có 7/35/63 ngày theo dõi vẫn đóng góp các tuần tương ứng. Tuần chưa quan sát, kể cả tuần cuối mới thấy event nhưng chưa quan sát đủ cả khoảng tuần, được để lại cho chu kỳ sau; không gán thành âm hoặc chỉ lấy riêng event dương.

Validation/audit cash13 vẫn cần đủ 91 ngày. Dữ liệu ít có thể dùng để học một số tuần nhưng chưa đủ để quyết định đổi model dự báo 13 tuần; khi đó giữ model đang dùng/G0 và ghi rõ lý do.

## Chọn model và ngăn đánh giá nhìn trước

1. Fit cả ba họ từ global trên cùng bảng risk/replay. Mỗi họ có LR/budget riêng, grid cố định trong mã và được lưu trong trace.
2. Chấm tất cả global và bản học tiếp trên cùng census validation. Tiêu chí chính là `cash13 = 0,5 × (tổng lỗi thu tuyệt đối theo tuần + trung bình lỗi thu lũy kế tuyệt đối) / tổng dư nợ`. IBS có trọng số dư nợ là guard.
3. Chọn một ứng viên bằng validation. Audit không thử tiếp ứng viên khác để tìm người thắng.
4. Chỉ chấm incumbent trực tiếp trên một origin nếu phiên bản/việc lựa chọn incumbent đã tồn tại trước origin đó. Incumbent được tạo sau origin không được dùng để backtest ngược.
5. Nếu audit hợp lệ và ứng viên giảm cash ít nhất 0,0001, đồng thời IBS không vượt `baseline ×1,02 +0,0001`, refit cấu hình đã khóa và lưu model được chọn. Các ngưỡng này là cấu hình tham chiếu, chưa phải chứng nhận mức cải thiện kinh doanh.
6. Nếu incumbent quá mới để audit lịch sử, giữ incumbent. Ứng viên có bằng chứng lịch sử so với G0 được lưu làm challenger; chưa được thay incumbent chỉ nhờ thắng G0.

## Audit bằng dự báo đã lưu trước khi biết kết quả

Mỗi challenger lưu model đã đóng băng và cặp dự báo challenger/incumbent tại ngày tạo, gồm PMF tất toán, lịch tiền từ adapter, invoice IDs, dư nợ/claim và hash snapshot. Các bản ghi này nằm trong kho mã hóa của đúng doanh nghiệp; API trạng thái chỉ trả metadata/tổng hợp.

Chu kỳ sau, khi origin đã đủ 91 ngày và người dùng/feed xác nhận thanh toán đầy đủ, hệ thống chấm bằng kết quả đã biết lúc đó. Không tính lại dự báo cũ bằng profile partial mới. Hai model được chấm trên cùng các khoản vẫn đủ điều kiện.

- Mỗi chu kỳ chỉ xét **một challenger đủ nhãn theo thứ tự FIFO**, không chọn người có audit tốt nhất trong cả hàng chờ.
- Dùng policy/guard đã lưu lúc tạo challenger, không đổi ngưỡng sau khi biết outcomes.
- Challenger phải được so với đúng phiên bản incumbent mà nó đã dự báo cùng. Incumbent đã thay thì bản so sánh đó bị đánh dấu stale.
- Forecast tạo hồi cứu sau origin không được coi là prospective để kích hoạt model.
- Khi được chấp nhận, dùng chính artifact challenger đã chấm. Không âm thầm refit nó bằng dữ liệu mới rồi gọi artifact mới là đã được chấm.
- Sau khi thay model, tạo tiếp challenger mới theo chu kỳ. Quyết định chỉ sẵn sàng tại ngày chấm, không ghi lùi ngày sẵn sàng về ngày fit cũ.

Vì vậy, **tạo ứng viên mỗi 28 ngày không có nghĩa cứ 28 ngày chắc chắn đổi model**. Model mới phải có đủ bằng chứng; giữ model hiện tại là một kết quả bình thường của pipeline.

## API và job định kỳ

`POST /v1/training` và `POST /v1/t1/updates` dùng cùng chu kỳ, nhận:

```json
{"asof":"2026-11-13","payments_complete":true,"force":false}
```

Trả job 202; kết quả job lưu quyết định, model đang dùng và `next_due`. Chu kỳ chưa đến hạn không học lại. `force=true` cho phép yêu cầu kiểm tra lại, nhưng không bỏ qua guard/audit. Trùng tác vụ đang chạy bị từ chối. Import/kích hoạt model thay đổi trong lúc train khiến CAS từ chối kích hoạt kết quả cũ.

`GET /v1/t1/updates` trả state, nhật ký và trạng thái challenger; không trả artifact hoặc các dự báo riêng từng hóa đơn dùng audit. Forecast chỉ suy luận từ bundle đã chọn/G0, không tự fit T1 khi xem dự báo. Phiên bản local cũ không còn được chọn lại; record cũ vẫn giữ để đọc forecast lịch sử.

Từ gốc repository, đặt `PYTHONPATH` trỏ tới thư mục `agent1`, rồi có thể gọi job bằng scheduler của doanh nghiệp:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'agent1'
.\.venv\Scripts\python.exe -m agent1_service.jobs.t1_update --firm SME --state 'DUONG_DAN_KHO_DU_LIEU' --payments-complete
```

Job đọc cùng kho/khóa mã hóa với dịch vụ, không cần web server đang chạy. Có `--catalog`, `--interval-days`, `--lookback-days`, `--cutoff`, `--force`. Có thể gọi hằng ngày; state ngăn học trùng trước `next_due`. Chỉ khai `--payments-complete` khi feed/người vận hành thực sự xác nhận dữ liệu tới cutoff. Code không tự cài tác vụ Windows hoặc tự xác nhận dữ liệu chưa kiểm tra.

## Những phần cũ đã bỏ khỏi mã phục vụ

- `Method`, `DistributionEnsemble`, catalog local và train/pool top-3 cũ trong `adaptive/methods.py`.
- SHAP theo giao diện T1 năm feature lúc phát hành và bộ sinh lý do nghiệp vụ cũ; phục vụ dùng grouped SHAP của landmark đang dự báo.
- Model customer được fit riêng/ngầm để tạo xác suất xếp hạng. Xác suất ranking có dùng thì lấy đúng active T1 và có provenance tương ứng.
- Đường override research allowlist của API dự báo mới. Cấu hình gói global bằng manifest thay cho env research cũ.

Mã model/nguồn đã đo trong các thư mục output frozen không bị ghi đè. `experiments/t1_compact/historical_workspace.py` chỉ là adapter đọc snapshot để chạy kiểm thử/đối chiếu lịch sử; mã phục vụ không import nó. Đây không phải một bản catalog local mới còn được chọn trong sản phẩm.

## Giới hạn cần đọc đúng

Đợt sửa này là triển khai và kiểm thử T1 theo yêu cầu, không phải test mới chứng minh selector thắng trên mọi doanh nghiệp. T6 vẫn dùng contract tiền và engine hiện có; mô phỏng partial paths/correlation/calibration đầy đủ trong quyết định T1–T6–T10 là công việc riêng. Kiểm thử kỹ thuật và smoke synthetic không thay đánh giá trên doanh nghiệp mới chưa dùng để thiết kế pipeline.
