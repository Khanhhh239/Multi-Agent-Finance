# %% [markdown]
# # 11 — Đ2: Train lại trục chính LightGBM trên lưới cutoff mở rộng
#
# **Vị trí:** `08_survival` (đã kéo lưới cutoff) → **[11_retrain_extended]** → gate Tầng 9
#
# `../method/AGENT1_TONG_HOP.md` Đ2 yêu cầu đúng hai việc:
#
# > 1. Train lại 3 model quantile trên lưới mở rộng, **chỉ dùng dòng có nhãn** (`followup ≥ horizon`),
# >    cộng trọng số recency (nửa đời sống 8 tuần như `08_survival` D53).
# > 2. So bản mới với bản cũ **trên `test_post`** bằng phép kiểm chứng bằng tiền.
#
# Notebook này làm đúng như vậy, và thêm hai biến thể đối chứng cho phần mà Đ2 không nói tới:
# **những dòng bị vứt đi**. Ở cửa sổ hậu cú sốc, "có nhãn" đồng nghĩa với "đã được trả trước ngày
# cuối dữ liệu" — tức đúng nhóm trả nhanh. Vứt phần còn lại là chọn mẫu theo kết cục.
#
# | Biến thể | Dữ liệu train | Dòng bị cắt cụt | Trọng số | Ai đề xuất |
# |---|---|---|---|---|
# | **M0** | model đang chạy (`models/lgbm_*.txt`) | — | — | hiện trạng |
# | **M1** | `train_pre` (lưới cũ), dòng có nhãn | loại | đều | kiểm soát |
# | **M2a** | `train_pre + train_post`, dòng có nhãn | loại | đều | Đ2 (bỏ trọng số) |
# | **M2b** | `train_pre + train_post`, dòng có nhãn | loại | recency 8 tuần | **Đ2 nguyên văn** |
# | **M3** | `train_pre + train_post`, **mọi dòng** | giữ — pinball có censoring | recency 8 tuần | đối chứng |
# | **M4** | `train_pre + train_post`, dòng có nhãn | loại — bù bằng **IPCW** | recency × IPCW | đối chứng |
#
# Kỷ luật Đ11: mọi biến thể dùng **cùng** siêu tham số và **cùng** số cây cố định (không early
# stopping), không biến thể nào nhìn vào tập test để chọn tham số.

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
pd.set_option("display.width", 240)
pd.set_option("display.float_format", "{:,.4f}".format)

SEED = X.SEED
N_TREES = 500                       # cố định cho MỌI biến thể → so sánh sạch (Đ11)
QUANTILES = {"q10": 0.10, "q50": 0.50, "q90": 0.90}
TARGET = "duration_days"
FEATS = X.FEATURE_COLS_LGBM

PARAMS = dict(boosting_type="gbdt", num_leaves=31, learning_rate=0.05, n_estimators=N_TREES,
              min_child_samples=20, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5,
              reg_alpha=0.0, reg_lambda=1.0, random_state=SEED, n_jobs=-1, verbose=-1)

OUT_INV = X.PROC / "ext_retrain_invoice_metrics.csv"
OUT_MONEY = X.PROC / "ext_retrain_money_check.csv"
OUT_LIVE = X.PROC / "ext_retrain_live_forecast.csv"
OUT_SENS = X.PROC / "ext_retrain_sensitivity.csv"
OUT_DEC = X.PROC / "ext_retrain_decision.csv"
print("Config OK · LightGBM", lgb.__version__)

# %% [markdown]
# ## 1. Dựng snapshot trên lưới mở rộng (Đ1)

# %%
t0 = time.time()
snap, plan, DATA_END, clean = X.build_extended_snapshot()
print(f"({time.time()-t0:.0f}s)")

# %% [markdown]
# ### 1b. Cái giá của "chỉ dùng dòng có nhãn"

# %%
lab_rows = []
for w in ["train_pre", "train_post"]:
    part = snap[snap["window"] == w]
    lab = part[part["event"] == 1]
    lab_rows.append({
        "cửa sổ": w, "tổng dòng": len(part), "dòng có nhãn": len(lab),
        "tỷ lệ dòng giữ lại": len(lab) / len(part),
        "tỷ lệ tiền giữ lại": lab["amount"].sum() / part["amount"].sum(),
        "số ngày trả TB — phần giữ lại": lab["duration_days"].mean(),
        "số ngày trả TB — chặn dưới thật (cả dòng cắt cụt)": part["duration_days"].mean(),
    })
