# Rà soát tiếp T1 — 14/11/2026

Phát hiện thêm **4 vấn đề**: 1 P1, 2 P2, 1 P3. Cả bốn có test tái hiện; riêng lỗi thời điểm còn được kiểm bằng model GBM thật và catalog production. Đây là phần bổ sung cho [9 vấn đề ở lượt trước](../t1_ui_20261114/REVIEW_T1_UI.md), không đếm lại chúng.

Review working tree hiện tại. Không sửa mã sản phẩm, ghi đè catalog/trọng số frozen hay chạy trên kho doanh nghiệp thật. Các phép fit bổ sung chạy trong bộ nhớ trên dữ liệu tự tạo; API test dùng kho tạm.

## 1. [P1] Giữ ngày T1 cũ làm lọt tham số nhánh phụ học sau ngày forecast

**Vị trí:** `agent1/adaptive/methods.py:19,129–135,221–245,285`; `agent1_service/workspace/api.py:823–825`; `agent1/adaptive/operating.py:183–193`; `agent1/adaptive/risk.py:114–130`.

`train_update()` cố ý giữ `asof` của incumbent khi T1 không đổi. Nhưng wrapper `methods.train()` vẫn học lại risk tại ngày cập nhật; callback API vẫn gắn operating vừa học tại ngày đó. Hai nhánh phụ không lưu mốc sẵn sàng riêng. Khi forecast, guard chỉ kiểm `bundle.asof` và `partial.fitted_through`, nên một bundle chứa T1 cũ và operating/risk mới vẫn vượt qua kiểm tra cho ngày dự báo cũ.

**Tái hiện không dùng model giả:** `probe_operating_dates.py` tạo sao kê tuần nối số dư hợp lệ, được `validate_dataset()` chấp nhận, rồi chạy `methods.train`, `select_operating`, `forecast` thật:

- Cập nhật ngày **30/12/2025**, T1 thiếu coverage quá khứ nên giữ global sẵn sàng **01/07/2024**.
- Gắn operating GBM học đến **30/12/2025**, giống callback của API.
- Forecast tại **31/12/2024**, bật operating: vẫn được chấp nhận.
- Với cùng dữ liệu và ngày dự báo, thay operating bằng GBM chỉ học đến **31/12/2024** làm tiền thu theo tuần khác tới **1.638.603,53 đồng**. Đây là chênh lệch giữa hai kết quả của ca thử, không phải số đo sai số với thực tế doanh nghiệp.

Số đầy đủ ở [operating_dates_evidence.json](operating_dates_evidence.json). Test `test_kept_t1_must_not_authorize_future_auxiliary_parameters` kiểm nhánh risk bằng spy của trainer: risk được fit 31/12/2025 nhưng vẫn trả xác suất 99% trong forecast 01/01/2025.

**Ảnh hưởng:** có thể làm dự báo hồi cứu, rủi ro và số tiền T6 sử dụng tham số chưa tồn tại tại ngày chốt. T1 nguyên trạng không tự bị học từ tương lai trong ca này; lỗ hổng nằm ở bundle kết hợp nhiều thành phần. Luồng dự báo từ ngày cập nhật trở đi không gặp vi phạm thời điểm này.

**Hướng sửa:** ghi ngày học/ngày sẵn sàng cho từng thành phần T1, partial, risk, operating; kiểm thành phần thực sự được dùng theo cutoff. Khi ngày chốt cũ hơn nhánh phụ, chọn đúng phiên bản cũ, loại nhánh đó với trạng thái rõ ràng hoặc từ chối yêu cầu. Giữ đúng ý nghĩa ngày của T1 cũ, tránh giải quyết bằng cách ghi đè toàn bộ ngày bundle.

## 2. [P2] Forecast và hash đầu vào T1 có thể thuộc hai snapshot khác nhau

**Vị trí:** `agent1_service/workspace/api.py:1207–1212,1235–1236,1300–1308`.

API lấy `data = current(firm)` cho phép tính tiền, sau đó đọc lại active dataset qua `current_t1_data()` để tính `t1_input_dataset_hash`. Các lần đọc không nằm trong một snapshot giao dịch. Import có thể commit giữa chúng.

Test `test_forecast_input_hash_must_describe_its_frozen_data` chèn đúng một import giữa hai lần đọc, không cần thread hoặc thời gian ngẫu nhiên:

- Snapshot A có dư nợ **100**.
- Import B ghi nhận khoản thu **40**, dư nợ còn **60**.
- Forecast và replay vẫn dùng A, trả `outstanding=100`; `t1_input_dataset_hash` lại là hash của B.

**Ảnh hưởng:** chứng từ đầu vào được khai báo cho T1 không khớp snapshot thực sự tính dự báo; `stale_model` cũng có thể đối chiếu nhầm dữ liệu. Trong ca thử này, lịch tiền và replay cùng dùng A; không kết luận lịch tiền đã bị trộn giao dịch A/B.

**Hướng sửa:** chụp một bộ dữ liệu, coverage và phiên bản phục vụ nhất quán trong giao dịch đọc ngắn; tính hash, forecast và replay từ bản chụp đó. Không cần giữ khóa suốt thời gian mô phỏng. Cần tính đến cả worker/CLI bên ngoài mutex của API.

## 3. [P2] Chọn nguyên trạng global nhưng ghi lại ngày học tham số T1

**Vị trí:** `agent1/adaptive/t1_update.py:390–410,438`; `agent1_service/workspace/t1_lifecycle.py:249`.

