"""Backtest frozen global T1 versus origin-trained Workspace T1 in T6.

Separates opening-book receipts from bank balances. New-invoice forecasting is
disabled. Original bank truth stays unchanged; counterfactual closed-book stress
fixtures have separate tables and no generalization claim. No model activation.
"""
import argparse
from collections import defaultdict
from datetime import date, timedelta
import gzip
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import time
import warnings

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from threadpoolctl import threadpool_limits

from agent1.adaptive.data import account_scope, fingerprint
from agent1.adaptive.compact_t1 import load_research_t1_bundle
from experiments.t1_compact.historical_workspace import forecast, train
from agent1.adaptive.operating import select_operating
from experiments.t6_backtest.evaluation import measure, score, ar_score, event_score, knowledge_snapshot
from experiments.t6_backtest.stress import make_stress, PROFILES, SEED
from scripts.business.backtest_t6_baseline import (
    KINDS, CUTOFFS, HORIZON, load_demo, opening_balance, validate_origins,
    cash_equivalent, model_details, training_config, sha256, write_json, write_csv,
)

VERSION = "t6-global-scope-no-new-invoice-v1"
MODELS = ("workspace", "global75_25")
SCOPES = ("ar_only", "ar_operating_schedule")


def capture(output, source_data, global_run):
    """Capture executable sources, calendar resources, data, and release evidence."""
    targets = []
    for package in (
        "agent1", "agent1_service", "experiments/t6_backtest", "experiments/t1_compact",
        "outputs/t1/global_local_families_20261113/source_snapshot/agent1/adaptive",
    ):
        for p in sorted((ROOT/package).rglob("*")):
            if p.is_file() and p.suffix in (".py", ".json"):
                targets.append((p, output/"runtime_source"/p.relative_to(ROOT)))
    for name in ("backtest_t6_global.py", "backtest_t6_baseline.py"):
        p = ROOT/"scripts/business"/name
        targets.append((p, output/"runtime_source/scripts/business"/name))
    for i, kind in enumerate(KINDS, 1):
        p = source_data/f"{i:02}_{kind}.csv"
        targets.append((p, output/"inputs"/p.name))
    targets.append((source_data/"manifest.json", output/"inputs/manifest.json"))
    release = json.loads((global_run/"release.json").read_text(encoding="utf-8"))
    release_names = set(release["required_hashes"]) | {"release.json"}
    release_names |= {str(p.relative_to(global_run)) for p in
                      (global_run/release["artifact_directory"]).rglob("*") if p.is_file()}
    for name in sorted(release_names):
        targets.append((global_run/name, output/"global_release"/name))
    entries = []
    for source, destination in targets:
        content = source.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != content:
            raise ValueError("Frozen input/source changed; use a new output directory: "+str(destination))
        destination.write_bytes(content)
        entries.append(dict(original=str(source.resolve()), snapshot=str(destination.resolve()), sha256=sha256(destination)))
    if not all(sha256(Path(r["original"])) == r["sha256"] for r in entries):
        raise ValueError("Inputs changed during snapshot")
    write_json(output/"snapshot.json", dict(files=entries))


def locked_protocol(output, data, inventory, cutoffs):
    source_files = [p for p in (ROOT/"agent1").rglob("*") if p.is_file() and p.suffix in (".py", ".json")]
    source_files += list((ROOT/"experiments/t6_backtest").glob("*.py"))
    source_files += list((ROOT/"experiments/t1_compact").glob("*.py"))
    source_files += list((ROOT/"outputs/t1/global_local_families_20261113/source_snapshot/agent1/adaptive").glob("*.py"))
    source_files += [Path(__file__), ROOT/"scripts/business/backtest_t6_baseline.py"]
    value = dict(version=VERSION, synthetic=True, cutoff_dates=cutoffs, horizon_weeks=HORIZON,
        truth_asof=max(r["known_at"] for r in data["statements"]),
        simulation_paths=1000, simulation_seed=7, shap_limit=0, cash_floor=200_000_000,
        timing_dependence="independent", alert_rule="expected balance < floor OR simulated weekly probability >= .25",
        new_invoice_forecasting=False, operating_candidates=["seasonal", "gbm"], operating_try_deep=False,
        training_config=training_config(), global_refit=False, local_finetune=False,
        workspace_training="Default full candidate selection, validation, audit and refit; past data at each origin only.",
        sources={str(p.relative_to(ROOT)): sha256(p) for p in source_files},
        global_release_sha256=sha256(output/"global_release/release.json"),
        full_data_sha256=fingerprint(data), input_files=inventory,
        original_data_policy="Unchanged actual bank balances; excluded future-invoice receipts and unexplained cash remain explicit scope effects.",
        stress_design=dict(seed=SEED, profiles=PROFILES,
            unit="same demo AR book at four origins; scenario repeats are not independent firms",
            future_invoices="closed book: no invoices issued after origin in separate generated fixtures",
            budget="trailing 13-week cash only; profile amounts and floor locked before scoring",
            bank_truth="fresh fixture balances from opening cash and generated movements; never overwrite original demo"),
        calibration="none; retrospective plans are not eligible prospective calibration history",
        scoring="Separate AR cumulative bands, raw bank balance bands and weekly/context alert decisions; horizon 1-4 and 5-13.",
        threshold_tuning=False, selection_on_outcomes=False,
        limitations=["one synthetic company and reused historical origins", "stress fixtures are counterfactual",
                     "new-invoice receipts excluded from forecasts", "no real-company or pilot acceptance"])
    path = output/"protocol.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
        raise ValueError("Locked protocol changed")
    write_json(path, value)
    return value


