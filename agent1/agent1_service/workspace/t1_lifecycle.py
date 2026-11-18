"""Tenant-scoped T1 registry and periodic updates with delayed paired audits."""

from __future__ import annotations

import base64
import hashlib
import pickle
import uuid
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from agent1.adaptive.data import fingerprint
from agent1.adaptive.bundle_metadata import serving_manifest
from agent1.adaptive.methods import train
from agent1.adaptive.payment_coverage import (
    attest,
    attest_reconciled_books,
    check_reconciled_completeness,
)
from agent1.adaptive.t1_catalog import GlobalCatalog
from agent1.adaptive.t1_data import (
    score_audit_snapshot,
    snapshot_for_audit,
    visible_data,
)
from agent1.adaptive.t1_update import (
    VERSION,
    UpdatePolicy,
    improves,
    valid_incumbent,
)


def now():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))


def _challenger_metadata(record):
    fields = (
        "id",
        "origin",
        "status",
        "baseline_version",
        "challenger_version",
        "created_at",
        "evaluated_asof",
        "evaluation",
        "policy",
    )
    return {k: record[k] for k in fields if k in record}


def confirm_reconciled_books(
    store,
    firm,
    reconciled_through,
    *,
    start_date=None,
    periods=None,
    policy=None,
    strict=False,
):
    """Confirm reconciled historical ledger periods honestly with known_at = today.

    Validates period continuity and resolved 91-day cohort counts, persists the
    honest confirmation record to `company_payment_coverage` (unless `strict=True`
    and missing periods/cohorts exist), and returns Vietnamese diagnostics.
    """
    policy = policy or UpdatePolicy()
    confirmation = now().isoformat()
    today_iso = str(now().date())
    if str(pd.Timestamp(reconciled_through).date()) > today_iso:
        raise ValueError("Không xác nhận đối soát sổ sách cho ngày tương lai")
    with store.lock:
        data = current_data(store, firm)
        diagnostics = check_reconciled_completeness(
            data,
            reconciled_through,
            confirmation_date=today_iso,
            start_date=start_date,
            periods=periods,
            minimum_fit_snapshots=policy.minimum_fit_snapshots,
            minimum_fit_invoices=policy.minimum_fit_invoices,
            minimum_validation_snapshots=policy.minimum_validation_snapshots,
            minimum_audit_snapshots=policy.minimum_audit_snapshots,
            validation_offsets_days=policy.validation_offsets_days,
            stride_days=policy.stride_days,
            lookback_days=policy.lookback_days,
        )
        if strict and not diagnostics["ok"]:
            raise ValueError(diagnostics["summary_vi"])
        if diagnostics["missing_periods"]:
            return dict(diagnostics, recorded=False, coverage=None)
        coverage = dict(
            id=uuid.uuid4().hex,
            created_at=confirmation,
            **attest_reconciled_books(
                data,
                reconciled_through,
                today_iso,
                start_date=diagnostics["start_date"],
                periods=periods,
            ),
        )
        with store.connection:
            store.connection.execute("BEGIN IMMEDIATE")
            store.put(firm, "company_payment_coverage", [coverage])
    return dict(diagnostics, recorded=True, coverage=coverage)


