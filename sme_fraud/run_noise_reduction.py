"""Phase 2: finite validation-only comparison, then frozen rule rescore. No ML."""
import argparse
from collections import Counter, defaultdict
import csv
import gc
import json
from pathlib import Path
import shutil

from .case_queue import review_queue
from .generate import write_csv
from .name_challenge import run_challenge
from .rule_audit import confusion, read_csv, replay_scores, sha
from .rules import load_inputs, score_rules
from .run_rule_repairs import baseline_hits, write_jsonl

NOISE_RULES = ('E3', 'C1', 'A1', 'A2', 'A5', 'B3', 'B5', 'E4')


def sets_from_hits(hits):
    candidates, active, signals = defaultdict(set), defaultdict(set), defaultdict(set)
    for hit in hits:
        for code in [hit['rule_id'], *hit.get('aliases', [])]:
            candidates[code].add(hit['transaction_id'])
            if not hit['suppressed_reason']:
                signals[code].add(hit['transaction_id'])
            if hit['points'] > 0:
                active[code].add(hit['transaction_id'])
    return candidates, active, signals


def choose_validation(data, baseline, output):
    tables, features, _ = load_inputs(data)
    tables['transactions'] = [r for r in tables['transactions'] if r['posted_at'] < '2025-07-01T00:00:00+07:00']
    ids = {r['transaction_id'] for r in tables['transactions']}
    features = [r for r in features if r['transaction_id'] in ids]
    validation = {r['transaction_id'] for r in tables['transactions'] if r['posted_at'] >= '2025-01-01T00:00:00+07:00'}
    config = json.loads((baseline / 'rule_config.json').read_text(encoding='utf-8'))
    candidates = [dict(noise_policy='phase2', amount_baseline='raw', robust_z=3.5),
                  *[dict(noise_policy='phase2', amount_baseline='log_mad', robust_z=z) for z in (2.5, 3.0, 3.5)]]
    for candidate in candidates:
        candidate['spec_policy'] = 'legacy'
        candidate['evidence_policy'] = 'disabled'
    # No test label is retained or scored during this selection stage.
    with (data / 'labels.csv').open(encoding='utf-8-sig', newline='') as stream:
        labels = {r['transaction_id']: r for r in csv.DictReader(stream) if r['transaction_id'] in validation}
    records = []
    for candidate in candidates:
        print(f'Validation candidate: {candidate}', flush=True)
        result = score_rules(tables, config={**config, **candidate}, features=features)
        _, active, signals = sets_from_hits(result['hits'])
        operational = {r['transaction_id'] for r in result['scores'] if r['operational_alert']}
        metric = confusion(validation, operational, labels)
        amount = confusion(validation, signals['A5'], labels)
        record = dict(config={**config, **candidate}, operational_validation=metric, a5_signals=amount,
            a5_hard_negative_signals=sum(bool(labels[i]['hard_negative_type']) for i in signals['A5'] & validation),
            selection_note='A5 lacks specific positive fraud truth; minimize nuisance only among finite candidates that preserve the 3m/1m business control.')
        # Predeclared positive control: 25 observations around 1m, then 3m.
        from .rule_audit_cases import Case
        from datetime import timedelta
        control = Case()
        control.config = candidate
        control.sequence([1_000_000 + (i%5-2)*10_000 for i in range(25)], kind='cash_expense', start=control.at-timedelta(days=30))
        target = control.pay(amount=3_000_000, kind='cash_expense')
        checked = control.score()
        record['positive_control_retained'] = any(h['rule_id'] == 'A5' and h['transaction_id'] == target['transaction_id'] for h in checked['hits'])
        records.append(record)
        del result
        gc.collect()
    valid = [r for r in records if r['positive_control_retained']]
    # Operational TP is reported, not optimized through test labels. Lower
    # thresholds win ties, rather than silently making the detector inert.
    selected = min(valid, key=lambda r: (r['a5_hard_negative_signals'], r['a5_signals']['fp'], r['config']['robust_z']))
    selection = dict(dataset=str(data), selection_partition='validation_only', test_labels_used=False,
        candidates=records, selected_config=selected['config'], frozen_before_test_evaluation=True)
    (output / 'validation_selection.json').write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding='utf-8')
    return selected['config']


