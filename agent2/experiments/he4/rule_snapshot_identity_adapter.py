"""Slice 3 prototype adapters: identity rules `B1`, `B5`, `E4` on bounded `circuits.graph`.

Reuses the verified 4-node x 4-field SHA-256 encrypted nibble equality circuit
(`build-graph-difference-v1`), keeping:
- Ambiguous bare bank-account match (`missing bank_code`) separate from strong `bank_identity`
- Disclosed related-party downgrades (`weight=4, hard_trigger=0`)
- Vendor `B5`/`E4` `shared_address_only` weak vs `shared_bank_or_phone` strong
- Single `master_quality` / `master_duplicate` family (no B5+E4 double count)
- Explicit `he_graph_node_limit` (`unavailable`) whenever > 4 entities are needed (never sliced)
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import re

import numpy as np

from . import circuits as c
from sme_fraud.identity import normalize
from sme_fraud.import_files import canonical, digest, fail
from sme_fraud.native_rule_node import _gaps, validate_bundle
from sme_fraud.rule_snapshot import CONTRACT, validate as validate_rule_snapshot
from sme_fraud.temporal_evidence import EmployeeHistory, bank_identity, bank_token


def _token_nibbles(slot_name: str, value: str) -> list[int]:
    hex_digest = hashlib.sha256((slot_name + '\x00' + value).encode('utf-8')).hexdigest()
    return [int(ch, 16) for ch in hex_digest]


def _empty_graph_inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.zeros((c.GRAPH_NODES, c.GRAPH_FIELDS, c.TOKEN_DIGITS), dtype=np.int64),
        np.zeros((c.GRAPH_NODES, c.GRAPH_FIELDS), dtype=np.int64),
        np.zeros(c.GRAPH_NODES, dtype=np.int64),
    )


def _decode_links(raw_out: list[int] | np.ndarray) -> np.ndarray:
    arr = np.asarray(raw_out, dtype=np.int64)
    if arr.shape != (c.GRAPH_FIELDS * c.GRAPH_NODES * c.GRAPH_NODES + c.GRAPH_NODES * c.GRAPH_NODES,):
        raise ValueError('invalid graph circuit output shape')
    return arr[: c.GRAPH_FIELDS * c.GRAPH_NODES * c.GRAPH_NODES].reshape((c.GRAPH_FIELDS, c.GRAPH_NODES, c.GRAPH_NODES))


def plan_b1_from_rule_snapshot(data: dict, scope) -> dict:
    """Plan bounded encrypted graph checks for rule `B1` (`1 tx/vendor + <=3 employees`)."""
    if data.get('contract_version') != CONTRACT:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Yêu cầu profile agent2-rule-snapshot/1.0.0.', 'Xuất lại đúng profile.')
    report = validate_rule_snapshot(data, scope, committed=True)
    if report['status'] == 'rejected':
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Snapshot nguồn luật không hợp lệ.', 'Kiểm tra lại schema và coverage.')

    source = data['source']
    as_of = source['as_of']
    checked = validate_bundle(source, scope)
    if checked['status'] != 'accepted':
        fail(422, 'NATIVE_RULE_SOURCE_INVALID', 'Bundle nguồn luật không hợp lệ.', 'Sửa lỗi nguồn.')

    tables = source['tables']
    visible_txs = {
        r['transaction_id']: deepcopy(r)
        for r in tables.get('transactions', [])
        if r.get('observed_at', '') <= as_of and r.get('posted_at', '') <= as_of
    }
    staff_history = EmployeeHistory([r for r in tables.get('employees', []) if r.get('observed_at', '') <= as_of])
    vendor_rows = sorted(
        [r for r in tables.get('vendors', []) if r.get('observed_at', '') <= as_of],
        key=lambda r: (r['observed_at'], r['vendor_id']),
    )
    b1_gaps = list(_gaps(source, 'B1'))

    rows_plan = []
    for cid in data['candidate_transaction_ids']:
        tx = visible_txs.get(cid)
        if tx is None:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason='transaction_not_known_at_cutoff', requests=[])
            )
            continue
        if b1_gaps:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason=b1_gaps[0].get('reason', 'rule_sources_unavailable'),
                    gaps=deepcopy(b1_gaps),
                    requests=[],
                )
            )
            continue

        now = tx['posted_at']
        vid = tx.get('vendor_id', '')
        vendors_now = {r['vendor_id']: r for r in vendor_rows if r['observed_at'] <= now}
        vendor = vendors_now.get(vid)
        financial = int(tx.get('is_financial_entry', 0)) == 1
        vendor_outflow = bool(
            vendor
            and financial
            and tx.get('payment_channel') in {'bank', 'cash'}
            and str(tx.get('credit_account', '')).startswith(('111', '112'))
            and vid
        )
        if not vendor_outflow:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=True, status='evaluated_no_hit', reason=None, requests=[])
            )
            continue

        company_staff = sorted(
            (e for e in staff_history.at(now).values() if e['company_id'] == tx['company_id']),
            key=lambda e: e['employee_id'],
        )
        if 1 + len(company_staff) > c.GRAPH_NODES:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason='he_graph_node_limit', requests=[])
            )
            continue

        tokens, known, active = _empty_graph_inputs()
        active[0] = 1
        tx_bank_id = bank_identity(tx.get('recipient_account'), tx.get('recipient_bank_code', ''))
        tx_bank_num = bank_token(tx.get('recipient_account'))
        v_nat = bank_token(vendor.get('national_id'))
        v_nat = v_nat if re.fullmatch(r'(?:\d{9}|\d{12})', v_nat) else ''
        if tx_bank_id:
            tokens[0, 0] = _token_nibbles('bank_identity', tx_bank_id)
            known[0, 0] = 1
        if v_nat:
            tokens[0, 1] = _token_nibbles('national_id', v_nat)
            known[0, 1] = 1
        if tx_bank_num:
            tokens[0, 2] = _token_nibbles('bank_number', tx_bank_num)
            known[0, 2] = 1

        emp_slots = []
        for idx_emp, emp in enumerate(company_staff, start=1):
            active[idx_emp] = 1
            e_bank_id = bank_identity(emp.get('bank_account'), emp.get('bank_code', ''))
            e_bank_num = bank_token(emp.get('bank_account'))
            e_nat = bank_token(emp.get('national_id'))
            e_nat = e_nat if re.fullmatch(r'(?:\d{9}|\d{12})', e_nat) else ''
            if e_bank_id:
                tokens[idx_emp, 0] = _token_nibbles('bank_identity', e_bank_id)
                known[idx_emp, 0] = 1
            if e_nat:
                tokens[idx_emp, 1] = _token_nibbles('national_id', e_nat)
                known[idx_emp, 1] = 1
            if e_bank_num:
                tokens[idx_emp, 2] = _token_nibbles('bank_number', e_bank_num)
                known[idx_emp, 2] = 1
            emp_slots.append(
                dict(
                    slot=idx_emp,
                    employee_id=emp['employee_id'],
                    ambiguous_possible=(not tx_bank_id) or (not e_bank_id),
                )
            )

        if not np.any(known):
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=True, status='evaluated_no_hit', reason=None, requests=[])
            )
            continue

        disclosed = bool(vendor.get('related_party_disclosed_at') and vendor['related_party_disclosed_at'] <= now)
        rows_plan.append(
            dict(
                record_id=cid,
                transaction_id=cid,
                available=True,
                status='ready',
                reason=None,
                disclosed=disclosed,
                employee_slots=emp_slots,
                requests=[
                    dict(
                        profile='graph',
                        rule_id='B1',
                        role='row',
                        values=[tokens.tolist(), known.tolist(), active.tolist()],
                        source_refs=dict(
                            transaction_id=cid,
                            vendor_id=vid,
                            employee_ids=[s['employee_id'] for s in emp_slots],
                        ),
                    )
                ],
            )
        )

    return dict(
        version='he4-rule-snapshot-b1-plan/1.0.0',
        contract_version=CONTRACT,
        company_id=data['company_id'],
        tenant_id=data['tenant_id'],
        as_of=as_of,
        rule_id='B1',
        profile='graph',
        source_sha256=digest(canonical(source)),
        rows=rows_plan,
    )


def decode_b1_plan_results(plan: dict, decrypted_outputs: list[list[int]]) -> dict:
    """Decode `circuits.graph` outputs for B1, preserving disclosed & ambiguity roles."""
    idx = 0
    rows_out = []
    for entry in plan['rows']:
        reqs = entry.get('requests', [])
        outputs = decrypted_outputs[idx : idx + len(reqs)]
        idx += len(reqs)
        if not entry['available']:
            rows_out.append(
                dict(transaction_id=entry['transaction_id'], available=False, status='unavailable', matched=None, score=None, hard_trigger=None, reason=entry['reason'])
            )
            continue
        if not reqs:
            rows_out.append(
                dict(transaction_id=entry['transaction_id'], available=True, status='evaluated_no_hit', matched=False, score=0, hard_trigger=0, reason=None)
            )
            continue
        links = _decode_links(outputs[0])
        direct_bank, national, ambiguous = set(), set(), set()
        for slot in entry['employee_slots']:
            j = slot['slot']
            if links[0, 0, j]:
                direct_bank.add(slot['employee_id'])
            elif slot['ambiguous_possible'] and links[2, 0, j]:
                ambiguous.add(slot['employee_id'])
            if links[1, 0, j]:
                national.add(slot['employee_id'])

        strong = sorted(direct_bank | national)
        if strong:
            disclosed = bool(entry['disclosed'])
            rows_out.append(
                dict(
                    transaction_id=entry['transaction_id'],
                    available=True,
                    status='evaluated_hit',
                    matched=True,
                    score=4 if disclosed else 20,
                    hard_trigger=0 if disclosed else 1,
                    scoring_role='transaction',
                    matched_employee_ids=strong,
                    ambiguous_employee_ids=sorted(ambiguous),
                    disclosed=disclosed,
                )
            )
        elif ambiguous:
            rows_out.append(
                dict(
                    transaction_id=entry['transaction_id'],
                    available=True,
                    status='evaluated_hit',
                    matched=True,
                    score=0,
                    hard_trigger=0,
                    scoring_role='context',
                    matched_employee_ids=[],
                    ambiguous_employee_ids=sorted(ambiguous),
                    disclosed=False,
                )
            )
        else:
            rows_out.append(
                dict(
                    transaction_id=entry['transaction_id'],
                    available=True,
                    status='evaluated_no_hit',
                    matched=False,
                    score=0,
                    hard_trigger=0,
                    scoring_role='transaction',
                    matched_employee_ids=[],
                    ambiguous_employee_ids=[],
                    disclosed=False,
                )
            )
    return dict(version='he4-rule-snapshot-b1-result/1.0.0', company_id=plan['company_id'], as_of=plan['as_of'], rule_id='B1', rows=rows_out)


def plan_b5_e4_from_rule_snapshot(data: dict, scope) -> dict:
    """Plan bounded encrypted graph checks for unified `B5`/`E4` (`<= 4` vendors)."""
    if data.get('contract_version') != CONTRACT:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Yêu cầu profile agent2-rule-snapshot/1.0.0.', 'Xuất lại đúng profile.')
    report = validate_rule_snapshot(data, scope, committed=True)
    if report['status'] == 'rejected':
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Snapshot nguồn luật không hợp lệ.', 'Kiểm tra lại schema và coverage.')

    source = data['source']
    as_of = source['as_of']
    tables = source['tables']
    visible_txs = {
        r['transaction_id']: deepcopy(r)
        for r in tables.get('transactions', [])
        if r.get('observed_at', '') <= as_of and r.get('posted_at', '') <= as_of
    }
    vendor_rows = sorted(
        [r for r in tables.get('vendors', []) if r.get('observed_at', '') <= as_of],
        key=lambda r: (r['observed_at'], r['vendor_id']),
    )
    b5_gaps = list(_gaps(source, 'B5'))

    rows_plan = []
    for cid in data['candidate_transaction_ids']:
        tx = visible_txs.get(cid)
        if tx is None or b5_gaps:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='transaction_not_known_at_cutoff' if tx is None else b5_gaps[0].get('reason', 'rule_sources_unavailable'),
                    requests=[],
                )
            )
            continue
        now = tx['posted_at']
        vid = tx.get('vendor_id', '')
        vendors_now = {r['vendor_id']: r for r in vendor_rows if r['observed_at'] <= now and r.get('company_id') == tx['company_id']}
        if not vid or vid not in vendors_now:
            rows_plan.append(dict(record_id=cid, transaction_id=cid, available=True, status='evaluated_no_hit', reason=None, requests=[]))
            continue
        # source_guards checks unknown contact fields on vendors unless matched=True; check field validity cleanly
        ordered_vendors = [vendors_now[vid]] + sorted((v for k, v in vendors_now.items() if k != vid), key=lambda r: r['vendor_id'])
        if len(ordered_vendors) > c.GRAPH_NODES:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason='he_graph_node_limit', requests=[])
            )
            continue

        # Enforce unknown-contact guard (source_guards rule_snapshot.py:129-136) when no field matches are prechecked
        invalid_contact = False
        for v_rec in vendors_now.values():
            for field in ('phone', 'address', 'bank_account', 'related_party_disclosed_at'):
                val = v_rec.get(field)
                if not isinstance(val, str) or (field in ('phone', 'address') and val.strip() and not normalize(val, field)):
                    invalid_contact = True
                    break
        tokens, known, active = _empty_graph_inputs()
        for slot_i, v_rec in enumerate(ordered_vendors):
            active[slot_i] = 1
            for field_j, field_name in enumerate(('bank_account', 'phone', 'address')):
                norm = normalize(v_rec.get(field_name), field_name)
                if norm:
                    tokens[slot_i, field_j] = _token_nibbles(field_name, norm)
                    known[slot_i, field_j] = 1
        if not np.any(known):
            rows_plan.append(dict(record_id=cid, transaction_id=cid, available=True, status='evaluated_no_hit', reason=None, requests=[]))
            continue
        rows_plan.append(
            dict(
                record_id=cid,
                transaction_id=cid,
                available=True,
                status='ready',
                reason=None,
                invalid_contact_present=invalid_contact,
                vendor_slots=[r['vendor_id'] for r in ordered_vendors],
                requests=[dict(profile='graph', rule_id='B5', role='row', values=[tokens.tolist(), known.tolist(), active.tolist()])],
            )
        )
    return dict(
        version='he4-rule-snapshot-b5-plan/1.0.0',
        contract_version=CONTRACT,
        company_id=data['company_id'],
        as_of=as_of,
        rule_id='B5',
        profile='graph',
        rows=rows_plan,
    )


def decode_b5_e4_plan_results(plan: dict, decrypted_outputs: list[list[int]]) -> dict:
    """Decode `circuits.graph` for `B5`/`E4` (`weak address-only vs strong`, single `master_quality` family)."""
    idx = 0
    rows_out = []
    for entry in plan['rows']:
        reqs = entry.get('requests', [])
        outputs = decrypted_outputs[idx : idx + len(reqs)]
        idx += len(reqs)
        if not entry['available']:
            rows_out.append(dict(transaction_id=entry['transaction_id'], available=False, status='unavailable', matched=None, score=None, reason=entry['reason']))
            continue
        if not reqs:
            rows_out.append(dict(transaction_id=entry['transaction_id'], available=True, status='evaluated_no_hit', matched=False, score=0))
            continue
        links = _decode_links(outputs[0])
        duplicates = {}
        for field_j, field_name in enumerate(('bank_account', 'phone', 'address')):
            peers = [entry['vendor_slots'][k] for k in range(1, len(entry['vendor_slots'])) if links[field_j, 0, k]]
            if peers:
                duplicates[field_name] = sorted(peers)
        matched = bool(duplicates)
        if not matched and entry.get('invalid_contact_present'):
            rows_out.append(
                dict(transaction_id=entry['transaction_id'], available=False, status='unavailable', matched=None, score=None, reason='identity_field_unknown')
            )
            continue
        weak = set(duplicates) == {'address'}
        intrinsic_points = (1 if weak else 3) if matched else 0
        # Unified family (`master_quality` + `master_duplicate`): B5 & E4 never double-count; effective row score 0
        rows_out.append(
            dict(
                transaction_id=entry['transaction_id'],
                available=True,
                status='evaluated_hit' if matched else 'evaluated_no_hit',
                matched=matched,
                aliases=['E4'] if matched else [],
                scoring_role='master_quality',
                scoring_family='master_duplicate',
                intrinsic_points=intrinsic_points,
                score=0,
                overlap_kind=('shared_address_only' if weak else 'shared_bank_or_phone') if matched else None,
                shared_fields=duplicates,
            )
        )
    return dict(version='he4-rule-snapshot-b5-result/1.0.0', company_id=plan['company_id'], as_of=plan['as_of'], rule_id='B5', rows=rows_out)