Selector cho phép chọn global hoặc incumbent nguyên trạng. Nhánh học lại T1 chỉ chạy khi `selected['family']` có giá trị và `alpha > 0`. Dù vậy, khi historical audit đạt, `t1_parameter_asof` luôn bị gán bằng T. Challenger cũng gán mốc này theo `proposal.asof`, tức ngày tạo bundle.

Test `test_selected_frozen_global_must_keep_its_parameter_fit_date` dùng các global thật của fixture, không chạy cấu hình continuation nào. Selector chọn `global_*`, qua audit, chỉ fit lại partial. Global được khai báo sẵn sàng **01/01/2020**, nhưng metadata tham số T1 thành **31/12/2025**.

**Ảnh hưởng:** provenance nói T1 được học mới trong khi chỉ có quyết định chọn/partial thay đổi. Điểm này khác lỗi UI dùng `asof` cho nhãn “dữ liệu đến” ở lượt trước: bản thân trường chuyên ghi mốc tham số của backend cũng sai trong nhánh chọn global.

**Hướng sửa:** giữ mốc khai báo của global khi chọn global; giữ mốc tham số incumbent khi chọn incumbent; chỉ nâng ngày tham số T1 khi thực sự continuation/refit. Ngày chọn sẵn sàng của bundle và ngày fit partial vẫn có thể là T. Mang riêng các mốc này qua proposal, shadow và metadata.

## 4. [P3] Báo cáo được tạo trước khi gắn thông tin chu kỳ hiện tại

**Vị trí:** `agent1_service/workspace/t1_lifecycle.py:234,283–292`; `agent1/adaptive/training_report.py:33–60`.

`save_training_report()` chạy trước khi `bundle['update_period']` được cập nhật. Chu kỳ đầu báo cáo ghi `null`; nếu incumbent đã có chu kỳ trước, `deepcopy(incumbent)` có thể mang chu kỳ cũ vào báo cáo mới. Artifact sau đó được lưu với chu kỳ hiện tại nên hai nguồn bằng chứng không khớp nhau.

Test `test_encrypted_report_must_include_the_period_committed_with_its_model` spy đúng dữ liệu truyền vào bộ tạo báo cáo: `training.update_period=None`, trong khi artifact được commit có `current_asof=2025-01-01`.

Kiểm thêm schema báo cáo: thiếu `update_asof`, `t1_parameter_asof`, `partial_version`, `adapter_version`, `serving_manifest`, dù bundle có các trường này. [report_fields_evidence.json](report_fields_evidence.json) ghi danh sách trường thực tế. Không cần xuất trọng số hoặc dữ liệu thô để bổ sung định danh thành phần.

**Hướng sửa:** hoàn thiện metadata chu kỳ trước khi tạo báo cáo; đưa định danh T1/partial và các ngày liên quan vào schema báo cáo. Đảm bảo báo cáo cùng phiên bản với artifact/decision đã commit. Việc mã hóa báo cáo không phải nguyên nhân lỗi.

## Kiểm chứng trong lượt này

| Nhóm | Kết quả |
|---|---:|
| Bộ có sẵn: T1 periodic, cash adapter, landmark/refit, T1 explanations, T10 bundle, T6 acceptance | **85 passed**, 0 skipped |
| Bốn test mới | **4 failed** tại assertion hành vi đúng mong đợi |
| Năm test tái hiện từ lượt trước | **5 failed**, xác nhận lỗi vẫn còn |
| Case operating dùng model GBM thật, catalog production và ledger tự tạo hợp lệ | Forecast hồi cứu sai điều kiện thời điểm được chấp nhận |

Không có lỗi setup trong 9 probe thất bại. Test mới nằm trong `outputs/review/`, không thêm vào bộ test sản phẩm. JUnit hiện hành: [existing_tests.xml](existing_tests.xml) và [review_probes.xml](review_probes.xml). `regressions.xml` là lần chạy ban đầu khi mới có ba probe; dùng `review_probes.xml` cho kết quả đầy đủ.

Đã kiểm thêm serialize/deepcopy của partial thực tế và việc phát lại bundle. Không coi thay đổi bytes khi pickle lại booster là lỗi mới: T10 hiện kiểm bytes artifact đã lưu và có xử lý riêng cho aliasing của estimator. Không phát hiện hồi quy mới ở các test SHAP, tiền/phân phối và replay đã chạy. Lượt này không chụp lại UI; các lỗi metadata trên có ảnh hưởng tới độ đúng của thông tin UI/báo cáo.

## Chạy lại

Từ gốc workspace, PowerShell:

```powershell
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='2'
$env:PYTHONPATH='agent1;agent1/tests/adaptive'
.\.venv\Scripts\python.exe -m pytest agent1/outputs/review/t1_deep_20261114/test_deep_review.py agent1/outputs/review/t1_ui_20261114/test_review_regressions.py -q --tb=short
.\.venv\Scripts\python.exe agent1/outputs/review/t1_deep_20261114/probe_operating_dates.py
```

Test pytest hiện được kỳ vọng thất bại vì sản phẩm chưa sửa. Probe operating ghi lại JSON trong thư mục review; không ghi kho doanh nghiệp. Các file sản phẩm được đối chiếu có SHA-256 trong [source_manifest.json](source_manifest.json).

Ưu tiên xử lý lỗi thời điểm của bundle cùng hai lỗi nhãn/partial đã nêu ở lượt trước; sau đó sửa snapshot/hash và provenance, rồi đồng bộ báo cáo/UI.
