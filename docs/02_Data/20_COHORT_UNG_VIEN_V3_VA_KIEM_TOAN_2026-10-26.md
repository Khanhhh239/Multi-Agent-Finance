# Cohort v3 ứng viên 2019–2025 và kiểm toán trước khóa split (26/10/2026)

**Cập nhật 27/10/2026:** cohort này dùng RNG v1 và được giữ làm đối chứng.
`v3_candidate_r3_20261026` là ứng viên tiếp theo của vòng kiểm 26/10, không còn
là bộ mới nhất; xem [báo cáo 21](21_KIEM_CHUNG_AR_AP_VA_DO_BEN_SEED_2026-10-26.md)
để đối chiếu vòng đó. Bộ train synthetic cuối là `v3_final_20261027` trong
[báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md).

## Phạm vi chạy

Đã chạy `scripts/build_final_train.py` với prefix `v3_candidate_20261026`, cửa sổ
01/01/2019–31/12/2025, origin 01/07/2024, 24 doanh nghiệp/World, hai World train,
một validation, hai test, base seed 97100. Dừng ở `--stop-after audit_worlds`:
**chưa khóa cohort, chưa train, chưa đánh giá kết cục test**. World smoke dùng một
doanh nghiệp. Năm World chính dùng seed 97101–97105, không trùng pilot cũ.

Nguồn calibration, OxCGRT và WDI đều có SHA-256 trong manifest. Commit ghi nhận là
`70c0ceb0653161f70535b4c8b9fb3cee63b7405f`; hash toàn bộ mã Python của lần sinh
này là `ca205ab5749a7476d8083fc0a528ed745e9a8b6bcc52f419673c87c07f1b7a56`.
Hash nguồn và mã lưu đầy đủ trong
[`readiness.json`](../../outputs/data/v3_candidate_20261026/readiness.json) và manifest
của từng World. Mã working tree còn thay đổi, nên đây là phiên bản **ứng viên**,
chưa phải bản phát hành bất biến.

## Kết quả cổng kỹ thuật

`readiness.json` báo **PASS**: cửa sổ đủ 2019–2025, hash OxCGRT/WDI có mặt, tỷ số
doanh thu thuần 2025/2019 thấp nhất ở train/validation là **1,364** (ngưỡng chặn
sụp đổ nội bộ: 0,6). Train/validation có episode cầu, cung, giá; episode tín dụng
chỉ ở test. Test A có 15 tuần tín dụng hoạt động trong cửa sổ đánh giá; Test B
giá + tín dụng có 16 tuần. Cả sáu World kể cả smoke đều có 12 Parquet, config và
manifest riêng. Lúc tạo manifest, runner đã chạy `validate_world` và ghi SHA-256
từng bảng. Cổng này không kiểm độ sát dữ liệu Việt Nam.

Kiểm lại sau lần sinh: **72/72 hash Parquet** của sáu World khớp manifest;
hash mã và ba nguồn hiện tại khớp cả sáu manifest.

Kiểm toán sâu **chỉ đọc ba World train/validation** bằng `one_world()` trong
`scripts/audit_existing_world_metrics.py`; bảng 147 dòng World × năm × ngành ở
[`yearly_industry_metrics.csv`](../../outputs/data/v3_candidate_20261026/yearly_industry_metrics.csv).
Hàm này xác minh lại manifest/hợp đồng và tái dựng AR tại 31/12; sai khác với
`invoices.remaining_amount` không vượt 1,01 VND. Kiểm miền 0–1 của các tỷ lệ
và thứ tự phân vị tiền, ngày thu trên 147 dòng không phát hiện lỗi. Không đọc
kết cục hóa đơn ở hai World test.

| World | Seed | Hóa đơn cả kỳ | Doanh thu 2025/2019 | Bán chịu theo giá trị 2025 | Nợ quá hạn / AR mở cuối 2025 | Ngày số dư âm 2025 |
|---|---:|---:|---:|---:|---:|---:|
| train_000 | 97101 | 72.308 | 1,364 | 66,2% | 33,4% | 10,3% |
| train_001 | 97102 | 113.593 | 2,668 | 64,4% | 65,4% | 4,5% |
| validation_000 | 97103 | 82.281 | 2,110 | 70,8% | 40,5% | 10,1% |

`train_001` dùng đuôi trễ `coface` theo cấu hình runner; `train_000` dùng `uk`,
validation dùng `atradius`. Tỷ lệ nợ quá hạn 65,4% của `train_001` vượt mức lớn nhất
59,1% của 10 World đối chứng không episode mới trong
[báo cáo 19](19_KIEM_TOAN_CHI_SO_10_WORLD_2026-10-26.md). Đây là **cảnh báo phân phối**,
không đủ để kết luận lỗi: các cấu hình đuôi trễ và shock của hai lô khác nhau.
Doanh thu 2025/2019 của `train_001` và validation cũng cao hơn dải 0,886–1,886
của 10 World đối chứng. Ở `train_001`, cả sáu ngành đều tăng, tỷ số từ 1,709
đến 3,896; nợ quá hạn / AR mở đã là 71,2% trong năm 2019. Nhân tố chung
`macro.common_factor` trung bình đổi từ −0,655 (2019) sang 0,035 (2025), đồng
thời với mức tăng doanh thu, nhưng chưa chứng minh đó là nguyên nhân. Validation
có riêng ngành nhựa/cao su tăng 4,432 lần trên tám doanh nghiệp. Cần kiểm tiếp
theo từng công ty/tuần và đối chứng giữ cấu trúc doanh nghiệp nhưng đổi đường
vĩ mô trước khi quyết định giữ hoặc sửa tham số.

## Quyết định sau bước ứng viên

**Đạt cổng kỹ thuật để tiếp tục kiểm chứng; chưa GO cho bộ train cuối.** Chưa có
đối chiếu AR/AP SME Việt Nam độc lập với cùng định nghĩa, chưa kiểm độ nhạy qua
nhiều seed cho từng kịch bản held-out, và chưa đánh giá mô hình. Ngưỡng doanh thu
0,6 chỉ bắt xu hướng sụp đổ, không xác nhận mức tăng 2,668 hoặc tỷ lệ nợ quá hạn
65,4% là hợp lý. Giữ nguyên prefix này làm bằng chứng ứng viên; nếu sửa máy phát
hoặc cấu hình, sinh bằng prefix mới và kiểm lại trước khi khóa split.
