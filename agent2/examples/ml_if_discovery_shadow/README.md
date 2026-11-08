# Shadow mở admission ngoài baseline bằng IF

Nhánh riêng dùng điểm evaluation đã khóa, không load/fit/chấm model, không viết queue hoặc kết luận nghiệp vụ. Bản mới dùng [giao thức giữ ngày baseline](delay_guard_protocol.json), giới hạn **0 ngày trễ thêm so với đối chứng**. [Kết quả mới](../../docs/reports/ml/if_delay_guard_20261027.md) ghi cả đánh đổi thời gian chờ IF; [giao thức v1](protocol.json) giữ riêng để tái hiện nghiên cứu trước guard.

```powershell
python -B -m sme_fraud.compare_if_discovery --dataset reports/rr09_ml_completion_20261024/ml_v4/cache/sme_fraud_001 --baseline reports/rr09_ml_completion_20261024/ml_v4/baseline/sme_fraud_001 --comparison reports/rr09_ml_completion_20261024/ml_v4/comparison/sme_fraud_001 --coverage reports/rr09_ml_completion_20261024/ml_v4/coverage/sme_fraud_001 --protocol examples/ml_if_discovery_shadow/delay_guard_protocol.json --output reports/my_if_guard_001
```

Đổi 001 thành 003 cho cohort kia; luôn dùng output mới. Dùng môi trường trong [hướng dẫn phát triển](../../docs/DEVELOPMENT.md). Runner xác minh commitment nguồn/điểm/model/coverage/case builder. Chạy đối chứng 0%, quota 20%/40%, chi phí IF 20/30 phút, ở cả 5/120 và 10/240. Ngưỡng lấy từ training record đã khóa; không dùng evaluation để đổi ngưỡng.

Mỗi ngày giữ sức chứa cho mọi lượt baseline được chọn bởi đối chứng tại cùng cutoff; các lượt đã hoàn tất không bị nhận lại. Sau đó mới dùng số suất và phút còn lại cho IF, giảm quota khi cần. Không đọc lịch baseline ngày tương lai để quyết định hôm nay. Đây là giới hạn trễ tăng thêm do IF, không phải giới hạn chờ tuyệt đối hoặc cam kết sửa mọi SLA quá hạn có sẵn. Các khoảng grace dương chưa được chính sách này hỗ trợ.

Trong output v2, `legacy_controls/` chạy lại nhánh không guard để đối chiếu. Dùng giao thức v1 cũ nếu cần tái hiện lịch sử; giao thức đó không tự có giới hạn trì hoãn mới. Ngày baseline tham chiếu và phần trễ thêm trong selections là chú thích hậu kiểm, không dùng thông tin tương lai khi chọn.

Ứng viên là giao dịch vượt ngưỡng, ngoài phạm vi giao dịch/chứng từ baseline đã thấy tại cutoff. Một giao dịch đại diện mỗi chứng từ theo invoice → journal document → transaction; một lần rà/chứng từ/nhánh. Phần còn lại giữ thứ tự baseline. Giữ các pin hard/nontransaction và mọi giới hạn suất/phút. Lượt IF không tự hoàn tất công việc baseline về sau.

`baseline_signal_class` phân biệt 0 điểm giao dịch với tín hiệu giao dịch yếu chưa admission; `context_only_hits` đếm hit không cộng điểm, không chứng minh hoàn toàn không có ngữ cảnh luật. `first_baseline_document_cutoff` là chú thích hồi cứu, không dùng để loại ứng viên trước khi baseline biết.

Đọc cả số đầu mối mới, tổng phút ước tính, độ trễ cùng work key, tồn cuối kỳ và suất bắt buộc. Không cộng cùng chứng từ giữa cấu hình. Trần ngân sách bằng nhau không có nghĩa thời gian đã dùng bằng nhau. Các CSV private có nhánh/điểm/ID, giữ nội bộ.

Gói reviewer riêng nằm ở `reports/ml_if_discovery_review_20261022/reviewer_packet.zip`. Sau khi phân công người rà độc lập và người phân xử khác, có thể dùng validator sẵn có:

```powershell
python -B -m sme_fraud.independent_ml_review validate --prepared reports/ml_if_discovery_review_20261022 --primary reports/ml_if_discovery_review_20261022/public/primary_reviews.csv --adjudications reports/ml_if_discovery_review_20261022/public/adjudications.csv --output reports/my_discovery_review_validation
```

Điền `private/reviewer_assignment.json` với ID hai người thực tế trước khi nhập kết quả. Không tự ký, điền outcome hoặc dùng phút ước tính thay phút đo thực tế. Gói chỉ là nguồn mô phỏng, chưa chứng minh hiệu quả SME thật; giữ các khoản rà tham chiếu/phân xử riêng.
