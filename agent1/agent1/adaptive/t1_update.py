"""Rolling global-to-local T1 selection, with causal validation and audit gates."""

from __future__ import annotations

import hashlib
import math
import pickle
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

import pandas as pd
from threadpoolctl import threadpool_limits

from .data import fingerprint
from .bundle_metadata import serving_manifest
from .cash_adapter import VERSION as ADAPTER_VERSION, bundle_version, fit_partial
from .landmark_adaptation import continue_neural, continue_tree, pool
from .landmark_features import SCHEMA
from .t1_catalog import GlobalCatalog
from .t1_data import (
    landmarks,
    predict,
    risk_rows,
    rolling_landmarks,
    score,
    visible_data,
)

VERSION = "t1-partial-bundle-v2"
FAMILIES = ("neural", "lightgbm", "xgboost")
GRIDS = {
    "neural": tuple((lr, n) for lr in (0.00005, 0.0001) for n in (5, 20)),
    "lightgbm": tuple((lr, n) for lr in (0.01, 0.05) for n in (16, 64)),
    "xgboost": tuple((lr, n) for lr in (0.02, 0.08) for n in (12, 48)),
}


@dataclass(frozen=True)
class UpdatePolicy:
    interval_days: int = 28
    lookback_days: int = 730
    stride_days: int = 28
    risk_cap: int = 12000
    half_life_days: float = 180.0
    partial_prior_strength: float = 30.0
    replay_fraction: float = 0.30
    minimum_fit_snapshots: int = 60
    minimum_fit_invoices: int = 20
    minimum_validation_snapshots: int = 20
    minimum_audit_snapshots: int = 20
    minimum_cash_gain: float = 0.0001
    ibs_ratio: float = 1.02
    ibs_slack: float = 0.0001
    alphas: tuple = (0.0, 0.25, 0.5, 0.75, 1.0)
    validation_offsets_days: tuple = (210, 182)

    def __post_init__(self):
        if any(
            type(n) is not int or n < 1
            for n in (
                self.interval_days,
                self.lookback_days,
                self.stride_days,
                self.risk_cap,
                self.minimum_fit_snapshots,
                self.minimum_fit_invoices,
                self.minimum_validation_snapshots,
                self.minimum_audit_snapshots,
            )
        ):
            raise ValueError("Ngân sách/cửa sổ cập nhật T1 không hợp lệ")
        if self.lookback_days > 730:
            raise ValueError("Cửa sổ cập nhật T1 tối đa 730 ngày")
        if (
            not all(
                math.isfinite(v)
                for v in (
                    self.half_life_days,
                    self.partial_prior_strength,
                    self.replay_fraction,
                    self.minimum_cash_gain,
                    self.ibs_ratio,
                    self.ibs_slack,
                    *self.alphas,
                )
            )
            or not self.validation_offsets_days
            or any(type(n) is not int or n < 182 for n in self.validation_offsets_days)
            or len(set(self.validation_offsets_days))
            != len(self.validation_offsets_days)
            or self.half_life_days <= 0
            or self.partial_prior_strength <= 0
            or not 0 <= self.replay_fraction < 1
            or self.minimum_cash_gain < 0
            or self.ibs_ratio < 1
            or self.ibs_slack < 0
            or not self.alphas
            or any(not 0 <= a <= 1 for a in self.alphas)
        ):
            raise ValueError("Guard/trọng số cập nhật T1 không hợp lệ")


def code_signature():
    root = Path(__file__).parent
    names = (
        "t1_update.py",
        "t1_data.py",
        "t1_catalog.py",
        "landmark_adaptation.py",
        "landmark_features.py",
        "compact_t1.py",
        "compact_ensemble.py",
        "data.py",
        "cash_history.py",
        "cash_adapter.py",
        "payment_coverage.py",
        "bundle_metadata.py",
    )
    return hashlib.sha256(b"".join((root / n).read_bytes() for n in names)).hexdigest()