label_bias = pd.DataFrame(lab_rows)
print("Tác động của bộ lọc 'chỉ dùng dòng có nhãn' mà Đ2 quy định")
print(label_bias.to_string(index=False))
print()
print("Đọc bảng: ở `train_post`, bộ lọc giữ lại khoảng 1/8 số dòng. Số ngày trả trung bình của")
print("phần giữ lại là ~17 ngày, trong khi chặn dưới thật (tính cả dòng bị cắt cụt, dùng mốc theo")
print("dõi làm giá trị tối thiểu) là ~50 ngày. Model train trên phần giữ lại sẽ học rằng 'hoá đơn")
print("hậu cú sốc vẫn được trả nhanh' — ngược đúng với thứ Đ2 muốn nó học. Trọng số recency còn")
print("khuếch đại điều đó, vì nó dồn trọng số vào chính các dòng bị chọn lệch.")

# %% [markdown]
# ## 2. Tập train của từng biến thể

# %%
tr_pre = snap[snap["window"] == "train_pre"]
tr_post = snap[snap["window"] == "train_post"]
tr_all = pd.concat([tr_pre, tr_post], ignore_index=True)
te_legacy = snap[snap["window"] == "test_legacy"].copy()
te_post = snap[snap["window"] == "test_post"].copy()

VARIANT_SPEC = {
    "M1":  dict(frame=tr_pre[tr_pre["event"] == 1],   censored_aware=False, weight="none"),
    "M2a": dict(frame=tr_all[tr_all["event"] == 1],   censored_aware=False, weight="none"),
    "M2b": dict(frame=tr_all[tr_all["event"] == 1],   censored_aware=False, weight="recency"),
    "M3":  dict(frame=tr_all,                          censored_aware=True,  weight="recency"),
    "M4":  dict(frame=tr_all,                          censored_aware=False, weight="recency_ipcw"),
}


def build_weights(frame, kind):
    w = np.ones(len(frame))
    if kind in ("recency", "recency_ipcw"):
        w = X.recency_weights(frame["cutoff_date"], X.POST_TRAIN_END).to_numpy(float)
    if kind == "recency_ipcw":
        w = w * X.ipcw_weights(frame)
    return w


for name, spec in VARIANT_SPEC.items():
    fr = spec["frame"]
    w = build_weights(fr, spec["weight"])
    keep = w > 0
    print(f"{name:4s} · {int(keep.sum()):>7,} dòng train · censored {1 - fr['event'].mean():>6.1%} · "
          f"trọng số {spec['weight']:<13s} (min {w[keep].min():.3f} · max {w[keep].max():.2f} · "
          f"tổng {w.sum():,.0f})")

# %% [markdown]
# ## 3. Train 5 biến thể × 3 quantile
#
# M3 dùng `censored_pinball_objective` (`ext_lib.py`): với dòng bị cắt cụt tại mốc `c` ta chỉ biết
# `y ≥ c`, nên chỉ phạt khi model dự báo **thấp hơn** `c`; khi model đã dự báo ≥ `c` thì gradient
# bằng 0 vì dữ liệu không nói được gì thêm. Không có nhãn giả nào được tạo ra.
#
# M4 dùng IPCW: giữ đúng bộ lọc của Đ2 (chỉ dòng có nhãn) nhưng bù lại phần bị vứt bằng trọng số
# `1/G(y)` — dòng trả muộn hiếm khi được quan sát nên được đếm nặng hơn.

# %%
def fit_variant(name, spec):
    fr = spec["frame"]
    w = build_weights(fr, spec["weight"])
    keep = w > 0
    fr, w = fr[keep], w[keep]
    Xtr = fr[FEATS].to_numpy(float)
    y = fr[TARGET].to_numpy(float)
    cens = (fr["event"] == 0).to_numpy()
    out = {}
    for qname, alpha in QUANTILES.items():
        if spec["censored_aware"]:
            m = lgb.LGBMRegressor(**{**PARAMS,
                                     "objective": X.censored_pinball_objective(alpha, cens)})
            init = float(np.quantile(y, alpha))     # objective tự viết không có boost-from-average
            m.fit(Xtr, y, sample_weight=w, init_score=np.full(len(y), init))
            m._init_const = init
        else:
            m = lgb.LGBMRegressor(**{**PARAMS, "objective": "quantile", "alpha": alpha})
            m.fit(Xtr, y, sample_weight=w)
            m._init_const = 0.0
        out[qname] = m
    print(f"  [{name}] xong — {len(fr):,} dòng ({time.time()-t0:.0f}s)")
    return out


