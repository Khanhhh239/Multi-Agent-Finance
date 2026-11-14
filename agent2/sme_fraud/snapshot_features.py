"""Bitemporal snapshot adapter around the retained feature engine.

IDs/evidence never enter the exported numeric matrix. The private legacy DTO
contains inert placeholders for unsupported legacy inputs; only the explicit
source-backed allowlist below is exported. No generator, labels or fitting.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
from pathlib import Path

from finance_input.validation import stamp
from . import features as legacy
from .feature_contract import current_contract as legacy_contract
from .import_files import canonical, digest, fail
from .imports import validate_input
from .temporal_evidence import bank_identity

VERSION = "snapshot-point-in-time/1.1.0"
VN = timezone(timedelta(hours=7))
KINDS = ("payment", "receipt", "payroll", "transfer", "adjustment", "reversal")
LEGACY_TYPES = dict(payment="vendor_payment", receipt="customer_receipt", payroll="payroll",
                    transfer="all", adjustment="adjustment", reversal="*")
DESCRIPTIONS = {
    "log_abs_amount": "log1p(abs(signed VND)); sign retained separately, never overwrites source",
    "amount_negative": "Signed amount is negative", "amount_zero": "Signed amount is zero",
    "round_million": "Signed amount is a multiple of 1,000,000 VND",
    "event_hour_sin": "VN economic-event hour sine, not upload/creation hour",
    "event_hour_cos": "VN economic-event hour cosine",
    "event_weekday_sin": "VN economic-event weekday sine",
    "event_weekday_cos": "VN economic-event weekday cosine",
    "event_weekend": "VN economic-event date is Saturday/Sunday; not a policy violation",
    "prior_type_history_log_count": "Retained log1p count: same kind, strictly prior on both clocks",
    "log_abs_deviation_from_history": "Retained magnitude log deviation; unavailable if zero affects legacy kernel",
    "abs_amount_history_z": "Retained magnitude z, >=5 prior same-kind samples and SD floor .25; not detector readiness",
    "employee_bank_overlap_observed": "Retained recipient bank match among known employee sources",
    "graph_employee_count_observed": "Retained current graph employee count, bank-only input profile",
    "graph_vendor_count_observed": "Retained current graph vendor count including self; bank-only input profile",
    "journal_line_count": "Retained count of source accounting lines, absent lines remain missing",
    "journal_imbalance_abs_ratio": "Retained abs(total debit-credit)/abs(amount); unavailable for zero amount",
    "known_document_count": "Known linked documents; raw evidence IDs/hashes stay outside predictors",
    "verified_original_document_count": "Known original verified documents; not a fraud label or complete checklist",
    "known_invoice_count": "Distinct known invoice identities through explicit allocations",
    "linked_invoice_log_abs_total": "log1p(abs(sum known linked invoice face amounts)); not outstanding obligation",
    "allocation_to_invoice_face_ratio": "Signed current allocated amount/positive linked invoice face total",
    "prior_invoice_payment_count": "Distinct prior payment identities linked to the same known invoices; null if relevant visible allocation sources are unresolved",
    "prior_invoice_allocation_log_abs": "log1p(abs(prior signed allocations)); null if relevant visible allocation sources are unresolved; exact VND in evidence",
    "prior_invoice_allocation_negative": "Prior signed allocation sum is negative; null if relevant visible allocation sources are unresolved",
    "creator_equals_approver": "Known creator and unique approved employee identity match",
    "observed_approval_limit_ratio": "Signed amount/one unambiguous positive observed approved limit",
}
DESCRIPTIONS.update({"kind_"+kind: "Source transaction kind: "+kind for kind in KINDS})
COLUMNS = tuple(DESCRIPTIONS)


@lru_cache(maxsize=100000)
def utc(value):
    return stamp(value).astimezone(timezone.utc)


def available(row):
    return max(utc(row["effective_at"]), utc(row["observed_at"]))


def _time(value):
    return value.astimezone(VN).isoformat(timespec="seconds")


def _id(table, row):
    return table+"_"+digest(canonical([row["tenant_id"], row["company_id"], row["record_id"]]))


def _ref(table, row):
    return dict(table=table, record_id=row["record_id"], revision=row["revision"],
                observed_at=row["observed_at"], effective_at=row["effective_at"])


def _selected(rows, cid, knowledge, valid, *, strict=False, exclude=()):
    """Filter both clocks before choosing revisions; never global-latest first."""
    eligible = {}
    latest = {}
    for row in rows:
        if row["company_id"] != cid or row["record_id"] in exclude:
            continue
        observed, effective = utc(row["observed_at"]), utc(row["effective_at"])
        outside=(observed >= knowledge or effective >= valid) if strict else (observed > knowledge or effective > valid)
        if outside:
            continue
        eligible[(row["record_id"], row["revision"])] = row
        old = latest.get(row["record_id"])
        if old is None or row["revision"] > old["revision"]:
            latest[row["record_id"]] = row
    return latest, eligible


def feature_contract():
    contract = dict(version=VERSION, columns=list(COLUMNS), descriptions=DESCRIPTIONS,
        dtype="float64", nullable=True, missing="parallel boolean matrix; null never implicitly imputed",
        timezone="Asia/Ho_Chi_Minh (+07:00) for calendar; aware UTC comparisons",
        knowledge="global as_of caps outputs; per-row cutoff=max(effective_at,observed_at)",
        context="source observed_at<=cutoff and effective_at<=event_at, current eligible revision",
        history="effective_at<event_at AND available_at<cutoff, revision chosen before group; exclude self identity",
        simultaneous="same event timestamp OR same availability timestamp cannot enter each other's histories",
        windows={"magnitude_history":"all eligible strictly prior rows of same kind", "z_minimum_samples":5, "z_sd_floor":.25},
        signed_money="source unchanged; abs magnitude + negative/zero indicators, exact signed evidence sums",
        predictor_exclusions=["tenant_id","company_id","record_id","revision","snapshot_id","as_of","labels","document IDs/hashes/text","source system/seed/template"],
        snapshot_read_validation="Committed, scoped, checksum-verified sources retain verification; evidence.verify authorizes writes, not reads. All other validation remains enforced.",
        prior_invoice_history=dict(coverage="Visible prior allocations to current linked invoice IDs and eligible prior transaction IDs, within this snapshot/cutoff only; not proof of complete external books",
            incomplete="Unresolved referenced invoice/transaction revision makes all three prior_invoice predictors and evidence prior_signed_allocation_vnd null; never backfill future sources",
            evidence="prior_invoice_history status/coverage_basis/unavailable_references; known allocation records retained; no future source values or timestamps"),
        legacy=legacy_contract(), adapter_sha256=digest(Path(__file__).read_bytes()),
        model_compatibility="new contract; legacy caches/models are not automatically compatible")
    contract["private_core_clock"]="order-preserving second ranks for legacy time validation; never exported; full-precision clocks control selection/groups"
    return dict(contract, fingerprint=digest(canonical(contract)))


def _project(cid, history, targets, sources, cutoff):
    """Only magnitude/history/calendar/bank-graph/line primitives leave this DTO."""
    ordered = sorted([*history.values(), *targets], key=lambda r:(available(r), LEGACY_TYPES[r["kind"]], abs(r["amount_vnd"]), r["record_id"]))
    # Legacy validators require second-resolution +07:00 timestamps. Preserve
    # full input precision via ordered private slots; only non-window primitives
    # leave the adapter. Calendar primitives retain the real economic timestamp.
    clocks=sorted({available(r) for r in ordered}|{available(r) for table in ("employees","vendors") for r in sources[table][0].values()})
    slots={value:datetime(2000,1,1,tzinfo=VN)+timedelta(seconds=index) for index,value in enumerate(clocks)}
    first=slots[clocks[0]]
    stub = "private_unobserved_creator"
    employees = [dict(employee_id=stub, company_id=cid, recorded_at=_time(first), bank_account="", bank_code="", phone="", address="", self_approval_limit_vnd=0, contract_on_file=0)]
    for row in sources["employees"][0].values():
        employees.append(dict(employee_id=_id("employees",row), company_id=cid, recorded_at=_time(slots[available(row)]),
            bank_account=row.get("bank_account") or "", bank_code=row.get("bank_code") or "", phone="", address="",
            self_approval_limit_vnd=0, contract_on_file=0))
    vendors = [dict(vendor_id=_id("vendors",r), company_id=cid, recorded_at=_time(slots[available(r)]),
        bank_account=r.get("bank_account") or "", bank_code=r.get("bank_code") or "", phone="", address=r.get("address") or "",
        registered_at=_time(first), onboarded_at=_time(first), related_party_disclosed_at="")
        for r in sources["vendors"][0].values()]

    def entity(table, reference):
        if reference and (reference["record_id"], reference["revision"]) in sources[table][1]:
            return sources[table][0].get(reference["record_id"])
        return None

    projected=[]; routes={}; lines=[]; target_ids={r["record_id"] for r in targets}
    for index, row in enumerate(ordered):
        identity=f"T{index:012d}"
        vendor=entity("vendors",row.get("vendor_ref")); employee=entity("employees",row.get("employee_ref"))
        creator=entity("employees",row.get("created_by_ref")) if row["record_id"] in target_ids else None
        value=dict(transaction_id=identity, company_id=cid, amount_vnd=max(1,abs(row["amount_vnd"])),
            txn_type=LEGACY_TYPES[row["kind"]], posted_at=_time(slots[available(row)]), created_at=_time(utc(row["effective_at"])),
            approved_at=_time(slots[available(row)]), vendor_id=_id("vendors",vendor) if vendor else "",
            employee_id=_id("employees",employee) if employee else "", creator_id=_id("employees",creator) if creator else stub,
            approver_id="", approval_limit_vnd=1, customer_id="", advance_id="", payroll_period="", is_financial_entry=1,
            recipient_account=row.get("bank_account") or "", recipient_bank_code=row.get("bank_code") or "",
            invoice_id="", invoice_number="", invoice_issued_at="", invoice_observed_at="", invoice_gross_vnd=0,
            invoice_net_vnd=0, invoice_vat_vnd=0, linked_input_vat_vnd=0, support_doc_count=0,
            goods_receipt_verified=0, evidence_on_file=0, debit_account="",credit_account="",
            accounting_purpose="",journal_signature="",recognised_input_vat_vnd=0,recognised_output_vat_vnd=0,
            writeoff_provision_vnd=0,production_cost_vnd=0)
        projected.append(value); routes[identity]=row
        for line in row.get("accounting_lines",[]):
            lines.append(dict(transaction_id=identity,company_id=cid,posted_at=value["posted_at"],account_code=line["account"],debit_vnd=line["debit_vnd"],credit_vnd=line["credit_vnd"]))
    tables=dict(transactions=projected, employees=employees, vendors=vendors,
        companies=[dict(company_id=cid,accounting_framework="TT200")],calendar=[],journal_lines=lines)
    computed=legacy.build_features(tables)
    return {routes[f["transaction_id"]]["record_id"]:f for f in computed if routes[f["transaction_id"]]["record_id"] in target_ids}, entity


def build_feature_rows(bundle, scope, as_of):
    """Raw/offline input still requires authorization to assert verification."""
    return _build_feature_rows(bundle, scope, as_of)


def _build_feature_rows(bundle, scope, as_of, *, committed_snapshot=False):
    validation=validate_input(bundle,scope)
    # Only build_from_snapshot can select this internal read path, after the
    # store's tenant/permission and checksum checks. Do not grant permissions or
    # skip provenance/time/schema errors. No client-facing bypass is accepted.
    verification_read_only=(committed_snapshot and validation["errors"] and
        all(e["code"]=="VERIFICATION_PERMISSION" for e in validation["errors"]))
    if validation["status"]=="rejected" and not verification_read_only:
        fail(422,"FEATURE_INPUT_INVALID","Snapshot không thỏa hợp đồng đầu vào.","Kiểm tra lại ValidationReport; không bỏ dòng hoặc dùng snapshot ngoài quyền.")
    ceiling=utc(as_of)
    groups=defaultdict(list)
    for cid in sorted(scope.company_ids):
        targets,_=_selected(bundle["transactions"],cid,ceiling,ceiling)
        for row in targets.values():groups[(cid,utc(row["effective_at"]),available(row))].append(row)
    vectors=[]; missing=[]; row_meta=[]; evidence=[]
    for (cid,event,cutoff), targets in sorted(groups.items()):
        targets=sorted(targets,key=lambda r:r["record_id"])
        history,history_versions=_selected(bundle["transactions"],cid,cutoff,event,strict=True,exclude={r["record_id"] for r in targets})
        sources={table:_selected(bundle.get(table,[]),cid,cutoff,event) for table in ("employees","vendors","companies","invoices","payment_allocations","approvals","supporting_documents","vendor_bank_history")}
        primitive, entity=_project(cid,history,targets,sources,cutoff)
        past_allocations,_=_selected(bundle["payment_allocations"],cid,cutoff,event,strict=True)
        for row in targets:
            values={k:None for k in COLUMNS}; reasons={}; refs={}
            def use(table, record):
                if record:refs[(table,record["record_id"],record["revision"])]=_ref(table,record)
                return record
            def put(name,value,reason="source_unavailable"):
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
                    raise ValueError("Non-finite or non-numeric predictor: "+name)
                values[name]=value
                if value is None:reasons[name]=reason
            use("transactions",row)
            for h in history.values():use("transactions",h)
            f=primitive[row["record_id"]]; amount=row["amount_vnd"]
            put("log_abs_amount",f["log_amount"] if amount else 0)
            put("amount_negative",int(amount<0));put("amount_zero",int(amount==0));put("round_million",int(amount%1000000==0))
            for exported,old in (("event_hour_sin","hour_sin"),("event_hour_cos","hour_cos"),("event_weekday_sin","weekday_sin"),("event_weekday_cos","weekday_cos"),("event_weekend","created_weekend")):
                put(exported,f[old])
            put("prior_type_history_log_count",f["prior_type_history_log_count"])
            same=[h for h in history.values() if h["kind"]==row["kind"]]
            magnitude_ok=amount!=0 and all(h["amount_vnd"]!=0 for h in same)
            put("log_abs_deviation_from_history",f["log_amount_vs_history"] if same and magnitude_ok else None,"no_history_or_zero_unsupported_by_legacy_magnitude_kernel")
            put("abs_amount_history_z",f["amount_history_z"] if len(same)>=5 and magnitude_ok else None,"legacy_z_requires_5_nonzero_prior_samples")
            vendor=use("vendors",entity("vendors",row.get("vendor_ref")))
            employee_sources=[e for e in sources["employees"][0].values() if bank_identity(e.get("bank_account"),e.get("bank_code"))]
            recipient=bank_identity(row.get("bank_account"),row.get("bank_code"))
            graph_ok=bool(vendor and bank_identity(vendor.get("bank_account"),vendor.get("bank_code")))
            for e in employee_sources:use("employees",e)
            for v in sources["vendors"][0].values():
                if bank_identity(v.get("bank_account"),v.get("bank_code")):use("vendors",v)
            put("employee_bank_overlap_observed",f["employee_bank_overlap"] if recipient and vendor and employee_sources else None,"recipient_or_employee_bank_source_missing")
            put("graph_employee_count_observed",f["graph_employee_count_current"] if graph_ok else None,"vendor_bank_identity_missing")
            put("graph_vendor_count_observed",f["linked_vendor_count_current"] if graph_ok else None,"vendor_bank_identity_missing")
            lines=row.get("accounting_lines")
            put("journal_line_count",f["journal_line_count"] if lines is not None else None,"accounting_lines_not_provided")
            put("journal_imbalance_abs_ratio",f["journal_balance_difference_ratio"] if lines is not None and amount else None,"accounting_lines_missing_or_zero_denominator")

            current_alloc=[]; linked={}; all_links_known=True
            for allocation in sources["payment_allocations"][0].values():
                reference=allocation["transaction_ref"]
                if reference["record_id"]!=row["record_id"]:continue
                # A future transaction revision must not authorize a link.
                tx_known=any(t["record_id"]==row["record_id"] and t["revision"]==reference["revision"] and utc(t["observed_at"])<=cutoff and utc(t["effective_at"])<=event for t in bundle["transactions"])
                if not tx_known:all_links_known=False;continue
                use("payment_allocations",allocation);current_alloc.append(allocation)
                invoice=entity("invoices",allocation["invoice_ref"])
                if invoice:linked[invoice["record_id"]]=use("invoices",invoice)
                else:all_links_known=False
            put("known_invoice_count",len(linked))
            invoice_total=sum(r["amount_vnd"] for r in linked.values())
            put("linked_invoice_log_abs_total",math.log1p(abs(invoice_total)) if linked and all_links_known else None,"invoice_source_or_link_missing")
            put("allocation_to_invoice_face_ratio",sum(a["amount_vnd"] for a in current_alloc)/invoice_total if linked and all_links_known and invoice_total>0 else None,"invoice_links_incomplete_or_nonpositive_denominator")
            prior_total=0; prior_payments=set(); history_limits=[]
            def unavailable_history_reference(table, allocation, reference):
                label="hóa đơn" if table=="invoices" else "giao dịch"
                history_limits.append(dict(code="PRIOR_SOURCE_UNAVAILABLE",
                    source=_ref("payment_allocations",allocation),
                    field="invoice_ref" if table=="invoices" else "transaction_ref",
                    reference=dict(table=table,record_id=reference["record_id"],revision=reference["revision"]),
                    message=f"Chưa đủ dữ liệu: phiên bản {label} được phân bổ lịch sử tham chiếu chưa khả dụng tại thời điểm phân tích.",
                    action="Đối chiếu bản ghi được tham chiếu và thời điểm nguồn được biết; khi bổ sung, tạo snapshot mới, không lùi thời gian nguồn."))
            for allocation in past_allocations.values():
                tx=allocation["transaction_ref"]; inv=allocation["invoice_ref"]
                if inv["record_id"] not in linked or tx["record_id"] not in history:continue
                # The known allocation itself proves a relevant dependency exists.
                # Retain it even if its referenced revision cannot be used yet.
                use("payment_allocations",allocation)
                tx_known=(tx["record_id"],tx["revision"]) in history_versions
                if not tx_known:unavailable_history_reference("transactions",allocation,tx)
                invoice=entity("invoices",inv)
                if invoice:use("invoices",invoice)
                else:unavailable_history_reference("invoices",allocation,inv)
                if not tx_known or not invoice:continue
                prior_total+=allocation["amount_vnd"]
                if history[tx["record_id"]]["kind"]=="payment":prior_payments.add(tx["record_id"])
            prior_available=bool(linked and all_links_known and not history_limits)
            prior_reason="prior_invoice_history_incomplete" if history_limits else "no_complete_known_invoice_links"
            for name,value in (("prior_invoice_payment_count",len(prior_payments)),("prior_invoice_allocation_log_abs",math.log1p(abs(prior_total))),("prior_invoice_allocation_negative",int(prior_total<0))):
                put(name,value if prior_available else None,prior_reason)
            prior_coverage=dict(status="available" if prior_available else "unavailable",
                coverage_basis="visible_prior_allocations_to_linked_invoices_in_submitted_snapshot",
                unavailable_references=sorted(history_limits,key=lambda item:(item["source"]["record_id"],item["source"]["revision"],item["field"])))

            subjects={("transactions",row["record_id"],row["revision"])}|{("invoices",r["record_id"],r["revision"]) for r in linked.values()}
            docs=[]
            for document in sources["supporting_documents"][0].values():
                if any((s["table"],s["record_id"],s["revision"]) in subjects for s in document["subject_refs"]):docs.append(use("supporting_documents",document))
            put("known_document_count",len(docs))
            put("verified_original_document_count",sum(d["source_kind"]=="original" and not d["source"]["is_simulated"] and d["verification_status"]=="verified" for d in docs))
            approved=[]
            for approval in sources["approvals"][0].values():
                reference=approval["transaction_ref"]
                if reference["record_id"]==row["record_id"] and reference["revision"]==row["revision"] and approval["decision"]=="approved":approved.append(use("approvals",approval))
            creator=use("employees",entity("employees",row.get("created_by_ref")))
            approvers=[use("employees",entity("employees",a["employee_ref"])) for a in approved]
            identities={r["record_id"] for r in approvers if r}
            put("creator_equals_approver",int(creator["record_id"] in identities) if creator and len(identities)==1 and all(approvers) else None,"creator_or_unique_approver_source_missing")
            limits={a["limit_vnd"] for a in approved if "limit_vnd" in a}
            put("observed_approval_limit_ratio",amount/next(iter(limits)) if approved and len(limits)==1 and all("limit_vnd" in a for a in approved) and next(iter(limits))>0 else None,"approved_limit_missing_ambiguous_or_zero")
            for kind in KINDS:put("kind_"+kind,int(row["kind"]==kind))
            assert set(values)==set(COLUMNS)
            assert {k for k,v in values.items() if v is None}==set(reasons)
            index=len(vectors)
            vectors.append([values[k] for k in COLUMNS]);missing.append([values[k] is None for k in COLUMNS])
            row_meta.append(dict(row_index=index,tenant_id=row["tenant_id"],company_id=cid,record_id=row["record_id"],revision=row["revision"],event_at=event.isoformat(),as_of=cutoff.isoformat()))
            evidence.append(dict(row_index=index,records=[refs[k] for k in sorted(refs)],missing_reasons=reasons,
                signed_amount_vnd=amount,prior_signed_allocation_vnd=prior_total if prior_available else None,
                prior_invoice_history=prior_coverage,linked_invoice_face_total_vnd=invoice_total,
                history_record_count=len(history),history_type_record_count=len(same)))
    return dict(as_of=ceiling.isoformat(),contract=feature_contract(),features=vectors,missing=missing,rows=row_meta,evidence=evidence)


def build_from_snapshot(store, scope, snapshot_id, as_of, recheck=None):
    # Both reads are scoped and checksum-verified; snapshots cannot mutate between them.
    manifest=store.get_snapshot(scope,snapshot_id,recheck)
    from finance_input.json_io import loads
    raw=store.get_snapshot(scope,snapshot_id,recheck,data=True)
    if digest(raw)!=manifest["data_checksum"]:fail(500,"ARTIFACT_INTEGRITY","Checksum snapshot không khớp.","Đối chiếu kho/backup trước khi tạo feature.")
    result=_build_feature_rows(loads(raw),scope,as_of,committed_snapshot=True)
    if recheck is not None and recheck()!=scope:fail(409,"AUTH_CONTEXT_CHANGED","Quyền đã thay đổi khi tạo feature.","Chạy lại job theo quyền hiện hành.")
    result["snapshot"]=dict(snapshot_id=snapshot_id,tenant_id=manifest["tenant_id"],company_id=manifest["company_id"],checksum=manifest["checksum"],data_checksum=manifest["data_checksum"],contract_version=manifest["contract_version"])
    return result
