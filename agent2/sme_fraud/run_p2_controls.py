"""Prepare and replay a separate P2 control set; frozen 001/003/005 stay opaque."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from .case_queue import review_queue
from .feature_contract import sha, current_contract
from .features import build_features
from .generate import write_csv
from .p2_control_cases import VERSION, declarations, build_control, check_books
from .rules import score_rules

PROJECT = Path(__file__).resolve().parents[1]
PROTECTED = tuple(PROJECT/name for name in (
    'data/synthetic_sources_20261017_v2','reports/synthetic_sources_20261017_v2',
    'reports/pipeline_rehearsal_20261018_v2','reports/cash_review_20261018_v2'))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def fingerprints():
    return {str(path.relative_to(PROJECT)):sha(path) for folder in PROTECTED if folder.exists()
            for path in sorted(folder.rglob('*')) if path.is_file() and not path.name.endswith(('-wal','-shm','.lock'))}


def fresh(path):
    path=Path(path).resolve()
    for protected in PROTECTED:
        if path==protected or protected in path.parents or path in protected.parents:
            raise ValueError('Control outputs must be separate from frozen 001/003/005 roots')
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise FileExistsError('Use a fresh output; existing sources and reports are preserved')
    return path


def separate(source, output):
    if source==output or source in output.parents or output in source.parents:
        raise ValueError('Control data and report roots must be separate')


def prepare(path):
    path=fresh(path)
    path.mkdir(parents=True,exist_ok=True)
    specs=declarations()
    index,expectations=[],[]
    for spec in specs:
        tables,config=build_control(spec)
        check_books(tables)
        folder=path/spec['control_id']
        folder.mkdir()
        write(folder/'tables.json',tables)
        write(folder/'rule_config.json',config)
        for table in ('transactions','invoices','journal_documents','journal_lines','account_flow_edges','document_links','recurring_payments'):
            if tables.get(table):
                write_csv(folder/(table+'.csv'),tables[table],sorted({key for row in tables[table] for key in row}))
        index.append({key:spec[key] for key in ('control_id','group','title_vi')})
        if len(spec['expected'])!=len(tables['transactions']):
            raise ValueError('Every control observation needs a declared outcome')
        expectations.extend(dict(control_id=spec['control_id'],transaction_id=row['transaction_id'],**outcome)
            for row,outcome in zip(tables['transactions'],spec['expected']))
    write(path/'control_index.json',index)
    write(path/'expected_outcomes.json',expectations)
    files={p.relative_to(path).as_posix():sha(p) for p in sorted(path.rglob('*')) if p.is_file()}
    manifest=dict(version=VERSION,role='separate_declared_p2_controls',is_synthetic=True,
        controls=len(specs),observations=len(expectations),expected_outcomes_declared_before_scoring=True,
        financial_fraud_labels=False,files=files)
    write(path/'manifest.json',manifest)
    return path


def verify_sources(path):
    manifest=read(path/'manifest.json')
    if manifest.get('version')!=VERSION or manifest.get('role')!='separate_declared_p2_controls' or manifest.get('is_synthetic') is not True:
        raise ValueError('Only the separate P2 control set is accepted; no reporting/holdout dataset')
    for name,expected in manifest['files'].items():
        file=(path/name).resolve()
        if path not in file.parents or sha(file)!=expected:
            raise ValueError('Control source hash/scope mismatch: '+name)
    return manifest


def observations(result, cases):
    p2={h['transaction_id']:h for h in result['hits'] if h['rule_id']=='P2'}
    a5={h['transaction_id']:h for h in result['hits'] if h['rule_id']=='A5'}
    binding={}
    for case in cases:
        for tid in json.loads(case['transaction_ids']): binding.setdefault(tid,[]).append(case)
    rows=[]
    for score in result['scores']:
        tid=score['transaction_id'];hit=p2.get(tid);attached=binding.get(tid,[])
        rows.append(dict(transaction_id=tid,p2_present=bool(hit),category=hit['evidence']['review_category'] if hit else None,
            points=hit['points'] if hit else 0,case_types=sorted({c['case_type'] for c in attached}),
            priorities=sorted({c['priority'] for c in attached}),case_ids=sorted(c['case_id'] for c in attached),
            operational_alert=score['operational_alert'],a5_suppressed=bool(a5.get(tid,{}).get('suppressed_reason')),
            other_positive_rules=sorted(h['rule_id'] for h in result['hits'] if h['transaction_id']==tid and h['rule_id']!='P2' and h['points']>0)))
    return rows


def compare(expected, actual):
    fields=('p2_present','category','points')
    differences={field:dict(expected=expected[field],actual=actual[field]) for field in fields if expected[field]!=actual[field]}
    for target,field in (('case_type','case_types'),('priority','priorities')):
        value=[expected[target]] if expected[target] else []
        if value!=actual[field]: differences[field]=dict(expected=value,actual=actual[field])
    if 'a5_suppressed' in expected and expected['a5_suppressed']!=actual['a5_suppressed']:
        differences['a5_suppressed']=dict(expected=expected['a5_suppressed'],actual=actual['a5_suppressed'])
    return differences


def evaluate(source, output):
    source=Path(source).resolve();output=fresh(output)
    separate(source,output)
    if any(source==p or p in source.parents for p in PROTECTED):
        raise ValueError('Frozen reporting/holdout roots cannot be loaded as P2 controls')
    manifest=verify_sources(source)
    manifest_sha256=sha(source/'manifest.json')
    protected=fingerprints()
    output.mkdir(parents=True,exist_ok=True)
    implementation={str(p.relative_to(PROJECT)):sha(p) for p in (PROJECT/'sme_fraud').glob('*.py')}
    write(output/'evaluation_plan.json',dict(version=VERSION,source=str(source),manifest_sha256=manifest_sha256,
        expected_sha256=manifest['files']['expected_outcomes.json'],code_sha256=implementation,
        protected_inputs_sha256=protected,model_fit=False,model_scored=False,holdout_scored=False,
        expected_join='Only after every detector/queue artifact is frozen; expectations never enter source tables or features'))
    all_predictions,accounting=[],[]
    prediction_files={}
    for control in read(source/'control_index.json'):
        identity=control['control_id']
        if not identity or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for ch in identity):
            raise ValueError('Invalid control ID')
        tables=read(source/identity/'tables.json')
        if {'labels','splits','expected','expected_outcomes'} & tables.keys():
            raise ValueError('Truth metadata cannot enter detector tables')
        config=read(source/identity/'rule_config.json')
        accounting.append(dict(control_id=identity,**check_books(tables)))
        features=build_features(tables)
        result=score_rules(tables,config=config,features=features)
        cases,events=review_queue(result,tables)
        folder=output/identity;folder.mkdir()
        write(folder/'predictions.json',observations(result,cases))
        write(folder/'rule_hits.json',result['hits'])
        write(folder/'case_queue.json',cases)
        write(folder/'case_events.json',events)
        write(folder/'rule_config.json',result['config'])
        write(folder/'feature_contract.json',dict(contract=current_contract(),rows=len(features),truth_loaded=False))
        for name in ('case_queue','rule_scores'):
            rows=cases if name=='case_queue' else result['scores']
            if rows: write_csv(folder/(name+'.csv'),rows,sorted({key for row in rows for key in row}))
        all_predictions.extend(dict(control_id=identity,**r) for r in observations(result,cases))
        prediction_files.update({p.relative_to(output).as_posix():sha(p) for p in folder.iterdir() if p.is_file()})
    write(output/'predictions.json',all_predictions)
    prediction_files['predictions.json']=sha(output/'predictions.json')
    write(output/'predictions_frozen.json',dict(files=prediction_files,expectations_joined=False,
        plan_sha256=sha(output/'evaluation_plan.json'),source_manifest_sha256=sha(source/'manifest.json')))
    assert all(sha(output/name)==checksum for name,checksum in prediction_files.items())
    # First read of expected outcomes during evaluation, after frozen predictions.
    expected=read(source/'expected_outcomes.json')
    actual={(r['control_id'],r['transaction_id']):r for r in all_predictions}
    assert len(actual)==len(all_predictions)==len(expected)
    comparisons=[dict(control_id=r['control_id'],transaction_id=r['transaction_id'],expected=r,
                      actual=actual[(r['control_id'],r['transaction_id'])],differences=compare(r,actual[(r['control_id'],r['transaction_id'])])) for r in expected]
    mismatches=[r for r in comparisons if r['differences']]
    write(output/'comparison.json',comparisons)
    write(output/'mismatches.json',mismatches)
    write(output/'accounting_validation.json',accounting)
    assert fingerprints()==protected,'Frozen original source/report changed'
    assert verify_sources(source)==manifest,'Prepared control inputs changed'
    assert sha(source/'manifest.json')==manifest_sha256,'Control manifest changed during replay'
    assert {name:sha(PROJECT/name) for name in implementation}==implementation,'Implementation changed during replay'
    summary=dict(successful=not mismatches,status='passed' if not mismatches else 'declared_expectations_require_fix',
        controls=manifest['controls'],observations=len(expected),matched_observations=len(expected)-len(mismatches),mismatches=len(mismatches),
        groups=dict(Counter(r['group'] for r in read(source/'control_index.json'))),
        category_counts=dict(Counter(r['category'] or 'no_p2' for r in all_predictions)),
        protected_input_files=len(protected),protected_inputs_unchanged=True,source_inputs_unchanged=True,
        expected_joined_after_freeze=True,model_fit=False,model_scored=False,holdout_005_scored=False,
        independent_human_reviews=0,financial_fraud_precision=None,external_messages_sent=0,
        journal_documents=sum(r['documents'] for r in accounting),journal_lines=sum(r['journal_lines'] for r in accounting))
    write(output/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--data-output',type=Path,help='Create the declared source fixtures in a fresh directory')
    inputs.add_argument('--prepared',type=Path,help='Replay previously committed control inputs')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=fresh(args.output)
    source=Path(args.prepared or args.data_output).resolve()
    separate(source,output)
    if args.data_output: source=prepare(source)
    result=evaluate(source,output)
    if not result['successful']: raise SystemExit(1)


if __name__=='__main__':
    main()
