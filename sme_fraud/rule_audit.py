"""Audit each frozen rule; no model imports, training, or threshold selection."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from datetime import timedelta
from itertools import groupby
from pathlib import Path

from .generate import parse, write_csv
from .rules import RULE_NAMES
from .rule_audit_policy import NO_POSITIVE_TRUTH, SPEC_NOTES, TARGETS, eligible, target_match

MAIN_RULES = [rule for rule in RULE_NAMES if rule[0] in 'ABCDEF']
EXTRA_RULES = ['P1', 'T1', 'T2']
PERIODS = ('train', 'validation', 'test')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def wilson(success, total):
    if not total:
        return None
    z = 1.95996398454
    p, scale = success / total, 1 + z * z / total
    center = (p + z * z / (2 * total)) / scale
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / scale
    return [max(0., center - half), min(1., center + half)]


def confusion(ids, predictions, labels):
    population = set(ids)
    positives = {i for i in population if int(labels[i]['is_fraud'])}
    selected = population & set(predictions)
    tp, fp = len(selected & positives), len(selected - positives)
    fn, tn = len(positives - selected), len(population - positives - selected)
    return dict(rows=len(population), fraud_rows=len(positives), normal_rows=len(population) - len(positives),
        alerts=len(selected), tp=tp, fp=fp, fn=fn, tn=tn, fraud_precision=ratio(tp, tp + fp),
        fraud_recall_all=ratio(tp, tp + fn), fpr=ratio(fp, fp + tn),
        accuracy=ratio(tp + tn, len(population)),
        false_alerts_per_1000_normal=1000 * fp / (fp + tn) if fp + tn else None,
        fraud_precision_wilson_row95=wilson(tp, tp + fp))


def replay_scores(transactions, points, config, omitted=frozenset()):
    """Exact frozen-hit replay, including changed recurrence after dropping a rule."""
    history, result = defaultdict(deque), {}
    for timestamp, iterator in groupby(transactions, key=lambda r: r['posted_at']):
        batch, updates = list(iterator), []
        now = parse(timestamp)
        for row in batch:
            key = (row['company_id'], row['vendor_id'] or row['employee_id'] or row['creator_id'])
            prior = history[key]
            while prior and (now - prior[0]).total_seconds() > 30 * 86400:
                prior.popleft()
            family_points = {}
            for code, weight in points.get(row['transaction_id'], {}).items():
                if code in omitted:
                    continue
                family = 'master_duplicate' if code in {'B5', 'E4', 'E3'} else code[0]
                family_points[family] = max(family_points.get(family, 0), weight)
            base = sum(family_points.values())
            recurrent = min(config['recurrence_cap'], len(prior)) if base >= config['operational_score'] else 0
            score = base + recurrent
            result[row['transaction_id']] = dict(base_score=base, recurrence_points=recurrent, rule_score=score,
                                                 alert=score >= config['operational_score'])
            if score >= config['operational_score']:
                updates.append(key)
        for key in updates:
            history[key].append(now)
    return result


def period_for_window(cutoff):
    # The diagnostic is reported after a closed calendar window; Jan 1 belongs
    # to the year ending immediately before it, not an invented future test set.
    ending = parse(cutoff) - timedelta(microseconds=1)
    return 'train' if ending.year == 2024 else 'validation' if ending.year == 2025 and ending.month <= 6 else 'test' if ending.year == 2025 else None


def scenario_coverage(rule, ids, selected, labels):
    if rule not in TARGETS:
        return dict(status='no_rule_specific_positive_truth', rows=None, hits=None, coverage=None,
                    cases=None, detected_cases=None, case_coverage=None, available_label_rows=None,
                    available_label_coverage=None, note=NO_POSITIVE_TRUTH.get(rule, 'Không có nhãn riêng cho điều kiện rule.'))
    relevant = {i for i in ids if target_match(rule, labels[i])}
    detected = relevant & selected
    cases = {labels[i]['case_id'] for i in relevant}
    found_cases = {labels[i]['case_id'] for i in detected}
    available = {i for i in relevant if labels[i]['observability'] == 'available'}
    family, variants = TARGETS[rule]
    return dict(status='mapped_synthetic_scenario_proxy', family=family, variants=sorted(variants) if variants else None,
                rows=len(relevant), hits=len(detected), coverage=ratio(len(detected), len(relevant)),
                cases=len(cases), detected_cases=len(found_cases), case_coverage=ratio(len(found_cases), len(cases)),
                available_label_rows=len(available), available_label_coverage=ratio(len(available & selected), len(available)),
                note='Bao phủ nhãn kịch bản, không phải sensitivity đối với vi phạm/điều kiện rule được gán nhãn độc lập.')


def profiles_for_rule(rule, ids, active, candidates, suppressed, labels, transactions, all_active):
    selected, raw, waived = active & set(ids), candidates & set(ids), suppressed & set(ids)
    metric = confusion(ids, selected, labels)
    scoped = [i for i in ids if eligible(rule, transactions[i])]
    metric['input_scope'] = confusion(scoped, selected, labels)
    metric['candidate_count'] = len(raw)
    metric['suppressed_count'] = len(waived)
    metric['suppressed_fraud_rows'] = sum(int(labels[i]['is_fraud']) for i in waived)
    metric['suppressed_normal_rows'] = len(waived) - metric['suppressed_fraud_rows']
    metric['candidate_fraud_precision'] = confusion(ids, raw, labels)['fraud_precision']
    metric['scenario'] = scenario_coverage(rule, ids, selected, labels)
    metric['exclusive_tp'] = sum(int(labels[i]['is_fraud']) for i in selected if all_active[i] == {rule})
    metric['exclusive_fp'] = sum(not int(labels[i]['is_fraud']) for i in selected if all_active[i] == {rule})
    metric['per_fraud_type'] = []
    for name in sorted({labels[i]['fraud_type'] for i in ids if int(labels[i]['is_fraud'])}):
        members = {i for i in ids if labels[i]['fraud_type'] == name and int(labels[i]['is_fraud'])}
        metric['per_fraud_type'].append(dict(name=name, support=len(members), hits=len(members & selected), coverage=ratio(len(members & selected), len(members))))
    metric['hard_negatives'] = []
    for name in sorted({labels[i]['hard_negative_type'] for i in ids} - {''}):
        members = {i for i in ids if labels[i]['hard_negative_type'] == name}
        metric['hard_negatives'].append(dict(name=name, support=len(members), flags=len(members & selected),
                                           fpr=ratio(len(members & selected), len(members)), suppressed=len(members & waived)))
    metric['per_company'] = [dict(name=name, **confusion([i for i in ids if transactions[i]['company_id'] == name], selected, labels))
                             for name in sorted({transactions[i]['company_id'] for i in ids})]
    metric['per_framework'] = [dict(name=name, **confusion([i for i in ids if transactions[i]['accounting_framework'] == name], selected, labels))
                               for name in sorted({transactions[i]['accounting_framework'] for i in ids})]
    metric['false_positive_breakdown'] = dict(Counter(
        f"hard_negative:{labels[i]['hard_negative_type']}" if labels[i]['hard_negative_type']
        else 'labelled_normal_support' if labels[i]['case_role'] == 'support' else 'normal_background'
        for i in selected if not int(labels[i]['is_fraud'])))
    return metric


def audit_scenario(dataset, report):
    manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    required = ['transactions.csv', 'labels.csv', 'splits.csv', 'companies.csv', 'vendors.csv']
    source_hashes = {}
    for name in required:
        current = sha(dataset / name)
        if current != manifest['files'][name]['sha256']:
            raise ValueError(f'Source checksum differs: {dataset / name}')
        source_hashes[str(dataset / name)] = current
    saved_names = ['rule_hits.jsonl', 'rule_scores.csv', 'rule_config.json', 'rule_coverage.json', 'benford_diagnostics.jsonl']
    for name in saved_names:
        source_hashes[str(report / name)] = sha(report / name)
    rows = read_csv(dataset / 'transactions.csv')
    transactions = {r['transaction_id']: r for r in rows}
    labels = {r['transaction_id']: r for r in read_csv(dataset / 'labels.csv')}
    splits = {r['transaction_id']: r['split'] for r in read_csv(dataset / 'splits.csv')}
    if len(transactions) != len(rows) or set(transactions) != set(labels) or set(labels) != set(splits):
        raise ValueError('Observation keys are not aligned one-to-one')
    if rows != sorted(rows, key=lambda r: (r['posted_at'], r['transaction_id'])):
        raise ValueError('Source observations must be sorted chronologically')
    partitions = {name: [i for i in transactions if splits[i] == name] for name in PERIODS}
    coverage = {r['rule_id']: r for r in json.loads((report / 'rule_coverage.json').read_text(encoding='utf-8'))}
    config = json.loads((report / 'rule_config.json').read_text(encoding='utf-8'))
    active, candidates, suppressed = defaultdict(set), defaultdict(set), defaultdict(set)
    points, details = defaultdict(dict), defaultdict(dict)
    all_active = defaultdict(set)
    with (report / 'rule_hits.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            hit = json.loads(line)
            code, tid = hit['rule_id'], hit['transaction_id']
            if tid not in transactions or code not in RULE_NAMES or tid in candidates[code]:
                raise ValueError('Unknown or duplicate rule hit')
            if hit['detected_at'] != transactions[tid]['posted_at'] or hit['points'] < 0:
                raise ValueError('Invalid scored evidence')
            if any(transactions[i]['posted_at'] >= hit['detected_at'] for i in hit['related_transaction_ids']):
                raise ValueError('Future/simultaneous evidence in saved hit')
            if any(e['observed_at'] > hit['detected_at'] for e in hit['graph_path']):
                raise ValueError('Future graph evidence')
            candidates[code].add(tid)
            details[code][tid] = hit
            if hit['suppressed_reason']:
                if hit['points'] or hit['hard_trigger']:
                    raise ValueError('Suppressed rule contributes points')
                suppressed[code].add(tid)
            elif hit['points'] > 0:
                active[code].add(tid)
                points[tid][code] = hit['points']
                all_active[tid].add(code)
    baseline = replay_scores(rows, points, config)
    saved_scores = {r['transaction_id']: r for r in read_csv(report / 'rule_scores.csv')}
    if set(saved_scores) != set(transactions):
        raise ValueError('Saved rule scores do not cover observations')
    for tid, current in baseline.items():
        for field in ('base_score', 'recurrence_points', 'rule_score'):
            if current[field] != int(saved_scores[tid][field]):
                raise ValueError(f'Frozen replay differs: {tid} {field}')
        if current['alert'] != bool(int(saved_scores[tid]['operational_alert'])):
            raise ValueError('Operational alert replay differs')
    operational = {i for i in transactions if baseline[i]['alert']}
    baseline_metrics = {name: confusion(ids, operational, labels) for name, ids in partitions.items()}
    diagnostics = defaultdict(list)
    with (report / 'benford_diagnostics.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['adds_transaction_score']:
                raise ValueError('Aggregate diagnostic incorrectly adds transaction score')
            diagnostics[row['rule_id']].append(row)
    result, examples, overlaps = [], [], []
    for code in [*MAIN_RULES, *EXTRA_RULES]:
        row = dict(rule_id=code, rule_name=RULE_NAMES[code], is_main_31=code in MAIN_RULES,
                   scope=coverage[code]['scope'], implementation_status=coverage[code]['status'],
                   coverage_note=coverage[code]['note'], specification_review=SPEC_NOTES[code], periods={})
        if coverage[code]['status'] == 'not_evaluable':
            row['audit_status'] = 'missing_source_or_implementation'
            row['periods'] = {name: None for name in PERIODS}
        elif code.startswith('D'):
            row['audit_status'] = 'aggregate_truth_unavailable'
            for name in PERIODS:
                windows = [w for w in diagnostics[code] if period_for_window(w['cutoff_at']) == name]
                tested = [w for w in windows if w['status'] == 'evaluated']
                row['periods'][name] = dict(unit='aggregate_window', windows=len(windows), evaluated=len(tested),
                    skipped=len(windows) - len(tested), signals=sum(bool(w.get('signal')) for w in tested),
                    skip_reasons=dict(Counter(reason for w in windows for reason in w['skip_reasons'])),
                    fraud_precision=None, fpr=None, target_coverage=None,
                    note='Không có nhãn gian lận/vi phạm độc lập cấp cửa sổ; không tính TP/FP từ nhãn từng dòng.')
        else:
            row['audit_status'] = 'transaction_fraud_label_audit'
            for name, ids in partitions.items():
                row['periods'][name] = profiles_for_rule(code, ids, active[code], candidates[code], suppressed[code], labels, transactions, all_active)
            without = replay_scores(rows, points, config, omitted={code})
            if any(without[i]['rule_score'] > baseline[i]['rule_score'] for i in transactions):
                raise ValueError('Dropping a nonnegative rule increased score')
            no_rule = {i for i in transactions if without[i]['alert']}
            row['ablation'] = {}
            for name in ('validation', 'test'):
                current = confusion(partitions[name], no_rule, labels)
                base = baseline_metrics[name]
                row['ablation'][name] = dict(without_rule=current, fewer_false_alerts=base['fp'] - current['fp'],
                    fewer_true_detections=base['tp'] - current['tp'], fixed_operational_threshold=config['operational_score'],
                    mode='frozen_hits_replay_with_30day_recurrence_not_threshold_retuning')
            test_ids = set(partitions['test'])
            categories = {'false_positive': [i for i in active[code] & test_ids if not int(labels[i]['is_fraud'])],
                          'true_positive': [i for i in active[code] & test_ids if int(labels[i]['is_fraud'])],
                          'missed_target_scenario': [i for i in test_ids - active[code] if target_match(code, labels[i])],
                          'suppressed_fraud': [i for i in suppressed[code] & test_ids if int(labels[i]['is_fraud'])]}
            for kind, ids in categories.items():
                ids.sort(key=lambda i: (not bool(labels[i]['hard_negative_type']), labels[i]['hard_negative_type'], transactions[i]['txn_type'], i))
                chosen, signatures = [], set()
                for tid in ids:
                    signature = (labels[tid]['hard_negative_type'], transactions[tid]['txn_type'], transactions[tid]['company_id'])
                    if signature not in signatures:
                        chosen.append(tid)
                        signatures.add(signature)
                    if len(chosen) == 8:
                        break
                for tid in chosen:
                    tx, truth, hit = transactions[tid], labels[tid], details[code].get(tid)
                    examples.append(dict(rule_id=code, example_type=kind, transaction_id=tid, company_id=tx['company_id'],
                        posted_at=tx['posted_at'], txn_type=tx['txn_type'], amount_vnd=int(tx['amount_vnd']),
                        approval_limit_vnd=int(tx['approval_limit_vnd']), vendor_id=tx['vendor_id'], employee_id=tx['employee_id'],
                        creator_id=tx['creator_id'], approver_id=tx['approver_id'], debit_account=tx['debit_account'],
                        credit_account=tx['credit_account'], support_doc_count=tx['support_doc_count'],
                        is_fraud=int(truth['is_fraud']), fraud_type=truth['fraud_type'], variant=truth['variant'],
                        case_id=truth['case_id'], case_role=truth['case_role'], hard_negative_type=truth['hard_negative_type'],
                        observability=truth['observability'], evidence_json=json.dumps(hit['evidence'], ensure_ascii=False) if hit else '',
                        related_transaction_ids=json.dumps(hit['related_transaction_ids']) if hit else '',
                        suppression_reason=hit['suppressed_reason'] if hit else ''))
        result.append(row)
    transaction_codes = [c for c in MAIN_RULES if not c.startswith('D') and coverage[c]['status'] != 'not_evaluable']
    test_population = set(partitions['test'])
    for index, left in enumerate(transaction_codes):
        for right in transaction_codes[index + 1:]:
            a, b = active[left] & test_population, active[right] & test_population
            union, common = a | b, a & b
            if common:
                overlaps.append(dict(left=left, right=right, intersection=len(common), jaccard=len(common) / len(union),
                    identical_incidence=a == b, shared_normal=sum(not int(labels[i]['is_fraud']) for i in common)))
    for path, before in source_hashes.items():
        if sha(Path(path)) != before:
            raise ValueError(f'Input changed during audit: {path}')
    vendors = read_csv(dataset / 'vendors.csv')
    return dict(dataset=str(dataset), dataset_version=manifest['version'], seed=manifest['seed'],
                requested_fraud_rate=manifest['requested_fraud_rate'], rules=result, source_hashes=source_hashes,
                baseline_operational=baseline_metrics, frozen_score_replay='passed', examples=examples,
                overlaps=sorted(overlaps, key=lambda r: (-r['jaccard'], -r['intersection'])),
                master_name_quality=dict(vendors=len(vendors),
                    synthetic_common_prefix=sum(v['name'].startswith('Công ty mô phỏng đối tác') for v in vendors)))


def fmt(value, percent=False):
    return 'N/A' if value is None else f'{value:.4%}' if percent and 0 < value < .0001 else f'{value:.2%}' if percent else str(value)


def recommendation(code, fixtures):
    gaps = [r for r in fixtures if r['rule_id'] == code and not r['passed']]
    if gaps:
        return 'Sửa/đối chiếu logic và ngoại lệ trước khi nâng thành luật cứng.'
    if code in {'C4', 'E2', 'F2', 'F3', 'F4'}:
        return 'Bổ sung dữ liệu nguồn và implementation; chưa thể nghiệm thu.'
    if code.startswith('D'):
        return 'Giữ chẩn đoán tập dữ liệu; cần nhãn cấp cửa sổ để đo hiệu quả phát hiện.'
    if code in {'B5', 'E4', 'E3'}:
        return 'Ưu tiên chất lượng master/đối chứng tên thật; không dùng riêng để kết luận gian lận.'
    if code in {'C1', 'A4', 'A5', 'B3', 'B6', 'C3'}:
        return 'Giữ tín hiệu bổ trợ; cần bối cảnh nghiệp vụ và đối chứng hợp lệ trước khi cảnh báo cứng.'
    if code in {'A1', 'A2', 'A3'}:
        return 'Ưu tiên tách giao dịch mua độc lập với yêu cầu chi chung; kiểm tra các cửa sổ và ngoại lệ.'
    return 'Ứng viên kiểm soát có điều kiện trong phạm vi đã thử; cần mẫu độc lập và nguồn thực để nghiệm thu.'


def review_decision(code, fixtures):
    gaps = [r for r in fixtures if r['rule_id'] == code and not r['passed']]
    if code in {'C4', 'E2', 'F2', 'F3', 'F4'}:
        return 'Chưa nghiệm thu: thiếu nguồn/implementation'
    if code.startswith('D'):
        return 'Chẩn đoán cấp tập; chưa đo precision gian lận'
    if any(r['scope'] in {'business_expectation', 'causal_temporal'} for r in gaps):
        return 'Ưu tiên sửa lỗi/ngoại lệ trước khi dùng cứng'
    if gaps:
        return 'Cần thống nhất mô tả và phạm vi trước khi dùng cứng'
    if code in {'B5', 'E3', 'E4'}:
        return 'Kiểm tra chất lượng master; tránh cảnh báo gian lận độc lập'
    if code in {'A4', 'A5', 'B3', 'B6', 'C1', 'C3'}:
        return 'Tín hiệu bổ trợ, cần thêm ngữ cảnh nghiệp vụ'
    return 'Ứng viên kiểm soát có điều kiện; chưa nghiệm thu thực địa'


def write_reports(output, audits, fixtures, detector_hashes):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'rules').mkdir(exist_ok=True)
    flat, sample_rows, overlap_rows, ablations = [], [], [], []
    for audit in audits:
        rate = audit['requested_fraud_rate']
        for rule in audit['rules']:
            for period, metric in rule['periods'].items():
                record = dict(prevalence=rate, period=period, rule_id=rule['rule_id'], is_main_31=rule['is_main_31'],
                    scope=rule['scope'], implementation_status=rule['implementation_status'], audit_status=rule['audit_status'])
                if metric is not None and rule['scope'] == 'transaction':
                    record.update({k: metric[k] for k in ('rows', 'alerts', 'tp', 'fp', 'fn', 'tn', 'fraud_precision', 'fraud_recall_all', 'fpr', 'accuracy', 'candidate_count', 'suppressed_count', 'suppressed_fraud_rows', 'exclusive_tp', 'exclusive_fp')})
                    record.update(scope_rows=metric['input_scope']['rows'], scope_fpr=metric['input_scope']['fpr'],
                        scenario_support=metric['scenario']['rows'], scenario_coverage=metric['scenario']['coverage'],
                        scenario_cases=metric['scenario']['cases'], scenario_case_coverage=metric['scenario']['case_coverage'],
                        precision_ci_lower=metric['fraud_precision_wilson_row95'][0] if metric['fraud_precision_wilson_row95'] else None,
                        precision_ci_upper=metric['fraud_precision_wilson_row95'][1] if metric['fraud_precision_wilson_row95'] else None)
                elif metric is not None:
                    record.update({k: metric[k] for k in ('windows', 'evaluated', 'skipped', 'signals')})
                flat.append(record)
            for period, result in rule.get('ablation', {}).items():
                ablations.append(dict(prevalence=rate, period=period, rule_id=rule['rule_id'],
                    fewer_false_alerts=result['fewer_false_alerts'], fewer_true_detections=result['fewer_true_detections'],
                    fixed_threshold=result['fixed_operational_threshold'],
                    remaining_alerts=result['without_rule']['alerts']))
        sample_rows.extend(dict(prevalence=rate, **row) for row in audit['examples'])
        overlap_rows.extend(dict(prevalence=rate, **row) for row in audit['overlaps'])
    fields = list(dict.fromkeys(key for row in flat for key in row))
    write_csv(output / 'rule_metrics.csv', [{key: row.get(key) for key in fields} for row in flat], fields)
    write_csv(output / 'examples.csv', sample_rows)
    write_csv(output / 'overlap.csv', overlap_rows)
    write_csv(output / 'ablation.csv', ablations)
    fixture_fields = ['rule_id', 'case_id', 'description', 'expected_active', 'actual_active', 'passed', 'observed_points', 'scope']
    write_csv(output / 'controlled_cases.csv',
              [{field: row[field] for field in fixture_fields} for row in fixtures], fixture_fields)
    decisions = [dict(rule_id=code, rule_name=RULE_NAMES[code],
                      decision=review_decision(code, fixtures), recommendation=recommendation(code, fixtures),
                      controlled_cases=sum(r['rule_id'] == code for r in fixtures),
                      controlled_gaps=sum(r['rule_id'] == code and not r['passed'] for r in fixtures),
                      specification_review=SPEC_NOTES[code]) for code in MAIN_RULES]
    write_csv(output / 'rule_decisions.csv', decisions)
    full = dict(audits=audits, controlled_cases=fixtures, inspected_detector_sha256=detector_hashes,
        model_usage='none', rule_mutations='none', main_rule_count=len(MAIN_RULES), decisions=decisions,
        inspected_auditor_sha256={str(path): sha(path) for path in
            [Path(__file__), Path(__file__).with_name('rule_audit_policy.py'), Path(__file__).with_name('rule_audit_cases.py')]},
        method='frozen per-rule candidates and active flags, fraud intent labels, scenario coverage proxy, operational ablation replay',
        limitations=['Một seed tổng hợp; ba tỷ lệ là các kịch bản liên quan, không phải ba mẫu độc lập.',
            'Nhãn ý đồ gian lận chưa phải nhãn độc lập về điều kiện/vi phạm từng rule; precision gian lận không chứng minh predicate đúng/sai.',
            'Wilson theo dòng chưa hiệu chỉnh tương quan theo vụ/NCC.',
            'Không có hit thì precision N/A; thiếu kịch bản dương không đủ cơ sở kết luận sensitivity.',
            'Các rule D và rule thiếu nguồn không được gán TP/FP/accuracy giả.',
            'Test đã được xem trước đó; tối ưu trên validation và dùng test mới giữ kín để nghiệm thu.',
            'Ablation dùng ngưỡng vận hành cố định và hit đã lưu; không chọn ngân sách/ngưỡng theo nhãn.',
            'Fixture kiểm tra kỳ vọng nghiệp vụ cụ thể, không đo precision/recall thực tế.',
            'Replay đối chiếu tổng điểm; chưa tái chạy toàn bộ predicate trên 300.000 dòng.'])
    (output / 'audit.json').write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding='utf-8')
    main = next(a for a in audits if math.isclose(a['requested_fraud_rate'], .003))
    lines = ['# Rule Audit — 31 quy tắc A–F', '',
        'Audit baseline trên ba bộ v2, cùng seed, tổng 300.000 quan sát. Không train/chấm ML, không sửa luật/ngưỡng/dữ liệu.',
        'Mỗi rule được đánh giá độc lập ở tất cả hit còn điểm sau ngoại lệ, không lấy top-75 hoặc ngưỡng tổng hợp làm hit của rule.',
        'Bảng chính dùng **test 0,3%: 25.000 quan sát, 75 dòng gian lận**. Train/validation/test và cả ba tỷ lệ có trong CSV/JSON.', '',
        'Precision dưới đây là tỷ lệ hit rơi vào dòng có ý đồ gian lận được cài. FP là hit trên dòng nhãn 0, chưa chứng minh rule sai về điều kiện nghiệp vụ.',
        'Bao phủ kịch bản là proxy theo family/variant, không phải sensitivity của vi phạm rule được gán nhãn độc lập.', '',
        '**Phạm vi:** 20 rule giao dịch đo được theo nhãn dòng, 6 rule D thiếu nhãn cấp tập, 5 rule thiếu nguồn/implementation. ',
        'Không có rule nào được tuyên bố hoàn thiện chỉ từ một seed tổng hợp. Quyết định cho đủ 31 rule ở [rule_decisions.csv](rule_decisions.csv).', '',
        '| Rule | Hit độc lập | TP | FP | Precision gian lận | FPR trong phạm vi | Bao phủ kịch bản | Ghi chú |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for rule in main['rules']:
        if not rule['is_main_31']:
            continue
        code, metric = rule['rule_id'], rule['periods']['test']
        if metric is None:
            lines.append(f'| [{code}](rules/{code}.md) | N/A | N/A | N/A | N/A | N/A | N/A | Thiếu nguồn/implementation |')
        elif code.startswith('D'):
            lines.append(f"| [{code}](rules/{code}.md) | {metric['signals']} cửa sổ | N/A | N/A | N/A | N/A | N/A | {metric['evaluated']}/{metric['windows']} cửa sổ đủ điều kiện; thiếu nhãn cấp tập |")
        else:
            note = 'Chưa có nhãn dương riêng' if code not in TARGETS else 'Kịch bản là proxy'
            lines.append(f"| [{code}](rules/{code}.md) | {metric['alerts']} | {metric['tp']} | {metric['fp']} | {fmt(metric['fraud_precision'], True)} | {fmt(metric['input_scope']['fpr'], True)} | {fmt(metric['scenario']['coverage'], True)} | {note} |")
    lines += ['', '## Baseline hàng đợi tại ngưỡng nghiệp vụ 7', '',
        '| Tỷ lệ gian lận mô phỏng | Cảnh báo test | TP | FP | Precision | FPR toàn tập |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for audit in audits:
        metric = audit['baseline_operational']['test']
        lines.append(f"| {audit['requested_fraud_rate']:.1%} | {metric['alerts']} | {metric['tp']} | {metric['fp']} | {fmt(metric['fraud_precision'], True)} | {fmt(metric['fpr'], True)} |")
    lines += ['', 'Baseline trên gồm 31 rule và ba rule phụ lục đang hoạt động. Đây là ngưỡng vận hành 7, khác benchmark top-75 hoặc ngưỡng validation 14 trong báo cáo trước.', '',
        '## Nguồn cảnh báo sai cần xem trước', '',
        '| Rule | FP độc lập test 0,3% | Giảm FP validation | Mất TP validation | Giảm FP test | Mất TP test |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    measured = [r for r in main['rules'] if r['is_main_31'] and 'ablation' in r]
    for rule in sorted(measured, key=lambda r: -r['ablation']['validation']['fewer_false_alerts'])[:10]:
        metric, dropped = rule['periods']['test'], rule['ablation']['test']
        validation = rule['ablation']['validation']
        lines.append(f"| {rule['rule_id']} | {metric['fp']} | {validation['fewer_false_alerts']} | {validation['fewer_true_detections']} | {dropped['fewer_false_alerts']} | {dropped['fewer_true_detections']} |")
    lines += ['', 'Thứ tự trên theo mức giảm FP **validation**, không chọn ngưỡng theo test. Loại bỏ rule chỉ là đối chứng audit, chưa áp dụng vào engine.',
        'Không cộng các delta bỏ rule do chồng lặp và max theo nhóm; không suy ra việc tắt rule là an toàn chỉ từ delta TP bằng 0 ở một kỳ.',
        'Ablation giữ các hit khác, lấy max theo nhóm như engine và phát lại lịch sử điểm tái diễn 30 ngày; baseline khớp tất cả 300.000 điểm đã lưu.', '',
        '## Đối chứng logic và ngoại lệ', '',
        f"{sum(r['passed'] for r in fixtures)}/{len(fixtures)} tình huống có kết quả khớp kỳ vọng. Các trường hợp lệch được giữ nguyên để chỉ ra việc cần sửa.", '',
        '| Rule | Tình huống lệch | Kỳ vọng / thực tế |', '| --- | --- | --- |']
    for row in fixtures:
        if not row['passed']:
            lines.append(f"| {row['rule_id']} | {row['description']} | {row['expected_active']} / {row['actual_active']} |")
    lines += ['', 'Đối chứng là tình huống có kiểm soát, nằm ngoài ba dataset; không trộn vào prevalence hay số liệu hiệu quả phát hiện.', '',
        '## Chồng lặp và chất lượng dữ liệu', '',
        '| Hai rule | Hit chung test 0,3% | Jaccard | Hit nhãn 0 chung |', '| --- | ---: | ---: | ---: |']
    for row in main['overlaps'][:8]:
        lines.append(f"| {row['left']} / {row['right']} | {row['intersection']} | {row['jaccard']:.2%} | {row['shared_normal']} |")
    quality = main['master_name_quality']
    lines += ['', f"Tên NCC có tiền tố chung 'Công ty mô phỏng đối tác': {quality['synthetic_common_prefix']}/{quality['vendors']}. "
        'Cần đối chứng E3 trên tên thật/fixture đa dạng; không sửa bộ sinh để làm đẹp precision.', '',
        '## P1/T1/T2 — phụ lục ngoài 31', '', '| Rule | Hit test | TP | FP | Precision gian lận |', '| --- | ---: | ---: | ---: | ---: |']
    for rule in main['rules']:
        if not rule['is_main_31']:
            metric = rule['periods']['test']
            lines.append(f"| {rule['rule_id']} | {metric['alerts']} | {metric['tp']} | {metric['fp']} | {fmt(metric['fraud_precision'], True)} |")
    lines += ['', 'Các rule phụ lục không được cộng vào con số 31. Baseline ablation vẫn gồm chúng vì đó là cấu hình hàng đợi hiện tại.', '',
        '## Cách đọc và giới hạn', '', *[f'- {note}' for note in full['limitations']], '',
        'Accuracy tổng thể có trong CSV/JSON để đối soát, không dùng xếp hạng vì tỷ lệ gian lận thấp. ',
        'Nguồn định nghĩa chỉ số: [precision](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.precision_score.html), '
        '[recall](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.recall_score.html). Mã audit tính bằng Python chuẩn, không gọi mô hình.', '',
        'Chi tiết từng rule: bấm mã trong bảng. [Ma trận CSV](rule_metrics.csv), [ví dụ TP/FP/bỏ sót](examples.csv), '
        '[đối chứng loại rule](ablation.csv), [đối chứng logic](controlled_cases.csv), [JSON đầy đủ](audit.json).',
        'Thứ tự việc tiếp theo: [ưu tiên sửa và tiêu chí kiểm tra](../rule_audit_priorities.md).', '']
    (output / 'summary_vi.md').write_text('\n'.join(lines), encoding='utf-8')
    for code in MAIN_RULES:
        first = next(r for r in main['rules'] if r['rule_id'] == code)
        detail = [f'# {code} — {RULE_NAMES[code]}', '', f"Phạm vi: {first['scope']}. Implementation: {first['implementation_status']}. Audit: {first['audit_status']}.", '',
            f"Kết luận audit: **{review_decision(code, fixtures)}**.", '',
            f"Giới hạn đã khai báo: {first['coverage_note'] or 'Không có ghi chú coverage cũ; vẫn cần kiểm tra spec bên dưới.'}", '',
            f"Đối chiếu mã/mô tả: {SPEC_NOTES[code]}", '', f"Hướng xử lý đề xuất: {recommendation(code, fixtures)}", '',
            '## Kết quả trên test ba tỷ lệ', '',
            '| Tỷ lệ | Hit | TP | FP | Precision | FPR trong phạm vi | Bao phủ kịch bản / số mẫu |',
            '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
        for audit in audits:
            entry = next(r for r in audit['rules'] if r['rule_id'] == code)
            metric = entry['periods']['test']
            if metric is None:
                detail.append(f"| {audit['requested_fraud_rate']:.1%} | N/A | N/A | N/A | N/A | N/A | Thiếu nguồn/implementation |")
            elif code.startswith('D'):
                detail.append(f"| {audit['requested_fraud_rate']:.1%} | {metric['signals']} cửa sổ | N/A | N/A | N/A | N/A | Đủ điều kiện {metric['evaluated']}/{metric['windows']} |")
            else:
                detail.append(f"| {audit['requested_fraud_rate']:.1%} | {metric['alerts']} | {metric['tp']} | {metric['fp']} | {fmt(metric['fraud_precision'], True)} | {fmt(metric['input_scope']['fpr'], True)} | {fmt(metric['scenario']['coverage'], True)} / {fmt(metric['scenario']['rows'])} |")
        detail += ['', '## Đối chứng có kiểm soát', '', '| Tình huống | Kỳ vọng hit | Thực tế hit | Kết quả |', '| --- | ---: | ---: | --- |']
        subset = [r for r in fixtures if r['rule_id'] == code]
        for fixture in subset:
            detail.append(f"| {fixture['description']} | {fixture['expected_active']} | {fixture['actual_active']} | {'Khớp' if fixture['passed'] else 'Cần sửa/đối chiếu'} |")
        if not subset:
            detail.append('| Chưa có đối chứng predicate đủ nguồn trong đợt này | N/A | N/A | Không nghiệm thu |')
        if first['periods']['test'] is not None and not code.startswith('D'):
            metric = first['periods']['test']
            detail += ['', '## Tác động bỏ rule khỏi hàng đợi', '',
                '| Kỳ | Giảm FP | Mất TP |', '| --- | ---: | ---: |']
            detail += [f"| {period} | {first['ablation'][period]['fewer_false_alerts']} | {first['ablation'][period]['fewer_true_detections']} |"
                       for period in ('validation', 'test')]
            detail += ['', 'Đối chứng tại ngưỡng 7, phát lại tái diễn và giữ hit khác; chưa áp dụng vào engine.']
            detail += ['', '## Hard negatives — test 0,3%', '', '| Loại hợp lệ | Số mẫu | Hit còn điểm | Ngoại lệ đã loại |', '| --- | ---: | ---: | ---: |']
            detail += [f"| {r['name']} | {r['support']} | {r['flags']} | {r['suppressed']} |" for r in metric['hard_negatives']]
            detail += ['', f"Ứng viên trước ngoại lệ: {metric['candidate_count']}; loại {metric['suppressed_count']}, trong đó {metric['suppressed_fraud_rows']} dòng mang nhãn gian lận.",
                f"95% Wilson theo dòng cho precision: {metric['fraud_precision_wilson_row95']}; không hiệu chỉnh tương quan vụ/NCC.", '',
                '## Ví dụ audit test 0,3%', '', '| Loại ví dụ | ID | Loại nghiệp vụ | Giá trị VND | Nhãn/kịch bản |', '| --- | --- | --- | ---: | --- |']
            selected_examples = [r for r in main['examples'] if r['rule_id'] == code]
            detail += [f"| {r['example_type']} | {r['transaction_id']} | {r['txn_type']} | {r['amount_vnd']} | {r['hard_negative_type'] or r['fraud_type'] or r['case_role']} |" for r in selected_examples]
        detail += ['', 'Chi tiết train/validation/test, theo công ty/chế độ kế toán, bằng chứng và giao dịch ngữ cảnh ở [audit.json](../audit.json) và [examples.csv](../examples.csv).',
                   'Precision là theo nhãn ý đồ gian lận mô phỏng; bao phủ kịch bản là proxy, không chứng minh predicate chính xác hay hiệu quả thực địa.', '']
        (output / 'rules' / f'{code}.md').write_text('\n'.join(detail), encoding='utf-8')
    return full


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--reports-root', type=Path, default=Path('reports/rules'))
    parser.add_argument('--output', type=Path, default=Path('reports/rule_audit'))
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f'Refusing to overwrite audit: {args.output}')
    root = Path(__file__).resolve().parents[1]
    codes = []
    import re
    for code in re.findall(r'\*\*([A-F]\d+)\*\*', (root / 'rule_class_1.md').read_text(encoding='utf-8')):
        if code not in codes:
            codes.append(code)
    if codes != MAIN_RULES or len(codes) != 31:
        raise ValueError('Rule registry does not match the 31 codes in rule_class_1.md')
    detector_paths = [root / 'rule_class_1.md', *[root / 'sme_fraud' / name for name in ('rules.py', 'features.py', 'benford.py', 'accounting.py', 'generate.py')]]
    detector_hashes = {str(path): sha(path) for path in detector_paths}
    audits = []
    for tag in ('001', '003', '005'):
        print(f'Auditing frozen rules: {tag}', flush=True)
        audits.append(audit_scenario(args.data_root / f'sme_fraud_{tag}', args.reports_root / f'sme_fraud_{tag}'))
    from .rule_audit_cases import run_cases
    fixtures = run_cases()
    if any(sha(Path(path)) != original for path, original in detector_hashes.items()):
        raise ValueError('Detector source changed during audit')
    write_reports(args.output, audits, fixtures, detector_hashes)
    print(json.dumps(dict(output=str(args.output), rules=31, controlled_cases=len(fixtures),
                         controlled_gaps=[r['case_id'] for r in fixtures if not r['passed']], model_usage='none'), ensure_ascii=False))


if __name__ == '__main__':
    main()
