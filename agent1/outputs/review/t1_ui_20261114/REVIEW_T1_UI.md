# Rà soát pipeline T1 và Workspace UI — 14/11/2026

Có 9 vấn đề còn mở: 1 P1, 7 P2 và 1 P3. Năm ca đầu đã có test tái hiện thất bại theo hành vi đúng mong đợi. Bốn ca UI được đối chiếu mã và trình duyệt. Đây là review mã hiện có trong working tree, bao gồm các file đang sửa/chưa được Git theo dõi; không chỉ review bản HEAD.

Không sửa mã sản phẩm, trọng số, catalog hoặc kho doanh nghiệp. Các file trong thư mục này là báo cáo, test tái hiện và ảnh của dữ liệu kiểm thử cách ly.

## Phát hiện

### 1. [P1] Điều chỉnh công nợ rồi hoàn nguyên vẫn lọt vào target cố định

Vị trí: `agent1/adaptive/t1_data.py:99–115`.

`landmarks()` kiểm các phiên bản sửa có cùng `invoice_id` trong `record_history`, nhưng không kiểm đủ chứng từ điều chỉnh có ID riêng tham chiếu về hóa đơn gốc. Khi hóa đơn 1.100 có điều chỉnh −110, sau đó điều chỉnh +110 trong 91 ngày, số tiền hai đầu vẫn bằng nhau nên snapshot được giữ. Dữ liệu này đi qua `validate_dataset()` hợp lệ; sổ tại ngày giữa kỳ thực sự là 990.

Test `test_adjustment_and_reversal_must_invalidate_fixed_claim` trả 1 target thay vì loại snapshot. Hành vi trái ngay với comment trong hàm và contract target cố định. Các khoản từng đóng/mở lại hoặc thay đổi claim có thể vào train, validation và audit như một khoản nợ không đổi.

Hướng sửa: dựng lịch sử claim/định danh của cả chuỗi chứng từ trong cửa sổ target, bao gồm chứng từ điều chỉnh, hủy/thay thế và các phiên bản của chúng. Không chỉ so hai endpoint hoặc revision của ID gốc.

### 2. [P2] Sự kiện sau tuần 13 làm thay đổi tập audit đã đủ 91 ngày

Vị trí: `agent1/adaptive/t1_data.py:83`, `:107–115`, `:341`.

`score_audit_snapshot()` truyền ngày chấm hiện tại vào `landmarks()`. Hàm dựng `outcome` tại ngày đó, rồi so claim/khách với origin, trong khi follow-up được giới hạn 91 ngày. Vì vậy thay đổi khách/claim sau ngày 91 vẫn loại một khoản có nhãn 13 tuần hợp lệ.

Test: origin 01/01/2025; ngày 02/04 còn 1 target đủ nhãn; đổi khách ngày 01/05; chấm ngày 02/05 thì target biến mất. Chu kỳ 28 ngày có thể chấm challenger sau ngày 91, nên đây là nhánh vận hành thực tế. Tập audit có thể thay đổi chỉ vì chạy chấm muộn, gây thiên lệch loại mẫu hoặc tiếp tục chờ vì không đủ số khoản.

Hướng sửa: tách ngày kết thúc cửa sổ outcome `origin + 91` khỏi ngày biết dữ liệu dùng để tiếp nhận bằng chứng đến muộn. Kiểm sự kiện kinh tế trong cửa sổ cố định, đồng thời vẫn xử lý sửa sai hồi tố có ảnh hưởng đến cửa sổ đó.

### 3. [P2] Prior partial thêm tỷ lệ trả 50% không có bằng chứng với trọng số 30 mẫu

Vị trí: `agent1/adaptive/cash_adapter.py:143–151`.

Ngay khi `prior=None`, mã tạo `prior_values=[0.5]`, `prior_w=[1.0]`, sau đó cộng `prior_w * strength` vào phân phối tỷ lệ. Atom được mô tả là placeholder cũng được giữ khi một nhóm prior không có event partial bắt đầu nhận bằng chứng local. Nó trở thành hành vi tiền có xác suất dương.

Test chỉ có một lần partial bằng 1% dư nợ, prior rỗng: tỷ lệ partial trung bình thành **48,419%**; incidence là 1/31. Đây là vấn đề của tỷ lệ có điều kiện; không nhầm incidence với tỷ lệ tiền thu.

Đã dựng lại prior từ đúng prepared validation đang được script đóng gói sử dụng. Nhóm 1 chỉ có 4 partial week nhưng trọng số tại tỷ lệ 50% là khoảng **89,28%**. Vì script đóng gói gọi `fit_partial(..., prior=None)`, cơ chế này cũng tham gia prior global hiện tại. Số đo lưu ở `model_evidence.json`.

Hướng sửa: chỉ mang khối lượng tỷ lệ từ prior có bằng chứng partial, hoặc khai báo một hyperprior giả định rõ ràng và đánh giá riêng. Khi không có ratio evidence, placeholder cần có khối lượng dự báo bằng 0. Thay luật này cần catalog/adapter version và kiểm định lại; không ghi đè artifact frozen.

