"""Continue the frozen global T1 on Dai Phat's past and compare with Workspace."""
import argparse
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from agent1.adaptive.compact_t1 import Ledger, load_research_t1_bundle, workspace_context
from agent1.adaptive.data import fingerprint
from agent1.adaptive.landmark_features import FEATURES, LandmarkHazard
from agent1.adaptive.ledger_bridge import ledger_context
from experiments.t1_compact.aligned_data import landmarks
from experiments.t1_compact.compare_adaptation import adapt, local_frames
from experiments.t1_compact.landmark_data import CASH_COLUMNS
from experiments.t1_compact.train_landmark import (
    context_for, score_prediction, summarize_prediction,
)
from experiments.t6_backtest.evaluation import ar_score, knowledge_snapshot, measure
from scripts.business.backtest_t6_baseline import (
    CUTOFFS, cash_equivalent, load_demo, sha256, write_csv, write_json,
)
from scripts.business.backtest_t6_global import capture, forecast_checked

VERSION = "dai-phat-global-local-adaptation-v1"
MODEL_NAMES = (
    "workspace", "global75_25", "global_finetuned",
    "global_adapted_audited", "global_reweighted",
)


def demo_ledger(data):
    """Adapter for the demo's original claims, linked cash and dated write-offs."""
    invoices = pd.DataFrame(data["invoices"]).copy()
    if invoices.invoice_id.duplicated().any() or data.get("record_history"):
        raise ValueError("This experiment requires original, unversioned demo claims")
    if invoices.get("replaces_invoice_id", pd.Series(dtype=str)).notna().any():
        raise ValueError("Replacement invoices need a separate label adapter")
    payments = pd.DataFrame(data["payments"]).rename(columns={"payment_date": "date"})
    writeoffs = {}
    for row in data.get("actions", []):
        if row["kind"] == "write_off":
            if row["date"] != row["known_at"]:
                raise ValueError("This demo adapter requires same-day write-off knowledge")
            identifier = row["invoice_id"]
            writeoffs[identifier] = min(writeoffs.get(identifier, row["date"]), row["date"])
    invoices["written_off_at"] = pd.to_datetime(invoices.invoice_id.map(writeoffs))
    return Ledger(invoices, payments)


def assert_feature_parity(ledger, data, frame):
    """Check the fast research adapter against the actual serving input builder."""
    columns = [
        "amount", "known_at", "settled", "settled_known_at", "received",
        "remaining_amount", "receipt_count", "received_28d", "last_receipt", "written_off_at",
    ]
    checked = 0
    for origin, part in frame.groupby("origin", sort=True):
        cutoff = str(origin.date())
        canonical = workspace_context(knowledge_snapshot(data, cutoff), cutoff)
        fast = ledger_context(ledger, cutoff)
        for column in ("known_at", "settled", "settled_known_at", "last_receipt", "written_off_at"):
            canonical[column] = canonical[column].astype("datetime64[ns]")
            fast[column] = fast[column].astype("datetime64[ns]")
        pd.testing.assert_frame_equal(
            canonical.set_index("invoice_id")[columns].sort_index(),
            fast.set_index("invoice_id")[columns].sort_index(),
            check_dtype=False, check_names=False,
        )
        from agent1.adaptive.landmark_features import prepare_features
        targets = canonical.set_index("invoice_id").loc[part.invoice_id].reset_index()
        expected = prepare_features(targets, canonical, origin)
        np.testing.assert_allclose(expected, part[list(FEATURES)], atol=1e-12, rtol=0)
        checked += len(part)
    return checked


def capture_experiment(output, data_dir, global_run, baseline):
    capture(output, data_dir, global_run)
    snapshot = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
    targets = [(p, output / "runtime_source" / p.relative_to(ROOT))
               for p in sorted((ROOT / "experiments/t1_compact").glob("*.py"))]
    targets.append((Path(__file__), output / "runtime_source/scripts/business" / Path(__file__).name))
    targets += [(global_run / name, output / "adaptation_inputs" / name)
                for name in ("protocol.json", "current_global_replay.npz")]
    baseline_names = ["protocol.json", "ar_metrics.csv", "verification.json", "independent_verification.json"]
    baseline_names += [f"models/{cutoff}/{name}" for cutoff in CUTOFFS
                       for name in ("bundle.pkl", "receipt.json")]
    targets += [(baseline / name, output / "workspace_reference" / name) for name in baseline_names]
    for source, destination in targets:
        content = source.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != content:
            raise ValueError("Captured input changed: " + str(destination))
        destination.write_bytes(content)
        snapshot["files"].append(dict(original=str(source.resolve()), snapshot=str(destination.resolve()),
                                      sha256=sha256(destination)))
    write_json(output / "snapshot.json", snapshot)


