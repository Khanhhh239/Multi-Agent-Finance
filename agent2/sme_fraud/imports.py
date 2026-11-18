"""Agent2's input profile. No file I/O, persistence, fitting or alert delivery.

An authenticated backend must construct AccessScope before reading uploaded data.
This module is also callable offline for synthetic contract acceptance tests.
"""
from collections import OrderedDict, defaultdict
from copy import deepcopy
from datetime import timezone
from functools import lru_cache
import hashlib
import json
import re
import threading

from finance_input import AccessScope, CONTRACT_VERSION, SUPPORTED_CONTRACT_VERSIONS, check_core, schema
from finance_input.money import minor
from finance_input.validation import TABLES as CORE_TABLES, issue, key, records, stamp
from . import p1_inputs
from .identity import normalize as _norm_identity

PROFILE_VERSION = "agent2-posted-vnd/1.1.0"
VALIDATOR_VERSION = "1.3.0"
REPORT_VERSION = "1.2.0"
DEFINITIONS = {"companies":"company", "transactions":"transaction", "vendors":"vendor",
               "invoices":"invoice", "payment_allocations":"allocation", "employees":"employee",
               "approvals":"approval", "supporting_documents":"document", "vendor_bank_history":"bank_history",
               "payment_history_coverage":"payment_history_coverage"}

_VND_RE = re.compile(r"-?[0-9]+(?:\.[0-9]+)?\Z")
_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_SHA256_RE = re.compile(r"[a-f0-9]{64}\Z")
_PROP_NAME_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
_MISSING_ENUM = frozenset({"missing", "unknown", "not_provided_by_source", "not_applicable"})
_REF_MAP = {
    "transactions": {"vendor_ref": "vendors", "employee_ref": "employees", "created_by_ref": "employees", "adjusts_ref": "transactions"},
    "invoices": {"vendor_ref": "vendors", "adjusts_ref": "invoices"},
    "payment_allocations": {"transaction_ref": "transactions", "invoice_ref": "invoices", "adjusts_ref": "payment_allocations"},
    "approvals": {"transaction_ref": "transactions", "employee_ref": "employees"},
    "vendor_bank_history": {"vendor_ref": "vendors"},
}


_VALIDATED_CHECKSUMS_LOCK = threading.Lock()
_VALIDATED_CHECKSUMS = OrderedDict()


def mark_validated_checksum(data_checksum, tenant_id, company_ids):
    if not data_checksum or not tenant_id:
        return
    with _VALIDATED_CHECKSUMS_LOCK:
        for cid in company_ids:
            k = (data_checksum, tenant_id, cid)
            _VALIDATED_CHECKSUMS[k] = True
            _VALIDATED_CHECKSUMS.move_to_end(k)
        while len(_VALIDATED_CHECKSUMS) > 256:
            _VALIDATED_CHECKSUMS.popitem(last=False)


def is_validated_checksum(data_checksum, tenant_id, company_id):
    with _VALIDATED_CHECKSUMS_LOCK:
        return (data_checksum, tenant_id, company_id) in _VALIDATED_CHECKSUMS


@lru_cache(maxsize=262144)
def _stamp(value):
    return stamp(value).astimezone(timezone.utc)


@lru_cache(maxsize=131072)
def _cached_id_str(val):
    return _ID_RE.fullmatch(val) is not None


def _valid_id_str(val):
    return isinstance(val, str) and _cached_id_str(val)


@lru_cache(maxsize=262144)
def _cached_ts_str(val):
    try:
        _stamp(val)
        return True
    except ValueError:
        return False


def _valid_ts_str(val):
    return isinstance(val, str) and _cached_ts_str(val)


@lru_cache(maxsize=8)
def _cached_schema(ver):
    return schema(ver)


def _valid_ref_obj(val):
    if not isinstance(val, dict) or len(val) != 2:
        return False
    rid = val.get("record_id")
    rev = val.get("revision")
    return _valid_id_str(rid) and type(rev) is int and rev >= 1


def _valid_source_obj(val):
    if not isinstance(val, dict):
        return False
    n = len(val)
    if n not in (3, 4):
        return False
    sys_v = val.get("system")
    rec_v = val.get("record_id")
    sim_v = val.get("is_simulated")
    if not (_valid_id_str(sys_v)
            and isinstance(rec_v, str) and 1 <= len(rec_v) <= 2000
            and type(sim_v) is bool):
        return False
    if n == 4:
        sha = val.get("content_sha256")
        if not (isinstance(sha, str) and _SHA256_RE.fullmatch(sha) is not None):
            return False
    return True


def _compile_prop_checker(prop_spec, defs):
    if "$ref" in prop_spec:
        ref_name = prop_spec["$ref"].rsplit("/", 1)[-1]
        if ref_name == "reference":
            return _valid_ref_obj
        return _compile_obj_checker(defs[ref_name], defs)
    if "anyOf" in prop_spec:
        subs = [_compile_prop_checker(sub, defs) for sub in prop_spec["anyOf"]]
        return lambda v: any(chk(v) for chk in subs)
    if "const" in prop_spec:
        expected = prop_spec["const"]
        return lambda v: v == expected and type(v) is type(expected)
    if "enum" in prop_spec:
        allowed_vals = tuple(prop_spec["enum"])
        return lambda v: any(v == a and type(v) is type(a) for a in allowed_vals)
    ptype = prop_spec.get("type")
    if ptype == "null":
        return lambda v: v is None
    if ptype == "boolean":
        return lambda v: type(v) is bool
    if ptype == "integer":
        lo = prop_spec.get("minimum")
        hi = prop_spec.get("maximum")
        return lambda v: type(v) is int and (lo is None or v >= lo) and (hi is None or v <= hi)
    if ptype == "string":
        if prop_spec.get("format") == "source-timestamp":
            return _valid_ts_str
        min_l = prop_spec.get("minLength", 0)
        max_l = prop_spec.get("maxLength")
        raw_pat = prop_spec.get("pattern")
        if raw_pat == "^[A-Za-z0-9_.:-]+$" and min_l == 1 and max_l == 128:
            return _valid_id_str
        pat = re.compile(raw_pat + r"\Z") if raw_pat is not None else None
        def _chk_str(v):
            if not isinstance(v, str):
                return False
            if len(v) < min_l or (max_l is not None and len(v) > max_l):
                return False
            if pat is not None and pat.fullmatch(v) is None:
                return False
            return True
        return _chk_str
    if ptype == "array":
        min_items = prop_spec.get("minItems", 0)
        max_items = prop_spec.get("maxItems")
        item_chk = _compile_prop_checker(prop_spec["items"], defs) if "items" in prop_spec else (lambda _: True)
        return lambda v: (isinstance(v, list) and len(v) >= min_items
                          and (max_items is None or len(v) <= max_items)
                          and all(item_chk(x) for x in v))
    if ptype == "object":
        return _compile_obj_checker(prop_spec, defs)
    return lambda _: False


