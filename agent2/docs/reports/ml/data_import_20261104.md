# Nhập CSV/Excel theo doanh nghiệp — 04/11/2026

**Cập nhật 07/11:** màn hình dùng chính đã chuyển về **http://127.0.0.1:8765/data-import**, dùng chung phiên với hàng đợi, chọn ML và phiếu rà. Chạy `python -B start_review.py` để mở lại đúng cấu hình. Phần mô tả các cổng 8853/8854 phía dưới là lịch sử kiểm thử. [Biên bản hợp nhất](../app/unified_local_20261107.md).

Đã thêm màn hình `/data-import`, truy cập từ bước 1 của `/company-ml`. Luồng: chọn doanh nghiệp → chọn tệp → kiểm tra → xem dữ liệu chuẩn hóa/feature và cảnh báo → xác nhận thay thế dữ liệu → chuyển sang chọn ML đúng doanh nghiệp, đúng bộ dữ liệu.

## Hành vi

- CSV UTF-8/BOM hoặc Windows-1258; dấu phẩy, chấm phẩy hoặc tab. Excel `.xlsx` có một sheet. Mẫu CSV được tải ngay trên giao diện. Giới hạn 10 MB, 10.000 giao dịch, 80 cột.
- Tên cột theo mẫu; cột thiếu/trùng/không hỗ trợ được báo rõ. Mã giao dịch không trùng trong tệp. Mã nhân viên, người duyệt, NCC, khách hàng phải thuộc doanh nghiệp và có trong danh mục tại thời điểm giao dịch.
- Kiểm tra các ô bắt buộc, số nguyên VND, cờ 0/1, thời gian và thứ tự tạo ≤ duyệt ≤ ghi sổ. Giờ không ghi múi giờ được hiểu là Việt Nam; có lựa chọn ISO hoặc DD/MM/YYYY. Giữ nguyên mã dạng chuỗi và số 0 đầu; Excel dùng ô số cho mã/tài khoản bị chặn, yêu cầu đối chiếu lại nguồn.
- Mỗi lỗi có dòng, cột, lý do và cách sửa. Có lỗi thì không có token lưu. Không tự bỏ giao dịch lỗi để lưu phần còn lại. Xem tối đa 200 lỗi đầu, 10 giao dịch chuẩn hóa đầu; báo số dòng rỗng, khoảng trắng và ô tùy chọn thiếu.
- Dữ liệu hợp lệ được chạy qua `build_features`, tạo đủ **194 feature** theo hợp đồng hiện hành. Model/scaler chưa được học tại bước nhập. Bộ tạo feature chỉ dùng lịch sử giao dịch trước thời điểm chấm và danh mục đã quan sát.
- Bản xem trước nằm tạm trong bộ nhớ, hết hạn sau 20 phút, giới hạn 8 bản/server và chỉ giữ bản mới nhất của mỗi người dùng/doanh nghiệp; không ghi tập dữ liệu ML trước xác nhận. Token ràng buộc người dùng, doanh nghiệp, bộ dữ liệu, revision, master hash, feature contract và model đang dùng. Máy chủ khởi động lại thì cần kiểm tra tệp lại.
- Lưu nguyên tử trong SQLite: tập ML chuẩn hóa, matrix, bản nhập gốc đã chuẩn hóa và lịch sử hash chain. Có kiểm tra xung đột revision/model và thay đổi danh mục. Không sửa file nguồn kết nối hoặc hàng đợi rà soát.
- Model binding và artifact cũ giữ nguyên. Nguồn nhập dùng định dạng riêng `company-transaction-upload-v1`; nếu model từ nguồn kết nối cũ không tương thích thì giao diện giải thích và yêu cầu đánh giá/kích hoạt ứng viên mới. Những lần nhập cùng định dạng còn tương thích dùng được model cố định.
- Bổ sung nhãn đã rà bằng `/api/company-ml/labels-update` khi đang dùng dữ liệu nhập; không thay giao dịch/feature bằng nguồn kết nối. Nhãn vẫn được xác thực người rà, thời điểm, căn cứ và cờ verified. CatBoost vẫn yêu cầu nhãn train phù hợp.
- Quyền ghi: kế toán trưởng/giám đốc trong phạm vi công ty. Xem, CSRF, origin, holdout 005 và danh tính máy chủ tiếp tục theo cơ chế Company ML hiện hành.

## Giới hạn cần biết khi nhập

