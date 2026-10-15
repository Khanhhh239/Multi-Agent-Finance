"""Reconcile saved alerts, evidence chronology and fixed-capacity metrics."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .evaluate import threshold_metrics
import numpy as np
from sklearn.metrics import average_precision_score


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def audit(dataset, report_directory):
    manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    for name, entry in manifest['files'].items():
        if hashlib.sha256((dataset / name).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'Dataset changed: {name}')
    transactions = {r['transaction_id']: r for r in read_csv(dataset / 'transactions.csv')}
    scores = {r['transaction_id']: r for r in read_csv(report_directory / 'rule_scores.csv')}
    if set(scores) != set(transactions):
        raise ValueError('Scored observations differ from dataset')
    hit_count = 0
    with (report_directory / 'rule_hits.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            hit = json.loads(line)
            current = transactions[hit['transaction_id']]
            if hit['detected_at'] != current['posted_at']:
                raise ValueError('Alert time differs from observation time')
            for identifier in hit['related_transaction_ids']:
                prior = transactions[identifier]
                if prior['company_id'] != current['company_id'] or prior['posted_at'] >= current['posted_at']:
                    raise ValueError('Evidence transaction is future, simultaneous or cross-company')
            if any(e['observed_at'] > hit['detected_at'] for e in hit['graph_path']):
                raise ValueError('Graph evidence was not known at scoring time')
            if hit['suppressed_reason'] and (hit['points'] != 0 or hit['hard_trigger']):
                raise ValueError('Suppressed rule incorrectly contributes points')
            hit_count += 1
    cases = read_csv(report_directory / 'case_queue.csv')
    assigned = []
    for case in cases:
        identifiers = json.loads(case['transaction_ids'])
        assigned.extend(identifiers)
        members = [scores[i] for i in identifiers]
        if any(int(r['operational_alert']) != 1 or r['company_id'] != case['company_id'] for r in members):
            raise ValueError('Invalid queue membership')
        if max(int(r['rule_score']) for r in members) != int(case['max_score']):
            raise ValueError('Case score does not reconcile')
    expected_assigned = {i for i, r in scores.items() if int(r['operational_alert'])}
    if len(set(assigned)) != len(assigned) or set(assigned) != expected_assigned:
        raise ValueError('Queue duplicates or omits operational alerts')
    comparison = json.loads((report_directory / 'comparison.json').read_text(encoding='utf-8'))
    truth = {r['transaction_id']: r for r in read_csv(dataset / 'labels.csv')}
    partitions = {r['transaction_id']: r['split'] for r in read_csv(dataset / 'splits.csv')}
    predictions = defaultdict(list)
    for row in read_csv(report_directory / 'comparison_scores_test.csv'):
        if partitions[row['transaction_id']] != 'test':
            raise ValueError('Non-test observation in test benchmark')
        predictions[row['model']].append(row)
    models = {}
    for name, rows in predictions.items():
        if len(rows) != comparison['test_rows'] or len({r['transaction_id'] for r in rows}) != len(rows):
            raise ValueError('Test prediction keys/count differ')
        metric = comparison['models'][name]
        values = np.array([float(r['score']) for r in rows])
        y = np.array([int(truth[r['transaction_id']]['is_fraud']) for r in rows])
        ap = float(average_precision_score(y, values))
        if abs(ap - metric['average_precision']) > 1e-12:
            raise ValueError('AP does not reconcile')
        if not np.array_equal(values >= metric['threshold'], [bool(int(r['threshold_alert'])) for r in rows]):
            raise ValueError('Saved threshold decisions differ')
        selected = threshold_metrics(y, values, metric['threshold'])
        for key in ('tp', 'fp', 'alerts', 'precision', 'recall', 'fpr'):
            if abs(selected[key] - metric['threshold_metrics'][key]) > 1e-12:
                raise ValueError(f'Threshold metric differs: {name} {key}')
        tie_keys = np.array([hashlib.sha256(r['transaction_id'].encode()).hexdigest() for r in rows])
        order = np.lexsort((tie_keys, -values))
        capacity = np.zeros(len(rows), dtype=bool)
        capacity[order[:comparison['fixed_capacity_k']]] = True
        if not np.array_equal(capacity, [bool(int(r['capacity_alert'])) for r in rows]):
            raise ValueError('Saved capacity decisions differ')
        tp = int(y[capacity].sum())
        if tp != metric['fixed_capacity']['tp'] or int(capacity.sum()) != metric['fixed_capacity']['alerts']:
            raise ValueError('Fixed-capacity confusion counts differ')
        models[name] = dict(average_precision=ap, capacity_tp=tp, capacity_alerts=int(capacity.sum()))
    result = dict(status='passed', observations=len(scores), evidence_hits=hit_count,
                  cases=len(cases), operational_observations=len(assigned), models=models,
                  checks=['all_dataset_checksums', 'strictly_past_transaction_evidence', 'asof_graph_edges',
                          'suppression_points', 'queue_membership', 'saved_AP', 'validation_threshold_decisions', 'fixed_capacity_ranking'])
    (report_directory / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.data, args.report), ensure_ascii=False))


if __name__ == '__main__':
    main()