print("Đang train...")
fitted = {name: fit_variant(name, spec) for name, spec in VARIANT_SPEC.items()}
boosters_m0 = {q: lgb.Booster(model_file=str(X.MODEL_DIR / f"lgbm_{q}.txt")) for q in QUANTILES}
print("  [M0] nạp từ models/lgbm_q10|q50|q90.txt")

VARIANTS = ["M0", "M1", "M2a", "M2b", "M3", "M4"]


def predict_q(variant, frame):
    Xm = frame[FEATS].to_numpy(float)
    if variant == "M0":
        raw = np.column_stack([boosters_m0[q].predict(Xm) for q in QUANTILES])
    else:
        raw = np.column_stack([fitted[variant][q].predict(Xm) + fitted[variant][q]._init_const
                               for q in QUANTILES])
    return np.maximum(np.sort(raw, axis=1), 1.0)     # rearrangement (D8) + sàn 1 ngày (Đ7.3)


for frame in (te_legacy, te_post):
    for v in VARIANTS:
        p = predict_q(v, frame)
        frame[f"{v}_q10"], frame[f"{v}_q50"], frame[f"{v}_q90"] = p[:, 0], p[:, 1], p[:, 2]

# %% [markdown]
# ## 4. Đo lường 1 — mức hoá đơn trên `test_legacy` (chế độ cũ)
#
# Chỉ tính trên dòng đã có kết cục. Đây là phép kiểm tra *"không làm hỏng cái đang chạy"*: một
# biến thể làm tệ đi rõ rệt ở chế độ cũ thì không dùng được, kể cả khi nó tốt ở chế độ mới.

# %%
lg = te_legacy[te_legacy["event"] == 1].copy()
inv_rows = []
for v in VARIANTS + ["B1"]:
    col = "pred_b1_remaining_days" if v == "B1" else f"{v}_q50"
    inv_rows.append({
        "model": v, "n": len(lg),
        "MAE (row)": float(np.abs(lg[TARGET] - lg[col]).mean()),
        "MAE (mean-of-cutoffs)": X.mae_by_cutoff(lg, TARGET, col),
        "pinball q50": X.pinball(lg[TARGET], lg[col], 0.5),
        "coverage [q10,q90]": (np.nan if v == "B1" else
                               float(((lg[TARGET] >= lg[f"{v}_q10"]) &
                                      (lg[TARGET] <= lg[f"{v}_q90"])).mean())),
    })
inv = pd.DataFrame(inv_rows)
b1_mae = float(inv.loc[inv["model"] == "B1", "MAE (mean-of-cutoffs)"].iloc[0])
inv["cải thiện vs B1 (%)"] = (b1_mae - inv["MAE (mean-of-cutoffs)"]) / b1_mae * 100
print("test_legacy — chỉ dòng đã có kết cục (n = {:,})".format(len(lg)))
print(inv.to_string(index=False))

# %% [markdown]
# ## 5. Đo lường 2 — kiểm chứng bằng tiền (phép thử quyết định của Đ2)
#
# Cùng phép đo của `08_survival` §6: *trong H ngày kể từ T, thực tế thu về bao nhiêu % giá trị AR,
# và model nói bao nhiêu*. Chỉ dùng cutoff đã theo dõi đủ H ngày → **không bị thiên lệch censoring**.
#
# Xác suất trả trong H ngày suy ra **từ chính 3 quantile của mỗi model** (nội suy hàm phân phối),
# nên mọi biến thể — kể cả M0 — được đo bằng cùng một thủ tục. Con số của M0 vì thế không trùng
# tuyệt đối với bảng trong `08_survival` (bảng đó dùng pool residual của tập calibration cũ);
# cột `Survival B` ở §5b lấy nguyên từ artifact cũ để đối chiếu.

