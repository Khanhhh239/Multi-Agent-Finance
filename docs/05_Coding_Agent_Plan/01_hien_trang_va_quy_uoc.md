# 1. Hiện trạng, môi trường và quy ước

## 1.1 Bản đồ mã (đã có)

```
agent1/
  paths.py            ROOT/DATA/RAW/INTERIM/PROCESSED/SYNTH/OUT (tự tạo thư mục)
  threads.py          NT = AGENT1_THREADS (mặc định 6)
  calendar_vn.py      T5: holiday_set, business-day, vat_deadline, cit_*, si_deadline, license_fee_deadline, min_wage, vat_rate,
                      obligation_schedule(firm, start, end, payroll_by_month, vat_by_period, cit_by_quarter)
  synth/
    world.py          WorldConfig, World(cfg).run(), generate(cfg)  — máy phát (6 lớp L0..L5)
    names.py          tên DN/khách, MST (checksum), counterparty_variant, transfer_memo, einvoice_symbol
    einvoice.py       invoice_to_xml, write_xml_samples, parse_xml
    fidelity.py       value_outcomes, structural_signature, report(world_dir, reference_csv)
    calibration_vn.json  đích Atradius (chép nguyên)
  data/
    real_loaders.py   customer_invoices, bpi2019, online_retail_weekly, berka_weekly, berka_loans, sba_7a, uk_ppr_stats
    schema.py         quality_gate, inject_errors
  models/
    features.py       FEATURES (46), SnapshotBuilder(invoices, payments, promises, label_col).snapshot(T)/.build(cutoffs, ...), add_labels
    t1.py             HazardGBM, HazardLR, QuantileLGBM, AFT, CureGBM, expand, pmf_from_hazard, quantiles_from_hazard,
                      expected_days_from_hazard, b0/b1/b1_dist, cqr_fit/cqr_apply, evaluate_quantiles, weekly_cdf_from_quantiles, collections_by_week
    t4_revenue.py     GlobalQuantileLGBM, make_rows, baseline_rows, chronos_predict, spl
    t6_cash.py        simulate, collection_kernel, ACI
    t7_changepoint.py residual_stream (PIT/MAD), cusum, page_hinkley, bocpd, naive, GRIDS, run_detector
    t9_recon.py       Reconciler(candidates, fit, assign_customers, allocate), rule_exact_amount, rule_memo_regex, score_links
  eval/metrics.py     pinball, coverage, interval_score, crps_*, brier, logloss, ece, ibs_weekly, c_index, wape, bootstrap_ci
scripts/
  crawl.py            tải dữ liệu thật + MANIFEST
  build_worlds.py     hiệu chỉnh + dựng src/tgt/sens_uk/sens_coface
  run_t1.py           exp A,B,C,D,E (E gồm F) ; run_t2_t3.py ; run_t4.py ; run_t6.py ; run_t7.py ; run_t9.py
  run_all_t1.sh, run_rest.sh   chạy tuần tự
  make_report.py      gom CSV → docs/RESULTS_TABLES.md
  roi_calc.py         ROI (docs/03_Evaluation/06)
  realism_audit.py    kiểm tra bộ hoá đơn (từ Phần 7)
tests/test_t0_t5.py   15 kiểm thử
data/{raw,interim,processed,synthetic}/  outputs/{t1,t2_t3,t4,t6,t7,t9}/  docs/
```

## 1.2 Môi trường

- Windows 11, 15,7 GB RAM, 20 luồng CPU, GPU RTX 4050 (6 GB) — **chưa dùng GPU**.
- Python mặc định của máy hỏng; dùng venv `Agent1/.venv` (tạo từ Python 3.12 của `codex-primary-runtime`):
  `.venv/Scripts/python.exe`. Gói: numpy 2.5, pandas 3.0, lightgbm 4.7, xgboost 3.4, scikit-learn 1.9, scipy 1.18, holidays 0.106, rapidfuzz 3.14, ruptures 1.1.10, statsmodels 0.15, pyarrow, torch 2.14 (CPU), chronos-forecasting 2.3, transformers 5.19.
- Cần ghim phiên bản vào `requirements.txt` (việc WP-0.1).
- Máy dùng chung với tiến trình khác → luôn `AGENT1_THREADS≤6`, `OMP_NUM_THREADS≤4`.

