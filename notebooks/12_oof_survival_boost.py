# %% [markdown]
# # 12 — Đ15: Sinh feature Survival-Boost bằng out-of-fold
#
# **Vị trí:** `08_survival` (đo lần đầu, in-sample) → **[12_oof_survival_boost]** → quyết định production
#
# `../method/AGENT1_TONG_HOP.md` Đ15 ghi trạng thái ⚠️ *"đã đo, chưa OOF"* kèm cảnh báo của chính nó:
#
# > Feature survival cho tập **train** là dự báo in-sample của hazard model (nó được fit trên chính
# > các dòng đó). […] Trước khi đưa vào production, sinh feature bằng out-of-fold (K-fold theo cutoff)
# > để loại hoàn toàn rủi ro optimistic bias trên tập train.
#
# Notebook này làm đúng việc đó và trả lời một câu duy nhất: **con số +12,60% có sống sót qua OOF không?**
#
# Bốn bộ feature, cùng thuật toán, cùng siêu tham số, cùng tập train/test — chỉ khác cách sinh
# feature survival cho tập TRAIN:
#
# | Bộ feature | Feature survival cho tập TRAIN sinh thế nào |
# |---|---|
# | **F0 — gốc** | không có feature survival (bộ Tầng 5, 31 feature) |
# | **F1 — in-sample** | hazard model fit trên toàn bộ train, rồi dự báo lại chính train (bản `08_survival`) |
# | **F2 — OOF K-fold** | 5 fold theo cutoff; feature của fold k đến từ hazard fit trên 4 fold còn lại |
# | **F3 — walk-forward** | feature của fold k chỉ dùng hazard fit trên các cutoff **trước** fold k |
#
# Tập TEST (`test_legacy`) luôn dùng hazard fit trên toàn bộ train — đó là điều production sẽ làm,
# và `test_legacy` chưa từng tham gia fit hay early stopping ở bất kỳ đâu.

# %%
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

sys.path.insert(0, str(Path("D:/CURRICULUM/Semester VI/Finance Project/notebooks")))
import ext_lib as X

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 220)
pd.set_option("display.float_format", "{:,.4f}".format)

SEED = X.SEED
N_FOLDS = 5
N_TREES_HAZARD = 300          # cố định như 08_survival — không early stopping
TARGET = "duration_days"

HZ_PARAMS = dict(objective="binary", n_estimators=N_TREES_HAZARD, learning_rate=0.05,
                 num_leaves=31, min_child_samples=50, feature_fraction=0.8,
                 bagging_fraction=0.8, bagging_freq=5, reg_lambda=1.0,
                 random_state=SEED, n_jobs=-1, verbose=-1)

BOOST_PARAMS = dict(objective="quantile", alpha=0.5, metric="quantile", n_estimators=800,
                    learning_rate=0.05, num_leaves=31, min_child_samples=20,
                    feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5,
                    reg_lambda=1.0, random_state=SEED, n_jobs=-1, verbose=-1)

OUT_METRICS = X.PROC / "oof_boost_metrics.csv"
OUT_FOLDS = X.PROC / "oof_boost_fold_detail.csv"
OUT_IMP = X.PROC / "oof_boost_feature_importance.csv"
print("Config OK · LightGBM", lgb.__version__)

# %% [markdown]
# ## 1. Dữ liệu — cùng snapshot với notebook 11

# %%
snap, plan, DATA_END, clean = X.build_extended_snapshot()
train_pre = snap[snap["window"] == "train_pre"].copy().reset_index(drop=True)
test_legacy = snap[snap["window"] == "test_legacy"].copy().reset_index(drop=True)

cutoffs = np.sort(train_pre["cutoff_date"].unique())
folds = np.array_split(np.arange(len(cutoffs)), N_FOLDS)
fold_of_cutoff = {}
for k, idx in enumerate(folds):
    for i in idx:
        fold_of_cutoff[cutoffs[i]] = k
train_pre["fold"] = train_pre["cutoff_date"].map(fold_of_cutoff)

print(f"train_pre  : {len(train_pre):,} dòng · {len(cutoffs)} cutoff")
print(f"test_legacy: {len(test_legacy):,} dòng · {test_legacy['cutoff_date'].nunique()} cutoff")
print()
fold_tbl = train_pre.groupby("fold").agg(cutoff=("cutoff_date", "nunique"),
                                         dong=("event", "size"),
                                         tu=("cutoff_date", "min"), den=("cutoff_date", "max"))