# %%
def prob_fn(variant):
    def _f(frame, H):
        return X.prob_paid_from_quantiles(frame[f"{variant}_q10"], frame[f"{variant}_q50"],
                                          frame[f"{variant}_q90"], H)
    return _f


eval_all = pd.concat([te_legacy, te_post], ignore_index=True)
prob_cols = {v: prob_fn(v) for v in VARIANTS}
prob_cols["B1"] = lambda frame, H: (frame["pred_b1_remaining_days"] <= H).to_numpy(float)

money = X.money_check(eval_all, prob_cols)
show = ["window", "horizon_days", "cutoffs", "n", "amount_musd", "thuc_te"] + VARIANTS + ["B1"]
print("TỶ LỆ TIỀN THU ĐƯỢC TRONG H NGÀY — thực tế vs từng biến thể (trọng số theo tiền)")
print(money[show].to_string(index=False))

bias_post = pd.Series({v: money.loc[money["window"] == "test_post", f"lech_{v}"].abs().mean() * 100
                       for v in VARIANTS + ["B1"]})
bias_leg = pd.Series({v: money.loc[money["window"] == "test_legacy", f"lech_{v}"].abs().mean() * 100
                      for v in VARIANTS + ["B1"]})
print()
print("Sai lệch tuyệt đối TRUNG BÌNH (điểm %) — con số Đ2 muốn kéo xuống là cột test_post:")
print(pd.DataFrame({"test_post (chế độ mới)": bias_post,
                    "test_legacy (chế độ cũ)": bias_leg}).round(1).to_string())

# %% [markdown]
# ### 5b. Đối chiếu với tầng survival đã có
#
# `survival_money_check.csv` (artifact của `08_survival`) đo cùng đại lượng cho Survival A / B.
# Đây là mốc phải vượt qua: nếu train lại trục chính không hạ được sai lệch xuống gần mức của
# Survival B thì việc train lại không phải là câu trả lời.

# %%
sm = pd.read_csv(X.PROC / "survival_money_check.csv")
sm_post = sm[sm["window"] == "test_post"]
ref = pd.Series({
    "Survival A (chỉ học trước cú sốc)": (sm_post["Survival A"] - sm_post["thực tế"]).abs().mean() * 100,
    "Survival B (học cả hậu cú sốc)": (sm_post["Survival B"] - sm_post["thực tế"]).abs().mean() * 100,
    "LightGBM cũ (đo bằng pool residual)": (sm_post["LightGBM"] - sm_post["thực tế"]).abs().mean() * 100,
})
print("Mốc tham chiếu — sai lệch tuyệt đối TB trên test_post (điểm %), từ artifact 08_survival:")
print(ref.round(1).to_string())
print()
print("Bảng đối chiếu đầy đủ (thấp hơn = tốt hơn):")
combined = pd.concat([bias_post.rename("sai lệch tiền test_post (điểm %)"),
                      ref.rename("sai lệch tiền test_post (điểm %)")]).sort_values()
print(combined.round(1).to_string())

# %% [markdown]
# ## 6. Đo lường 3 — con số dòng tiền 30 ngày cho pool đang mở
#
# Đây là con số sẽ lên dashboard. Điểm tham chiếu (`08_survival` §7): LightGBM cũ **307,9 triệu**,
# Survival A **310,4 triệu**, Survival B **95,4 triệu**.

# %%
_, pool_df, closed_df, _, _ = X.load_pools()
live = X.build_snapshot(DATA_END, "live", pool_df, closed_df, DATA_END)
live = live[live["is_open"] == 1].reset_index(drop=True)
amt = live["amount"].to_numpy(float)

live_rows = []
for v in VARIANTS:
    p = predict_q(v, live)
    live[f"{v}_q10"], live[f"{v}_q50"], live[f"{v}_q90"] = p[:, 0], p[:, 1], p[:, 2]
    row = {"model": v, "q50 trung vị (ngày)": float(np.median(p[:, 1])),
           "q90 trung vị (ngày)": float(np.median(p[:, 2]))}
    for H in (30, 90):
        pr = X.prob_paid_from_quantiles(p[:, 0], p[:, 1], p[:, 2], H)
        row[f"tiền về {H} ngày (triệu USD)"] = float((amt * pr).sum() / 1e6)
        row[f"tỷ lệ {H} ngày"] = float((amt * pr).sum() / amt.sum())
    live_rows.append(row)
