"""Limited evidence mode using unchanged C2/C3 predicates from the existing rules.

This is a separate operational fallback, not the frozen benchmark policy. No
missing history or master attribute is interpreted as evidence of misconduct.
"""
from __future__ import annotations

from bisect import bisect_right
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sme_fraud.rules import DEFAULT_CONFIG, RULE_NAMES, WEIGHTS
from .alerting import build_cases
from .explain_v4 import rule_observations
from .inference_v4 import snapshot_input, week_bounds
from .metrics import weekly_alerts
from .pipeline import to_case_queue
from .review_store_v4 import clean


def reduced_scores(frames, company_id, week):
    """Only C3 has enough evidence in the minimum transaction contract.

    C2 additionally requires an observed employee master version and an explicit
    self-approval limit. All other checks and all learned models are disabled.
    """
    frame = frames['transactions'].copy()
    start, end = week_bounds(week)
    dates = pd.to_datetime(frame.posted_at, utc=True, format='mixed')
    frame = frame[(dates >= start) & (dates < end)].copy()
    frame['t'] = pd.to_datetime(frame.posted_at, utc=True).dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None)
    frame = frame.sort_values(['t', 'transaction_id'], kind='stable').reset_index(drop=True)
    frame['week'] = week
    for column in ('vendor_id', 'employee_id', 'creator_id', 'approver_id'):
        if column not in frame:
            frame[column] = ''
    masters, enabled = {}, ['C3']
    staff = frames.get('employees')
    required = {'company_id', 'employee_id', 'recorded_at', 'self_approval_limit_vnd'}
    if staff is not None and required <= set(staff):
        for row in staff.to_dict('records'):
            when = pd.to_datetime(row['recorded_at'], utc=True, errors='coerce')
            limit = pd.to_numeric(row['self_approval_limit_vnd'], errors='coerce')
            if pd.isna(when) or not np.isfinite(limit) or limit < 0:
                continue
            masters.setdefault((str(row['company_id']), str(row['employee_id'])), []).append((when, float(limit)))
        for rows in masters.values():
            rows.sort()
        if masters:
            enabled.append('C2')
    scores, hard, evidence = [], [], []
    for row in frame.to_dict('records'):
        hits = {}
        amount = float(row['amount_vnd'])
        seconds = (pd.to_datetime(row['approved_at'], utc=True) - pd.to_datetime(row['created_at'], utc=True)).total_seconds()
        if 0 <= seconds < 60 and amount >= DEFAULT_CONFIG['high_approval_vnd']:
            hits['C3'] = {'approval_seconds': seconds, 'amount_vnd': amount,
                          'high_approval_vnd': DEFAULT_CONFIG['high_approval_vnd']}
        if row['creator_id'] and row['creator_id'] == row['approver_id']:
            versions = masters.get((str(company_id), str(row['creator_id'])), [])
            position = bisect_right([r[0] for r in versions], pd.to_datetime(row['posted_at'], utc=True)) - 1
            if position >= 0 and amount > versions[position][1]:
                hits['C2'] = {'amount_vnd': amount, 'self_approval_limit_vnd': versions[position][1]}
        # Existing C-family max pooling: correlated checks do not add twice.
        scores.append(max((WEIGHTS[r] for r in hits), default=0))
        hard.append('C2' in hits)
        evidence.append(hits)
    frame['rule_ids'] = ['|'.join(sorted(h)) for h in evidence]
    frame['rule_evidence_json'] = [json.dumps(h) for h in evidence]
    frame['rule_hard'] = hard
    texts, explanations = [], []
    for row in frame.to_dict('records'):
        observed = rule_observations(row)
        texts.append(' | '.join(item['text'] for item in observed))
        explanations.append({'company_id': company_id, 'transaction_id': row['transaction_id'], 'observations': observed})
    frame['explanation_vi'] = texts
    frame['creator_id'] = frame.creator_id.where(frame.creator_id.ne(''), frame.transaction_id)
    flags = weekly_alerts(frame, np.asarray(scores, dtype=float), 3) & (np.asarray(scores) > 0) if len(frame) else np.zeros(0, bool)
    return frame, flags, np.asarray(scores, dtype=float), enabled, explanations


def run_reduced(data, out, config, week, company_id):
    from .pipeline_v4 import sha, ROOT
    frames, report, hashes = snapshot_input(data, Path(out) / 'input_snapshot', company_id, week, require_full=False)
    frame, flags, scores, enabled, explanations = reduced_scores(frames, company_id, week)
    if frame.empty:
        raise ValueError('no transactions in the requested week')
    cases = build_cases(frame, flags, scores)
    hard_ids = set(frame.loc[flags & frame.rule_hard.to_numpy(dtype=bool), 'transaction_id'])
    if len(cases):
        cases.loc[cases.transaction_ids.map(lambda ids: bool(hard_ids.intersection(ids))), 'priority'] = 'cao_nhat'
    cases['iso_week'] = week
    cases['action_vi'] = 'Đối chiếu chứng từ và thẩm quyền đã có; bổ sung dữ liệu còn thiếu trước khi rà soát đầy đủ.'
    queue = to_case_queue(cases)
    queue['iso_week'] = week
    cases['sla_due_at'], cases['sla_basis'] = queue.sla_due_at, queue.sla_basis
    cases['explanation_vi'] = cases.reason
    out = Path(out)
    cases.assign(transaction_ids=cases.transaction_ids.map(json.dumps)).to_csv(out / 'cases.csv', index=False, encoding='utf-8-sig')
    queue.to_csv(out / 'case_queue.csv', index=False, encoding='utf-8-sig')
    frame.loc[flags].assign(ranking_score=scores[flags]).drop(columns='rule_evidence_json').to_csv(out / 'alerts.csv', index=False, encoding='utf-8-sig')
    with (out / 'explanations.jsonl').open('w', encoding='utf-8') as stream:
        for index in np.flatnonzero(flags):
            stream.write(json.dumps(clean(explanations[index]), ensure_ascii=False) + '\n')
    result = {'company_id': company_id, 'week': week, 'profile': 'reduced', 'chosen_policy': 'existing_rules_subset',
              'model_version': 'reduced:C2-C3:v1', 'training_data_kind': 'none', 'rows_scored': len(frame),
              'alert_rows': int(flags.sum()), 'cases': len(cases), 'budget_per_company_week': 3,
              'enabled_rules': enabled, 'disabled_rules': sorted(set(RULE_NAMES) - set(enabled)),
              'disabled_models': ['frozen_supervised_policy', 'entity', 'autoencoder', 'isolation_forest', 'graph'],
              'input_report': report, 'priority_score_is_fraud_probability': False,
              'explanation_numbers_supported': True, 'performance_on_real_data_verified': False}
    cfg = json.loads(Path(config).read_text(encoding='utf-8')) if isinstance(config, (str, Path)) else config
    manifest = {'config': cfg, 'week': week, 'company_id': company_id, 'labels_read': False,
                'input_snapshot_sha256': hashes, 'model_sha256': None,
                'code_sha256': {str(path.relative_to(ROOT)): sha(path) for path in (ROOT / 'agent2').glob('*.py')}}
    for name, content in (('report.json', result), ('run_manifest.json', manifest)):
        (out / name).write_text(json.dumps(clean(content), ensure_ascii=False, indent=2), encoding='utf-8')
    return result, cases