def _compile_obj_checker(obj_spec, defs):
    if obj_spec.get("additionalProperties") is not False:
        # e.g. missing_fields map
        add_spec = obj_spec.get("additionalProperties", {})
        val_chk = _compile_prop_checker(add_spec, defs) if isinstance(add_spec, dict) and add_spec else (lambda _: True)
        name_pat = re.compile(obj_spec["propertyNames"]["pattern"] + r"\Z") if "propertyNames" in obj_spec else None
        def _chk_map(v):
            if not isinstance(v, dict):
                return False
            for k, item in v.items():
                if not isinstance(k, str) or (name_pat is not None and name_pat.fullmatch(k) is None):
                    return False
                if not val_chk(item):
                    return False
            return True
        return _chk_map
    props = obj_spec.get("properties", {})
    req = frozenset(obj_spec.get("required", ()))
    allowed = frozenset(props)
    compiled_props = {}
    for k, pspec in props.items():
        if k == "source" and "system" in pspec.get("properties", {}):
            compiled_props[k] = _valid_source_obj
        elif k == "missing_fields":
            compiled_props[k] = lambda v: (isinstance(v, dict) and all(
                isinstance(mk, str) and _PROP_NAME_RE.fullmatch(mk) is not None and mv in _MISSING_ENUM
                for mk, mv in v.items()))
        else:
            compiled_props[k] = _compile_prop_checker(pspec, defs)
    def _chk_obj(v):
        if not isinstance(v, dict):
            return False
        keys = v.keys()
        if not req.issubset(keys) or not (keys <= allowed):
            return False
        for k, val in v.items():
            if not compiled_props[k](val):
                return False
        return True
    return _chk_obj


@lru_cache(maxsize=8)
def _compiled_bundle_validator(version):
    spec = _cached_schema(version)
    defs = spec["$defs"]
    top_props = spec["properties"]
    top_req = frozenset(spec["required"])
    top_allowed = frozenset(top_props)
    table_checkers = {}
    table_min_items = {}
    for tname, tspec in top_props.items():
        if tname in ("contract_version", "tenant_id"):
            continue
        ref_name = tspec["items"]["$ref"].rsplit("/", 1)[-1]
        table_checkers[tname] = _compile_obj_checker(defs[ref_name], defs)
        table_min_items[tname] = tspec.get("minItems", 0)
    return top_req, top_allowed, table_checkers, table_min_items


def _fast_check_core(bundle, scope):
    """Fast exact schema+scope+chronology check; delegates to check_core on any schema/scope failure."""
    if (not isinstance(scope, AccessScope) or not scope.actor_id or not scope.tenant_id
            or "data.import" not in scope.permissions or not scope.company_ids
            or not isinstance(bundle, dict)):
        return check_core(bundle, scope)
    declared_ver = bundle.get("contract_version")
    if not isinstance(declared_ver, str) or declared_ver not in SUPPORTED_CONTRACT_VERSIONS:
        return check_core(bundle, scope)
    top_req, top_allowed, table_checkers, table_min_items = _compiled_bundle_validator(declared_ver)
    bkeys = bundle.keys()
    if not top_req.issubset(bkeys) or not (bkeys <= top_allowed):
        return check_core(bundle, scope)
    tid = bundle.get("tenant_id")
    if not isinstance(tid, str) or _ID_RE.fullmatch(tid) is None or tid != scope.tenant_id:
        return check_core(bundle, scope)
    allowed_companies = scope.company_ids
    for tname, row_chk in table_checkers.items():
        if tname not in bundle:
            continue
        rows = bundle[tname]
        if not isinstance(rows, list) or len(rows) < table_min_items[tname]:
            return check_core(bundle, scope)
        for row in rows:
            if not row_chk(row) or row["tenant_id"] != tid or row["company_id"] not in allowed_companies:
                return check_core(bundle, scope)
    errors = []
    seen = set()
    timelines = defaultdict(list)
    declared_companies = {row["company_id"] for row in bundle["companies"]}
    for table in CORE_TABLES:
        rows = bundle.get(table, ())
        for index, row in enumerate(rows):
            path = f"/{table}/{index}"
            cid = row["company_id"]
            if cid not in declared_companies:
                errors.append(issue("COMPANY_MISSING", path + "/company_id", "Chưa có doanh nghiệp trong danh mục.",
                                    "Bổ sung bản ghi companies trong cùng gói dữ liệu."))
            if table == "companies" and row["record_id"] != cid:
                errors.append(issue("COMPANY_ID", path + "/record_id", "ID danh mục doanh nghiệp không khớp company_id.",
                                    "Dùng cùng mã ở record_id và company_id của doanh nghiệp."))
            identity = (row["tenant_id"], cid, table, row["record_id"], row["revision"])
            if identity in seen:
                errors.append(issue("DUPLICATE_REVISION", path + "/record_id", "Trùng định danh và phiên bản trong doanh nghiệp.",
                                    "Bỏ bản sao nhập trùng; sửa đổi nghiệp vụ phải tạo revision mới."))
            seen.add(identity)
            timelines[(row["tenant_id"], cid, table, row["record_id"])].append((row["revision"], _stamp(row["observed_at"]), path))
    for versions in timelines.values():
        if len(versions) > 1:
            ordered = sorted(versions)
            for previous, current in zip(ordered, ordered[1:]):
                if current[1] < previous[1]:
                    errors.append(issue("REVISION_TIME", current[2] + "/observed_at", "Revision mới có thời điểm biết sớm hơn revision cũ.",
                                        "Kiểm tra revision và observed_at; không ghi lùi lịch sử đã biết."))
    return errors


