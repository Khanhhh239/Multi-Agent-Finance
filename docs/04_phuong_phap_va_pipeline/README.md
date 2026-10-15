# 04. Phương pháp và pipeline (vai trò AI engineer, AI researcher)

Nhãn độ tin cậy: **[Đ]** đã đọc nguồn; **[T]** chỉ đọc tóm tắt; **[N]** thiết kế của tôi (có lập luận, chưa chắc đã chứng minh); **[M]** số đo trên dữ liệu tổng hợp.

| Tệp | Nội dung |
|---|---|
| [01_kien_truc_pipeline.md](01_kien_truc_pipeline.md) | Sơ đồ, các giai đoạn, đầu vào đầu ra, ba hồ sơ triển khai, khởi đầu lạnh |
| [02_dac_trung_va_luat.md](02_dac_trung_va_luat.md) | Nguyên tắc nhân quả, các nhóm đặc trưng, 34 mã luật, 15 dấu hiệu đỏ v4 |
| [03_bo_phat_hien_khong_nhan.md](03_bo_phat_hien_khong_nhan.md) | EntityDeviation, ECOD, HBOS, Isolation Forest, autoencoder; cách chọn và tham số |
| [04_mo_hinh_co_giam_sat_va_lai.md](04_mo_hinh_co_giam_sat_va_lai.md) | LightGBM (L3), L4, cân bằng họ, hai tầng, CES, các phép hợp nhất |
| [05_chinh_sach_canh_bao_va_giai_thich.md](05_chinh_sach_canh_bao_va_giai_thich.md) | Ngân sách, khe thăm dò, conformal, gộp vụ, ưu tiên, lý do tiếng Việt |
| [06_phan_hoi_va_hoc_dan.md](06_phan_hoi_va_hoc_dan.md) | Vòng phản hồi, độ trôi, ba bậc khởi đầu lạnh |
| [07_thi_nghiem_da_chay.md](07_thi_nghiem_da_chay.md) | Mọi thí nghiệm đã chạy, kết luận, thất bại |
| [08_gia_thuyet_can_thi_nghiem.md](08_gia_thuyet_can_thi_nghiem.md) | 16 giả thuyết còn mở, thiết kế thí nghiệm, tiêu chí |
| [09_tham_so_va_toi_uu.md](09_tham_so_va_toi_uu.md) | Bảng siêu tham số, đòn bẩy tối ưu, kỹ thuật hiệu năng |
| [10_tai_lieu_tham_khao.md](10_tai_lieu_tham_khao.md) | Bài báo và điều rút ra |

## Ý tưởng cốt lõi trong một đoạn
Gian lận nội bộ ở doanh nghiệp nhỏ có hai phần: phần **đã biết** (nhà cung cấp ma, chia nhỏ, trả trùng...) mà mô hình có giám sát học tốt từ thế giới tổng hợp, và phần **chưa biết** (kiểu mới, kiểu lẫn trong hành vi thường) mà chỉ phát hiện được khi so một thực thể với **chính lịch sử của nó**. Vì vậy Agent 2 gồm: (1) luật nghiệp vụ có giải thích, (2) bộ lệch theo thực thể không cần nhãn, (3) mô hình có giám sát huấn luyện sẵn trên thế giới tổng hợp, (4) chính sách cảnh báo dành một phần ngân sách cho kênh không nhãn, và (5) vòng phản hồi nhẹ. Mọi cảnh báo đều qua ngân sách cứng và có lý do bằng tiếng Việt.
