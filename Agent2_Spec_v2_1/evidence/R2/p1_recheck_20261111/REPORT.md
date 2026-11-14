# CR-020 — đối chiếu lại P1

**Đường snapshot mới qua các kiểm tra đã chạy; còn một lỗi thời gian ở raw/native engine. Không nghiệm thu toàn engine.**

[111 kiểm thử tập trung](focused_tests.json) pass, 0 lỗi/thất bại/bỏ qua, 49.411 giây; có 7 ca audit mới. [Log](focused_tests.log). Test pass bao gồm xác nhận lỗi native vẫn tái hiện, không có nghĩa lỗi đã sửa. [Audit](audit/summary.json) trả **exit 2**, native_acceptance_pass=false vì finding OPEN.

## Kết quả bảy tình huống

Hóa đơn 10 triệu; các số tiền là triệu VND. Từng tệp liên kết giữ nguồn, validation, RuleResult và raw/native P1 hits/events/config. Hai schema dùng ID và lịch mô phỏng riêng, ánh xạ theo thứ tự giao dịch và khoảng cách thời gian tương ứng; không tuyên bố cùng byte nguồn hay dữ liệu thật.

| Ca | Đầu vào | Snapshot canonical | Raw/native engine | Nhận xét |
|---|---|---|---|---|
| [Chưa vượt](audit/below.json) | Đã trả 4, trả thêm 5 | no-hit, 0 | Không hit, 0 | Khớp |
| [Đã vượt](audit/exceeded.json) | Đã trả 4, trả thêm 7 | hit, 20; tổng 11, vượt 1 | hit, 20; tổng 11, vượt 1 | Khớp điểm, cap, khoản trước, related IDs, hard trigger |
| [Thiếu phạm vi lịch sử](audit/missing_history.json) | 4+7 nhưng không khai báo coverage | unavailable, null | hit, 20 | Native không biểu diễn completeness/readiness; không ép null thành 0 để so |
| [Hóa đơn biết muộn](audit/late_invoice.json) | 6+6; hóa đơn chỉ biết sau khoản thứ hai | unavailable, null | hit, 20 | **Lỗi native P1-NATIVE-LATE-INVOICE** |
| [Phân bổ biết muộn](audit/late_allocation.json) | 4+7, phân bổ hiện tại chỉ đến sau | unavailable, null | hit, 20 | Flat native không có mốc phân bổ tương đương |
| [Tài liệu bổ sung đến muộn](audit/late_attachment.json) | Nguồn P1 đã đủ; file đính kèm không bắt buộc đến sau | hit, 20; file muộn không vào evidence | hit, 20 | Không chặn nhầm P1 vì tài liệu ngoài yêu cầu |
| [Hai khoản đồng thời](audit/simultaneous.json) | Trước 4, đồng thời 4+4 | Hai row 0; một kết quả nhóm 20, tổng 12, vượt 2 | Hai row 0; một batch event 20 | Khớp tổng, cap, thành viên, prior; không nhân điểm nhóm |

Các ca muộn được chạy lại với global as_of lớn hơn: kết quả giao dịch cũ không đổi. Sau khi hóa đơn đã biết, giao dịch mới dùng được nguồn đó; không làm quá khứ đổi từ null thành hit. Bốn tình huống trong miền nguồn chung khớp; hai giới hạn biểu diễn legacy ghi riêng, không gọi là parity số học.

## Finding còn mở

**P1-NATIVE-LATE-INVOICE — OPEN.** Nhánh P1 trong rules.py đọc invoice_gross_vnd dù invoice_observed_at sau posted_at. Guard invoice_at_cutoff hiện có ở nhánh A6, chưa bảo vệ P1. Ca 6+6 triệu/hóa đơn 10 triệu tái hiện native P1=20 trong khi feature thời gian/snapshot chưa được dùng hóa đơn đó.

Đề xuất sửa guard thời gian của đường native P1 và rà cả lịch sử/batch trước khi công nhận as_of; bổ sung hồi quy sau sửa. Lượt này chỉ kiểm thử/audit/docs, giữ nguyên thuật toán để ghi nhận chênh lệch thật. Canonical snapshot đã chặn đúng nguồn muộn. Không khẳng định đường native an toàn cho dữ liệu ngoài phạm vi đã thử.

## Phạm vi xác minh

[Provenance](provenance.json) xác nhận mọi file chấm/sources/schema đã bind trong CR-019 không đổi. Không chạy lại toàn bộ 640 test vì không sửa runtime; [640 regression trước](../p1_evaluation_20261111/native_tests.json) giữ làm lịch sử, lượt này chạy 111 test liên quan. Không fit/active, đổi trọng số, phát queue hoặc duyệt R2/DONE/production. R2 giữ PARTIAL.
