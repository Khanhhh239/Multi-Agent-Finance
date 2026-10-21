# Nhật ký quy tắc pháp lý

Ngày kiểm: 16/10/2026. Đã chuyển các hằng số của bản mô phỏng sang
`agent1/rules/rules_history.json`, có nguồn, ngày hiệu lực và trạng thái xác minh.
Giữ hành vi lịch sử để không thay giả định kinh tế trong lúc đo lại.

Các quy tắc **chưa được chuyên gia xác nhận**, `verified=false`; kiểm thử hồi quy chỉ
xác nhận mã thực hiện đúng cấu hình, không xác nhận cấu hình là tư vấn pháp lý hiện hành.

Nguồn đã mở đối chiếu:

- [Luật 38/2019/QH14, bản Chính phủ](https://vanban.chinhphu.vn/?pageid=27160&docid=197312).
- [NĐ 293/2025/NĐ-CP, toàn văn Chính phủ](https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-293-2025-nd-cp-quy-dinh-muc-luong-toi-thieu-doi-voi-nguoi-lao-dong-lam-viec-theo-hop-dong-lao-dong-119251110172808433.htm).
- [Giải đáp của Bộ Tài chính về Điều 6 TT48](https://m-portal.mof.gov.vn/hoidapcstc/home/cthoidap/118779).

Cần kiểm bản hợp nhất/thay thế áp dụng từ 2026 trước khi vận hành thật; không lấy
dự thảo thay TT48 làm văn bản đã có hiệu lực. Ngày hiệu lực, phụ lục loại trừ VAT,
các đợt miễn giảm BHXH và lịch nghỉ chính thức phải được rà soát theo từng giai đoạn.

Lệnh kiểm: `.venv/Scripts/python.exe scripts/check_rules.py --asof 2026-10-16`.
Đầu ra: `outputs/rules/rules_review.csv`.

## Kiểm thêm ngày 20/10/2026

Thêm lịch nhận số từ hồ sơ/hợp đồng cho TNCN, nhà thầu, hoàn VAT, thưởng,
thuê nhiều bậc và gốc/lãi vay. Chưa suy ra số thuế hoặc tự đặt ngày hoàn.
Nguồn chính thức và phạm vi áp dụng được ghi trong
[đặc tả lịch bổ sung](04_AI_Methods/11_extended_obligations.md).

Đã phát hiện Luật 108/2025/QH15 và NĐ252/2026 thay đổi khung quản lý thuế
từ 2026; TT80/2021 có sửa đổi TT94/2025. Giữ `verified=false`, chưa coi
quy tắc mô phỏng lịch sử là lịch khai/nộp thuế hiện hành. Cần chuyên gia
kiểm bản hợp nhất, quy định chuyển tiếp và lịch nghỉ trước khi vận hành.