## 1.3 Dữ liệu cần tái tạo trên máy mới

```bash
python scripts/crawl.py --only wdi_vn,oxcgrt,uk_ppr,online_retail_ii,berka,customer_invoices,sba_7a,bpi2019   # ~1,5 GB
python scripts/build_worlds.py --calibrate --worlds src,tgt,sens_uk,sens_coface                               # vài giờ khi máy bận
```
Cache chuẩn hoá (`data/interim/*.parquet`) tạo tự động lần đầu gọi `real_loaders.*`.
Snapshot cache: `data/processed/snap_*.parquet` — xoá khi đổi `FEATURES`.

## 1.4 Quy ước

| Chủ đề | Quy ước |
|---|---|
| Ngày | `pandas.Timestamp`, múi giờ naive; ngày làm việc theo `calendar_vn` |
| Nhãn | `remaining` = ngày từ T đến ngày tiền về (inf nếu không bao giờ); `event`, `time_obs`, `bad_known` (xem `add_labels`) |
| Tiền | VND (số thực); đặc trưng tiền luôn chia trung vị công ty |
| Chân trời | K=13 tuần; cap 120 ngày |
| Tên cột chuẩn | xem 02_Data/01 §1.5 |
| Seed | mọi script nhận seed qua cấu hình; ghi vào CSV đầu ra |
| Kết quả | CSV tại `outputs/<module>/`; tên có tiền tố thí nghiệm |
| Code | không viết mới nếu có hàm tương đương; thêm tham số thay vì sao chép |

## 1.5 Lỗi/điểm lạ đã biết (xử lý trong các WP)

| # | Vấn đề | Nơi | WP |
|---|---|---|---|
| L1 | `DH-GBM+CQR` ≡ `DH-GBM` (q̂≈0, CQR không thu hẹp) | `run_t1.py::exp_A`, `t1.cqr_*` | WP-1.3 |
| L2 | CDF xấp xỉ từ 3 phân vị thiên lợi hazard | `t1.weekly_cdf_from_quantiles` | WP-1.1 |
| L3 | SBA `EXEMPT` làm nhãn âm giả; AUC phóng đại | `real_loaders.sba_7a`, `run_t2_t3.py` | WP-2.1 |
| L4 | T3: LightGBM không thắng EB | `run_t2_t3.py::t3_synth` | WP-2.3 (giữ EB) |
| L5 | Thí nghiệm B/E/T6 chưa có kết quả đã kiểm | `run_t1.py`, `run_t6.py` | WP-3, WP-5 |
| L6 | `run_t6.py` có dòng thừa `Xr, Yr, _, _ = R1_build = (None,…)` rồi lại `build` — dọn | `run_t6.py` | WP-5.1 |
| L7 | AFT σ nhạy; hiện 0,3 nhưng exp C chạy với 0,6 | `t1.AFT` | WP-1.5 |
| L8 | BPI: DH-GBM kém vì không có hạn | exp C | WP-1.6 (ghi nhận / đặc trưng thay thế) |
| L9 | T9 ML precision 0,78 | `t9_recon.allocate` | WP-4 |
| L10 | T7 báo giả 0,63 > 0,5 trên giữ lại | `t7_changepoint` | WP-7 |
| L11 | Ước lượng tốc độ máy phát lớn chưa đo | `world.py` | WP-D1 |
| L12 | Lời hứa tổng hợp quá "sạch" (σ=1,5 ngày) | `world.promises` | WP-8.1 |
| L13 | Phương sai trễ do danh tính khách thấp (0,20 vs 0,60 ERP thật) | `world.make_customers` | WP-D2.3 |
| L14 | ~50% hoá đơn COD (theo số lượng) quá cao | `WorldConfig.cod_mult` | WP-D2.4 |
| L15 | Một số mã xử lý `str(payday)` — kiểu hỗn hợp int/'eom' | `world.py`, `calendar_vn.py` | WP-D1 |

## 1.6 Lệnh kiểm tra nhanh trạng thái

```bash
.venv/Scripts/python.exe -m pytest -q tests                              # 15 passed
.venv/Scripts/python.exe -c "from agent1.synth.world import *; print(WorldConfig())"
ls data/synthetic/*/invoices.parquet outputs/t1 outputs/t4 outputs/t7 outputs/t9
```
