"""Pilot KPIs (phase E5) straight from the review store. Read-only; never writes to the database.

K1 cases per company-week, K2 share of reviewed cases marked worth review (latest decision per case),
K3 cases concluded suspected or confirmed, K5 review minutes per company-week, plus usefulness by priority and
by signal family (from rule_ids and the first observation feature), so the pilot shows WHICH signals help.
  python scripts/pilot_kpis.py --db work/service/review.sqlite --out results/pilot/kpis.json
Thresholds in docs/03_danh_gia_va_hieu_qua_kinh_te/02_chi_so_kinh_te_va_kpi.md are assumptions until measured.
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def family(payload):
    rules = [r for r in str(payload.get("rule_ids", "")).split("|") if r]
    if rules:
        return "rule:" + rules[0][0]                     # rule group A..F, P, T
    signal = payload.get("top_signal") or ""
    return f"signal:{signal}" if signal else "ranking_only"


def kpis(db_path):
    db = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    cases = {(r["company_id"], r["id"]): json.loads(r["payload"]) for r in db.execute("SELECT company_id,id,payload FROM cases")}
    weeks = {(r["company_id"], r["week"]) for r in db.execute("SELECT company_id,week FROM scores")}
    latest = {}
    minutes = defaultdict(float)
    for r in db.execute("SELECT * FROM decisions ORDER BY id"):
        latest[(r["company_id"], r["case_id"])] = r
        minutes[r["company_id"]] += r["review_minutes"]
    reviewed = [k for k in cases if k in latest]
    marked = [latest[k]["worth_review"] for k in reviewed if latest[k]["worth_review"] is not None]
    by = lambda keyfn: _group(reviewed, cases, latest, keyfn)
    companies = sorted({c for c, _ in cases})
    return {
        "data_kind": "pilot review store (real only if the store holds pilot data)",
        "companies": len(companies), "company_weeks": len(weeks), "cases": len(cases),
        "K1_cases_per_company_week": len(cases) / len(weeks) if weeks else None,
        "reviewed_cases": len(reviewed),
        "K2_worth_review_rate": sum(marked) / len(marked) if marked else None, "K2_measured_cases": len(marked),
        "K3_suspected_or_confirmed": sum(latest[k]["conclusion"] in ("suspected", "confirmed") for k in reviewed),
        "K5_review_minutes_per_company_week": sum(minutes.values()) / len(weeks) if weeks else None,
        "by_priority": by(lambda p: p.get("priority", "unknown")),
        "by_signal_family": by(family),
    }


def _group(reviewed, cases, latest, keyfn):
    out = defaultdict(lambda: {"reviewed": 0, "worth_review": 0, "measured": 0, "suspected_or_confirmed": 0})
    for k in reviewed:
        g = out[keyfn(cases[k])]
        g["reviewed"] += 1
        flag = latest[k]["worth_review"]
        if flag is not None:
            g["measured"] += 1
            g["worth_review"] += int(flag)
        g["suspected_or_confirmed"] += latest[k]["conclusion"] in ("suspected", "confirmed")
    for g in out.values():
        g["worth_review_rate"] = g["worth_review"] / g["measured"] if g["measured"] else None
    return dict(sorted(out.items()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = kpis(a.db)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if not k.startswith("by_")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