def _build_p1_company_index(bundle, company):
    """Pre-index company records once so P1 gate runs in O(1) amortized per payment."""
    alloc_revs = defaultdict(list)
    alloc_ids_by_tx = defaultdict(set)
    alloc_ids_by_inv = defaultdict(set)
    for a in bundle.get("payment_allocations", ()):
        if a["company_id"] != company:
            continue
        aid = a["record_id"]
        alloc_revs[aid].append((_stamp(a["observed_at"]), _stamp(a["effective_at"]), a["revision"], a))
        alloc_ids_by_tx[a["transaction_ref"]["record_id"]].add(aid)
        alloc_ids_by_inv[a["invoice_ref"]["record_id"]].add(aid)

    inv_revs = defaultdict(list)
    inv_adj_neighbors = defaultdict(set)
    inv_by_vendor_num = defaultdict(set)
    inv_norm_num = {}
    for inv in bundle.get("invoices", ()):
        if inv["company_id"] != company:
            continue
        iid = inv["record_id"]
        inv_revs[iid].append((_stamp(inv["observed_at"]), _stamp(inv["effective_at"]), inv["revision"], inv))
        adj = inv.get("adjusts_ref")
        if adj:
            inv_adj_neighbors[adj["record_id"]].add(iid)
            inv_adj_neighbors[iid].add(adj["record_id"])
        if inv["kind"] == "invoice" and inv.get("vendor_ref"):
            norm_num = _norm_identity(inv["number"])
            inv_norm_num[id(inv)] = norm_num
            if norm_num:
                inv_by_vendor_num[(inv["vendor_ref"]["record_id"], norm_num)].add(iid)

    tx_revs = defaultdict(list)
    corr_tx_ids_by_target = defaultdict(set)
    for t in bundle.get("transactions", ()):
        if t["company_id"] != company:
            continue
        tid = t["record_id"]
        tx_revs[tid].append((_stamp(t["observed_at"]), _stamp(t["effective_at"]), t["revision"], t))
        adj = t.get("adjusts_ref")
        if adj:
            corr_tx_ids_by_target[adj["record_id"]].add(tid)

    vendor_by_ident = {}
    for v in bundle.get("vendors", ()):
        if v["company_id"] == company:
            vendor_by_ident[(v["record_id"], v["revision"])] = (_stamp(v["observed_at"]), _stamp(v["effective_at"]), v)

    claim_revs = defaultdict(list)
    claim_ids_by_inv = defaultdict(set)
    claim_meta = {}
    for c in bundle.get("payment_history_coverage", ()):
        if c["company_id"] != company:
            continue
        cid_rec = c["record_id"]
        obs_dt = _stamp(c["observed_at"])
        eff_dt = _stamp(c["effective_at"])
        claim_revs[cid_rec].append((obs_dt, eff_dt, c["revision"], c))
        inv_set = frozenset(r["record_id"] for r in c["invoice_refs"])
        for iid in inv_set:
            claim_ids_by_inv[iid].add(cid_rec)
        sig = p1_inputs._bytes({k: c[k] for k in ("covered_from", "covered_through", "history_basis", "coverage_status", "manifest")})
        # Compute manifest validity ONCE per claim in the bundle, not N times!
        expected = _fast_export_manifest(c, inv_set, inv_revs, alloc_revs, alloc_ids_by_inv, tx_revs)
        manifest_ok = (
            c["manifest"]["record_counts"] == expected["record_counts"]
            and c["manifest"]["records_sha256"] == expected["records_sha256"]
            and all(
                sorted(map(p1_inputs._identity, c["manifest"][f])) == sorted(map(p1_inputs._identity, expected[f]))
                for f in p1_inputs.REF_FIELDS.values()
            )
        )
        claim_meta[id(c)] = (inv_set, sig, manifest_ok, obs_dt, _stamp(c["covered_through"]))

    return dict(
        alloc_revs=alloc_revs, alloc_ids_by_tx=alloc_ids_by_tx, alloc_ids_by_inv=alloc_ids_by_inv,
        inv_revs=inv_revs, inv_adj_neighbors=inv_adj_neighbors, inv_by_vendor_num=inv_by_vendor_num,
        inv_norm_num=inv_norm_num,
        tx_revs=tx_revs, corr_tx_ids_by_target=corr_tx_ids_by_target,
        vendor_by_ident=vendor_by_ident,
        claim_revs=claim_revs, claim_ids_by_inv=claim_ids_by_inv, claim_meta=claim_meta,
    )


def _fast_export_manifest(claim, inv_set, inv_revs, alloc_revs, alloc_ids_by_inv, tx_revs):
    known = _stamp(claim["observed_at"])
    start = _stamp(claim["covered_from"])
    end = _stamp(claim["covered_through"])
    since_inc = claim["history_basis"] == "since_inception"
    invoices = [r for iid in inv_set for obs, _eff, _rev, r in inv_revs.get(iid, ()) if obs <= known]
    cand_aids = set()
    for iid in inv_set:
        cand_aids.update(alloc_ids_by_inv.get(iid, ()))
    allocations = [
        r for aid in cand_aids for obs, eff, _rev, r in alloc_revs.get(aid, ())
        if obs <= known and r["invoice_ref"]["record_id"] in inv_set and eff <= end and (since_inc or eff >= start)
    ]
    tx_ids = {a["transaction_ref"]["record_id"] for a in allocations}
    transactions = [r for tid in tx_ids for obs, _eff, _rev, r in tx_revs.get(tid, ()) if obs <= known]
    rows = {
        "invoices": sorted(invoices, key=lambda r: (r["record_id"], r["revision"])),
        "transactions": sorted(transactions, key=lambda r: (r["record_id"], r["revision"])),
        "payment_allocations": sorted(allocations, key=lambda r: (r["record_id"], r["revision"])),
    }
    result = {p1_inputs.REF_FIELDS[t]: [p1_inputs._ref(r) for r in recs] for t, recs in rows.items()}
    result.update(
        record_counts={t: len(r) for t, r in rows.items()},
        records_sha256=hashlib.sha256(p1_inputs._bytes(rows)).hexdigest(),
    )
    return result


def _latest_visible_for_ids(revs_map, ids, cutoff, event):
    out = []
    for rid in ids:
        best = None
        best_rev = -1
        for obs, eff, rev, row in revs_map.get(rid, ()):
            if obs <= cutoff and eff <= event and rev > best_rev:
                best_rev = rev
                best = row
        if best is not None:
            out.append(best)
    return out


_SCOPE_MISSING_GAP = p1_inputs._gap("payment_history_coverage", "invoice_refs", "p1_history_scope_missing")


