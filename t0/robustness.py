"""Independent intent fixtures for new allocation capabilities and failure modes."""

from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import platform
import random
from time import perf_counter

from . import allocation, constrained, offline
from .data import fingerprint, iso_date, prepare_experiment_output, read_json, read_jsonl, write_json, write_jsonl
from .evaluation import describe


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "research/references/data-checks/t0/allocation-robustness-plan-v1.json"


def generate(seed, blocks, profile, noise):
    invoices, payments, truth, manifest = offline.generate(seed, blocks, "clean")
    rng = random.Random(seed + 987654)

    def identifier():
        return f"R{rng.getrandbits(128):032x}"

    def invoice(party, amount, currency):
        r = {"tenant_id": "SYNTH", "id": identifier(), "invoice_number": identifier(), "side": "AR",
             "party_id": party, "currency": currency, "amount_minor": amount, "issued_on": "2025-01-01",
             "available_on": "2025-01-01"}
        invoices.append(r)
        return r

    def payment(targets, amounts, scenario, currency, *, references=None, gross=None, remittance=False):
        refs = targets if references is None else references
        p = {"tenant_id": "SYNTH", "id": identifier(), "side": "AR", "party_id": targets[0]["party_id"],
             "currency": currency, "amount_minor": sum(amounts) if gross is None else gross,
             "payment_on": "2025-01-31", "available_on": "2025-01-31",
             "reference": " + ".join(i["invoice_number"] for i in refs)}
        if remittance:
            p["remittance"] = [{"invoice_number": i["invoice_number"], "amount_minor": a} for i, a in zip(targets, amounts)]
        payments.append(p)
        for i, amount in zip(targets, amounts):
            truth.append({"tenant_id": "SYNTH", "payment_id": p["id"], "invoice_id": i["id"], "side": "AR",
                          "currency": currency, "amount_minor": amount, "scenario": scenario})

    for _ in range(blocks):
        for currency, unit in (("VND", 100000), ("USD", 100)):
            party = identifier()
            i1, i2 = [invoice(party, 100 * unit, currency) for _ in range(2)]
            payment([i1], [100 * unit], "wrong_valid_reference", currency, references=[i2])
            party = identifier()
            i1, i2 = invoice(party, 40 * unit, currency), invoice(party, 60 * unit, currency)
            payment([i1, i2], [40 * unit, 30 * unit], "unique_nm", currency)
            payment([i2], [30 * unit], "unique_nm", currency)
            party = identifier()
            i1, i2 = invoice(party, 40 * unit, currency), invoice(party, 60 * unit, currency)
            payment([i1, i2], [25 * unit, 30 * unit], "explicit_partial_group", currency, gross=80 * unit, remittance=True)
            party = identifier()
            i1, i2 = invoice(party, 40 * unit, currency), invoice(party, 60 * unit, currency)
            payment([i1, i2], [30 * unit, 20 * unit], "nonunique_nm", currency)
            payment([i1, i2], [10 * unit, 40 * unit], "nonunique_nm", currency)
    # The observation channel runs after every intent/truth is fixed.
    mask, unknown, lag = noise.get(profile, [0, 0, 0])
    for p in payments:
        if rng.random() < mask:
            p["reference"] = "Thanh toan"
        if rng.random() < unknown:
            p["party_id"] = ""
        if lag:
            p["payment_on"] = (date.fromisoformat(p["payment_on"]) + timedelta(days=rng.randint(-lag, lag))).isoformat()
            # Received by cutoff independently of settlement effective day.
            p["available_on"] = max(p["available_on"], p["payment_on"])
    manifest = {**manifest, "profile": profile, "cutoff": "2025-02-05", "task": "synthetic_allocation_robustness",
                "limits": "Capability/regression suite, not SME distribution; remittance is observed input, never reconstructed from truth"}
    return invoices, payments, truth, manifest


