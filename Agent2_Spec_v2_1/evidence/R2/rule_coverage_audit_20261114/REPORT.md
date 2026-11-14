# Kiểm kê 35 luật — 14/11/2026

**READY_FOR_REVIEW cho kiểm kê; không nghiệm thu thêm evaluator/HE hoặc toàn R2.**

Người dùng giao bảng từng luật: cần nguồn gì, còn thiếu gì, adapter và HE
đã có chưa. Báo cáo sinh bằng `agent2/scripts/audit_rule_coverage.py` từ code
và schema hiện tại; lưu SHA256 nguồn được kiểm kê và JSON chi tiết.

| Kết quả | Số lượng |
|---|---:|
| Danh mục và source map | 35 |
| Evaluator snapshot đã nối | 2: E3, P1 |
| Chưa nối evaluator snapshot | 33 |
| Luật nối HE trên Portal | 1: P1 |
| Còn gap bảng/trường theo contract/import 1.1.0 hiện tại | 33 |

Không đồng nhất metadata coverage tĩnh của engine cũ với sẵn sàng chạy trên
snapshot mới. Không suy graph/RobustZ là B1/E4/A5/D đã nối HE. Source map là
phụ thuộc khai báo, không có nghĩa đã nhận đủ bảng/trường hoặc đã đánh giá.

Replay resolver/evaluator local bằng bản nguồn public synthetic đã khóa
checksum ở CR-043, giữ as_of từ run lưu sẵn. Mỗi DN có 8 giao dịch và đủ 35
trạng thái cho mỗi giao dịch; P1 5 no-hit + 1 hit + 1 unavailable + 1 không
áp dụng, E3 8 no-hit. Kết quả nhóm đồng thời P1 nằm ngoài điểm từng dòng.
E1/E2 không áp dụng cho bộ demo này, không coi là đã nghiệm thu luật lương.
Không phát sinh native HE, fit, kết nối Portal hoặc truy cập DB/khóa live.

JSON tách thiếu schema, thiếu nguồn nhìn thấy, trạng thái evaluator và phạm
vi HE; không trả thiếu nguồn thành 0. Nội dung không thay thế rà nghiệp vụ
hoặc kiểm thử cho từng họ rủi ro. Bảng nguồn/field còn thiếu trong import
chưa chứng minh doanh nghiệp không có các nguồn tương ứng.

Bảng chính: [rule_coverage_status_20261114.md](../../../../reports/rule_coverage_status_20261114.md).
Chi tiết: [rule_coverage_status_20261114.json](../../../../reports/rule_coverage_status_20261114.json).

Audit thêm phần việc cho từng luật; không tự chốt ngưỡng/trọng số, sửa kernel,
schema hoặc đưa thêm luật vào hàng đợi. Các quyết định và triển khai tiếp theo
cần căn cứ vào nguồn thật và đối chiếu engine, rồi kiểm chứng HE nếu áp dụng.
