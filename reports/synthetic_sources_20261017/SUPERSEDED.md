# Bản sinh đầu được giữ để truy vết

Phiên bản này còn liên kết liên hệ cũ của một số nhân viên được thêm khi tăng headcount. Sau khi trang trí lại master, bộ sinh chưa xóa các mirror do `Generator.employee()` tự thêm. Phát hiện qua kiểm tra tính nhất quán master–entity_links, không dựa trên nhãn hoặc chọn ngưỡng.

Không dùng bản này làm bộ đối chứng chính. Bản sửa xuất sang `data/synthetic_sources_20261017_v2` và `reports/synthetic_sources_20261017_v2`, cùng seed/kịch bản/cấu hình detector. Các commitment và kết quả đầu được giữ nguyên; kiểm tra hash mã nguồn trong plan đầu chỉ đúng tại lần chạy đầu.
