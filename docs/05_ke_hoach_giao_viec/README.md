# 05. Kế hoạch giao việc cho coding agent kế tiếp

Người đọc: một coding agent (hoặc kỹ sư) tiếp nhận dự án, **chưa có ngữ cảnh**. Tài liệu này nói: việc gì, theo thứ tự nào, tạo tệp nào, thí nghiệm giả thuyết gì, làm thế nào, thế nào là xong.

## Vòng v5 sau M2

Chủ dự án đã giao vòng mới: [hậu kiểm R0](../03_danh_gia_va_hieu_qua_kinh_te/08_mo_xe_niem_phong_v4.md) hoàn tất trên dữ liệu tổng hợp; [đăng ký trước](08_dang_ky_truoc_v5.md) đã duyệt v1.1 và có sửa đổi v1.2, v1.3 ghi trước mọi so sánh. R2 đang chạy bằng `scripts/run_r2_master.py`; báo cáo tự sinh bằng `scripts/report_r2.py`. Nếu chốt chặn đạt: R3 theo [brief_v5.md](independent_scenarios/brief_v5.md), mã hóa vào `agent2/world_v5_sealed.py`, rồi `scripts/run_sealed_v5.py` (sinh, chuẩn bị, thử khô, đánh giá một lần). Nếu không đạt: [đề xuất đổi hướng](../01_phan_tich_kinh_te_va_nghiep_vu/09_de_xuat_doi_huong_dich_vu_ra_soat.md). Bàn giao các thành phần chính: [09_ban_giao_nhanh_drivers.md](09_ban_giao_nhanh_drivers.md). Không dùng các kết quả hậu kiểm để viết lại kết luận v4 không đạt G5. Kế hoạch A đến E bên dưới được giữ để truy vết; trạng thái mới tại [STATUS.md](../STATUS.md).

## Đọc theo thứ tự này
1. [STATUS.md](../STATUS.md): trạng thái hiện tại.
2. [00_thiet_lap_va_quy_tac.md](00_thiet_lap_va_quy_tac.md): môi trường, bản đồ mã, **quy tắc không được vi phạm**.
3. Làm lần lượt các pha:

| Pha | Tệp | Nội dung | Phụ thuộc |
|---|---|---|---|
| **A** | [01_pha_A_hoan_tat_so_sanh_va_niem_phong.md](01_pha_A_hoan_tat_so_sanh_va_niem_phong.md) | Tái lập, hoàn tất so sánh phương pháp, đóng băng, chạy niêm phong v4 một lần, huấn luyện lại mô hình v4 | không |
| **B** | [02_pha_B_thi_nghiem_cai_tien.md](02_pha_B_thi_nghiem_cai_tien.md) | Thí nghiệm H4, H5, H6, H9, H12, H13 và các giả thuyết khác để cải thiện phương pháp | A |
| **C** | [03_pha_C_san_pham_hoa.md](03_pha_C_san_pham_hoa.md) | Đường ống v4 hoàn chỉnh, bộ nhận dữ liệu, dịch vụ, lý do tiếng Việt, hiệu năng | A (song song với B) |
| **D** | [04_pha_D_du_lieu_mo_rong_va_doc_lap.md](04_pha_D_du_lieu_mo_rong_va_doc_lap.md) | Mở rộng bộ sinh, quy mô lớn, thế giới niêm phong độc lập, nền thật | A |
| **E** | [05_pha_E_thi_diem_va_phap_ly.md](05_pha_E_thi_diem_va_phap_ly.md) | Thí điểm 3 đến 5 doanh nghiệp, pháp lý, đo kinh tế thật | C |
| **E+** | [10_ke_hoach_chuan_bi_thi_diem_sau_v6.md](10_ke_hoach_chuan_bi_thi_diem_sau_v6.md) | Việc máy làm ngay, việc cần người, điều kiện bắt đầu thí điểm sau v6 | E |
| | [06_checklist_va_lich.md](06_checklist_va_lich.md) | Danh sách việc, công ước tính, định nghĩa hoàn thành | |
| | [07_cam_bay_va_meo.md](07_cam_bay_va_meo.md) | Lỗi đã gặp, mẹo | |

## Mục tiêu cuối
Một sản phẩm Agent 2 chạy được cho doanh nghiệp thật ở chế độ chỉ xem, với:
- cấu hình phát hiện đã chọn bằng quy trình sạch và đã kiểm thử trên tập niêm phong;
- mỗi cảnh báo có lý do tiếng Việt trung thực;
- số đo hiệu năng thật (thí điểm) thay cho giả định trong [thư mục 03](../03_danh_gia_va_hieu_qua_kinh_te/README.md);
- một bộ dữ liệu tổng hợp lớn, có kịch bản do người khác viết, để kiểm thử độc lập.

## Cách làm việc (quy trình mỗi nhiệm vụ)
1. Đọc phần "Đầu vào" của nhiệm vụ và các tệp mã được nêu.
2. Viết kiểm thử trước hoặc cùng lúc; chạy `pytest tests_agent2 tests_sme_fraud -q`.
3. Chạy thí nghiệm bằng **tiến trình tách rời**, lưu JSON sau mỗi giao thức.
4. Ghi nhật ký vào `docs/06_ghi_chep_lam_viec/AGENT2_WORKLOG.md` (mục mới đánh số tiếp): giả thuyết, tiêu chí đặt trước, kết quả, kết luận.
5. Cập nhật tài liệu liên quan (METHODS, DATA, thư mục 03) và [STATUS.md](../STATUS.md).
6. Không đẩy dữ liệu lớn lên Git.
