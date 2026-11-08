# Hợp nhất phiên local về cổng 8765 — 07/11/2026

Phiên dùng chính hiện tại là **http://127.0.0.1:8765/**. Công việc chuẩn bị/sao lưu bắt đầu ngày 06/11; giữ thư mục bằng chứng `.runtime/unified_8765_20261106/` để liên tục lịch sử. Các chức năng cùng máy chủ, database và phạm vi doanh nghiệp:

| Chức năng | Đường dẫn |
| --- | --- |
| Hồ sơ/hàng đợi hiện có | `/` |
| Nhập CSV/Excel, xem lỗi và chuẩn hóa | `/data-import` |
| Chọn/đánh giá/kích hoạt/chấm ML | `/company-ml` |
| Phiếu rà, căn cứ và thời gian | `/ml-reviews` |

Menu bên trái trang hồ sơ có liên kết trực tiếp đến ba chức năng mới. Không cần đổi cổng để chuyển màn hình.

## Dữ liệu được giữ

Database chính tiếp tục là `.runtime/review/sprint14_demo.sqlite3`, nguồn `data/feature_model_sync_20261017` và báo cáo `reports/case_management_20261018`. Giữ nguyên **1.146 hồ sơ** và danh mục **5 doanh nghiệp** của phiên 8765.

Chuyển 11 bảng `company_ml_*`/`ml_review_*` từ phiên đang dùng 8853 vào phần ML còn trống của database chính: **70 dòng SQLite**, gồm hai snapshot 30 giao dịch C001/C002, 5 phiên bản model, hai binding hiện hành, nhãn hiện có, 9 bản nhập, lịch sử/lượt chấm và gói **12 phiếu chưa rà**. C001 giữ IF phiên bản đang dùng tại thời điểm chuyển; C002 giữ ECOD. Giữ nguyên byte artifact, revision, hash chain và các dữ kiện gói đã khóa; không huấn luyện hoặc tự kích hoạt lại.

Các bảng hồ sơ, giao dịch, danh mục và thông báo của demo nhập trước đây không được chép đè lên phiên chính. Database thử sửa nhãn và thử CSV/Excel tiếp tục nằm riêng trên đĩa; không nhập các kết quả mô phỏng của chúng vào dữ liệu dùng chính.

Nguồn danh mục dùng cho các lần nhập mới là nguồn của phiên 8765. Tập ML được chuyển vẫn giữ metadata nguồn và feature snapshot khi nhập trước đó. Việc nhập mới vẫn yêu cầu xem trước và xác nhận thay thế đầy đủ, đồng thời kiểm tương thích model như trước.

## Khởi động và danh tính local

```powershell
python -B start_review.py
python -B start_review.py --stop
```

Launcher tự đọc `.runtime/review/server_8765.config.json`, lưu đúng đường dẫn nguồn/database, executable Python và đường dẫn thư viện tương thích artifact. Khởi chạy lại khi đúng profile đang phục vụ trả về `Already running`, không tạo writer thứ hai. Dừng cần instance_id khớp bản ghi của launcher.

Phiên này có `qa=true` và `demo_ml_manager=true`: danh tính **MÔ PHỎNG · Quản lý phiên local** được tạo tại máy chủ, giới hạn vào danh sách doanh nghiệp hiện có. Không nhận vai trò hoặc công ty do browser/header tự khai. CLI từ chối `--demo-ml-manager` khi không có `--qa`. Đây là cấu hình demo trên loopback; chưa bổ sung đăng nhập/tài khoản thực tế hoặc thay chính sách rà hai cấp.

Các tiến trình 8853/8854, 8859/8860 và 8861/8862 đã dừng sau kiểm tra. Bản gốc và các database QA vẫn tồn tại trong các thư mục `.runtime` tương ứng. Kiểm kê sau cùng trong khoảng cổng local 8700–8900 chỉ còn ứng dụng ở **8765**.

## Cách chuyển và đối chiếu

`sme_fraud/ml_workspace_merge.py` lập kế hoạch có checksum/danh mục dòng cho 11 bảng. Chỉ chép vào đích trống, hoặc nhận diện bản đã chuyển giống hệt để không tạo trùng. Đích đã có dữ liệu khác, sai schema/công ty/bộ dữ liệu hoặc dữ liệu đổi sau khi lập kế hoạch đều dừng trước ghi. Chép trong một transaction SQLite và đối chiếu toàn bộ kết quả trước commit; lỗi giữa chừng rollback các bảng ML.

Đã ghép thử trên bản sao trước, kiểm tra model còn tương thích và danh mục nhập C001/C002 dùng được. Khi chuyển thật, dừng writer, tạo snapshot cuối, chép ML vào database chính rồi khởi động bằng profile mới. Sau đó đối chiếu lại:

- **27 bảng** hồ sơ/quản lý cũ: số dòng và hash nội dung giữ nguyên.
- **11 bảng** ML/phiếu rà: khớp hoàn toàn nguồn 8853 tại thời điểm chuyển; nguồn 8853 giữ nguyên.
- **16 tệp** nguồn/báo cáo và feedback: hash giữ nguyên, không chấm lại luật hoặc viết lại hồ sơ.

Lưu ý `sqlite_sequence` tăng tương ứng khi chép các sự kiện có số thứ tự; đây là metadata cần thiết cho lần ghi tiếp theo.

## Kiểm thử

- **211 test Python liên quan đạt**, gồm 10 test mới về copy không mất dữ liệu, lặp an toàn, xung đột/stale plan, rollback giữa chừng, phạm vi, danh tính QA và profile khởi động.
- **146 kiểm tra JavaScript đạt**; 92 test entry của Node và số kiểm tra chi tiết bên trong các script cũ.
- **30/30 kiểm tra Playwright đạt** ngay trên 8765: menu cùng origin, queue trên 1.000 hồ sơ, chọn tệp được mở cho 5 doanh nghiệp, tải mẫu, preview một giao dịch từ nguồn chính tạo **194 feature**, giữ khóa lưu khi chưa xác nhận, model C001/C002 vẫn chấm được, CatBoost tiếp tục bị khóa khi thiếu nhãn, đủ 12 phiếu với dữ kiện mù, viewport desktop/mobile và không lỗi JavaScript. Chỉ gửi POST xem trước, không xác nhận thay thế dữ liệu hoặc ghi kết quả người rà trong bài này.

Nhật ký và bằng chứng tại `.runtime/unified_8765_20261106/`: `regression.log`, `ui_tests.log`, `preflight_result.json`, `cutover_state.json`, `cutover_plan.json`, `cutover_result.json`, `browser_1793984471892/results.json` và các ảnh desktop/mobile cùng thư mục. Script kiểm tra sau chuyển: `cutover.py verify`. Đã chạy lại launcher để xác nhận dùng phiên đang chạy.

## Sao lưu và khôi phục

Snapshot SQLite trước chuyển cuối cùng: `cutover_before_8765.sqlite3` và `cutover_before_8853.sqlite3`; bản ghi launcher cũ ở `previous_server_record.json`. Bản gốc của 8853 cũng được giữ tại `.runtime/data_import_demo_20261104/review.sqlite3`.

Muốn quay về trước chuyển phải dừng writer, sao lưu thêm trạng thái mới, rồi dùng SQLite backup để khôi phục snapshot phù hợp; giữ nguyên nguồn/báo cáo đã ràng buộc và kiểm lại binding. Không chép đè file SQLite đang mở hoặc dùng snapshot cũ khi đã có công việc mới chưa được lưu riêng. Chưa thực hiện thao tác khôi phục trên phiên dùng chính.
