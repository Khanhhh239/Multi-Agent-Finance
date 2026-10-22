# 02 · Data — Chiến lược và đặc tả dữ liệu cho Agent 1

Góc nhìn: data scientist / data analyst. Trả lời: dữ liệu nào dùng, dữ liệu nào không và vì sao, bộ tổng hợp được
làm ra thế nào, quy mô, hard case, bộ đánh giá từng năng lực.

| File | Nội dung | Đọc khi |
|---|---|---|
| [01_chien_luoc_du_lieu.md](01_chien_luoc_du_lieu.md) | Ba tầng dữ liệu, cách kết hợp thật + tổng hợp, quy tắc chống ảo tưởng | Cần nắm bức tranh |
| [02_du_lieu_that_dung.md](02_du_lieu_that_dung.md) | 8 nguồn thật đang dùng: mô tả, cột, thống kê, vai trò, hạn chế | Cần biết chính xác dữ liệu thật |
| [03_du_lieu_khong_dung.md](03_du_lieu_khong_dung.md) | Nguồn đã khảo sát nhưng không dùng / chưa dùng, lý do, phân tích sơ | Cần biết vì sao loại |
| [04_may_phat_tong_hop.md](04_may_phat_tong_hop.md) | Máy phát SME VN: kiến trúc, quy tắc sinh từng thực thể, tham số, hiệu chỉnh | Cần hiểu/mở rộng máy phát |
| [05_hard_cases.md](05_hard_cases.md) | Danh mục tình huống khó (đã chèn / còn thiếu), cách sinh và cách đo | Cần thiết kế kiểm thử |
| [06_quy_mo_va_ke_hoach_sinh.md](06_quy_mo_va_ke_hoach_sinh.md) | Quy mô hiện có, kế hoạch sinh dữ liệu rất lớn, cấu hình, chi phí tính toán | Cần sinh thêm dữ liệu |
| [07_bo_danh_gia.md](07_bo_danh_gia.md) | Bộ đánh giá riêng từng năng lực và đánh giá chung, quy tắc niêm phong | Cần chạy benchmark |
| [08_tai_lieu_tham_khao.md](08_tai_lieu_tham_khao.md) | Paper/nguồn tham khảo cho dữ liệu và máy phát, ánh xạ vào thiết kế | Cần trích dẫn |
| [10_realism_v2.md](10_realism_v2.md) | C2ST tách đặc trưng thiết kế/hành vi, khớp cửa sổ quan sát, máy phát `realism=v2`; vì sao dừng chỉnh máy phát (22/10/2026) | Cần biết dữ liệu tổng hợp giống thật tới đâu |

Vị trí thực tế trong repo: `data/raw/` (crawl, MANIFEST.json), `data/interim/` (cache chuẩn hoá), `data/synthetic/`
(4 thế giới), code `agent1/data/`, `agent1/synth/`, `scripts/crawl.py`, `scripts/build_worlds.py`.
Thẻ dữ liệu cô đọng: [../DATA_CARD.md](../DATA_CARD.md).