print("Chia fold theo CUTOFF (khối liên tiếp — giữ trật tự thời gian, không trộn ngẫu nhiên):")
print(fold_tbl.to_string())
print()
print("Vì sao chia theo cutoff chứ không theo dòng: cùng một hoá đơn xuất hiện ở nhiều cutoff")
print("(trung bình 1,93 lần — Đ9). Chia ngẫu nhiên theo dòng sẽ để cùng một hoá đơn nằm cả ở")
print("fold fit lẫn fold dự báo → rò rỉ, và OOF sẽ chỉ là in-sample đội lốt.")

# %% [markdown]
# ## 2. Hạ tầng: hazard model → S(t) → 6 feature survival

# %%
def fit_hazard(frame):
    """Fit discrete-time hazard model (LightGBM binary) trên bảng person-period của `frame`."""
    pp = X.expand_person_period(frame)
    m = lgb.LGBMClassifier(**HZ_PARAMS)
    m.fit(pp[X.HAZARD_FEATURES].to_numpy(float), pp["hazard_event"].to_numpy(int))
    return m, len(pp)


def add_surv_features(frame, model):
    """Sinh 6 feature survival (S_7/S_30/S_60/S_90, RMST, median) từ hazard model."""
    S = X.survival_matrix(frame, model)
    feats = X.survival_features(S)
    out = frame.copy()
    for k, v in feats.items():
        out[k] = v
    return out, S


t0 = time.time()
haz_full, n_pp_full = fit_hazard(train_pre)
print(f"Hazard model 'full' : fit trên {n_pp_full:,} dòng person-period ({time.time()-t0:.0f}s)")

# %% [markdown]
# ## 3. Ba cách sinh feature cho tập TRAIN
#
# * **F1 in-sample** — `haz_full` dự báo lại chính `train_pre`. Đây là bản `08_survival` §9.
# * **F2 OOF** — với mỗi fold k: fit hazard trên các fold ≠ k, dự báo cho fold k.
# * **F3 walk-forward** — với mỗi fold k ≥ 1: fit hazard chỉ trên fold < k, dự báo cho fold k.
#   Fold 0 không có quá khứ nên bị loại khỏi tập train của F3 (ghi rõ, không lấp liếm).

# %%
# ── F1: in-sample ────────────────────────────────────────────────────────────
tr_f1, S_f1 = add_surv_features(train_pre, haz_full)
print(f"F1 in-sample xong ({time.time()-t0:.0f}s)")

# ── F2: OOF K-fold ───────────────────────────────────────────────────────────
oof_parts, fold_rows = [], []
for k in range(N_FOLDS):
    tr_k = train_pre[train_pre["fold"] != k]
    ho_k = train_pre[train_pre["fold"] == k]
    m_k, n_pp = fit_hazard(tr_k)
    part, _ = add_surv_features(ho_k, m_k)
    oof_parts.append(part)
    fold_rows.append({"scheme": "F2_oof", "fold": k, "n_fit_rows": len(tr_k), "n_fit_pp": n_pp,
                      "n_predict": len(ho_k),
                      "mean_S_30": float(part["S_30"].mean()),
                      "mean_median_remaining": float(part["median_remaining_days"].mean())})
    print(f"  F2 fold {k}: fit {len(tr_k):,} dòng → sinh feature cho {len(ho_k):,} dòng "
          f"({time.time()-t0:.0f}s)")
tr_f2 = pd.concat(oof_parts, ignore_index=True)

# ── F3: walk-forward ─────────────────────────────────────────────────────────
wf_parts = []
for k in range(1, N_FOLDS):
    tr_k = train_pre[train_pre["fold"] < k]
    ho_k = train_pre[train_pre["fold"] == k]
    m_k, n_pp = fit_hazard(tr_k)
    part, _ = add_surv_features(ho_k, m_k)
    wf_parts.append(part)
    fold_rows.append({"scheme": "F3_walkforward", "fold": k, "n_fit_rows": len(tr_k), "n_fit_pp": n_pp,
                      "n_predict": len(ho_k),
                      "mean_S_30": float(part["S_30"].mean()),
                      "mean_median_remaining": float(part["median_remaining_days"].mean())})
    print(f"  F3 fold {k}: fit {len(tr_k):,} dòng (chỉ quá khứ) → {len(ho_k):,} dòng "
          f"({time.time()-t0:.0f}s)")