def valid_incumbent(bundle, cutoff, catalog):
    if bundle and bundle.get("algorithm_version") == VERSION:
        if pd.Timestamp(bundle["asof"]) > pd.Timestamp(cutoff):
            raise ValueError("Model T1 hiện tại được tạo sau ngày cập nhật")
        if bundle.get("catalog_sha256") != catalog.digest:
            raise ValueError("Gói global đã đổi; cần migration có kiểm định riêng")
        if getattr(bundle["model"], "feature_schema", None) != SCHEMA:
            raise ValueError("Schema model T1 đang phục vụ không khớp")
        if (bundle.get("partial") is None or bundle["partial"].version != ADAPTER_VERSION
                or pd.Timestamp(bundle["partial"].fitted_through) > pd.Timestamp(cutoff)):
            raise ValueError("Bundle thiếu nhánh partial hợp lệ tại ngày chốt")
        if not bundle.get("serving_manifest"):
            bundle = dict(bundle, serving_manifest=serving_manifest(
                bundle, data_version=bundle.get("dataset_hash") or catalog.digest,
                policy=bundle.get("policy", {"method": "legacy_serving"}), ready_on=bundle["asof"],
            ))
        return bundle
    # Legacy local-from-scratch ensembles are not eligible for the new selector.
    result = catalog.default_bundle(cutoff, auxiliary=bundle)
    result["legacy_t1_ignored"] = bool(bundle)
    return result


def ibs_guard(metrics, baseline, policy):
    return (
        metrics["integrated_brier13"]
        <= baseline["integrated_brier13"] * policy.ibs_ratio + policy.ibs_slack
    )


def improves(metrics, baseline, policy):
    return metrics["score"] <= baseline[
        "score"
    ] - policy.minimum_cash_gain and ibs_guard(metrics, baseline, policy)


def learn(reference, arrays, replay, lr, budget, policy):
    if reference.name == "neural":
        started = time.perf_counter()
        before = reference.booster[-1]._optimizer.t
        model = continue_neural(
            reference,
            *arrays,
            replay,
            epochs=budget,
            learning_rate=lr,
            replay_fraction=policy.replay_fraction,
        )
        return model, {
            "optimizer_updates": int(model.booster[-1]._optimizer.t - before),
            "frozen_scaler": True,
            "training_seconds": time.perf_counter() - started,
        }
    return continue_tree(
        reference,
        *arrays,
        replay,
        rounds=budget,
        learning_rate=lr,
        replay_fraction=policy.replay_fraction,
    )


