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
from agent1.adaptive.payment_coverage import attest
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
    train_update,
    valid_incumbent,
)


def now():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))


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
    data["payment_coverage"] = [*data.get("payment_coverage", []),
                                *store.get(firm, "company_payment_coverage")]
    return data


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
    result = valid_incumbent(bundle, cutoff, catalog)
    return result, record


def metadata(bundle, identifier, created_at):
    fields = (
        "asof",
        "update_asof",
        "dataset_hash",
        "audit",
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
    )
    return dict(
        {k: bundle.get(k) for k in fields},
        id=identifier,
        artifact_id=identifier,
        created_at=created_at,
        operating_ready=bool(bundle.get("operating")),
        synthetic_sandbox=bool(bundle.get("synthetic_sandbox")),
    )


def run_cycle(
    store,
    firm,
    cutoff,
    *,
    payments_complete,
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
    if not payments_complete:
        raise ValueError("Cần xác nhận dữ liệu thanh toán đầy đủ đến ngày cập nhật")
    policy, catalog = policy or UpdatePolicy(), catalog or GlobalCatalog()
    T = pd.Timestamp(cutoff).normalize()
    created = now().isoformat()
    if T.date() > now().date():
        raise ValueError("Không tạo chu kỳ T1 cho ngày tương lai")
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
    coverage = dict(id=uuid.uuid4().hex, **attest(data, T, created))
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
                dict(record, status="pending" if result["status"] == "insufficient_eligible_outcomes"
                     else result["status"], evaluation=result)
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
            baseline["audit"] = dict(result, accepted=True)
            baseline["serving_manifest"] = serving_manifest(
                baseline, data_version=baseline["serving_manifest"]["data_version"],
                policy=baseline["serving_manifest"]["policy"], ready_on=str(T.date()),
            )
            baseline_version = baseline["t1_version"]
            promoted_live = record["id"]
        break  # Audit one preselected challenger; never search by audit outcomes.
    progress("T1: tạo ứng viên trên cửa sổ trượt gần nhất")
    fit = trainer or train_update
    bundle = fit(data, T, progress, incumbent=baseline, catalog=catalog, policy=policy)
    proposal = bundle.pop("proposal", None)
    if promoted_live:
        bundle["promotion_status"] = "accepted_prospective_audit"
        bundle["prospective_audit_id"] = promoted_live
    bundle["t1_provenance"] = dict(
        bundle.get("t1_provenance", {}),
        promotion_status=bundle["promotion_status"],
        local_adaptation="local" in bundle.get("serving_method", ""),
    )
    identifier = uuid.uuid4().hex
    from agent1.adaptive.training_report import save_training_report

    encrypted_report = bool(save_training_report(bundle, data, identifier))
    challenger_row = challenger_weight = None
    if (
        proposal
        and (proposal["historical_audit_passed"] or proposal.get("prospective_eligible"))
        and proposal["version"] != bundle["t1_version"]
    ):
        shadow = deepcopy(bundle)
        shadow.update(
            model=proposal["model"],
            partial=proposal["partial"],
            partial_version=proposal["partial"].digest,
            anchor=proposal["model"],
            weight=1.0,
            t1_version=proposal["version"],
            t1_parameter_asof=proposal["asof"],
            serving_method=proposal["method"],
            promotion_status="pending_prospective_audit",
        )
        shadow["serving_manifest"] = serving_manifest(
            shadow, data_version=bundle.get("dataset_hash"), policy=bundle["policy"],
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
        "model_id": identifier,
        "created_at": created,
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
