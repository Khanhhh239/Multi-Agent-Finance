# 03 · Evaluation — Đánh giá kỹ thuật, kinh tế, chi phí và ROI

Góc nhìn: tester + BA đánh giá. Mục tiêu: chứng minh sản phẩm tốt **bằng số**, nói rõ phần nào đã đo, phần nào mới là giả định.

| File | Nội dung |
|---|---|
| [01_metric_ky_thuat.md](01_metric_ky_thuat.md) | Định nghĩa và công thức chỉ số kỹ thuật cho từng T, vì sao chọn |
| [02_metric_kinh_te.md](02_metric_kinh_te.md) | Chỉ số kinh tế/kinh doanh: tiền, vốn lưu động, chi phí thiếu hụt, nợ xấu, nhân công, sản phẩm |
| [03_cong_nghiem_thu.md](03_cong_nghiem_thu.md) | Ngưỡng và trạng thái lịch sử ngày 15/10; trạng thái hiện hành ở `GATES_CURRENT.md` |
| [04_ket_qua_hien_co.md](04_ket_qua_hien_co.md) | Kết quả đã đo (bảng số từ `outputs/`), kể cả chỗ thua, và điều chưa đo |
| [04_ket_qua_2026-10-15_lich_su.md](04_ket_qua_2026-10-15_lich_su.md) | Ảnh chụp kết quả trước khi sửa giao thức đo; dùng để truy vết |
| [05_chi_phi_xay_dung_va_van_hanh.md](05_chi_phi_xay_dung_va_van_hanh.md) | Chi phí xây dựng, vận hành, biên gộp, điểm hoà vốn |
| [06_roi_truoc_sau.md](06_roi_truoc_sau.md) | Phép tính trước/sau cho một SME mẫu, độ nhạy, ROI khách hàng và nhà cung cấp |
| [07_ke_hoach_kiem_thu.md](07_ke_hoach_kiem_thu.md) | Kế hoạch kiểm thử: đơn vị, tích hợp, backtest, UAT, A/B ở đối tác, giám sát sau triển khai |
| [GATES_CURRENT.md](GATES_CURRENT.md) | Bảng cổng sinh tự động từ CSV (trạng thái hiện hành, thay cho bảng tay trong 03) |
| [KET_QUA_CHUA_DAT.md](KET_QUA_CHUA_DAT.md) | Kết quả không đạt và giới hạn bằng chứng, sinh từ CSV |
| [GO_NO_GO_SYNTHETIC_ONLY.md](GO_NO_GO_SYNTHETIC_ONLY.md) | Quyết định lịch sử giai đoạn 21/10 khi chỉ có dữ liệu tổng hợp; trạng thái cổng hiện hành ở `GATES_CURRENT.md` |
| [G13_ALERT_POLICY.md](G13_ALERT_POLICY.md) | Chính sách cảnh báo thiếu tiền: đăng ký trước, chọn trên nguồn, kết quả tgt và tgt2 |
| [T9_RECALL_DIAGNOSIS.md](T9_RECALL_DIAGNOSIS.md) | Vì sao T9 (G15) trượt trên tgt, phân rã lỗi, hướng sửa |

Các file `G8_T2_PREREG.md`, `G13_*_PREREG.md`, `G14_T7_PREREG.md`,
`G15_T9_V2_PREREG.md`, `G17_T8_PREREG.md` và
`SPRINT6_PREREG_2026-10-22.md` là giao thức đăng ký trước cho những phép thử
riêng; giữ chúng để kiểm tra tiêu chí đã chọn **trước** khi xem kết quả.
GO kỹ thuật của bộ dữ liệu synthetic cuối đọc ở
[báo cáo dữ liệu 23](../02_Data/23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md);
nó không đổi trạng thái cổng G1–G18 của sản phẩm.

**Ba quy tắc đọc kết quả:**
1. Mọi chỉ số có **mốc so sánh** (không có con số tuyệt đối đứng một mình).
2. Mỗi kết quả ghi **tầng bằng chứng**: [Thật] dữ liệu thật tương tự · [Tổng hợp] chịu nhiễu · [Giả định] kinh tế chưa đo.
3. Kết quả xấu được công bố cùng kết quả tốt.