def _fast_p1_state(idx, tx):
    """Exact O(1) amortized match of p1_inputs.transaction_inputs(bundle, tx)[1]."""
    tx_obs = _stamp(tx["observed_at"])
    event = _stamp(tx["effective_at"])
    cutoff = tx_obs if tx_obs >= event else event
    tid = tx["record_id"]
    cand_cur_aids = idx["alloc_ids_by_tx"].get(tid, ())

    # Ultra-fast exact path for the 99% common case: 1 allocation -> 1 invoice, no adjustments
    if (len(cand_cur_aids) == 1 and tx["kind"] == "payment" and tx.get("payment_channel") in ("bank", "cash")
            and not idx["corr_tx_ids_by_target"].get(tid)):
        only_aid = next(iter(cand_cur_aids))
        a_revs = idx["alloc_revs"].get(only_aid, ())
        t_revs = idx["tx_revs"].get(tid, ())
        if len(a_revs) == 1 and len(t_revs) == 1:
            a_obs, a_eff, _ar, a0 = a_revs[0]
            if a_obs <= cutoff and a_eff <= event and a0["transaction_ref"]["revision"] == tx["revision"]:
                iid = a0["invoice_ref"]["record_id"]
                i_revs = idx["inv_revs"].get(iid, ())
                if (len(i_revs) == 1 and not idx["inv_adj_neighbors"].get(iid)
                        and len(idx["alloc_ids_by_inv"].get(iid, ())) == 1):
                    i_obs, i_eff, i_rev, inv0 = i_revs[0]
                    if (i_obs <= cutoff and i_eff <= event and i_rev == a0["invoice_ref"]["revision"]
                            and inv0["kind"] == "invoice" and not inv0.get("adjusts_ref")):
                        tv = tx.get("vendor_ref")
                        iv = inv0.get("vendor_ref")
                        if tv and iv and tv["record_id"] == iv["record_id"]:
                            n0 = idx["inv_norm_num"].get(id(inv0), "")
                            if len(idx["inv_by_vendor_num"].get((iv["record_id"], n0), ())) <= 1:
                                v_map = idx["vendor_by_ident"]
                                vt = v_map.get((tv["record_id"], tv["revision"]))
                                vi = v_map.get((iv["record_id"], iv["revision"]))
                                if (vt and vt[0] <= cutoff and vt[1] <= event
                                        and vi and vi[0] <= cutoff and vi[1] <= event):
                                    cids = idx["claim_ids_by_inv"].get(iid, ())
                                    if not cids:
                                        return dict(available=False, gaps=[dict(_SCOPE_MISSING_GAP)])
                                    if len(cids) == 1:
                                        only_cid = next(iter(cids))
                                        c_revs = idx["claim_revs"].get(only_cid, ())
                                        if len(c_revs) == 1:
                                            c_obs, c_eff, _cr, c0 = c_revs[0]
                                            if c_obs > cutoff or c_eff > event:
                                                return dict(available=False, gaps=[dict(_SCOPE_MISSING_GAP)])
                                            inv_set_c, _sig_c, manifest_ok_c, claim_obs_c, claim_end_c = idx["claim_meta"][id(c0)]
                                            if (iid in inv_set_c and manifest_ok_c
                                                    and c0["coverage_status"] == "complete"
                                                    and c0["history_basis"] == "since_inception"
                                                    and claim_end_c >= event
                                                    and i_obs <= claim_obs_c and a_obs <= claim_obs_c and tx_obs <= claim_obs_c):
                                                return dict(available=True, gaps=[])

    gaps = []
    current = [
        a for a in _latest_visible_for_ids(idx["alloc_revs"], cand_cur_aids, cutoff, event)
        if a["transaction_ref"]["record_id"] == tid
    ]
    if not current:
        gaps.append(p1_inputs._gap("payment_allocations", "transaction_ref", "p1_current_allocation_missing", tx))

    # Expand obligation_ids using only visible invoices in the connected component
    inv_ids = {a["invoice_ref"]["record_id"] for a in current}
    single_simple = False
    if len(inv_ids) == 1:
        only_iid = next(iter(inv_ids))
        revs_only = idx["inv_revs"].get(only_iid, ())
        if len(revs_only) == 1 and not idx["inv_adj_neighbors"].get(only_iid):
            o0, e0, _rv0, r0 = revs_only[0]
            if o0 <= cutoff and e0 <= event and not r0.get("adjusts_ref"):
                if r0["kind"] == "invoice" and r0.get("vendor_ref"):
                    n0 = _norm_identity(r0["number"])
                    peers0 = idx["inv_by_vendor_num"].get((r0["vendor_ref"]["record_id"], n0), ()) if n0 else ()
                    if len(peers0) <= 1:
                        single_simple = True
    if not single_simple:
        seen_keys = set()
        while True:
            expanded = set(inv_ids)
            for iid in list(inv_ids):
                for obs, eff, _rev, r in idx["inv_revs"].get(iid, ()):
                    if obs <= cutoff and eff <= event:
                        if r.get("adjusts_ref"):
                            expanded.add(r["adjusts_ref"]["record_id"])
                        if r["kind"] == "invoice" and r.get("vendor_ref"):
                            norm_num = _norm_identity(r["number"])
                            if norm_num:
                                vk = (r["vendor_ref"]["record_id"], norm_num)
                                if vk not in seen_keys:
                                    seen_keys.add(vk)
                                    for peer_iid in idx["inv_by_vendor_num"].get(vk, ()):
                                        for p_obs, p_eff, _prev, pr in idx["inv_revs"].get(peer_iid, ()):
                                            if (p_obs <= cutoff and p_eff <= event and pr["kind"] == "invoice"
                                                    and pr.get("vendor_ref")
                                                    and (pr["vendor_ref"]["record_id"], _norm_identity(pr["number"])) == vk):
                                                expanded.add(peer_iid)
                for neighbor_iid in idx["inv_adj_neighbors"].get(iid, ()):
                    for n_obs, n_eff, _nrev, nr in idx["inv_revs"].get(neighbor_iid, ()):
                        if n_obs <= cutoff and n_eff <= event:
                            if (nr.get("adjusts_ref") or {}).get("record_id") in expanded:
                                expanded.add(neighbor_iid)
                            if nr["record_id"] in expanded and nr.get("adjusts_ref"):
                                expanded.add(nr["adjusts_ref"]["record_id"])
            if expanded == inv_ids:
                break
            inv_ids = expanded

    invoice_rows = [
        r for iid in inv_ids
        for obs, eff, _rev, r in idx["inv_revs"].get(iid, ())
        if obs <= cutoff and eff <= event
    ]
    cand_rel_aids = set()
    for iid in inv_ids:
        cand_rel_aids.update(idx["alloc_ids_by_inv"].get(iid, ()))
    related = [
        a for a in _latest_visible_for_ids(idx["alloc_revs"], cand_rel_aids, cutoff, event)
        if a["invoice_ref"]["record_id"] in inv_ids
    ]
    tx_ids = {a["transaction_ref"]["record_id"] for a in related} | {tx["record_id"]}
    tx_rows = [
        r for tid in tx_ids
        for obs, eff, _rev, r in idx["tx_revs"].get(tid, ())
        if obs <= cutoff and eff <= event
    ]
    cand_corr_tids = set()
    for tid in tx_ids:
        cand_corr_tids.update(idx["corr_tx_ids_by_target"].get(tid, ()))
    corrections = [
        r for r in _latest_visible_for_ids(idx["tx_revs"], cand_corr_tids, cutoff, event)
        if (r.get("adjusts_ref") or {}).get("record_id") in tx_ids
    ]
    for row in corrections:
        corr_aids = idx["alloc_ids_by_tx"].get(row["record_id"], ())
        corr_allocs = _latest_visible_for_ids(idx["alloc_revs"], corr_aids, cutoff, event)
        if not any(a["transaction_ref"] == p1_inputs._ref(row) and a["invoice_ref"]["record_id"] in inv_ids for a in corr_allocs):
            gaps.append(p1_inputs._gap("payment_allocations", "transaction_ref", "p1_adjustment_allocation_missing", row))

    tx_rows = list({(r["record_id"], r["revision"]): r for r in tx_rows + corrections}.values())
    by_inv = {p1_inputs._identity(r): r for r in invoice_rows}
    by_tx = {p1_inputs._identity(r): r for r in tx_rows}
    if tx.get("payment_channel") not in ("bank", "cash"):
        gaps.append(p1_inputs._gap("transactions", "payment_channel", "p1_channel_missing_or_unsupported", tx))
    for row in tx_rows:
        if row.get("payment_channel") not in ("bank", "cash"):
            gaps.append(p1_inputs._gap("transactions", "payment_channel", "p1_channel_missing_or_unsupported", row))
        if row["kind"] not in ("payment", "adjustment", "reversal"):
            gaps.append(p1_inputs._gap("transactions", "kind", "p1_transaction_kind_unsupported", row))
    current_ids = {id(a) for a in current}
    for a in related:
        t = by_tx.get(p1_inputs._identity(a["transaction_ref"]))
        inv = by_inv.get(p1_inputs._identity(a["invoice_ref"]))
        if t is None:
            gaps.append(p1_inputs._gap("transactions", "transaction_ref", "referenced_revision_unavailable", a))
        if inv is None:
            gaps.append(p1_inputs._gap("invoices", "invoice_ref", "referenced_revision_unavailable", a))
        if id(a) in current_ids and a["transaction_ref"]["revision"] != tx["revision"]:
            gaps.append(p1_inputs._gap("payment_allocations", "transaction_ref", "p1_current_revision_mismatch", a))
        if t and inv and (not t.get("vendor_ref") or not inv.get("vendor_ref")
                          or t["vendor_ref"]["record_id"] != inv["vendor_ref"]["record_id"]):
            gaps.append(p1_inputs._gap("payment_allocations", "invoice_ref", "p1_vendor_link_unresolved", a))
    v_map = idx["vendor_by_ident"]
    for row in invoice_rows + tx_rows:
        ref = row.get("vendor_ref")
        v_entry = v_map.get(p1_inputs._identity(ref)) if ref else None
        if not (v_entry and v_entry[0] <= cutoff and v_entry[1] <= event):
            gaps.append(p1_inputs._gap("vendors", "vendor_ref", "referenced_revision_unavailable", row))

    for identity in sorted(inv_ids):
        cand_cids = idx["claim_ids_by_inv"].get(identity, ())
        vis_claims = _latest_visible_for_ids(idx["claim_revs"], cand_cids, cutoff, event)
        candidates = [c for c in vis_claims if identity in idx["claim_meta"][id(c)][0]]
        if not candidates:
            gaps.append(p1_inputs._gap("payment_history_coverage", "invoice_refs", "p1_history_scope_missing"))
            continue
        newest = max(idx["claim_meta"][id(c)][3] for c in candidates)
        top = [c for c in candidates if idx["claim_meta"][id(c)][3] == newest]
        signatures = {idx["claim_meta"][id(c)][1] for c in top}
        if len(signatures) > 1:
            gaps.append(p1_inputs._gap("payment_history_coverage", "manifest", "p1_history_scope_conflict"))
            continue
        claim = sorted(top, key=lambda c: (c["record_id"], c["revision"]))[0]
        _inv_set, _sig, manifest_ok, claim_obs, claim_end = idx["claim_meta"][id(claim)]
        if not manifest_ok:
            gaps.append(p1_inputs._gap("payment_history_coverage", "manifest", "p1_history_manifest_mismatch", claim))
        if claim["coverage_status"] != "complete" or claim["history_basis"] != "since_inception":
            gaps.append(p1_inputs._gap("payment_history_coverage", "coverage_status", "p1_history_scope_partial_or_unknown", claim))
        if claim_end < event:
            gaps.append(p1_inputs._gap("payment_history_coverage", "covered_through", "p1_history_scope_ends_before_transaction", claim))
        relevant_rows = [r for r in invoice_rows if r["record_id"] == identity]
        related_allocs = [a for a in related if a["invoice_ref"]["record_id"] == identity]
        relevant_rows += related_allocs
        related_tx = {a["transaction_ref"]["record_id"] for a in related_allocs}
        relevant_rows += [r for r in tx_rows if r["record_id"] in related_tx]
        if any(_stamp(r["observed_at"]) > claim_obs for r in relevant_rows):
            gaps.append(p1_inputs._gap("payment_history_coverage", "manifest", "p1_history_scope_stale", claim))

    if not gaps:
        return dict(available=True, gaps=[])
    if len(gaps) == 1:
        return dict(available=False, gaps=gaps)
    unique = {p1_inputs._bytes(g): g for g in gaps}
    return dict(available=False, gaps=[unique[k] for k in sorted(unique)])


