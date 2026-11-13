"""Public CI research only; frozen origins and sample rules, no customer uploads or IDs in reports."""

from pathlib import Path
import hashlib
import sys
import time
import warnings
import numpy as np
import pandas as pd
import psutil
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.t1_compact.historical_workspace import Method


def main():
    path = ROOT / "data/interim/real_customer_invoices.parquet"
    d = pd.read_parquet(path, filters=[("firm_id", "==", "HR-CA02")]).rename(
        columns={"paid_date_true": "settled", "amount_gross": "amount"}
    )
    d = d[
        (d.amount > 0)
        & (d.due_date >= d.issue_date)
        & (d.settled.isna() | (d.settled >= d.issue_date))
    ].sort_values(["issue_date", "invoice_id"])
    d["known_at"] = d.issue_date
    rows = []

    def measure(origin, stage, name, fraction, seed):
        clock = pd.Timestamp(origin)
        past = d[d.issue_date <= clock].copy()
        past.loc[past.settled > clock, "settled"] = pd.NaT
        past["settled_known_at"] = past.settled
        opened = past[past.settled.isna()]
        history = past.tail(max(1, int(len(past) * fraction)))
        t = time.perf_counter()
        model = Method(name, seed).fit(history, clock)
        p = model.distribution(opened, (clock - opened.issue_date).dt.days)
        days = (d.loc[opened.index, "settled"] - clock).dt.days.fillna(10000).to_numpy()
        amount = opened.amount.to_numpy()
        exp = (p[:, :13] * amount[:, None]).sum(0)
        actual = np.array(
            [amount[(days > 7 * i) & (days <= 7 * (i + 1))].sum() for i in range(13)]
        )
        loss = (p[:, :4].sum(1) - (days <= 28)) ** 2
        row = dict(
            stage=stage,
            origin=origin,
            method=name,
            seed=seed,
            fraction=fraction,
            train_n=len(history),
            open_n=len(opened),
            customer_n=opened.customer_id.nunique(),
            brier4=loss.mean(),
            mae_weekly_source_units=np.abs(exp - actual).mean(),
            seconds=time.perf_counter() - t,
            rss_mib=psutil.Process().memory_info().rss / 2**20,
        )
        for label, mask in [
            ("overdue", opened.due_date < clock),
            ("current", opened.due_date >= clock),
        ]:
            row["brier4_" + label] = loss[mask].mean() if mask.any() else None
        rows.append(row)
        return loss, opened.customer_id.to_numpy()

    # Labels for the final validation origin mature before the locked January audit.
    with threadpool_limits(1), warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        for o in ["2019-08-01", "2019-09-01", "2019-10-01"]:
            for name in ["customer", "survival", "spline", "neural"]:
                measure(o, "selection", name, 1.0, 7)
        selected = pd.DataFrame(rows).groupby("method").brier4.mean().idxmin()
        for frac in [0.25, 0.5, 0.75, 1.0]:
            for seed in [7, 17, 27]:
                measure("2019-10-01", "learning_curve", "neural", frac, seed)
        base, g = measure("2020-01-15", "locked_anchor", "customer", 1.0, 7)
        loss, _ = measure("2020-01-15", "locked_selected", selected, 1.0, 7)
        u, idx = np.unique(g, return_inverse=True)
        draws = np.random.default_rng(7).integers(len(u), size=(1000, len(u)))
        delta = np.bincount(idx, weights=base - loss)[draws].sum(1) / np.bincount(idx)[
            draws
        ].sum(1)
        rows[-1].update(
            zip(("delta_ci_low", "delta_ci_high"), np.quantile(delta, [0.025, 0.975]))
        )
    out = ROOT / "outputs/business"
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    with path.open("rb") as source:
        df["input_sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
    df["code_sha256"] = hashlib.sha256(
        Path(__file__).read_bytes() + (ROOT / "agent1/adaptive/methods.py").read_bytes()
    ).hexdigest()
    df.to_csv(out / "invoice_benchmark.csv", index=False)
    print(df.tail(2).iloc[:, :15].to_string(index=False))


if __name__ == "__main__":
    main()
