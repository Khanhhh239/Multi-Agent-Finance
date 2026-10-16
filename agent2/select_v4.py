"""Apply the pre-registered selection rule (AGENT2_WORKLOG.md section 14) to the dev results and write the freeze file.

score(c) = mean over dev worlds of (P1 Recall@B3 + macro-mean over ACFE branches of P2 Recall@B3 + P3 Recall@B3) / 3,
subject to P1 false-alert rate on legitimate look-alikes <= 20 percent; ties within .01 -> earlier in the listed order.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .eval_v4 import CANDIDATES, POLICIES
from .sealed_v4 import file_hashes

LABEL_FREE = ["Rules+Graph (friend)", "Novelty max(R,E)", "Novelty max(R,E,AE)"]


def table(results: list[dict]) -> pd.DataFrame:
    order = list(CANDIDATES) + [p[0] for p in POLICIES]
    rows = []
    for name in order:
        p1 = [r["P1"][name]["recall"] for r in results]
        p2 = [np.mean([b[name]["recall"] for b in r["P2"].values()]) for r in results]
        p3 = [r["P3"][name]["recall"] for r in results]
        rows.append(dict(config=name, P1=np.mean(p1), P2=np.mean(p2), P3=np.mean(p3),
                         P1_case=np.mean([r["P1"][name]["case_recall"] for r in results]),
                         P1_decoy=np.mean([r["P1"][name]["hard_neg_alert_rate"] for r in results]),
                         P1_ap=np.mean([r["P1"][name].get("ap", np.nan) for r in results]),
                         P1_B1_precision=np.mean([r["P1"][name].get("B1_precision", np.nan) for r in results])))
    t = pd.DataFrame(rows)
    t["score"] = (t.P1 + t.P2 + t.P3) / 3
    t["eligible"] = t.P1_decoy <= .20
    return t


def pick(t: pd.DataFrame, among=None) -> str:
    c = t[t.eligible] if among is None else t[t.eligible & t.config.isin(among)]
    if c.empty or not np.isfinite(c.score).all():
        raise ValueError("no eligible configuration with finite development scores")
    best = c.score.max()
    # The registered rule says strictly less than .01, not less than or equal.
    return c[((best - c.score) < .01) & ~np.isclose(best - c.score, .01, rtol=0, atol=1e-12)].iloc[0]["config"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, default=Path("work/results/v4_methods"))
    p.add_argument("--freeze", type=Path, default=Path("work/results/v4_frozen.json"))
    a = p.parse_args()
    if a.freeze.exists():
        raise SystemExit(f"{a.freeze} exists; not overwriting the freeze")
    results = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(a.results.glob("w4_s*.json"))]
    assert all(k in r for r in results for k in ("P1", "P2", "P3")) and len(results) == 3, "dev study incomplete"
    t = table(results)
    chosen, cold = pick(t), pick(t, LABEL_FREE)
    workers = {r.get("candidate_workers", 1) for r in results}
    assert len(workers) == 1, "dev study execution settings differ between worlds"
    pd.set_option("display.width", 220)
    print(t.round(3).to_string(index=False))
    print("chosen:", chosen, "| cold start:", cold)
    t.to_csv(a.results / "selection_table.csv", index=False)
    a.freeze.parent.mkdir(parents=True, exist_ok=True)
    a.freeze.write_text(json.dumps(dict(chosen=chosen, cold_start=cold, rule="worklog section 14", candidate_workers=workers.pop(),
                                        hashes=file_hashes(Path(".")), dev_scores=t.set_index("config")[["P1", "P2", "P3", "score", "P1_decoy"]]
                                        .round(4).to_dict(orient="index")), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
