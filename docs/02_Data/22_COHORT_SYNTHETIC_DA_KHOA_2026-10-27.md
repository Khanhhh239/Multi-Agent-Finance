# Cohort synthetic đã khóa sau sửa RNG, AP và regime vĩ mô (27/10/2026)

**Cập nhật:** đây là cohort ứng viên 24 doanh nghiệp/World. Bộ train synthetic
cuối đã sinh ở quy mô lớn hơn trong [báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md).

## Quyết định và phạm vi

**GO kỹ thuật cho bộ train synthetic theo giả định đã công bố.** Cohort
`v3_candidate_r5_20261026` đã sinh, kiểm, khóa split, train và evaluate. Đây là
World mô phỏng; **không có bằng chứng bộ dữ liệu đại diện phân phối AR/AP của
SME Việt Nam**. Người dùng không có ledger SME thực để đối chiếu cùng định
nghĩa, nên không dùng kết quả này để tuyên bố độ sát thực tế hoặc hiệu năng
trên dữ liệu doanh nghiệp thật.

## Ba thay đổi

1. [`build_final_train.py`](../../scripts/build_final_train.py) chạy `rng_version=3`
   trực tiếp. Không cần override thủ công như cohort r3. Hai train, hai
   validation và hai test dùng cùng hash mã.
2. [`world.py`](../../agent1/synth/world.py) gán `supplier_payment_mode` ở mức
   doanh nghiệp bằng luồng RNG riêng. Xác suất **20% trả ngay** là **giả định
   mô phỏng**, không phải ước lượng SME Việt Nam. Với nhóm này, ngày mua, ngày
   đến hạn và ngày trả trùng nhau. Nhóm mua chịu có kỳ hạn dương; bảng
   `inventory_weekly` lưu `supplier_due_date` và `supplier_pay_date` riêng.
   [`contracts.py`](../../agent1/data/contracts.py) kiểm thứ tự ngày, mode và
   đối soát tiền chi nhà cung cấp.
3. [`scenario_protocol.json`](../../outputs/data/v3_candidate_r5_20261026/scenario_protocol.json)
   được ghi **trước khi sinh World**. Train/validation ordinal chẵn là
   `baseline`, lẻ là `stress`; hai test là baseline với episode tín dụng
   held-out. Baseline chặn nhân tố chung hàng tuần trong [−0,8; 0,8]. Stress
   áp trần âm hình sin trong năm cuối: đường đã âm hơn trần được giữ nguyên,
   tránh cộng dồn một cú sốc vào seed vốn rất xấu. Regime là **đầu vào kịch
   bản**, không phải nhãn gán sau khi xem doanh thu.

| Vai trò | World | Seed | Regime |
|---|---|---:|---|
| Train | `train_000` | 94318 | Baseline |
| Train | `train_001` | **94319** | **Stress** |
| Validation | `validation_000` | 94320 | Baseline |
| Validation | `validation_001` | 94321 | Stress |
| Test | `test_000`, `test_001` | 94322, 94323 | Baseline; credit held-out |

## Kiểm sau sinh

Mã nguồn SHA-256:
`a0dbcbe6df9c7552da84c1a043e56e02d1c9542ae0daf8a793f4b4d45dcc49cd`.
**84/84 Parquet** của smoke + sáu World khớp manifest. Cổng
[`readiness.json`](../../outputs/data/v3_candidate_r5_20261026/readiness.json)
PASS: nguồn vĩ mô, cửa sổ 2019–2025, ngưỡng doanh thu baseline và hai
kịch bản held-out. Bộ train/validation có 96 doanh nghiệp; **22/96** thuộc
nhóm trả ngay và **0/22** có AP mở cuối 2025. Toàn bộ 74 doanh nghiệp mua
chịu có AP mở dương. Số 22/96 là tỷ lệ hiện thực hóa của xác suất giả định
20%, không phải tỷ lệ thị trường.

| World | Doanh thu 2025/2019 | 2025/2024 | AR quá hạn/AR mở | DN AP dương | AP quá hạn/AP mở |
|---|---:|---:|---:|---:|---:|
| Train baseline | 1,657 | 1,031 | 34,7% | 20/24 | 6,0% |
| Train stress, seed 94319 | 0,976 | **0,389** | **65,1%** | 19/24 | 11,6% |
| Validation baseline | 1,278 | 0,976 | 45,4% | 18/24 | 9,2% |
| Validation stress | 1,785 | 0,959 | 26,3% | 17/24 | 7,1% |

Nguồn tính: [`world_summary.csv`](../../outputs/data/release_gate_audit_20261026/r5_candidate/world_summary.csv),
[`firm_2025_ar_ap.csv`](../../outputs/data/release_gate_audit_20261026/r5_candidate/firm_2025_ar_ap.csv)
và `macro_ap_year.csv` cùng thư mục. AP chỉ gồm mua hàng nhà cung cấp;
không gồm lương, thuế, vay và chi phí khác. `train_001` vẫn là trường hợp
stress mạnh; không xóa seed 94319 hoặc trình bày mức AR 65,1% như baseline.
World validation stress có doanh thu gần ổn định dù đầu vào vĩ mô bất lợi;
regime không ép mọi kết quả đầu ra cùng chiều.

Bản `r4` thử cú sốc cộng thêm làm seed 94319 giảm doanh thu 2025/2024 còn
0,205 và AR quá hạn/AR mở 76,2%; kiểm này bộc lộ cơ chế cộng dồn. Bản `r5`
giữ đường vĩ mô âm sẵn có, kết quả tương ứng là 0,389 và 65,1%. `r4` là
World thử, không nằm trong cohort đã khóa.

## Split, model và giới hạn

[`v3_candidate_r5_20261026_cohort.json`](../../data/synthetic/v3_candidate_r5_20261026_cohort.json)
đã khóa sáu World theo vai trò, SHA-256 cohort
`fd210fb63578d9277d03a139da6569d7c41446409a20c00e301fad73d3f9150d`.
[`train.json`](../../outputs/data/v3_candidate_r5_20261026/train.json) ghi
50.000 dòng train, 30.265 sự kiện, 200 vòng và SHA-256 model
`0e21c518c32053d8264ef8620bf2d02eba844d2b38488bcac18ce02b2f429c7e`.
Mô hình DH-GBM có độ bao phủ 80% là 0,897/0,900 ở hai validation và
0,897/0,905 ở hai test; xem
[`evaluation.csv`](../../outputs/data/v3_candidate_r5_20261026/evaluation.csv).
Đây là đánh giá **nội bộ trên synthetic**, không phải kiểm định với SME thật.

Mã nguồn hiện có nhiều sửa đổi chưa commit. Manifest lưu base commit và hash
toàn bộ mã Python; để phát hành/tái lập ngoài workspace này cần lưu nguyên
trạng mã có đúng hash trên. Nếu thay mã, runner sẽ chặn dùng lại cohort đã
khóa. Các giới hạn còn lại: xác suất trả ngay 20%, trần baseline/stress và
quy tắc thanh toán AP đều là giả định; chưa có ledger độc lập để hiệu chỉnh
theo ngành/quy mô hoặc xác nhận tần suất cú sốc vĩ mô.
