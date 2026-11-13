"""Eighteen-feature T1 comparison with cash validation and a common survival baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import warnings
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.compact_t1 import CompactT1, sha256
from agent1.adaptive.landmark_features import (
    FEATURES,
    GROUPS,
    SCHEMA,
    LandmarkEnsemble,
    LandmarkHazard,
    LandmarkRule,
)
from experiments.t1_compact.landmark_data import (
    CASH_COLUMNS,
    OVERRIDE_COLUMNS,
    prepare_role,
)
from experiments.t1_compact.train import PROTOCOL as DATA_PROTOCOL
from experiments.t1_compact.train import risk_rows, write_json
from experiments.t1_compact.train_ensemble import (
    BASELINES,
    SEED,
    benchmark_ensemble,
    candidate_specs,
    empirical_hazards,
    estimator_for,
    estimator_parameters,
    latency_contexts,
    row_weights,
    stable_improvement,
    weight_grid,
)

SOURCE_FILES = (
    "agent1/adaptive/compact_t1.py",
    "agent1/adaptive/compact_ensemble.py",
    "agent1/adaptive/landmark_features.py",
    "agent1/adaptive/landmark_explanations.py",
    "agent1/adaptive/explanation_reference.py",
    "agent1/adaptive/explanations.py",
    "agent1/adaptive/methods.py",
    "agent1/adaptive/cash_history.py",
    "agent1/adaptive/data.py",
    "agent1_service/ingest/invoices.py",
    "agent1_service/ingest/money.py",
    "experiments/t1_compact/train.py",
    "experiments/t1_compact/train_ensemble.py",
    "experiments/t1_compact/landmark_data.py",
    "experiments/t1_compact/train_landmark.py",
)


def context_for(frame):
    keys = pd.MultiIndex.from_frame(frame[["world", "firm", "origin"]])
    codes, unique = pd.factorize(keys, sort=True)
    groups = unique.set_names(keys.names).to_frame(index=False)
    groups["invoice_id"] = np.arange(len(groups))
    amounts = frame.amount_open.to_numpy(float)
    group_amount = np.bincount(codes, weights=amounts)
    truth_cash = np.zeros((len(groups), 13))
    np.add.at(
        truth_cash, codes, frame[list(CASH_COLUMNS)].to_numpy(float) * amounts[:, None]
    )
    group_weights = row_weights(groups)
    amount_weights = group_weights[codes] * amounts / group_amount[codes]
    windows = {}
    for origin in sorted(groups.origin.unique()):
        take = (groups.origin == origin).to_numpy()
        weights = np.zeros(len(groups))
        weights[take] = row_weights(groups[take])
        windows[str(pd.Timestamp(origin).date())] = weights
    return {
        "codes": codes,
        "groups": groups,
        "amounts": amounts,
        "group_amount": group_amount,
        "group_weights": group_weights,
        "windows": windows,
        "row_weights": row_weights(frame),
        "amount_weights": amount_weights,
        "truth_cash": truth_cash / group_amount[:, None],
        "truth_cdf": frame.paid_days.to_numpy(float)[:, None] <= 7 * np.arange(1, 14),
        "override": frame[list(OVERRIDE_COLUMNS)].to_numpy(float),
        "override_support": frame.partial_override.to_numpy(bool),
    }


def summarize_prediction(distribution, context):
    distribution = np.asarray(distribution, float)
    if (
        distribution.shape != (len(context["codes"]), 14)
        or not np.isfinite(distribution).all()
        or (distribution < 0).any()
    ):
        raise ValueError("Invalid landmark payment distribution")
    np.testing.assert_allclose(distribution.sum(1), 1.0, atol=1e-12, rtol=0)
    cash = distribution.copy()
    support = context["override_support"]
    cash[support] = context["override"][support]
    totals = np.zeros_like(context["truth_cash"])
    np.add.at(totals, context["codes"], cash[:, :13] * context["amounts"][:, None])
    return {
        "cdf": np.cumsum(distribution[:, :13], axis=1),
        "cash": totals / context["group_amount"][:, None],
    }


def score_prediction(prediction, context):
    error = prediction["cash"] - context["truth_cash"]
    absolute_weekly = abs(error)
    absolute_cumulative = abs(np.cumsum(error, axis=1))
    # Normalize to the outstanding claim at each World/firm/origin. Summing
    # weekly errors puts weekly timing and mean cumulative error on comparable
    # claim-fraction scales. The two components have equal declared weight.
    loss = 0.5 * (absolute_weekly.sum(1) + absolute_cumulative.mean(1))
    weights = context["group_weights"]
    brier = (prediction["cdf"] - context["truth_cdf"]) ** 2
    return {
        "score": float(weights @ loss),
        "windows": {
            key: float(window @ loss) for key, window in context["windows"].items()
        },
        "cash_weekly_mae_vnd": float(
            weights @ (absolute_weekly.mean(1) * context["group_amount"])
        ),
        "cash_cumulative_mae_vnd": float(
            weights @ (absolute_cumulative.mean(1) * context["group_amount"])
        ),
        "cash_bias13_fraction": float(weights @ error.sum(1)),
        "brier4": float(context["row_weights"] @ brier[:, 3]),
        "brier13": float(context["row_weights"] @ brier[:, 12]),
        "integrated_brier13": float(context["amount_weights"] @ brier.mean(1)),
    }


def pool_predictions(predictions, members, weights):
    return {
        "cdf": sum(
            weight * predictions[name]["cdf"] for name, weight in zip(members, weights)
        ),
        "cash": sum(
            weight * predictions[name]["cash"] for name, weight in zip(members, weights)
        ),
    }


def fit_candidates(train, validation, output, protocol):
    x, y, weights = risk_rows(train, tuple(range(len(FEATURES))), FEATURES)
    total = len(y)
    indices = np.sort(
        np.random.default_rng(SEED).choice(total, min(total, 100000), replace=False)
    )
    x, y, weights = x[indices], y[indices], weights[indices]
    weights *= len(weights) / weights.sum()
    sample_hash = hashlib.sha256(
        indices.tobytes() + x.tobytes() + y.tobytes() + weights.tobytes()
    ).hexdigest()
    write_json(
        output / "training_sample.json",
        {
            "total_risk_rows": total,
            "fitted_risk_rows": len(y),
            "events": int(y.sum()),
            "sample_sha256": sample_hash,
        },
    )
    empirical = empirical_hazards(x, y, weights)
    context = context_for(validation)
    features = validation[list(FEATURES)].to_numpy(float)
    models, predictions, records = {}, {}, []
    for spec in protocol["candidates"]:
        name = spec["name"]
        if not spec["eligible"]:
            records.append(dict(**spec, status="unavailable"))
            continue
        completed = []
        for trial in range(spec["trials"]):
            directory = output / "trials" / f"{name}_{trial}"
            directory.mkdir(parents=True, exist_ok=True)
            receipt = directory / "trial.json"
            if receipt.exists():
                record = json.loads(receipt.read_text(encoding="utf-8"))
                if record["sample_sha256"] != sample_hash or record[
                    "protocol_sha256"
                ] != sha256(output / "protocol.json"):
                    raise ValueError("Trial input hashes changed")
                if (
                    sha256(directory / "validation.npz") != record["prediction_sha256"]
                    or sha256(directory / "model/metadata.json")
                    != record["model_metadata_sha256"]
                ):
                    raise ValueError("Trial artifact changed")
                model = CompactT1.load(directory / "model")
                with np.load(
                    directory / "validation.npz", allow_pickle=False
                ) as cached:
                    distribution = cached["distribution"]
            else:
                started = time.perf_counter()
                parameters, messages = {}, []
                if name in BASELINES:
                    model = LandmarkRule(name, empirical)
                else:
                    estimator = estimator_for(name, trial, len(FEATURES))
                    if name.startswith("neural"):
                        estimator.steps[-1][1].set_params(max_iter=protocol.get("neural_max_iter", [120, 180])[trial])
                    options = (
                        {f"{estimator.steps[-1][0]}__sample_weight": weights}
                        if isinstance(estimator, Pipeline)
                        else {"sample_weight": weights}
                    )
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        estimator.fit(x, y, **options)
                    messages = sorted({str(item.message) for item in caught})
                    parameters = estimator_parameters(estimator)
                    model = LandmarkHazard(estimator, name)
                distribution = model.distribution_from_features(features)
                measured = score_prediction(
                    summarize_prediction(distribution, context), context
                )
                model.save(
                    directory / "model",
                    {"candidate": name, "trial": trial, "sample_sha256": sample_hash},
                )
                np.savez_compressed(
                    directory / "validation.npz", distribution=distribution
                )
                record = dict(
                    name=name,
                    trial=trial,
                    **measured,
                    seconds=time.perf_counter() - started,
                    parameters=parameters,
                    warnings=messages,
                    sample_sha256=sample_hash,
                    protocol_sha256=sha256(output / "protocol.json"),
                    prediction_sha256=sha256(directory / "validation.npz"),
                    model_metadata_sha256=sha256(directory / "model/metadata.json"),
                )
                write_json(receipt, record)
                print(
                    json.dumps(
                        {
                            "event": "fit",
                            "name": name,
                            "trial": trial,
                            "score": record["score"],
                            "brier13": record["brier13"],
                            "seconds": record["seconds"],
                            "warnings": messages,
                        }
                    ),
                    flush=True,
                )
            completed.append((record, model, distribution))
        eligible_completed = [item for item in completed if not (
            protocol.get("require_neural_convergence", False) and name.startswith("neural")
            and any("Maximum iterations" in message for message in item[0].get("warnings", []))
        )]
        if not eligible_completed:
            records.append(dict(**spec, status="excluded_nonconverged"))
            continue
        best, model, distribution = min(
            eligible_completed, key=lambda item: (item[0]["score"], item[0]["trial"])
        )
        models[name] = model
        predictions[name] = summarize_prediction(distribution, context)
        destination = output / "validation_predictions" / f"{name}.npz"
        destination.parent.mkdir(exist_ok=True)
        np.savez_compressed(destination, distribution=distribution)
        records.append(
            dict(
                **spec,
                status="trained",
                selected_trial=best["trial"],
                score=best["score"],
                brier4=best["brier4"],
                brier13=best["brier13"],
                integrated_brier13=best["integrated_brier13"],
                windows=best["windows"],
                prediction_sha256=sha256(destination),
            )
        )
    write_json(output / "candidate_results.json", records)
    return models, predictions, context


def select(models, predictions, context, contexts, output, protocol):
    singles = [
        dict(members=[name], weights=[1.0], **score_prediction(prediction, context))
        for name, prediction in predictions.items()
    ]
    singles.sort(key=lambda item: (item["score"], item["members"]))
    timing, searches, steps = [], [], []
    for candidate in singles:
        model = LandmarkEnsemble(
            [models[name] for name in candidate["members"]], candidate["weights"]
        )
        latency = benchmark_ensemble(model, contexts)
        timing.append(
            dict(members=candidate["members"], weights=candidate["weights"], **latency)
        )
        print(
            json.dumps(
                {
                    "event": "shap_gate",
                    "members": candidate["members"],
                    "p95": latency["p95_seconds"],
                    "passed": latency["passed"],
                }
            ),
            flush=True,
        )
        if latency["passed"]:
            current = dict(candidate, latency=latency)
            steps.append(current)
            break
    else:
        write_json(output / "latency_trials.json", timing)
        raise ValueError("No candidate meets the representative-background SHAP budget")
    while len(current["members"]) < 3:
        trials = []
        for name in sorted(set(predictions) - set(current["members"])):
            members = current["members"] + [name]
            for weights in weight_grid(len(members)):
                measured = score_prediction(
                    pool_predictions(predictions, members, weights), context
                )
                stable = stable_improvement(current, measured, protocol["stability"])
                guard = (
                    measured["integrated_brier13"]
                    <= current["integrated_brier13"] * 1.02 + 0.0001
                )
                trials.append(
                    dict(
                        members=members,
                        weights=list(weights),
                        **measured,
                        stable=stable,
                        brier_guard=bool(guard),
                    )
                )
        trials.sort(key=lambda item: (item["score"], item["members"], item["weights"]))
        searches.extend(trials)
        accepted = None
        failed = set()
        for trial in trials:
            member_set = tuple(trial["members"])
            if not trial["stable"] or not trial["brier_guard"] or member_set in failed:
                continue
            model = LandmarkEnsemble(
                [models[name] for name in trial["members"]], trial["weights"]
            )
            latency = benchmark_ensemble(model, contexts)
            timing.append(
                dict(members=trial["members"], weights=trial["weights"], **latency)
            )
            print(
                json.dumps(
                    {
                        "event": "shap_gate",
                        "members": trial["members"],
                        "weights": trial["weights"],
                        "p95": latency["p95_seconds"],
                        "passed": latency["passed"],
                    }
                ),
                flush=True,
            )
            if latency["passed"]:
                accepted = dict(trial, latency=latency)
                break
            failed.add(member_set)
        if accepted is None:
            break
        current = accepted
        steps.append(current)
    selection = {
        "selected": current,
        "steps": steps,
        "ranked_singles": singles,
        "combination_count": len(searches),
        "survival_is_optional_member": True,
    }
    write_json(output / "ensemble_search.json", searches)
    write_json(output / "latency_trials.json", timing)
    write_json(output / "selection.json", selection)
    return LandmarkEnsemble(
        [models[name] for name in current["members"]], current["weights"]
    ), selection


def evaluate(model, frame, context):
    columns = list(model.feature_names)
    distribution = model.distribution_from_features(frame[columns].to_numpy(float))
    return score_prediction(
        summarize_prediction(distribution, context), context
    ), distribution


def protocol_for(source, previous, inputs):
    if (
        json.loads((source / "protocol.json").read_text(encoding="utf-8"))
        != DATA_PROTOCOL
    ):
        raise ValueError(
            "Source data protocol differs from the declared World/time split"
        )
    audit = json.loads((source / "data_audit.json").read_text(encoding="utf-8"))
    roles = {entry["world"]: entry["role"] for entry in audit}
    if (
        len(roles) != 14
        or sum(role == "train" for role in roles.values()) != 8
        or sum(role == "validation" for role in roles.values()) != 3
        or sum(role == "test" for role in roles.values()) != 3
    ):
        raise ValueError("Incomplete World split")
    return {
        "version": "landmark-18-cash-survival-v2",
        "dependencies": {
            name: version(name)
            for name in ("numpy", "pandas", "scikit-learn", "lightgbm", "xgboost")
        },
        "seed": SEED,
        "source": str(source),
        "previous": str(previous),
        "feature_schema": SCHEMA,
        "features": list(FEATURES),
        "groups": [
            {
                "key": key,
                "label": label,
                "features": [FEATURES[column] for column in columns],
            }
            for key, label, columns in GROUPS
        ],
        "feature_definition": {
            "history_days": 180,
            "receipt_window_days": 28,
            "history_trend": "OLS delay-days per 30 calendar days; customer estimates shrink toward company",
            "count_transform": "log1p",
            "overdue_thresholds_days": [30, 90],
            "customer_exposure": "customer open balance divided by company open balance",
        },
        "candidates": candidate_specs(),
        "budget": {
            "risk_rows": 100000,
            "learned_trials": 2,
            "baseline_trials": 1,
            "threads": 2,
            "blas_threads": 1,
            "neural_max_iter": [120, 180],
        },
        "source_audit_sha256": sha256(source / "data_audit.json"),
        "source_protocol_sha256": sha256(source / "protocol.json"),
        "previous_artifact_metadata_sha256": sha256(
            previous / "artifact/metadata.json"
        ),
        "validation_origins": DATA_PROTOCOL["validation_origins"],
        "available_asof": DATA_PROTOCOL["available_asof"],
        "selection_score": "0.5 * (sum absolute weekly cash error / outstanding + mean absolute cumulative cash error / outstanding); equal World/firm/origin",
        "selection_cash": "same observed partial-payment override as T6; actual receipts capped at the origin claim; shared source landmarks",
        "payment_diagnostics": "Brier4, Brier13, amount-weighted integrated Brier over all 13 weeks",
        "stability": {
            "minimum_mean_gain": 0.0001,
            "minimum_window_gain": 0.00001,
            "minimum_window_fraction": 0.75,
            "maximum_window_regression": 0.001,
        },
        "ensemble_guard": "amount-weighted integrated Brier may rise at most 2% plus 0.0001 per addition",
        "survival_contract": "same open landmarks, as-of receipts and cash-full-settlement labels; noncash writeoff never creates a Paid label; every mature unpaid landmark remains exposed through 13 weeks",
        "maximum_members": 3,
        "weight_step": 0.05,
        "calibration": {"method": "identity"},
        "shap": {
            "groups": 6,
            "coalitions": 64,
            "census_limit": 512,
            "stratified_primary": 128,
            "sensitivity_samples": 3,
            "single_invoice_p95_seconds": 1.0,
            "model_and_context_ready": True,
            "feature_preparation_included": True,
        },
        "latency_inputs": str(inputs) if inputs else None,
        "latency_input_hashes": {}
        if inputs is None
        else {
            name: sha256(inputs / name)
            for name in ("01_invoices.csv", "03_payments.csv", "06_actions.csv")
        },
        "source_hashes": {name: sha256(ROOT / name) for name in SOURCE_FILES},
        "limitations": [
            "Reused simulator-family Worlds and reused test holdout.",
            "Sampled eligible fixed-claim landmarks. Cash labels cap receipts at outstanding claims.",
            "This run changes features, the validation objective and the neural iteration budget together.",
            "Company adaptation and real-company holdout evaluation require a separate dated local validation.",
        ],
    }


def run(source, output, previous, inputs=None, selection_only=False):
    source, output, previous = source.resolve(), output.resolve(), previous.resolve()
    inputs = inputs.resolve() if inputs else None
    output.mkdir(parents=True, exist_ok=True)
    protocol = protocol_for(source, previous, inputs)
    path = output / "protocol.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != protocol:
        raise ValueError("Run inputs changed")
    write_json(path, protocol)
    for name in SOURCE_FILES:
        target = output / "runtime_source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    if (output / "test_results.json").exists():
        print(
            json.dumps({"event": "already_complete", "output": str(output)}), flush=True
        )
        return
    frozen_path = output / "frozen.json"
    if frozen_path.exists():
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        if frozen["artifact_metadata_sha256"] != sha256(
            output / "artifact/metadata.json"
        ) or frozen["selection_sha256"] != sha256(output / "selection.json"):
            raise ValueError("Frozen selection changed")
        selection = json.loads((output / "selection.json").read_text(encoding="utf-8"))
    else:
        train = prepare_role(source, output, "train")
        validation = prepare_role(source, output, "validation")
        if (
            set(train.world) & set(validation.world)
            or train.origin.max() + pd.Timedelta(days=91) >= validation.origin.min()
        ):
            raise ValueError("World/time leakage")
        if set(validation.origin.dt.strftime("%Y-%m-%d")) != set(
            protocol["validation_origins"]
        ):
            raise ValueError("Unexpected validation windows")
        validation.to_parquet(output / "validation_rows.parquet", index=False)
        models, predictions, context = fit_candidates(
            train, validation, output, protocol
        )
        contexts = latency_contexts(source, validation, inputs)
        model, selection = select(
            models, predictions, context, contexts, output, protocol
        )
        model.save(
            output / "artifact",
            {
                "available_asof": protocol["available_asof"],
                "synthetic": True,
                "activation": "candidate_only",
                "data_fingerprint": protocol["source_audit_sha256"],
                "source_sha256": protocol["source_hashes"][
                    "agent1/adaptive/landmark_features.py"
                ],
                "protocol_sha256": sha256(path),
                "validation": selection["selected"],
            },
        )
        best_single = selection["ranked_singles"][0]["members"][0]
        models[best_single].save(
            output / "single_reference", {"candidate": best_single}
        )
        models["survival"].save(
            output / "survival_reference", {"candidate": "survival"}
        )
        frozen = {
            "features": list(FEATURES),
            "members": selection["selected"]["members"],
            "weights": selection["selected"]["weights"],
            "protocol_sha256": sha256(path),
            "selection_sha256": sha256(output / "selection.json"),
            "artifact_metadata_sha256": sha256(output / "artifact/metadata.json"),
            "validation_rows_sha256": sha256(output / "validation_rows.parquet"),
            "single_metadata_sha256": sha256(output / "single_reference/metadata.json"),
            "survival_metadata_sha256": sha256(
                output / "survival_reference/metadata.json"
            ),
            "previous_artifact_metadata_sha256": protocol[
                "previous_artifact_metadata_sha256"
            ],
        }
        write_json(frozen_path, frozen)
        print(
            json.dumps(
                {
                    "event": "frozen",
                    "members": frozen["members"],
                    "weights": frozen["weights"],
                }
            ),
            flush=True,
        )
    if selection_only:
        return
    # Test preparation and all test labels are accessed after the freeze.
    test = prepare_role(source, output, "test")
    if test.origin.min() < pd.Timestamp(protocol["available_asof"]):
        raise ValueError("Test starts before the model ready date")
    context = context_for(test)
    result = {}
    for name, directory in (
        ("selected", output / "artifact"),
        ("best_validation_single", output / "single_reference"),
        ("survival", output / "survival_reference"),
        ("previous_10_feature_ensemble", previous / "artifact"),
    ):
        model = CompactT1.load(directory)
        measured, distribution = evaluate(model, test, context)
        np.savez_compressed(output / f"test_{name}.npz", distribution=distribution)
        result[name] = measured
    result.update(
        frozen_sha256=sha256(frozen_path),
        test_anchors=len(test),
        test_worlds=test.world.nunique(),
        test_firms=test.groupby(["world", "firm"]).ngroups,
        selection_uses_test=False,
    )
    write_json(output / "test_results.json", result)
    write_report(output, protocol, selection, result)
    print(
        json.dumps(
            {
                "event": "complete",
                "members": frozen["members"],
                "weights": frozen["weights"],
                "validation": selection["selected"]["score"],
                "test": result["selected"]["score"],
                "shap_p95": selection["selected"]["latency"]["p95_seconds"],
            }
        ),
        flush=True,
    )


def write_report(output, protocol, selection, result):
    chosen = selection["selected"]
    members = ", ".join(
        f"{name} {weight:.0%}"
        for name, weight in zip(chosen["members"], chosen["weights"])
    )
    rows = [
        "# T1 với 18 feature và baseline Survival",
        "",
        f"Tổ hợp được chọn bằng validation gồm **{members}**.",
        "",
        "Dùng đúng 18 feature trong sáu nhóm người dùng cung cấp. Các ứng viên dùng cùng snapshot hóa đơn mở, trạng thái tiền đã thu tại ngày chốt và nhãn tất toán bằng tiền trong 13 tuần. Baseline Survival sử dụng hazard thực nghiệm phân tầng tuổi, cùng risk set và trọng số. Nó tham gia cả đối chứng lẫn tìm ensemble.",
        "",
        "Mỗi model học có hai cấu hình trên cùng 100.000 risk-row. MLP được cấp tối đa 120/180 vòng. Dự báo validation được lưu theo trial để tìm tổ hợp và trọng số.",
        "",
        "Tiêu chí chính là trung bình hai sai số tiền thu chuẩn hóa theo dư nợ tại từng World/doanh nghiệp/origin. Thành phần tuần dùng tổng sai số tuyệt đối theo 13 tuần, thành phần lũy kế dùng trung bình sai số tuyệt đối lũy kế. Hai thành phần có trọng số 0,5. Phân phối tiền thu đi qua cùng empirical partial override như T6. Integrated Brier 13 tuần có trọng số dư nợ là giới hạn phụ khi thêm thành viên. Đây là tiêu chí được khai báo cho lượt tìm có giới hạn này.",
        "",
        f"Đã chấm {selection['combination_count']} cấu hình ensemble. SHAP toàn tổ hợp có p95 **{chosen['latency']['p95_seconds']:.4f} giây** trên các context đã đo. Nền dùng toàn bộ cohort khi tối đa 512 hóa đơn, tập lớn hơn dùng 128 mẫu phân tầng có trọng số và ba mẫu kiểm tra độ nhạy.",
        "",
        "Feature, thành viên, trọng số và artifact được ghi trong `frozen.json` trước khi chuẩn bị bảng test.",
        "",
        "| Cấu hình test | Cash score chuẩn hóa ↓ | MAE thu tuần VND ↓ | MAE thu lũy kế VND ↓ | Brier4 ↓ | Brier13 ↓ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in (
        "selected",
        "best_validation_single",
        "survival",
        "previous_10_feature_ensemble",
    ):
        measured = result[name]
        rows.append(
            f"| {name} | {measured['score']:.6f} | {measured['cash_weekly_mae_vnd']:.0f} | {measured['cash_cumulative_mae_vnd']:.0f} | {measured['brier4']:.6f} | {measured['brier13']:.6f} |"
        )
    rows.extend(
        [
            "",
            "Các số đo tiền thu trên World dùng cùng các landmark đủ điều kiện đã lấy mẫu. Backtest toàn bộ công nợ của doanh nghiệp qua T6 được ghi riêng.",
            "",
            "## Giới hạn",
            "",
        ]
    )
    rows.extend(f"- {limitation}" for limitation in protocol["limitations"])
    (output / "REPORT.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=ROOT / "outputs/t1/compact_world_20261112"
    )
    parser.add_argument(
        "--previous",
        type=Path,
        default=ROOT / "outputs/t1/compact_ensemble_20261112_v3",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latency-inputs", type=Path)
    parser.add_argument("--selection-only", action="store_true")
    args = parser.parse_args()
    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        run(
            args.source,
            args.output,
            args.previous,
            args.latency_inputs,
            args.selection_only,
        )
