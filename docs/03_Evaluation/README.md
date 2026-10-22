# 03 · Evaluation — Đánh giá kỹ thuật, kinh tế, chi phí và ROI

Góc nhìn: tester + BA đánh giá. Mục tiêu: chứng minh sản phẩm tốt **bằng số**, nói rõ phần nào đã đo, phần nào mới là giả định.

| File | Nội dung |
|---|---|
| [01_metric_ky_thuat.md](01_metric_ky_thuat.md) | Định nghĩa và công thức chỉ số kỹ thuật cho từng T, vì sao chọn |
| [02_metric_kinh_te.md](02_metric_kinh_te.md) | Chỉ số kinh tế/kinh doanh: tiền, vốn lưu động, chi phí thiếu hụt, nợ xấu, nhân công, sản phẩm |
| [03_cong_nghiem_thu.md](03_cong_nghiem_thu.md) | Cổng GO/NO-GO G1–G14, ngưỡng, trạng thái hiện tại |
| [04_ket_qua_hien_co.md](04_ket_qua_hien_co.md) | Kết quả đã đo (bảng số từ `outputs/`), kể cả chỗ thua, và điều chưa đo |
| [05_chi_phi_xay_dung_va_van_hanh.md](05_chi_phi_xay_dung_va_van_hanh.md) | Chi phí xây dựng, vận hành, biên gộp, điểm hoà vốn |
| [06_roi_truoc_sau.md](06_roi_truoc_sau.md) | Phép tính trước/sau cho một SME mẫu, độ nhạy, ROI khách hàng và nhà cung cấp |
| [07_ke_hoach_kiem_thu.md](07_ke_hoach_kiem_thu.md) | Kế hoạch kiểm thử: đơn vị, tích hợp, backtest, UAT, A/B ở đối tác, giám sát sau triển khai |
| [GATES_CURRENT.md](GATES_CURRENT.md) | Bảng cổng sinh tự động từ CSV (trạng thái hiện hành, thay cho bảng tay trong 03) |
| [GO_NO_GO_SYNTHETIC_ONLY.md](GO_NO_GO_SYNTHETIC_ONLY.md) | **Quyết định triển khai khi chỉ có dữ liệu tổng hợp**: chứng minh được gì, luật an toàn, bậc triển khai, kết quả tgt2 và cổng thoái lui trên dữ liệu thật |
| [G13_ALERT_POLICY.md](G13_ALERT_POLICY.md) | Chính sách cảnh báo thiếu tiền: đăng ký trước, chọn trên nguồn, kết quả tgt và tgt2 |
| [T9_RECALL_DIAGNOSIS.md](T9_RECALL_DIAGNOSIS.md) | Vì sao T9 (G15) trượt trên tgt, phân rã lỗi, hướng sửa |

**Ba quy tắc đọc kết quả:**
1. Mọi chỉ số có **mốc so sánh** (không có con số tuyệt đối đứng một mình).
2. Mỗi kết quả ghi **tầng bằng chứng**: [Thật] dữ liệu thật tương tự · [Tổng hợp] chịu nhiễu · [Giả định] kinh tế chưa đo.
3. Kết quả xấu được công bố cùng kết quả tốt.