def lock_protocol(output, data):
    previous = json.loads((output / "workspace_reference/protocol.json").read_text(encoding="utf-8"))
    global_protocol = json.loads((output / "adaptation_inputs/protocol.json").read_text(encoding="utf-8"))
    for name, digest in previous["sources"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Workspace reference source changed: " + name)
    if fingerprint(data) != previous["full_data_sha256"]:
        raise ValueError("Dai Phat data differ from the Workspace reference")
    snapshot = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
    value = dict(
        version=VERSION, synthetic=True, independent_companies=1,
        cutoffs=list(CUTOFFS), horizon_weeks=13, models=list(MODEL_NAMES),
        adaptation=global_protocol["adaptation"],
        adaptation_protocol_sha256=sha256(output / "adaptation_inputs/protocol.json"),
        replay_sha256=sha256(output / "adaptation_inputs/current_global_replay.npz"),
        global_metadata_sha256=sha256(output / "global_release/serving_artifact/metadata.json"),
        workspace_protocol_sha256=sha256(output / "workspace_reference/protocol.json"),
        data_fingerprint=fingerprint(data), snapshot_sha256=sha256(output / "snapshot.json"),
        runtime_sources={str(Path(row["snapshot"]).relative_to(output / "runtime_source")): row["sha256"]
                         for row in snapshot["files"] if Path(row["snapshot"]).is_relative_to(output / "runtime_source")},
        simulation_paths=previous["simulation_paths"], simulation_seed=previous["simulation_seed"],
        shap_limit=0, cash_floor=previous["cash_floor"], truth_asof=previous["truth_asof"],
        new_invoice_forecasting=False,
        selection="same declared adaptation protocol; validation chooses epochs/pooling/mode; past audit accepts or returns to global",
        workspace="reuse hash-verified origin-trained bundles and reconstruct their AR scores",
        evaluation="all valid opening invoices; actual cash receipts and paid targets over 13 weeks; no operating inflows or expense schedules",
        history="four previously inspected origins; diagnostic comparison, not a fresh holdout",
        inference="independent company count is one; no confidence intervals treating invoices/origins as independent firms",
    )
    path = output / "protocol.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != value:
        raise ValueError("Experiment protocol changed")
    write_json(path, value)
    return value


def load_workspace(output, cutoff, past):
    folder = output / "workspace_reference/models" / cutoff
    receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
    if receipt["sha256"] != sha256(folder / "bundle.pkl"):
        raise ValueError("Workspace model checksum changed")
    if receipt["signature"]["data_hash"] != fingerprint(past):
        raise ValueError("Workspace training data differ")
    bundle = pickle.loads((folder / "bundle.pkl").read_bytes())
    if bundle["asof"] != cutoff or bundle["operating"].get("credit") is not None:
        raise ValueError("Workspace model date or cash scope mismatch")
    return bundle


def serving_bundle(workspace, model, cutoff, name):
    result = dict(workspace)
    result.update(model=model, anchor=model, weight=1., asof=cutoff,
                  selected_method=name, algorithm_version="dai-phat-landmark18-adapted-v1",
                  t1_provenance=dict(source=name, local_adaptation=True, local_asof=cutoff,
                                     synthetic=True, real_pilot_accepted=False))
    return result


def probabilities(bundle, frame, data, cutoff):
    history = workspace_context(knowledge_snapshot(data, cutoff), cutoff)
    targets = history.set_index("invoice_id").loc[frame.invoice_id].reset_index()
    targets.attrs["compact_context"] = history
    ages = (pd.Timestamp(cutoff) - targets.issue_date).dt.days.to_numpy()
    weight = bundle["weight"]
    result = (weight * bundle["model"].distribution(targets, ages)
              + (1 - weight) * bundle["anchor"].distribution(targets, ages))
    np.testing.assert_allclose(result.sum(1), 1., atol=1e-12, rtol=0)
    return result


def fit_origin(output, data, cutoff, config, global_bundle, replay):
    folder = output / "origins" / cutoff
    receipt_path = folder / "receipt.json"
    if receipt_path.exists():
        record = json.loads(receipt_path.read_text(encoding="utf-8"))
        for name, digest in record["files"].items():
            if sha256(folder / name) != digest:
                raise ValueError("Origin checkpoint changed")
        if record["protocol_sha256"] != sha256(output / "protocol.json"):
            raise ValueError("Origin checkpoint protocol mismatch")
        return pickle.loads((folder / "models.pkl").read_bytes()), record
    started = time.perf_counter()
    past = knowledge_snapshot(data, cutoff)
    ledger = demo_ledger(past)
    origin = pd.Timestamp(cutoff)
    frame = local_frames(ledger, past, origin, "dai_phat", "DP", output, config)
    # Independently rebuild from the complete input to expose future-data leakage.
    full_frame = local_frames(demo_ledger(data), data, origin, "dai_phat", "DP", output / "future_removal_check", config)
    pd.testing.assert_frame_equal(frame, full_frame)
    parity_rows = assert_feature_parity(ledger, past, frame)
    reference = next(member for member in global_bundle["model"].members
                     if isinstance(member, LandmarkHazard) and member.name.startswith("neural"))
    print(cutoff + ": fitting the declared local adaptation", flush=True)
    adapted, record = adapt(global_bundle["model"], reference, replay, frame, config)
    models = {name: adapted[name] for name in MODEL_NAMES if name.startswith("global_")}
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(folder / "training_landmarks.parquet", index=False)
    (folder / "models.pkl").write_bytes(pickle.dumps(models, protocol=pickle.HIGHEST_PROTOCOL))
    record.update(cutoff=cutoff, protocol_sha256=sha256(output / "protocol.json"),
                  past_data_fingerprint=fingerprint(past), serving_feature_parity_rows=parity_rows,
                  future_removal_training_check=True, seconds=time.perf_counter() - started,
                  files={name: sha256(folder / name) for name in ("training_landmarks.parquet", "models.pkl")})
    write_json(receipt_path, record)
    print(json.dumps(dict(cutoff=cutoff, status=record["status"], epochs=record.get("continuation_epochs"),
                         alpha=record.get("continuation_weight"), mode=record.get("selected_validation_mode"),
                         audit_passed=record["audit_passed"], seconds=record["seconds"])), flush=True)
    return models, record


def aggregate(output, weekly, contexts):
    metrics = []
    for name in MODEL_NAMES:
        rows = [row for row in weekly if row["model"] == name]
        cases = [row for row in contexts if row["model"] == name]
        for horizon, selected in (
            ("w1-13", rows), ("w1-4", [row for row in rows if row["week"] <= 4]),
            ("w5-13", [row for row in rows if row["week"] >= 5]),
        ):
            metrics.append(dict(model=name, horizon=horizon, **ar_score(selected),
                                cash_score=float(np.mean([row["t1_metrics"]["score"] for row in cases])),
                                brier4=float(np.mean([row["t1_metrics"]["brier4"] for row in cases])),
                                brier13=float(np.mean([row["t1_metrics"]["brier13"] for row in cases])),
                                integrated_brier13=float(np.mean([row["t1_metrics"]["integrated_brier13"] for row in cases]))))
    write_csv(output / "metrics.csv", metrics)
    write_csv(output / "weekly.csv", weekly)
    write_csv(output / "per_origin_metrics.csv", [dict(cutoff=row["cutoff"], model=row["model"],
                                                       **row["t1_metrics"], **row["ar_metrics"])
                                                   for row in contexts])
    return metrics


def write_report(output, metrics, receipts):
    primary = {row["model"]: row for row in metrics if row["horizon"] == "w1-13"}
    lines = [
        "# Fine-tune global trên Đại Phát và đối chiếu Workspace — 13/11/2026", "",
        "So sánh trên cùng toàn bộ công nợ mở tại 30/09/2025, 31/12/2025, 30/04/2026 và 31/07/2026, mỗi kỳ 13 tuần. Dữ liệu thuộc một doanh nghiệp mô phỏng. Bốn origin đã được xem trong các lượt trước, nên đây là phép chẩn đoán hồi cứu.", "",
        "Dùng lại model Workspace đã train ở từng origin sau kiểm hash và dữ liệu đầu vào. Global 75/25, replay và cấu hình thích nghi được khóa trước lần chấm này. Fine-tune thử 5/20 epoch, learning rate 0,0001, trọng số học local/replay 70/30 và pooling 0/25/50/75/100%. Validation quá khứ chọn cấu hình, audit quá khứ chấp nhận hoặc quay về global. Fine-tune thuần và nhánh thích nghi qua audit được chấm riêng.", "",
        "Các số tiền dưới đây có đơn vị triệu VND. Cash score và Brier càng thấp càng tốt. Coverage là độ phủ từng tuần của dải thu AR lũy kế P10–P90, mức danh nghĩa 80%.", "",
        "| Model | Cash score | MAE thu tuần | MAE thu lũy kế | Brier 4 tuần | Brier 13 tuần | Coverage | Độ rộng dải |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in MODEL_NAMES:
        row = primary[name]
        lines.append(f"| {name} | {row['cash_score']:.6f} | {row['mae_weekly_ar_vnd']/1e6:.2f} | {row['mae_cumulative_ar_vnd']/1e6:.2f} | {row['brier4']:.6f} | {row['brier13']:.6f} | {row['coverage80']:.1%} | {row['mean_width80_vnd']/1e6:.2f} |")
    lines += ["", "| Ngày chốt | Fit/validation/audit snapshots | Epoch | Alpha | Phương án validation chọn | Audit chấp nhận |",
              "|---|---|---:|---:|---|---|"]
    for receipt in receipts:
        counts = receipt["rows"]
        lines.append(f"| {receipt['cutoff']} | {counts.get('fit',0)}/{counts.get('validation',0)}/{counts.get('audit',0)} | {receipt.get('continuation_epochs')} | {receipt.get('continuation_weight')} | {receipt.get('selected_validation_mode')} | {receipt['audit_passed']} |")
    lines += ["", "Snapshots có thể lặp cùng hóa đơn ở các ngày khác nhau. Số doanh nghiệp độc lập bằng 1. Các cửa sổ được dựng bằng dữ liệu đã biết tại origin, nhãn đủ 91 ngày theo dõi. Toàn bộ công nợ mở hợp lệ được chấm và đưa vào forecast, trong khi mẫu học giữ giới hạn 50 snapshots mỗi origin theo protocol đã có.", "",
              "Nhánh global_finetuned là fine-tune + pooling do validation chọn. global_adapted_audited là phương án fine-tune hoặc đổi trọng số đã được audit, có thể trả về global gốc. global_reweighted chỉ đổi trọng số thành viên theo validation. Trạng thái model thực tế tại mỗi origin nằm trong receipt, cùng toàn bộ điểm validation/audit.", "",
              "Đánh giá chính dùng tiền thu từ danh mục mở. Nhánh dự báo hóa đơn mới được tắt. Dải tiền được tính bằng T6 1.000 đường/seed 7 với cùng phạm vi AR; các số dư ngân hàng đầy đủ và cảnh báo thiếu tiền thuộc backtest T6 riêng.", "",
              "## Bằng chứng", "",
              "`protocol.json` và `snapshot.json` lưu cấu hình và hash. `origins/` lưu mẫu học, model, dự báo từng hóa đơn, kế hoạch và receipt. `metrics.csv`, `per_origin_metrics.csv`, `weekly.csv` lưu số đo. `verification.json` ghi kiểm tra tính lại và tái tạo dự báo. Không có cấu hình tenant được kích hoạt trong lần đo này.", "",
              "```powershell", ".\\.venv\\Scripts\\python.exe -X utf8 agent1/scripts/business/backtest_t1_dai_phat_adaptation.py", "```", ""]
    (output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def verify(output, data, protocol, contexts, weekly):
    """Recompute scores from saved distributions and raw allocated receipts."""
    baseline = pd.read_csv(output / "workspace_reference/ar_metrics.csv")
    metrics = pd.read_csv(output / "metrics.csv")
    for name in ("workspace", "global75_25"):
        reference = baseline[(baseline.dataset == "original") & (baseline.model == name)]
        current = metrics[metrics.model == name]
        for horizon in current.horizon:
            old = reference[reference.horizon == horizon].iloc[0]
            new = current[current.horizon == horizon].iloc[0]
            for column in ("mae_weekly_ar_vnd", "mae_cumulative_ar_vnd", "coverage80", "mean_width80_vnd"):
                np.testing.assert_allclose(new[column], old[column], atol=.01, rtol=1e-12)
    reconstructed = 0
    reconstructed_distributions = 0
    numeric_difference = 0.
    for cutoff in CUTOFFS:
        folder = output / "origins" / cutoff
        frame = pd.read_parquet(folder / "evaluation_landmarks.parquet")
        models = pickle.loads((folder / "models.pkl").read_bytes())
        workspace = load_workspace(output, cutoff, knowledge_snapshot(data, cutoff))
        global_bundle = load_research_t1_bundle(output / "global_release", cutoff, workspace)
        bundles = dict(workspace=workspace, global75_25=global_bundle)
        bundles.update({name: serving_bundle(workspace, model, cutoff, name) for name, model in models.items()})
        with np.load(folder / "probabilities.npz", allow_pickle=False) as saved:
            for name, bundle in bundles.items():
                predicted = probabilities(bundle, frame, data, cutoff)
                np.testing.assert_allclose(predicted, saved[name], atol=1e-12, rtol=0)
                reconstructed_distributions += 1
                cumulative_paid = np.cumsum(saved[name][:, :13], axis=1)
                paid = frame.paid_days.to_numpy()[:, None] <= np.arange(1, 14) * 7
                brier = ((cumulative_paid - paid) ** 2).mean(axis=0)
                entry = next(row for row in contexts if row["cutoff"] == cutoff and row["model"] == name)
                amount_weights = frame.amount_open.to_numpy(float) / frame.amount_open.sum()
                integrated_brier = amount_weights @ ((cumulative_paid - paid) ** 2).mean(axis=1)
                for actual, key in ((brier[3], "brier4"), (brier[12], "brier13"), (integrated_brier, "integrated_brier13")):
                    np.testing.assert_allclose(actual, entry["t1_metrics"][key], atol=1e-12, rtol=0)
                if name == "global_finetuned":
                    plan, _ = forecast_checked(data, cutoff, bundle, "ar_only", (), protocol)
                    saved_plan = json.loads((folder / f"plan_{name}.json").read_text(encoding="utf-8"))
                    if not cash_equivalent(plan, saved_plan):
                        raise ValueError("Plan reconstruction failed")
                    reconstructed += 1
                rows = [row for row in weekly if row["cutoff"] == cutoff and row["model"] == name]
                incoming = np.array([row["predicted_ar_in"] for row in rows])
                actual_cash = frame[list(CASH_COLUMNS)].to_numpy() * frame.amount_open.to_numpy()[:, None]
                actual = actual_cash.sum(axis=0)
                raw_actual = np.zeros(13)
                opened = set(frame.invoice_id)
                for payment in data["payments"]:
                    day = (pd.Timestamp(payment["payment_date"]) - pd.Timestamp(cutoff)).days
                    if payment["invoice_id"] in opened and 1 <= day <= 91 and payment["known_at"] <= protocol["truth_asof"]:
                        raw_actual[(day-1)//7] += payment["amount"]
                np.testing.assert_allclose(actual, raw_actual, atol=.01, rtol=0)
                np.testing.assert_allclose(actual, [row["actual_ar_in"] for row in rows], atol=.01, rtol=0)
                error = incoming - actual
                amount = frame.amount_open.sum()
                score = .5 * (abs(error).sum() + abs(error.cumsum()).mean()) / amount
                np.testing.assert_allclose(score, entry["t1_metrics"]["score"], atol=1e-12, rtol=0)
                numeric_difference = max(numeric_difference, abs(float(score) - entry["t1_metrics"]["score"]))
    snapshot = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
    for entry in snapshot["files"]:
        if sha256(Path(entry["snapshot"])) != entry["sha256"]:
            raise ValueError("Captured source or input changed")
    return dict(passed=True, reconstructed_plans=reconstructed,
                reconstructed_distributions=reconstructed_distributions,
                original_workspace_global_scores_reproduced=True,
                raw_receipt_truth_checks=len(weekly), independently_recomputed_cash_and_brier=True,
                maximum_cash_score_difference=numeric_difference,
                snapshot_hashes_checked=len(snapshot["files"]),
                future_removal_plan_checks=len(contexts), future_removal_training_checks=len(CUTOFFS),
                new_invoice_forecasting=False, independent_companies=1)


def run(output):
    started = time.perf_counter()
    data, _ = load_demo(output / "inputs")
    protocol = lock_protocol(output, data)
    with np.load(output / "adaptation_inputs/current_global_replay.npz", allow_pickle=False) as saved:
        replay = tuple(saved[key] for key in ("x", "y", "weights"))
    ledger = demo_ledger(data)
    weekly, contexts, receipts = [], [], []
    for cutoff in CUTOFFS:
        past = knowledge_snapshot(data, cutoff)
        workspace = load_workspace(output, cutoff, past)
        global_bundle = load_research_t1_bundle(output / "global_release", cutoff, workspace)
        models, receipt = fit_origin(output, data, cutoff, protocol["adaptation"], global_bundle, replay)
        receipts.append(receipt)
        folder = output / "origins" / cutoff
        frame = landmarks(ledger, data, pd.Timestamp(cutoff), protocol["truth_asof"],
                          "dai_phat", "DP", "evaluation", cap=100000)
        assert_feature_parity(ledger, data, frame)
        frame.to_parquet(folder / "evaluation_landmarks.parquet", index=False)
        bundles = dict(workspace=workspace, global75_25=global_bundle)
        bundles.update({name: serving_bundle(workspace, model, cutoff, name) for name, model in models.items()})
        distributions = {}
        for name in MODEL_NAMES:
            bundle = bundles[name]
            prediction = probabilities(bundle, frame, data, cutoff)
            distributions[name] = prediction
            context = context_for(frame)
            summary = summarize_prediction(prediction, context)
            t1_metrics = score_prediction(summary, context)
            plan, accounts = forecast_checked(data, cutoff, bundle, "ar_only", (), protocol)
            ids = set(row["invoice_id"] for row in plan["cash_decomposition"]["invoices"])
            if ids != set(frame.invoice_id):
                raise ValueError("Paid-score cohort differs from the forecast opening book")
            expected = summary["cash"][0] * frame.amount_open.sum()
            np.testing.assert_allclose(expected, [row["ar_in"] for row in plan["cash_decomposition"]["weeks"]], atol=.01, rtol=1e-12)
            rows = measure(data, plan, protocol["truth_asof"], accounts)
            for row in rows:
                row["model"] = name
            weekly.extend(rows)
            write_json(folder / f"plan_{name}.json", plan)
            contexts.append(dict(cutoff=cutoff, model=name, open_invoices=len(ids),
                                 t1_metrics=t1_metrics, ar_metrics=ar_score(rows)))
        np.savez_compressed(folder / "probabilities.npz", **distributions)
        print(cutoff + ": all model forecasts scored", flush=True)
    metrics = aggregate(output, weekly, contexts)
    write_json(output / "contexts.json", contexts)
    write_report(output, metrics, receipts)
    result = verify(output, data, protocol, contexts, weekly)
    result["elapsed_seconds"] = time.perf_counter() - started
    result["result_hashes"] = {name: sha256(output / name) for name in (
        "metrics.csv", "weekly.csv", "per_origin_metrics.csv", "contexts.json", "REPORT.md")}
    write_json(output / "verification.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/t1/dai_phat_adaptation_20261113")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "pilot/demo_dai_phat")
    parser.add_argument("--global-run", type=Path, default=ROOT / "outputs/t1/aligned_cashcalendar_20261113")
    parser.add_argument("--baseline-run", type=Path, default=ROOT / "outputs/t6/global_scope_no_new_credit_20261113")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--frozen-runtime", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.verify_only:
        started = time.perf_counter()
        data, _ = load_demo(output / "inputs")
        protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
        contexts = json.loads((output / "contexts.json").read_text(encoding="utf-8"))
        weekly = pd.read_csv(output / "weekly.csv").to_dict("records")
        with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
            result = verify(output, data, protocol, contexts, weekly)
        result.update(verification_seconds=time.perf_counter() - started,
                      verification_runner_sha256=sha256(Path(__file__)),
                      result_hashes={name: sha256(output / name) for name in (
                          "metrics.csv", "weekly.csv", "per_origin_metrics.csv", "contexts.json", "REPORT.md")})
        write_json(output / "verification.json", result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    if not args.frozen_runtime:
        capture_experiment(output, args.data_dir.resolve(), args.global_run.resolve(), args.baseline_run.resolve())
        command = [sys.executable, "-X", "utf8", str(output / "runtime_source/scripts/business" / Path(__file__).name),
                   "--output", str(output), "--frozen-runtime"]
        raise SystemExit(subprocess.run(command, check=False).returncode)
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        run(output)


if __name__ == "__main__":
    main()
