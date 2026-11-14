# Fit và chấm riêng theo doanh nghiệp — CR-013

Ngày 11/11/2026, spec 2.1. **Đã thực hiện phần fit/persist/inference được giao; R2 tổng thể vẫn PARTIAL** vì bridge luật canonical và benchmark E1–E2 còn riêng. Không tự mở active model/queue, R3 hoặc production.

## Thay đổi

- `method_jobs.py`: CLI/job fit và score riêng, auth trước mở DB/config; fit cần `model.fit` + `data.import`, đọc/chấm chỉ cần quyền đọc. Scope được kiểm lại trước công bố và trả kết quả.
- `method_store.py` + `method_storage.sql`: SQLite mới riêng có application_id/schema version; job/idempotency, artifact BLOB/manifest, audit. Artifact/audit không UPDATE/DELETE; publish artifact + succeeded + audit atomic. Score mở kho model read-only; không có DB/model thì unavailable, không tạo file hoặc fit ngầm.
- `method_preprocess.py`: strict hoặc median_flags được khai báo/lưu theo artifact. Median, scaler và model chỉ học train; reference chỉ tạo reference scores. All-null training columns bị loại có lý do, không lấp 0 hoặc học lại từ reference/test. Dòng thiếu toàn bộ cột còn dùng không có điểm giả.
- `method_adapters.py`: artifact format company-method-artifact/1.0.0, lưu full FeatureContract, preprocess/learned params/hash, payload/model/reference versions, runtime/Python/platform/code, source/window/job bindings. Chỉ load khi đúng tenant/DN/contract/versions; legacy và contract cùng chiều nhưng khác thứ tự vẫn bị chặn trước unpickle.
- `auth.py`: thêm permission backend `model.fit`, không tự cấp theo role; giữ nguyên quyền đọc/verify. Lõi luật, ML estimators, thống kê, graph và R1 feature kernel không đổi.

## Thời gian và source

History/reference được replay riêng từ snapshot bất biến tại cuối mỗi kỳ, rồi lọc cả event-time và known-time trong khoảng đầu bao gồm/cuối không bao gồm. Các phiên bản giao dịch được biết sau history_end không thay train version; không trùng transaction ID giữa hai tập. Reference kết thúc trước evaluation_start.

Backtest là đánh giá hồi cứu dùng nguồn trước kỳ, không giả artifact được triển khai trong quá khứ. Prospective kiểm cả thời điểm tạo/hoàn tất và deadline công bố; job vượt kỳ không công bố artifact. Job-start và model-ready time được ghi riêng, không dùng thời điểm bắt đầu fit làm thời điểm model đã sẵn sàng.

## Chứng minh bằng demo và test

- Demo C001 dùng Isolation Forest, C002 dùng ECOD. Cùng ID H/R/T ở hai DN nhưng snapshot/artifact/job riêng. Mỗi DN train 10, reference 5, chấm được 5/5 giao dịch mới. Fit và score chạy bằng các tiến trình Python khác nhau; score đọc DB bằng tài khoản chỉ có data.import, không mang model ở bộ nhớ từ fit.
- Full input contract là 33 cột; transformed model input order/width, kept/dropped columns và learned medians ghi trong từng manifest. Không nhập lại model/vector legacy. Dữ liệu gốc/missing mask không bị sửa.
- Kiểm retry sau restart không fit lại; 10 concurrent request chỉ một claim; config khác cùng key conflict; scope sai không đọc model DN khác; thiếu/corrupt/incompatible model không load/fit fallback; strict thiếu dữ liệu làm job failed; median chỉ học train; nguồn muộn không thay train; publish/audit rollback cùng nhau; thu hồi quyền không công bố model.
- Kiểm CLI fit/score ở process riêng và từ chối thiếu quyền trước khi tạo DB/output; score store read-only. Reference/preprocess không fit theo batch test; các kiểm spy cấm mọi fit trong inference vẫn chạy.
- **30 focused tests pass** trên source cuối: [JSON](focused_tests.json), [log](focused_tests.log), gồm 17 ca mới về job/missing policy và 13 ca normalization. Bộ kiểm auth 31 ca cũng đã chạy trong [auth_focused_tests.json](auth_focused_tests.json). **557 tests hồi quy pass**, 0 skip/failure/error, 235,979 giây: [JSON](native_tests.json), [log](native_tests.log). [Parity](parity_report.json): 5 phương pháp số max_abs_error=0, native luật/hit/graph vẫn khớp.
- Khi bổ sung validation config, test phát hiện local variable `re` che module regex. Đã đổi thành tên đầy đủ reference_end, giữ [log lỗi](config_validation_failure.log) và [JSON](config_validation_failure.json); lỗi dừng trước fit, không điều chỉnh expected/tolerance hoặc bỏ test để xanh.

Demo đầu giữ tại `demo/`; demo sau source cuối giữ tại `demo_final/`. `initial_method_jobs.py` giữ code job tương ứng demo đầu. Chỉ nguồn mô phỏng, không đo precision/recall/accuracy. `minimum_history=5` là điều kiện kỹ thuật thử, không chốt D-03 sản xuất.

## Giới hạn và trạng thái

Kho/job local đã bền vững qua restart, nhưng chưa có scheduler/lease recovery, UI chọn/duyệt active hoặc Portal identity bridge. Job crash/revoked có thể còn running; không tự giành quyền/refit hoặc phát hành artifact. Không chọn latest/active model ngầm; caller chỉ định artifact ID đúng DN.

Bridge canonical sang toàn bộ luật cũ và benchmark E1–E2 chưa làm trong phạm vi này; thiếu nhãn thật không được báo accuracy. D-03/D-04/D-09 và triển khai dữ liệu thật vẫn mở. R1 technical gate trước được giữ, không tự ghi DONE hoặc chốt quyết định nghiệp vụ. Bản báo cáo/output CR-012 trước được lưu `prior_*` khi cập nhật overview R2.

Hướng dẫn: [COMPANY_MODEL_JOBS.md](../../../../agent2/docs/COMPANY_MODEL_JOBS.md); demo `agent2/scripts/demo_company_models.py`. Lệnh đã chạy, version/checksum, kết quả từng ca và artifact manifest được lưu trong thư mục này.