### 4. [P2] Điểm audit dẫn tới promotion bị ghi đè trong cùng chu kỳ

Vị trí: `agent1_service/workspace/t1_lifecycle.py:209–225`; `agent1/adaptive/t1_update.py:229–234`.

Sau khi prospective audit đạt, lifecycle gán kết quả vào `baseline['audit']`. Nó tiếp tục gọi trainer để tạo ứng viên mới; `train_update()` khởi tạo lại `audit`. Lifecycle chỉ khôi phục `promotion_status` và ID, không khôi phục bằng chứng promotion vào metadata phiên bản.

Test tái hiện: challenger thực sự được chấp nhận, điểm cash của challenger là 0 và vẫn còn trong bản ghi challenger; nhưng metadata active có `audit={'accepted': False}`. UI đọc `version.audit`, nên có thể vừa nói đã chọn qua audit vừa hiện “Chưa đủ nhãn” hoặc chỉ số của lần kiểm tra khác. Không mất toàn bộ bằng chứng trong kho; mất liên kết đúng trong báo cáo phiên bản.

Hướng sửa: lưu riêng `promotion_audit` và `candidate_update_audit`, đưa ID promotion và điểm tương ứng vào metadata/API/UI. Báo cáo quyết định phải lấy đúng audit làm căn cứ kích hoạt.

### 5. [P2] Có thể xóa phiên bản đã được dùng trong kế hoạch lưu

Vị trí: `agent1_service/workspace/api.py:893–905`, `:1246–1248`, `:1311–1325`.

Guard xóa so `forecast_index.model_version` với ID registry. Sau migration, `model_version` là `global:...`/`bundle:...`, còn ID registry được chuyển sang `company_bundle_version`. Forecast index không lưu trường sau.

Test tạo forecast bằng registry ID `old`, chuyển active sang `new`, rồi DELETE `old`: API trả **200 / deleted=true**, thay vì 409. Metadata và weights của registry cũ bị xóa dù UI hứa giữ phiên bản của kế hoạch đã lưu. Forecast/replay đã đóng băng vẫn còn; không kết luận rằng việc đọc forecast cũ chắc chắn bị hỏng. Tác hại đã xác nhận là mất phiên bản để truy vết và quay lại dùng.

Hướng sửa: lưu/check registry ID riêng trong index; xử lý tương thích forecast cũ từ payload `company_bundle_version` hoặc replay trước khi cho xóa.

### 6. [P2] Global dự phòng bị hiển thị thành mô hình riêng đã học cho doanh nghiệp

Vị trí: `agent1/adaptive/methods.py:127–128`, `:376`; `agent1_service/ui/workspace/app.js:2014–2015`.

Sau khi hàm đã cấp default bundle, điều kiện `if bundle` luôn đúng. Kết quả dùng global nguyên bản có provenance `source=global_catalog`, `local_adaptation=false` vẫn trả `mode=company_trained`; UI đổi thành **PHIÊN BẢN RIÊNG**. Đã kiểm bằng catalog thực tế và ảnh forecast desktop/mobile.

Hướng sửa: trả trạng thái phục vụ rõ global dự phòng, global được chọn hoặc bundle đã thích nghi; UI đọc trạng thái đó thay vì sự tồn tại của object bundle. Không cần đưa tên thuật toán vào luồng nghiệp vụ.

### 7. [P2] Hướng dẫn nói đổi phiên bản bằng tay trong khi backend tự kích hoạt

Vị trí: `agent1_service/ui/workspace/index.html:789–794`; `agent1_service/workspace/t1_lifecycle.py:331`.

FAQ ghi “Phiên bản mới không tự thay phiên bản cũ: bạn xem kết quả, chọn sử dụng”. Lifecycle luôn ghi pointer active cho chu kỳ đã hoàn tất; khi audit đạt, model mới tự phục vụ mà không cần bấm nút “Sử dụng phiên bản này”.

Hướng sửa phù hợp contract hiện hành: giải thích tự đổi khi đủ điều kiện kiểm định, chỉ rõ quyết định và phiên bản đang dùng; nút chọn phiên bản cũ là thao tác quay lại. Nếu muốn một cổng duyệt thủ công thì đó là thay đổi policy backend, không chỉ sửa câu chữ.

### 8. [P2] UI không hiện lịch cập nhật và hàng chờ challenger

Vị trí: `agent1_service/ui/workspace/app.js:420–490`, `:1301–1410`; API đã có ở `workspace/api.py:876`.

Trình duyệt chỉ lấy `/v1/workspace`, không gọi `/v1/t1/updates`. Kho có `next_due=2026-12-12` và 1 challenger pending nhưng trang kiểm định không hiện chúng. Người dùng không biết ngày bắt đầu đối chiếu, mốc đủ 91 ngày, lý do thiếu coverage, trạng thái stale/rejected/accepted hoặc lịch cập nhật tiếp theo. Có thể liên tục bấm kiểm định nhưng chỉ nhận `not_due`.