def train_update(
    data,
    cutoff,
    progress=lambda _: None,
    *,
    incumbent=None,
    catalog=None,
    policy=None,
    grids=None,
):
    catalog = catalog or GlobalCatalog()
    policy = policy or UpdatePolicy()
    grids = GRIDS if grids is None else grids
    T = pd.Timestamp(cutoff).normalize()
    incumbent = valid_incumbent(incumbent, T, catalog)
    original = {
        n: pickle.dumps(m, protocol=pickle.HIGHEST_PROTOCOL)
        for n, m in catalog.models.items()
    }
    # Training sees only records known at T; future revisions never enter its hash.
    data = visible_data(data, T)
    validation_origins = sorted(
        T - pd.Timedelta(days=n) for n in policy.validation_offsets_days
    )
    validation_origin = validation_origins[0]
    audit_origin = T - pd.Timedelta(days=91)
    result = deepcopy(incumbent)
    result.update(
        update_asof=str(T.date()),
        algorithm_version=VERSION,
        dataset_hash=fingerprint(data),
        code_hash=code_signature(),
        dependencies={
            n: version(n)
            for n in ("numpy", "pandas", "scikit-learn", "lightgbm", "xgboost")
        },
        policy=asdict(policy),
        selection=[],
        training_trace=[],
        train_n=0,
        validation_n=0,
        selected_method=incumbent.get("serving_method", incumbent["selected_method"]),
        selected_weight=0.0,
        audit={"accepted": False, "status": "insufficient_local_windows"},
        promotion_status="kept_incumbent",
        proposal=None,
        windows={
            "training_label_through": str(validation_origin.date()),
            "validation_origin": str(validation_origin.date()),
            "validation_origins": [str(t.date()) for t in validation_origins],
            "validation_label_through": str(audit_origin.date()),
            "audit_origin": str(audit_origin.date()),
            "audit_label_through": str(T.date()),
            "final_label_through": str(T.date()),
            "rolling_lookback_days": policy.lookback_days,
        },
        limitation="Chọn bằng cash13 và guard IBS; nhãn tuần chưa quan sát bị censor. Dải tiền T6 được kiểm định riêng.",
    )
    if not catalog.ready(validation_origin):
        result["audit"]["status"] = "globals_unavailable_at_validation_origin"
        return result
    progress("T1: dựng snapshot và nhãn local theo từng ngày biết")
    fit = rolling_landmarks(
        data,
        validation_origin,
        lookback_days=policy.lookback_days,
        stride_days=policy.stride_days,
    )
    fit = fit[fit.followup_days >= 7].reset_index(drop=True)
    validation_parts = [
        landmarks(data, origin, audit_origin) for origin in validation_origins
    ]
    validation_parts = [p[p.followup_days >= 91].reset_index(drop=True) for p in validation_parts]
    val = pd.concat(validation_parts, ignore_index=True)
    result["train_n"], result["validation_n"] = len(fit), len(val)
    if (
        len(fit) < policy.minimum_fit_snapshots
        or fit.invoice_id.nunique() < policy.minimum_fit_invoices
        or any(
            len(part) < policy.minimum_validation_snapshots for part in validation_parts
        )
    ):
        result["audit"].update(
            fit_rows=len(fit), validation_rows=len(val)
        )
        return result
    arrays, result["fit_data"] = risk_rows(
        fit, cap=policy.risk_cap, half_life_days=policy.half_life_days
    )
    partial = fit_partial(fit, validation_origin, prior=catalog.partial,
                          strength=policy.partial_prior_strength,
                          half_life_days=policy.half_life_days)
    result["partial_selection"] = dict(sha256=partial.digest, **partial.evidence)
    baseline_val = catalog.models["default"]
    if pd.Timestamp(incumbent["asof"]) <= validation_origin:
        baseline_val = incumbent["model"]
    vm = score(predict(baseline_val, val), val, partial=partial)
    result["validation_baseline"] = vm
    candidates = []
    fitted = {}

    def evaluate(name, model, *, family=None, learning_rate=0.0, budget=0, alpha=0.0):
        measured = score(predict(model, val), val, partial=partial)
        guard = ibs_guard(measured, vm, policy)
        record = {
            "method": name,
            "family": family,
            "learning_rate": learning_rate,
            "budget": budget,
            "alpha": alpha,
            "status": "evaluated",
            "guard": bool(guard),
            "validation_cash13": measured["score"],
            "validation_ibs13": measured["integrated_brier13"],
            "metrics": measured,
            "partial_sha256": partial.digest,
        }
        result["selection"].append(record)
        fitted[name] = model
        if guard:
            candidates.append(
                (measured["score"], budget, learning_rate, alpha, name, record)
            )

    with threadpool_limits(limits=2), threadpool_limits(limits=1, user_api="blas"):
        for name, model in catalog.models.items():
            evaluate("global_" + name, model)
        if pd.Timestamp(incumbent["asof"]) <= validation_origin:
            evaluate("incumbent", incumbent["model"])
        for family in FAMILIES:
            reference = catalog.models[family]
            for index, (lr, budget) in enumerate(grids[family]):
                progress(
                    f"T1: học tiếp {family}, cấu hình {index + 1}/{len(grids[family])}"
                )
                model, trace = learn(
                    reference, arrays, catalog.replay, lr, budget, policy
                )
                result["training_trace"].append(
                    dict(
                        stage="selection",
                        family=family,
                        learning_rate=lr,
                        budget=budget,
                        sample_sha256=result["fit_data"]["sample_sha256"],
                        **trace,
                    )
                )
                for alpha in policy.alphas:
                    evaluate(
                        f"{family}_local_{index}_a{alpha}",
                        pool(reference, model, alpha),
                        family=family,
                        learning_rate=lr,
                        budget=budget,
                        alpha=alpha,
                    )
        selected = min(candidates, key=lambda r: r[:5])[-1]
        chosen = fitted[selected["method"]]
        comparator_available = pd.Timestamp(incumbent["asof"]) <= audit_origin
        # The specification is locked before any audit outcome is inspected.
        result["locked_spec"] = dict(selected)
        audit = pd.DataFrame()
        baseline_audit = chosen_audit = None
        passed = False
        if comparator_available:
            audit = landmarks(data, audit_origin, T)
            audit = audit[audit.followup_days >= 91].reset_index(drop=True)
            if len(audit) < policy.minimum_audit_snapshots:
                result["audit"].update(status="insufficient_audit_outcomes", n=len(audit))
                return result
            baseline_audit = score(predict(incumbent["model"], audit), audit,
                                   partial=incumbent["partial"])
            chosen_audit = score(predict(chosen, audit), audit, partial=partial)
            passed = improves(chosen_audit, baseline_audit, policy)
        result["audit"] = {
            "status": "scored" if comparator_available else "incumbent_too_new",
            "accepted": bool(passed and comparator_available),
            "candidate": chosen_audit,
            "baseline": baseline_audit,
            "comparator": "incumbent",
            "baseline_bundle_version": incumbent["t1_version"],
            "baseline_partial_sha256": incumbent["partial"].digest,
            "candidate_partial_sha256": partial.digest,
            "incumbent_available_at_origin": bool(comparator_available),
            "candidate_passed": bool(passed),
            "n": len(audit),
        }
        result["selected_method"] = selected["method"]
        result["selected_weight"] = selected["alpha"]
        if comparator_available and not passed:
            # No refit and no second candidate after a failed audit.
            return result
        final = chosen
        full = rolling_landmarks(data, T, lookback_days=policy.lookback_days,
                                 stride_days=policy.stride_days)
        final_partial = fit_partial(full, T, prior=catalog.partial,
                                    strength=policy.partial_prior_strength,
                                    half_life_days=policy.half_life_days)
        if selected["family"] and selected["alpha"] > 0:
            progress(
                "T1: refit từ global trên cửa sổ gần nhất, chỉ dùng tuần đã quan sát"
            )
            final_arrays, result["final_data"] = risk_rows(
                full, cap=policy.risk_cap, half_life_days=policy.half_life_days
            )
            updated, trace = learn(
                catalog.models[selected["family"]],
                final_arrays,
                catalog.replay,
                selected["learning_rate"],
                selected["budget"],
                policy,
            )
            result["training_trace"].append(
                dict(
                    stage="final_refit",
                    family=selected["family"],
                    learning_rate=selected["learning_rate"],
                    budget=selected["budget"],
                    sample_sha256=result["final_data"]["sample_sha256"],
                    **trace,
                )
            )
            final = pool(catalog.models[selected["family"]], updated, selected["alpha"])
        proposal_version = bundle_version(final, final_partial)
        # A candidate can be trained now, but cannot be back-scored against an
        # incumbent whose own training/selection occurred after the audit origin.
        result["proposal"] = {
            "model": final,
            "partial": final_partial,
            "version": proposal_version,
            "asof": str(T.date()),
            "method": selected["method"],
            "spec": {
                k: selected[k] for k in ("family", "learning_rate", "budget", "alpha")
            },
            "historical_audit_passed": bool(passed),
            "prospective_eligible": not comparator_available,
        }
        if passed and comparator_available:
            result.update(
                model=final,
                partial=final_partial,
                partial_version=final_partial.digest,
                adapter_version=ADAPTER_VERSION,
                asof=str(T.date()),
                anchor=final,
                weight=1.0,
                t1_version=proposal_version,
                t1_parameter_asof=str(T.date()),
                serving_method=selected["method"],
                promotion_status="accepted_historical_audit",
            )
            result["serving_manifest"] = serving_manifest(
                result, data_version=result["dataset_hash"], policy=result["policy"],
                ready_on=str(T.date()),
            )
        else:
            result["promotion_status"] = "pending_prospective_audit"
    result["t1_provenance"] = {
        "source": "global_local_selector",
        "catalog_sha256": catalog.digest,
        "metadata_sha256": catalog.digest,
        "local_adaptation": "local_" in result.get("serving_method", ""),
        "synthetic": bool(catalog.metadata.get("synthetic")),
        "promotion_status": result["promotion_status"],
    }
    for name, model in catalog.models.items():
        if pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL) != original[name]:
            raise AssertionError("Global T1 bị thay đổi khi học local")
    return result
