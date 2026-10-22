# Phiếu 17: DRV_7058e2cdcf224f9d

Công ty **DN08**. Cutoff loại trừ (VN): **2026-01-01T00:00:00+07:00**.

**Rà sơ bộ của trợ lý, nguồn mô phỏng.** Người rà độc lập/phân xử chưa được phân công. Trợ lý có tham gia phát triển nên không ký độc lập hoặc mù.

Kết quả sơ bộ: **Chưa đủ căn cứ — cần bổ sung**. Đề xuất actionable: **unknown**; chưa được người rà xác nhận.

Hóa đơn bán hàng 106.615.000 đồng khớp số tiền và bút toán. Số tiền cao hơn approval_limit_vnd 100 triệu của approver master, nhưng chưa có ma trận nêu hạn mức này có áp dụng cho bán hàng hay không hoặc có ngoại lệ; chưa xác nhận vượt quyền hay sai doanh thu.

**Hành động đề xuất**

Xác minh phạm vi thẩm quyền đối với hóa đơn bán hàng và phê duyệt/ngoại lệ khoản 106.615.000 đồng; không sửa doanh thu chỉ do trường hạn mức.

**Tài liệu cần bổ sung có mục tiêu**

- Ma trận thẩm quyền nêu rõ phạm vi áp dụng cho bán hàng
- Phê duyệt/ủy quyền và ngoại lệ cho hóa đơn 106.615.000 đồng nếu cần

Bản gốc/scan chứng từ không nằm trong gói; evidence_on_file chỉ là xác nhận mô phỏng.

**Thời gian và xác nhận**

Phút rà thực tế của con người: **chưa có (null)**. Phút phân xử: **chưa có**. Chưa có hành động nào được xác nhận đã thực hiện.
Phiếu thuộc batch trợ lý `009_020`, 2026-10-23T00:28:18.748518+07:00 → 2026-10-23T00:29:21.303359+07:00, 1.0426 phút thời gian trôi qua cho cả batch. Có thời gian công cụ/chuẩn bị; không phân bổ thành phút từng phiếu hoặc phút active của con người.

Cùng phạm vi danh sách thành viên/nguồn ở STT: —. Các cutoff là các lượt rà riêng; không đếm lại thành sự kiện mới.

**Căn cứ nguồn**

[Phiếu nguồn](../../ml_if_discovery_review_20261022/public/evidence/DRV_7058e2cdcf224f9d/review.md) · [evidence.json](../../ml_if_discovery_review_20261022/public/evidence/DRV_7058e2cdcf224f9d/evidence.json)

SHA256 evidence: `bf6ef8e4f79a26416d6127bd242fa4f294c550bc7d13a26e78382fa0b701a682`.

JSON pointers trong evidence.json:

- `/tables/employees/0`
- `/tables/employees/3`
- `/tables/invoices/0`
- `/tables/journal_lines/0`
- `/tables/journal_lines/1`
- `/tables/journal_lines/2`
- `/tables/member_transactions/0`

Đã hiệu chỉnh sau kiểm tra nhất quán; kết quả trước và lý do được lưu tại `revision_history` trong [bản JSON](../assessments/DRV_7058e2cdcf224f9d.json).

[Danh sách 128 phiếu](../CASE_INDEX.md) · [Phiếu trước](DRV_b721a8d60c426a39.md) · [Phiếu sau](DRV_417f7066f06cbe14.md)