def evaluate_dataset(data, baseline, destination, config):
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    fingerprints = {str(data / name): entry['sha256'] for name, entry in manifest['files'].items()}
    fingerprints[str(data / 'manifest.json')] = sha(data / 'manifest.json')
    for filename, expected in fingerprints.items():
        if sha(Path(filename)) != expected:
            raise ValueError(f'Dataset changed: {filename}')
    for name in ('rule_scores.csv', 'rule_hits.jsonl', 'rule_config.json', 'benford_diagnostics.jsonl'):
        fingerprints[str(baseline / name)] = sha(baseline / name)
    tables, features, meta = load_inputs(data)
    result = score_rules(tables, config=config, features=features)
    print(f'{data.name}: phase 2 scored {len(result["scores"]):,}', flush=True)
    candidates, active, signals = sets_from_hits(result['hits'])
    old = baseline_hits(baseline / 'rule_hits.jsonl')
    for code in ('B1', 'B2', 'B4', 'B7', 'C2', 'E1', 'P1', 'T2'):
        if old[code] != active[code]:
            raise ValueError(f'Protected control changed: {code}')
    points = defaultdict(dict)
    tx = {r['transaction_id']: r for r in tables['transactions']}
    for hit in result['hits']:
        if hit['suppressed_reason'] and (hit['points'] or hit['hard_trigger']):
            raise ValueError('Suppressed evidence contributes')
        if any(tx[i]['posted_at'] >= hit['detected_at'] for i in hit['related_transaction_ids']):
            raise ValueError('Future/simultaneous payment evidence')
        if hit['points']:
            points[hit['transaction_id']][hit['rule_id']] = hit['points']
    replay = replay_scores(tables['transactions'], points, result['config'])
    if any(any(replay[r['transaction_id']][k] != r[k] for k in ('base_score', 'recurrence_points', 'rule_score')) for r in result['scores']):
        raise ValueError('Replay mismatch')
    # Selection was already persisted. Only now evaluate test labels.
    labels = {r['transaction_id']: r for r in read_csv(data / 'labels.csv')}
    partitions = defaultdict(set)
    for row in read_csv(data / 'splits.csv'):
        partitions[row['split']].add(row['transaction_id'])
    previous_scores = read_csv(baseline / 'rule_scores.csv')
    old_alerts = {r['transaction_id'] for r in previous_scores if int(r['operational_alert'])}
    alerts = {r['transaction_id'] for r in result['scores'] if r['operational_alert']}
    metrics, lost = [], []
    for period in ('train', 'validation', 'test'):
        ids = partitions[period]
        for code in [*NOISE_RULES, 'operational']:
            if code == 'operational':
                current, earlier = alerts, old_alerts
                raw = current
            else:
                current, earlier = active[code], old[code]
                raw = signals[code]
            metrics.append(dict(period=period, rule_id=code, before=confusion(ids, earlier, labels),
                contributing_after=confusion(ids, current, labels), unsuppressed_signal_after=confusion(ids, raw, labels),
                candidate_rows_after=len(candidates[code] & ids) if code != 'operational' else len(current & ids),
                note='Point contribution is distinct from predicate/diagnostic accuracy; master/context zero points do not establish correctness.'))
        for tid in sorted((old_alerts-alerts) & ids):
            if int(labels[tid]['is_fraud']):
                prior = next(r for r in previous_scores if r['transaction_id'] == tid)
                lost.append(dict(period=period, transaction_id=tid, fraud_type=labels[tid]['fraud_type'], variant=labels[tid]['variant'],
                    old_rule_ids=prior['rule_ids'], after_signal_ids='|'.join(c for c in NOISE_RULES if tid in signals[c])))
    clusters = {}
    for hit in result['hits']:
        if hit.get('scoring_role') == 'master_quality':
            cluster = clusters.setdefault(hit['evidence_id'], dict(evidence_id=hit['evidence_id'], company_id=hit['company_id'],
                rule_id=hit['rule_id'], aliases=hit.get('aliases', []), evidence=hit['evidence'], first_seen_at=hit['detected_at'],
                last_seen_at=hit['detected_at'], transaction_count=0))
            cluster['last_seen_at'] = hit['detected_at']
            cluster['transaction_count'] += 1
    # Inspect the exact pre-existing B3 false positive cohort; labels are only
    # used to report this cohort, never to create a fulfilment exemption.
    b3_review = []
    for hit in result['hits']:
        tid = hit['transaction_id']
        if hit['rule_id'] == 'B3' and tid in old['B3'] and tid in partitions['test'] and labels[tid]['hard_negative_type'] == 'new_legitimate_vendor':
            b3_review.append(dict(transaction_id=tid, company_id=tx[tid]['company_id'], amount_vnd=tx[tid]['amount_vnd'],
                support_doc_count=tx[tid]['support_doc_count'], goods_receipt_verified=tx[tid]['goods_receipt_verified'],
                verified_document_types='|'.join(r['document_type'] for r in hit['evidence']['verified_documents']),
                evidence_status=hit['evidence']['evidence_status'], contributing_points=hit['points']))
    cases, events = review_queue(result, tables)
    if {tid for c in cases for tid in json.loads(c['transaction_ids'])} != alerts:
        raise ValueError('Queue membership differs')
    destination.mkdir(parents=True)
    write_csv(destination / 'rule_scores.csv', [{k: v for k, v in r.items() if k != 'known_risky_prior_ids'} for r in result['scores']])
    write_jsonl(destination / 'rule_hits.jsonl', result['hits'])
    write_csv(destination / 'case_queue.csv', cases)
    write_csv(destination / 'case_events.csv', events)
    write_jsonl(destination / 'master_findings.jsonl', list(clusters.values()))
    write_csv(destination / 'master_name_quality.csv', result['master_name_quality'])
    write_csv(destination / 'b3_review.csv', b3_review, ['transaction_id', 'company_id', 'amount_vnd', 'support_doc_count', 'goods_receipt_verified', 'verified_document_types', 'evidence_status', 'contributing_points'])
    write_csv(destination / 'lost_true_detections.csv', lost, ['period', 'transaction_id', 'fraud_type', 'variant', 'old_rule_ids', 'after_signal_ids'])
    (destination / 'rule_config.json').write_text(json.dumps(result['config'], indent=2), encoding='utf-8')
    (destination / 'rule_coverage.json').write_text(json.dumps(result['coverage'], ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(baseline / 'benford_diagnostics.jsonl', destination / 'benford_diagnostics.jsonl')
    for filename, expected in fingerprints.items():
        if sha(Path(filename)) != expected:
            raise ValueError(f'Input changed during phase2: {filename}')
    record = dict(dataset=str(data), requested_fraud_rate=meta['requested_fraud_rate'], metrics=metrics,
        source_hashes=fingerprints, protected_controls_unchanged=True, score_replay='passed', model_usage='none',
        input_evidence_rows={name: len(tables.get(name, [])) for name in
            ('procurement_links', 'transaction_documents', 'operating_schedules', 'recurring_payments')},
        master_clusters=len(clusters), uninformative_master_names=len(result['master_name_quality']),
        lost_true_detections=lost, b3_test_review_rows=len(b3_review), review_cases=len(cases))
    (destination / 'comparison.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--baseline-root', type=Path, default=Path('reports/rule_repairs/phase1'))
    parser.add_argument('--output', type=Path, default=Path('reports/rule_repairs/phase2'))
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f'Refusing to overwrite: {args.output}')
    args.output.mkdir(parents=True, exist_ok=True)
    code = Path(__file__).resolve().parent
    fingerprints = {str(code / name): sha(code / name) for name in ('rules.py', 'noise_policy.py', 'temporal_evidence.py',
        'features.py', 'case_queue.py', 'name_challenge.py', 'run_noise_reduction.py')}
    selected = choose_validation(args.data_root / 'sme_fraud_003', args.baseline_root / 'sme_fraud_003', args.output)
    results = []
    for tag in ('001', '003', '005'):
        results.append(evaluate_dataset(args.data_root / f'sme_fraud_{tag}', args.baseline_root / f'sme_fraud_{tag}',
                                        args.output / f'sme_fraud_{tag}', selected))
        gc.collect()
    challenge = run_challenge()
    write_csv(args.output / 'name_challenge.csv', challenge)
    for filename, original in fingerprints.items():
        if sha(Path(filename)) != original:
            raise ValueError('Detector changed during phase2')
    (args.output / 'verification.json').write_text(json.dumps(dict(source_hashes=fingerprints, results=results,
        validation_selection_sha256=sha(args.output / 'validation_selection.json'), name_pairs=len(challenge), model_usage='none'),
        ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Xử lý nguồn nhiễu và cộng điểm — đợt 2', '',
        'Chọn trong bốn cấu hình A5 trên validation 0,3%, lưu cấu hình trước khi đánh giá test; chấm lại 300.000 quan sát, không ML.',
        'E3/B5/E4 là kiểm tra master; C1/A5/B3 là ngữ cảnh cần bằng chứng giao dịch đủ ngưỡng để góp điểm. Hit chẩn đoán vẫn được lưu, không được coi 0 điểm là predicate đúng 100%.', '',
        '## Hàng đợi test tại ngưỡng 7', '',
        '| Tỷ lệ | TP trước → sau | FP trước → sau | Precision trước → sau |', '| --- | ---: | ---: | ---: |']
    for record in results:
        row = next(r for r in record['metrics'] if r['period'] == 'test' and r['rule_id'] == 'operational')
        old, new = row['before'], row['contributing_after']
        lines.append(f"| {record['requested_fraud_rate']:.1%} | {old['tp']} → {new['tp']} | {old['fp']} → {new['fp']} | {old['fraud_precision']:.2%} → {new['fraud_precision']:.2%} |")
    lines += ['', '## Rule — test 0,3%', '',
        '| Rule | FP góp điểm trước → sau | Ứng viên sau | Tín hiệu chưa loại |', '| --- | ---: | ---: | ---: |']
    for row in results[1]['metrics']:
        if row['period'] == 'test' and row['rule_id'] != 'operational':
            lines.append(f"| {row['rule_id']} | {row['before']['fp']} → {row['contributing_after']['fp']} | {row['candidate_rows_after']} | {row['unsuppressed_signal_after']['alerts']} |")
    lines += ['', '## Phát hiện đúng bị ảnh hưởng', '',
        'Mọi TP mất khỏi hàng đợi có ID/family/variant/luật cũ trong lost_true_detections.csv từng bộ. Một số tín hiệu yếu còn trong rule_hits nhưng không đủ bằng chứng độc lập để mở hồ sơ.',
        'Đây là đánh đổi được báo cáo, chưa đủ để nghiệm thu trên SME thật. Không thay threshold theo test hoặc sửa master gốc để làm đẹp precision.', '',
        '## Master và hồ sơ chưa đủ nguồn', '',
        f"Bộ 0,3%: {results[1]['uninformative_master_names']} tên giả lập không đủ dùng cho so khớp; {results[1]['master_clusters']} cụm master riêng. B5/E4 cùng evidence, không nhân đôi bằng chứng.",
        f"Đã rà {results[1]['b3_test_review_rows']} hồ sơ B3 trước đó mang nhãn new_legitimate_vendor; chi tiết ở sme_fraud_003/b3_review.csv. Thiếu nguồn loại chứng từ được ghi needs_typed_fulfilment_evidence, không tự xem là đã xác minh hợp lệ.",
        '540 cặp tên hư cấu độc lập gồm biến thể cố ý, tên gần giống hợp lệ và tên độc lập cùng loại hình pháp nhân: name_challenge.csv. Nhãn gần giống/same_entity khác nhãn gian lận; fuzzy match không tự gộp hai pháp nhân.', '',
        '## Tái lập và nguồn mới', '',
        f"Cấu hình đã chọn: amount_baseline={selected['amount_baseline']}, robust_z={selected['robust_z']}.",
        'Validation selection có số liệu từng cấu hình và positive control. comparison.json chứa ba kỳ và TP/FP góp điểm so với tín hiệu chưa loại.',
        'Thiết kế, nguồn lịch ca/chứng từ và kiểm thử: [báo cáo triển khai](../../rule_repairs_phase2.md).', '',
        '```powershell', 'python -m sme_fraud.run_noise_reduction --output reports/rule_repairs/phase2_new',
        'python -m sme_fraud.review_server --reports-root reports/rule_repairs/phase2 --database .runtime/review/phase2.sqlite3 --port 8767', '```', '',
        'UI cũ/snapshot trước và phản hồi người dùng được giữ nguyên; lệnh trên đọc hàng đợi mới.']
    (args.output / 'summary_vi.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), selected=selected, rows=300000, name_pairs=len(challenge))))


if __name__ == '__main__':
    main()