def update_status(store, firm):
    """Business-facing lifecycle state without snapshots or model artifacts."""
    today = pd.Timestamp(now().date())
    with store.lock:
        state = store.one(firm, "company_t1_update_state", "current")
        runs = sorted(
            store.get(firm, "company_t1_update_runs"),
            key=lambda r: r.get("created_at", ""),
            reverse=True,
        )[:100]
        ids = set(store.ids(firm, "company_t1_challengers"))
        indexed = {r["id"]: r for r in store.get(firm, "company_t1_challenger_index")}
        # Backfill old stores once, one snapshot at a time. Subsequent polls
        # read only compact metadata; the lifecycle writer keeps it atomic.
        if ids - indexed.keys():
            with store.connection:
                store.connection.execute("BEGIN IMMEDIATE")
                # A CLI cycle may have committed since the first read. Never
                # overwrite its newer status with a stale migration snapshot.
                ids = set(store.ids(firm, "company_t1_challengers"))
                indexed = {
                    r["id"]: r for r in store.get(firm, "company_t1_challenger_index")
                }
                missing = []
                for identifier in sorted(ids - indexed.keys()):
                    record = store.one(firm, "company_t1_challengers", identifier)
                    if record:
                        row = _challenger_metadata(record)
                        indexed[identifier] = row
                        missing.append(row)
                if missing:
                    store.put(firm, "company_t1_challenger_index", missing)
        records = [row for key, row in indexed.items() if key in ids]
    challengers = []
    for record in records:
        row = dict(record)
        maturity = (
            pd.Timestamp(record["origin"]) + pd.Timedelta(days=91)
            if record.get("origin")
            else None
        )
        evaluation = record.get("evaluation") or {}
        status = record["status"]
        if status == "pending":
            status = (
                "origin_not_recorded"
                if maturity is None
                else "waiting_for_91_days"
                if today < maturity
                else "insufficient_eligible_outcomes"
                if evaluation.get("status") == "insufficient_eligible_outcomes"
                else "ready_for_audit"
            )
        row.update(
            matures_on=str(maturity.date()) if maturity is not None else None,
            display_status=status,
            eligible_rows=evaluation.get("rows", evaluation.get("n")),
            minimum_rows=(record.get("policy") or {}).get(
                "minimum_audit_snapshots", 20
            ),
        )
        challengers.append(row)
    challengers.sort(key=lambda r: (r.get("origin", ""), r["id"]), reverse=True)
    return dict(
        state=state,
        runs=runs,
        challengers=challengers,
        pending_count=sum(r["status"] == "pending" for r in challengers),
        asof=str(today.date()),
        due=not state or today >= pd.Timestamp(state["next_due"]),
    )


def encode(bundle):
    payload = pickle.dumps(bundle, protocol=pickle.HIGHEST_PROTOCOL)
    return {
        "artifact": base64.b64encode(payload).decode(),
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
    }


def decode(record):
    payload = base64.b64decode(record["artifact"], validate=True)
    if (
        record.get("artifact_sha256")
        and hashlib.sha256(payload).hexdigest() != record["artifact_sha256"]
    ):
        raise ValueError("Artifact T1 của doanh nghiệp đã thay đổi")
    return pickle.loads(payload)  # Internally produced encrypted records only.


def current_data(store, firm):
    pointers = store.get(firm, "company_dataset_active")
    if not pointers:
        return {"invoices": [], "payments": [], "outflows": []}
    record = store.one(firm, "company_datasets", pointers[0]["version"])
    if not record:
        raise ValueError("Không tìm thấy snapshot dữ liệu của doanh nghiệp")
    data = dict(record["data"])
    data["payment_coverage"] = [
        *data.get("payment_coverage", []),
        *store.get(firm, "company_payment_coverage"),
    ]
    return data


def with_promotion_evidence(store, firm, row):
    """Recover pre-fix metadata from its accepted frozen challenger, read-only."""
    if row.get("promotion_audit"):
        return row
    identifier = row.get("prospective_audit_id")
    if (
        not identifier
        and row.get("promotion_status") == "accepted_prospective_audit"
        and row.get("id")
    ):
        decision = store.one(firm, "company_t1_update_runs", row["id"]) or {}
        identifier = decision.get("prospective_audit_id")
    if not identifier:
        return row
    challenger = (
        store.one(firm, "company_t1_challenger_index", identifier)
        or store.one(firm, "company_t1_challengers", identifier)
        or {}
    )
    evaluation = challenger.get("evaluation") or {}
    if (
        challenger.get("status") != "accepted"
        or evaluation.get("status") != "scored"
        or challenger.get("challenger_version") != row.get("t1_version")
    ):
        return row
    audit = dict(
        evaluation,
        accepted=True,
        kind="prospective",
        challenger_id=identifier,
        evaluated_asof=challenger["evaluated_asof"],
        serving_version=row["t1_version"],
    )
    result = dict(
        row,
        promotion_audit=audit,
        prospective_audit_id=identifier,
        candidate_update_audit=row.get("candidate_update_audit", row.get("audit")),
    )
    if row.get("promotion_status") == "accepted_prospective_audit":
        result["audit"] = deepcopy(audit)
    return result


def load_active(store, firm, cutoff, *, catalog=None):
    catalog = catalog or GlobalCatalog()
    active = store.one(firm, "company_model_active", "active")
    record = store.one(firm, "company_models", active["version"]) if active else None
    bundle = None
    if record:
        if record.get("algorithm_version") != VERSION:
            result = catalog.default_bundle(cutoff)
            result["legacy_t1_ignored"] = True
            return result, record
        weight = store.one(firm, "company_weights", record["artifact_id"])
        if not weight:
            raise ValueError("Thiếu artifact của phiên bản đang phục vụ")
        bundle = decode(weight)
    result = with_promotion_evidence(
        store, firm, valid_incumbent(bundle, cutoff, catalog)
    )
    return result, record