Đây là **thay thế toàn bộ tập ML của một doanh nghiệp**, chưa có nối thêm từng lô hoặc sửa trực tiếp từng ô trên web. Người dùng cần nhập đủ lịch sử để các feature lịch sử có ý nghĩa. Bản nhập không chứa nhãn; nhãn cũ không tự được giữ khi thay thế, cần tải lại nhãn đã rà.

Phiên bản này lấy danh mục doanh nghiệp/nhân viên/NCC/khách hàng và lịch nghỉ từ nguồn đã kết nối. Chưa có màn hình nhập master, lịch sử quan hệ/chấm công/đổi ngân hàng/tạm ứng hoặc dòng bút toán. Giao diện nêu rõ các khoảng thiếu này trước lưu: feature phụ thuộc có thể bằng 0 và không xác nhận không có rủi ro. Hồ sơ/hóa đơn thiếu thời điểm quan sát giữ mask chưa biết; các khoản tiền không có mask cần khai rõ thay vì tự điền 0.

Chỉ hỗ trợ tên cột và loại giao dịch theo mẫu; chưa tự ánh xạ các định dạng ERP tùy ý. `.xls`, `.xlsm`, công thức/lỗi Excel, workbook nhiều sheet, tệp nén vượt giới hạn hoặc XML không an toàn đều bị chặn. Đọc XLSX bằng openpyxl read-only, đóng workbook sau đọc theo [tài liệu chính thức](https://openpyxl.readthedocs.io/en/stable/optimized.html), dùng defusedxml và giới hạn kích thước giải nén.

## Chạy thử

Cài `requirements-data-import.txt` vào cùng môi trường review/Company ML. Chạy server review mới để có route nhập dữ liệu; server đang chạy từ trước cần khởi động lại. Danh tính thật vẫn do `identity_provider` cung cấp, chưa bổ sung hệ thống đăng nhập mới.

Demo riêng, dữ liệu và danh tính mô phỏng:

```powershell
python -B tests/data_import_demo.py --port 8853
```

- `http://127.0.0.1:8853/data-import`: kế toán trưởng giả lập, C001/C002.
- `http://127.0.0.1:8854/data-import`: kế toán viên giả lập, chỉ xem C001.
- Tệp mẫu CSV, XLSX và CSV lỗi: `.runtime/data_import_demo_20261104/SIMULATED_*`.
- Database riêng, không thay demo ML cũ cổng 8851/8852 hoặc dữ liệu vận hành.

Kiểm thử trình duyệt bằng `node tests/data_import_e2e.js` (Playwright và Chrome cục bộ). Lần đối chiếu đã đạt **39/39 kiểm tra**: lỗi không lưu, tải mẫu, preview không ghi DB, xác nhận lưu, thay đổi tệp/tùy chọn/công ty làm mất hiệu lực preview, C001 CSV → Isolation Forest, C002 XLSX → ECOD, đánh giá/kích hoạt/chấm/reload, nhập lại giữ artifact/model/điểm, bổ sung nhãn giữ nguyên dữ liệu nhập, phân quyền và màn hình di động không tràn trang. Đây là kiểm thử chức năng với dữ liệu mô phỏng, chưa phải đánh giá chất lượng phát hiện trên dữ liệu doanh nghiệp thực.

Kiểm thử hồi quy cuối: **125 test Python đạt** (17 test nhập dữ liệu/API mới, Company ML, review, phân quyền, workflow, feature contract, shadow scoring và backup/restore); **118 kiểm tra JavaScript trong 11 bộ đạt**, gồm hai kiểm tra escaping mới cho nội dung tệp nhập. Lệnh Python: `python -B -m unittest test_data_import test_company_ml test_company_ml_web test_review test_review_roles test_review_workflow test_feature_model_sync test_shadow_scoring test_review_backup -q`. Lệnh JavaScript: `node --test tests/*test.js`. Nhật ký cục bộ: `.runtime/data_import_final_tests.log`, `.runtime/data_import_js_tests.log`. Các bộ JavaScript tự báo đếm riêng được cộng theo số kiểm tra bên trong, thay vì chỉ đếm một file như một test.

Bằng chứng cục bộ mới nhất: `.runtime/data_import_e2e_1793804245988/results.json`, `errors_desktop.png`, `preview_desktop.png`, `preview_mobile.png`. Bản xem trước tạm không được đưa vào backup; bản nhập đã lưu và ML artifact ở SQLite nên được backup cùng database.
