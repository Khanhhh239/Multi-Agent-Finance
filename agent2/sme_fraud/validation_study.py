"""Data-driven detector selection, verified calibration, and explicit fallback validation for Agent2."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import tracemalloc

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, recall_score
from sklearn.model_selection import StratifiedKFold

from finance_input.validation import FORMATS, StrictValidator
from sme_fraud.import_files import canonical, digest
from sme_fraud.rule35_comparison import MASTER_QUALITY_RULES, SCOPE_RULES, extract_rule35_records
from sme_fraud.score_statistics import empirical_rank
from sme_fraud.selection_comparison import BUDGET, POLICY, identity, select_records
from sme_fraud.snapshot_features import utc

STUDY_VERSION = "agent2-validation-study/1.0.0"
PLAN_VERSION = "evaluation-plan/1.0.0"
REFERENCE_VERSION = "historical-reference-dist/1.0.0"
CALIBRATOR_VERSION = "verified-calibrator/1.0.0"
FALLBACK_PLAN_VERSION = "explicit-fallback-plan/1.0.0"
CANDIDATE_SHADOW_VERSION = "candidate-shadow-bundle/1.0.0"

SPLIT_NAMES = (
    "history_train",
    "detector_validation",
    "calibration_policy_validation",
    "sealed_future_test",
)
VALID_VERIFIED_OUTCOMES = frozenset({"verified_fraud", "verified_non_fraud", "inconclusive", None})
FORBIDDEN_VERIFIED_OUTCOMES = frozenset({"confirmed_risk", "legitimate"})
HE_ONLY_BRANCH_TOKENS = frozenset({"he", "fhe", "concrete_fhe", "he_vote", "encrypted_vote"})

DEFAULT_OPEN_QUALITY_GATES = (
    {
        "decision_id": "D-03",
        "status": "OPEN_BLOCKING",
        "metric": "precision_and_recall_at_review_budget",
        "proposed_threshold": ">=80% resolved precision / pilot review capacity",
        "approved_for_production": False,
        "note": "Threshold and metric weights remain unapproved in Agent2_Spec_v2_1/99_decision_log.md.",
    },
    {
        "decision_id": "D-04",
        "status": "OPEN_BLOCKING",
        "metric": "cross_branch_weight_and_calibration_cutoff",
        "proposed_threshold": "experimental shadow only; requires human sign-off",
        "approved_for_production": False,
        "note": "Ensemble combination weights and probability action thresholds are not production approved.",
    },
    {
        "decision_id": "D-06",
        "status": "OPEN_BLOCKING",
        "metric": "production_review_budget_capacity",
        "proposed_threshold": "5 transactions/enterprise evaluation trial (experimental)",
        "approved_for_production": False,
        "note": "Five-transaction cap is locked only for comparison trial, not approved as production SLA.",
    },
    {
        "decision_id": "D-07",
        "status": "PROPOSED_DEFAULT_EXPERIMENTAL_ONLY",
        "metric": "high_risk_calibration_operating_point",
        "proposed_threshold": "unapproved; calibrated probability is informational in shadow mode",
        "approved_for_production": False,
        "note": "Operating threshold for automated triage escalation stays open.",
    },
    {
        "decision_id": "D-09",
        "status": "OPEN_BLOCKING",
        "metric": "minimum_verified_sample_size_for_release",
        "proposed_threshold": "requires real enterprise multi-quarter verified sample before promotion",
        "approved_for_production": False,
        "note": "Synthetic validation benchmarks technical behavior only and does not approve production go-live.",
    },
)

SCHEMA_PATH = Path(__file__).with_name("evaluation_plan.schema.json")


class ValidationStudyError(ValueError):
    """Structured error raised on plan, isolation, calibration, or fallback violations."""

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _require(condition: bool, code: str, message: str, **details) -> None:
    if not condition:
        raise ValidationStudyError(code, message, details=details)


def load_plan_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _trace_cost(fn, *args, **kwargs):
    started_here = not tracemalloc.is_tracing()
    if started_here:
        tracemalloc.start()
    before_cur, before_peak = tracemalloc.get_traced_memory()
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    finally:
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        after_cur, after_peak = tracemalloc.get_traced_memory()
        if started_here:
            tracemalloc.stop()
    peak_delta = max(0, after_peak - before_cur)
    return result, {
        "runtime_ms": elapsed_ms,
        "peak_memory_kb": round(peak_delta / 1024.0, 2),
        "observed_peak_kb": round(after_peak / 1024.0, 2),
    }


def _is_finite_number(val) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def _row_key(row: dict) -> tuple[str, int]:
    return (str(row["record_id"]), int(row["revision"]))


def _safe_float_dict(d: dict) -> dict[str, float]:
    return {str(k): round(float(v), 10) for k, v in d.items()}


def _validate_split_schedule(plan: dict) -> None:
    splits = plan["splits"]
    prev_end = None
    for name in SPLIT_NAMES:
        spec = splits[name]
        start_dt = utc(spec["start_at"])
        end_dt = utc(spec["end_at"])
        as_of_dt = utc(spec["as_of"])
        _require(start_dt <= end_dt, "SPLIT_CHRONOLOGY_INVALID",
                 f"Split {name} has start_at > end_at.", split=name)
        _require(end_dt <= as_of_dt, "SPLIT_CHRONOLOGY_INVALID",
                 f"Split {name} has end_at > as_of.", split=name)
        if prev_end is not None:
            _require(prev_end <= start_dt, "SPLIT_CHRONOLOGY_INVALID",
                     f"Split {name} overlaps preceding split chronologically.", split=name)
        prev_end = end_dt

    _require("sealed_future_test" in splits, "SPLIT_CHRONOLOGY_INVALID", "Missing sealed_future_test.")
    test_uses = set(splits["sealed_future_test"]["allowed_uses"])
    forbidden_test_uses = test_uses & {"fit_detectors", "fit_preprocess", "fit_reference_distribution",
                                       "select_combination", "fit_calibrator", "tune_thresholds"}
    _require(not forbidden_test_uses, "TEST_LEAKAGE_IN_PLAN",
             f"sealed_future_test allows forbidden training/tuning uses: {sorted(forbidden_test_uses)}",
             forbidden_uses=sorted(forbidden_test_uses))


def _validate_scope_and_versions(plan: dict) -> None:
    company = plan["scope"]["company_id"]
    seen_split_snaps = set()
    for snap in plan["snapshots"]:
        seen_split_snaps.add((snap["split"], snap["snapshot_id"]))
        split_spec = plan["splits"][snap["split"]]
        _require(snap["snapshot_id"] == split_spec["snapshot_id"], "EVALUATION_PLAN_PIN_MISMATCH",
                 f"Snapshot binding mismatch for split {snap['split']}.")
        _require(utc(snap["as_of"]) == utc(split_spec["as_of"]), "EVALUATION_PLAN_PIN_MISMATCH",
                 f"Snapshot as_of mismatch for split {snap['split']}.")

    for split_name, split_spec in plan["splits"].items():
        _require((split_name, split_spec["snapshot_id"]) in seen_split_snaps,
                 "EVALUATION_PLAN_PIN_MISMATCH",
                 f"Missing pinned snapshot entry for split {split_name}.")

    for binding in plan["versions"]["model_bindings"]:
        _require(binding["company_id"] == company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                 f"Model binding {binding['method_id']} belongs to {binding['company_id']}, expected {company}.",
                 expected_company=company, found_company=binding["company_id"])

    ref_by_id = {}
    for ref in plan["versions"]["reference_bindings"]:
        _require(ref["company_id"] == company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                 f"Reference binding {ref['reference_id']} belongs to {ref['company_id']}, expected {company}.",
                 expected_company=company, found_company=ref["company_id"])
        ref_by_id[ref["reference_id"]] = ref

    test_prov = [p for p in plan["labels"]["source_provenance"] if p["split"] == "sealed_future_test"]
    for src in plan["labels"]["source_provenance"]:
        _require(src["company_id"] == company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                 f"Label provenance for {src['split']} belongs to {src['company_id']}, expected {company}.")
    _require(bool(test_prov) and all(p["labels_blinded_before_lock"] for p in test_prov),
             "TEST_LEAKAGE_IN_PLAN", "sealed_future_test label provenance must stay blinded before lock.")


def _validate_candidates_and_fallbacks(plan: dict) -> None:
    ref_map = {r["reference_id"]: r for r in plan["versions"]["reference_bindings"]}
    arms = plan["candidates"]
    _require(any(a["kind"] == "rules_only" for a in arms),
             "EVALUATION_PLAN_SCHEMA_INVALID", "Plan must include a rules_only baseline arm.")

    seen_arm_ids = set()
    for arm in arms:
        aid = arm["arm_id"]
        _require(aid not in seen_arm_ids, "EVALUATION_PLAN_SCHEMA_INVALID", f"Duplicate arm_id {aid}.")
        seen_arm_ids.add(aid)

        lowered = {b.lower() for b in arm["branches"]}
        _require(not (lowered & HE_ONLY_BRANCH_TOKENS), "EVALUATION_PLAN_SCHEMA_INVALID",
                 f"Arm {aid} treats HE as an independent voter instead of training mechanism.")
        _require(len(arm["branches"]) == len(set(arm["branches"])),
                 "EVALUATION_PLAN_SCHEMA_INVALID", f"Arm {aid} contains duplicate branches.")

        kind = arm["kind"]
        if kind in ("percentile_ensemble", "rules_plus_percentile_ensemble"):
            _require(arm["uses_percentile_reference"] is True, "RAW_SCORE_MIXING_FORBIDDEN",
                     f"Combined ensemble arm {aid} cannot mix raw scores across scales without frozen historical percentiles.")
            weights = arm["weights"]
            _require(isinstance(weights, dict) and bool(weights), "RAW_SCORE_MIXING_FORBIDDEN",
                     f"Combined ensemble arm {aid} requires explicit branch weights.")
            _require(set(weights) <= set(arm["branches"]), "EVALUATION_PLAN_SCHEMA_INVALID",
                     f"Weights in {aid} must reference only declared branches.")
            total_w = sum(float(v) for v in weights.values())
            _require(abs(total_w - 1.0) <= 1e-6, "EVALUATION_PLAN_SCHEMA_INVALID",
                     f"Ensemble weights in {aid} must sum to 1.0, got {total_w}.")
            if kind == "rules_plus_percentile_ensemble":
                _require("rules_35" in arm["branches"] and len(weights) >= 2, "EVALUATION_PLAN_SCHEMA_INVALID",
                         f"Arm {aid} must combine rules_35 with >=2 weighted branches.")
            else:
                _require(len(weights) >= 2, "EVALUATION_PLAN_SCHEMA_INVALID",
                         f"Arm {aid} requires >=2 weighted branches.")

            bound_ref_methods = set()
            for rid in arm["reference_ids"]:
                _require(rid in ref_map, "EVALUATION_PLAN_PIN_MISMATCH",
                         f"Arm {aid} cites unknown reference_id {rid}.")
                bound_ref_methods.add(ref_map[rid]["method_id"])
            _require(set(weights) <= bound_ref_methods, "RAW_SCORE_MIXING_FORBIDDEN",
                     f"Arm {aid} lacks frozen historical reference distribution for weighted branches {sorted(set(weights) - bound_ref_methods)}.")
        elif kind == "individual_detector":
            _require(len(arm["branches"]) == 1, "EVALUATION_PLAN_SCHEMA_INVALID",
                     f"Individual arm {aid} must contain exactly 1 branch.")
        elif kind == "rules_plus_ml":
            _require("rules_35" in arm["branches"] and len(arm["branches"]) == 2,
                     "EVALUATION_PLAN_SCHEMA_INVALID", f"Arm {aid} must pair rules_35 with 1 ML branch.")

    seen_fb = set()
    for fb in plan["fallback_specs"]:
        fid = fb["fallback_config_id"]
        _require(fid not in seen_fb, "EVALUATION_PLAN_SCHEMA_INVALID", f"Duplicate fallback_config_id {fid}.")
        seen_fb.add(fid)
        if fb["weight_policy"] == "unavailable":
            _require(fb["used_branches"] == [] and (fb["weights"] is None or fb["weights"] == {}),
                     "FALLBACK_SILENT_REWEIGHT_FORBIDDEN",
                     f"Unavailable fallback {fid} cannot keep active branches or weights.")
        else:
            _require(fb["is_full_ensemble"] is False, "FALLBACK_SILENT_REWEIGHT_FORBIDDEN",
                     f"Degraded fallback {fid} cannot claim is_full_ensemble=True.")
            if fb["weights"]:
                _require(set(fb["weights"]) <= set(fb["used_branches"]),
                         "EVALUATION_PLAN_SCHEMA_INVALID",
                         f"Fallback {fid} weights must reference used_branches only.")
                _require(abs(sum(float(v) for v in fb["weights"].values()) - 1.0) <= 1e-6,
                         "EVALUATION_PLAN_SCHEMA_INVALID",
                         f"Fallback {fid} weights must sum to 1.0.")


def validate_evaluation_plan(plan: dict) -> None:
    """Validate EvaluationPlan against JSON schema and mathematical/governance invariants."""
    schema = load_plan_schema()
    errors = list(StrictValidator(schema, format_checker=FORMATS).iter_errors(plan))
    if errors:
        first = errors[0]
        raise ValidationStudyError(
            "EVALUATION_PLAN_SCHEMA_INVALID",
            f"EvaluationPlan schema validation failed: {first.message}",
            details={"path": list(first.absolute_path), "error_count": len(errors)},
        )
    _validate_split_schedule(plan)
    _validate_scope_and_versions(plan)
    _validate_candidates_and_fallbacks(plan)


def _check_manifest_pins(plan: dict, snapshot_manifests: dict[str, dict]) -> None:
    scope = plan["scope"]
    for snap in plan["snapshots"]:
        split = snap["split"]
        manifest = snapshot_manifests.get(split)
        _require(manifest is not None, "EVALUATION_PLAN_PIN_MISMATCH",
                 f"Missing runtime snapshot manifest for split {split}.", split=split)
        _require(manifest.get("tenant_id") == scope["tenant_id"] and manifest.get("company_id") == scope["company_id"],
                 "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                 f"Manifest for {split} has scope {manifest.get('tenant_id')}:{manifest.get('company_id')}, expected {scope['tenant_id']}:{scope['company_id']}.")
        _require(manifest.get("snapshot_id") == snap["snapshot_id"]
                 and manifest.get("checksum") == snap["snapshot_sha256"]
                 and manifest.get("data_checksum") == snap["data_checksum"]
                 and manifest.get("contract_version") == snap["contract_version"],
                 "EVALUATION_PLAN_PIN_MISMATCH",
                 f"Snapshot checksum/ID mismatch on split {split}.",
                 split=split, expected_snapshot=snap["snapshot_id"], got_snapshot=manifest.get("snapshot_id"))
        if manifest.get("as_of"):
            _require(utc(manifest["as_of"]) == utc(snap["as_of"]),
                     "EVALUATION_PLAN_PIN_MISMATCH", f"Snapshot as_of mismatch on split {split}.")


def _check_model_and_ref_pins(plan: dict, model_artifacts: dict | None, reference_artifacts: dict | None) -> None:
    company = plan["scope"]["company_id"]
    if model_artifacts is not None:
        for b in plan["versions"]["model_bindings"]:
            mid = b["method_id"]
            if b["kind"] == "rules":
                continue
            art = model_artifacts.get(mid)
            if art is None:
                continue  # Allow controlled missing-model tests when not explicitly asserting pre-lock
            _require(art.get("company_id") == company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                     f"Model artifact {mid} belongs to {art.get('company_id')}, expected {company}.")
            actual_sha = art.get("artifact_sha256") or art.get("approval_sha256") or art.get("sha256")
            _require(art.get("artifact_id") == b["artifact_id"] and actual_sha == b["artifact_sha256"],
                     "EVALUATION_PLAN_PIN_MISMATCH",
                     f"Model binding mismatch for {mid}.", method_id=mid, expected=b["artifact_id"], got=art.get("artifact_id"))

    if reference_artifacts is not None:
        for rb in plan["versions"]["reference_bindings"]:
            rid = rb["reference_id"]
            ref = reference_artifacts.get(rid)
            _require(ref is not None, "EVALUATION_PLAN_PIN_MISMATCH",
                     f"Pinned historical reference {rid} not supplied.", reference_id=rid)
            _require(ref.get("company_id") == company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                     f"Reference {rid} belongs to {ref.get('company_id')}, expected {company}.")
            _require(ref.get("reference_version") == rb["reference_version"]
                     and ref.get("reference_sha256") == rb["reference_sha256"]
                     and ref.get("fitted_split") == "history_train",
                     "EVALUATION_PLAN_PIN_MISMATCH",
                     f"Reference artifact mismatch for {rid}.", reference_id=rid)


def lock_evaluation_plan(
    plan: dict,
    *,
    snapshot_manifests: dict[str, dict] | None = None,
    model_artifacts: dict[str, dict] | None = None,
    reference_artifacts: dict[str, dict] | None = None,
    label_packets: dict[str, dict] | None = None,
) -> dict:
    """Validate and cryptographically lock an EvaluationPlan before inspecting sealed_future_test labels."""
    validate_evaluation_plan(plan)
    if snapshot_manifests is not None:
        _check_manifest_pins(plan, snapshot_manifests)
    _check_model_and_ref_pins(plan, model_artifacts, reference_artifacts)

    if label_packets is not None:
        company = plan["scope"]["company_id"]
        for src in plan["labels"]["source_provenance"]:
            if src["source_type"] != "label_store_packet":
                continue
            pkt = label_packets.get(src.get("packet_id")) or label_packets.get(src["split"])
            _require(pkt is not None, "EVALUATION_PLAN_PIN_MISMATCH",
                     f"Missing label packet metadata for split {src['split']}.")
            _require(pkt.get("company_id") == company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                     f"Label packet for {src['split']} belongs to wrong company.")
            _require(pkt.get("packet_id") == src.get("packet_id")
                     and pkt.get("revision") == src.get("revision")
                     and pkt.get("lock_sha256") == src.get("lock_sha256"),
                     "EVALUATION_PLAN_PIN_MISMATCH",
                     f"Label packet pin mismatch for split {src['split']}.")

    plan_copy = deepcopy(plan)
    plan_sha256 = digest(canonical(plan_copy))
    return {
        "version": PLAN_VERSION,
        "plan_id": f"evp_{plan_sha256[:24]}",
        "plan_sha256": plan_sha256,
        "locked_before_test_inspection": True,
        "test_labels_inspected_at_lock": False,
        "plan": plan_copy,
    }


def build_reference_distribution(
    method_id: str,
    history_scores: list[float],
    *,
    company_id: str,
    tenant_id: str,
    snapshot_id: str,
    as_of: str,
    source_split: str = "history_train",
    score_scale: str = "raw",
) -> dict:
    """Freeze a sorted empirical reference distribution strictly from pre-validation history."""
    _require(source_split == "history_train", "REFERENCE_MISMATCH_OR_TEST_LEAK",
             f"Reference distribution must be fitted strictly on history_train, got {source_split}.",
             method_id=method_id, source_split=source_split)
    clean = [float(x) for x in history_scores if _is_finite_number(x)]
    _require(len(clean) >= 5, "REFERENCE_MISMATCH_OR_TEST_LEAK",
             f"Need >=5 finite history scores to build frozen reference for {method_id}, got {len(clean)}.")
    sorted_vals = sorted(clean)
    arr = np.asarray(sorted_vals, dtype=float)
    body = {
        "reference_version": REFERENCE_VERSION,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "method_id": method_id,
        "snapshot_id": snapshot_id,
        "as_of": as_of,
        "fitted_split": "history_train",
        "score_scale": score_scale,
        "count": len(sorted_vals),
        "sorted_scores": sorted_vals,
        "summary": {
            "min": round(float(arr[0]), 8),
            "p50": round(float(np.median(arr)), 8),
            "p95": round(float(np.percentile(arr, 95)), 8),
            "max": round(float(arr[-1]), 8),
            "mean": round(float(arr.mean()), 8),
        },
    }
    ref_sha = digest(canonical(body))
    body["reference_sha256"] = ref_sha
    body["reference_id"] = f"ref_{method_id}_{ref_sha[:16]}"
    return body


def transform_with_reference(
    reference: dict | None,
    raw_by_key: dict[tuple[str, int], float | None],
    *,
    expected_binding: dict,
    expected_company: str,
) -> dict[tuple[str, int], float | None]:
    """Map raw scores to frozen historical percentiles without inspecting batch distribution."""
    _require(reference is not None, "EVALUATION_PLAN_PIN_MISMATCH",
             f"Missing historical reference {expected_binding.get('reference_id')}.")
    _require(reference.get("company_id") == expected_company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
             f"Reference belongs to {reference.get('company_id')}, expected {expected_company}.")
    _require(reference.get("reference_id") == expected_binding.get("reference_id")
             and reference.get("reference_sha256") == expected_binding.get("reference_sha256")
             and reference.get("fitted_split") == "history_train",
             "EVALUATION_PLAN_PIN_MISMATCH",
             f"Reference distribution pin mismatch for {expected_binding.get('method_id')}.")

    frozen = tuple(float(v) for v in reference["sorted_scores"])
    mapped = {}
    finite_keys = []
    finite_vals = []
    for key, val in raw_by_key.items():
        if not _is_finite_number(val):
            mapped[key] = None
        else:
            finite_keys.append(key)
            finite_vals.append(float(val))
    if finite_vals:
        ranked = empirical_rank(frozen, np.asarray(finite_vals, dtype=float))
        for key, rk in zip(finite_keys, ranked):
            mapped[key] = round(float(rk), 10)
    return mapped


def _extract_rule_points(row: dict) -> float | None:
    if row.get("availability", {}).get("available", True) is False:
        return None
    cov = (row.get("rule_coverage") or {}).get("rules") or []
    applicable_rules = [e for e in cov if e["rule_id"] not in (SCOPE_RULES | MASTER_QUALITY_RULES)]
    unavailable = [e for e in applicable_rules if e["status"] == "unavailable"]
    not_app = [e for e in applicable_rules if e["status"] == "not_applicable"]
    if len(applicable_rules) - len(not_app) > 0 and len(unavailable) == (len(applicable_rules) - len(not_app)):
        return None
    total = 0.0
    for entry in applicable_rules:
        for hit in entry.get("hits") or []:
            if not hit.get("suppressed_reason"):
                pts = float(hit.get("points") or 0.0)
                if pts > 0:
                    total += pts
                elif hit.get("hard_trigger"):
                    total += 100.0
    return round(total, 6)


def extract_split_rows(
    split_name: str,
    scope,
    manifest: dict,
    analysis: dict,
    *,
    shadow: dict | None = None,
    raw_data: dict | None = None,
    model_artifacts: dict | None = None,
    candidate_ids_filter: set[str] | None = None,
) -> tuple[list[dict], dict[str, set[tuple[str, int]]]]:
    """Build standardized split rows joining 35 rules, unsupervised detectors, and supervised shadow."""
    company = next(iter(scope.company_ids))
    _require(manifest.get("tenant_id") == scope.tenant_id and manifest.get("company_id") == company,
             "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
             f"Snapshot {manifest.get('snapshot_id')} outside enterprise scope {scope.tenant_id}:{company}.")
    _require(analysis.get("version") == "snapshot-rule-analysis/1.0.0" and analysis.get("view") == "technical",
             "EVALUATION_PLAN_PIN_MISMATCH", "Analysis must be technical 35-rule snapshot analysis.")
    _require(analysis["snapshot"]["snapshot_id"] == manifest["snapshot_id"]
             and analysis["snapshot"]["checksum"] == manifest["checksum"]
             and analysis["snapshot"]["data_checksum"] == manifest["data_checksum"],
             "EVALUATION_PLAN_PIN_MISMATCH", f"Analysis snapshot mismatch on split {split_name}.")

    if shadow is not None:
        _require(shadow.get("tenant_id") == scope.tenant_id and shadow.get("company_id") == company,
                 "TENANT_OR_COMPANY_ISOLATION_VIOLATION", "Shadow run belongs to another tenant/company.")
        sb = shadow["snapshot"]
        _require(sb["snapshot_id"] == manifest["snapshot_id"]
                 and sb["checksum"] == manifest["checksum"]
                 and sb["data_checksum"] == manifest["data_checksum"]
                 and utc(sb["as_of"]) == utc(analysis["as_of"]),
                 "EVALUATION_PLAN_PIN_MISMATCH", f"Shadow run does not match {split_name} snapshot/as_of.")
        sup_pin = (model_artifacts or {}).get("supervised_shadow")
        if sup_pin is not None:
            _require(sup_pin.get("company_id") == company, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                     "Supervised shadow model artifact belongs to wrong company.")
            smodel = shadow.get("model") or {}
            actual_sha = smodel.get("approval_sha256") or smodel.get("artifact_sha256")
            actual_id = smodel.get("job_id") or smodel.get("model_id") or smodel.get("artifact_id")
            _require(actual_id == sup_pin["artifact_id"] and actual_sha == sup_pin["artifact_sha256"],
                     "EVALUATION_PLAN_PIN_MISMATCH",
                     f"Supervised shadow pin mismatch on {split_name}.",
                     expected=sup_pin["artifact_id"], got=actual_id)

    tx_meta = {}
    if raw_data is not None:
        src_scope = raw_data.get("source", {})
        _require(raw_data.get("tenant_id") == scope.tenant_id and raw_data.get("company_id") == company,
                 "TENANT_OR_COMPANY_ISOLATION_VIOLATION", "Raw snapshot source belongs to wrong tenant/company.")
        for tx in (src_scope.get("tables") or {}).get("transactions") or []:
            tx_meta[tx["transaction_id"]] = tx

    analysis_rows = {(r["transaction_id"], int(r["revision"])): r for r in analysis["rows"]}
    cases_stub = {
        k: {"case_id": "valcase_" + digest(canonical([scope.tenant_id, company, split_name, manifest["snapshot_id"], *k]))}
        for k in analysis_rows
    }
    pins = (analysis.get("bridge_provenance") or {}).get("model_pins") or {}
    first_ml = next((m for m, p in pins.items() if m != "robust_z" and p is not None), None)
    base_records, groups, _, _ = extract_rule35_records(analysis, cases_stub, ml_method=first_ml)
    shadow_map = {(r["record_id"], int(r["revision"])): r for r in (shadow.get("rows") or [])} if shadow else {}

    rows = []
    as_of_dt = utc(analysis["as_of"])
    for rec in base_records:
        key = identity(rec)
        if candidate_ids_filter is not None and key[0] not in candidate_ids_filter:
            continue
        raw_row = analysis_rows[key]
        tx = tx_meta.get(key[0], {})
        obs_str = tx.get("observed_at")
        post_cutoff = bool(obs_str and utc(obs_str) > as_of_dt) or (not rec["tx_visible"])
        rule_pts = None if post_cutoff else _extract_rule_points(raw_row)
        rule_available = (not post_cutoff) and (rec["rule_state"] != "unavailable")

        branches = {
            "rules_35": {
                "available": rule_available,
                "raw_score": rule_pts if rule_available else None,
                "score": rule_pts if rule_available else None,
                "score_kind": "rule_points",
                "rule_state": rec["rule_state"],
                "rule_completeness": rec["rule_eval_completeness"],
                "actionable_hit_rules": list(rec["actionable_hit_rules"]),
                "unavailable_rule_ids": list(rec["unavailable_rule_ids"]),
                "reason": None if rule_available else {"code": rec["rule_eval_completeness"]},
            }
        }

        for mid, mdata in (raw_row.get("methods") or {}).items():
            pin = (model_artifacts or {}).get(mid)
            pin_mismatch = (
                pin is not None
                and mdata.get("available") is True
                and (
                    (pin.get("company_id") and pin["company_id"] != company)
                    or (pin.get("artifact_id") and mdata.get("artifact_id") != pin["artifact_id"])
                )
            )
            _require(not (pin is not None and pin.get("company_id") and pin["company_id"] != company),
                     "TENANT_OR_COMPANY_ISOLATION_VIOLATION", f"Model {mid} belongs to wrong company.")
            _require(not pin_mismatch, "EVALUATION_PLAN_PIN_MISMATCH",
                     f"Runtime method {mid} artifact_id does not match plan binding.")
            avail = (not post_cutoff) and (mdata.get("available") is True)
            raw_val = mdata.get("raw_score") if avail else None
            score_val = mdata.get("score") if avail else None
            if avail and not _is_finite_number(score_val):
                avail, raw_val, score_val = False, None, None
            branches[mid] = {
                "available": avail,
                "raw_score": float(raw_val) if _is_finite_number(raw_val) else None,
                "score": float(score_val) if _is_finite_number(score_val) else None,
                "score_kind": mdata.get("score_kind", "empirical_midrank"),
                "artifact_id": mdata.get("artifact_id"),
                "feature_contract_fingerprint": mdata.get("feature_contract_fingerprint"),
                "reason": None if avail else ({"code": "post_cutoff"} if post_cutoff else deepcopy(mdata.get("reason"))),
            }

        srow = shadow_map.get(key)
        unapproved = shadow is not None and (
            shadow.get("model", {}).get("approved_for_shadow") is not True
            or not shadow.get("model", {}).get("approval_sha256")
        )
        if shadow is None:
            branches["supervised_shadow"] = {
                "available": False, "raw_score": None, "score": None,
                "score_kind": "uncalibrated_supervised_score",
                "reason": {"code": "missing_supervised_model"},
            }
        elif unapproved:
            branches["supervised_shadow"] = {
                "available": False, "raw_score": None, "score": None,
                "score_kind": "uncalibrated_supervised_score",
                "reason": {"code": "unapproved_shadow_model"},
            }
        elif srow is None or post_cutoff:
            branches["supervised_shadow"] = {
                "available": False, "raw_score": None, "score": None,
                "score_kind": "uncalibrated_supervised_score",
                "reason": {"code": "post_cutoff" if post_cutoff else "row_missing_in_shadow"},
            }
        elif not srow.get("is_new_transaction") or srow.get("history_status") != "new_transaction":
            branches["supervised_shadow"] = {
                "available": False, "raw_score": None, "score": None,
                "score_kind": "uncalibrated_supervised_score",
                "reason": {"code": "seen_in_supervised_training_or_evaluation"},
            }
        else:
            s_avail = srow.get("available") is True and srow.get("status") == "scored"
            s_val = float(srow["score"]) if s_avail and _is_finite_number(srow.get("score")) else None
            if s_val is None:
                s_avail = False
            branches["supervised_shadow"] = {
                "available": s_avail,
                "raw_score": s_val,
                "score": s_val,
                "score_kind": "uncalibrated_supervised_score",
                "model_id": shadow["model"].get("model_id") or shadow["model"].get("job_id"),
                "reason": None if s_avail else deepcopy(srow.get("issues") or {"code": srow.get("status", "unavailable")}),
            }

        episode_id = tx.get("episode_id") or tx.get("case_id") or tx.get("simultaneous_group_id")
        rows.append({
            "split": split_name,
            "tenant_id": scope.tenant_id,
            "company_id": company,
            "record_id": key[0],
            "revision": key[1],
            "case_id": rec["case_id"],
            "episode_id": episode_id,
            "event_at": rec["event_at"],
            "amount_vnd": rec["amount_vnd"],
            "tx_visible": not post_cutoff,
            "rule_state": "unavailable" if post_cutoff else rec["rule_state"],
            "rule_eval_completeness": "post_cutoff" if post_cutoff else rec["rule_eval_completeness"],
            "actionable_hit_rules": [] if post_cutoff else list(rec["actionable_hit_rules"]),
            "unavailable_rule_ids": list(rec["unavailable_rule_ids"]),
            "branches": branches,
        })

    if candidate_ids_filter is not None:
        kept_keys = {_row_key(r) for r in rows}
        groups = {gid: (set(members) & kept_keys) for gid, members in groups.items() if set(members) & kept_keys}
    return rows, groups


def parse_verified_labels(raw_labels: dict, *, scope_company_id: str) -> dict[tuple[str, int], dict]:
    """Validate verified-fraud/1.0.0 label mapping; forbid confirmed_risk coercion and cross-company labels."""
    if raw_labels.get("packets") is not None:
        merged = {}
        for pkt in raw_labels["packets"]:
            merged.update(parse_verified_labels(pkt, scope_company_id=scope_company_id))
        return merged

    if raw_labels.get("company_id") is not None:
        _require(raw_labels["company_id"] == scope_company_id, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                 f"Labels belong to {raw_labels['company_id']}, expected {scope_company_id}.")

    entries = raw_labels.get("records") if "records" in raw_labels else raw_labels.get("labels", {})
    parsed = {}
    items = entries.items() if isinstance(entries, dict) else [(e.get("key") or (e["record_id"], e["revision"]), e) for e in entries]
    for k, info in items:
        key = (str(k[0]), int(k[1])) if isinstance(k, (list, tuple)) else (str(k), 1)
        row_company = info.get("company_id") if isinstance(info, dict) else None
        if row_company is not None:
            _require(row_company == scope_company_id, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                     f"Verified label for {key} belongs to {row_company}, expected {scope_company_id}.")
        outcome = info.get("outcome") if isinstance(info, dict) else info
        if outcome in FORBIDDEN_VERIFIED_OUTCOMES:
            raise ValidationStudyError(
                "LABEL_COERCION_FORBIDDEN",
                f"Operational review outcome '{outcome}' cannot be used as verified_fraud label.",
                details={"key": list(key), "outcome": outcome},
            )
        _require(outcome in VALID_VERIFIED_OUTCOMES, "LABEL_COERCION_FORBIDDEN",
                 f"Unsupported verified label outcome '{outcome}' for {key}.")
        parsed[key] = {
            "outcome": outcome,
            "episode_id": info.get("episode_id") if isinstance(info, dict) else None,
            "source_target": info.get("target", "verified-fraud/1.0.0") if isinstance(info, dict) else "verified-fraud/1.0.0",
        }
    return parsed


def separate_review_feedback(review_data: dict | None, *, scope_company_id: str) -> dict[tuple[str, int], dict]:
    """Parse operational ReviewStore outcomes cleanly separated from verified fraud labels."""
    if not review_data:
        return {}
    if review_data.get("company_id") is not None:
        _require(review_data["company_id"] == scope_company_id, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                 f"Review records belong to {review_data['company_id']}, expected {scope_company_id}.")
    parsed = {}
    entries = review_data.get("reviews", review_data)
    if isinstance(entries, dict):
        for k, val in entries.items():
            if not isinstance(val, dict):
                continue
            key = (str(k[0]), int(k[1])) if isinstance(k, (list, tuple)) else (str(k), 1)
            if val.get("company_id") is not None:
                _require(val["company_id"] == scope_company_id, "TENANT_OR_COMPANY_ISOLATION_VIOLATION",
                         f"Review record {key} belongs to wrong company.")
            parsed[key] = dict(val)
    return parsed


def validate_split_boundaries(
    locked_plan: dict,
    rows_by_split: dict[str, list[dict]],
    groups_by_split: dict[str, dict[str, set[tuple[str, int]]]],
    *,
    history_keys: set[tuple[str, int]] | None = None,
) -> list[str]:
    """Enforce chronological windowing, disjoint record keys, and no episode leakage across splits."""
    plan = locked_plan["plan"]
    seen_keys: dict[tuple[str, int], str] = {k: "history_train" for k in (history_keys or set())}
    seen_episodes: dict[str, str] = {}
    limitations = []

    for split in ("detector_validation", "calibration_policy_validation", "sealed_future_test"):
        spec = plan["splits"][split]
        start_dt = utc(spec["start_at"])
        end_dt = utc(spec["end_at"])
        ep_cfg = spec["episode_grouping"]
        if not ep_cfg["episode_metadata_complete"]:
            limitations.append(ep_cfg["limitation_note"] or f"{split}: incomplete external episode metadata.")

        rows = rows_by_split.get(split, [])
        for row in rows:
            key = _row_key(row)
            _require(key not in seen_keys, "SPLIT_RECORD_OVERLAP",
                     f"Record {key} appears in both {seen_keys.get(key)} and {split}.",
                     key=list(key), first_split=seen_keys.get(key), second_split=split)
            seen_keys[key] = split

            ev_dt = utc(row["event_at"])
            _require(start_dt <= ev_dt <= end_dt, "SPLIT_CHRONOLOGY_INVALID",
                     f"Row {key} event_at {row['event_at']} outside {split} window [{spec['start_at']}, {spec['end_at']}].",
                     key=list(key), split=split)

            ep = row.get("episode_id")
            if ep:
                if ep in seen_episodes:
                    _require(seen_episodes[ep] == split, "EPISODE_SPLIT_LEAKAGE",
                             f"Episode {ep} spans splits {seen_episodes[ep]} and {split}.",
                             episode_id=ep, first_split=seen_episodes[ep], second_split=split)
                else:
                    seen_episodes[ep] = split

        for gid, members in (groups_by_split.get(split) or {}).items():
            for mk in members:
                if mk in seen_keys and seen_keys[mk] != split:
                    raise ValidationStudyError(
                        "EPISODE_SPLIT_LEAKAGE",
                        f"Linked group {gid} touches {seen_keys[mk]} and {split}.",
                        details={"group_id": gid, "key": list(mk), "other_split": seen_keys[mk], "split": split},
                    )
            if gid in seen_episodes:
                _require(seen_episodes[gid] == split, "EPISODE_SPLIT_LEAKAGE",
                         f"Simultaneous group {gid} spans splits {seen_episodes[gid]} and {split}.",
                         episode_id=gid)
            seen_episodes[gid] = split

    return sorted(set(limitations))


def _resolve_arm_ml_scores(
    rows: list[dict],
    arm: dict,
    references: dict[str, dict],
    ref_bindings_by_id: dict[str, dict],
    company_id: str,
) -> tuple[dict[tuple[str, int], dict], dict]:
    """Compute per-row priority/ML availability and scores for one candidate arm without raw mixing."""
    kind = arm["kind"]
    branches = arm["branches"]
    weights = arm.get("weights") or {}
    row_out = {}
    unavailable_counts: Counter[str] = Counter()

    if kind == "rules_only":
        for r in rows:
            key = _row_key(r)
            rb = r["branches"]["rules_35"]
            avail = rb["available"]
            if not avail:
                unavailable_counts[(rb.get("reason") or {}).get("code", "rules_unavailable")] += 1
            row_out[key] = {
                "available": avail, "ml_available": False, "ml_score": None,
                "priority_score": rb["score"] if avail else None,
                "reason": rb.get("reason"),
            }
        return row_out, dict(unavailable_counts)

    if kind in ("individual_detector", "rules_plus_ml"):
        target = branches[0] if kind == "individual_detector" else next(b for b in branches if b != "rules_35")
        raw_map = {_row_key(r): (r["branches"].get(target) or {}).get("raw_score") for r in rows}
        score_map = {_row_key(r): (r["branches"].get(target) or {}).get("score") for r in rows}
        if arm["uses_percentile_reference"] and arm["reference_ids"]:
            rid = arm["reference_ids"][0]
            rb = ref_bindings_by_id[rid]
            _require(rb["method_id"] == target, "EVALUATION_PLAN_PIN_MISMATCH", f"Reference {rid} method mismatch.")
            pct_map = transform_with_reference(references.get(rid), raw_map, expected_binding=rb, expected_company=company_id)
        else:
            pct_map = None

        for r in rows:
            key = _row_key(r)
            mb = r["branches"].get(target) or {"available": False, "reason": {"code": f"missing_{target}"}}
            rb = r["branches"]["rules_35"]
            ml_avail = mb.get("available") is True
            val = pct_map[key] if (ml_avail and pct_map is not None) else (score_map[key] if ml_avail else None)
            if ml_avail and not _is_finite_number(val):
                ml_avail, val = False, None
            branch_avail = ml_avail if kind == "individual_detector" else (rb["available"] and ml_avail)
            if not ml_avail:
                code = ((mb.get("reason") or [{}])[0].get("code")
                        if isinstance(mb.get("reason"), list) and mb.get("reason")
                        else (mb.get("reason") or {}).get("code", f"{target}_unavailable"))
                unavailable_counts[code] += 1
            elif kind == "rules_plus_ml" and not rb["available"]:
                unavailable_counts[(rb.get("reason") or {}).get("code", "rules_unavailable")] += 1
            row_out[key] = {
                "available": branch_avail,
                "ml_available": ml_avail,
                "ml_score": float(val) if ml_avail else None,
                "priority_score": float(val) if ml_avail else None,
                "reason": None if branch_avail else (mb.get("reason") or rb.get("reason")),
            }
        return row_out, dict(unavailable_counts)

    # Combined percentile_ensemble or rules_plus_percentile_ensemble
    ref_for_method = {}
    for rid in arm["reference_ids"]:
        rb = ref_bindings_by_id[rid]
        ref_for_method[rb["method_id"]] = (rid, rb)

    pct_by_branch = {}
    for b in weights:
        rid, rb = ref_for_method[b]
        raw_map = {}
        for r in rows:
            key = _row_key(r)
            br = r["branches"].get(b) or {}
            raw_map[key] = br.get("raw_score") if br.get("available") else None
        pct_by_branch[b] = transform_with_reference(
            references.get(rid), raw_map, expected_binding=rb, expected_company=company_id
        )

    for r in rows:
        key = _row_key(r)
        rb = r["branches"]["rules_35"]
        missing_b = [b for b in weights if pct_by_branch[b][key] is None]
        if missing_b:
            unavailable_counts[f"missing_branch:{'+'.join(sorted(missing_b))}"] += 1
            row_out[key] = {
                "available": False, "ml_available": False, "ml_score": None,
                "priority_score": None, "reason": {"code": "incomplete_ensemble_branches", "missing": sorted(missing_b)},
            }
            continue
        ens = sum(float(weights[b]) * float(pct_by_branch[b][key]) for b in weights)
        full_avail = True if kind == "percentile_ensemble" else rb["available"]
        if not full_avail:
            unavailable_counts[(rb.get("reason") or {}).get("code", "rules_unavailable")] += 1
        row_out[key] = {
            "available": full_avail,
            "ml_available": True,
            "ml_score": round(ens, 8),
            "priority_score": round(ens, 8),
            "reason": None if full_avail else rb.get("reason"),
        }
    return row_out, dict(unavailable_counts)


def _select_keys_for_arm(
    rows: list[dict],
    groups: dict[str, set[tuple[str, int]]],
    arm: dict,
    arm_scores: dict[tuple[str, int], dict],
    *,
    policy_kind: str = "rules_first_fill",
    budget: int = BUDGET,
    min_threshold: float | None = None,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], list[tuple[str, int]], list[list[tuple[str, int]]]]:
    """Run selection without mutating raw scores or masking unavailable rows as zero."""
    by_key = {_row_key(r): r for r in rows}

    if arm["kind"] == "individual_detector" or policy_kind == "priority_top_k":
        def score_of(r):
            s = arm_scores[_row_key(r)]
            return s["priority_score"] if s["available"] else None

        def raw_tiebreak(r):
            if len(arm["branches"]) == 1:
                raw_v = (r["branches"].get(arm["branches"][0]) or {}).get("raw_score")
                if _is_finite_number(raw_v):
                    return -float(raw_v)
            return 0.0

        eligible_rows = [r for r in rows if score_of(r) is not None and (min_threshold is None or float(score_of(r)) >= min_threshold)]
        ordered = sorted(
            eligible_rows,
            key=lambda r: (-float(score_of(r)), raw_tiebreak(r), utc(r["event_at"]), r["record_id"], int(r["revision"])),
        )
        chosen = [_row_key(r) for r in ordered[:budget]]
        return chosen, [], list(chosen), [[k] for k in chosen]

    synth = []
    for r in rows:
        key = _row_key(r)
        s = arm_scores[key]
        ml_ok = s["ml_available"] and arm["kind"] != "rules_only"
        if ml_ok and min_threshold is not None and float(s["ml_score"]) < min_threshold:
            ml_ok = False
        synth.append({
            "record_id": key[0],
            "revision": key[1],
            "event_at": r["event_at"],
            "rule_state": "alert" if r["branches"]["rules_35"]["available"] and r["rule_state"] == "alert" else "no_signal",
            "ml_available": ml_ok,
            "ml_score": float(s["ml_score"]) if ml_ok else None,
        })
    baseline, deferred, additions, components = select_records(synth, groups, budget=budget)
    if arm["kind"] == "rules_only":
        return baseline, deferred, [], components
    if min_threshold is not None and policy_kind == "threshold_gated_rules_first":
        additions = [
            k for k in additions
            if arm_scores[k]["ml_score"] is not None and float(arm_scores[k]["ml_score"]) >= min_threshold
        ]
    return baseline + additions, deferred, additions, components


def _episode_map(rows: list[dict], groups: dict[str, set[tuple[str, int]]]) -> dict[tuple[str, int], str]:
    """Build deterministic episode identifier map for deduplicated case accounting."""
    ep_of: dict[tuple[str, int], str] = {}
    for gid in sorted(groups):
        for k in groups[gid]:
            ep_of.setdefault(k, gid)
    for r in rows:
        k = _row_key(r)
        if k not in ep_of:
            ep_of[k] = str(r.get("episode_id") or f"tx:{k[0]}:{k[1]}")
    return ep_of


def _compute_arm_metrics(
    arm: dict,
    rows: list[dict],
    groups: dict[str, set[tuple[str, int]]],
    arm_scores: dict[tuple[str, int], dict],
    unavailable_reasons: dict,
    labels_map: dict[tuple[str, int], dict],
    reviews_map: dict[tuple[str, int], dict],
    baseline_rules_selected: list[tuple[str, int]],
    *,
    policy_kind: str = "rules_first_fill",
    budget: int = BUDGET,
    min_threshold: float | None = None,
    full_split_ground_truth: bool = False,
) -> dict:
    selected, deferred, added, _ = _select_keys_for_arm(
        rows, groups, arm, arm_scores, policy_kind=policy_kind, budget=budget, min_threshold=min_threshold
    )
    ep_of = _episode_map(rows, groups)
    selected_set = set(selected)
    baseline_set = set(baseline_rules_selected)

    avail_rows = sum(1 for r in rows if arm_scores[_row_key(r)]["available"])
    unavail_rows = len(rows) - avail_rows

    resolved_sel = [k for k in selected if labels_map.get(k, {}).get("outcome") in ("verified_fraud", "verified_non_fraud")]
    vf_sel = [k for k in resolved_sel if labels_map[k]["outcome"] == "verified_fraud"]
    vnf_sel = [k for k in resolved_sel if labels_map[k]["outcome"] == "verified_non_fraud"]
    unres_sel = [k for k in selected if k not in set(resolved_sel)]

    sel_cases = {ep_of[k] for k in selected}
    base_cases = {ep_of[k] for k in baseline_set}
    added_vf_keys = [k for k in selected if k not in baseline_set and k in set(vf_sel)]
    added_vf_cases = {ep_of[k] for k in added_vf_keys} - base_cases
    added_all_cases = sel_cases - base_cases

    # Separate operational review outcomes (NEVER mixed into verified_fraud numerator!)
    reviewed_sel = [reviews_map[k] for k in selected if k in reviews_map and reviews_map[k].get("feedback") is not None]
    conf_risk_n = sum(1 for rev in reviewed_sel if rev["feedback"].get("outcome") == "confirmed_risk")
    legit_rev_n = sum(1 for rev in reviewed_sel if rev["feedback"].get("outcome") == "legitimate")
    inc_rev_n = sum(1 for rev in reviewed_sel if rev["feedback"].get("outcome") == "inconclusive")
    recorded_secs = [
        float(rev["active_seconds"])
        for rev in reviewed_sel
        if _is_finite_number(rev.get("active_seconds")) and float(rev["active_seconds"]) > 0
    ]

    # Strict ground-truth scope gating for recall & PR-AUC
    all_keys = [_row_key(r) for r in rows]
    total_unres_in_split = sum(
        1 for k in all_keys if labels_map.get(k, {}).get("outcome") not in ("verified_fraud", "verified_non_fraud")
    )
    recall_val, pr_auc_val = None, None
    recall_reason = "incomplete_or_selective_ground_truth_in_split"
    if full_split_ground_truth and total_unres_in_split == 0 and all_keys:
        y_all = np.asarray([1 if labels_map[k]["outcome"] == "verified_fraud" else 0 for k in all_keys], dtype=int)
        if y_all.sum() > 0:
            y_pred_top = np.asarray([1 if k in selected_set else 0 for k in all_keys], dtype=int)
            recall_val = round(float(recall_score(y_all, y_pred_top)), 6)
            score_vals = [arm_scores[k]["priority_score"] for k in all_keys]
            if all(_is_finite_number(v) for v in score_vals) and arm["kind"] != "rules_only":
                y_score = np.asarray([float(v) for v in score_vals], dtype=float)
                if np.ptp(y_score) > 0:
                    pr_auc_val = round(float(average_precision_score(y_all, y_score)), 6)
                    recall_reason = "full_split_verified_ground_truth"
                else:
                    recall_reason = "recall_only_no_continuous_rank_spread"
            else:
                recall_reason = "recall_at_budget_full_split_gt; pr_auc_requires_continuous_score"

    inter = len(selected_set & baseline_set)
    union = len(selected_set | baseline_set)
    prec = (len(vf_sel) / len(resolved_sel)) if resolved_sel else None

    return {
        "arm_id": arm["arm_id"],
        "kind": arm["kind"],
        "branches": list(arm["branches"]),
        "complexity": arm["complexity"],
        "policy_id": policy_kind,
        "budget": budget,
        "availability": {
            "total_rows": len(rows),
            "available_rows": avail_rows,
            "unavailable_rows": unavail_rows,
            "availability_rate": round(avail_rows / len(rows), 6) if rows else 0.0,
            "unavailable_reasons": unavailable_reasons,
        },
        "selected": [list(k) for k in selected],
        "added_over_rules": [list(k) for k in added],
        "deferred_rule_alerts": [list(k) for k in deferred],
        "selected_count": len(selected),
        "unused_slots": max(0, budget - len(selected)),
        "cases_selected_count": len(sel_cases),
        "additional_tx_over_rules": len(selected_set - baseline_set),
        "additional_cases_over_rules": len(added_all_cases),
        "useful_verified_fraud_selected": len(vf_sel),
        "additional_useful_verified_tx_over_rules": len(added_vf_keys),
        "additional_useful_verified_cases_over_rules": len(added_vf_cases),
        "overlap_with_rules": {
            "intersection_count": inter,
            "jaccard": round(inter / union, 6) if union else 1.0,
        },
        "verified_label_metrics": {
            "resolved_count": len(resolved_sel),
            "verified_fraud_count": len(vf_sel),
            "verified_non_fraud_count": len(vnf_sel),
            "unresolved_count": len(unres_sel),
            "unresolved_rate": round(len(unres_sel) / len(selected), 6) if selected else None,
            "resolved_precision": {
                "value": round(prec, 6) if prec is not None else None,
                "numerator": len(vf_sel),
                "denominator": len(resolved_sel),
            },
            "recall_at_budget": recall_val,
            "pr_auc": pr_auc_val,
            "recall_pr_auc_scope": recall_reason,
        },
        "review_feedback_separate": {
            "reviewed_count": len(reviewed_sel),
            "confirmed_risk_count": conf_risk_n,
            "legitimate_count": legit_rev_n,
            "inconclusive_count": inc_rev_n,
            "confirmed_risk_coerced_to_fraud_label": False,
            "review_effort_seconds": {
                "recorded": bool(recorded_secs),
                "recorded_count": len(recorded_secs),
                "total_active_seconds": round(sum(recorded_secs), 3) if recorded_secs else None,
                "mean_active_seconds": round(sum(recorded_secs) / len(recorded_secs), 3) if recorded_secs else None,
            },
        },
    }


def _pairwise_overlap_matrix(arm_results: list[dict]) -> dict:
    matrix = {}
    for a in arm_results:
        sa = {tuple(k) for k in a["selected"]}
        matrix[a["arm_id"]] = {}
        for b in arm_results:
            sb = {tuple(k) for k in b["selected"]}
            u = len(sa | sb)
            matrix[a["arm_id"]][b["arm_id"]] = {
                "intersection": len(sa & sb),
                "jaccard": round(len(sa & sb) / u, 6) if u else 1.0,
            }
    return matrix


def evaluate_arms_on_split(
    plan: dict,
    rows: list[dict],
    groups: dict[str, set[tuple[str, int]]],
    labels_map: dict[tuple[str, int], dict],
    reviews_map: dict[tuple[str, int], dict],
    *,
    references: dict[str, dict] | None = None,
    include_policy_variants: bool = True,
) -> dict:
    """Measure individual detectors, rule baseline, small combinations, common-coverage, and policy variants."""
    ref_map = references or {}
    ref_bindings = {r["reference_id"]: r for r in plan["versions"]["reference_bindings"]}
    company = plan["scope"]["company_id"]
    locked_pol = plan["selection_policy"]["locked_policy"]
    budget = int(locked_pol["budget"])
    full_gt = bool(plan["labels"]["full_split_ground_truth"])

    # Deterministic baseline from rules_only first
    arm_scores_map = {}
    unavail_map = {}
    for arm in plan["candidates"]:
        scores, unavail = _resolve_arm_ml_scores(rows, arm, ref_map, ref_bindings, company)
        arm_scores_map[arm["arm_id"]] = scores
        unavail_map[arm["arm_id"]] = unavail

    rules_arm = next(a for a in plan["candidates"] if a["kind"] == "rules_only")
    baseline_rules, _, _, _ = _select_keys_for_arm(
        rows, groups, rules_arm, arm_scores_map[rules_arm["arm_id"]],
        policy_kind="rules_first_fill", budget=budget,
    )

    arm_results = [
        _compute_arm_metrics(
            arm, rows, groups, arm_scores_map[arm["arm_id"]], unavail_map[arm["arm_id"]],
            labels_map, reviews_map, baseline_rules,
            policy_kind="rules_first_fill", budget=budget, full_split_ground_truth=full_gt,
        )
        for arm in plan["candidates"]
    ]

    # Common coverage subset where ALL arms are simultaneously available
    common_rows = [
        r for r in rows
        if all(arm_scores_map[arm["arm_id"]][_row_key(r)]["available"] for arm in plan["candidates"])
    ]
    common_keys = {_row_key(r) for r in common_rows}
    common_groups = {gid: (set(m) & common_keys) for gid, m in groups.items() if set(m) & common_keys}
    common_baseline, _, _, _ = _select_keys_for_arm(
        common_rows, common_groups, rules_arm, arm_scores_map[rules_arm["arm_id"]],
        policy_kind="rules_first_fill", budget=budget,
    ) if common_rows else ([], [], [], [])
    common_results = [
        _compute_arm_metrics(
            arm, common_rows, common_groups, arm_scores_map[arm["arm_id"]], {},
            labels_map, reviews_map, common_baseline,
            policy_kind="rules_first_fill", budget=budget, full_split_ground_truth=full_gt,
        )
        for arm in plan["candidates"]
    ] if common_rows else []

    # Separate policy sensitivity analysis (never mixed into main locked-policy winner selection)
    policy_sensitivity = []
    if include_policy_variants:
        for var in plan["selection_policy"].get("policy_variants") or []:
            v_budget = int(var["budget"])
            v_kind = var["policy_kind"]
            v_thresh = var.get("min_priority_threshold")
            var_rows = []
            for arm in plan["candidates"]:
                res = _compute_arm_metrics(
                    arm, rows, groups, arm_scores_map[arm["arm_id"]], unavail_map[arm["arm_id"]],
                    labels_map, reviews_map, baseline_rules,
                    policy_kind=v_kind, budget=v_budget, min_threshold=v_thresh, full_split_ground_truth=full_gt,
                )
                locked_equiv = next(x for x in arm_results if x["arm_id"] == arm["arm_id"])
                lp = locked_equiv["verified_label_metrics"]["resolved_precision"]["value"]
                vp = res["verified_label_metrics"]["resolved_precision"]["value"]
                res["delta_vs_locked_policy"] = {
                    "vf_selected_delta": res["useful_verified_fraud_selected"] - locked_equiv["useful_verified_fraud_selected"],
                    "precision_delta": round(vp - lp, 6) if (vp is not None and lp is not None) else None,
                }
                var_rows.append(res)
            policy_sensitivity.append({
                "variant_id": var["variant_id"],
                "policy_kind": v_kind,
                "budget": v_budget,
                "min_priority_threshold": v_thresh,
                "arms": var_rows,
            })

    return {
        "arm_results": arm_results,
        "arm_scores_map": arm_scores_map,
        "common_coverage_subset": {
            "row_count": len(common_rows),
            "total_rows": len(rows),
            "arms": common_results,
        },
        "pairwise_overlap": _pairwise_overlap_matrix(arm_results),
        "policy_sensitivity": policy_sensitivity,
    }


def _objective_tuple(res: dict, metric_name: str) -> tuple[float, float, float]:
    vm = res["verified_label_metrics"]
    vf = float(res["useful_verified_fraud_selected"])
    prec = float(vm["resolved_precision"]["value"]) if vm["resolved_precision"]["value"] is not None else -1.0
    added = float(res["additional_useful_verified_cases_over_rules"])
    if metric_name == "verified_fraud_cases_selected":
        return (vf, prec, added)
    if metric_name == "useful_cases_added_over_rules":
        return (added, vf, prec)
    return (prec, vf, added)


def run_detector_validation(
    locked_plan: dict,
    val_rows: list[dict],
    val_groups: dict[str, set[tuple[str, int]]],
    val_labels: dict[tuple[str, int], dict],
    val_reviews: dict[tuple[str, int], dict] | None = None,
    *,
    references: dict[str, dict] | None = None,
) -> dict:
    """Compare standalone detectors, rules baseline, and small combinations strictly on detector_validation."""
    plan = locked_plan["plan"]

    def _run():
        evaluated = evaluate_arms_on_split(
            plan, val_rows, val_groups, val_labels, val_reviews or {}, references=references, include_policy_variants=True
        )
        obj = plan["selection_policy"]["selection_objective"]
        primary = obj["primary_metric"]
        min_gain = float(obj["min_incremental_gain"])
        require_pos = bool(obj["require_positive_marginal_value"])

        # Operational eligibility excludes individual_detector unless it IS rules_only, or rank all operational rules_* arms
        operational = [
            r for r in evaluated["arm_results"]
            if r["kind"] in ("rules_only", "rules_plus_ml", "rules_plus_percentile_ensemble")
            and r["availability"]["available_rows"] > 0
        ]
        _require(bool(operational), "VALIDATION_NO_ELIGIBLE_ARMS", "No operational arms available on detector_validation.")

        # Parsimony selection: start from rules_only, only promote higher complexity with strictly positive gain
        rules_res = next(r for r in operational if r["kind"] == "rules_only")
        best = rules_res
        best_score = _objective_tuple(best, primary)
        candidates_sorted = sorted(operational, key=lambda r: (r["complexity"], r["arm_id"]))

        trace = [{
            "step": "baseline",
            "arm_id": best["arm_id"],
            "complexity": best["complexity"],
            "objective": list(best_score),
            "decision": "initial_rules_baseline",
        }]
        for cand in candidates_sorted:
            if cand["arm_id"] == best["arm_id"]:
                continue
            cand_score = _objective_tuple(cand, primary)
            margin = cand_score[0] - best_score[0]
            if cand["complexity"] <= best["complexity"]:
                better = cand_score > best_score
            else:
                thresh = min_gain if require_pos else 0.0
                better = (margin > thresh) or (abs(margin) <= 1e-12 and cand_score > best_score and not require_pos)
            trace.append({
                "step": f"compare_{cand['arm_id']}",
                "arm_id": cand["arm_id"],
                "complexity": cand["complexity"],
                "objective": list(cand_score),
                "margin_over_current": round(margin, 6),
                "decision": "promoted_positive_incremental_value" if better else "rejected_no_incremental_gain_keep_simpler",
            })
            if better:
                best = cand
                best_score = cand_score

        arm_spec = next(a for a in plan["candidates"] if a["arm_id"] == best["arm_id"])
        selection_body = {
            "version": STUDY_VERSION,
            "plan_sha256": locked_plan["plan_sha256"],
            "selection_split": "detector_validation",
            "test_labels_accessed": False,
            "selected_arm_id": best["arm_id"],
            "selected_arm": deepcopy(arm_spec),
            "selection_trace": trace,
            "individual_and_ensemble_comparison": evaluated["arm_results"],
            "common_coverage_comparison": evaluated["common_coverage_subset"],
            "pairwise_overlap": evaluated["pairwise_overlap"],
            "policy_sensitivity": evaluated["policy_sensitivity"],
        }
        sel_sha = digest(canonical(selection_body))
        selection_body["selection_sha256"] = sel_sha
        return selection_body

    result, cost = _trace_cost(_run)
    result["execution_cost"] = cost
    return result


def evaluate_calibration_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    *,
    raw_probs: np.ndarray | None = None,
    n_bins: int = 5,
) -> dict:
    """Compute Brier score, log loss, ECE, and reliability bin table with optional uncalibrated delta."""
    probs = np.clip(np.asarray(y_prob, dtype=float), 1e-6, 1.0 - 1e-6)
    yt = np.asarray(y_true, dtype=int)
    brier = float(brier_score_loss(yt, probs))
    ll = float(log_loss(yt, probs, labels=[0, 1]))

    edges = np.linspace(0.0, 1.0, int(n_bins) + 1)
    ece = 0.0
    bins_out = []
    n = len(yt)
    for i in range(int(n_bins)):
        lo, hi = float(edges[i]), float(edges[i + 1])
        mask = (probs >= lo) & (probs <= hi if i == int(n_bins) - 1 else probs < hi)
        cnt = int(mask.sum())
        if cnt == 0:
            bins_out.append({"bin": i, "lower": round(lo, 4), "upper": round(hi, 4),
                             "count": 0, "mean_predicted_prob": None, "observed_fraud_rate": None, "abs_gap": None})
            continue
        mp = float(probs[mask].mean())
        obs = float(yt[mask].mean())
        gap = abs(mp - obs)
        ece += (cnt / n) * gap
        bins_out.append({
            "bin": i, "lower": round(lo, 4), "upper": round(hi, 4), "count": cnt,
            "mean_predicted_prob": round(mp, 6), "observed_fraud_rate": round(obs, 6), "abs_gap": round(gap, 6),
        })

    delta = None
    uncal_brier, uncal_ll = None, None
    if raw_probs is not None:
        r_arr = np.asarray(raw_probs, dtype=float)
        if np.all((r_arr >= 0.0) & (r_arr <= 1.0)):
            rc = np.clip(r_arr, 1e-6, 1.0 - 1e-6)
            uncal_brier = round(float(brier_score_loss(yt, rc)), 6)
            uncal_ll = round(float(log_loss(yt, rc, labels=[0, 1])), 6)
            delta = {
                "brier_improvement": round(uncal_brier - brier, 6),
                "log_loss_improvement": round(uncal_ll - ll, 6),
            }

    return {
        "count": n,
        "positive_count": int(yt.sum()),
        "negative_count": int(n - yt.sum()),
        "brier_score": round(brier, 6),
        "log_loss": round(ll, 6),
        "ece": round(ece, 6),
        "uncalibrated_brier_score": uncal_brier,
        "uncalibrated_log_loss": uncal_ll,
        "delta_vs_uncalibrated": delta,
        "reliability_bins": bins_out,
    }


def _fit_predict_calibrator_arrays(method: str, x_tr: np.ndarray, y_tr: np.ndarray, x_ev: np.ndarray, seed: int) -> tuple[np.ndarray, dict]:
    if method == "platt_logistic":
        clf = LogisticRegression(C=1.0, random_state=int(seed), solver="lbfgs", max_iter=1000)
        clf.fit(x_tr.reshape(-1, 1), y_tr)
        preds = clf.predict_proba(x_ev.reshape(-1, 1))[:, 1]
        params = {"coef": round(float(clf.coef_[0][0]), 10), "intercept": round(float(clf.intercept_[0]), 10)}
        return preds, params
    if method == "isotonic_regression":
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(x_tr, y_tr)
        preds = iso.predict(x_ev)
        params = {
            "x_thresholds": [round(float(v), 10) for v in iso.X_thresholds_],
            "y_thresholds": [round(float(v), 10) for v in iso.y_thresholds_],
        }
        return preds, params
    raise ValidationStudyError("CALIBRATION_METHOD_INVALID", f"Unsupported calibration method {method}.")


def apply_calibrator(calibrator: dict, raw_score: float | None) -> float | None:
    """Apply frozen verified calibrator; return None if calibration is blocked or raw score unavailable."""
    if calibrator.get("status") != "calibrated" or not _is_finite_number(raw_score):
        return None
    val = float(raw_score)
    method = calibrator["method"]
    params = calibrator["params"]
    if method == "platt_logistic":
        z = float(params["coef"]) * val + float(params["intercept"])
        prob = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
    elif method == "isotonic_regression":
        prob = float(np.interp(val, params["x_thresholds"], params["y_thresholds"]))
    else:
        return None
    return round(float(min(1.0 - 1e-6, max(1e-6, prob))), 6)


def fit_and_evaluate_calibration(
    locked_plan: dict,
    cal_rows: list[dict],
    cal_labels: dict[tuple[str, int], dict],
    cal_reviews: dict[tuple[str, int], dict] | None = None,
    *,
    references: dict[str, dict] | None = None,
) -> dict:
    """Fit probability calibrator ONLY on calibration_policy_validation verified labels; block if insufficient."""
    plan = locked_plan["plan"]
    cspec = plan["calibration_spec"]
    target = cspec["target_branch"]
    seed = int(plan["versions"]["random_seed"])
    min_tot = int(cspec["min_total_labels"])
    min_pos = int(cspec["min_positive_labels"])
    min_neg = int(cspec["min_negative_labels"])
    n_bins = int(cspec["ece_bins"])
    ref_bindings = {r["reference_id"]: r for r in plan["versions"]["reference_bindings"]}
    reviews = cal_reviews or {}

    def _run():
        # Extract target raw scores (NEVER using ReviewStore confirmed_risk!)
        usable_x, usable_y, usable_keys = [], [], []
        counts = {"total_rows": len(cal_rows), "verified_fraud": 0, "verified_non_fraud": 0,
                  "inconclusive": 0, "unlabeled": 0, "unavailable_score": 0,
                  "review_confirmed_risk_excluded": 0}
        target_arm = next((a for a in plan["candidates"] if a["arm_id"] == target), None)
        if target_arm is not None:
            scores_map, _ = _resolve_arm_ml_scores(cal_rows, target_arm, references or {}, ref_bindings, plan["scope"]["company_id"])
            score_getter = lambda r: (scores_map[_row_key(r)]["priority_score"] if scores_map[_row_key(r)]["available"] else None)
        else:
            score_getter = lambda r: ((r["branches"].get(target) or {}).get("score") if (r["branches"].get(target) or {}).get("available") else None)

        for r in cal_rows:
            k = _row_key(r)
            rev = reviews.get(k) or {}
            if (rev.get("feedback") or {}).get("outcome") == "confirmed_risk":
                counts["review_confirmed_risk_excluded"] += 1
            lbl = (cal_labels.get(k) or {}).get("outcome")
            if lbl is None:
                counts["unlabeled"] += 1
                continue
            if lbl == "inconclusive":
                counts["inconclusive"] += 1
                continue
            val = score_getter(r)
            if not _is_finite_number(val):
                counts["unavailable_score"] += 1
                continue
            y = 1 if lbl == "verified_fraud" else 0
            counts["verified_fraud" if y == 1 else "verified_non_fraud"] += 1
            usable_x.append(float(val))
            usable_y.append(y)
            usable_keys.append(k)

        pos_n, neg_n = counts["verified_fraud"], counts["verified_non_fraud"]
        tot_n = pos_n + neg_n
        if tot_n < min_tot or pos_n < min_pos or neg_n < min_neg:
            body = {
                "version": CALIBRATOR_VERSION,
                "plan_sha256": locked_plan["plan_sha256"],
                "fit_split": "calibration_policy_validation",
                "target_branch": target,
                "status": "insufficient_labels",
                "calibrated": False,
                "reason": (f"Need total>={min_tot}, pos>={min_pos}, neg>={min_neg}; "
                           f"got total={tot_n}, pos={pos_n}, neg={neg_n}."),
                "counts": counts,
                "method": None,
                "params": None,
                "oos_cv_evaluation": None,
            }
            body["calibrator_sha256"] = digest(canonical(body))
            return body

        x_arr = np.asarray(usable_x, dtype=float)
        y_arr = np.asarray(usable_y, dtype=int)
        if np.ptp(x_arr) <= 1e-12:
            body = {
                "version": CALIBRATOR_VERSION,
                "plan_sha256": locked_plan["plan_sha256"],
                "fit_split": "calibration_policy_validation",
                "target_branch": target,
                "status": "insufficient_labels",
                "calibrated": False,
                "reason": "Zero score variance on verified calibration subset.",
                "counts": counts, "method": None, "params": None, "oos_cv_evaluation": None,
            }
            body["calibrator_sha256"] = digest(canonical(body))
            return body

        n_splits = min(int(cspec["internal_eval_folds"]), pos_n, neg_n)
        cv_evals = {}
        if n_splits >= 2:
            skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
            for method in cspec["allowed_methods"]:
                oof_pred = np.zeros_like(x_arr, dtype=float)
                for tr_idx, ev_idx in skf.split(x_arr, y_arr):
                    oof_pred[ev_idx], _ = _fit_predict_calibrator_arrays(method, x_arr[tr_idx], y_arr[tr_idx], x_arr[ev_idx], seed)
                cv_evals[method] = evaluate_calibration_metrics(y_arr, oof_pred, raw_probs=x_arr, n_bins=n_bins)

        chosen_method = cspec["allowed_methods"][0]
        if cv_evals:
            chosen_method = min(
                cspec["allowed_methods"],
                key=lambda m: (cv_evals[m]["log_loss"], cv_evals[m]["brier_score"], 0 if m == "platt_logistic" else 1),
            )

        _, final_params = _fit_predict_calibrator_arrays(chosen_method, x_arr, y_arr, x_arr, seed)
        body = {
            "version": CALIBRATOR_VERSION,
            "plan_sha256": locked_plan["plan_sha256"],
            "fit_split": "calibration_policy_validation",
            "target_branch": target,
            "status": "calibrated",
            "calibrated": True,
            "reason": None,
            "counts": counts,
            "method": chosen_method,
            "params": final_params,
            "internal_oos_cv_folds": n_splits,
            "oos_cv_evaluation": cv_evals,
            "fitted_keys": [list(k) for k in usable_keys],
        }
        body["calibrator_sha256"] = digest(canonical(body))
        return body

    result, cost = _trace_cost(_run)
    result["execution_cost"] = cost
    return result


def _inject_fallback_fault(rows: list[dict], trigger: str) -> list[dict]:
    """Produce isolated fault-injected copy of split rows without mutating caller rows or emitting 0."""
    cloned = deepcopy(rows)
    if trigger == "missing_supervised_model":
        for r in cloned:
            r["branches"]["supervised_shadow"] = {
                "available": False, "raw_score": None, "score": None,
                "score_kind": "uncalibrated_supervised_score", "reason": {"code": "missing_supervised_model"},
            }
    elif trigger == "missing_unsupervised_model":
        for r in cloned:
            for mid in ("isolation_forest", "ecod", "robust_z", "autoencoder", "lof"):
                if mid in r["branches"]:
                    r["branches"][mid] = {
                        "available": False, "raw_score": None, "score": None,
                        "score_kind": "empirical_midrank", "reason": {"code": "missing_unsupervised_model"},
                    }
    elif trigger == "incompatible_contract":
        for r in cloned:
            for mid in ("isolation_forest", "ecod", "robust_z", "autoencoder", "lof", "supervised_shadow"):
                if mid in r["branches"]:
                    r["branches"][mid] = {
                        "available": False, "raw_score": None, "score": None,
                        "score_kind": "incompatible", "reason": {"code": "artifact_contract_incompatible"},
                    }
    elif trigger == "missing_feature_or_post_cutoff":
        # Corrupt every 3rd row as missing feature / late source; NEVER fill 0.
        for idx, r in enumerate(cloned):
            if idx % 3 == 0:
                for mid, br in r["branches"].items():
                    if mid != "rules_35":
                        br["available"] = False
                        br["raw_score"] = None
                        br["score"] = None
                        br["reason"] = {"code": "missing_required_features_or_post_cutoff"}
    elif trigger == "missing_reference_distribution":
        pass  # Handled explicitly by passing empty reference map during fallback scoring
    elif trigger == "partial_rule_source_gap":
        for r in cloned:
            rb = r["branches"]["rules_35"]
            if r["rule_state"] != "alert":
                r["rule_state"] = "partial_unavailable"
                r["rule_eval_completeness"] = "partial_rule_source_gap"
                rb["rule_state"] = "partial_unavailable"
                rb["unavailable_rule_ids"] = sorted(set(rb.get("unavailable_rule_ids") or []) | {"E2"})
    elif trigger == "all_branches_unavailable":
        for r in cloned:
            r["rule_state"] = "unavailable"
            r["rule_eval_completeness"] = "all_branches_unavailable"
            for mid, br in r["branches"].items():
                br["available"] = False
                br["raw_score"] = None
                br["score"] = None
                br["status"] = "unavailable"
                br["reason"] = {"code": "all_branches_unavailable"}
    return cloned


def evaluate_fallback_scenarios(
    locked_plan: dict,
    split_rows: list[dict],
    split_groups: dict[str, set[tuple[str, int]]],
    labels_map: dict[tuple[str, int], dict],
    reviews_map: dict[tuple[str, int], dict],
    *,
    references: dict[str, dict] | None = None,
) -> dict:
    """Validate explicit versioned fallback plans across missing model/source/contract/reference conditions."""
    plan = locked_plan["plan"]
    ref_bindings = {r["reference_id"]: r for r in plan["versions"]["reference_bindings"]}
    company = plan["scope"]["company_id"]
    budget = int(plan["selection_policy"]["locked_policy"]["budget"])
    full_gt = bool(plan["labels"]["full_split_ground_truth"])

    rules_arm = next(a for a in plan["candidates"] if a["kind"] == "rules_only")
    base_scores, _ = _resolve_arm_ml_scores(split_rows, rules_arm, references or {}, ref_bindings, company)
    baseline_rules, _, _, _ = _select_keys_for_arm(split_rows, split_groups, rules_arm, base_scores, budget=budget)

    scenarios_out = []
    for fb in plan["fallback_specs"]:
        trigger = fb["trigger_condition"]
        faulted_rows = _inject_fallback_fault(split_rows, trigger)
        used_refs = {} if trigger == "missing_reference_distribution" else (references or {})
        used_branches = fb["used_branches"]
        weights = fb.get("weights") or {}

        if fb["weight_policy"] == "unavailable":
            row_scores = {
                _row_key(r): {"available": False, "ml_available": False, "ml_score": None,
                              "priority_score": None, "status": "unavailable",
                              "reason": {"code": trigger}}
                for r in faulted_rows
            }
            unavail_reasons = {trigger: len(faulted_rows)}
            synth_arm = {"arm_id": fb["fallback_config_id"], "kind": "rules_only", "branches": [], "complexity": 0}
        elif len(used_branches) == 1 and used_branches[0] == "rules_35":
            synth_arm = {"arm_id": fb["fallback_config_id"], "kind": "rules_only", "branches": ["rules_35"], "complexity": 1}
            row_scores, unavail_reasons = _resolve_arm_ml_scores(faulted_rows, synth_arm, used_refs, ref_bindings, company)
        elif len(used_branches) == 1:
            synth_arm = {
                "arm_id": fb["fallback_config_id"], "kind": "individual_detector",
                "branches": used_branches, "uses_percentile_reference": False, "reference_ids": [], "complexity": 1,
            }
            row_scores, unavail_reasons = _resolve_arm_ml_scores(faulted_rows, synth_arm, used_refs, ref_bindings, company)
        elif "rules_35" in used_branches and len(used_branches) == 2 and not weights:
            ml_b = next(b for b in used_branches if b != "rules_35")
            synth_arm = {
                "arm_id": fb["fallback_config_id"], "kind": "rules_plus_ml",
                "branches": used_branches, "uses_percentile_reference": False, "reference_ids": [], "complexity": 2,
            }
            row_scores, unavail_reasons = _resolve_arm_ml_scores(faulted_rows, synth_arm, used_refs, ref_bindings, company)
        else:
            need_methods = set(weights)
            r_ids = [r["reference_id"] for r in plan["versions"]["reference_bindings"] if r["method_id"] in need_methods]
            kind = "rules_plus_percentile_ensemble" if "rules_35" in used_branches else "percentile_ensemble"
            synth_arm = {
                "arm_id": fb["fallback_config_id"], "kind": kind, "branches": used_branches,
                "weights": weights, "uses_percentile_reference": bool(weights),
                "reference_ids": r_ids, "complexity": len(used_branches),
            }
            row_scores, unavail_reasons = _resolve_arm_ml_scores(faulted_rows, synth_arm, used_refs, ref_bindings, company)

        metrics = (
            {
                "selected": [], "selected_count": 0, "unused_slots": budget,
                "availability": {"total_rows": len(faulted_rows), "available_rows": 0,
                                 "unavailable_rows": len(faulted_rows), "availability_rate": 0.0,
                                 "unavailable_reasons": unavail_reasons},
                "verified_label_metrics": {"resolved_count": 0, "verified_fraud_count": 0,
                                           "resolved_precision": {"value": None, "numerator": 0, "denominator": 0}},
                "score_sample_is_null": all(v["priority_score"] is None for v in row_scores.values()),
            }
            if fb["weight_policy"] == "unavailable"
            else _compute_arm_metrics(
                synth_arm, faulted_rows, split_groups, row_scores, unavail_reasons,
                labels_map, reviews_map, baseline_rules, budget=budget, full_split_ground_truth=full_gt,
            )
        )

        cfg_payload = {
            "fallback_config_id": fb["fallback_config_id"],
            "config_version": fb["config_version"],
            "trigger_condition": trigger,
            "is_full_ensemble": False,
            "silent_weight_redistribution": False,
            "weight_policy": fb["weight_policy"],
            "used_branches": used_branches,
            "missing_or_ineligible_branches": fb["missing_or_ineligible_branches"],
            "weights": _safe_float_dict(weights) if weights else None,
        }
        cfg_sha = digest(canonical(cfg_payload))
        scenarios_out.append({
            **cfg_payload,
            "config_sha256": cfg_sha,
            "coverage": metrics["availability"],
            "effectiveness": {
                "selected_count": metrics["selected_count"],
                "resolved_count": metrics["verified_label_metrics"]["resolved_count"],
                "verified_fraud_selected": metrics["verified_label_metrics"]["verified_fraud_count"],
                "resolved_precision": metrics["verified_label_metrics"]["resolved_precision"],
                "null_score_when_unavailable": all(
                    v["priority_score"] is None for v in row_scores.values() if not v["available"]
                ),
            },
        })

    out = {
        "version": FALLBACK_PLAN_VERSION,
        "plan_sha256": locked_plan["plan_sha256"],
        "scenarios": scenarios_out,
    }
    out["fallback_plan_sha256"] = digest(canonical(out))
    return out


def _score_sealed_calibration(
    calibrator: dict,
    plan: dict,
    test_rows: list[dict],
    test_labels: dict[tuple[str, int], dict],
    *,
    references: dict[str, dict] | None = None,
) -> dict:
    """Evaluate frozen calibrator out-of-sample on sealed_future_test without altering calibrator."""
    target = calibrator["target_branch"]
    ref_bindings = {r["reference_id"]: r for r in plan["versions"]["reference_bindings"]}
    company = plan["scope"]["company_id"]
    target_arm = next((a for a in plan["candidates"] if a["arm_id"] == target), None)
    if target_arm is not None:
        scores_map, _ = _resolve_arm_ml_scores(test_rows, target_arm, references or {}, ref_bindings, company)
        score_getter = lambda r: (scores_map[_row_key(r)]["priority_score"] if scores_map[_row_key(r)]["available"] else None)
    else:
        score_getter = lambda r: ((r["branches"].get(target) or {}).get("score") if (r["branches"].get(target) or {}).get("available") else None)

    per_row = []
    yt_eval, yp_eval, raw_eval = [], [], []
    for r in test_rows:
        k = _row_key(r)
        raw_val = score_getter(r)
        cal_prob = apply_calibrator(calibrator, raw_val)
        per_row.append({
            "record_id": k[0], "revision": k[1],
            "priority_score": round(float(raw_val), 6) if _is_finite_number(raw_val) else None,
            "calibrated_fraud_probability": cal_prob,
            "calibration_status": calibrator["status"],
        })
        lbl = (test_labels.get(k) or {}).get("outcome")
        if calibrator["status"] == "calibrated" and cal_prob is not None and lbl in ("verified_fraud", "verified_non_fraud"):
            yt_eval.append(1 if lbl == "verified_fraud" else 0)
            yp_eval.append(cal_prob)
            raw_eval.append(float(raw_val))

    if calibrator["status"] != "calibrated":
        return {"status": calibrator["status"], "calibrated": False,
                "sealed_test_metrics": None, "row_predictions": per_row}
    if len(yt_eval) < 4 or len(set(yt_eval)) < 2:
        return {"status": "insufficient_sealed_test_labels_for_eval", "calibrated": True,
                "sealed_test_metrics": None, "row_predictions": per_row}
    metrics = evaluate_calibration_metrics(
        np.asarray(yt_eval, dtype=int), np.asarray(yp_eval, dtype=float),
        raw_probs=np.asarray(raw_eval, dtype=float), n_bins=int(plan["calibration_spec"]["ece_bins"]),
    )
    return {"status": "evaluated", "calibrated": True, "sealed_test_metrics": metrics, "row_predictions": per_row}


def run_validation_study(
    plan: dict,
    *,
    snapshot_manifests: dict[str, dict],
    model_artifacts: dict[str, dict],
    reference_artifacts: dict[str, dict],
    split_bundles: dict[str, dict],
    label_packets: dict[str, dict] | None = None,
    execution_costs_extra: dict | None = None,
) -> dict:
    """Execute end-to-end locked validation study across all 4 splits for a single enterprise."""
    # Step 1: Lock plan strictly BEFORE touching sealed_future_test verified labels
    locked_plan = lock_evaluation_plan(
        plan,
        snapshot_manifests=snapshot_manifests,
        model_artifacts=model_artifacts,
        reference_artifacts=reference_artifacts,
        label_packets=label_packets,
    )
    scope_company = plan["scope"]["company_id"]

    # Step 2: Validate split boundaries & episode containment across splits
    rows_by_split = {s: split_bundles[s]["rows"] for s in ("detector_validation", "calibration_policy_validation", "sealed_future_test")}
    groups_by_split = {s: split_bundles[s]["groups"] for s in ("detector_validation", "calibration_policy_validation", "sealed_future_test")}
    history_keys = set(split_bundles.get("history_train", {}).get("keys") or set())
    episode_limitations = validate_split_boundaries(locked_plan, rows_by_split, groups_by_split, history_keys=history_keys)

    # Step 3 (Blinded): Detector validation using ONLY detector_validation verified labels
    val_labels = parse_verified_labels(split_bundles["detector_validation"]["verified_labels"], scope_company_id=scope_company)
    val_reviews = separate_review_feedback(split_bundles["detector_validation"].get("reviews"), scope_company_id=scope_company)
    selection = run_detector_validation(
        locked_plan, rows_by_split["detector_validation"], groups_by_split["detector_validation"],
        val_labels, val_reviews, references=reference_artifacts,
    )

    # Step 4 (Blinded): Calibration using ONLY calibration_policy_validation verified labels
    cal_labels = parse_verified_labels(split_bundles["calibration_policy_validation"]["verified_labels"], scope_company_id=scope_company)
    cal_reviews = separate_review_feedback(split_bundles["calibration_policy_validation"].get("reviews"), scope_company_id=scope_company)
    calibrator = fit_and_evaluate_calibration(
        locked_plan, rows_by_split["calibration_policy_validation"],
        cal_labels, cal_reviews, references=reference_artifacts,
    )

    # Mint immutable pre-test lock over configuration + calibrator + fallback specs
    pre_test_lock = {
        "plan_sha256": locked_plan["plan_sha256"],
        "selection_sha256": selection["selection_sha256"],
        "selected_arm_id": selection["selected_arm_id"],
        "calibrator_sha256": calibrator["calibrator_sha256"],
        "calibrator_status": calibrator["status"],
        "fallback_specs_sha256": digest(canonical(plan["fallback_specs"])),
    }
    pre_test_lock_sha256 = digest(canonical(pre_test_lock))

    # Step 5: Unseal sealed_future_test AFTER pre_test_lock and measure final comparison, calibration & fallback
    test_labels = parse_verified_labels(split_bundles["sealed_future_test"]["verified_labels"], scope_company_id=scope_company)
    test_reviews = separate_review_feedback(split_bundles["sealed_future_test"].get("reviews"), scope_company_id=scope_company)

    sealed_eval, eval_cost = _trace_cost(
        evaluate_arms_on_split, plan, rows_by_split["sealed_future_test"], groups_by_split["sealed_future_test"],
        test_labels, test_reviews, references=reference_artifacts, include_policy_variants=True,
    )
    sealed_cal_eval = _score_sealed_calibration(calibrator, plan, rows_by_split["sealed_future_test"], test_labels, references=reference_artifacts)
    fallback_eval, fb_cost = _trace_cost(
        evaluate_fallback_scenarios, locked_plan, rows_by_split["sealed_future_test"],
        groups_by_split["sealed_future_test"], test_labels, test_reviews, references=reference_artifacts,
    )

    # Assemble candidate shadow artifact & deterministic comparison report
    candidate_shadow_artifact = {
        "version": CANDIDATE_SHADOW_VERSION,
        "scope": deepcopy(plan["scope"]),
        "plan_id": locked_plan["plan_id"],
        "plan_sha256": locked_plan["plan_sha256"],
        "pre_test_lock_sha256": pre_test_lock_sha256,
        "selected_arm": deepcopy(selection["selected_arm"]),
        "calibrator_summary": {
            "calibrator_sha256": calibrator["calibrator_sha256"],
            "status": calibrator["status"],
            "method": calibrator["method"],
            "target_branch": calibrator["target_branch"],
            "counts": deepcopy(calibrator["counts"]),
        },
        "fallback_plan_sha256": fallback_eval["fallback_plan_sha256"],
        "governance": {
            "candidate_shadow_only": True,
            "production_approved": False,
            "active_model_replaced": False,
            "operational_queue_changed": False,
            "execution_location": "enterprise_local_only",
            "cloud_plaintext_sent": False,
        },
    }
    candidate_shadow_artifact["candidate_artifact_sha256"] = digest(canonical(candidate_shadow_artifact))

    deterministic_report = {
        "version": STUDY_VERSION,
        "scope": deepcopy(plan["scope"]),
        "plan_lock": {
            "plan_id": locked_plan["plan_id"],
            "plan_sha256": locked_plan["plan_sha256"],
            "locked_before_test_inspection": True,
            "test_labels_inspected_at_lock": False,
            "pre_test_lock_sha256": pre_test_lock_sha256,
        },
        "data_splits": {
            s: {"row_count": len(rows_by_split[s]), "as_of": plan["splits"][s]["as_of"]}
            for s in ("detector_validation", "calibration_policy_validation", "sealed_future_test")
        },
        "episode_limitations": episode_limitations,
        "detector_validation": {k: v for k, v in selection.items() if k != "execution_cost"},
        "calibration_validation": {
            "calibrator": {k: v for k, v in calibrator.items() if k != "execution_cost"},
            "sealed_future_test_calibration": sealed_cal_eval,
        },
        "sealed_future_test": {
            "arm_results": sealed_eval["arm_results"],
            "common_coverage_subset": sealed_eval["common_coverage_subset"],
            "pairwise_overlap": sealed_eval["pairwise_overlap"],
            "policy_sensitivity": sealed_eval["policy_sensitivity"],
            "selected_arm_summary": next(
                r for r in sealed_eval["arm_results"] if r["arm_id"] == selection["selected_arm_id"]
            ),
        },
        "fallback_validation": fallback_eval,
        "open_quality_gates": deepcopy(plan["metrics_and_criteria"]["quality_gates"]),
        "governance": deepcopy(plan["governance"]),
        "candidate_shadow_artifact": candidate_shadow_artifact,
        "synthetic_data_disclosure": plan["governance"].get("synthetic_data_disclosure"),
    }
    study_sha256 = digest(canonical(deterministic_report))
    return {
        **deterministic_report,
        "study_result_sha256": study_sha256,
        "execution_costs": {
            **(execution_costs_extra or {}),
            "detector_validation": selection["execution_cost"],
            "calibration_validation": calibrator["execution_cost"],
            "sealed_test_evaluation": eval_cost,
            "fallback_validation": fb_cost,
        },
    }