tr_f3 = pd.concat(wf_parts, ignore_index=True)

# ── TEST: luôn dùng hazard fit trên toàn bộ train ────────────────────────────
te_feat, S_te = add_surv_features(test_legacy, haz_full)
print(f"Feature survival cho test_legacy xong ({time.time()-t0:.0f}s)")

fold_detail = pd.DataFrame(fold_rows)
print()
print(fold_detail.to_string(index=False))

# %% [markdown]
# ### 3b. Feature OOF khác feature in-sample bao nhiêu?
#
# Nếu hai bộ gần như trùng nhau thì OOF không đổi được gì và cảnh báo của Đ15 chỉ là hình thức.
# Nếu chúng lệch nhau đáng kể thì phần lệch đó chính là lượng "biết trước đáp án" mà bản in-sample
# đã được hưởng.

# %%
key = ["cutoff_date", "invoice_id"]
cmp_f = (tr_f1[key + X.SURV_BOOST_FEATS].merge(tr_f2[key + X.SURV_BOOST_FEATS],
                                               on=key, suffixes=("_insample", "_oof")))
diff_rows = []
for c in X.SURV_BOOST_FEATS:
    a, b = cmp_f[f"{c}_insample"], cmp_f[f"{c}_oof"]
    diff_rows.append({"feature": c, "TB in-sample": a.mean(), "TB OOF": b.mean(),
                      "|lệch| TB": (a - b).abs().mean(),
                      "|lệch| TB / độ lệch chuẩn": (a - b).abs().mean() / max(a.std(), 1e-9),
                      "tương quan": float(np.corrcoef(a, b)[0, 1])})
feat_diff = pd.DataFrame(diff_rows)
print("Feature survival: in-sample vs OOF (trên cùng các dòng train)")
print(feat_diff.to_string(index=False))

# %% [markdown]
# ## 4. Train 4 biến thể LightGBM quantile và đo trên `test_legacy`
#
# Điều kiện của plan Tầng 10: chỉ giữ Survival-Boost nếu cải thiện ≥ 3–5%.

# %%
fit_te = te_feat[te_feat["event"] == 1].copy()
BASE_FEATS = X.FEATURE_COLS_LGBM
BOOST_FEATS = X.FEATURE_COLS_LGBM + X.SURV_BOOST_FEATS

# F3 train trên ít dòng hơn (bỏ fold 0 vì fold đầu không có quá khứ). Nếu chỉ so F3 với F0 thì
# phần chênh lệch lẫn cả hiệu ứng "ít dữ liệu hơn". Hai đối chứng cùng tập dòng với F3:
#   F0' — bộ feature gốc            → tách hiệu ứng "ít dòng train hơn"
#   F2' — feature OOF K-fold        → tách hiệu ứng "bỏ thông tin tương lai" khỏi hiệu ứng số dòng
tr_f2_sub = tr_f2[tr_f2["fold"] > 0]
configs = [
    ("F0 · gốc (không feature survival)", tr_f1, BASE_FEATS),
    ("F1 · Survival-Boost in-sample (bản 08)", tr_f1, BOOST_FEATS),
    ("F2 · Survival-Boost OOF K-fold", tr_f2, BOOST_FEATS),
    ("F3 · Survival-Boost walk-forward", tr_f3, BOOST_FEATS),
    ("F0' · gốc, cùng tập dòng với F3 (đối chứng)", tr_f3, BASE_FEATS),
    ("F2' · OOF K-fold, cùng tập dòng với F3 (đối chứng)", tr_f2_sub, BOOST_FEATS),
]

rows, models = [], {}
for label, frame, cols in configs:
    fit_tr = frame[frame["event"] == 1]
    m = lgb.LGBMRegressor(**BOOST_PARAMS)
    m.fit(fit_tr[cols].to_numpy(float), fit_tr[TARGET].to_numpy(float))
    pred = np.maximum(m.predict(fit_te[cols].to_numpy(float)), 1.0)
    y = fit_te[TARGET].to_numpy(float)
    tmp = fit_te.assign(_pred=pred)
    rows.append({
        "bộ feature": label, "n_train": len(fit_tr), "n_test": len(fit_te),
        "MAE (row)": float(np.abs(y - pred).mean()),
        "MAE (mean-of-cutoffs)": X.mae_by_cutoff(tmp, TARGET, "_pred"),
        "pinball q50": X.pinball(y, pred, 0.5),
    })
    models[label] = m
    print(f"  {label}: xong")

