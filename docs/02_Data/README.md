# 02 · Data — Chiến lược và đặc tả dữ liệu cho Agent 1

> **Đọc kết luận mới nhất về bộ train synthetic ở [báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md).** Báo cáo 11–22 ghi kế hoạch, đối chứng và các lần sửa theo thời gian; một kết luận NO-GO của cohort cũ không phủ định GO kỹ thuật của cohort cuối. GO kỹ thuật không chứng minh dữ liệu giống SME Việt Nam hoặc cho phép pilot thật.

Góc nhìn: data scientist / data analyst. Trả lời: dữ liệu nào dùng, dữ liệu nào không và vì sao, bộ tổng hợp được
làm ra thế nào, quy mô, hard case, bộ đánh giá từng năng lực.

| File | Nội dung | Đọc khi |
|---|---|---|
| [01_chien_luoc_du_lieu.md](01_chien_luoc_du_lieu.md) | Ba tầng dữ liệu, cách kết hợp thật + tổng hợp, quy tắc chống ảo tưởng | Cần nắm bức tranh |
| [02_du_lieu_that_dung.md](02_du_lieu_that_dung.md) | 8 nguồn thật của các thí nghiệm trước: mô tả, cột, thống kê, vai trò, hạn chế; hiện chỉ còn WDI/OxCGRT trên đĩa | Cần tra nguồn và kết quả lịch sử |
| [03_du_lieu_khong_dung.md](03_du_lieu_khong_dung.md) | Nguồn đã khảo sát nhưng không dùng / chưa dùng, lý do, phân tích sơ | Cần biết vì sao loại |
| [04_may_phat_tong_hop.md](04_may_phat_tong_hop.md) | Máy phát SME VN: kiến trúc, quy tắc sinh từng thực thể, tham số, hiệu chỉnh | Cần hiểu/mở rộng máy phát |
| [05_hard_cases.md](05_hard_cases.md) | Danh mục tình huống khó (đã chèn / còn thiếu), cách sinh và cách đo | Cần thiết kế kiểm thử |
| [06_quy_mo_va_ke_hoach_sinh.md](06_quy_mo_va_ke_hoach_sinh.md) | Quy mô hiện có, kế hoạch sinh dữ liệu rất lớn, cấu hình, chi phí tính toán | Cần sinh thêm dữ liệu |
| [07_bo_danh_gia.md](07_bo_danh_gia.md) | Bộ đánh giá riêng từng năng lực và đánh giá chung, quy tắc niêm phong | Cần chạy benchmark |
| [08_tai_lieu_tham_khao.md](08_tai_lieu_tham_khao.md) | Paper/nguồn tham khảo cho dữ liệu và máy phát, ánh xạ vào thiết kế | Cần trích dẫn |
| [09_vn_listed_spot_check.md](09_vn_listed_spot_check.md) | Đối chiếu DSO/DPO trên ba báo cáo niêm yết; PDF gốc hiện vắng trên đĩa | Cần xem phép đối chiếu lịch sử và giới hạn |
| [10_realism_v2.md](10_realism_v2.md) | C2ST tách đặc trưng thiết kế/hành vi, khớp cửa sổ quan sát, máy phát `realism=v2`; vì sao dừng chỉnh máy phát (22/10/2026) | Cần biết dữ liệu tổng hợp giống thật tới đâu |
| [11_KE_HOACH_SOC_THI_TRUONG_TICH_HOP_2026-10-25.md](11_KE_HOACH_SOC_THI_TRUONG_TICH_HOP_2026-10-25.md) | Kế hoạch cú sốc tích hợp, nguồn tham chiếu và cổng độ thực tế | Cần phân biệt kế hoạch với phần đã triển khai |
| [12_KIEM_TOAN_KICH_BAN_SINH_DU_LIEU_CU_2026-10-25.md](12_KIEM_TOAN_KICH_BAN_SINH_DU_LIEU_CU_2026-10-25.md) | Kiểm toán lỗi và giới hạn của máy phát cũ | Cần tra nguyên nhân trước sửa |
| [13_RUNNER_V3_MANIFEST_VA_SPLIT.md](13_RUNNER_V3_MANIFEST_VA_SPLIT.md) | Runner v3, hash từng bảng, registry chặn thiếu Parquet và split cố định theo thế giới | Cần sinh/train bộ v3 |
| [14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md](14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md) | Kiểm lại phân phối, sốc và 12 hard case trên dữ liệu tái sinh; quyết định NO-GO bộ train cuối | Trước khi khóa split/train |
| [15_SUA_VONG_DOI_KHACH_VA_HARD_CASE_2026-10-26.md](15_SUA_VONG_DOI_KHACH_VA_HARD_CASE_2026-10-26.md) | Sửa vòng đời khách, vỡ nợ lặp lại, `heterogeneity` và `lumpy_customer`; kiểm lại ba seed và hai hard case | Khi cần kết quả sau sửa |
| [16_KIEM_TOAN_CHI_SO_V5_TU_DU_LIEU_HIEN_CO_2026-10-26.md](16_KIEM_TOAN_CHI_SO_V5_TU_DU_LIEU_HIEN_CO_2026-10-26.md) | Doanh thu, khách, bán chịu, ngày trả, tuổi nợ quá hạn và số dư tiền trên ba World v5 đã có | Khi cần kiểm chỉ số theo năm/ngành |
| [17_HELDOUT_SHOCK_VA_KIEM_TRA_NHIEU_SEED_2026-10-26.md](17_HELDOUT_SHOCK_VA_KIEM_TRA_NHIEU_SEED_2026-10-26.md) | Hai kịch bản shock test giữ riêng và kiểm xu hướng doanh thu/khách trên 10 seed | Trước khi chốt cohort train cuối |
| [18_TONG_KET_KIEM_CHUNG_PHAT_TRIEN_SYNTHETIC_DATA_2026-10-26.md](18_TONG_KET_KIEM_CHUNG_PHAT_TRIEN_SYNTHETIC_DATA_2026-10-26.md) | Tổng kết theo phiên bản, đối chiếu mã/dữ liệu, trạng thái lỗi và readiness | Cần kết luận kiểm chứng toàn bộ quá trình |
| [19_KIEM_TOAN_CHI_SO_10_WORLD_2026-10-26.md](19_KIEM_TOAN_CHI_SO_10_WORLD_2026-10-26.md) | Tính lại doanh thu, khách, bán chịu, ngày trả, tuổi nợ và tiền mặt trên 10 World theo năm/ngành | Cần kiểm toán chỉ số sau khi sinh thêm seed |
| [20_COHORT_UNG_VIEN_V3_VA_KIEM_TOAN_2026-10-26.md](20_COHORT_UNG_VIEN_V3_VA_KIEM_TOAN_2026-10-26.md) | Cohort ứng viên RNG v1 và kiểm kỹ thuật trước khóa split | Cần xem kết quả ứng viên ban đầu |
| [21_KIEM_CHUNG_AR_AP_VA_DO_BEN_SEED_2026-10-26.md](21_KIEM_CHUNG_AR_AP_VA_DO_BEN_SEED_2026-10-26.md) | Đối chiếu AR/AP độc lập, phát lại 10 seed, phản thực vĩ mô và cohort RNG v2/v3 trước khi sửa AP | Cần lịch sử kiểm chứng đến r3 |
| [22_COHORT_SYNTHETIC_DA_KHOA_2026-10-27.md](22_COHORT_SYNTHETIC_DA_KHOA_2026-10-27.md) | Cohort ứng viên RNG v3 đã sửa AP, định trước baseline/stress, khóa split và train/evaluate | Cần lịch sử kiểm chứng trước khi sinh bộ cuối |
| [23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md) | Bộ cuối 320 doanh nghiệp, 1.424.342 hóa đơn, kiểm AR/AP, khóa split và train/evaluate | Cần trạng thái bộ train synthetic mới nhất |

**Phân biệt ba bản kê:** `data/raw/MANIFEST.json` mô tả 2 nguồn thô hiện có;
[manifest 8 nguồn ngày 14/10](MANIFEST_RAW_8_SOURCES_2026-10-14_ARCHIVE.json)
là lịch sử; [worlds_registry.csv](worlds_registry.csv) kê 61 World cũ, hiện
chỉ còn cấu hình/báo cáo ở các thư mục đó, không có Parquet giao dịch. Registry
này **không** phải danh sách World dùng để train cuối. Split cuối đọc ở
[cohort JSON](../../data/synthetic/v3_final_20261027_cohort.json).
[vn_listed_inputs.json](vn_listed_inputs.json) lưu số chép từ ba BCTC để tái tính
DSO/DPO, chưa có người kiểm tra thứ hai.

Vị trí dữ liệu và mã: `data/raw/`, `data/interim/`, `data/synthetic/`,
`agent1/data/`, `agent1/synth/`, `scripts/crawl.py`, `scripts/build_worlds.py`.
Thẻ dữ liệu cô đọng: [../DATA_CARD.md](../DATA_CARD.md).