def checkpoint(output, cutoff, past, p):
    target = output/"models"/cutoff
    signature = dict(data_hash=fingerprint(past), sources=p["sources"], training=p["training_config"],
                     new_invoice_forecasting=False, operating_candidates=p["operating_candidates"])
    if (target/"receipt.json").exists():
        receipt = json.loads((target/"receipt.json").read_text(encoding="utf-8"))
        if receipt["signature"] != signature or receipt["sha256"] != sha256(target/"bundle.pkl"):
            raise ValueError("Checkpoint input/source mismatch")
        result = pickle.loads((target/"bundle.pkl").read_bytes())
        print(f"{cutoff}: reused verified origin-trained bundle", flush=True)
        return result, receipt
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        local = train(past, cutoff, progress=lambda msg: print(cutoff+": "+msg, flush=True))
        operating = select_operating(past, cutoff, try_deep=False, include_new_credit=False)
    if local["asof"] != cutoff or operating is None:
        raise ValueError("Historical T1 or operating learner is unavailable")
    if operating.get("credit") is not None:
        raise ValueError("New-invoice branch must be disabled")
    local["operating"] = operating
    target.mkdir(parents=True, exist_ok=True)
    (target/"bundle.pkl").write_bytes(pickle.dumps(local, protocol=pickle.HIGHEST_PROTOCOL))
    receipt = dict(signature=signature, sha256=sha256(target/"bundle.pkl"), seconds=time.perf_counter()-started,
        warnings=sorted({str(w.message) for w in caught}), t1=model_details(local),
        operating=dict(name=operating["name"], validation=operating["validation"], audit_mae=operating["audit_mae"],
                       reference_mae=operating["reference_mae"], new_invoice_forecasting=False))
    write_json(target/"receipt.json", receipt)
    return local, receipt


def forecast_checked(data, cutoff, bundle, scope, confirmed, p):
    selected = dict(data)
    if scope == "ar_only":
        selected.update(outflows=[], expense_payments=[])
    past = knowledge_snapshot(selected, cutoff)
    accounts = account_scope(past, cutoff)
    balance = opening_balance(past, cutoff, accounts)
    options = dict(bundle=bundle, horizon_weeks=HORIZON, simulation_paths=p["simulation_paths"],
        simulation_seed=p["simulation_seed"], shap_limit=p["shap_limit"], cash_floor=p["cash_floor"],
        include_operating=scope != "ar_only", confirmed_weeks=confirmed if scope != "ar_only" else ())
    plan = forecast(selected, cutoff, balance, **options)
    replay = forecast(past, cutoff, balance, **options)
    if not cash_equivalent(plan, replay):
        raise ValueError("Removing future knowledge changed the forecast")
    if plan["new_credit_included"]:
        raise ValueError("New-invoice branch was unexpectedly used")
    return plan, accounts


def summarize(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["dataset"], r["profile"], r["model"], r["scope"])].append(r)
    bank, ar = [], []
    for (dataset, profile, model, scope), group in sorted(groups.items()):
        for horizon, subset in (("w1-13", group), ("w1-4", [r for r in group if r["week"] <= 4]),
                                ("w5-13", [r for r in group if r["week"] >= 5])):
            bank.append(dict(dataset=dataset, profile=profile, model=model, scope=scope, horizon=horizon,
                             **score(subset), **event_score(subset)))
            if scope == "ar_only":
                ar.append(dict(dataset=dataset, profile=profile, model=model, horizon=horizon, **ar_score(subset)))
    return bank, ar


