# Ma trận kiểm thử luật — 27/10/2026

**607 kiểm thử đạt, 0 lỗi/skip**, trong đó **169 kiểm thử mới**. Đã đối chiếu **35 mã**, mỗi mã có bảy nhóm tình huống: **228 ô có kiểm thử đã chạy đạt**, **17 ô không áp dụng có giải thích**. Đã kiểm tra thêm chính sách ưu tiên/hàng đợi/SLA hoặc phạm vi chẩn đoán tương ứng cho cả 35 mã.

[Trạng thái dự án](../../STATUS.md) · [Backlog](../../BACKLOG.md) · [Ma trận đầy đủ và ID từng test](../../../tests/fixtures/rule_test_matrix.json) · [Kết quả máy](../../../reports/rule_test_matrix_20261027/summary.json)

## Hai lỗi phát hiện và đã sửa

| Nhánh | Trước sửa | Sau sửa |
| --- | --- | --- |
| A6 | Hoá đơn phát hành/được biết sau ngày chi vẫn làm phát sinh 8 điểm cảnh báo làm tròn vượt hoá đơn. | Không dùng hoá đơn có ngày rõ ràng sau cutoff; đúng cutoff vẫn được xét. |
| T1/T2 | Cờ hồ sơ cuối cùng biết sau ngày xoá nợ có thể làm mất cảnh báo; bản ghi writeoff nguồn có thể bị đọc trước lúc quan sát. | Kiểm thời điểm hồ sơ và bản ghi nguồn, đúng công ty/khoản tạm ứng. Thiếu căn cứ tại cutoff vẫn giữ T1/T2; T2 có 20 điểm/hard trigger và hồ sơ ưu tiên cao nhất. |

[Test không đạt trước sửa](../../../reports/rule_test_matrix_20261027/regressions_before_fix.json) và [kết quả sau sửa](../../../reports/rule_test_matrix_20261027/test_results.json) được giữ riêng. Không đổi ngưỡng, trọng số, model hoặc feature contract. Bản sửa áp dụng khi chấm mới; snapshot đã khoá chưa được chấm lại.

Kết quả trên là một lượt chạy đầy đủ trên mã và fixture cuối cùng, không tính lặp các lần thử trong quá trình phát triển.

## Ma trận theo luật

✓: có test cụ thể trong ma trận và đã chạy đạt. N/A: không áp dụng theo phạm vi/chính sách, có lý do bên dưới. Dương là phát hiện đúng điều kiện nghiệp vụ, không đồng nghĩa kết luận gian lận; tín hiệu ngữ cảnh/master có thể vẫn 0 điểm vận hành.

| Mã | Dương | Âm | Biên | Thiếu | Muộn | Master | Ngoại lệ | Ưu tiên / hàng đợi / SLA |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| A2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| A3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | Trung bình, 168 giờ |
| A4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| A5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0 điểm, không mở hồ sơ chỉ vì tín hiệu này |
| A6 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | Trung bình, 168 giờ |
| B1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | Cao nhất, 24 giờ |
| B2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| B3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0 điểm, không mở hồ sơ chỉ vì tín hiệu này |
| B4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| B5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | 0 điểm, không mở hồ sơ chỉ vì tín hiệu này |
| B6 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| B7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Cao nhất, 24 giờ |
| C1 | ✓ | ✓ | ✓ | N/A | ✓ | ✓ | ✓ | 0 điểm, không mở hồ sơ chỉ vì tín hiệu này |
| C2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Cao nhất, 24 giờ |
| C3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | Trung bình, 168 giờ |
| C4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| D1 | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | ✓ | Chẩn đoán tập, không điểm/SLA giao dịch |
| D2 | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | ✓ | Chẩn đoán tập, không điểm/SLA giao dịch |
| D3 | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | ✓ | Chẩn đoán tập, không điểm/SLA giao dịch |
| D4 | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | N/A | Chẩn đoán tập, không điểm/SLA giao dịch |
| D5 | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | ✓ | Chẩn đoán tập, không điểm/SLA giao dịch |
| D6 | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | ✓ | Chẩn đoán tập, không điểm/SLA giao dịch |
| E1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Cao nhất, 24 giờ |
| E2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Cao nhất, 24 giờ |
| E3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | 0 điểm, không mở hồ sơ chỉ vì tín hiệu này |
| E4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | 0 điểm, không mở hồ sơ chỉ vì tín hiệu này |
| F1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | Trung bình, 168 giờ |
| F2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| F3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Nguồn: TB 168 giờ; thiếu coverage: thấp 336 giờ |
| F4 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Nguồn: TB 168 giờ; thiếu coverage: thấp 336 giờ |
| P1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Cao nhất, 24 giờ |
| P2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | N/A | Thấp, 720 giờ |
| T1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Trung bình, 168 giờ |
| T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Cao nhất, 24 giờ |