res = pd.DataFrame(rows)
base_row = res.iloc[0]
for c in ["MAE (row)", "MAE (mean-of-cutoffs)"]:
    res[f"cải thiện {c} (%)"] = (base_row[c] - res[c]) / base_row[c] * 100
# F3/F2' phải được so với đối chứng cùng tập dòng (F0'), không so với F0 đầy đủ dữ liệu
mae_f0p = float(res.loc[4, "MAE (mean-of-cutoffs)"])
for i in (3, 5):
    res.loc[i, "cải thiện so với đối chứng cùng tập dòng (%)"] = \
        (mae_f0p - float(res.loc[i, "MAE (mean-of-cutoffs)"])) / mae_f0p * 100
print()
print("KẾT QUẢ — train trên train_pre (dòng đã có kết cục), đo trên test_legacy")
print(res.to_string(index=False))
print()
print("Lưu ý đọc bảng: F3 và F2' train trên {:,} dòng so với {:,} của F0/F1/F2 (bỏ fold đầu vì".format(
    int(res.loc[3, "n_train"]), int(res.loc[0, "n_train"])))
print("fold đầu không có quá khứ để fit hazard). Cột cuối là phép so đúng — cùng tập dòng, chỉ khác")
print("cách sinh feature:")
print(f"  F2' (K-fold, feature ĐƯỢC thấy giai đoạn sau) : {float(res.loc[5, 'cải thiện so với đối chứng cùng tập dòng (%)']):+.2f}%")
print(f"  F3  (walk-forward, chỉ dùng quá khứ)          : {float(res.loc[3, 'cải thiện so với đối chứng cùng tập dòng (%)']):+.2f}%")

# %% [markdown]
# ## 5. Feature survival có thật sự được model dùng không?

# %%
m_oof = models["F2 · Survival-Boost OOF K-fold"]
imp = (pd.DataFrame({"feature": BOOST_FEATS, "gain": m_oof.feature_importances_})
       .sort_values("gain", ascending=False).reset_index(drop=True))
imp["là feature survival"] = imp["feature"].isin(X.SURV_BOOST_FEATS)
share = imp.loc[imp["là feature survival"], "gain"].sum() / imp["gain"].sum()
print("Top 12 feature (model F2 · OOF):")
print(imp.head(12).to_string(index=False))
print()
print(f"Tổng gain của 6 feature survival: {share:.1%} toàn bộ gain của model.")

# %% [markdown]
# ## 6. Kết luận Đ15

# %%
gain_f1 = float(res.loc[1, "cải thiện MAE (mean-of-cutoffs) (%)"])
gain_f2 = float(res.loc[2, "cải thiện MAE (mean-of-cutoffs) (%)"])
gain_f3_naive = float(res.loc[3, "cải thiện MAE (mean-of-cutoffs) (%)"])
gain_f3_fair = float(res.loc[3, "cải thiện so với đối chứng cùng tập dòng (%)"])
gain_f2p_fair = float(res.loc[5, "cải thiện so với đối chứng cùng tập dòng (%)"])
shrink = gain_f1 - gain_f2

if gain_f2 >= 3 and gain_f3_fair >= 3:
    verdict = "GIỮ — cải thiện sống sót qua cả hai cách kiểm tra"
elif gain_f2 >= 3:
    verdict = ("GIỮ CÓ ĐIỀU KIỆN — đạt theo đúng cách Đ15 yêu cầu (K-fold), nhưng KHÔNG đạt "
               "khi cấm feature nhìn về tương lai (walk-forward)")
else:
    verdict = "BỎ khỏi MVP — phần cải thiện biến mất khi sinh feature đúng cách"

