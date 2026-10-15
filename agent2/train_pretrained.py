"""Train the pretrained voices (CES stack + L3 ranker) on labelled synthetic worlds and save one joblib.

    python -m agent2.train_pretrained --worlds work/data/w3_s201 ... --out models/pretrained_v1.joblib

The saved object contains NO company data, only 14 stack weights, a rule-weight vector and a LightGBM model.
Retrain it whenever real, reviewed cases become available (the same call accepts real labelled worlds).
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import joblib

from .data import load
from .final_eval import pretrain


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worlds", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    worlds = [load(w) for w in a.worlds]
    ces, l3 = pretrain(worlds)
    meta = dict(worlds=[w.name for w in a.worlds], trained_at=dt.datetime.now().isoformat(timespec="seconds"),
                labelled_rows=int(sum(len(w[w.split.isin(["train", "validation"])]) for w in worlds)),
                positives=int(sum(w[w.split.isin(["train", "validation"])].is_fraud.sum() for w in worlds)),
                note="Synthetic worlds only. Do not present as evidence about real SMEs.")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(dict(ces=ces, l3=l3, meta=meta), a.out)
    print(meta)
    print(ces.weights())


if __name__ == "__main__":
    main()
