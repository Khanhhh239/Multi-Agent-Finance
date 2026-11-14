# Demo P1: hóa đơn, phân bổ thanh toán và lịch sử

Đây là **dữ liệu mô phỏng**, không phải chứng từ gốc hoặc nhãn gian lận đã xác
minh. Bộ demo có 5 ca chính, dùng 8 giao dịch để giữ nguyên khoản trả trước,
điều chỉnh âm và hai khoản đồng thời. Không phải nâng ngân sách rà soát ML.

## Cách mở trên Portal

1. Mở [Chạy phân tích](http://127.0.0.1:8800/agent2/encrypted-analysis).
2. Chọn **C001**, chọn bản dữ liệu **8 bản ghi**, kỳ **02–08/10/2026**, được
   lưu ngày **13/11/2026**. Snapshot mới:
   `snp_25b7fd36815346619377fd430b9002fc`.
3. Để thử C002, chọn bản 8 bản ghi tương ứng, snapshot
   `snp_2b8bce04da224fc2aa71f94a496ccfed`.
4. Mở **Xem lại lần phân tích đã lưu** để xem yêu cầu đã tạo:
   C001 `herun_a41f1c89c0b04bb9bd85021731bdaf7f`,
   C002 `herun_83f30523ede5495a97a9957a07a000dc`. Cả hai lượt đã hoàn tất; mở kết quả để rà.
5. Muốn thử một lượt mới, bấm **Chạy phân tích** để chạy bốn nhánh bằng model/khóa hiện có. P1 HE có
   nhiều phép tính nên có thể mất lâu; không tạo thêm yêu cầu khi đang chờ.
   Nếu phiên đăng nhập hết hạn, đăng nhập lại rồi tiếp tục đúng yêu cầu đã lưu.

Hai snapshot đã được thêm bằng luồng kiểm tra → xác nhận lưu, có backup kho
snapshot trước khi thêm. Giữ nguyên bộ 5 giao dịch cũ, model, khóa và quyền.

Nếu muốn tự thử nhập, mở **Nhập dữ liệu**, chọn doanh nghiệp rồi tải đúng tệp:

- [C001_P1_5_ca_8_ban_ghi.json](C001_P1_5_ca_8_ban_ghi.json)
- [C002_P1_5_ca_8_ban_ghi.json](C002_P1_5_ca_8_ban_ghi.json)

**Không tải `demo_manifest.json` vào màn hình nhập**: đó là thông tin kiểm thử.
Kết quả kỳ vọng nằm trong hướng dẫn/báo cáo, không được thêm vào feature.
Dùng nguyên tệp để demo; đổi số tiền hoặc liên kết phải xuất lại manifest.

## Kết quả cần thấy với C001

Đơn vị trong bảng: **triệu VND**. Hóa đơn `P1_I_BASE` có nghĩa vụ 10 triệu,
`P1_I_GROUP` có nghĩa vụ 6 triệu. Các nguồn được biết trước hoặc đúng thời
điểm giao dịch; hai khoản T06/T07 có cùng thời điểm 07/10 lúc 08:00.

| Ca | Giao dịch | Cách đối chiếu | Kết quả P1 kỳ vọng |
|---|---|---|---|
| Khoản trả trước | P1_T01 | Trả 6 trên nghĩa vụ 10 | Chưa trúng P1 |
| Chưa vượt | P1_T02 | Đã trả 6, trả thêm 3 → tổng 9/10 | Không trúng; điểm riêng P1 = 0 |
| Đã vượt | P1_T03 | Đã trả 9, trả thêm 3 → tổng 12/10 | Trúng P1; vượt 2; điểm riêng P1 = 20 |
| Điều chỉnh âm | P1_T04 | Giảm 4, liên kết đúng T01 và phân bổ gốc | Không xem là một khoản thanh toán mới; P1 `not_applicable` |
| Sau điều chỉnh | P1_T05 | Lịch sử 6 + 3 + 3 − 4 = 8; trả thêm 1 → 9/10 | Không trúng; không bỏ số âm, không trừ hai lần |
| Đồng thời | P1_T06 và P1_T07 | Mỗi khoản 4/6; cả nhóm 8/6 | Từng khoản không trúng; nhóm trúng, vượt 2, điểm nhóm = 20 |
| Thiếu lịch sử | P1_T08 | Có hóa đơn `P1_I_GAP` và phân bổ 2; thiếu coverage cho nghĩa vụ này | `unavailable`, điểm và kết luận để trống, nêu lý do thiếu lịch sử |

Với **C002, toàn bộ số tiền nhân 3**, kết quả trạng thái/điểm giữ nguyên:
hóa đơn cơ sở 30 triệu, nhóm 18 triệu; hai mức vượt tương ứng đều 6 triệu.
Hai DN cố ý có cùng mã giao dịch để kiểm tra việc tách dữ liệu theo DN.

Tổng mỗi DN: **1 giao dịch trúng, 5 giao dịch đã kiểm tra không trúng, 1 điều
chỉnh không áp dụng P1, 1 giao dịch chưa khả dụng**. Nhóm đồng thời có kết quả
riêng; không cộng thêm 20 vào từng thành viên. Đây là điểm của một luật, không
phải điểm tổng, xác suất sai phạm hoặc kết luận gian lận.

Bảng trên dùng điểm của engine luật để đối chiếu. Portal HE hiện trả cờ P1,
các tổng tiền và kết quả nhóm; chưa có điểm tổng hợp bốn nhánh được duyệt.

## Nguồn đi kèm

Mỗi tệp có 3 bản ghi hóa đơn, 8 phân bổ liên kết rõ giao dịch–hóa đơn, 6 khai
báo lịch sử cùng manifest ID/revision/count/checksum, và master DN/NCC/nhân viên.
Tất cả có mã DN, thời điểm hiệu lực, thời điểm nguồn được biết và cờ mô phỏng.

Coverage chỉ khai báo cho `P1_I_BASE` và `P1_I_GROUP`. `P1_I_GAP` cố ý chưa
được bao phủ. Checksum chứng minh nguồn trong gói không bị đổi; không tự chứng
minh sổ sách của một DN thật đã đầy đủ.

Kết quả kiểm thử và giới hạn phép thử HE xem
[báo cáo nguồn P1](../../../Agent2_Spec_v2_1/evidence/HE/p1_sources_20261113/REPORT.md).
Lượt chạy trên Portal và đối chiếu chứng từ được ghi tại
[báo cáo Portal P1](../../../Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113/REPORT.md).