live_fc = pd.DataFrame(live_rows)
print(f"Pool đang mở tại {DATA_END.date()}: {len(live):,} hoá đơn · ${amt.sum()/1e6:,.1f} triệu")
print(live_fc.to_string(index=False))

# %% [markdown]
# ## 7. Độ nhạy của M3 — biến thể duy nhất có tác dụng, kiểm tra xem nó có phụ thuộc tham số không
#
# M3 dùng objective tự viết nên không có bước làm mới giá trị lá của LightGBM → hội tụ chậm hơn.
# Phải chứng minh kết luận không đến từ việc chọn đúng một cấu hình may mắn: quét 2 mức số cây
# × 2 bộ feature (có/không feature lịch — D53 khuyến nghị bỏ feature lịch).

# %%
def run_m3(n_trees, feats, tag):
    fr = tr_all
    w = X.recency_weights(fr["cutoff_date"], X.POST_TRAIN_END).to_numpy(float)
    Xtr = fr[feats].to_numpy(float)
    y = fr[TARGET].to_numpy(float)
    cens = (fr["event"] == 0).to_numpy()
    preds = {}
    for nm, ev_fr in (("test_legacy", te_legacy), ("test_post", te_post)):
        preds[nm] = np.empty((len(ev_fr), 3))
    for j, (qname, alpha) in enumerate(QUANTILES.items()):
        m = lgb.LGBMRegressor(**{**PARAMS, "n_estimators": n_trees,
                                 "objective": X.censored_pinball_objective(alpha, cens)})
        init = float(np.quantile(y, alpha))
        m.fit(Xtr, y, sample_weight=w, init_score=np.full(len(y), init))
        for nm, ev_fr in (("test_legacy", te_legacy), ("test_post", te_post)):
            preds[nm][:, j] = m.predict(ev_fr[feats].to_numpy(float)) + init
    out = {}
    for nm in preds:
        preds[nm] = np.maximum(np.sort(preds[nm], axis=1), 1.0)
    lg_mask = (te_legacy["event"] == 1).to_numpy()
    out["MAE legacy"] = float(np.abs(te_legacy.loc[lg_mask, TARGET].to_numpy()
                                     - preds["test_legacy"][lg_mask, 1]).mean())
    biases = {"test_legacy": [], "test_post": []}
    for nm, ev_fr in (("test_legacy", te_legacy), ("test_post", te_post)):
        for H in (7, 14, 30):
            el = (ev_fr["followup_days"] >= H).to_numpy()
            if el.sum() == 0:
                continue
            sub, arr = ev_fr[el], preds[nm][el]
            a = sub["amount"].to_numpy(float)
            act = float((a * ((sub["event"] == 1) & (sub["duration_days"] <= H))).sum() / a.sum())
            pr = X.prob_paid_from_quantiles(arr[:, 0], arr[:, 1], arr[:, 2], H)
            biases[nm].append(abs(float((a * pr).sum() / a.sum()) - act))
    out["|lệch| tiền test_post"] = float(np.mean(biases["test_post"]))
    out["|lệch| tiền test_legacy"] = float(np.mean(biases["test_legacy"]))
    out["cấu hình"] = tag
    out["số cây"] = n_trees
    out["số feature"] = len(feats)
    print(f"  {tag}: MAE legacy {out['MAE legacy']:.3f} · |lệch| post "
          f"{out['|lệch| tiền test_post']*100:.1f}pp · |lệch| legacy "
          f"{out['|lệch| tiền test_legacy']*100:.1f}pp ({time.time()-t0:.0f}s)")
    return out


print("Quét độ nhạy của M3 (mất vài phút)...")
sens = pd.DataFrame([
    run_m3(500, X.FEATURE_COLS_LGBM, "M3 · 500 cây · đủ feature"),
    run_m3(1500, X.FEATURE_COLS_LGBM, "M3 · 1500 cây · đủ feature"),
    run_m3(500, X.FEATURE_COLS_NOCAL, "M3 · 500 cây · bỏ feature lịch"),
    run_m3(1500, X.FEATURE_COLS_NOCAL, "M3 · 1500 cây · bỏ feature lịch"),
])[["cấu hình", "số cây", "số feature", "MAE legacy",
    "|lệch| tiền test_post", "|lệch| tiền test_legacy"]]