def _fast_validate_p1_sources(bundle, lookup):
    """Exact match of p1_inputs.validate_p1_sources using cached _stamp and single-pass manifest."""
    errors = []
    warnings = []
    claims = bundle.get("payment_history_coverage", [])
    if claims:
        for index, claim in enumerate(claims):
            path = f"/payment_history_coverage/{index}"
            start = _stamp(claim["covered_from"])
            end = _stamp(claim["covered_through"])
            known = _stamp(claim["observed_at"])
            if start > end or end > known or _stamp(claim["effective_at"]) > end:
                errors.append(issue("P1_COVERAGE_TIME", path + "/covered_through",
                    "Phạm vi lịch sử sai thứ tự hoặc kết thúc sau thời điểm nguồn được biết.",
                    "Dùng covered_from <= covered_through <= observed_at và effective_at phù hợp; không khai báo phủ tương lai."))
                continue
            ref_groups = {"invoice_refs": claim["invoice_refs"], **{
                "manifest/" + f: claim["manifest"][f] for f in p1_inputs.REF_FIELDS.values()
            }}
            for field, refs in ref_groups.items():
                seen_r = set()
                for r in refs:
                    ident = (r["record_id"], r["revision"])
                    if ident in seen_r:
                        errors.append(issue("P1_DUPLICATE_MANIFEST_REF", path + "/" + field, "Manifest/scope có tham chiếu trùng.",
                            "Giữ một tham chiếu cho mỗi ID/revision; không bỏ phiên bản khác."))
                        break
                    seen_r.add(ident)
            ctid, ccid = claim["tenant_id"], claim["company_id"]
            for field, table in (("invoice_refs", "invoices"), ("manifest/invoice_refs", "invoices"),
                                 ("manifest/transaction_refs", "transactions"), ("manifest/allocation_refs", "payment_allocations")):
                refs = claim["invoice_refs"] if field == "invoice_refs" else claim["manifest"][field.split("/")[1]]
                for pos, ref in enumerate(refs):
                    row = lookup.get((ctid, ccid, table, ref["record_id"], ref["revision"]))
                    if row and _stamp(row["observed_at"]) > known:
                        errors.append(issue("P1_COVERAGE_REFERENCE_TIME", f"{path}/{field}/{pos}",
                            "Manifest tham chiếu nguồn chỉ được biết sau khai báo phạm vi.",
                            "Tạo revision phạm vi mới với observed_at thực sau khi nguồn được biết; không lùi thời gian."))
            ids = {r["record_id"] for r in claim["invoice_refs"]}
            since_inc = claim["history_basis"] == "since_inception"
            invoices = sorted(
                (r for r in bundle.get("invoices", ())
                 if r["tenant_id"] == ctid and r["company_id"] == ccid and r["record_id"] in ids and _stamp(r["observed_at"]) <= known),
                key=lambda r: (r["record_id"], r["revision"]),
            )
            allocations = sorted(
                (r for r in bundle.get("payment_allocations", ())
                 if r["tenant_id"] == ctid and r["company_id"] == ccid and r["invoice_ref"]["record_id"] in ids
                 and _stamp(r["observed_at"]) <= known and _stamp(r["effective_at"]) <= end
                 and (since_inc or _stamp(r["effective_at"]) >= start)),
                key=lambda r: (r["record_id"], r["revision"]),
            )
            tx_ids = {a["transaction_ref"]["record_id"] for a in allocations}
            transactions = sorted(
                (r for r in bundle.get("transactions", ())
                 if r["tenant_id"] == ctid and r["company_id"] == ccid and r["record_id"] in tx_ids and _stamp(r["observed_at"]) <= known),
                key=lambda r: (r["record_id"], r["revision"]),
            )
            declared_rows = dict(invoices=invoices, transactions=transactions, payment_allocations=allocations)
            expected_refs = {p1_inputs.REF_FIELDS[t]: [p1_inputs._ref(r) for r in recs] for t, recs in declared_rows.items()}
            expected_counts = {t: len(recs) for t, recs in declared_rows.items()}
            expected_sha = hashlib.sha256(p1_inputs._bytes(declared_rows)).hexdigest()
            for field in p1_inputs.REF_FIELDS.values():
                if sorted(map(p1_inputs._identity, claim["manifest"][field])) != sorted(map(p1_inputs._identity, expected_refs[field])):
                    errors.append(issue("P1_MANIFEST_MEMBERSHIP", path + "/manifest/" + field,
                        "Danh sách manifest không khớp toàn bộ nguồn đã gửi thuộc phạm vi khai báo.",
                        "Xuất lại danh sách ID/revision và checksum từ cùng nguồn; không tự bỏ bản ghi hoặc dùng manifest cũ."))
            for table, count in expected_counts.items():
                if claim["manifest"]["record_counts"][table] != count:
                    errors.append(issue("P1_MANIFEST_COUNT", path + "/manifest/record_counts/" + table,
                        "Số bản ghi khai báo không khớp nguồn trong phạm vi.", "Xuất lại manifest từ đúng dữ liệu canonical và phạm vi."))
            if claim["manifest"]["records_sha256"] != expected_sha:
                errors.append(issue("P1_MANIFEST_CHECKSUM", path + "/manifest/records_sha256",
                    "Dữ liệu đã đổi hoặc manifest không được tạo từ đúng nguồn canonical.",
                    "Kiểm tra file/mapping và xuất lại manifest; không tái dùng kết quả kiểm tra cũ."))
            if since_inc and (any(_stamp(a["effective_at"]) < start for a in allocations)
                              or any(_stamp(inv["effective_at"]) < start for inv in invoices)):
                errors.append(issue("P1_COVERAGE_RANGE", path + "/covered_from",
                    "Có hóa đơn hoặc phân bổ cùng scope trước mốc bắt đầu dù nguồn khai báo từ đầu lịch sử.",
                    "Đối chiếu và khai báo lại phạm vi thực; không loại dữ liệu trước mốc hoặc coi số đã trả là 0."))
    for index, a in enumerate(bundle.get("payment_allocations", ())):
        tid, cid = a["tenant_id"], a["company_id"]
        tref = a["transaction_ref"]
        iref = a["invoice_ref"]
        tx = lookup.get((tid, cid, "transactions", tref["record_id"], tref["revision"]))
        inv = lookup.get((tid, cid, "invoices", iref["record_id"], iref["revision"]))
        if tx and inv and tx.get("vendor_ref") and inv.get("vendor_ref") and tx["vendor_ref"]["record_id"] != inv["vendor_ref"]["record_id"]:
            warnings.append(issue("P1_VENDOR_MISMATCH", f"/payment_allocations/{index}/invoice_ref",
                "NCC của giao dịch và hóa đơn chưa khớp; chưa đủ căn cứ đối chiếu P1.",
                "Đối chiếu nghĩa vụ, người nhận hoặc hồ sơ chi hộ; không tự đổi liên kết hay kết luận gian lận."))
    return errors, warnings


