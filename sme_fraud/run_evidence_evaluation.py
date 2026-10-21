"""Phase 4 source controls, independent window truth and fresh held-out SME seeds."""
import argparse
from collections import Counter, defaultdict
import gc
import json
from pathlib import Path
import sys

packages = Path(__file__).resolve().parents[1]/'.runtime/site-packages'
if packages.exists():
    sys.path.insert(0, str(packages))

from .accounting import enrich_accounting
from .aggregate_challenge import PATTERNS, window_case
from .benford import monthly_diagnostics
from .case_queue import review_queue, operational_members
from .evidence_cases import SCENARIOS, prepare, decision
from .evidence_evaluation import boolean_metrics, block_precision, budget_review
from .review_capacity import workload_scenarios
from .features import build_features
from .generate import generate, write_csv
from .rule_audit import confusion, read_csv, replay_scores, sha
from .rules import RULE_NAMES, INPUT_TABLES, OPTIONAL_INPUT_TABLES, load_inputs, score_rules
from .run_noise_reduction import sets_from_hits
from .run_rule_repairs import write_jsonl

CONTROL_SEEDS = dict(train=(1101,1102), validation=(2101,2102), test=(3101,3102,3103))
FRESH_SEEDS = dict(validation=(2026101401,), test=(2026101402,2026101403))


def source_controls(output, config):
    inputs, truths = [], []
    # All ground truth is fixed and persisted before any challenge is scored.
    for partition, seeds in CONTROL_SEEDS.items():
        for seed in seeds:
            for code, variants in SCENARIOS.items():
                for variant in variants:
                    case, row, expected, scope = prepare(code, variant, seed)
                    case.tables['transactions'] = case.rows
                    enrich_accounting(case.tables, seed)
                    identity = f'{partition}_{seed}_{code}_{variant}'
                    inputs.append(dict(case_id=identity, tables={k:case.tables.get(k,[]) for k in (*INPUT_TABLES,*OPTIONAL_INPUT_TABLES,'journal_documents','journal_lines')},
                        target_id=row['transaction_id'], rule_id=code, scope=scope, seed=seed, variant=variant, partition=partition))
                    truths.append(dict(case_id=identity, expected=expected, truth_unit='source_or_pattern_condition_not_financial_fraud'))
    write_jsonl(output/'source_cases.jsonl', inputs)
    write_jsonl(output/'source_truth.jsonl', truths)
    hashes = {str(output/name):sha(output/name) for name in ('source_cases.jsonl','source_truth.jsonl')}
    results, saved_hits, saved_findings = [], [], []
    for case, truth in zip(inputs,truths):
        features = build_features(case['tables'])
        result = score_rules(case['tables'], features=features, config=config)
        row = next(r for r in case['tables']['transactions'] if r['transaction_id']==case['target_id'])
        actual = decision(result, case['rule_id'], row, case['scope'])
        target_hits = [h for h in result['hits'] if h['transaction_id']==case['target_id'] and h['rule_id']==case['rule_id']]
        scored = next(r for r in result['scores'] if r['transaction_id']==case['target_id'])
        results.append(dict(case_id=case['case_id'], partition=case['partition'], seed=case['seed'], rule_id=case['rule_id'], variant=case['variant'],
            scope=case['scope'], expected=truth['expected'], actual=actual, passed=actual==truth['expected'],
            points=sum(h['points'] for h in target_hits), operational_alert=scored['operational_alert'],
            hard_trigger=scored['hard_trigger'], truth_unit=truth['truth_unit']))
        saved_hits.extend(dict(case_id=case['case_id'], **h) for h in result['hits'])
        saved_findings.extend(dict(case_id=case['case_id'], **f) for f in result['evidence_findings'])
    write_csv(output/'controlled_cases.csv', results)
    write_jsonl(output/'controlled_hits.jsonl', saved_hits)
    write_jsonl(output/'controlled_source_findings.jsonl', saved_findings)
    metrics = [dict(rule_id=code, partition=p, **boolean_metrics([r for r in results if r['rule_id']==code and r['partition']==p]))
        for p in CONTROL_SEEDS for code in SCENARIOS]
    write_jsonl(output/'control_metrics.jsonl',metrics)
    if any(not r['passed'] for r in results):
        raise ValueError(f"Source controls failed: {[r['case_id'] for r in results if not r['passed']]}")
    return dict(cases=len(results), passed=len(results), metrics=metrics, source_hashes=hashes)