def benchmark(output, plan=None):
    plan = read_json(PLAN) if plan is None else plan
    seeds = plan["seeds"]
    if (set(seeds) != {"validation", "test"} or any(not isinstance(v, list) or not v or
            any(type(s) is not int for s in v) or len(v) != len(set(v)) for v in seeds.values())
            or set(seeds["validation"]) & set(seeds["test"])):
        raise ValueError("nonoverlapping unique integer world seeds required")
    if plan["methods"] != ["v2_full", "constrained_flow"] or plan["profiles"] != ["clean", "masked", "noisy", "stress"]:
        raise ValueError("frozen robustness methods/profiles required")
    if type(plan["blocks"]) is not int or plan["blocks"] < 1:
        raise ValueError("positive block count required")
    if set(plan["noise"]) != {"masked", "noisy", "stress"}:
        raise ValueError("noise profiles required")
    for mask, unknown, lag in plan["noise"].values():
        if (any(type(v) not in (int, float) or not 0 <= v <= 1 for v in (mask, unknown))
                or type(lag) is not int or not 0 <= lag <= 7):
            raise ValueError("invalid frozen noise budget")
    config = allocation.Config(**plan["allocation_config"])
    output = prepare_experiment_output(output)
    code_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted((ROOT / "t0").glob("*.py"))}
    experiment = {"plan": plan, "plan_hash": fingerprint(plan), "code_hashes": code_hashes,
                  "python": platform.python_version(), "platform": platform.platform(),
                  "created_at_utc": datetime.now(timezone.utc).isoformat(), "test_scope": "Inspected synthetic development fixtures, not domain holdout"}
    write_json(output / "experiment.json", experiment)
    runs = []
    for split, split_seeds in seeds.items():
        for seed in split_seeds:
            for profile in plan["profiles"]:
                inv, pay, truth, manifest = generate(seed, plan["blocks"], profile, plan["noise"])
                folder = output / "datasets" / split / f"{profile}-{seed}"
                write_jsonl(folder / "invoices.jsonl", inv)
                write_jsonl(folder / "payments.jsonl", pay)
                write_jsonl(folder / "truth.jsonl", truth)
                write_json(folder / "manifest.json", {**manifest, "input_hash": fingerprint([inv, pay]), "truth_hash": fingerprint(truth)})
                universe = ({(i["tenant_id"], i["id"]) for i in inv}, {(p["tenant_id"], p["id"]) for p in pay})
                for rows, field in ((inv, "issued_on"), (pay, "payment_on")):
                    for row in rows:
                        iso_date(row["available_on"])
                        iso_date(row[field])
                inv = [{k: i[k] for k in plan["feature_allowlist"]["invoices"] if k in i}
                       for i in inv if max(i["available_on"], i["issued_on"]) <= manifest["cutoff"]]
                pay = [{k: p[k] for k in plan["feature_allowlist"]["payments"] if k in p}
                       for p in pay if max(p["available_on"], p["payment_on"]) <= manifest["cutoff"]]
                for method in plan["methods"]:
                    operation = constrained.allocate if method == "constrained_flow" else allocation.allocate
                    started = perf_counter()
                    predicted = operation(inv, pay, config)
                    runtime = perf_counter() - started
                    write_json(folder / f"predictions-{method}.json", predicted)
                    measured = offline.metrics(inv, pay, read_jsonl(folder / "truth.jsonl"), predicted, universe)
                    repeated = operation(inv[::-1], pay[::-1], config)
                    measured.update(runtime_seconds=runtime, order_stable=predicted["allocation_hash"] == repeated["allocation_hash"])
                    runs.append({"split": split, "seed": seed, "profile": profile, "method": method, "metrics": measured})
    summary = []
    for split in seeds:
        for profile in plan["profiles"]:
            for method in plan["methods"]:
                values = [r["metrics"] for r in runs if (r["split"], r["profile"], r["method"]) == (split, profile, method)]
                summary.append({"split": split, "profile": profile, "method": method,
                                "metrics": {k: describe([r[k] for r in values]) for k in ("precision", "recall", "runtime_seconds")},
                                "all_invariants_pass": all(not r["invariant_errors"] for r in values),
                                "all_order_stable": all(r["order_stable"] for r in values)})
    end_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((ROOT / "t0").glob("*.py"))}
    if code_hashes != end_hashes:
        raise ValueError("code changed during robustness benchmark")
    report = {"experiment": experiment, "runs": runs, "summary": summary,
              "all_pass": all(r["all_invariants_pass"] and r["all_order_stable"] for r in summary)}
    write_json(output / "report.json", report)
    return report