def parse_vnd(value):
    """Adapter boundary only: exact signed VND, no float/grouping/rounding.

    Canonical bundles already require integers. CSV localized or ambiguous text
    must be mapped/confirmed upstream; it is never guessed here.
    """
    if isinstance(value, str) and not _VND_RE.fullmatch(value):
        raise ValueError("Dùng số nguyên VND hoặc chuỗi thập phân chuẩn, không dấu phân nhóm.")
    result = minor(value, "VND")
    if abs(result) > 999999999999999999:
        raise ValueError("Số tiền vượt 18 chữ số VND.")
    return result


def _references(table, row):
    for field, target in _REF_MAP.get(table, {}).items():
        if row.get(field) is not None:
            yield field, target, row[field]
    for index, target in enumerate(row.get("subject_refs", ())):
        yield f"subject_refs/{index}", target["table"], target
    if table=='payment_history_coverage':
        for index,ref in enumerate(row['invoice_refs']):yield f'invoice_refs/{index}','invoices',ref
        for name,target in (('invoice_refs','invoices'),('transaction_refs','transactions'),('allocation_refs','payment_allocations')):
            for index,ref in enumerate(row['manifest'][name]):yield f'manifest/{name}/{index}',target,ref


def validate_input(bundle, scope):
    """Backend report for a closed, company-scoped bundle. No rows are dropped.

    Report is not a commit token. Snapshot store, report hashes and authentication
    integration are intentionally left for the remaining R1 work.
    """
    if isinstance(bundle,dict) and bundle.get('contract_version')=='agent2-rule-snapshot/1.0.0':
        from .rule_snapshot import validate
        return validate(bundle,scope)
    errors = _fast_check_core(bundle, scope)
    declared=bundle.get('contract_version') if isinstance(bundle,dict) else None
    contract=declared if isinstance(declared,str) and declared in SUPPORTED_CONTRACT_VERSIONS else CONTRACT_VERSION
    report = dict(contract_version=contract, validator_version=VALIDATOR_VERSION,
                  profile_version=PROFILE_VERSION, status="rejected", errors=errors,
                  report_version=REPORT_VERSION, warnings=[], counts={}, capabilities={}, analysis_limits={})
    if errors:
        return report
    warnings = report["warnings"]
    definitions = _cached_schema(contract)["$defs"]
    lookup = {}
    row_paths = {}
    for table, index, row in records(bundle):
        k = key(table, row)
        lookup[k] = row
        row_paths[k] = f"/{table}/{index}"
    adjustment_edges = {}
    has_verify_perm = "evidence.verify" in scope.permissions
    for table, index, row in records(bundle):
        path = f"/{table}/{index}"
        row_obs = _stamp(row["observed_at"])
        row_tid = row["tenant_id"]
        row_cid = row["company_id"]
        for field, target, reference in _references(table, row):
            target_key = (row_tid, row_cid, target,
                          reference["record_id"], reference["revision"])
            linked = lookup.get(target_key)
            if linked is None:
                errors.append(issue("REFERENCE_MISSING", f"{path}/{field}",
                    "Không tìm thấy bản ghi được tham chiếu trong cùng doanh nghiệp và revision.",
                    "Bổ sung bản ghi nguồn hoặc sửa tham chiếu; không dùng bản ghi của doanh nghiệp khác."))
            elif target_key == (row_tid, row_cid, table, row["record_id"], row["revision"]):
                errors.append(issue("SELF_REFERENCE", f"{path}/{field}", "Bản ghi không thể điều chỉnh chính nó.",
                                    "Dẫn định danh và revision của bản ghi gốc."))
            else:
                linked_obs = _stamp(linked["observed_at"])
                if field == "adjusts_ref" and linked_obs > row_obs:
                    errors.append(issue("ADJUSTMENT_TIME", f"{path}/{field}", "Điều chỉnh được biết trước bản ghi gốc.",
                                        "Kiểm tra thời điểm nguồn được biết của hai bản ghi."))
                elif linked_obs > row_obs:
                    warnings.append(issue("REFERENCE_KNOWN_LATER", f"{path}/{field}",
                        "Nguồn liên quan chỉ được biết sau bản ghi này.",
                        "Giữ thời điểm nguồn; khi chấm quá khứ không dùng nguồn đến muộn."))
                if field == "adjusts_ref":
                    adjustment_edges[(row_tid, row_cid, table, row["record_id"], row["revision"])] = target_key
        adjustment = row.get("kind") in {"adjustment", "reversal", "credit_note"}
        if table in {"transactions", "invoices", "payment_allocations"}:
            amt = row["amount_vnd"]
            if (amt < 0 or adjustment) and (
                not adjustment or not row.get("adjustment_reason", "").strip() or not row.get("adjusts_ref")
            ):
                field = "kind" if not adjustment else "adjustment_reason" if not row.get("adjustment_reason", "").strip() else "adjusts_ref"
                errors.append(issue("ADJUSTMENT_CONTEXT", path+"/"+field,
                    "Số âm hoặc khoản điều chỉnh cần loại, lý do và bản ghi gốc.",
                    "Chọn adjustment/reversal/credit_note phù hợp và bổ sung adjustment_reason, adjusts_ref; giữ nguyên dấu tiền."))
            if amt == 0:
                warnings.append(issue("ZERO_AMOUNT", path+"/amount_vnd", "Bản ghi có số tiền bằng 0.", "Xác nhận đây là bản ghi hợp lệ; không tự bỏ dòng."))
        missing_f = row.get("missing_fields")
        if missing_f:
            definition = definitions[DEFINITIONS[table]]
            def_props = definition["properties"]
            def_req = definition["required"]
            for field in missing_f:
                if field not in def_props or field in def_req or row.get(field) is not None:
                    errors.append(issue("MISSING_CONFLICT", f"{path}/missing_fields/{field}",
                        "Trạng thái thiếu mâu thuẫn với trường dữ liệu.",
                        "Chỉ ghi trạng thái thiếu cho cột tùy chọn chưa có giá trị; không gắn cho cột bắt buộc."))
        if table=='vendors' and row.get('related_party_disclosed_at') and _stamp(row['related_party_disclosed_at'])>row_obs:
            errors.append(issue('DISCLOSURE_TIME',path+'/related_party_disclosed_at',
                'Ngày khai báo quan hệ sau thời điểm nguồn được biết.',
                'Ghi đúng observed_at của revision nhận khai báo; không lùi thời gian nguồn.'))
        verification_status = row.get("verification_status")
        verification = row.get("verification")
        if verification_status == "verified":
            if not has_verify_perm:
                errors.append(issue("VERIFICATION_PERMISSION", path+"/verification_status", "Chưa có quyền xác nhận nguồn đã được xác minh.",
                                    "Giữ unverified hoặc chuyển người có quyền evidence.verify đối chiếu căn cứ."))
            if not verification:
                errors.append(issue("VERIFICATION_MISSING", path+"/verification", "Đã xác minh nhưng chưa ghi người, thời điểm và căn cứ.",
                                    "Bổ sung verification hoặc giữ trạng thái chưa xác minh."))
            elif _stamp(verification["verified_at"]) > row_obs:
                errors.append(issue("VERIFICATION_TIME", path+"/verification/verified_at", "Xác minh diễn ra sau thời điểm được biết của revision này.",
                                    "Tạo revision mới với observed_at đúng thời điểm xác minh được biết."))
        elif verification:
            errors.append(issue("VERIFICATION_CONFLICT", path+"/verification_status", "Thông tin xác minh không khớp trạng thái.",
                                "Dùng trạng thái verified khi đã có đủ căn cứ xác minh."))
        if table == "supporting_documents" and (row["source_kind"] == "simulated") != row["source"]["is_simulated"]:
            errors.append(issue("SOURCE_KIND_CONFLICT", path+"/source_kind", "Loại chứng từ không khớp nguồn mô phỏng.",
                                "Giữ rõ simulated cho chứng từ mô phỏng; không đổi thành bản gốc."))
    # Iterative walk avoids recursion limits for large correction histories.
    completed = set()
    for start in adjustment_edges:
        visited = set()
        current = start
        while current in adjustment_edges and current not in completed:
            if current in visited:
                errors.append(issue("ADJUSTMENT_CYCLE", row_paths[start]+"/adjusts_ref", "Tham chiếu điều chỉnh tạo vòng lặp.",
                                    "Dẫn chuỗi điều chỉnh tới bản ghi gốc, không tạo vòng."))
                break
            visited.add(current)
            current = adjustment_edges[current]
        completed.update(visited)
    if not any(e['code']!='VERIFICATION_PERMISSION' for e in errors):
        p1_errors,p1_warnings=_fast_validate_p1_sources(bundle, lookup)
        errors.extend(p1_errors);warnings.extend(p1_warnings)
    report["counts"] = {table: len(rows) for table, rows in bundle.items() if isinstance(rows, list)}
    if errors:
        return report  # a rejected bundle never advertises usable capabilities
    for company in sorted({r["company_id"] for r in bundle["companies"]}):
        rows = {t: [r for r in bundle.get(t, []) if r["company_id"] == company]
                for t in ("transactions", "vendor_bank_history", "payment_allocations", "supporting_documents")}
        caps = {}
        for name, table in (("transaction_input", "transactions"), ("bank_change_input", "vendor_bank_history"),
                            ("invoice_payment_links", "payment_allocations"), ("document_input", "supporting_documents")):
            available = bool(rows[table])
            caps[name] = dict(available=available, reason="records_present" if available else "not_provided")
            if not available:
                warnings.append(issue("CAPABILITY_UNAVAILABLE", f"/{table}",
                    f"{company}: chưa có dữ liệu cho {name}.", "Bổ sung nguồn khi cần phân tích này; các phần có dữ liệu vẫn được giữ."))
        report["capabilities"][company] = caps
        limits = analysis_limits(bundle, company)
        has_payments = any(r["kind"] == "payment" for r in p1_inputs._latest(rows["transactions"]))
        p1_unavail = any(l["code"] == "P1_INPUT_UNAVAILABLE" for l in limits)
        p1_ok = has_payments and not p1_unavail
        caps['p1_input']=dict(available=p1_ok,
            reason='source_declared_inputs_present' if p1_ok else 'p1_sources_missing_or_limited')
        report["analysis_limits"][company] = limits
        for limit in limits:
            detail = issue(limit["code"], "/transactions", limit["message"], limit["action"])
            detail.update(company_id=company, affected_count=limit["affected_count"])
            warnings.append(detail)
    report["status"] = "accepted_with_warnings" if warnings else "accepted"
    return report