def aggregate_controls(output):
    folder = output/'aggregate_inputs'
    folder.mkdir()
    prepared, truths, hashes = [], [], {}
    for partition,seeds in CONTROL_SEEDS.items():
        for seed in seeds:
            for pattern in PATTERNS:
                tables, expected = window_case(seed, pattern)
                identity = f'{partition}_{seed}_{pattern}'
                path = folder/f'{identity}.csv'
                write_csv(path,tables['transactions'])
                hashes[str(path)] = sha(path)
                truths.extend(dict(case_id=identity, partition=partition, seed=seed, **r) for r in expected)
                prepared.append((identity,partition,seed,tables,expected))
    write_jsonl(output/'aggregate_truth.jsonl',truths)
    hashes[str(output/'aggregate_truth.jsonl')] = sha(output/'aggregate_truth.jsonl')
    results, diagnostics = [], []
    for identity, partition, seed, tables, expected in prepared:
        scored = monthly_diagnostics(tables, 'phase4')
        diagnostics.extend(dict(case_id=identity, **r) for r in scored)
        for truth in expected:
            target = next((r for r in scored if r['rule_id']==truth['rule_id'] and r['scope']==truth['scope'] and r['cutoff_at']==truth['cutoff_at']), None)
            actual = target.get('signal') if target and target['status']=='evaluated' else None
            results.append(dict(case_id=identity, partition=partition, seed=seed, rule_id=truth['rule_id'], pattern=truth['pattern'],
                expected=truth['expected_signal'], actual=actual, status=target['status'] if target else 'not_evaluable',
                passed=actual==truth['expected_signal'], truth_unit=truth['truth_unit'], window_rows=target['rows'] if target else 0))
    write_csv(output/'aggregate_cases.csv',results)
    write_jsonl(output/'aggregate_diagnostics.jsonl',diagnostics)
    metrics = [dict(rule_id=code, partition=p, **boolean_metrics([r for r in results if r['rule_id']==code and r['partition']==p]))
        for p in CONTROL_SEEDS for code in ('D1','D2','D3','D4','D5','D6')]
    write_jsonl(output/'aggregate_metrics.jsonl',metrics)
    # Statistical power/false alarms are measured, not forced to match every label.
    return dict(cases=len(results), matched=sum(r['passed'] for r in results), metrics=metrics,
        source_hashes=hashes, segmentations=sorted({r.get('segmentation') for r in diagnostics if r.get('segmentation')}))


def baseline_prefixes(output, config):
    checks = []
    for tag in ('001','003','005'):
        data, report = Path('data')/f'sme_fraud_{tag}', Path('reports/rule_repairs/phase3')/f'sme_fraud_{tag}'
        tables, features, _ = load_inputs(data)
        tables['transactions'] = tables['transactions'][:10000]
        ids = {r['transaction_id'] for r in tables['transactions']}
        features = [r for r in features if r['transaction_id'] in ids]
        result = score_rules(tables, features=features, config=config)
        old = {r['transaction_id']:r for r in read_csv(report/'rule_scores.csv') if r['transaction_id'] in ids}
        for r in result['scores']:
            for field in ('base_score','rule_score','recurrence_points','hard_trigger','operational_alert'):
                if r[field] != int(old[r['transaction_id']][field]):
                    raise ValueError(f'Historical prefix changed: {tag} {r["transaction_id"]} {field}')
        checks.append(dict(scenario=tag, rows=len(ids), unchanged=True))
        del tables, features, result
        gc.collect()
    return checks


