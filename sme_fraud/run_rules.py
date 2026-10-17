"""Run explainable rules, a review queue and comparable IF benchmarks."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

# evaluate configures the optional workspace dependencies before third-party imports.
from .evaluate import threshold_metrics
import joblib
import numpy as np
from sklearn.metrics import average_precision_score

from .benford import monthly_diagnostics
from .features import FEATURE_DESCRIPTIONS
from .generate import write_csv
from .rules import load_inputs, score_rules
from .case_queue import review_queue, batch_groups
from .feature_contract import require_model
import sklearn


def jsonl(path, records):
    with path.open('w', encoding='utf-8') as stream:
        for row in records:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')


def empirical_rank(validation, scores):
    reference = np.sort(validation)
    # Mid-rank ties; never use future/test distribution as the reference.
    return (np.searchsorted(reference, scores, side='left') + np.searchsorted(reference, scores, side='right')) / (2 * len(reference))


def evaluate_scores(y, scores, predicted, truth, transactions, ids):
    tp = int(np.sum(predicted & (y == 1)))
    fp = int(np.sum(predicted & (y == 0)))
    positives = int(y.sum())
    normal = int(len(y) - positives)
    metric = dict(alerts=int(predicted.sum()), tp=tp, fp=fp,
                  precision=tp / (tp + fp) if tp + fp else 0., recall=tp / positives if positives else 0.,
                  fpr=fp / normal if normal else 0., per_fraud_type=[], hard_negatives=[], per_accounting_framework=[])
    for kind in sorted({truth[i]['fraud_type'] for i in ids if int(truth[i]['is_fraud'])}):
        mask = np.array([truth[i]['fraud_type'] == kind and int(truth[i]['is_fraud']) == 1 for i in ids])
        metric['per_fraud_type'].append(dict(name=kind, rows=int(mask.sum()), detected=int(predicted[mask].sum()), recall=float(predicted[mask].mean())))
    for kind in sorted({truth[i]['hard_negative_type'] for i in ids} - {''}):
        mask = np.array([truth[i]['hard_negative_type'] == kind and int(truth[i]['is_fraud']) == 0 for i in ids])
        metric['hard_negatives'].append(dict(name=kind, rows=int(mask.sum()), false_alerts=int(predicted[mask].sum()), fpr=float(predicted[mask].mean())))
    for framework in sorted({transactions[i]['accounting_framework'] for i in ids}):
        mask = np.array([transactions[i]['accounting_framework'] == framework for i in ids])
        support = int(y[mask].sum())
        hit = int(np.sum(predicted[mask] & (y[mask] == 1)))
        alerts = int(predicted[mask].sum())
        wrong = alerts - hit
        metric['per_accounting_framework'].append(dict(name=framework, rows=int(mask.sum()), fraud_rows=support,
            alerts=alerts, tp=hit, fp=wrong, precision=hit / alerts if alerts else 0., recall=hit / support if support else 0.,
            fpr=wrong / int(np.sum(y[mask] == 0)) if np.any(y[mask] == 0) else 0.))
    case_hits = defaultdict(bool)
    for i, alert in zip(ids, predicted):
        if int(truth[i]['is_fraud']):
            case_hits[truth[i]['case_id']] |= bool(alert)
    metric['case_recall'] = dict(cases=len(case_hits), detected=sum(case_hits.values()),
        recall=sum(case_hits.values()) / len(case_hits) if case_hits else 0.)
    return metric


def run(dataset, output, model_path, budget=.003, config=None):
    if not 0 < budget < .5:
        raise ValueError('Alert budget must be between 0 and .5')
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'Refusing to overwrite non-empty output: {output}')
    output.mkdir(parents=True, exist_ok=True)
    tables, features, metadata = load_inputs(dataset)
    result = score_rules(tables, config=config, features=features)
    direct = score_rules(tables, config={**(config or {}), 'enable_graph': False}, features=features)
    print(f'{dataset.name}: scored {len(result["scores"]):,} observations', flush=True)
    diagnostics = monthly_diagnostics(tables)
    cases, events = review_queue(result, tables)
    score_rows = [{k: v for k, v in row.items() if k != 'known_risky_prior_ids'} for row in result['scores']]
    write_csv(output / 'rule_scores.csv', score_rows)
    write_csv(output / 'case_queue.csv', cases, list(cases[0]) if cases else [
        'case_id', 'company_id', 'status', 'owner_id', 'priority', 'explanation_vi'])
    write_csv(output / 'case_events.csv', events, ['case_id', 'event_at', 'event', 'transaction_id', 'rule_score', 'priority'])
    jsonl(output / 'rule_hits.jsonl', result['hits'])
    jsonl(output / 'batch_events.jsonl', result['batch_events'])
    jsonl(output / 'benford_diagnostics.jsonl', diagnostics)
    counts = Counter(r['rule_id'] for r in result['hits'] if not r['suppressed_reason'])
    suppressions = Counter(r['rule_id'] for r in result['hits'] if r['suppressed_reason'])
    for row in result['coverage']:
        if row['rule_id'].startswith('D'):
            subset = [r for r in diagnostics if r['rule_id'] == row['rule_id']]
            row['evaluated_windows'] = sum(r['status'] == 'evaluated' for r in subset)
            row['skipped_windows'] = sum(r['status'] != 'evaluated' for r in subset)
            row['signals'] = sum(bool(r.get('signal')) for r in subset)
        else:
            row['hits'], row['suppressed_hits'] = counts[row['rule_id']], suppressions[row['rule_id']]
    (output / 'rule_coverage.json').write_text(json.dumps(result['coverage'], ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'rule_config.json').write_text(json.dumps(result['config'], ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(output / 'direct_rule_scores.csv', direct['scores'])
    return compare_results(dataset, output, model_path, budget, tables, features, metadata, result, direct, cases)


def compare_results(dataset, output, model_path, budget, tables, features, metadata, result, direct, cases):
    # Only the benchmark layer reads partition IDs, then labels AFTER thresholds freeze.
    import csv
    with (dataset / 'splits.csv').open(encoding='utf-8-sig', newline='') as stream:
        partitions = {r['transaction_id']: r['split'] for r in csv.DictReader(stream)}
    ids = [r['transaction_id'] for r in result['scores']]
    if set(partitions) != set(ids):
        raise ValueError('Split keys differ from scored IDs')
    val_mask = np.array([partitions[i] == 'validation' for i in ids])
    test_mask = np.array([partitions[i] == 'test' for i in ids])
    artifact = joblib.load(model_path)
    require_model(artifact, metadata, sklearn.__version__)
    x = np.array([[row[c] for c in artifact['feature_columns']] for row in features], dtype=np.float32)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite causal features')
    if_by_id = dict(zip([r['transaction_id'] for r in features], -artifact['model'].score_samples(x)))
    if_scores = np.array([if_by_id[i] for i in ids])
    rule_scores = np.array([r['rule_score'] for r in direct['scores']], dtype=float)
    graph_scores = np.array([r['rule_score'] for r in result['scores']], dtype=float)
    ensemble = .8 * empirical_rank(graph_scores[val_mask], graph_scores) + .2 * empirical_rank(if_scores[val_mask], if_scores)
    # Preserve the existing Agent 2 benchmark variant: IF only breaks ties within a rule-score band.
    gated = graph_scores + .5 * empirical_rank(if_scores[val_mask], if_scores)
    variants = {'Rules': rule_scores, 'IF': if_scores, 'Rules+Graph': graph_scores, 'Rules+Graph+IF': ensemble,
                'Rules+Graph gated by IF': gated}
    thresholds = {name: float(np.quantile(values[val_mask], 1 - budget, method='higher')) for name, values in variants.items()}
    with (dataset / 'labels.csv').open(encoding='utf-8-sig', newline='') as stream:
        truth = {r['transaction_id']: r for r in csv.DictReader(stream)}
    test_ids = [i for i, flag in zip(ids, test_mask) if flag]
    y = np.array([int(truth[i]['is_fraud']) for i in test_ids])
    transactions = {r['transaction_id']: r for r in tables['transactions']}
    report = dict(dataset=str(dataset), dataset_version=metadata['version'], seed=metadata['seed'],
        validation_alert_budget=budget, test_rows=len(test_ids), test_fraud_rows=int(y.sum()),
        fixed_capacity_k=math_ceil(budget * len(test_ids)),
        threshold_policy='Unlabelled validation quantile; all ties retained (may exceed budget)',
        ranking_policy='Fixed capacity set before test labels; tie-break by SHA256(transaction_id)',
        ensemble_policy='Preset .8 rule validation midrank + .2 IF validation midrank; no label tuning',
        models={}, review_cases=len(cases), operational_alerts=sum(r['operational_alert'] for r in result['scores']),
        batch_events=len(result['batch_events']),
        batch_review_participants=len({tid for group in batch_groups(result) for tid in group['_members']}),
        coverage_status=dict(Counter(r['status'] for r in result['coverage'])),
        limitations=['Synthetic single-seed benchmark, not real SME performance.',
            'Existing test was inspected in prior iterations; use a fresh sealed dataset for final acceptance.',
            'No retroactive alerts on an earlier payment using a later transaction.',
            'D-group diagnostics are aggregate screens and do not add transaction scores.',
            'Queue is an offline snapshot with suggested ownership/SLA, no messages or automatic transaction blocks.',
            'Rule score/ensemble score are not calibrated fraud probabilities.'])
    predictions = []
    tie_keys = np.array([hashlib.sha256(i.encode()).hexdigest() for i in test_ids])
    for name, values in variants.items():
        test_values = values[test_mask]
        predicted = test_values >= thresholds[name]
        order = np.lexsort((tie_keys, -test_values))
        k = report['fixed_capacity_k']
        top_predicted = np.zeros(len(y), dtype=bool)
        top_predicted[order[:k]] = True
        metrics = dict(average_precision=float(average_precision_score(y, test_values)),
            threshold=thresholds[name], validation_alert_rate=float(np.mean(values[val_mask] >= thresholds[name])),
            threshold_metrics=evaluate_scores(y, test_values, predicted, truth, transactions, test_ids),
            fixed_capacity=evaluate_scores(y, test_values, top_predicted, truth, transactions, test_ids), top_k=[])
        for count in (25, 50, 75, 100, 250):
            count = min(count, len(y))
            positives = int(y[order[:count]].sum())
            metrics['top_k'].append(dict(k=count, tp=positives, precision=positives / count, recall=positives / int(y.sum())))
        report['models'][name] = metrics
        predictions.extend(dict(transaction_id=i, model=name, score=float(s), threshold_alert=int(p), capacity_alert=int(q))
                           for i, s, p, q in zip(test_ids, test_values, predicted, top_predicted))
    operational = np.array([bool(row['operational_alert']) for row in result['scores']])[test_mask]
    report['operational_threshold_metrics'] = evaluate_scores(y, graph_scores[test_mask], operational, truth, transactions, test_ids)
    (output / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    write_csv(output / 'comparison_scores_test.csv', predictions)
    lines = ['# Bộ luật và benchmark phát hiện SME', '',
        f"Dữ liệu v{metadata['version']}, seed {metadata['seed']}; test {len(y):,} quan sát, {int(y.sum())} gian lận ({y.mean():.1%}).",
        'Đọc 6 nhóm A–F gồm 31 quy tắc; bổ sung P1/T1/T2 để giữ phạm vi sáu loại gian lận ban đầu.',
        f"Ngân sách validation {budget:.1%}; bảng dưới so sánh cùng sức chứa {report['fixed_capacity_k']} cảnh báo test.", '',
        '| Phương án | AP | Phát hiện | Precision | Recall | Cảnh báo sai |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name, item in report['models'].items():
        selected = item['fixed_capacity']
        lines.append(f"| {name} | {item['average_precision']:.4f} | {selected['tp']} | {selected['precision']:.1%} | {selected['recall']:.1%} | {selected['fp']} |")
    lines += ['', '## Ngưỡng validation và vấn đề điểm bằng nhau', '',
        '| Phương án | Ngưỡng | Tỷ lệ cảnh báo validation | Cảnh báo test | Precision test | Recall test |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name, item in report['models'].items():
        selected = item['threshold_metrics']
        lines.append(f"| {name} | {item['threshold']:.6f} | {item['validation_alert_rate']:.2%} | {selected['alerts']} | {selected['precision']:.1%} | {selected['recall']:.1%} |")
    lines += ['', 'Điểm luật rời rạc có nhiều trường hợp bằng nhau. Giữ mọi điểm bằng ngưỡng có thể vượt ngân sách; '
        'bảng sức chứa cố định chỉ dùng để so sánh thứ hạng, không lấy phân vị test để chọn ngưỡng vận hành.', '',
        f"Hàng đợi toàn kỳ: {len(cases):,} hồ sơ, {report['operational_alerts']:,} quan sát có điểm ≥ {result['config']['operational_score']}.",
        'Hàng đợi này dùng ngưỡng nghiệp vụ mặc định; không đồng nghĩa bộ cảnh báo đã hiệu chỉnh theo ngân sách.', '',
        '## Phạm vi triển khai', '', '| Rule | Trạng thái | Ghi chú |', '| --- | --- | --- |']
    lines += [f"| {r['rule_id']} | {r['status']} | {r['note']} |" for r in result['coverage']]
    lines += ['', '## Giới hạn', '', *[f'- {note}' for note in report['limitations']], '',
              f'Kiểm định Chi-square: [SciPy]({SOURCE_URL}). Ngưỡng Benford là giả định rà soát từ file luật; '
              'kiểm tra phạm vi, độ đa dạng và tần suất kỳ vọng trước khi tính p-value; hiệu chỉnh BH theo mỗi thời điểm.', '']
    (output / 'report_vi.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({name: {key: row['fixed_capacity'][key] for key in ('alerts', 'tp', 'fp', 'precision', 'recall')}
                           | {'average_precision': row['average_precision']} for name, row in report['models'].items()}, ensure_ascii=False), flush=True)
    return report


def math_ceil(value):
    import math
    return max(1, math.ceil(value))


SOURCE_URL = 'https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chisquare.html'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/sme_fraud_003'))
    parser.add_argument('--output', type=Path, default=Path('reports/rules/sme_fraud_003'))
    parser.add_argument('--if-model', type=Path, default=Path('reports/sme_fraud_003/isolation_forest.joblib'))
    parser.add_argument('--alert-budget', type=float, default=.003)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8')) if args.config else None
    run(args.data, args.output, args.if_model, args.alert_budget, config)


if __name__ == '__main__':
    main()
