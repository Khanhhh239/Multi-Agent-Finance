# Bộ dữ liệu train synthetic cuối đã sinh (27/10/2026)

## Quyết định và phạm vi

**GO kỹ thuật cho dữ liệu train synthetic theo các giả định đã công bố.**
`v3_final_20261027` là cohort mới, sinh đủ giai đoạn 2019-01-01 đến
2025-12-31, đã qua hợp đồng dữ liệu, readiness, khóa split, train và evaluate.
Đây không phải bằng chứng về phân phối AR/AP của SME Việt Nam: không có ledger
SME độc lập, cùng định nghĩa để đối chiếu theo ngành và quy mô.

## Cấu hình đã định trước khi sinh

[`scenario_protocol.json`](../../outputs/data/v3_final_20261027/scenario_protocol.json)
được ghi trước World đầu tiên. Runner dùng RNG v3, seed gốc 95317, 40 doanh
nghiệp mỗi World và xác suất doanh nghiệp trả nhà cung cấp ngay 20%. **20% là
giả định mô phỏng, không phải ước lượng thị trường Việt Nam.** Train và
validation ordinal chẵn là baseline, lẻ là stress; hai test là baseline với
episode tín dụng held-out. Không loại World sau khi xem kết quả.

| Split | World | Seed | Regime | Doanh nghiệp | Hóa đơn |
|---|---|---:|---|---:|---:|
| Train | `train_000` | 95318 | Baseline | 40 | 146.848 |
| Train | `train_001` | 95319 | Stress | 40 | 166.407 |
| Train | `train_002` | 95320 | Baseline | 40 | 222.342 |
| Train | `train_003` | 95321 | Stress | 40 | 173.707 |
| Validation | `validation_000` | 95322 | Baseline | 40 | 173.917 |
| Validation | `validation_001` | 95323 | Stress | 40 | 162.263 |
| Test | `test_000` | 95324 | Baseline, credit held-out | 40 | 152.162 |
| Test | `test_001` | 95325 | Baseline, price + credit held-out | 40 | 226.696 |
| **Tổng chính** | **8 World** | | | **320** | **1.424.342** |

Smoke tách riêng có 1 doanh nghiệp và 4.302 hóa đơn. Toàn bộ 9 World có
**108/108 bảng Parquet** và manifest. Mã nguồn SHA-256:
`a0dbcbe6df9c7552da84c1a043e56e02d1c9542ae0daf8a793f4b4d45dcc49cd`.
Nguồn calibration, OxCGRT và WDI có hash trong
[`v3_final_20261027_cohort.json`](../../data/synthetic/v3_final_20261027_cohort.json),
cohort SHA-256 `b195a4abed65f6f33e9f17b5e3be512dda625e19f703318a4acc76c564e392b9`.

## Kiểm sau sinh

[`readiness.json`](../../outputs/data/v3_final_20261027/readiness.json) **PASS**:
cửa sổ đầy đủ, nguồn vĩ mô hiện diện, doanh thu baseline 2025/2019 thấp nhất
1,854 > ngưỡng nội bộ 0,6; stress thấp nhất 0,957 > 0; cả hai kịch bản tín dụng
held-out hiện diện. Đây là cổng hợp lệ nội bộ, không đo độ sát SME thật.

[`world_summary.csv`](../../outputs/data/release_gate_audit_20261026/final_20261027/world_summary.csv)
và các bảng kiểm toán cùng thư mục ghi kết quả train/validation:

| World | Doanh thu 2025/2019 | 2025/2024 | AR quá hạn/AR mở | DN trả ngay | AP quá hạn/AP mở |
|---|---:|---:|---:|---:|---:|
| Train baseline 000 | 1,854 | 0,880 | 35,8% | 5/40 | 7,7% |
| Train stress 001 | 1,364 | 0,851 | 50,9% | 3/40 | 3,3% |
| Train baseline 002 | 2,011 | 1,189 | 28,1% | 6/40 | 7,7% |
| Train stress 003 | 1,717 | 0,961 | 26,0% | 13/40 | 7,8% |
| Validation baseline 000 | 2,123 | 1,087 | 41,5% | 7/40 | 7,1% |
| Validation stress 001 | 0,957 | 0,859 | **76,6%** | 11/40 | 5,6% |

