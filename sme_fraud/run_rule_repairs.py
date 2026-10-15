"""Rescore rules only and compare a repair against frozen baseline snapshots."""
import argparse
from collections import Counter, defaultdict
import gc
import json
from pathlib import Path
import shutil

from .case_queue import review_queue
from .generate import write_csv
from .rule_audit import confusion, read_csv, replay_scores, sha
from .rule_audit_cases import run_cases
from .rules import load_inputs, score_rules

CHANGED_RULES = {'A2', 'B7', 'E1'}


def write_jsonl(path, rows):
    with path.open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')


def baseline_hits(path):
    active = defaultdict(set)
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['points'] > 0:
                active[row['rule_id']].add(row['transaction_id'])
    return active


def run(dataset, baseline, output):
    manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    fingerprints = {str(dataset / name): entry['sha256'] for name, entry in manifest['files'].items()}
    fingerprints[str(dataset / 'manifest.json')] = sha(dataset / 'manifest.json')
    for filename, expected in fingerprints.items():
        if sha(Path(filename)) != expected:
            raise ValueError(f'Dataset differs from manifest: {filename}')
    for name in ('rule_scores.csv', 'rule_hits.jsonl', 'rule_config.json', 'benford_diagnostics.jsonl'):
        fingerprints[str(baseline / name)] = sha(baseline / name)
    tables, features, meta = load_inputs(dataset)
    config = json.loads((baseline / 'rule_config.json').read_text(encoding='utf-8'))
    config['noise_policy'] = 'legacy'
    config['spec_policy'] = 'legacy'
    config['evidence_policy'] = 'disabled'
    result = score_rules(tables, config=config, features=features)
    print(f'{dataset.name}: freshly scored {len(result["scores"]):,} rows; no ML', flush=True)
    active, points = defaultdict(set), defaultdict(dict)
    transactions = {r['transaction_id']: r for r in tables['transactions']}
    for hit in result['hits']:
        if hit['suppressed_reason'] and (hit['points'] or hit['hard_trigger']):
            raise ValueError('Suppression contributes to a hard trigger')
        if any(transactions[i]['posted_at'] >= hit['detected_at'] for i in hit['related_transaction_ids']):
            raise ValueError('Non-causal evidence')
        if any(edge['observed_at'] > hit['detected_at'] for edge in hit['graph_path']):
            raise ValueError('Future graph evidence')
        if hit['points'] > 0:
            active[hit['rule_id']].add(hit['transaction_id'])
            points[hit['transaction_id']][hit['rule_id']] = hit['points']
    replayed = replay_scores(tables['transactions'], points, result['config'])
    for row in result['scores']:
        replay = replayed[row['transaction_id']]
        if any(row[k] != replay[k] for k in ('base_score', 'recurrence_points', 'rule_score')):
            raise ValueError('Score replay mismatch')
    previous = baseline_hits(baseline / 'rule_hits.jsonl')
    for code in set(previous) | set(active):
        if code not in CHANGED_RULES and previous[code] != active[code]:
            raise ValueError(f'Unexpected unrelated rule incidence change: {code}')
    old_scores = read_csv(baseline / 'rule_scores.csv')
    if {r['transaction_id'] for r in old_scores} != set(transactions):
        raise ValueError('Baseline IDs differ')
    # Labels and partitions are used only after the detector is finished.
    labels = {r['transaction_id']: r for r in read_csv(dataset / 'labels.csv')}
    partitions = defaultdict(set)
    for row in read_csv(dataset / 'splits.csv'):
        partitions[row['split']].add(row['transaction_id'])
    before = {r['transaction_id'] for r in old_scores if int(r['operational_alert'])}
    after = {r['transaction_id'] for r in result['scores'] if r['operational_alert']}
    measurements, changes = [], []
    for period in ('train', 'validation', 'test'):
        ids = partitions[period]
        for code in ('A2', 'B7', 'E1', 'operational'):
            old, new = (before, after) if code == 'operational' else (previous[code], active[code])
            measurements.append(dict(period=period, rule_id=code, before=confusion(ids, old, labels),
                after=confusion(ids, new, labels), removed_hits=len((old-new) & ids), added_hits=len((new-old) & ids),
                hard_negative_before=dict(Counter(labels[i]['hard_negative_type'] for i in old & ids
                                                  if labels[i]['hard_negative_type'])),
                hard_negative_after=dict(Counter(labels[i]['hard_negative_type'] for i in new & ids
                                                 if labels[i]['hard_negative_type']))))
            for direction, members in [('removed', old-new), ('added', new-old)]:
                for tid in sorted(members & ids):
                    changes.append(dict(period=period, rule_id=code, direction=direction, transaction_id=tid,
                        is_fraud=labels[tid]['is_fraud'], hard_negative_type=labels[tid]['hard_negative_type'],
                        txn_type=transactions[tid]['txn_type'], company_id=transactions[tid]['company_id']))
    cases, events = review_queue(result, tables)
    members = [tid for case in cases for tid in json.loads(case['transaction_ids'])]
    if len(members) != len(set(members)) or set(members) != after:
        raise ValueError('Review queue does not reconcile with operational alerts')
    output.mkdir(parents=True)
    write_csv(output / 'rule_scores.csv', [{k: v for k, v in row.items() if k != 'known_risky_prior_ids'} for row in result['scores']])
    write_jsonl(output / 'rule_hits.jsonl', result['hits'])
    write_csv(output / 'case_queue.csv', cases)
    write_csv(output / 'case_events.csv', events)
    write_csv(output / 'changed_hits.csv', changes, ['period', 'rule_id', 'direction', 'transaction_id', 'is_fraud', 'hard_negative_type', 'txn_type', 'company_id'])
    counts = Counter(h['rule_id'] for h in result['hits'] if h['points'] > 0)
    suppressed = Counter(h['rule_id'] for h in result['hits'] if h['suppressed_reason'])
    for record in result['coverage']:
        if not record['rule_id'].startswith('D'):
            record.update(hits=counts[record['rule_id']], suppressed_hits=suppressed[record['rule_id']])
    (output / 'rule_config.json').write_text(json.dumps(result['config'], indent=2), encoding='utf-8')
    (output / 'rule_coverage.json').write_text(json.dumps(result['coverage'], ensure_ascii=False, indent=2), encoding='utf-8')
    # D inputs/implementation were not changed. Reuse the frozen diagnostics and
    # declare that explicitly rather than pretending to rerun their predicates.
    shutil.copyfile(baseline / 'benford_diagnostics.jsonl', output / 'benford_diagnostics.jsonl')
    for filename, expected in fingerprints.items():
        if sha(Path(filename)) != expected:
            raise ValueError(f'Source changed during rescore: {filename}')
    record = dict(dataset=str(dataset), requested_fraud_rate=meta['requested_fraud_rate'], measurements=measurements,
        changed_rules=sorted(CHANGED_RULES), source_hashes=fingerprints, model_usage='none',
        freshly_scored_rows=len(result['scores']), operational_cases=len(cases), unchanged_other_rule_incidence=True,
        score_replay='passed', source_unchanged=True, benford_diagnostics='reused_from_unchanged_baseline',
        optional_source_rows={name: len(tables.get(name, [])) for name in ('payroll_entitlements', 'supplier_payment_agreements')})
    (output / 'comparison.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--baseline-root', type=Path, default=Path('reports/rules'))
    parser.add_argument('--output', type=Path, default=Path('reports/rule_repairs/phase1'))
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f'Refusing to overwrite repair outputs: {args.output}')
    root = Path(__file__).resolve().parent
    source_hashes = {str(root / name): sha(root / name) for name in
        ('rules.py', 'features.py', 'temporal_evidence.py', 'case_queue.py', 'run_rule_repairs.py', 'rule_audit_cases.py')}
    measurements = []
    for tag in ('001', '003', '005'):
        print(f'Rescoring repaired rules: {tag}', flush=True)
        measurements.append(run(args.data_root / f'sme_fraud_{tag}', args.baseline_root / f'sme_fraud_{tag}',
                                args.output / f'sme_fraud_{tag}'))
        gc.collect()
    fixtures = run_cases()
    failures = [r['case_id'] for r in fixtures if r['rule_id'] in CHANGED_RULES and not r['passed']]
    if failures:
        raise ValueError(f'Repair fixtures still fail: {failures}')
    if any(sha(Path(filename)) != expected for filename, expected in source_hashes.items()):
        raise ValueError('Source changed during repair rescore')
    (args.output / 'verification.json').write_text(json.dumps(dict(source_hashes=source_hashes, scenarios=measurements,
        controlled_cases=fixtures, repaired_fixture_gaps=failures, remaining_fixture_gaps=[r['case_id'] for r in fixtures if not r['passed']],
        model_usage='none'), ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['rule_id', 'case_id', 'description', 'expected_active', 'actual_active', 'passed', 'observed_points', 'scope']
    write_csv(args.output / 'controlled_cases.csv', [{k: row[k] for k in fields} for row in fixtures], fields)
    lines = ['# Sửa rule đợt 1 — B7, E1, A2', '',
        'Đã chấm lại 300.000 giao dịch bằng engine mới trên dữ liệu gốc và cấu hình/ngưỡng cũ. Không train/chấm ML.',
        'Các rule giao dịch ngoài A2/B7/E1 giữ nguyên tập hit hoạt động. Benford được dùng lại từ baseline vì đầu vào và luật D không thay đổi.', '',
        f'Đối chứng: {sum(r["passed"] for r in fixtures)}/{len(fixtures)} khớp; toàn bộ đối chứng của ba rule đã sửa khớp. ',
        'E1 nghỉ hưởng lương được bổ sung nguồn quyền chi đã duyệt trong fixture; dữ liệu gốc không có nguồn này và không được tự điền ngoại lệ.', '',
        '## Hàng đợi test tại ngưỡng 7', '',
        '| Tỷ lệ | Cảnh báo trước → sau | TP trước → sau | FP trước → sau | Precision trước → sau |',
        '| --- | ---: | ---: | ---: | ---: |']
    for record in measurements:
        metric = next(r for r in record['measurements'] if r['period'] == 'test' and r['rule_id'] == 'operational')
        old, new = metric['before'], metric['after']
        lines.append(f"| {record['requested_fraud_rate']:.1%} | {old['alerts']} → {new['alerts']} | {old['tp']} → {new['tp']} | {old['fp']} → {new['fp']} | {old['fraud_precision']:.2%} → {new['fraud_precision']:.2%} |")
    lines += ['', '## Từng rule — test 0,3%', '',
        '| Rule | Hit trước → sau | TP trước → sau | FP trước → sau | Hit bỏ / thêm |', '| --- | ---: | ---: | ---: | ---: |']
    for metric in measurements[1]['measurements']:
        if metric['period'] == 'test' and metric['rule_id'] != 'operational':
            old, new = metric['before'], metric['after']
            lines.append(f"| {metric['rule_id']} | {old['alerts']} → {new['alerts']} | {old['tp']} → {new['tp']} | {old['fp']} → {new['fp']} | {metric['removed_hits']} / {metric['added_hits']} |")
    lines += ['', 'TP/FP theo nhãn ý đồ gian lận tổng hợp; chưa phải nhãn độc lập cho mọi vi phạm rule hoặc hiệu quả trên SME thật.',
        'E1/B7 có thể không thay đổi số liệu nền vì dữ liệu gốc không cài những trường hợp đã tái hiện; fixture và kiểm thử thời gian là bằng chứng sửa logic.',
        'Số liệu train/validation/test và hard negatives ở comparison.json từng bộ; changed_hits.csv liệt kê mọi hit thay đổi.', '',
        '## Đối chứng còn lệch, ngoài phạm vi đợt 1', '',
        *[f'- {r["case_id"]}: {r["description"]}' for r in fixtures if not r['passed']], '',
        '## Nguồn và cách chạy', '',
        'Chi tiết logic, nguồn HR/hợp đồng và kiểm thử ở [báo cáo triển khai](../../rule_repairs_phase1.md).',
        'Baseline [Rule Audit](../../rule_audit/summary_vi.md) được giữ nguyên để đối chiếu. Các báo cáo cũ thể hiện phiên bản trước khi sửa.', '',
        '```powershell', 'python -m sme_fraud.run_rule_repairs --output reports/rule_repairs/phase1_new', '```', '',
        'CLI không ghi đè dữ liệu/báo cáo đã có và không thay đổi features.csv hoặc model cũ.', '',
        'Các snapshot mới có rule_scores, rule_hits, case_queue và case_events để dùng trong UI. ',
        '```powershell', 'python -m sme_fraud.review_server --reports-root reports/rule_repairs/phase1 --database .runtime/review/phase1.sqlite3 --port 8766', '```', '',
        'Lệnh này mở hàng đợi mới trên cổng riêng; phản hồi của snapshot cũ giữ tại nguồn cũ.', '']
    (args.output / 'summary_vi.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), fresh_rule_rows=300000,
                         controlled_matches=sum(r['passed'] for r in fixtures), controlled_cases=len(fixtures), model_usage='none')))


if __name__ == '__main__':
    main()