def fresh_dataset(data, destination, config, seed, partition, rate, rows, reuse=False):
    print(f'Generate {partition} seed={seed} rate={rate}: {rows:,} rows',flush=True)
    if not reuse:
        generate(data, n=rows, rate=rate, seed=seed, companies=3)
    tables, features, manifest = load_inputs(data)
    if manifest['seed']!=seed or manifest['requested_fraud_rate']!=rate or len(tables['transactions'])!=rows:
        raise ValueError('Cached dataset does not match the declared evaluation plan')
    source_hashes = {str(data/name):v['sha256'] for name,v in manifest['files'].items()}
    source_hashes[str(data/'manifest.json')] = sha(data/'manifest.json')
    result = score_rules(tables, features=features, config=config)
    print(f'Scored {partition} seed={seed} rate={rate}',flush=True)
    tx = {r['transaction_id']:r for r in tables['transactions']}
    points = defaultdict(dict)
    for hit in result['hits']:
        if hit['suppressed_reason'] and (hit['points'] or hit['hard_trigger']):
            raise ValueError('Suppressed evidence contributes')
        if any(tx[t]['posted_at'] >= hit['detected_at'] for t in hit['related_transaction_ids']):
            raise ValueError('Noncausal evidence')
        if hit['points']:
            points[hit['transaction_id']][hit['rule_id']] = hit['points']
    replay = replay_scores(tables['transactions'], points, result['config'])
    if any(any(replay[r['transaction_id']][k] != r[k] for k in ('base_score','recurrence_points','rule_score')) for r in result['scores']):
        raise ValueError('Fresh score replay differs')
    # Labels are deliberately read only after the engine finishes.
    labels = {r['transaction_id']:r for r in read_csv(data/'labels.csv')}
    split = {r['transaction_id']:r['split'] for r in read_csv(data/'splits.csv')}
    active = {r['transaction_id'] for r in result['scores'] if r['operational_alert']}
    candidates, contributing, raw = sets_from_hits(result['hits'])
    cases, events = review_queue(result,tables)
    members = [t for c in cases for t in json.loads(c['transaction_ids'])]
    if len(members)!=len(set(members)) or set(members)!=operational_members(result):
        raise ValueError('Queue membership differs')
    diagnostics = monthly_diagnostics(tables, 'phase4')
    destination.mkdir(parents=True)
    write_csv(destination/'rule_scores.csv',[{k:v for k,v in r.items() if k!='known_risky_prior_ids'} for r in result['scores']])
    write_jsonl(destination/'rule_hits.jsonl',result['hits'])
    write_jsonl(destination/'batch_events.jsonl',result['batch_events'])
    write_csv(destination/'case_queue.csv',cases)
    write_csv(destination/'case_events.csv',events)
    write_jsonl(destination/'benford_diagnostics.jsonl',diagnostics)
    write_jsonl(destination/'evidence_findings.jsonl',result['evidence_findings'])
    write_jsonl(destination/'master_identity_findings.jsonl',result['master_identity_findings'])
    (destination/'rule_config.json').write_text(json.dumps(result['config'],indent=2),encoding='utf-8')
    (destination/'rule_coverage.json').write_text(json.dumps(result['coverage'],ensure_ascii=False,indent=2),encoding='utf-8')
    metrics, per_rule = [], []
    coverage = {r['rule_id']:r for r in result['coverage']}
    for period in ('train','validation','test'):
        ids = {t for t in tx if split[t]==period}
        metric = dict(period=period, **confusion(ids,active,labels),
            block_precision=block_precision(ids,active,labels,tx,seed),
            hard_negatives=[dict(name=kind, rows=sum(labels[t]['hard_negative_type']==kind for t in ids),
                false_alerts=sum(t in active and labels[t]['hard_negative_type']==kind for t in ids))
                for kind in sorted({labels[t]['hard_negative_type'] for t in ids}-{''})])
        metrics.append(metric)
        for code in RULE_NAMES:
            if code.startswith('D') or coverage[code]['status']=='not_evaluable' or coverage[code]['scope']=='source_diagnostic':
                per_rule.append(dict(period=period,rule_id=code,status='aggregate_or_missing_truth',fraud_precision=None,
                    note='No independent window/source truth in this SME base generator; see separate source/window challenges.'))
            else:
                per_rule.append(dict(period=period,rule_id=code,status='row_fraud_label_audit',
                    contributing=confusion(ids,contributing[code],labels), unsuppressed=confusion(ids,raw[code],labels),
                    candidate_rows=len(candidates[code]&ids),
                    hard_negative_contributions=dict(Counter(labels[t]['hard_negative_type'] for t in contributing[code]&ids if labels[t]['hard_negative_type'])),
                    note='Fraud intent labels are not independent predicate truth.'))
    budgets = [dict(capacity_profile=profile, profile_kind=kind,
                    **budget_review(cases, events, tx, labels, limits.slots, capacity_minutes=limits.minutes,
                                    period_end=max(row['posted_at'][:10] for row in tx.values())))
               for profile, kind, limits in workload_scenarios()]
    write_jsonl(destination/'rule_metrics.jsonl',per_rule)
    write_jsonl(destination/'budget_metrics.jsonl',budgets)
    aggregate_coverage = [dict(rule_id=code, windows=sum(r['rule_id']==code for r in diagnostics),
        evaluated=sum(r['rule_id']==code and r['status']=='evaluated' for r in diagnostics),
        skip_reasons=dict(Counter(reason for r in diagnostics if r['rule_id']==code for reason in r['skip_reasons']))) for code in ('D1','D2','D3','D4','D5','D6')]
    record = dict(seed=seed, seed_partition=partition, requested_rate=rate, data=str(data), report=str(destination),
        rows=len(tx), metrics=metrics, aggregate_coverage=aggregate_coverage, source_hashes=source_hashes,
        review_cases=len(cases), score_replay='passed', queue_membership='passed', model_usage='none',
        source_scope_note='Fresh six-family SME generator still lacks actual HR/ERP/receipt sources; source challenges assess those capabilities separately.')
    (destination/'evaluation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('reports/rule_repairs/phase4'))
    parser.add_argument('--data-root',type=Path,default=Path('data/rule_evidence_phase4'))
    parser.add_argument('--rows',type=int,default=50000)
    parser.add_argument('--reuse-data',action='store_true',help='Read and checksum existing datasets; rescore all observations')
    args = parser.parse_args()
    if args.rows<48000:
        raise ValueError('Need at least 48 positives at 0.1% for six-family generator coverage')
    for path in (args.output,) if args.reuse_data else (args.output,args.data_root):
        if path.exists() and any(path.iterdir()):
            raise FileExistsError(f'Refusing to overwrite {path}')
    args.output.mkdir(parents=True)
    config = json.loads(Path('reports/rule_repairs/phase3/sme_fraud_003/rule_config.json').read_text(encoding='utf-8'))
    config.setdefault('cash_payment_policy', 'disabled')
    config.update(evidence_policy='phase4',receivable_overdue_days=60)
    plan = dict(config=config, control_seeds=CONTROL_SEEDS, fresh_seeds=FRESH_SEEDS, rows_per_dataset=args.rows,
        test_threshold_tuning=False, held_out_test_seeds=True, benford_definition_policy='phase4',
        rationale='Business source predicates; preserve phase3 operational/A5 thresholds. BY for correlated window tests; no ML.')
    (args.output/'evaluation_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    code = Path(__file__).resolve().parent
    names = ('rules.py','evidence_policy.py','evidence_cases.py','evidence_evaluation.py','aggregate_challenge.py','benford.py',
             'features.py','accounting.py','generate.py','temporal_evidence.py','noise_policy.py','spec_policy.py','payment_evidence.py',
             'authority_policy.py','case_queue.py','run_evidence_evaluation.py','rule_audit.py','evidence_sources.schema.json',
             'payment_evidence.schema.json','authority_policy.schema.json','batch_controls.py','exception_validation.py','case_identity.py',
             'feature_contract.py','sync_feature_model.py','evaluate.py','run_rules.py','case_admission.py')
    fingerprints = {str(code/name):sha(code/name) for name in names}
    print('Predeclared source controls',flush=True)
    controls = source_controls(args.output,config)
    print('Independent aggregate windows',flush=True)
    aggregates = aggregate_controls(args.output)
    print('Historical 10k prefixes',flush=True)
    prefixes = baseline_prefixes(args.output,config)
    records = []
    for partition,seeds in FRESH_SEEDS.items():
        for seed in seeds:
            for rate in ((.003,) if partition=='validation' else (.001,.003,.005)):
                tag = f'{round(rate*1000):03d}'
                records.append(fresh_dataset(args.data_root/f'seed_{seed}'/f'sme_fraud_{tag}',
                    args.output/f'seed_{seed}'/f'sme_fraud_{tag}',config,seed,partition,rate,args.rows,args.reuse_data))
                gc.collect()
    all_hashes = {**fingerprints,**controls['source_hashes'],**aggregates['source_hashes']}
    for record in records:
        all_hashes.update(record['source_hashes'])
    for filename,fingerprint in all_hashes.items():
        if sha(Path(filename))!=fingerprint:
            raise ValueError(f'Source changed during evaluation: {filename}')
    if any(n.startswith(('sklearn','joblib')) for n in sys.modules):
        raise ValueError('Unexpected model module import')
    verification = dict(source_hashes=all_hashes, controls=controls, aggregates=aggregates, baseline_prefixes=prefixes,
        datasets=records, plan_sha256=sha(args.output/'evaluation_plan.json'), model_usage='none')
    (args.output/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
    lines = ['# Đợt 4 — bằng chứng và đánh giá độc lập', '',
        'Nguồn HR/override/số chứng từ/công nợ có phiên bản và thời điểm quan sát. C4/E2/F2 kiểm tra giao dịch; F3 gaps/F4 công nợ là hồ sơ nguồn riêng, không gán gian lận cho dòng tiền bất kỳ.',
        'Ngưỡng A5 và vận hành giữ từ đợt 3; không chọn lại theo test. Seed test mới khác seed validation; không train/chấm ML.', '',
        f"Đối chứng nguồn/mẫu hình: {controls['passed']}/{controls['cases']} khớp; nhãn điều kiện rule, không phải kết luận gian lận tài chính.",
        f"Cửa sổ D: {aggregates['matched']}/{aggregates['cases']} khớp nhãn can thiệp/đủ nguồn. Sai khác thống kê được giữ để đo power/FP, không chỉnh nhãn hoặc ngưỡng sau khi xem test.", '',
        '## Test mới — hai seed, mỗi bộ 50.000 dòng toàn thời gian', '',
        '| Seed | Tỷ lệ toàn bộ | Số dòng test | TP | FP | Precision | Recall |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for record in records:
        if record['seed_partition']=='test':
            m = next(r for r in record['metrics'] if r['period']=='test')
            lines.append(f"| {record['seed']} | {record['requested_rate']:.1%} | {m['rows']} | {m['tp']} | {m['fp']} | {m['fraud_precision']:.2%} | {m['fraud_recall_all']:.2%} |")
    lines += ['', '## Phạm vi kết luận', '',
        'Các bộ SME mới vẫn là generator sáu nhóm gian lận; nguồn HR/ERP thực chưa có. Accuracy C4/E2/F2/F3/F4 trên SME thật chưa đo được. Test chứa ít fraud ở tỷ lệ thấp; metric có số mẫu, Wilson theo dòng và bootstrap theo block công ty/tháng, không chứng minh độ tin cậy trên SME thật.',
        'control_metrics.jsonl tách điều kiện đã biết/thiếu nguồn; aggregate_metrics.jsonl dùng đơn vị cửa sổ. D3/D6 có tập đủ mẫu riêng; không hạ min_rows để ép dataset SME được đánh giá.',
        'rule_metrics.jsonl từng bộ có điểm góp và tín hiệu riêng, hard negatives; budget_metrics.jsonl so ngân sách 1/3/5 hồ sơ mới/công ty/ngày theo bằng chứng lúc mở, không dùng điểm hoặc thành viên tương lai.',
        '30.000 dòng đầu từ ba snapshot gốc giữ điểm/cảnh báo; đây là kiểm tra prefix, không phải chấm lại toàn bộ 300.000 dòng gốc.', '',
        '[Schema, chính sách và kiểm thử](../../rule_repairs_phase4.md). Cần thu nguồn thật và kết luận rà soát độc lập trước nghiệm thu sản phẩm/ML.']
    (args.output/'summary_vi.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(output=str(args.output),fresh_rows=sum(r['rows'] for r in records),controls=controls['cases'],model_usage='none')),flush=True)


if __name__=='__main__':
    main()
