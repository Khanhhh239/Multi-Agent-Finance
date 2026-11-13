"""Lock -> adapt on history -> freeze paths -> score unopened company futures.

This runner never promotes a tenant model. A holdout declaration is recorded,
not inferred from a company's name or a previously inspected synthetic World.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from agent1.adaptive.data import fingerprint, validate_dataset
from agent1.adaptive.methods import forecast
from agent1.adaptive.t1_data import visible_data
from agent1.adaptive.t1_update import UpdatePolicy, code_signature, train_update
from agent1.adaptive.t10_explanations import engine_identity
from experiments.t6_backtest.evaluation import measure, score

VERSION = "new-company-partial-paths-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def source_signature():
    root = Path(__file__).resolve().parents[2]
    names = ("agent1/adaptive/methods.py", "agent1/adaptive/cash_history.py",
             "agent1/adaptive/obligations.py", "experiments/t6_backtest/evaluation.py",
             "experiments/t6_backtest/new_company.py")
    return digest(dict(t1=code_signature(), engine=engine_identity(), files={n: hashlib.sha256((root/n).read_bytes()).hexdigest()
                                                   for n in names}))


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != json.loads(encoded):
            raise ValueError("Frozen evidence changed; use a new run directory")
        return
    with path.open("x", encoding="utf-8") as output:
        output.write(encoded)


def lock_protocol(path, companies, catalog, *, policy=None, simulation_paths=1000,
                  simulation_seed=7, cash_floor=0.0, development_firms=()):
    """Commit cohort, adaptation, path law and alert rule before fitting/scoring."""
    if type(simulation_paths) is not int or not 100 <= simulation_paths <= 10000:
        raise ValueError("Invalid simulation budget")
    if type(simulation_seed) is not int or not 0 <= simulation_seed < 2**32 or not np.isfinite(cash_floor):
        raise ValueError("Invalid simulation seed/floor")
    if not companies or len({r["firm_id"] for r in companies}) != len(companies):
        raise ValueError("Need distinct held-out companies")
    for company in companies:
        if company.get("heldout_from_global_and_policy_selection") is not True:
            raise ValueError("Declare whether this company is an unopened holdout")
        if company["firm_id"] in development_firms:
            raise ValueError("Development company cannot be a holdout")
        end = date.fromisoformat(company["cutoff"]) + timedelta(weeks=13)
        if date.fromisoformat(company["truth_asof"]) < end or not company["accounts"]:
            raise ValueError("Need mature bank truth and account scope")
        if not np.isfinite(company["opening_balance"]):
            raise ValueError("Invalid opening balance")
    body = dict(version=VERSION, catalog_sha256=catalog.digest, source_sha256=source_signature(),
                companies=companies, development_firms=list(development_firms),
                update_policy=asdict(policy or UpdatePolicy()),
                forecast_policy=dict(horizon_weeks=13, simulation_paths=simulation_paths,
                                     simulation_seed=simulation_seed, shap_limit=0, cash_floor=cash_floor,
                                     include_operating=False, shared_customer_risk=False),
                models=["global", "adapted"],
                alert_rule="expected balance below floor OR weekly simulation probability >= 0.25",
                selection="history through cutoff only; no selection on future scores",
                calibration="none; raw partial paths first; later studies need separate past OOS errors",
                aggregation="one result per company; no invoice/origin independence claim")
    body = json.loads(json.dumps(body, ensure_ascii=False, allow_nan=False))
    path = Path(path)
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous["spec_sha256"] != digest(body):
            raise ValueError("Locked protocol changed")
        return previous
    result = dict(spec=body, spec_sha256=digest(body), locked_at=datetime.now(timezone.utc).isoformat())
    write_once(path, result)
    return result


def read_protocol(path, catalog=None):
    protocol = json.loads(Path(path).read_text(encoding="utf-8"))
    spec = protocol["spec"]
    if digest(spec) != protocol["spec_sha256"] or source_signature() != spec["source_sha256"]:
        raise ValueError("Protocol/source changed after lock")
    if catalog and catalog.digest != spec["catalog_sha256"]:
        raise ValueError("Global catalog changed after lock")
    return protocol


def company_spec(protocol, firm):
    return next(r for r in protocol["spec"]["companies"] if r["firm_id"] == firm)


def freeze_predictions(protocol_path, firm, data, catalog, *, trainer=None):
    protocol = read_protocol(protocol_path, catalog)
    case = company_spec(protocol, firm)
    if fingerprint(data) != case["dataset_sha256"]:
        raise ValueError("Company data changed after lock")
    validate_dataset(data)
    # Only this physically filtered snapshot reaches fitting and forecasting.
    history = visible_data(data, case["cutoff"])
    folder = Path(protocol_path).parent / ("company_" + digest(firm)[:16])
    if (folder/"receipt.json").exists():
        receipt = json.loads((folder/"receipt.json").read_text(encoding="utf-8"))
        if (receipt["protocol_sha256"] != protocol["spec_sha256"]
                or receipt["history_sha256"] != fingerprint(history)):
            raise ValueError("Frozen prediction history/protocol changed")
        for name, expected in receipt["predictions"].items():
            if digest(json.loads((folder/(name+".json")).read_text(encoding="utf-8"))) != expected:
                raise ValueError("Frozen forecast changed before scoring")
        return folder
    baseline = catalog.default_bundle(case["cutoff"])
    adapted = (trainer or train_update)(history, case["cutoff"], incumbent=baseline,
        catalog=catalog, policy=UpdatePolicy(**protocol["spec"]["update_policy"]))
    plans = {}
    for name, bundle in (("global", baseline), ("adapted", adapted)):
        plan = forecast(history, case["cutoff"], case["opening_balance"], bundle,
                        return_paths=True, **protocol["spec"]["forecast_policy"])
        plan["accounts"] = case["accounts"]
        plans[name] = plan
    # A safe numeric directory avoids using untrusted company names as paths.
    for name, plan in plans.items():
        write_once(folder/(name+".json"), plan)
    receipt = dict(firm_id=firm, protocol_sha256=protocol["spec_sha256"],
                   history_sha256=fingerprint(history),
                   predictions={name: digest(plan) for name, plan in plans.items()},
                   adaptation={k: adapted.get(k) for k in
                               ("t1_version", "serving_manifest", "promotion_status", "selection", "audit", "windows")})
    write_once(folder/"receipt.json", receipt)
    return folder


def path_scores(paths, actual, floor):
    """Empirical CRPS and joint energy score, retaining temporal dependence.

    Energy uses all cross pairs in blocks (V-statistic), without an n² tensor.
    Scores are in VND; Euclidean distances are normalized by sqrt(horizon).
    """
    x, y = np.asarray(paths, float), np.asarray(actual, float)
    if (x.ndim != 2 or len(x) < 2 or x.shape[1:] != y.shape or not np.isfinite(x).all()
            or not np.isfinite(y).all() or not np.isfinite(floor)):
        raise ValueError("Invalid joint cash paths/truth")
    n, horizon = x.shape
    # Center before distance identities: VND balances can be very large while
    # differences between paths are small. Both scores are translation invariant.
    centered = x-y
    ordered = np.sort(centered, axis=0)
    crps = abs(centered).mean(0) - ((2*np.arange(1, n+1)-n-1)[:, None]*ordered).sum(0)/n**2
    pair_distance = 0.0
    # Squared-distance identity bounds memory by O(128*n), independent of H.
    norm = (centered*centered).sum(1)
    for start in range(0, n, 128):
        block = centered[start:start+128]
        distance2 = norm[start:start+128, None] + norm[None, :] - 2*block@centered.T
        pair_distance += np.sqrt(np.maximum(0, distance2)).sum()
    energy = (np.linalg.norm(centered, axis=1).mean() - pair_distance/(2*n*n))/np.sqrt(horizon)
    probability = float((x < floor).any(axis=1).mean())
    event = bool((y < floor).any())
    return dict(crps_balance_vnd=float(crps.mean()), energy_path_vnd=float(energy),
                any_shortfall_probability=probability, actual_any_shortfall=event,
                brier_any_shortfall=float((probability-event)**2))


def score_frozen(protocol_path, firm, data):
    """Open future labels only after the two complete forecasts have been saved."""
    protocol = read_protocol(protocol_path)
    case = company_spec(protocol, firm)
    if fingerprint(data) != case["dataset_sha256"]:
        raise ValueError("Company truth changed after lock")
    folder = Path(protocol_path).parent / ("company_" + digest(firm)[:16])
    receipt = json.loads((folder/"receipt.json").read_text(encoding="utf-8"))
    if receipt["protocol_sha256"] != protocol["spec_sha256"]:
        raise ValueError("Prediction receipt does not match protocol")
    result = dict(firm_id=firm, protocol_sha256=protocol["spec_sha256"], models={})
    for name in protocol["spec"]["models"]:
        plan = json.loads((folder/(name+".json")).read_text(encoding="utf-8"))
        if digest(plan) != receipt["predictions"][name]:
            raise ValueError("Frozen forecast changed before scoring")
        rows = measure(data, plan, case["truth_asof"], case["accounts"])
        actual = [r["actual_balance"] for r in rows]
        result["models"][name] = dict(**score(rows), **path_scores(
            plan["balance_paths"], actual, plan["cash_floor"]))
    write_once(folder/"scores.json", result)
    return result
