# Chạy app và phát triển

Chạy lệnh từ thư mục gốc `D:\agent22`. Hướng dẫn này dùng bản demo RR09/ML v4 đã chuẩn bị; [dữ liệu benchmark cũ](development/synthetic_data.md) có mục đích riêng.

## Python và thư viện

Môi trường của máy này có Python tại:

```powershell
$projectPython = 'C:\Users\Technical Support\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

Script demo hiện có tự thêm thư viện cục bộ trong `.runtime/site-packages`. Máy mới cần môi trường Python và thư viện theo profile thích hợp: `requirements-review-lock.txt` cho web/backup đã kiểm chứng; `requirements-lock.txt` là profile benchmark lịch sử. Cài ngoại tuyến theo [RELEASES](../RELEASES.md).

## Bản demo hiện tại

```powershell
& $projectPython -B .runtime/review_roles_20261024/serve.py
```

Mở **http://127.0.0.1:8774/** sau thông báo sẵn sàng. Nếu cổng đã có đúng bản demo chạy thì dùng tiến trình đó; không khởi chạy thêm một writer vào cùng database.

| Thành phần | Đường dẫn từ gốc dự án |
| --- | --- |
| Nguồn/cache v4 | `reports/rr09_ml_completion_20261024/ml_v4/cache/` |
| Kết quả baseline hiện tại | `reports/rr09_ml_completion_20261024/ml_v4/baseline/` |
| Model tương thích | `reports/rr09_ml_completion_20261024/ml_v4/models/` |
| Database demo | `.runtime/rr09_ml_completion_20261024/review.sqlite3` |
| Bộ đối chứng RR09 | `reports/rr09_ml_completion_20261024/rr09_controls/` |
| Phiếu ML mù theo vai trò | `reports/review_roles_20261024/ml_review_workspace/` |

Quyền ghi cần danh tính do máy chủ xác thực; chưa có tài khoản thực tế nên demo hiện ở chế độ xem. Xem [tích hợp vai trò](../examples/review_roles/README.md).

Để thử thao tác kế toán viên → người kiểm tra bằng danh tính mô phỏng, dùng [môi trường browser riêng](reports/app/browser_workflow_20261027.md#môi-trường-và-cách-thử-lại), cổng 8791–8794 và database test riêng. Không nhập kết quả test vào demo 8774 hoặc gói rà ML.

Thông báo hai cấp dùng [cấu hình theo vai trò](../examples/notifications/README.md), không dùng định dạng người nhận kiểu cũ khi gửi thật. Worker chạy riêng; giao diện chỉ chạy giả lập theo phạm vi công ty. Xem [nghiệm thu thông báo](reports/app/notification_roles_20261027.md) cho môi trường test riêng cổng 8795–8798 và bằng chứng lịch sử/chống trùng.

Nếu muốn khởi tạo một workspace thử riêng bằng CLI, xem `python -B -m sme_fraud.review_server --help`; truyền rõ `--data-root`, `--reports-root`, `--database` và `--two-stage-review`. Bộ P2 mặc định của CLI là bộ lịch sử, khác bộ RR09 riêng trong script demo trên.

## Kiểm thử

Các bộ kiểm thử nằm trong `tests/`; chạy bộ liên quan tới thay đổi. Ví dụ kiểm tra các bản sửa gần nhất:

```powershell
$env:PYTHONPATH = "$PWD;.runtime/site-packages;tests"
& $projectPython -B -m unittest test_b4_evidence_timing test_b2_company_transfer test_feature_evidence_timing test_feature_contact_identity test_current_relationship_features test_rr09_priority test_review_roles test_review_workflow
```

JavaScript có các bộ `tests/review_*_ui.test.js` và `tests/rr09_ui.test.js`, chạy bằng Node. Kiểm tra HTTP/renderer và kiểm tra thao tác trên browser là hai bằng chứng khác nhau; ghi rõ loại nào đã chạy.

Bộ CSV/cache mới cho C4/E2/F2/F3/F4 và lệnh mở từng nhóm trong app nằm ở [hướng dẫn dữ liệu đối chứng](../data/rule_branch_controls_20261027/README.md). Chạy `test_rule_branch_controls` để kiểm tra 98 biến thể và export/roundtrip. [Báo cáo](reports/rules/rule_branch_controls_20261027.md) phân biệt độ phủ cũ, đối chứng bổ sung và nghiệm thu nguồn thật còn mở.

[Ma trận kiểm thử luật](reports/rules/rule_test_matrix_20261027.md) ghi ID test cho từng mã/tình huống. Chạy phần ma trận và các ca biên mới:

```powershell
& $projectPython -B -m unittest test_rule_matrix_manifest test_rule_matrix_routing test_rule_boundaries test_rule_statistics_matrix
```

## Khi thêm kết quả mới

Giữ dữ liệu/nhãn/holdout và kết quả đã khoá riêng khỏi việc sửa giao diện hoặc dọn tài liệu. Chạy mới vào một thư mục mới, không huấn luyện lại chỉ để hợp thức hoá độ phủ. Đọc [trạng thái](STATUS.md), [backlog](BACKLOG.md) và hướng dẫn từng module trong `examples/` trước khi chạy benchmark.

Báo cáo diễn giải viết trong `docs/reports/<nhóm>/`; đầu ra lớn nằm trong `reports/<lượt_chạy>/`. Những đường dẫn lịch sử mà app, kiểm thử, manifest hoặc bộ đóng gói sử dụng được giữ tại chỗ và liên kết qua [mục lục báo cáo](reports/README.md).