def metadata(bundle, identifier, created_at):
    fields = (
        "asof",
        "update_asof",
        "dataset_hash",
        "audit",
        "promotion_audit",
        "candidate_update_audit",
        "prospective_audit_id",
        "validation_n",
        "train_n",
        "algorithm_version",
        "limitation",
        "windows",
        "code_hash",
        "dependencies",
        "t1_version",
        "t1_parameter_asof",
        "partial_version",
        "adapter_version",
        "partial_selection",
        "locked_spec",
        "catalog_sha256",
        "promotion_status",
        "policy",
        "fit_data",
        "final_data",
        "legacy_t1_ignored",
        "serving_manifest",
        "update_period",
    )
    return dict(
        {k: bundle.get(k) for k in fields},
        id=identifier,
        artifact_id=identifier,
        created_at=created_at,
        operating_ready=bool(bundle.get("operating")),
        partial_fitted_through=bundle["partial"].fitted_through,
        synthetic_sandbox=bool(bundle.get("synthetic_sandbox")),
    )


def run_cycle(
    store,
    firm,
    cutoff,
    *,
    payments_complete,
    reconciled_through=None,
    confirmed_periods=None,
    policy=None,
    catalog=None,
    force=False,
    progress=lambda _: None,
    trainer=None,
):
    """Train every policy interval; replace only on a causal historical/live audit.

    Every live challenger is frozen with paired predictions at its creation
    origin. A later job scores one FIFO challenger after 91 days, against the
    same still-active incumbent. Retrospective snapshots cannot promote.
    """
    if not payments_complete and reconciled_through is None:
        raise ValueError("Cần xác nhận dữ liệu thanh toán đầy đủ đến ngày cập nhật")
    policy, catalog = policy or UpdatePolicy(), catalog or GlobalCatalog()
    T = pd.Timestamp(cutoff).normalize()
    created = now().isoformat()
    if T.date() > now().date():
        raise ValueError("Không tạo chu kỳ T1 cho ngày tương lai")
    if reconciled_through is not None and pd.Timestamp(reconciled_through).date() > T.date():
        raise ValueError("Ngày chốt đối soát lịch sử không được vượt quá ngày chu kỳ cập nhật")
    state = store.one(firm, "company_t1_update_state", "current") or {}
    if state and T < pd.Timestamp(state["last_cycle_asof"]):
        raise ValueError("Ngày cập nhật T1 không được đi lùi")
    if state and not force and T < pd.Timestamp(state["next_due"]):
        return {
            "status": "not_due",
            "next_due": state["next_due"],
            "last_cycle_asof": state["last_cycle_asof"],
        }
    data = current_data(store, firm)
    snapshot_hash = fingerprint(visible_data(data, T))
    if reconciled_through is not None and confirmed_periods is not None:
        completeness = check_reconciled_completeness(
            data,
            reconciled_through,
            confirmation_date=created[:10],
            periods=confirmed_periods,
            minimum_fit_snapshots=policy.minimum_fit_snapshots,
            minimum_fit_invoices=policy.minimum_fit_invoices,
            minimum_validation_snapshots=policy.minimum_validation_snapshots,
            minimum_audit_snapshots=policy.minimum_audit_snapshots,
            validation_offsets_days=policy.validation_offsets_days,
            stride_days=policy.stride_days,
            lookback_days=policy.lookback_days,
        )
        if completeness["missing_periods"]:
            raise ValueError(completeness["summary_vi"])
    coverage = dict(
        id=uuid.uuid4().hex,
        **attest(
            data,
            T,
            created,
            reconciled_through=reconciled_through,
            periods=confirmed_periods,
        ),
    )
    data = dict(data, payment_coverage=[*data.get("payment_coverage", []), coverage])
    active_pointer = store.one(firm, "company_model_active", "active")
    baseline, _ = load_active(store, firm, T, catalog=catalog)
    baseline_version = baseline["t1_version"]
    pending = sorted(
        store.get(firm, "company_t1_challengers"), key=lambda r: (r["origin"], r["id"])
    )
    audit_updates = []
    promoted_live = None
    for record in pending:
        if record["status"] != "pending":
            continue
        if record["baseline_version"] != baseline_version:
            audit_updates.append(dict(record, status="stale_incumbent"))
            continue
        if T < pd.Timestamp(record["origin"]) + pd.Timedelta(days=91):
            continue
        locked_policy = UpdatePolicy(**record["policy"])
        result = score_audit_snapshot(
            record["snapshot"],
            data,
            T,
            minimum_rows=locked_policy.minimum_audit_snapshots,
        )
        if result["status"] != "scored":
            audit_updates.append(
                dict(
                    record,
                    status=(
                        "pending"
                        if result["status"] == "insufficient_eligible_outcomes"
                        else result["status"]
                    ),
                    evaluation=result,
                )
            )
            continue
        accepted = improves(result["challenger"], result["baseline"], locked_policy)
        audit_updates.append(
            dict(
                record,
                status="accepted" if accepted else "rejected",
                evaluation=result,
                evaluated_asof=str(T.date()),
            )
        )
        if accepted:
            weight = store.one(
                firm, "company_t1_challenger_weights", record["artifact_id"]
            )
            if not weight:
                raise ValueError("Thiếu artifact ứng viên đã chấm")
            baseline = decode(weight)
            if baseline.get("t1_version") != record["challenger_version"]:
                raise ValueError("Artifact không khớp ứng viên đã chấm")
            # The choice is available today even though its parameters were
            # fitted at the old origin. Never backdate the selection decision.
            baseline["asof"] = str(T.date())
            baseline["promotion_status"] = "accepted_prospective_audit"
            baseline["promotion_audit"] = dict(
                result,
                accepted=True,
                kind="prospective",
                challenger_id=record["id"],
                evaluated_asof=str(T.date()),
                serving_version=record["challenger_version"],
            )
            baseline["audit"] = deepcopy(baseline["promotion_audit"])
            baseline["serving_manifest"] = serving_manifest(
                baseline,
                data_version=baseline["serving_manifest"]["data_version"],
                policy=baseline["serving_manifest"]["policy"],
                ready_on=str(T.date()),
            )
            baseline_version = baseline["t1_version"]
            promoted_live = record["id"]
        break  # Audit one preselected challenger; never search by audit outcomes.
    progress("T1: tạo ứng viên trên cửa sổ trượt gần nhất")
    fit = trainer or train
    fit_kwargs = dict(incumbent=baseline, catalog=catalog, policy=policy)
    if trainer is None and reconciled_through is not None:
        fit_kwargs["reconciled_through"] = reconciled_through
    bundle = fit(data, T, progress, **fit_kwargs)
    proposal = bundle.pop("proposal", None)
    bundle["candidate_update_audit"] = deepcopy(bundle["audit"])
    if promoted_live:
        bundle["promotion_status"] = "accepted_prospective_audit"
        bundle["prospective_audit_id"] = promoted_live
        bundle["promotion_audit"] = deepcopy(baseline["promotion_audit"])
        # Legacy readers of audit still see the actual activation decision.
        bundle["audit"] = deepcopy(bundle["promotion_audit"])
    elif bundle["promotion_status"] == "accepted_historical_audit":
        bundle["promotion_audit"] = dict(
            bundle["audit"],
            kind="historical",
            evaluated_asof=str(T.date()),
            serving_version=bundle["t1_version"],
        )
        bundle["prospective_audit_id"] = None
    elif baseline.get("promotion_audit"):
        bundle["promotion_audit"] = deepcopy(baseline["promotion_audit"])
        bundle["prospective_audit_id"] = baseline.get("prospective_audit_id")
    bundle["t1_provenance"] = dict(
        bundle.get("t1_provenance", {}),
        promotion_status=bundle["promotion_status"],
        local_adaptation="local" in bundle.get("serving_method", ""),
    )
    identifier = uuid.uuid4().hex
    from agent1.adaptive.training_report import save_training_report

    bundle["update_period"] = {
        "previous_cycle_asof": state.get("last_cycle_asof"),
        "current_asof": str(T.date()),
        "lookback_days": policy.lookback_days,
        "strategy": "restart_each_family_from_global_on_rolling_history_with_censored_recent_weeks",
        "new_observation_period": {
            "after": state.get("last_cycle_asof"),
            "through": str(T.date()),
        },
    }
    if reconciled_through is not None:
        bundle["update_period"]["reconciled_through"] = str(
            pd.Timestamp(reconciled_through).date()
        )
    manifest = bundle["serving_manifest"]
    bundle["serving_manifest"] = serving_manifest(
        bundle,
        data_version=manifest["data_version"],
        policy=manifest["policy"],
        ready_on=manifest["ready_on"],
    )
    encrypted_report = bool(save_training_report(bundle, data, identifier))
    challenger_row = challenger_weight = None
    if (
        proposal
        and (
            proposal["historical_audit_passed"] or proposal.get("prospective_eligible")
        )
        and proposal["version"] != bundle["t1_version"]
    ):
        shadow = deepcopy(bundle)
        shadow.update(
            model=proposal["model"],
            catalog_sha256=catalog.digest,
            partial=proposal["partial"],
            partial_version=proposal["partial"].digest,
            anchor=proposal["model"],
            weight=1.0,
            t1_version=proposal["version"],
            asof=proposal["asof"],
            t1_parameter_asof=proposal.get("t1_parameter_asof"),
            serving_method=proposal["method"],
            promotion_status="pending_prospective_audit",
        )
        shadow["serving_manifest"] = serving_manifest(
            shadow,
            data_version=bundle.get("dataset_hash"),
            policy=bundle["policy"],
            ready_on=str(T.date()),
        )
        snapshot = snapshot_for_audit(
            data,
            T,
            bundle,
            shadow,
            bundle["t1_version"],
            proposal["version"],
            created,
        )
        if snapshot and not any(
            r["origin"] == str(T.date())
            and r["baseline_version"] == bundle["t1_version"]
            for r in pending
        ):
            challenger_row = {
                "id": identifier,
                "artifact_id": identifier,
                "origin": str(T.date()),
                "status": "pending",
                "baseline_version": bundle["t1_version"],
                "challenger_version": proposal["version"],
                "snapshot": snapshot,
                "created_at": created,
                "policy": bundle["policy"],
            }
            challenger_weight = dict(id=identifier, **encode(shadow))
    payload = dict(id=identifier, **encode(bundle))
    report = metadata(bundle, identifier, created)
    report["encrypted_report"] = encrypted_report
    next_due = str((T + pd.Timedelta(days=policy.interval_days)).date())
    decision = {
        "id": identifier,
        "status": bundle["promotion_status"],
        "asof": str(T.date()),
        "serving_version": bundle["t1_version"],
        "proposal_version": proposal["version"] if proposal else None,
        "next_due": next_due,
        "prospective_audit_id": promoted_live,
        "audit": bundle["audit"],
        "promotion_audit": bundle.get("promotion_audit"),
        "candidate_update_audit": bundle["candidate_update_audit"],
        "model_id": identifier,
        "created_at": created,
        "update_period": bundle["update_period"],
        "serving_manifest": bundle["serving_manifest"],
        "activated": True,
    }
    batches = {
        "company_payment_coverage": [coverage],
        "company_weights": [payload],
        "company_models": [report],
        "company_t1_update_runs": [decision],
        "company_t1_update_state": [
            {
                "id": "current",
                "last_cycle_asof": str(T.date()),
                "next_due": next_due,
                "last_dataset_sha256": snapshot_hash,
                "last_model_id": identifier,
                "serving_version": bundle["t1_version"],
            }
        ],
    }
    if audit_updates:
        batches["company_t1_challengers"] = audit_updates
    if challenger_row:
        batches.setdefault("company_t1_challengers", []).append(challenger_row)
        batches["company_t1_challenger_weights"] = [challenger_weight]
    if batches.get("company_t1_challengers"):
        batches["company_t1_challenger_index"] = [
            _challenger_metadata(row) for row in batches["company_t1_challengers"]
        ]
    batches["company_model_active"] = [{"id": "active", "version": identifier}]
    # CAS and all related records commit together. A concurrent import or model
    # activation must never silently overwrite the incumbent being compared.
    with store.lock, store.connection:
        store.connection.execute("BEGIN IMMEDIATE")
        if (
            store.one(firm, "company_model_active", "active") != active_pointer
            or fingerprint(visible_data(current_data(store, firm), T)) != snapshot_hash
            or store.one(firm, "company_t1_update_state", "current") != (state or None)
        ):
            raise ValueError(
                "Dữ liệu/phiên bản T1 đã đổi trong khi học; chưa kích hoạt kết quả"
            )
        store.put_many(firm, batches)
    return decision