## Các mục không áp dụng

| Mã | Nhóm | Lý do |
| --- | --- | --- |
| A3 | Ngoại lệ | Chính sách hiện tại không có whitelist miễn A3 bằng hồ sơ; địa chỉ đơn lẻ được loại ở điều kiện phạm vi, không phải miễn trừ chứng từ. |
| A6 | Ngoại lệ | Không có whitelist miễn vượt hoá đơn; dung sai 1 đồng và điều kiện làm tròn đã có ở kiểm tra biên. |
| B1 | Ngoại lệ | Không có cơ chế miễn trùng tài khoản/căn cước đã xác nhận chỉ bằng công bố liên quan; cần giữ đối chiếu độc lập. |
| B5 | Ngoại lệ | Đây là phát hiện chất lượng master, luôn 0 điểm giao dịch; công bố quan hệ là ngữ cảnh, không xoá dấu vết trùng. |
| C1 | Thiếu | Không dùng chứng từ mua hàng/giao nhận; dùng lịch vận hành mặc định hoặc lịch được duyệt, không suy tính hợp lệ từ số chứng từ. |
| C3 | Ngoại lệ | Không có whitelist miễn duyệt quá nhanh; cấp chuẩn thay vì cấp cao là điều kiện phạm vi, đã có đối chứng âm. |
| D1 | Master | Không đọc master nhân sự/NCC; phân đoạn dùng thuộc tính giao dịch. Có test lịch sử kỳ và phân đoạn riêng. |
| D2 | Master | Không đọc master nhân sự/NCC; phân đoạn dùng thuộc tính giao dịch. Có test lịch sử kỳ và phân đoạn riêng. |
| D3 | Master | Không đọc master nhân sự/NCC; phân đoạn dùng thuộc tính giao dịch. Có test lịch sử kỳ và phân đoạn riêng. |
| D4 | Master | Không đọc master nhân sự/NCC; phân đoạn dùng thuộc tính giao dịch. Có test lịch sử kỳ và phân đoạn riêng. |
| D4 | Ngoại lệ | So sánh đuôi số theo nền thực nghiệm; không có cơ chế miễn theo hồ sơ cá biệt. |
| D5 | Master | Không đọc master nhân sự/NCC; phân đoạn dùng thuộc tính giao dịch. Có test lịch sử kỳ và phân đoạn riêng. |
| D6 | Master | Không đọc master nhân sự/NCC; phân đoạn dùng thuộc tính giao dịch. Có test lịch sử kỳ và phân đoạn riêng. |
| E3 | Ngoại lệ | Đây là phát hiện chất lượng master 0 điểm, không phải kết luận gian lận; không có miễn trừ xoá vết tương đồng. |
| E4 | Ngoại lệ | Đây là phát hiện chất lượng master, luôn 0 điểm giao dịch; công bố quan hệ là ngữ cảnh, không xoá dấu vết trùng. |
| F1 | Ngoại lệ | Không có miễn trừ chung cho điều chỉnh đã xác nhận đủ nguồn/trọng yếu; nhánh proxy 0 điểm được kiểm tra ở thiếu nguồn. |
| P2 | Ngoại lệ | Không có whitelist miễn hạn mức đã xác minh; thiếu chứng từ/ngoại tệ chưa quy đổi là phân loại thiếu căn cứ, không phải miễn vi phạm. |

