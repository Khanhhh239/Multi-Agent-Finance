"""Freeze phase 3 business policy and rescore without ML or test tuning."""
import argparse
from collections import Counter, defaultdict
import gc
import json
from pathlib import Path
import shutil

from .case_queue import review_queue, operational_members
from .generate import write_csv
from .rule_audit import confusion, read_csv, replay_scores, sha
from .rules import load_inputs, score_rules, RULE_NAMES, OPTIONAL_INPUT_TABLES
from .run_noise_reduction import sets_from_hits
from .run_rule_repairs import write_jsonl

CHANGED = ('A3', 'A4', 'A5', 'B1', 'B3', 'F1')
PROTECTED = ('B2', 'B4', 'B7', 'C2', 'E1', 'P1', 'T2')


def run(data, baseline, output, config):
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    fingerprints = {str(data / n): r['sha256'] for n, r in manifest['files'].items()}
    fingerprints[str(data / 'manifest.json')] = sha(data / 'manifest.json')
    for name in ('rule_scores.csv', 'rule_hits.jsonl', 'rule_config.json', 'benford_diagnostics.jsonl'):
        fingerprints[str(baseline / name)] = sha(baseline / name)
    for filename, expected in fingerprints.items():
        if sha(Path(filename)) != expected:
            raise ValueError(f'Input changed: {filename}')
    tables, features, meta = load_inputs(data)
    result = score_rules(tables, features=features, config=config)
    print(f'{data.name}: scored {len(result["scores"]):,}; no ML', flush=True)
    candidates, active, signals = sets_from_hits(result['hits'])
    with (baseline / 'rule_hits.jsonl').open(encoding='utf-8') as stream:
        old_candidates, old_active, _ = sets_from_hits(json.loads(line) for line in stream)
    # New anchors can enable context C1/A5/B3. Their predicates must stay fixed.
    for code in PROTECTED:
        if active[code] != old_active[code]:
            raise ValueError(f'Unrelated control changed: {code}')
    for code in ('A1', 'A2', 'A6', 'B5', 'B6', 'C1', 'C3', 'E3', 'E4', 'T1', 'T2'):
        if candidates[code] != old_candidates[code]:
            raise ValueError(f'Unrelated candidate changed: {code}')
    tx = {r['transaction_id']: r for r in tables['transactions']}
    points = defaultdict(dict)
    for hit in result['hits']:
        if hit['suppressed_reason'] and (hit['points'] or hit['hard_trigger']):
            raise ValueError('Suppressed evidence contributes')
        if any(tx[i]['posted_at'] >= hit['detected_at'] for i in hit['related_transaction_ids']):
            raise ValueError('Noncausal transaction evidence')
        if any(e['observed_at'] > hit['detected_at'] for e in hit['graph_path']):
            raise ValueError('Future graph evidence')
        if hit['rule_id'] == 'F1' and hit['points'] and hit['evidence']['evidence_status'] != 'confirmed_sources':
            raise ValueError('F1 proxy contributes')
        if hit['points']:
            points[hit['transaction_id']][hit['rule_id']] = hit['points']
    replay = replay_scores(tables['transactions'], points, result['config'])
    if any(any(replay[r['transaction_id']][k] != r[k] for k in ('base_score', 'recurrence_points', 'rule_score')) for r in result['scores']):
        raise ValueError('Score replay mismatch')
    previous = {r['transaction_id']: r for r in read_csv(baseline / 'rule_scores.csv')}
    if set(previous) != set(tx):
        raise ValueError('Baseline IDs differ')
    before = {i for i, r in previous.items() if int(r['operational_alert'])}
    after = {r['transaction_id'] for r in result['scores'] if r['operational_alert']}
    # Truth is read only after scoring; policy already frozen on disk by main().
    labels = {r['transaction_id']: r for r in read_csv(data / 'labels.csv')}
    partitions = defaultdict(set)
    for r in read_csv(data / 'splits.csv'):
        partitions[r['split']].add(r['transaction_id'])
    metrics, changes = [], []
    for period in ('train', 'validation', 'test'):
        ids = partitions[period]
        for code in [*CHANGED, 'C1', 'operational']:
            old, new = (before, after) if code == 'operational' else (old_active[code], active[code])
            metrics.append(dict(period=period, rule_id=code, before=confusion(ids, old, labels), after=confusion(ids, new, labels),
                candidates_after=len(candidates[code] & ids), unsuppressed_after=len(signals[code] & ids),
                hard_negative_before=dict(Counter(labels[i]['hard_negative_type'] for i in old & ids if labels[i]['hard_negative_type'])),
                hard_negative_after=dict(Counter(labels[i]['hard_negative_type'] for i in new & ids if labels[i]['hard_negative_type']))))
            for direction, members in [('added', new-old), ('removed', old-new)]:
                for tid in sorted(members & ids):
                    changes.append(dict(period=period, rule_id=code, direction=direction, transaction_id=tid,
                        is_fraud=labels[tid]['is_fraud'], fraud_type=labels[tid]['fraud_type'], variant=labels[tid]['variant'],
                        hard_negative_type=labels[tid]['hard_negative_type'], old_rule_ids=previous[tid]['rule_ids']))
    cases, events = review_queue(result, tables)
    members = [tid for c in cases for tid in json.loads(c['transaction_ids'])]
    if len(members) != len(set(members)) or set(members) != operational_members(result):
        raise ValueError('Queue membership differs')
    output.mkdir(parents=True)
    write_csv(output / 'rule_scores.csv', [{k: v for k, v in r.items() if k != 'known_risky_prior_ids'} for r in result['scores']])
    write_jsonl(output / 'rule_hits.jsonl', result['hits'])
    write_jsonl(output / 'batch_events.jsonl', result['batch_events'])
    write_csv(output / 'case_queue.csv', cases)
    write_csv(output / 'case_events.csv', events)
    write_jsonl(output / 'master_identity_findings.jsonl', result['master_identity_findings'])
    write_csv(output / 'master_name_quality.csv', result['master_name_quality'])
    fields = ['period', 'rule_id', 'direction', 'transaction_id', 'is_fraud', 'fraud_type', 'variant', 'hard_negative_type', 'old_rule_ids']
    write_csv(output / 'changed_hits.csv', changes, fields)
    write_csv(output / 'lost_true_detections.csv', [r for r in changes if r['rule_id'] == 'operational' and r['direction'] == 'removed' and int(r['is_fraud'])], fields)
    counts = Counter(h['rule_id'] for h in result['hits'] if h['points'])
    for record in result['coverage']:
        record['hits'] = counts[record['rule_id']]
    for name, value in [('rule_config', result['config']), ('rule_coverage', result['coverage'])]:
        (output / f'{name}.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(baseline / 'benford_diagnostics.jsonl', output / 'benford_diagnostics.jsonl')
    for filename, expected in fingerprints.items():
        if sha(Path(filename)) != expected:
            raise ValueError(f'Source changed during rescore: {filename}')
    record = dict(dataset=str(data), requested_fraud_rate=meta['requested_fraud_rate'], metrics=metrics,
        source_hashes=fingerprints, source_unchanged=True, score_replay='passed', protected_controls=list(PROTECTED),
        protected_controls_unchanged=True, model_usage='none', rows=len(tx), review_cases=len(cases),
        optional_source_rows={name: len(tables.get(name, [])) for name in OPTIONAL_INPUT_TABLES},
        f1_status_counts=dict(Counter(h['evidence']['evidence_status'] for h in result['hits'] if h['rule_id'] == 'F1')),
        master_identity_findings=len(result['master_identity_findings']),
        benford_diagnostics='reused_unchanged_phase2')
    (output / 'comparison.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--baseline-root', type=Path, default=Path('reports/rule_repairs/phase2'))
    parser.add_argument('--output', type=Path, default=Path('reports/rule_repairs/phase3'))
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f'Refusing to overwrite: {args.output}')
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads((args.baseline_root / 'sme_fraud_003/rule_config.json').read_text(encoding='utf-8'))
    config.setdefault('cash_payment_policy', 'disabled')
    config.update(spec_policy='phase3', near_period='calendar_month', amount_tail='upper', evidence_policy='disabled')
    frozen = dict(config=config, test_tuning=False, rationale='Business definitions; A5 baseline and operational threshold unchanged from validation-selected phase2.')
    (args.output / 'policy_selection.json').write_text(json.dumps(frozen, indent=2), encoding='utf-8')
    code = Path(__file__).resolve().parent
    fingerprints = {str(code / name): sha(code / name) for name in ('rules.py', 'spec_policy.py', 'noise_policy.py',
        'temporal_evidence.py', 'features.py', 'case_queue.py', 'run_spec_alignment.py', 'rule_audit_policy.py')}
    results = []
    for tag in ('001', '003', '005'):
        results.append(run(args.data_root / f'sme_fraud_{tag}', args.baseline_root / f'sme_fraud_{tag}', args.output / f'sme_fraud_{tag}', config))
        gc.collect()
    for filename, expected in fingerprints.items():
        if sha(Path(filename)) != expected:
            raise ValueError(f'Detector changed during rescore: {filename}')
    (args.output / 'verification.json').write_text(json.dumps(dict(source_hashes=fingerprints, results=results,
        policy_sha256=sha(args.output / 'policy_selection.json'), model_usage='none'), ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Thống nhất mô tả và mã rule — đợt 3', '',
        'Chấm mới 300.000 dòng; giữ dữ liệu/nhãn, baseline A5 và ngưỡng 7 của đợt 2. Chính sách được ghi trước khi chấm test, không ML hoặc tối ưu theo test.', '',
        '| Tỷ lệ mô phỏng | TP test trước → sau | FP test trước → sau | Precision trước → sau |', '| --- | ---: | ---: | ---: |']
    for record in results:
        metric = next(r for r in record['metrics'] if r['period'] == 'test' and r['rule_id'] == 'operational')
        old, new = metric['before'], metric['after']
        lines.append(f"| {record['requested_fraud_rate']:.1%} | {old['tp']} → {new['tp']} | {old['fp']} → {new['fp']} | {old['fraud_precision']:.2%} → {new['fraud_precision']:.2%} |")
    lines += ['', '## Rule — test 0,3%', '', '| Rule | TP góp điểm trước → sau | FP góp điểm trước → sau | Ứng viên sau |', '| --- | ---: | ---: | ---: |']
    for r in results[1]['metrics']:
        if r['period'] == 'test' and r['rule_id'] != 'operational':
            lines.append(f"| {r['rule_id']} | {r['before']['tp']} → {r['after']['tp']} | {r['before']['fp']} → {r['after']['fp']} | {r['candidates_after']} |")
    lines += ['', 'B1 master là chẩn đoán riêng (master_identity_findings.jsonl); F1 proxy không góp điểm. Ứng viên/chẩn đoán không đồng nghĩa gian lận hoặc predicate đã chính xác.',
        'Nguồn mới còn trống trong dữ liệu gốc; không tự điền CCCD/mã ngân hàng/quyền lương/lịch khóa sổ. B3 là lần đầu trong lịch sử quan sát có sẵn, chưa chứng minh là lần đầu suốt đời NCC.',
        'changed_hits.csv và lost_true_detections.csv lưu thay đổi theo ID, family, variant và hard negative ở cả ba kỳ. comparison.json chứa replay, nguồn/hash và các kiểm soát giữ nguyên.', '',
        '[Chính sách, schema nguồn và đối chứng](../../rule_repairs_phase3.md). Các kết quả là một seed mô phỏng; bước tiếp theo cần nguồn nghiệp vụ và tập nghiệm thu mới có rà soát độc lập.']
    (args.output / 'summary_vi.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), rows=sum(r['rows'] for r in results), model_usage='none')), flush=True)


if __name__ == '__main__':
    main()