Trong 240 doanh nghiệp train/validation, **45** thuộc nhóm trả ngay và **0/45**
có AP nhà cung cấp mở cuối 2025; cả 195 doanh nghiệp mua chịu có AP mở. Trên
toàn bộ 320 doanh nghiệp chính có **55** nhóm trả ngay (17,2% hiện thực hóa từ
xác suất giả định 20%). AP ở đây chỉ gồm khoản mua hàng nhà cung cấp, không gồm
lương, thuế, khoản vay hay chi phí khác. Bảng `inventory_weekly` lưu riêng ngày
mua, ngày đến hạn và ngày trả; hợp đồng dữ liệu đã kiểm thứ tự ngày và đối soát
tiền chi. AR quá hạn cao ở validation stress là một kết quả stress, không phải
tỷ lệ SME Việt Nam.

## Train và đánh giá

[`train.json`](../../outputs/data/v3_final_20261027/train.json) ghi **704.334
snapshot train**, **435.615 sự kiện**, 200 vòng. `max_rows=10.000.000` nên không
cắt mẫu các snapshot này. SHA-256 của
[`model.txt`](../../outputs/data/v3_final_20261027/model.txt) là
`8d5f9b74f71f17e3289128a0071ca1044df5e55d4edfe670e8148f1a08b9d727`.

[`evaluation.csv`](../../outputs/data/v3_final_20261027/evaluation.csv) ghi độ
bao phủ khoảng 80% của DH-GBM: validation baseline **0,907**, validation stress
**0,913**, test credit **0,921**, test price + credit **0,916**. Đây là đánh giá
trên synthetic. Độ bao phủ cao hơn 0,8 cho thấy khoảng dự báo còn rộng/chưa
được hiệu chỉnh đến mức danh nghĩa; không diễn giải thành hiệu năng trên doanh
nghiệp thật. Model là artifact kiểm thử đi kèm cohort, chưa phải model triển
khai thực tế.

Để dùng dữ liệu, đọc danh sách World và vai trò từ cohort JSON đã khóa ở trên;
mỗi thư mục `data/synthetic/v3_final_20261027_<role>_<ordinal>/` có 12 bảng
Parquet, `config.json` và `manifest.json`. Chỉ các World `train_*` dùng để fit;
`validation_*` dùng đánh giá/chọn cấu hình; `test_*` chỉ dùng đánh giá giữ riêng.
Lệnh runner đã dùng (trong môi trường có đủ package Python):

```powershell
python scripts/build_final_train.py --prefix v3_final_20261027 --start 2019-01-01 --end 2025-12-31 --origin 2024-07-01 --firms 40 --train-worlds 4 --validation-worlds 2 --base-seed 95317 --rounds 200 --max-rows 10000000 --stop-after evaluate
```

Khi sinh dữ liệu, mã Python có thay đổi chưa commit; Git commit trong manifest
chỉ là base revision. Khi chuyển bộ dữ liệu sang môi trường khác, phải lưu đúng
trạng thái mã có hash trên. Thay mã sẽ khiến runner chặn dùng lại cohort đã
khóa. [`run_summary.json`](../../outputs/data/v3_final_20261027/run_summary.json)
ghi đầy đủ các bước đã chạy.

**Kiểm tra T0 bổ sung ngày 27/10/2026:**
[`summary.json`](../../outputs/wp0/t0_final_20261027/summary.json) và
[`world_quality.csv`](../../outputs/wp0/t0_final_20261027/world_quality.csv)
ghi cổng chất lượng đạt trên 1.424.342 hóa đơn của 8 World; mẫu 200 XML dựng từ
cohort nhận đủ 66 lỗi chèn có nhãn, không báo nhầm. Đây là kiểm nội bộ trên
synthetic, không phải hóa đơn thật. Công cụ chạy lại ở
[`tools/validate_t0_final.py`](../../tools/validate_t0_final.py).

**Tình trạng provenance khi chuẩn bị commit:** hash mã `agent1/` và `scripts/`
trong workspace là `ad278fb4babf8c2694d1ea35696f5116b9428beba6f9584378b81c9b31c0e876`,
khác hash `a0dbcbe6df9c7552da84c1a043e56e02d1c9542ae0daf8a793f4b4d45dcc49cd`
đã khóa trong cohort. Manifest và Parquet vẫn khớp nhau, nhưng runner phát hành
sẽ không sinh/nhận lại cohort cùng prefix với trạng thái mã hiện tại. Commit mới
chỉ lưu artifact đã sinh và code hiện tại; không chứng minh tái lập bằng code đó.