def analysis_limits(bundle, company):
    """Source coverage in this bundle, not detector readiness or a risk verdict.

    Current record revisions are used so an older verified document cannot mask a
    later unverified revision. Historical feature coverage is assessed at replay.
    """
    latest_by_table = defaultdict(dict)
    for table in CORE_TABLES:
        for index, row in enumerate(bundle.get(table, ())):
            if row["company_id"] != company:
                continue
            rid = row["record_id"]
            prev = latest_by_table[table].get(rid)
            if prev is None or row["revision"] > prev[1]["revision"]:
                latest_by_table[table][rid] = (index, row)
    txs = list(latest_by_table["transactions"].values())
    source_rows = lambda name: [r for _, r in latest_by_table[name].values()]
    allocations = source_rows("payment_allocations")
    invoices_by_tx = {}
    for row in allocations:
        target = row["transaction_ref"]
        invoices_by_tx.setdefault((target["record_id"], target["revision"]), set()).add(
            ("invoices", row["invoice_ref"]["record_id"], row["invoice_ref"]["revision"]))
    original_subjects = set()
    for row in source_rows("supporting_documents"):
        if row["source_kind"] == "original" and not row["source"]["is_simulated"] and row["verification_status"] == "verified":
            original_subjects.update((r["table"], r["record_id"], r["revision"]) for r in row["subject_refs"])
    bank_vendors = {(r["vendor_ref"]["record_id"], r["vendor_ref"]["revision"]) for r in source_rows("vendor_bank_history")}
    approved = {(r["transaction_ref"]["record_id"], r["transaction_ref"]["revision"]) for r in source_rows("approvals") if r["decision"] == "approved"}
    missing_docs = []; missing_bank = []; missing_invoice = []; missing_approval = []
    for index, row in txs:
        identity = (row["record_id"], row["revision"])
        subjects = {("transactions", *identity)} | invoices_by_tx.get(identity, set())
        entry = dict(table="transactions", row=index+1, record_id=row["record_id"], revision=row["revision"])
        if not subjects.intersection(original_subjects):
            missing_docs.append(entry)
        vendor = row.get("vendor_ref")
        if vendor and (vendor["record_id"], vendor["revision"]) not in bank_vendors:
            missing_bank.append(entry)
        if row["kind"] == "payment" and identity not in invoices_by_tx:
            missing_invoice.append(entry)
        if row["kind"] in {"payment", "payroll"} and identity not in approved:
            missing_approval.append(entry)
    limits = []
    p1_missing=[]
    payment_txs = [(index, row) for index, row in txs if row['kind'] == 'payment']
    if payment_txs:
        p1_idx = _build_p1_company_index(bundle, company)
        for index, row in payment_txs:
            state = _fast_p1_state(p1_idx, row)
            if not state['available']:
                p1_missing.append(dict(table='transactions',row=index+1,record_id=row['record_id'],revision=row['revision'],gaps=state['gaps']))
    if p1_missing:
        limits.append(dict(code='P1_INPUT_UNAVAILABLE',analysis='p1_input',
            message='P1 chưa đủ đầu vào kênh/liên kết/phạm vi lịch sử đã khai báo; không thay lịch sử thiếu bằng 0.',
            action='Xem gaps từng giao dịch; bổ sung nguồn theo contract 1.1.0 và xuất lại manifest, không suy từ tài khoản hoặc số tiền.',
            affected_count=len(p1_missing),affected_rows=p1_missing[:20],affected_rows_truncated=len(p1_missing)>20,
            coverage_basis='source_declared_manifest_not_complete_external_books'))
    for code, analysis, affected, message, action in [
        ("DOCUMENT_BASIS_MISSING", "document_verification", missing_docs,
         "Có giao dịch chưa có chứng từ gốc đã xác minh gắn với giao dịch hoặc hóa đơn liên quan; chưa đủ căn cứ kết luận nghiệp vụ.",
         "Bổ sung và đối chiếu chứng từ đúng giao dịch/nghĩa vụ. Bản mô phỏng hoặc bản xuất không tự là chứng từ gốc đã xác minh."),
        ("BANK_HISTORY_MISSING", "bank_change_analysis", missing_bank,
         "Chưa có lịch sử tài khoản tương ứng của NCC cho một số giao dịch; chưa đánh giá được thay đổi tài khoản từ nguồn hiện có.",
         "Bổ sung bank history có thời điểm hiệu lực và thời điểm được biết; không giả lịch sử từ tài khoản hiện tại."),
        ("INVOICE_LINK_MISSING", "payment_reconciliation", missing_invoice,
         "Có khoản thanh toán chưa có liên kết phân bổ hóa đơn; chưa đối chiếu được nghĩa vụ và số đã trả cho các khoản này.",
         "Bổ sung payment_allocations và hóa đơn có nguồn; không tự gán một hóa đơn theo số tiền gần giống."),
        ("APPROVAL_BASIS_MISSING", "approval_trace", missing_approval,
         "Chưa có bản ghi phê duyệt approved gắn với một số khoản chi/lương; chưa xác nhận được dấu vết phê duyệt.",
         "Bổ sung nguồn phê duyệt phù hợp chính sách. Thiếu bản ghi không tự chứng minh khoản chi chưa được duyệt."),
    ]:
        if affected:
            limits.append(dict(code=code, analysis=analysis, message=message, action=action,
                               affected_count=len(affected), affected_rows=affected[:20],
                               affected_rows_truncated=len(affected)>20, coverage_basis="submitted_bundle_current_revisions"))
    return limits


def records_as_of(bundle, scope, as_of):
    """Select visible revisions, not features or a persistent DataSnapshot.

    Effective and observed times both constrain visibility. Late-arriving revisions
    cannot overwrite old knowledge. Simultaneous feature replay remains R1 work.
    """
    report = validate_input(bundle, scope)
    if report["status"] == "rejected":
        raise ValueError("Không thể đọc gói bị từ chối; xem ValidationReport.")
    cutoff = _stamp(as_of)
    visible = {}
    for table, _, row in records(bundle):
        if _stamp(row["observed_at"]) > cutoff or _stamp(row["effective_at"]) > cutoff:
            continue
        identity = key(table, row)[:-1]
        old = visible.get(identity)
        if old is None or row["revision"] > old["revision"]:
            visible[identity] = row
    result = {table: [] for table, _, _ in records(bundle)}
    for identity, row in sorted(visible.items()):
        result[identity[2]].append(deepcopy(row))
    return result
