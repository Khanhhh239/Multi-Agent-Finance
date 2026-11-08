# 02 · Data — Dữ liệu hiện còn và lịch sử kiểm chứng

**Cập nhật 06/11/2026.** Cohort dùng cho T1 v5/v6 là
[cohort v4](../../data/synthetic/v4_shortpay_4shock_20261028_cohort.json),
được mô tả trong [báo cáo v4](25_V4_SHORTPAY_4SHOCK_RETRAIN_2026-10-28.md).
GO kỹ thuật của synthetic không xác nhận phân phối SME Việt Nam hoặc cho phép pilot thật.

## Dữ liệu hiện còn trong phạm vi nghiên cứu

- `data/raw/MANIFEST.json`: WDI Việt Nam và OxCGRT; `data/synthetic/calibration_fit.json` còn giữ.
- Cohort v4: 8 World chính và 1 smoke; 2 holdout của v6 ngày 01/11.
- Practical v6: 2 World augmentation supported và 4 fresh; unified v2: 4 holdout.
- `data/T0/` còn dữ liệu/bằng chứng lịch sử riêng. **Toàn bộ `data/T1/` đã xóa** theo yêu cầu.
- Dữ liệu/cohort v3, lifecycle, hard-case cũ và các thư mục chỉ còn config/báo cáo đã xóa.

Output release-gate và các bộ v3 candidate/final/pilot/readiness/inference đã
xóa theo yêu cầu. Các báo cáo riêng về ứng viên, bộ train cuối và inference
v3 cùng hồ sơ dọn dữ liệu cũng đã xóa. Artifact v4, v5/v6, practical v6 và
unified v2 vẫn giữ; dùng các nguồn hiện hành bên dưới.

## Chiến lược và đặc tả dùng tiếp

| Tài liệu | Nội dung |
|---|---|
| [Chiến lược dữ liệu](01_chien_luoc_du_lieu.md) | Ba tầng bằng chứng, cách kết hợp nguồn, lược đồ T0 |
| [Nguồn thật từng dùng](02_du_lieu_that_dung.md) | Nguồn, cột, vai trò và hạn chế của các thí nghiệm trước; không phải tồn kho hiện tại |
| [Nguồn đã loại/hoãn](03_du_lieu_khong_dung.md) | Lý do khảo sát để tránh làm lại và điều kiện xem xét sau này |
| [Máy phát, runner và quy mô](04_may_phat_tong_hop.md) | Kiến trúc, as-of, manifest/split, held-out và mở rộng; đã gộp tài liệu quy mô/runner rời |
| [Danh mục hard case](05_hard_cases.md) | Đặc tả tình huống và cách đo; giữ đặc tả không có nghĩa các World cũ còn trên đĩa |
| [Bộ đánh giá](07_bo_danh_gia.md) | Benchmark từng năng lực, đầu-cuối và quy tắc niêm phong |
| [Tài liệu tham khảo](08_tai_lieu_tham_khao.md) | Nguồn hiệu chỉnh, phương pháp và mức độ đã đọc |
| [Bộ v4 sau sửa short-pay](25_V4_SHORTPAY_4SHOCK_RETRAIN_2026-10-28.md) | Cohort nguồn cho v5/v6, retrain, inference và giới hạn |

## Lịch sử có giá trị đối chiếu

| Tài liệu | Lý do giữ |
|---|---|
| [Đối chiếu BCTC niêm yết](09_vn_listed_spot_check.md) | Số DSO/DPO độc lập và giới hạn mẫu; PDF gốc cần tải lại |
| [Realism v2 và C2ST](10_realism_v2.md) | Giải thích khác biệt thiết kế/hành vi và vì sao dừng chỉnh theo C2ST |
| [Kế hoạch shock 25/10](11_KE_HOACH_SOC_THI_TRUONG_TICH_HOP_2026-10-25.md) | Nguồn thiết kế, giả thuyết và phần chưa triển khai; không phải kết quả đã chạy |
| [Kiểm toán máy phát cũ](12_KIEM_TOAN_KICH_BAN_SINH_DU_LIEU_CU_2026-10-25.md) | Nguyên nhân lỗi nhân quả/kế toán trước sửa |
| [Kiểm toán sau sửa ban đầu](14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md) | Số đo trước sửa vòng đời và quyết định NO-GO tại thời điểm đó |
| [Tổng kết máy phát và sửa vòng đời](18_TONG_KET_KIEM_CHUNG_PHAT_TRIEN_SYNTHETIC_DATA_2026-10-26.md) | Lịch sử sửa lỗi; đã gộp cơ chế và số đo riêng của báo cáo 15 |
| [Kiểm toán mười World](19_KIEM_TOAN_CHI_SO_10_WORLD_2026-10-26.md) | Một nơi cho định nghĩa, bảng ba/mười World, ngành và từng seed; đã gộp báo cáo 16 và phần nhiều seed của 17 |

[Manifest 8 nguồn ngày 14/10](MANIFEST_RAW_8_SOURCES_2026-10-14_ARCHIVE.json)
và [registry 61 World cũ](worlds_registry.csv) là bản kê lịch sử, không phải
nguồn đang có hoặc split train hiện tại. [vn_listed_inputs.json](vn_listed_inputs.json)
giữ số chép từ BCTC để tính lại DSO/DPO, chưa có kiểm tra chép số độc lập thứ hai.

Mã: `agent1/data/`, `agent1/synth/`, `scripts/`. Thẻ dữ liệu
[DATA_CARD](../DATA_CARD.md) là mô tả giai đoạn cũ; trạng thái còn trên đĩa dùng mục đầu trang này.
