# Đồng bộ điều kiện ML giữa web và backend — 05/11/2026

Đã sửa `/company-ml`: CatBoost chỉ mở khi kỳ đang chọn đủ điều kiện huấn luyện; nút chấm/giữ model bị khóa khi artifact không tương thích. Giao diện hiển thị số nhãn hợp lệ, số thiếu/biết muộn và lý do khóa. Không thay model đang dùng hoặc dữ liệu của demo C001/C002 đã khóa trước đó.

## Chính sách dùng chung

- `evaluation_partition` trong `sme_fraud/company_ml.py` được dùng bởi cả đánh giá thật và API kiểm tra điều kiện: ranh giới train trước calibration; tối thiểu 5 train, 2 calibration, 2 evaluation; không quá 20.000 dòng train.
- `catboost_training_readiness` được dùng bởi API kiểm tra và `evaluate`: đã cài CatBoost, mọi giao dịch trong kỳ train có nhãn đã xác minh, thời điểm biết nhãn **nhỏ hơn** cuối kỳ train, có cả lớp 0 và 1. Nhãn biết đúng tại ranh giới vẫn là biết muộn. Số nhãn tổng của doanh nghiệp không đủ để mở lựa chọn.
- Kiểm tra tương thích dùng chính `_artifact` đang được `score`/`keep` sử dụng: đúng công ty, schema/định dạng nguồn/cột, checksum, môi trường chạy và metadata đã cố định. Có model tương thích nhưng không có giao dịch ngoài kỳ train/calibration thì vẫn được giữ model, chỉ khóa chấm.
- Backend tiếp tục kiểm tra khi nhận POST, kể cả người gọi bỏ qua nút khóa. API kiểm tra điều kiện là chỉ đọc và vẫn kiểm phạm vi danh tính/doanh nghiệp; không cấp quyền ghi cho kế toán viên.

## API và giao diện

`GET /api/company-ml/readiness` nhận `scenario`, `company`, `train_end`, `calibration_end`, cùng `expected_revision` và `expected_active` để kiểm tra cấu hình của form. Trả lại revision/binding hiện hành và ba nhóm `evaluation`, `catboost`, `model` với trạng thái, số dòng và lý do.

Giao diện kiểm tra lại khi tải cấu hình, đổi kỳ, đổi công ty/bộ dữ liệu hoặc nhận kết quả cập nhật dữ liệu/nhãn/model. Khi đang gõ, lựa chọn/nút liên quan khóa ngay và yêu cầu kiểm tra được gộp sau 300 ms; sự kiện chọn xong kỳ kiểm tra ngay. Phản hồi cũ của kỳ/công ty/revision khác bị bỏ qua. Không tự đổi lựa chọn CatBoost sang thuật toán khác khi kỳ mới không đạt điều kiện.

Khi chưa kiểm tra được hoặc mất kết nối, nút huấn luyện/chấm/giữ được khóa và có thông báo để tải lại. Sau thao tác ghi thất bại, giao diện kiểm tra lại điều kiện bằng GET để tránh giữ trạng thái mở nút đã cũ; không tự gửi lại POST. Kỳ train lỗi chỉ ảnh hưởng đánh giá ứng viên; model đang dùng tương thích và có dữ liệu chấm vẫn chấm được. Các dòng trạng thái có `role=status` và `aria-busy` khi đang kiểm tra.

## Kiểm chứng

- **150 test Python liên quan đạt**, gồm 13 test service mới và một test API mới. Bao phủ thiếu nhãn, nhãn ngoài train, nhãn biết tại/sau ranh giới, một lớp, thiếu thư viện, kỳ lỗi, chưa có model/dữ liệu, khác định dạng, artifact hỏng, đổi môi trường, metadata bị sửa, không có giao dịch chấm, phạm vi công ty và xung đột revision/binding. Các bộ nhập dữ liệu, so sánh model, review, workflow, shadow và backup/restore cùng đạt.
- **127 kiểm tra JavaScript trong 11 bộ đạt**, gồm 9 trường hợp luồng mới: độ phủ nhãn theo kỳ, khóa ngay khi sửa kỳ, giữ lựa chọn, model không tương thích, không có dòng chấm, lỗi mạng và phục hồi, kiểm tra lại sau POST thất bại, phản hồi trễ, quyền chỉ xem. Các bộ tự báo số kiểm tra được cộng theo số ca bên trong thay vì chỉ đếm file.
- **29/29 kiểm tra Chrome bằng Playwright đạt** trên workspace mô phỏng riêng. C001 đủ 18/18 nhãn train thì mở CatBoost; đổi kỳ còn 8/9 vì một nhãn biết muộn thì khóa; quay lại kỳ hợp lệ thì thực sự huấn luyện CatBoost và giữ nguyên binding đang dùng. C002 chỉ có 1/18 nhãn và model khác định dạng thì khóa CatBoost/chấm/giữ, nhưng vẫn cho đánh giá một ứng viên hợp lệ khác. Đã kiểm tra POST chấm bị backend từ chối, lỗi mạng/tải lại, quyền chỉ xem và viewport 390 px không tràn trang.
- Đã khởi động lại demo nhập dữ liệu cũ tại `http://127.0.0.1:8853/company-ml` với API mới. C001/C002 vẫn đúng revision và binding đã ghi trong gói so sánh `run_02`; CatBoost bị khóa với 0/18 và 1/18 nhãn, model tương thích hiện hữu vẫn chấm được. Không train lại các model của gói này.

Nhật ký cục bộ:

- `.runtime/company_ml_readiness_tests.log`
- `.runtime/company_ml_readiness_regression.log`
- `.runtime/company_ml_readiness_js_tests.log`
- `.runtime/company_ml_readiness_e2e_1793853129743/results.json`, `incompatible_desktop.png`, `readiness_mobile.png`

## Thử các trạng thái trên demo riêng

Trong môi trường review/Company ML, thêm thư mục gốc và `tests` vào `PYTHONPATH`, chạy:

```powershell
python -B tests/company_ml_readiness_demo.py --port 8855
node tests/company_ml_readiness_e2e.js
```

`8855/company-ml` là kế toán trưởng QA; `8856/company-ml` là kế toán viên chỉ xem. Dữ liệu/database nằm riêng trong `.runtime/company_ml_readiness_demo_20261105`. C001 có đủ nhãn ở kỳ mặc định và một nhãn được biết muộn nếu chọn kỳ train kết thúc trước 12/01/2024 12:00; C002 có ít nhãn và model không tương thích. Toàn bộ danh tính/nhãn/kết quả test đều mô phỏng.

Máy chủ đang chạy từ mã cũ cần khởi động lại để có route mới. Giao diện mới sẽ khóa thao tác nếu không đọc được endpoint, tránh cho phép thao tác khi chưa xác định điều kiện.

Phạm vi lượt sửa này là đồng bộ UI/backend. Hai lỗi về thay thế tập nhãn khi bổ sung và nhận bằng chứng ngoài manifest đã nêu trong [biên bản rà](company_ml_review_20261105.md) vẫn là các việc riêng chưa được sửa ở lượt này.
