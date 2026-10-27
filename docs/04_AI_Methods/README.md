# 04 · AI Methods — Phương pháp, pipeline và thí nghiệm

> Đây là bản đồ **thiết kế và phương pháp**. Để biết nhánh nào đã chạy và đạt cổng nào, đối chiếu [kết quả hiện hành](../03_Evaluation/04_ket_qua_hien_co.md), [cổng hiện hành](../03_Evaluation/GATES_CURRENT.md) và mã nguồn.

Góc nhìn: AI engineer / researcher. Nói rõ **mô hình nào, vì sao, tham số nào, đã chứng minh gì, còn phải thí nghiệm gì**.

| File | Nội dung |
|---|---|
| [01_pipeline_he_thong.md](01_pipeline_he_thong.md) | Kiến trúc đầu-cuối, luồng dữ liệu, chống rò rỉ, vận hành (batch/retrain/giám sát), vị trí LLM |
| [02_t1_hazard_thoi_diem_tra.md](02_t1_hazard_thoi_diem_tra.md) | T1: thiết kế chi tiết hazard rời rạc, đặc trưng, tham số, lượng phân vị, ensemble, CQR |
| [03_t2_t3_t8_xac_suat_hoa_don.md](03_t2_t3_t8_xac_suat_hoa_don.md) | T2 cure, T3 tranh chấp/trả một phần, T8 lời hứa |
| [04_t4_t5_thu_moi_va_chi.md](04_t4_t5_thu_moi_va_chi.md) | T4 doanh thu mới (LightGBM toàn cục + Chronos), T5 bộ máy quy tắc |
| [05_domain_adaptation.md](05_domain_adaptation.md) | Chuyển từ tổng hợp/nguồn sang SME đích: bất biến miền, 5 chiến lược, thiết kế thí nghiệm |
| [06_t6_monte_carlo_conformal.md](06_t6_monte_carlo_conformal.md) | T6 mô phỏng copula-t, ACI, đối chứng, kịch bản |
| [07_t7_t9_t10.md](07_t7_t9_t10.md) | Điểm gãy, khớp sao kê, giải thích và khuyến nghị |
| [08_thi_nghiem_de_xuat.md](08_thi_nghiem_de_xuat.md) | Danh mục giả thuyết/thí nghiệm cần làm thêm (kèm lý do, thiết kế, tiêu chí) |
| [09_tham_so_va_toi_uu.md](09_tham_so_va_toi_uu.md) | Bảng siêu tham số, tối ưu tốc độ/bộ nhớ, bẫy kỹ thuật đã gặp |
| [09_promise_chat_review.md](09_promise_chat_review.md) | Đặc tả thu lời hứa từ chat với người duyệt, tách khỏi bảng siêu tham số 09 |
| [10_cash_baselines.md](10_cash_baselines.md) | ETS/ARIMA và đối chứng thêm cho dự báo số dư |
| [11_extended_obligations.md](11_extended_obligations.md) | Lịch nghĩa vụ bổ sung từ hồ sơ, hợp đồng và giới hạn kiểm chứng pháp lý |
| [12_new_ablations.md](12_new_ablations.md) | Các phép đo bổ sung và ablation theo giao thức riêng |
| [13_fullweek_refresh_2026-10-21.md](13_fullweek_refresh_2026-10-21.md) | Kế hoạch/chứng cứ chạy lại hazard ngày 21/10; một số script/log lịch sử không còn trên đĩa |
| [T0_T10_PHUONG_PHAP_VA_KET_QUA_SYNTHETIC_2026-10-25.md](T0_T10_PHUONG_PHAP_VA_KET_QUA_SYNTHETIC_2026-10-25.md) | Ảnh chụp phương pháp và kết quả trên synthetic ở commit 25/10 |

**Tinh thần thiết kế (5 điều):**
1. *Mô hình hoá từng hoá đơn rồi tổng hợp* — phân phối theo tuần cho từng hoá đơn (hazard), sau đó cộng bằng mô phỏng có tương quan.
2. *Mốc đơn giản phải bị thắng* — mọi khối có đối chứng bắt buộc; không giữ mô hình phức tạp không thắng.
3. *Nhãn đúng, đặc trưng as-of, kiểm duyệt đúng* — ba nguyên nhân chính của kết quả đẹp giả.
4. *Bất biến miền + thích nghi nhanh* — vì không có dữ liệu thật SME VN ở quy mô lớn.
5. *Con số do mô hình định lượng, lời do LLM* — LLM không sinh số.
