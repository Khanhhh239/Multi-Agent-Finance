# Mẫu nguồn cho F1, C4, E2, F2, F3 và F4

Các CSV trong thư mục này chỉ chứa header chuẩn. Sao chép dữ liệu xuất từ HR/ERP/công nợ vào một **dataset mới**, giữ timestamp ISO có múi giờ và cập nhật `files[filename]` trong `manifest.json` bằng số dòng cùng SHA-256 thực tế. Không sửa manifest của dataset mô phỏng để giả lập nguồn thật.

F1 dùng `journal_audit_log.csv`, `closing_periods.csv`, `materiality_policies.csv`. C4 dùng lịch nghỉ, log thao tác và quyền làm việc trong kỳ nghỉ. E2 dùng lịch sử việc làm và loại/kỳ thanh toán. F2 dùng policy workflow và log override. F3 dùng dải số, sổ đăng ký và nhật ký hủy. F4 dùng hóa đơn phải thu, phân bổ thu tiền, coverage đồng bộ và giải trình.

File rỗng có header vẫn là một nguồn hợp lệ về schema, nhưng chỉ được coi là đầy đủ khi người phụ trách nguồn xác nhận coverage cho đúng công ty, khoảng thời gian và cutoff trong quy trình `sme_fraud.real_source_acceptance`.