def render_report(output, p, bank, ar, contexts):
    selected = [r for r in bank if r["horizon"] == "w1-13"]
    def m(v):
        return f"{v/1e6:,.2f}"
    def f(v):
        return "—" if v is None else f"{v:.1%}"
    lines = ["# Backtest T6 global, phạm vi tiền rõ ràng — 13/11/2026", "",
        "Dữ liệu 100% synthetic. Global là bản 18 feature Neural 75%/customer 25% đã khóa; Workspace học độc lập tại từng ngày chốt. Không học tiếp, đổi trọng số hoặc kích hoạt tenant.", "",
        "## Phạm vi và giao thức", "",
        "- Loại hoàn toàn nhánh dự báo thu từ hóa đơn phát hành sau ngày chốt, theo yêu cầu. Không fit/select learner new-credit.",
        "- Hai đường T6: `ar_only` chỉ công nợ đang mở; `ar_operating_schedule` thêm thu bán ngay, lịch chi được biết và chi biến đổi. Hai model dùng cùng learner hoạt động/lịch chi/số dư đầu.",
        "- 1.000 đường mô phỏng độc lập, seed 7; kỳ 13 tuần, ngưỡng tiền 200 triệu; giữ nguyên quy tắc cảnh báo của dịch vụ. Tắt SHAP trong vòng chấm điểm để dành thời gian cho backtest.",
        "- Bốn ngày chốt: "+", ".join(p["cutoff_dates"])+". Các cửa sổ không chồng lấn. Mọi forecast được chạy lại khi bỏ bản ghi biết sau ngày chốt.",
        "- Dải thô chưa hiệu chỉnh. P10–P90 đánh giá độ phủ từng tuần, không phải xác suất phủ toàn bộ 13 tuần. Không dùng các kế hoạch hồi cứu để giả thành lịch sử hiệu chỉnh prospective.", "",
        "## Dự thu riêng danh mục mở", "",
        "Chỉ bảng dữ liệu gốc dưới đây dùng để so dự thu; các stress lặp lại cùng danh mục nên không được cộng thêm cỡ mẫu T1. Đơn vị tiền: triệu VND.", "",
        "| Model | MAE thu tuần | MAE thu lũy kế | Độ phủ dải thu lũy kế | Độ rộng |",
        "|---|---:|---:|---:|---:|"]
    for r in ar:
        if r["dataset"] == "original" and r["horizon"] == "w1-13":
            lines.append(f"| {r['model']} | {m(r['mae_weekly_ar_vnd'])} | {m(r['mae_cumulative_ar_vnd'])} | {f(r['coverage80'])} | {m(r['mean_width80_vnd'])} |")
    lines += ["", "## Số dư ngân hàng thực tế của bộ gốc", "",
        "Giữ nguyên sao kê gốc, kể cả thu từ hóa đơn mới. Vì nhánh này đã bị loại, tiền đó nằm trong tác động ngoài phạm vi, không được âm thầm xóa khỏi nhãn. Bộ gốc thiếu lịch chi lịch sử; bật hoạt động không khiến phạm vi trở thành đầy đủ.", "",
        "| Model | Đường T6 | MAE số dư | Độ phủ P10–P90 | Độ rộng | Interval score 80% | Báo giả / bỏ sót |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for r in selected:
        if r["dataset"] == "original":
            lines.append(f"| {r['model']} | {r['scope']} | {m(r['mae_balance_vnd'])} | {f(r['coverage80'])} | {m(r['mean_width80_vnd'])} | {m(r['interval_score80_vnd'])} | {r['false_alert_weeks']} / {r['missed_shortfall_weeks']} |")
    lines += ["", "## Stress số dư trong phạm vi đã khai báo", "",
        "Bốn profile được khóa trước chấm: buffered, payment_pressure, cost_shock và schedule_gap. Đây là 16 fixture phản thực tế từ cùng bốn danh mục Đại Phát; không phải 16 doanh nghiệp độc lập hoặc holdout mới cho T1.",
        "Các fixture ngừng phát hành hóa đơn sau ngày chốt. Số dư đầu lấy từ sao kê lịch sử; ngân hàng tương lai được dựng từ tiền thu danh mục mở, bán thu ngay, chi biến đổi và chi hợp đồng. Chi phí dùng quy mô tiền quá khứ; không chọn số tiền/ngưỡng theo kết quả tương lai.",
        "payment_pressure có khoản chi lớn tuần 4 được biết tại origin; cost_shock tăng chi biến đổi tuần 5–9 chưa được biết tại origin; schedule_gap có một phần lịch chỉ được biết ngày chi. Bảng sau chỉ hiển thị đường có hoạt động/lịch; bảng đầy đủ giữ cả ar_only.", "",
        "| Profile | Model | MAE số dư | Độ phủ | Độ rộng | Tuần thiếu tiền | Báo giả / bỏ sót | Recall tuần | Precision tuần | Brier tuần |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in selected:
        if r["dataset"] == "stress" and r["scope"] == "ar_operating_schedule":
            lines.append(f"| {r['profile']} | {r['model']} | {m(r['mae_balance_vnd'])} | {f(r['coverage80'])} | {m(r['mean_width80_vnd'])} | {r['actual_shortfall_weeks']} | {r['false_alert_weeks']} / {r['missed_shortfall_weeks']} | {f(r['recall_weekly'])} | {f(r['precision_weekly'])} | {r['brier_weekly_shortfall']:.4f} |")
    lines += ["", "## Cách đọc và giới hạn", "",
        "- `weekly.csv` phân rã sai số số dư thành lỗi thu AR, thu bán ngay, lịch chi, chi biến đổi và tác động ngoài phạm vi; tổng phải khớp sai số ngân hàng trong 0,01 VND.",
        "- Số dư được chấm trực tiếp trên sao kê có đủ phủ, không lấy dự báo trừ ngược rồi gọi là số dư thực. Không coi tuần thiếu sao kê là dòng tiền bằng 0.",
        "- MAE, bias, độ phủ, độ rộng, interval score, Brier, báo giả/bỏ sót, precision/recall được giữ theo profile, model, đường T6 và tuần 1–4/5–13. Recall/precision để trống khi không có mẫu số.",
        "- `metrics.csv` có thêm đánh giá cảnh báo có ít nhất một lần trong kỳ ở cấp context; không ghép xác suất từng tuần thành một xác suất chung giả định độc lập.",
        "- Một doanh nghiệp synthetic, các stress chung danh mục. Không tính khoảng tin cậy bằng cách coi tuần/profile là doanh nghiệp độc lập; không suy ra độ chính xác trên SME thật.",
        "- Nghiên cứu không chọn model thắng để thay dịch vụ, không hiệu chỉnh ngưỡng trên outcomes và không đổi gate pilot.", "",
        "## Bằng chứng và chạy lại", "",
        "`protocol.json` khóa thiết kế trước chấm; `snapshot.json` giữ hash nguồn/đầu vào; `global_release/` giữ release global; `models/` giữ Workspace và learner hoạt động tại từng ngày; `plans/` giữ dự báo thực; `fixtures/` giữ stress; `contexts.json`, `metrics.csv`, `ar_metrics.csv`, `per_origin_metrics.csv`, `weekly.csv`, `verification.json` giữ số đo và kiểm tra.", "",
        "```powershell", ".\\.venv\\Scripts\\python.exe -X utf8 agent1/scripts/business/backtest_t6_global.py", "```", ""]
    (output/"REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def run(output, data_dir, cutoffs):
    started = time.perf_counter()
    data, inventory = load_demo(data_dir)
    p = locked_protocol(output, data, inventory, cutoffs)
    validate_origins(cutoffs, p["truth_asof"])
    rows, contexts, per_origin = [], [], []
    for cutoff in cutoffs:
        past = knowledge_snapshot(data, cutoff)
        local, training = checkpoint(output, cutoff, past, p)
        global_bundle = load_research_t1_bundle(output/"global_release", cutoff, local)
        if global_bundle["operating"] is not local["operating"]:
            raise ValueError("T1 replacement changed the operating learner")
        bundles = dict(workspace=local, global75_25=global_bundle)
        cases = [("original", "raw_dai_phat", data, dict(confirmed_weeks=[]), p["truth_asof"])]
        for profile in PROFILES:
            fixture, design = make_stress(data, cutoff, profile, account_scope(past, cutoff))
            fixture_path = output/"fixtures"/f"{cutoff}_{profile}.json.gz"
            fixture_path.parent.mkdir(parents=True, exist_ok=True)
            # Deterministic gzip metadata makes identical fixture bytes reproducible.
            fixture_path.write_bytes(gzip.compress(json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode(), mtime=0))
            cases.append(("stress", profile, fixture, design, str(date.fromisoformat(cutoff)+timedelta(weeks=13))))
        for dataset, profile, given, design, truth_asof in cases:
            for model, bundle in bundles.items():
                for scope in SCOPES:
                    plan, accounts = forecast_checked(given, cutoff, bundle, scope, design["confirmed_weeks"], p)
                    measured = measure(given, plan, truth_asof, accounts)
                    for r in measured:
                        r.update(dataset=dataset, profile=profile, model=model, scope=scope)
                    rows.extend(measured)
                    metrics = score(measured)
                    per_origin.append(dict(dataset=dataset, profile=profile, model=model, scope=scope, cutoff=cutoff, **metrics))
                    context = dict(dataset=dataset, profile=profile, model=model, scope=scope, cutoff=cutoff,
                        data_hash=fingerprint(given), origin_data_hash=fingerprint(knowledge_snapshot(given, cutoff)),
                        accounts=accounts, opening_balance=plan["opening_balance"], open_invoices=plan["open_invoices"],
                        outstanding=plan["outstanding"], operating_included=plan["operating_included"],
                        new_credit_included=plan["new_credit_included"], unknown_outflow_weeks=plan["unknown_outflow_weeks"],
                        future_removal_invariance=True, design=design, metrics=metrics,
                        workspace_bundle_sha256=training["sha256"], t1_provenance=plan.get("t1_provenance"))
                    contexts.append(context)
                    name = f"{cutoff}_{dataset}_{profile}_{model}_{scope}.json"
                    write_json(output/"plans"/name, plan)
                    print(f"{cutoff} {profile} {model} {scope}: MAE={metrics['mae_balance_vnd']/1e6:.1f}m coverage={metrics['coverage80']:.1%} events={metrics['actual_shortfall_weeks']}", flush=True)
    bank, ar = summarize(rows)
    write_csv(output/"weekly.csv", rows)
    write_csv(output/"metrics.csv", bank)
    write_csv(output/"ar_metrics.csv", ar)
    write_csv(output/"per_origin_metrics.csv", per_origin)
    write_json(output/"contexts.json", contexts)
    render_report(output, p, bank, ar, contexts)
    for name, digest in p["sources"].items():
        if sha256(ROOT/name) != digest:
            raise ValueError("Frozen source changed during run")
    snapshot = json.loads((output/"snapshot.json").read_text(encoding="utf-8"))
    if not all(sha256(Path(e["snapshot"])) == e["sha256"] for e in snapshot["files"]):
        raise ValueError("Frozen source, data or global artifact changed")
    actual_stress = [r for r in rows if r["dataset"] == "stress" and r["model"] == "global75_25" and r["scope"] == "ar_operating_schedule"]
    verification = dict(passed=True, plans=len(contexts), measured_weeks=len(rows),
        future_removal_checks=len(contexts), maximum_error_bridge_residual_vnd=max(abs(r["error_bridge_residual"]) for r in rows),
        new_invoice_forecasts=0, all_open_invoices_used=True, stress_shortfall_weeks=sum(r["shortfall"] for r in actual_stress),
        original_bank_unchanged=fingerprint(data) == p["full_data_sha256"], snapshot_hashes_checked=len(snapshot["files"]),
        elapsed_seconds=time.perf_counter()-started,
        result_hashes={name:sha256(output/name) for name in ("weekly.csv", "metrics.csv", "ar_metrics.csv", "per_origin_metrics.csv", "contexts.json", "REPORT.md")})
    if verification["stress_shortfall_weeks"] == 0:
        verification["shortfall_validation"] = "No events under locked design; recall remains unassessed. Do not tune the floor."
    write_json(output/"verification.json", verification)
    print(json.dumps(verification, ensure_ascii=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT/"pilot/demo_dai_phat")
    parser.add_argument("--global-run", type=Path, default=ROOT/"outputs/t1/aligned_cashcalendar_20261113")
    parser.add_argument("--output", type=Path, default=ROOT/"outputs/t6/global_scope_no_new_credit_20261113")
    parser.add_argument("--cutoffs", nargs="+", default=list(CUTOFFS))
    parser.add_argument("--frozen-runtime", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not args.frozen_runtime:
        capture(output, args.data_dir.resolve(), args.global_run.resolve())
        command = [sys.executable, "-X", "utf8", str(output/"runtime_source/scripts/business/backtest_t6_global.py"),
                   "--frozen-runtime", "--output", str(output), "--data-dir", str(output/"inputs"), "--cutoffs", *args.cutoffs]
        raise SystemExit(subprocess.run(command, check=False).returncode)
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        run(output, args.data_dir.resolve(), args.cutoffs)


if __name__ == "__main__":
    main()
