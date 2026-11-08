# Invoice Prediction (T1) — thời điểm thanh toán từng hoá đơn, end-to-end

Bám `invoice_forecast.ipynb`, tách gọn thành `data / metrics / model / xử lý`. Chỉ chạy data thật.

## T1 checklist trong repo này
- [x] LightGBM quantile Q10/Q50/Q90 (`model.py`, contest-style params)
- [x] Ensemble + tuning (`ensemble.py`: grid C0/C1/C2 + bagging seeds)
- [x] Survival rời rạc + censor nhân tạo N1=30/N2=60 (`survival.py`)
- [x] Chia theo thời gian + rolling cutoff W-FRI (`features.py`)
- [x] Hiệu chỉnh VN: Tết/lễ/cuối tháng/quý/weekend + bias theo aging (`vn.py`)
- [x] Test bộ thứ 2 tương tự: `second --input2` (MAE vs B1 + PSI)

## Cấu trúc
```
invoice_prediction/
  run.py
  requirements.txt
  data/dataset.csv            # data thật (bắt buộc)
  src/invoice_pred/
    config.py                 # N1/N2, SURVIVAL_BINS, VN holidays, ensemble grid
    data_loader.py            # load_raw
    preprocessing.py          # standardize + quality gate
    features.py               # as-of T, history, rolling snapshot
    baseline.py               # B1, B1R
    metrics.py                # pinball/MAE/coverage/segment/gate
    model.py                  # LGBM quantile single
    ensemble.py               # tune + seed-bagging
    survival.py               # classifier P(paid<=N) + expected days
    vn.py                     # VN feats + group bias + PSI
    plots.py
  outputs/  models/  data/processed/
```

## Chạy
```powershell
pip install -r requirements.txt
python run.py all --input data/dataset.csv          # baseline T1
python run.py full-t1 --input data/dataset.csv      # end-to-end T1

# từng bước:
python run.py preprocess --input data/dataset.csv
python run.py baseline
python run.py train [--no-stack]
python run.py tune                                  # grid C0/C1/C2 -> outputs/tune_results.csv
python run.py ensemble [--seeds 3]                  # bagging -> ensemble_predictions.csv
python run.py survival                              # P(paid<=30/60/90) + expected -> survival_predictions.csv
python run.py vn                                    # bias aging + Tet stats -> vn_metrics.csv
python run.py second --input2 data/dataset_ledger2.csv
python run.py evaluate
python run.py plot
```

## Output
- `data/processed/{rolling_snapshot_features,baseline_snapshot_predictions,lgbm_snapshot_predictions,ensemble_predictions,survival_predictions}.csv`
- `outputs/{metrics_summary,segment_metrics,tune_results,vn_metrics,vn_calibrated_test}.csv`
- `outputs/plots/*.png` + `models/{lgbm_q*.txt,ensemble_qbag.pkl,survival_clf.pkl}`

## Gate T1
- MAE gain vs B1 >=10% cả 3 tổng hợp row / mean-of-cutoffs / unique
- coverage [P10,P90] 75-85%, crossing <5%
- survival: AUC@30/60 + Brier; ensemble lift vs single; VN gain; PSI ledger2
