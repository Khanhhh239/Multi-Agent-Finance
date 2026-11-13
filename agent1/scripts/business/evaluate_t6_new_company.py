"""Explicit three-phase evaluation of the current T1/partial/T6 runtime."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent1.adaptive.data import fingerprint
from agent1.adaptive.t1_catalog import GlobalCatalog
from agent1.adaptive.t1_update import UpdatePolicy
from experiments.t6_backtest.new_company import (
    freeze_predictions, lock_protocol, read_protocol, score_frozen, write_once,
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("lock", "predict", "score"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path, help="Required for lock only")
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args()
    protocol_path = args.output / "protocol.json"
    if args.phase == "lock":
        if args.config is None:
            parser.error("lock requires --config")
        config = read(args.config)
        companies = []
        for case in config["companies"]:
            source = (args.config.parent / case["dataset"]).resolve()
            companies.append(dict(case, dataset=str(source), dataset_sha256=fingerprint(read(source))))
        lock_protocol(protocol_path, companies, GlobalCatalog(args.catalog),
                      policy=UpdatePolicy(**config.get("update_policy", {})),
                      development_firms=config.get("development_firms", ()),
                      **config.get("simulation", {}))
        print("Locked cohort, history adaptation, cash paths and alert rule.")
        return
    protocol = read_protocol(protocol_path)
    catalog = GlobalCatalog(args.catalog) if args.phase == "predict" else None
    results = []
    for case in protocol["spec"]["companies"]:
        data = read(case["dataset"])
        if args.phase == "predict":
            freeze_predictions(protocol_path, case["firm_id"], data, catalog)
        else:
            results.append(score_frozen(protocol_path, case["firm_id"], data))
        print(case["firm_id"] + ": " + args.phase, flush=True)
    if results:
        # Equal weight per company; week/invoice counts do not inflate sample size.
        names = protocol["spec"]["models"]
        metrics = ("mae_balance_vnd", "mae_weekly_ar_vnd", "mae_cumulative_ar_vnd",
                   "coverage80", "interval_score80_vnd", "crps_balance_vnd", "energy_path_vnd",
                   "brier_weekly_shortfall", "brier_any_shortfall")
        write_once(args.output/"summary.json", dict(
            companies=len(results), protocol_sha256=protocol["spec_sha256"],
            models={name: {key: sum(r["models"][name][key] for r in results)/len(results)
                           for key in metrics} for name in names},
            interpretation="Declared held-out companies; synthetic flags remain per company; no tenant activation"))


if __name__ == "__main__":
    main()