Bằng chứng DOM/network: `ui_result.json`, trường `lifecycle_api` có `requested_by_browser=false`, `due_date_visible=false`, `pending=1`.

Hướng sửa: đưa trạng thái lifecycle vào response workspace hoặc lấy API riêng; hiện ngày cập nhật tiếp, challenger chờ kiểm tra và lý do giữ model bằng ngôn ngữ nghiệp vụ.

### 9. [P3] Nhãn “dữ liệu đến” dùng ngày sẵn sàng model thay vì ngày dữ liệu của chu kỳ

Vị trí: `agent1_service/ui/workspace/app.js:1326–1329`.

UI dùng `version.asof`. Khi chu kỳ giữ G0/incumbent, trường này cố ý giữ ngày model sẵn sàng, còn ngày kiểm tra dữ liệu mới nằm ở `update_asof`. Ảnh kiểm thử có chu kỳ 14/11/2026 nhưng hiện **“dữ liệu đến 01-07-24”**. Đổi sang `update_asof` đơn thuần rồi gọi đó là ngày model đã học cũng không đúng.

Hướng sửa: tách ngày dữ liệu đã kiểm tra, ngày tham số được học và ngày model được chọn sẵn sàng; với kept-incumbent ghi rõ vẫn giữ tham số cũ.

## Kiểm chứng đã chạy

| Nhóm | Kết quả |
|---|---:|
| T1 periodic, cash adapter, landmark/refit, T1 explanations | 68 passed |
| Cash/ranking explanations, catalog, thời gian và báo cáo train, selection | 48 passed, 3 skipped |
| Company workspace, T10 bundle, T6 acceptance | 91 passed |
| Node UI: T1 explanations, T6 cash, Portal connect | 57 passed |
| Test tái hiện mới trong thư mục review | 5 failed như dự kiến, 0 errors |
| Chromium: 6 trang × 1500px/390px, thêm mở forecast đã lưu | Không có pageerror hoặc tràn ngang toàn trang trong ca kiểm tra |

Tổng bộ có sẵn đã chạy: **207 Python passed + 57 Node passed; 3 skipped**. Test bổ sung thất bại là bằng chứng lỗi còn mở, không phải xác nhận đã sửa. Chúng nằm trong `outputs/review/`, không thêm vào bộ test sản phẩm.

Ảnh chính: `ui_training_1500.png`, `ui_training_390.png`, `ui_saved_forecast_1500.png`, `ui_saved_forecast_390.png`. Có thêm ảnh sáu trang desktop/mobile. Các bảng rộng dùng vùng cuộn nội bộ; kết quả không tràn ngang toàn trang không có nghĩa mọi cột cùng hiện trên mobile.

## Cách tái hiện

Tại thư mục gốc repository, PowerShell:

```powershell
$env:PYTHONUTF8='1'
$env:OMP_NUM_THREADS='2'
$env:PYTHONPATH='agent1;agent1/tests/adaptive'
.\.venv\Scripts\python.exe -m pytest agent1/outputs/review/t1_ui_20261114/test_review_regressions.py -q --tb=short
.\.venv\Scripts\python.exe agent1/outputs/review/t1_ui_20261114/audit_ui.py
```

Script trình duyệt dùng TestClient và kho tạm; không kết nối Portal hoặc kho doanh nghiệp đang chạy. Chrome phải có tại đường dẫn đã dùng trong các test hiện có.

## Phạm vi và giới hạn

Đã đọc và đối chiếu luồng snapshot/knowledge-date, 18 feature, nhãn cash-full, coverage/censoring, risk-row/replay, continuation Neural/LightGBM/XGBoost, validation/audit, challenger, registry, forecast T1→partial→T6, SHAP và các màn Workspace. Catalog v2 thực tế tải và dự báo được. Bộ kiểm thử hiện có xác nhận nhiều guard quan trọng như không gán âm cho tuần chưa đủ quan sát, không sửa global khi học tiếp, hash artifact và snapshot dự báo/giải thích.

Review này không chứng minh hết mọi lỗi. Không huấn luyện lại catalog global, không thay artifact frozen, không chạy cập nhật trên dữ liệu doanh nghiệp thật, không kiểm lại toàn bộ Portal/T9 ngoài các test được liệt kê. Các số đo chất lượng cũ và test synthetic không chứng nhận hiệu quả dự báo trên SME thật; `pilot_ready=false` vẫn phù hợp phạm vi hiện tại.

Thứ tự xử lý đề xuất: sửa 1–3 và kiểm định lại nhãn/adapter; sửa 4–5 để giữ bằng chứng và vòng đời artifact; sau đó đồng bộ 6–9 để UI phản ánh đúng quyết định phục vụ.