## Các đối chứng bổ sung đáng chú ý

- A1/A2/A3: tổng đúng ngưỡng, thấp hơn 1 đồng; điểm biên cửa sổ 3/30 ngày và giây kế tiếp.
- A4: hai đầu khoảng 80%–99%; A6/P1: dung sai 1 đồng và điều kiện làm tròn.
- B2: một/hai liên hệ trực tiếp, token rỗng, công bố liên quan tại cutoff. B3: 89/90 ngày, hồ sơ giao nhận đến muộn.
- B5/E4/E3: thay/xoá liên hệ hoặc đổi tên master không giữ phát hiện cũ. E3 dùng điều kiện lớn hơn ngưỡng đúng đặc tả.
- B6: 179/180 ngày, bằng/vượt P90, 19/20 mẫu. C1: 08:00/19:00; C3: 59/60 giây và proxy 50 triệu.
- E1/E2/F2/F3/F4: ngày công 0/1, ngày chấm dứt, trần override, dải đóng tại cutoff, công nợ 60/61 ngày.
- T1/T2: ngày đến hạn/grace, gia hạn biết trước/sau, dư nợ trước chính sự kiện tất toán/xoá nợ và chứng từ đến muộn.
- F3/F4 thiếu coverage vẫn có hồ sơ nguồn ưu tiên thấp, rà lại sau 7 ngày, SLA 336 giờ. P2 thiếu chứng từ có 0 điểm rủi ro và SLA thấp 720 giờ.

[Các đối chứng dương và kết quả xếp hồ sơ](../../../reports/rule_test_matrix_20261027/routing_controls.json) ghi cả điểm gốc, điểm vận hành, admission, loại hồ sơ và số giờ SLA.

## Cách chạy lại phần mới

Dùng Python và môi trường thư viện trong [hướng dẫn phát triển](../../DEVELOPMENT.md), từ gốc dự án:

```powershell
$env:PYTHONPATH = "$PWD;tests;.runtime/site-packages"
python -B -m unittest test_rule_matrix_manifest test_rule_matrix_routing test_rule_boundaries test_rule_statistics_matrix
```

Validator của ma trận kiểm tra đủ mã/chiều, lý do N/A và tên test còn tồn tại. Biên bản chạy đối chiếu mọi test được trích dẫn đều có kết quả PASS; không suy độ phủ từ việc có/không có hit trong dataset.

## Phạm vi và bảo toàn

Đối chiếu opaque hash **10209 file**: chỉ mã `sme_fraud/rules.py` thay đổi theo bản sửa này; dữ liệu, model, feature contract, snapshot, phiếu rà và database đã bảo vệ không đổi. [Biên bản bảo toàn](../../../reports/rule_test_matrix_20261027/protected_verification.json). Không nạp/chấm/fit holdout 005 hoặc dùng nhãn/oracle đã lưu để tạo kỳ vọng; các test sinh fixture mô phỏng mới.

Ma trận này xác nhận các tình huống đã khai báo và các ranh giới được nêu, không bao quát mọi tổ hợp dữ liệu, không phải độ phủ dòng/nhánh mã và không chứng minh độ chính xác thực địa. A6 giữ giả định legacy cho header không có thời điểm quan sát. Riêng hồ sơ xoá nợ T1/T2 chỉ được miễn khi có header chứng từ với thời điểm rõ ràng hoặc bản writeoff đúng phạm vi đã biết tại cutoff; cờ cuối cùng không có căn cứ thời gian không đủ để miễn. Đợt này không tự điền thời điểm biết chứng từ. Lợi ích ML, kiểm tra browser toàn luồng và gửi thông báo thật vẫn có trạng thái riêng trong backlog.
