# 02. Dữ liệu (vai trò data scientist, data analyst)

**Câu trả lời ngắn:** không có bộ dữ liệu công khai nào gán nhãn gian lận nội bộ của doanh nghiệp nhỏ. Vì vậy Agent 2 dùng **dữ liệu tổng hợp tự sinh**, hiệu chỉnh theo ACFE 2024 và vụ án Việt Nam, kiểm tra thêm trên hai bộ dữ liệu công khai của người khác. Toàn bộ số đo mô hình là trên dữ liệu tổng hợp.

## Thứ tự đọc

| # | Tệp | Nội dung |
|---|---|---|
| 1 | [01_tong_quan_va_nguyen_tac.md](01_tong_quan_va_nguyen_tac.md) | Chiến lược bốn lớp dữ liệu và 8 nguyên tắc sinh |
| 2 | [02_nguon_cong_khai_dung_va_khong_dung.md](02_nguon_cong_khai_dung_va_khong_dung.md) | Từng nguồn công khai: dùng gì, bỏ gì, vì sao |
| 3 | [03_lich_su_phien_ban_du_lieu.md](03_lich_su_phien_ban_du_lieu.md) | v2 (bạn bạn) → v3 → v4 → niêm phong: sai ở đâu, sửa thế nào |
| 4 | [04_the_gioi_v4_cach_sinh.md](04_the_gioi_v4_cach_sinh.md) | Công ty, nhân sự, nhà cung cấp, khách hàng, quy trình nền, kế toán |
| 5 | [05_danh_muc_kich_ban_gian_lan.md](05_danh_muc_kich_ban_gian_lan.md) | 37 kịch bản (30 phát triển, 7 niêm phong) |
| 6 | [06_ca_kho_va_ca_hop_le_giong_gian_lan.md](06_ca_kho_va_ca_hop_le_giong_gian_lan.md) | Mức che giấu, ca "mồi", cách làm khó |
| 7 | [07_hieu_chinh_va_gia_dinh.md](07_hieu_chinh_va_gia_dinh.md) | Tham số nào có nguồn, tham số nào là giả định, chỗ lệch với ACFE |
| 8 | [08_quy_mo_va_ke_hoach_sinh_du_lieu.md](08_quy_mo_va_ke_hoach_sinh_du_lieu.md) | Quy mô hiện tại, mở rộng rất lớn, kết hợp dữ liệu thật và sinh |
| 9 | [09_bo_danh_gia_theo_nang_luc.md](09_bo_danh_gia_theo_nang_luc.md) | Bộ dữ liệu nào đo năng lực nào |
| 10 | [10_tu_dien_du_lieu.md](10_tu_dien_du_lieu.md) | 21 bảng, cột quan trọng, khóa |
| 11 | [11_kiem_dinh_chat_luong_du_lieu.md](11_kiem_dinh_chat_luong_du_lieu.md) | Các phép kiểm, kiểm tra lối tắt, thống kê sau sinh |
| 12 | [12_han_che_va_viec_can_lam.md](12_han_che_va_viec_can_lam.md) | Những gì dữ liệu chưa làm được |

## Số liệu nhanh (một thế giới v4)

| Chỉ tiêu | Giá trị |
|---|---|
| Dòng giao dịch | 200.000 (26 loại nghiệp vụ) |
| Công ty | 48 (v4 phát triển), 40 (v4 niêm phong) |
| Thời gian | 2024-01 đến 2025-12; huấn luyện 2024, kiểm định nửa đầu 2025, kiểm thử nửa cuối 2025 |
| Dòng gian lận | khoảng 800 (0,4%); khoảng 190 vụ; 30 kịch bản (37 ở bản niêm phong) |
| Ca hợp lệ giống gian lận | 25 loại (30 ở bản niêm phong); khoảng 17.900 dòng |
| Dung lượng | khoảng 350 MB mỗi thế giới (CSV) |
| Thế giới đã sinh | v3: 5 phát triển + 3 niêm phong; v4: 3 phát triển + 3 niêm phong |

Dữ liệu **không** được đẩy lên Git (quá lớn); lệnh sinh lại nằm ở tệp 08.
