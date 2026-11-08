"""Blind acceptance workflow for source-dependent deterministic rules.

The detector output is committed before reviewers label the predicate.  A rule can
only be accepted when the source export is attested as real SME data, coverage is
complete at an explicit cutoff, two different reviewers sign every conclusion,
and pre-approved quality gates are met.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from .evidence_policy import REQUIRED as PHASE4_REQUIRED, SOURCES, required_columns
from .generate import TZ, parse, stamp, write_csv
from .rules import load_inputs, score_rules
from .source_snapshot import inspect_sources


RULES = ('F1', 'C4', 'E2', 'F2', 'F3', 'F4')
RULE_SOURCES = {
    'F1': ('journal_audit_log', 'closing_periods', 'materiality_policies'),
    'C4': (*PHASE4_REQUIRED['C4'], 'leave_activity_authorizations'),
    'E2': PHASE4_REQUIRED['E2'],
    'F2': PHASE4_REQUIRED['F2'],
    'F3': PHASE4_REQUIRED['F3'],
    'F4': PHASE4_REQUIRED['F4'],
}
SOURCE_IDS = {
    **SOURCES,
    'journal_audit_log': 'audit_id',
    'closing_periods': 'closing_id',
    'materiality_policies': 'policy_id',
}
F1_COLUMNS = {
    'journal_audit_log': ('audit_id', 'company_id', 'employee_id', 'transaction_id',
                          'entry_origin', 'entered_at', 'observed_at', 'evidence_id'),
    'closing_periods': ('closing_id', 'company_id', 'period_start', 'period_end',
                        'closing_at', 'status', 'approver_id', 'approved_at',
                        'observed_at', 'evidence_on_file', 'evidence_id'),
    'materiality_policies': ('policy_id', 'company_id', 'effective_from', 'effective_to',
                             'materiality_vnd', 'status', 'approver_id', 'approved_at',
                             'observed_at', 'evidence_on_file', 'evidence_id'),
}
PACKET_FIELDS = (
    'review_id', 'company_id', 'rule_id', 'unit_type', 'unit_id', 'event_at',
    'source_record_ids', 'condition_present', 'information_gap',
    'primary_reviewer_id', 'adjudicator_id', 'reviewed_at', 'adjudicated_at',
    'rationale', 'blind_to_prediction', 'sample_weight', 'evidence_id',
    'source_manifest_sha256',
)
INVENTORY_FIELDS = (
    'rule_id', 'source_name', 'filename', 'declared_in_manifest', 'file_exists',
    'checksum_matches', 'schema_complete', 'rows', 'sha256', 'missing_columns',
)
COVERAGE_FIELDS = (
    'coverage_id', 'company_id', 'rule_id', 'covered_from', 'covered_through',
    'source_names', 'completeness_status', 'data_origin', 'attested_by',
    'attested_at', 'evidence_id', 'source_manifest_sha256', 'notes',
)
METRIC_FIELDS = (
    'rule_id', 'status', 'review_units', 'reviewed_units', 'evaluable_units',
    'condition_present', 'condition_absent', 'detector_information_gaps',
    'information_gap_rate', 'tp', 'fp', 'fn', 'tn', 'precision', 'recall',
    'precision_wilson_95_low', 'precision_wilson_95_high',
    'recall_wilson_95_low', 'recall_wilson_95_high', 'weighted_tp',
    'weighted_fp', 'weighted_fn', 'weighted_tn', 'weighted_precision',
    'weighted_recall', 'reasons',
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def manifest_hash(directory: Path) -> str:
    return sha(directory / 'manifest.json')


def _entry_hash(entry):
    return entry.get('sha256', '') if isinstance(entry, dict) else str(entry or '')


def _required_columns(name):
    if name in F1_COLUMNS:
        return F1_COLUMNS[name]
    return tuple(required_columns(name))


def source_inventory(directory: Path, manifest: dict) -> list[dict]:
    result = []
    for rule in RULES:
        for name in RULE_SOURCES[rule]:
            path = directory / f'{name}.csv'
            entry = manifest.get('files', {}).get(path.name)
            exists = path.exists()
            actual = sha(path) if exists else ''
            declared = entry is not None
            checksum = bool(exists and declared and actual == _entry_hash(entry))
            fields, rows = [], 0
            if exists:
                with path.open(encoding='utf-8-sig', newline='') as stream:
                    reader = csv.DictReader(stream)
                    fields = reader.fieldnames or []
                    rows = sum(1 for _ in reader)
            missing = sorted(set(_required_columns(name)) - set(fields))
            result.append(dict(rule_id=rule, source_name=name, filename=path.name,
                declared_in_manifest=int(declared), file_exists=int(exists),
                checksum_matches=int(checksum), schema_complete=int(exists and not missing),
                rows=rows, sha256=actual, missing_columns='|'.join(missing)))
    return result


def inventory_ready(inventory: list[dict], rule: str) -> bool:
    rows = [r for r in inventory if r['rule_id'] == rule]
    return bool(rows) and all(int(r[k]) for r in rows for k in
                              ('declared_in_manifest', 'file_exists',
                               'checksum_matches', 'schema_complete'))


def _timezone_timestamp(value: str, label: str):
    try:
        parsed = parse(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be an ISO timestamp with timezone') from exc
    if parsed.tzinfo is None:
        raise ValueError(f'{label} must include timezone')
    return parsed


def _cutoffs(evaluation_from: str, as_of: str):
    start = _timezone_timestamp(evaluation_from, 'evaluation_from').astimezone(TZ)
    end = _timezone_timestamp(as_of, 'as_of').astimezone(TZ)
    if start > end:
        raise ValueError('evaluation_from must not be after as_of')
    return stamp(start), stamp(end)


def _latest(rows: list[dict], identity: str, cutoff: str) -> list[dict]:
    versions = {}
    for row in sorted(rows, key=lambda r: (r.get('observed_at', ''), r.get(identity, ''))):
        if row.get('observed_at', '') <= cutoff:
            versions[(row.get('company_id', ''), row.get(identity, ''))] = row
    return list(versions.values())


def _packet_row(rule, unit_type, unit_id, company, event_at, source_ids, manifest_sha):
    key = [company, rule, unit_type, unit_id]
    return dict(review_id='RV_' + canonical_sha(key)[:20], company_id=company,
        rule_id=rule, unit_type=unit_type, unit_id=unit_id, event_at=event_at,
        source_record_ids='|'.join(sorted(set(x for x in source_ids if x))),
        condition_present='', information_gap='', primary_reviewer_id='',
        adjudicator_id='', reviewed_at='', adjudicated_at='', rationale='',
        blind_to_prediction='', sample_weight='1', evidence_id='',
        source_manifest_sha256=manifest_sha)


def review_universe(tables: dict, evaluation_from: str, as_of: str,
                    manifest_sha: str) -> list[dict]:
    """Build the review population from source records, never detector output."""
    tx = {r['transaction_id']: r for r in tables['transactions']
          if evaluation_from <= r['posted_at'] <= as_of}
    rows = {}

    def add(rule, unit_type, unit_id, company, event_at, source_id):
        if not unit_id or not company:
            return
        key = company, rule, unit_type, unit_id
        if key not in rows:
            rows[key] = _packet_row(rule, unit_type, unit_id, company, event_at,
                                    [source_id], manifest_sha)
        elif source_id:
            known = set(rows[key]['source_record_ids'].split('|'))
            rows[key]['source_record_ids'] = '|'.join(sorted((known | {source_id}) - {''}))

    for item in _latest(tables.get('journal_audit_log', []), 'audit_id', as_of):
        transaction = tx.get(item.get('transaction_id'))
        if transaction:
            add('F1', 'transaction', transaction['transaction_id'], transaction['company_id'],
                transaction['posted_at'], item.get('audit_id', ''))
    for item in _latest(tables.get('system_actions', []), 'action_id', as_of):
        transaction = tx.get(item.get('transaction_id'))
        if transaction:
            add('C4', 'transaction', transaction['transaction_id'], transaction['company_id'],
                item.get('action_at', transaction['posted_at']), item.get('action_id', ''))
    employment = defaultdict(set)
    for item in _latest(tables.get('employment_events', []), 'employment_event_id', as_of):
        employment[item.get('company_id', '')].add(item.get('employee_id', ''))
    for transaction in tx.values():
        if (transaction.get('txn_type') == 'payroll' and
                transaction.get('employee_id') in employment[transaction['company_id']]):
            add('E2', 'transaction', transaction['transaction_id'], transaction['company_id'],
                transaction['posted_at'], transaction.get('employee_id', ''))
    for item in _latest(tables.get('override_events', []), 'override_id', as_of):
        transaction = tx.get(item.get('transaction_id'))
        if transaction:
            add('F2', 'transaction', transaction['transaction_id'], transaction['company_id'],
                item.get('operation_at', transaction['posted_at']), item.get('override_id', ''))
    for item in _latest(tables.get('document_register', []), 'register_id', as_of):
        transaction = tx.get(item.get('transaction_id'))
        if transaction:
            add('F3', 'transaction', transaction['transaction_id'], transaction['company_id'],
                transaction['posted_at'], item.get('register_id', ''))
    for item in _latest(tables.get('document_series', []), 'series_id', as_of):
        if evaluation_from <= item.get('closed_at', '') <= as_of:
            add('F3', 'document_series', item['series_id'], item['company_id'],
                item['closed_at'], item['series_id'])
    for item in _latest(tables.get('receivable_invoices', []), 'invoice_id', as_of):
        # F4 is a cutoff backlog test: an old unpaid invoice remains in scope even
        # when it was issued before the evaluation window.
        if item.get('issued_at', '') <= as_of:
            add('F4', 'receivable_invoice', item['invoice_id'], item['company_id'],
                item['issued_at'], item['invoice_id'])
    return [rows[key] for key in sorted(rows)]


def _restricted_score(tables: dict, features: list[dict], as_of: str):
    limited = dict(tables)
    limited['transactions'] = [r for r in tables['transactions'] if r['posted_at'] <= as_of]
    ids = {r['transaction_id'] for r in limited['transactions']}
    limited_features = [r for r in features if r['transaction_id'] in ids]
    return score_rules(limited, features=limited_features)


def predictions_for_packet(tables: dict, features: list[dict], packet: list[dict],
                           as_of: str) -> list[dict]:
    result = _restricted_score(tables, features, as_of)
    return predictions_from_result(result, tables, packet, as_of)


def predictions_from_result(result: dict, tables: dict, packet: list[dict], as_of: str) -> list[dict]:
    """Project a scored snapshot; acceptance callers still recompute the engine."""
    hits = defaultdict(list)
    for hit in result['hits']:
        if hit['rule_id'] in RULES:
            hits[(hit['company_id'], hit['rule_id'], 'transaction',
                  hit['transaction_id'])].append(hit)
    source_findings = {}
    for finding in inspect_sources(tables, as_of):
        unit_type, _, unit_id = finding['scope'].partition(':')
        mapped_type = 'document_series' if unit_type == 'series' else 'receivable_invoice'
        source_findings[(finding['company_id'], finding['rule_id'], mapped_type,
                         unit_id)] = finding
    predictions = []
    for row in packet:
        key = (row['company_id'], row['rule_id'], row['unit_type'], row['unit_id'])
        prediction = False
        status = 'evaluated'
        evidence_ids = []
        if row['unit_type'] == 'transaction':
            candidates = hits.get(key, [])
            active = [h for h in candidates if not h.get('suppressed_reason') and
                      h.get('evidence', {}).get('evidence_status') != 'information_gap' and
                      (row['rule_id'] != 'F1' or
                       h.get('evidence', {}).get('evidence_status') == 'confirmed_sources')]
            gaps = [h for h in candidates if
                    h.get('evidence', {}).get('evidence_status') == 'information_gap']
            prediction = bool(active)
            if not active and gaps:
                prediction, status = None, 'information_gap'
            evidence_ids = [h.get('evidence_id', '') for h in active or gaps]
        else:
            finding = source_findings.get(key)
            if finding is None or finding.get('signal') is None:
                prediction, status = None, 'information_gap'
            else:
                prediction = bool(finding['signal'])
                evidence_ids = [canonical_sha(finding.get('evidence', {}))]
        predictions.append(dict(company_id=key[0], rule_id=key[1], unit_type=key[2],
            unit_id=key[3], prediction=prediction, detector_status=status,
            evidence_ids=sorted(x for x in evidence_ids if x)))
    return sorted(predictions, key=lambda r: (r['company_id'], r['rule_id'],
                                               r['unit_type'], r['unit_id']))


def _code_hashes():
    root = Path(__file__).resolve().parent
    names = ('real_source_acceptance.py', 'real_source_acceptance.schema.json',
             'rules.py', 'evidence_policy.py', 'evidence_sources.schema.json',
             'source_snapshot.py', 'spec_policy.py', 'temporal_evidence.py',
             'noise_policy.py', 'payment_evidence.py', 'payment_evidence.schema.json',
             'authority_policy.py', 'authority_policy.schema.json', 'features.py',
             'generate.py', 'batch_controls.py', 'case_queue.py', 'exception_validation.py', 'case_identity.py',
             'feature_contract.py', 'sync_feature_model.py', 'evaluate.py', 'run_rules.py', 'case_admission.py',
             'review_capacity.py', 'a4_pattern_queue.py')
    return {name: sha(root / name) for name in names}


def _looks_synthetic(manifest: dict) -> bool:
    return (manifest.get('is_synthetic') is True
            or str(manifest.get('data_origin', '')).startswith('synthetic')
            or any(key in manifest for key in ('requested_fraud_rate', 'actual_fraud_rows', 'fraud_variants')))


def make_commitment(data: Path, packet: list[dict], predictions: list[dict],
                    evaluation_from: str, as_of: str, manifest: dict,
                    criteria_path: Path | None = None) -> dict:
    criteria = (json.loads(criteria_path.read_text(encoding='utf-8'))
                if criteria_path else {})
    return dict(version='1.0', dataset_manifest_sha256=manifest_hash(data),
        dataset_declares_synthetic=int(_looks_synthetic(manifest)),
        evaluation_from=evaluation_from, as_of=as_of,
        review_packet_sha256=canonical_sha(packet), prediction_count=len(predictions),
        prediction_sha256=canonical_sha(predictions), code_sha256=_code_hashes(),
        criteria_sha256=sha(criteria_path) if criteria_path else '',
        criteria_status=criteria.get('policy_status', 'not_frozen'),
        disclosure='Predictions are committed by hash and are not present in the blind review packet.')


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def _ensure_empty(output: Path):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'Refusing to overwrite non-empty output: {output}')
    output.mkdir(parents=True, exist_ok=True)


def prepare(data: Path, output: Path, evaluation_from: str, as_of: str,
            criteria_path: Path | None = None) -> dict:
    evaluation_from, as_of = _cutoffs(evaluation_from, as_of)
    _ensure_empty(output)
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    inventory = source_inventory(data, manifest)
    write_csv(output / 'source_inventory.csv', inventory, list(INVENTORY_FIELDS))
    tables, features, _ = load_inputs(data)
    packet = review_universe(tables, evaluation_from, as_of, manifest_hash(data))
    write_csv(output / 'review_packet.csv', packet, list(PACKET_FIELDS))
    predictions = predictions_for_packet(tables, features, packet, as_of) if packet else []
    commitment = make_commitment(data, packet, predictions, evaluation_from, as_of,
                                 manifest, criteria_path)
    _write_json(output / 'prediction_commitment.json', commitment)
    source_ready = {rule: inventory_ready(inventory, rule) for rule in RULES}
    statuses = {rule: ('awaiting_source_coverage' if source_ready[rule] and
                       not _looks_synthetic(manifest) else 'awaiting_real_data')
                for rule in RULES}
    readiness = dict(status='awaiting_real_data' if not all(source_ready.values()) or
                     _looks_synthetic(manifest) else 'awaiting_source_coverage',
        dataset=str(data), dataset_manifest_sha256=manifest_hash(data),
        dataset_declares_synthetic=_looks_synthetic(manifest),
        criteria_status=commitment['criteria_status'],
        evaluation_from=evaluation_from, as_of=as_of, review_units=len(packet),
        rules={rule: dict(status=statuses[rule], source_ready=source_ready[rule],
                          review_units=sum(r['rule_id'] == rule for r in packet),
                          required_sources=list(RULE_SOURCES[rule])) for rule in RULES})
    _write_json(output / 'readiness.json', readiness)
    lines = ['# Sẵn sàng nghiệm thu rule trên nguồn SME thật', '',
        f"- Trạng thái chung: `{readiness['status']}`",
        f"- Cửa sổ: `{evaluation_from}` đến `{as_of}`",
        f"- Số đơn vị đưa vào phiếu chấm mù: **{len(packet)}**",
        f"- Manifest hiện tại được nhận diện là dữ liệu mô phỏng: **{'có' if _looks_synthetic(manifest) else 'không'}**",
        f"- Chính sách ngưỡng đã khóa cùng prediction: `{commitment['criteria_status']}`",
        '', '| Rule | Trạng thái | Nguồn đủ file/schema/checksum | Số đơn vị rà soát |',
        '| --- | --- | ---: | ---: |']
    for rule in RULES:
        item = readiness['rules'][rule]
        lines.append(f"| {rule} | `{item['status']}` | {'có' if item['source_ready'] else 'không'} | {item['review_units']} |")
    lines += ['', 'Phiếu `review_packet.csv` không chứa kết quả detector. Hash dự đoán đã khóa trong '
              '`prediction_commitment.json`; chỉ mở so sánh sau khi có kết luận của hai người khác nhau.',
              '', 'Không có rule nào được nghiệm thu từ fixture mô phỏng hoặc từ việc không phát sinh hit.']
    (output / 'summary_vi.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return readiness


def _wilson(success, total):
    if not total:
        return (None, None)
    z = 1.95996398454
    p = success / total
    scale = 1 + z*z/total
    center = (p + z*z/(2*total)) / scale
    half = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/scale
    return max(0, center-half), min(1, center+half)


def _parse_flag(value, label, allow_blank=False):
    if allow_blank and value == '':
        return None
    if str(value) not in {'0', '1'}:
        raise ValueError(f'{label} must be 0 or 1')
    return int(value)


def _validate_reviews(packet: list[dict], reviews: list[dict], cutoff: str,
                      manifest_sha: str):
    expected = {r['review_id']: r for r in packet}
    supplied = {}
    errors = []
    for row in reviews:
        rid = row.get('review_id', '')
        if rid not in expected:
            errors.append(f'unknown review_id:{rid}')
            continue
        if rid in supplied:
            errors.append(f'duplicate review_id:{rid}')
            continue
        # Selection metadata and weights are frozen before reviewers see cases.
        for field in ('company_id', 'rule_id', 'unit_type', 'unit_id', 'event_at',
                      'source_record_ids', 'sample_weight'):
            if row.get(field) != expected[rid][field]:
                errors.append(f'{rid}:changed_{field}')
        if row.get('source_manifest_sha256') != manifest_sha:
            errors.append(f'{rid}:manifest_mismatch')
        if row.get('primary_reviewer_id', '') == row.get('adjudicator_id', '') or not row.get('primary_reviewer_id') or not row.get('adjudicator_id'):
            errors.append(f'{rid}:reviewers_not_independent')
        try:
            blind = _parse_flag(row.get('blind_to_prediction', ''), f'{rid}.blind_to_prediction')
            gap = _parse_flag(row.get('information_gap', ''), f'{rid}.information_gap')
            condition = _parse_flag(row.get('condition_present', ''), f'{rid}.condition_present', allow_blank=bool(gap))
            reviewed = _timezone_timestamp(row.get('reviewed_at', ''), f'{rid}.reviewed_at')
            adjudicated = _timezone_timestamp(row.get('adjudicated_at', ''), f'{rid}.adjudicated_at')
            if not blind:
                errors.append(f'{rid}:not_blind')
            if gap and condition is not None:
                errors.append(f'{rid}:condition_must_be_blank_for_gap')
            if reviewed <= parse(cutoff) or adjudicated < reviewed:
                errors.append(f'{rid}:invalid_review_time')
            if float(row.get('sample_weight', '')) <= 0:
                errors.append(f'{rid}:invalid_weight')
        except (ValueError, TypeError) as exc:
            errors.append(f'{rid}:{exc}')
        if not row.get('rationale') or not row.get('evidence_id'):
            errors.append(f'{rid}:missing_rationale_or_evidence')
        supplied[rid] = row
    return supplied, errors


def _coverage_by_rule(rows: list[dict], companies: set[str], evaluation_from: str,
                      as_of: str, manifest_sha: str):
    covered, errors = defaultdict(set), []
    for row in rows:
        rule, company = row.get('rule_id', ''), row.get('company_id', '')
        if rule not in RULES or company not in companies:
            errors.append(f"unknown coverage scope:{company}/{rule}")
            continue
        sources = set(row.get('source_names', '').split('|')) - {''}
        try:
            covered_from = _timezone_timestamp(row.get('covered_from', ''), 'covered_from')
            covered_through = _timezone_timestamp(row.get('covered_through', ''), 'covered_through')
            attested_at = _timezone_timestamp(row.get('attested_at', ''), 'attested_at')
            requested_from = parse(evaluation_from)
            requested_through = parse(as_of)
        except ValueError:
            covered_from = covered_through = attested_at = None
            requested_from = requested_through = None
        valid = (row.get('completeness_status') == 'complete' and
                 row.get('data_origin') == 'real_sme_export' and
                 row.get('source_manifest_sha256') == manifest_sha and
                 set(RULE_SOURCES[rule]) <= sources and
                 covered_from is not None and covered_from <= requested_from and
                 covered_through >= requested_through and attested_at >= covered_through and
                 bool(row.get('attested_by')) and bool(row.get('evidence_id')))
        if valid:
            covered[rule].add(company)
        else:
            errors.append(f"invalid coverage:{company}/{rule}/{row.get('coverage_id','')}")
    return {rule: covered[rule] >= companies for rule in RULES}, errors


def _metric(rule, packet_rows, reviews_by_id, predictions_by_key, gates,
            source_ready, coverage_ready, criteria_approved):
    counts = dict(tp=0, fp=0, fn=0, tn=0)
    weighted = dict(tp=0., fp=0., fn=0., tn=0.)
    reviewed = evaluable = positives = negatives = detector_gaps = 0
    comparison = []
    for item in packet_rows:
        review = reviews_by_id.get(item['review_id'])
        key = (item['company_id'], rule, item['unit_type'], item['unit_id'])
        pred = predictions_by_key[key]['prediction']
        if review is None:
            continue
        reviewed += 1
        human_gap = int(review['information_gap'])
        label = None if human_gap else int(review['condition_present'])
        weight = float(review['sample_weight'])
        if label is not None:
            positives += label
            negatives += 1-label
            evaluable += 1
            if pred is None:
                detector_gaps += 1
            else:
                cell = 'tp' if label and pred else 'fn' if label else 'fp' if pred else 'tn'
                counts[cell] += 1
                weighted[cell] += weight
        comparison.append(dict(review_id=item['review_id'], company_id=item['company_id'],
            rule_id=rule, unit_type=item['unit_type'], unit_id=item['unit_id'],
            condition_present='' if label is None else label, review_information_gap=human_gap,
            detector_prediction='' if pred is None else int(pred),
            detector_information_gap=int(pred is None), sample_weight=weight))
    precision_den = counts['tp'] + counts['fp']
    recall_den = counts['tp'] + counts['fn']
    precision = counts['tp']/precision_den if precision_den else None
    recall = counts['tp']/recall_den if recall_den else None
    wp_den, wr_den = weighted['tp']+weighted['fp'], weighted['tp']+weighted['fn']
    p_low, p_high = _wilson(counts['tp'], precision_den)
    r_low, r_high = _wilson(counts['tp'], recall_den)
    total_gaps = len(packet_rows)-evaluable + detector_gaps
    gap_rate = total_gaps/len(packet_rows) if packet_rows else 1.
    reasons = []
    if not source_ready:
        reasons.append('source_files_not_ready')
    if not coverage_ready:
        reasons.append('coverage_not_attested')
    if reviewed < len(packet_rows):
        reasons.append('reviews_incomplete')
    if not criteria_approved:
        reasons.append('criteria_not_approved')
    if reviewed == len(packet_rows) and criteria_approved:
        if evaluable < int(gates.get('min_evaluable', 0)):
            reasons.append('min_evaluable_not_met')
        if positives < int(gates.get('min_condition_present', 0)):
            reasons.append('min_condition_present_not_met')
        if negatives < int(gates.get('min_condition_absent', 0)):
            reasons.append('min_condition_absent_not_met')
        if precision is None or precision < float(gates.get('min_precision', 1)):
            reasons.append('min_precision_not_met')
        if recall is None or recall < float(gates.get('min_recall', 1)):
            reasons.append('min_recall_not_met')
        if gap_rate > float(gates.get('max_information_gap_rate', 0)):
            reasons.append('max_information_gap_rate_exceeded')
    if not source_ready:
        status = 'awaiting_real_data'
    elif not coverage_ready:
        status = 'awaiting_source_coverage'
    elif reviewed < len(packet_rows):
        status = 'awaiting_independent_review'
    elif not criteria_approved:
        status = 'awaiting_criteria'
    elif any(r in {'min_evaluable_not_met', 'min_condition_present_not_met',
                   'min_condition_absent_not_met'} for r in reasons):
        status = 'insufficient_review'
    elif any(r.endswith('_not_met') or r.endswith('_exceeded') for r in reasons):
        status = 'rejected'
    else:
        status = 'accepted'
    metric = dict(rule_id=rule, status=status, review_units=len(packet_rows),
        reviewed_units=reviewed, evaluable_units=evaluable,
        condition_present=positives, condition_absent=negatives,
        detector_information_gaps=detector_gaps, information_gap_rate=gap_rate,
        **counts, precision=precision, recall=recall,
        precision_wilson_95_low=p_low, precision_wilson_95_high=p_high,
        recall_wilson_95_low=r_low, recall_wilson_95_high=r_high,
        weighted_tp=weighted['tp'], weighted_fp=weighted['fp'],
        weighted_fn=weighted['fn'], weighted_tn=weighted['tn'],
        weighted_precision=weighted['tp']/wp_den if wp_den else None,
        weighted_recall=weighted['tp']/wr_den if wr_den else None,
        reasons='|'.join(reasons))
    return metric, comparison


def evaluate(data: Path, prepared: Path, reviews_path: Path, coverage_path: Path,
             criteria_path: Path, output: Path) -> dict:
    _ensure_empty(output)
    commitment = json.loads((prepared/'prediction_commitment.json').read_text(encoding='utf-8'))
    if manifest_hash(data) != commitment['dataset_manifest_sha256']:
        raise ValueError('Dataset manifest differs from frozen preparation')
    packet = read_csv(prepared/'review_packet.csv')
    if canonical_sha(packet) != commitment['review_packet_sha256']:
        raise ValueError('Blind review packet differs from frozen preparation')
    manifest = json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    inventory = source_inventory(data, manifest)
    tables, features, _ = load_inputs(data)
    predictions = predictions_for_packet(tables, features, packet, commitment['as_of'])
    if canonical_sha(predictions) != commitment['prediction_sha256']:
        raise ValueError('Detector predictions differ from the frozen commitment')
    if _code_hashes() != commitment['code_sha256']:
        raise ValueError('Rule implementation differs from the frozen commitment')
    reviews = read_csv(reviews_path)
    reviews_by_id, review_errors = _validate_reviews(packet, reviews,
        commitment['as_of'], commitment['dataset_manifest_sha256'])
    if review_errors:
        raise ValueError('Invalid independent reviews: ' + '; '.join(review_errors[:10]))
    coverage = read_csv(coverage_path)
    companies = {r['company_id'] for r in tables['companies']}
    coverage_ready, coverage_errors = _coverage_by_rule(coverage, companies,
        commitment['evaluation_from'], commitment['as_of'], commitment['dataset_manifest_sha256'])
    criteria = json.loads(criteria_path.read_text(encoding='utf-8'))
    if criteria.get('policy_status') not in {'draft', 'approved'}:
        raise ValueError('criteria.policy_status must be draft or approved')
    criteria_frozen = bool(commitment.get('criteria_sha256'))
    if criteria_frozen and sha(criteria_path) != commitment['criteria_sha256']:
        raise ValueError('Acceptance criteria differ from the policy frozen at preparation')
    approved = (criteria_frozen and criteria.get('policy_status') == 'approved' and
                bool(criteria.get('approved_by')) and bool(criteria.get('approved_at')))
    if approved:
        _timezone_timestamp(criteria['approved_at'], 'criteria.approved_at')
    if set(criteria.get('rules', {})) != set(RULES):
        raise ValueError('Acceptance criteria must define exactly F1/C4/E2/F2/F3/F4')
    for rule, gates in criteria['rules'].items():
        counts = [int(gates.get(name, 0)) for name in
                  ('min_evaluable', 'min_condition_present', 'min_condition_absent')]
        rates = [float(gates.get(name, -1)) for name in
                 ('min_precision', 'min_recall', 'max_information_gap_rate')]
        if any(value <= 0 for value in counts) or counts[1] + counts[2] > counts[0]:
            raise ValueError(f'Invalid minimum sample criteria for {rule}')
        if any(not 0 <= value <= 1 for value in rates):
            raise ValueError(f'Invalid rate criteria for {rule}')
    if approved and reviews_by_id:
        first_review = min(parse(row['reviewed_at']) for row in reviews_by_id.values())
        if parse(criteria['approved_at']) > first_review:
            raise ValueError('Acceptance criteria were approved after review began')
    prediction_map = {(r['company_id'], r['rule_id'], r['unit_type'], r['unit_id']): r
                      for r in predictions}
    metrics, comparisons = [], []
    synthetic = _looks_synthetic(manifest) or bool(commitment.get('dataset_declares_synthetic'))
    for rule in RULES:
        rule_packet = [r for r in packet if r['rule_id'] == rule]
        source_ready = inventory_ready(inventory, rule) and not synthetic
        metric, rows = _metric(rule, rule_packet, reviews_by_id, prediction_map,
            criteria['rules'][rule], source_ready, coverage_ready[rule], approved)
        metrics.append(metric)
        comparisons.extend(rows)
    write_csv(output/'rule_metrics.csv', metrics, list(METRIC_FIELDS))
    comparison_fields = ('review_id','company_id','rule_id','unit_type','unit_id',
        'condition_present','review_information_gap','detector_prediction',
        'detector_information_gap','sample_weight')
    write_csv(output/'review_comparison.csv', comparisons, list(comparison_fields))
    result = dict(status='accepted' if all(m['status'] == 'accepted' for m in metrics)
                  else 'not_accepted', dataset=str(data),
        dataset_manifest_sha256=commitment['dataset_manifest_sha256'],
        evaluation_from=commitment['evaluation_from'], as_of=commitment['as_of'],
        criteria_status=criteria.get('policy_status'), synthetic_dataset=synthetic,
        coverage_errors=coverage_errors, rules={m['rule_id']: m for m in metrics})
    _write_json(output/'acceptance.json', result)
    lines = ['# Kết quả nghiệm thu rule cần nguồn bổ sung', '',
        f"- Kết luận chung: `{result['status']}`",
        f"- Chính sách ngưỡng: `{result['criteria_status']}`",
        f"- Dữ liệu được nhận diện là mô phỏng: **{'có' if synthetic else 'không'}**",
        '', '| Rule | Trạng thái | TP | FP | FN | Precision | Recall | Gap |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for m in metrics:
        fmt = lambda x: 'NA' if x is None else f'{x:.3f}'
        lines.append(f"| {m['rule_id']} | `{m['status']}` | {m['tp']} | {m['fp']} | {m['fn']} | {fmt(m['precision'])} | {fmt(m['recall'])} | {m['information_gap_rate']:.3f} |")
    lines += ['', 'Chỉ trạng thái `accepted` mới là nghiệm thu. `not_accepted` không được '
              'diễn giải thành rule sai; đọc cột `reasons` để biết thiếu nguồn, thiếu mẫu, '
              'thiếu review hay không đạt ngưỡng.']
    (output/'summary_vi.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('--data', type=Path, required=True)
    prepare_parser.add_argument('--output', type=Path, required=True)
    prepare_parser.add_argument('--from', dest='evaluation_from', required=True)
    prepare_parser.add_argument('--as-of', required=True)
    prepare_parser.add_argument('--criteria', type=Path,
                                help='Approved criteria to freeze before blind review')
    evaluate_parser = commands.add_parser('evaluate')
    evaluate_parser.add_argument('--data', type=Path, required=True)
    evaluate_parser.add_argument('--prepared', type=Path, required=True)
    evaluate_parser.add_argument('--reviews', type=Path, required=True)
    evaluate_parser.add_argument('--coverage', type=Path, required=True)
    evaluate_parser.add_argument('--criteria', type=Path, required=True)
    evaluate_parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.data, args.output, args.evaluation_from, args.as_of,
                         args.criteria)
    else:
        result = evaluate(args.data, args.prepared, args.reviews, args.coverage,
                          args.criteria, args.output)
    print(json.dumps({'status': result['status'], 'output': str(args.output)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