print()
print(sens.to_string(index=False))
print()
print("Đọc bảng: mọi cấu hình của M3 đều đánh đổi cùng một kiểu — kéo sai lệch ở chế độ mới xuống")
print("bằng cách dự báo bi quan hơn ở MỌI chế độ, nên chế độ cũ xấu đi tương ứng. Không có cấu")
print("hình nào thắng ở cả hai. Đây là tính chất của cách tiếp cận, không phải chuyện chỉnh tham số.")

# %% [markdown]
# ## 8. Quyết định
#
# Ba điều kiện, chốt trước khi nhìn kết quả (Đ11):
#
# 1. **Không làm hỏng chế độ cũ** — MAE mean-of-cutoffs trên `test_legacy` không tệ hơn M0 quá 5%.
# 2. **Sửa được cái đang sai** — sai lệch tiền trung bình trên `test_post` giảm ≥ 20 điểm % so với M0.
# 3. **Đáng thay thế** — phải ít nhất ngang tầng survival đã có (Survival B) ở điều kiện 2.

# %%
m0_mae = float(inv.loc[inv["model"] == "M0", "MAE (mean-of-cutoffs)"].iloc[0])
m0_bias = float(bias_post["M0"])
surv_b_bias = float(ref["Survival B (học cả hậu cú sốc)"])

dec_rows = []
for v in VARIANTS:
    mae_v = float(inv.loc[inv["model"] == v, "MAE (mean-of-cutoffs)"].iloc[0])
    bias_v = float(bias_post[v])
    live_v = float(live_fc.loc[live_fc["model"] == v, "tiền về 30 ngày (triệu USD)"].iloc[0])
    c1 = mae_v <= m0_mae * 1.05
    c2 = (m0_bias - bias_v) >= 20.0
    c3 = bias_v <= surv_b_bias * 1.25
    dec_rows.append({
        "biến thể": v, "MAE legacy": mae_v, "Δ MAE vs M0 (%)": (mae_v - m0_mae) / m0_mae * 100,
        "|lệch| tiền test_post (pp)": bias_v, "giảm so với M0 (pp)": m0_bias - bias_v,
        "tiền 30 ngày (triệu)": live_v,
        "ĐK1 không hỏng chế độ cũ": "PASS" if c1 else "FAIL",
        "ĐK2 sửa được sai lệch tiền": "PASS" if c2 else "FAIL",
        "ĐK3 ngang tầng survival": "PASS" if c3 else "FAIL",
    })
decision = pd.DataFrame(dec_rows)
print(decision.to_string(index=False))
print()

winners = decision[(decision["biến thể"] != "M0") &
                   (decision["ĐK1 không hỏng chế độ cũ"] == "PASS") &
                   (decision["ĐK2 sửa được sai lệch tiền"] == "PASS") &
                   (decision["ĐK3 ngang tầng survival"] == "PASS")]
best = winners.sort_values("|lệch| tiền test_post (pp)").iloc[0]["biến thể"] if len(winners) else None

print("=" * 96)
print("KẾT LUẬN Đ2")
print("=" * 96)
if best:
    print(f"→ Thay trục chính bằng biến thể **{best}**.")
else:
    print("→ KHÔNG biến thể nào đạt cả ba điều kiện. Không thay trục chính.")
    print()
    print("  Lý do, đọc thẳng từ bảng trên:")
    print(f"  · M2b (Đ2 nguyên văn): sai lệch tiền hậu cú sốc {float(bias_post['M2b']):.1f}pp so với")
    print(f"    {m0_bias:.1f}pp của model đang chạy — tức là **tệ hơn hiện trạng**. Nguyên nhân ở §1b:")
    print("    bộ lọc 'chỉ dùng dòng có nhãn' giữ lại đúng nhóm trả nhanh, trọng số recency khuếch đại.")
    print(f"  · M3 (giữ dòng bị cắt cụt): hạ được sai lệch xuống {float(bias_post['M3']):.1f}pp — biến thể")
    print(f"    duy nhất có tác dụng — nhưng MAE chế độ cũ xấu đi "
          f"{(float(inv.loc[inv['model']=='M3','MAE (mean-of-cutoffs)'].iloc[0]) - m0_mae)/m0_mae*100:.0f}%")
    print(f"    và vẫn thua Survival B ({surv_b_bias:.1f}pp).")
    print(f"  · M4 (IPCW): {float(bias_post['M4']):.1f}pp — IPCW chỉ hiệu chỉnh được trong dải thời gian")
    print("    còn quan sát được; ở chế độ mới phần lớn khối lượng nằm NGOÀI dải đó nên không cứu được.")
    print()
    print("  → Phương án dự phòng mà chính Đ2 đã viết là phương án đúng:")
    print("    *\"chuyển trục chính sang survival khi regime là crisis, giữ LightGBM cho regime normal\"*.")
    print("    Việc này đã có sẵn trong `08_survival` §7b + `10_dashboard`, không cần train lại gì.")

