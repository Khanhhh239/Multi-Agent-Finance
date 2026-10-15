# 04 · AI Methods — Phương pháp, pipeline và thí nghiệm

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

**Tinh thần thiết kế (5 điều):**
1. *Mô hình hoá từng hoá đơn rồi tổng hợp* — phân phối theo tuần cho từng hoá đơn (hazard), sau đó cộng bằng mô phỏng có tương quan.
2. *Mốc đơn giản phải bị thắng* — mọi khối có đối chứng bắt buộc; không giữ mô hình phức tạp không thắng.
3. *Nhãn đúng, đặc trưng as-of, kiểm duyệt đúng* — ba nguyên nhân chính của kết quả đẹp giả.
4. *Bất biến miền + thích nghi nhanh* — vì không có dữ liệu thật SME VN ở quy mô lớn.
5. *Con số do mô hình định lượng, lời do LLM* — LLM không sinh số.