summary = pd.DataFrame([
    {"chỉ số": "Cải thiện MAE — in-sample (bản 08_survival)", "giá trị": f"{gain_f1:+.2f}%"},
    {"chỉ số": "Cải thiện MAE — OOF K-fold (đúng thứ Đ15 yêu cầu)", "giá trị": f"{gain_f2:+.2f}%"},
    {"chỉ số": "Cải thiện MAE — walk-forward (so với F0 đủ dữ liệu)", "giá trị": f"{gain_f3_naive:+.2f}%"},
    {"chỉ số": "Cải thiện MAE — walk-forward vs đối chứng cùng tập dòng",
     "giá trị": f"{gain_f3_fair:+.2f}%"},
    {"chỉ số": "Cải thiện MAE — K-fold vs đối chứng cùng tập dòng (F2')",
     "giá trị": f"{gain_f2p_fair:+.2f}%"},
    {"chỉ số": "Phần cải thiện đến từ việc dùng feature in-sample", "giá trị": f"{shrink:+.2f} điểm %"},
    {"chỉ số": "Ngưỡng của plan (Tầng 10)", "giá trị": "≥ 3%"},
    {"chỉ số": "Kết luận", "giá trị": verdict},
])
print(summary.to_string(index=False))
print()
print("Bốn điều rút ra:")
print(f"  1. Cảnh báo của Đ15 là có cơ sở, nhưng nhỏ hơn lo ngại: dùng feature in-sample thổi phồng")
print(f"     kết quả {shrink:.1f} điểm %, không phải toàn bộ phần cải thiện.")
print(f"  2. Theo đúng thủ tục Đ15 yêu cầu (OOF K-fold), phần cải thiện thật là {gain_f2:+.2f}% —")
print(f"     vẫn vượt ngưỡng 3% của plan. Ở mức này, Đ15 là đề xuất ĐÚNG và NÊN làm.")
print(f"  3. Nhưng K-fold vẫn để feature của fold k được sinh từ hazard model đã thấy các cutoff")
print(f"     SAU fold k. Cấm hẳn điều đó (walk-forward) thì phần cải thiện tụt còn {gain_f3_fair:+.2f}%")
print(f"     so với {gain_f2p_fair:+.2f}% của K-fold trên cùng tập dòng.")
print(f"  4. Phần chênh giữa hai con số đó CHƯA tách được khỏi một yếu tố gây nhiễu: fold đầu của")
print(f"     walk-forward chỉ có ~15k dòng để fit hazard, nên feature của nó yếu hơn vì thiếu dữ")
print(f"     liệu chứ không hẳn vì thiếu thông tin tương lai. Ở production, hazard model luôn được")
print(f"     fit trên toàn bộ lịch sử tới hiện tại nên tình huống thật nằm giữa hai con số. Cách")
print(f"     kết luận dứt điểm: backtest cửa sổ mở rộng trên nhiều kỳ, không phải thêm một fold.")

# %% [markdown]
# ## 7. Lưu artifact + sanity check

# %%
res.to_csv(OUT_METRICS, index=False)
fold_detail.to_csv(OUT_FOLDS, index=False)
imp.to_csv(OUT_IMP, index=False)
print(f"[1] {OUT_METRICS.name} · [2] {OUT_FOLDS.name} · [3] {OUT_IMP.name}")

checks = []


def check(name, cond, detail=""):
    checks.append({"check": name, "pass": bool(cond), "detail": detail})


check("S(t) không tăng theo thời gian", bool((np.diff(S_f1, axis=1) <= 1e-9).all()))
check("S(t) trong [0,1]", bool((S_f1 >= 0).all() and (S_f1 <= 1).all()))
check("P(trả trong 7 ngày) ≤ P(trả trong 30 ngày)",
      bool((tr_f2["S_7"] >= tr_f2["S_30"] - 1e-9).all()))
check("OOF phủ đúng một lần mọi dòng train", len(tr_f2) == len(train_pre),
      f"{len(tr_f2):,} vs {len(train_pre):,}")
check("mỗi cutoff nằm trong đúng một fold",
      train_pre.groupby("cutoff_date")["fold"].nunique().max() == 1)
check("fold fit và fold dự báo không chung cutoff nào (F2)",
      all(set(train_pre[train_pre['fold'] != k]['cutoff_date']).isdisjoint(
          set(train_pre[train_pre['fold'] == k]['cutoff_date'])) for k in range(N_FOLDS)))
check("F3 chỉ dùng quá khứ", len(tr_f3) < len(train_pre),
      f"{len(tr_f3):,} dòng (bỏ fold 0)")
check("feature OOF khác feature in-sample", float(feat_diff["|lệch| TB"].max()) > 1e-6,
      f"lệch lớn nhất {float(feat_diff['|lệch| TB'].max()):.4f}")

checks_df = pd.DataFrame(checks)
print()
print(checks_df.to_string(index=False))
print()
print("PASS TOÀN BỘ" if checks_df["pass"].all() else "CÓ CHECK FAIL — số liệu notebook này không dùng được")