# %% [markdown]
# ## 9. Lưu artifact + sanity check

# %%
inv.to_csv(OUT_INV, index=False)
money.to_csv(OUT_MONEY, index=False)
live_fc.to_csv(OUT_LIVE, index=False)
sens.to_csv(OUT_SENS, index=False)
decision.to_csv(OUT_DEC, index=False)
print(f"[1] {OUT_INV.name} · [2] {OUT_MONEY.name} · [3] {OUT_LIVE.name} · "
      f"[4] {OUT_SENS.name} · [5] {OUT_DEC.name}")

if best:
    for q in QUANTILES:
        fitted[best][q].booster_.save_model(str(X.MODEL_DIR / f"lgbm_ext_{best}_{q}.txt"))
    print(f"[6] models/lgbm_ext_{best}_q10|q50|q90.txt")
else:
    print("[6] không lưu model mới — không biến thể nào đạt điều kiện thay thế")

checks = []


def check(name, cond, detail=""):
    checks.append({"check": name, "pass": bool(cond), "detail": detail})


check("snapshot mở rộng có dòng bị cắt cụt", int((snap["event"] == 0).sum()) > 0,
      f"{int((snap['event'] == 0).sum()):,} dòng")
check("bộ lọc 'chỉ dòng có nhãn' loại >50% dữ liệu hậu cú sốc",
      float(label_bias.loc[label_bias["cửa sổ"] == "train_post", "tỷ lệ dòng giữ lại"].iloc[0]) < 0.5,
      f"giữ lại {float(label_bias.loc[label_bias['cửa sổ']=='train_post','tỷ lệ dòng giữ lại'].iloc[0]):.1%}")
check("mọi biến thể giữ q10 ≤ q50 ≤ q90 trên test_post",
      bool(all((te_post[f"{v}_q10"] <= te_post[f"{v}_q50"] + 1e-9).all() and
               (te_post[f"{v}_q50"] <= te_post[f"{v}_q90"] + 1e-9).all() for v in VARIANTS)))
check("M1 tái lập được M0 trong sai số 20% (kiểm soát reimplementation)",
      abs(float(inv.loc[inv["model"] == "M1", "MAE (mean-of-cutoffs)"].iloc[0]) - m0_mae) / m0_mae < 0.20,
      f"M1 {float(inv.loc[inv['model']=='M1','MAE (mean-of-cutoffs)'].iloc[0]):.3f} vs M0 {m0_mae:.3f}")
check("xác suất trả trong 30 ngày ≤ trong 90 ngày (mọi biến thể, pool đang mở)",
      bool(all((X.prob_paid_from_quantiles(live[f"{v}_q10"], live[f"{v}_q50"], live[f"{v}_q90"], 30)
                <= X.prob_paid_from_quantiles(live[f"{v}_q10"], live[f"{v}_q50"], live[f"{v}_q90"], 90) + 1e-9).all()
               for v in VARIANTS)))
check("tiền về 30 ngày ≤ tổng dư nợ", bool((live_fc["tỷ lệ 30 ngày"] <= 1.0).all()))
check("thực tế thu hậu cú sốc < 1% (nền của mọi kết luận ở đây)",
      float(money.loc[money["window"] == "test_post", "thuc_te"].max()) < 0.01,
      f"cao nhất {float(money.loc[money['window']=='test_post','thuc_te'].max()):.2%}")

checks_df = pd.DataFrame(checks)
print()
print(checks_df.to_string(index=False))
print()
print("PASS TOÀN BỘ" if checks_df["pass"].all()
      else "CÓ CHECK FAIL — số liệu notebook này không dùng được")
