"""Replay all 35 retained rules through immutable import and analysis API core."""
import argparse,json,sys,time
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from finance_input import AccessScope
from sme_fraud.import_files import canonical,digest
from sme_fraud.rule_snapshot import CONTRACT
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.rules import RULE_NAMES,score_rules
from sme_fraud.benford import monthly_diagnostics


def run(inputs,output):
    manifest=json.loads((inputs/'manifest.json').read_bytes());output.mkdir(parents=True,exist_ok=False);samples=output/'inputs';samples.mkdir();store=SnapshotStore(output/'private-snapshots.sqlite3');checks=[];started=time.monotonic()
    if manifest['version']!='native-rule-demo/1.0.0' or len(manifest['cases'])!=120:raise ValueError('Complete synthetic source manifest required')
    for item in manifest['cases']:
        path=inputs/item['source_file']
        if path.resolve().parent!=inputs.resolve() or digest(path.read_bytes())!=item['source_sha256']:raise ValueError('Source checksum/path mismatch')
        source=json.loads(path.read_bytes());company=item['company_id'];scope=AccessScope('native-demo',frozenset({company}),'full-rules-check',frozenset({'data.import'}))
        if source['tenant_id']!='native-demo' or source['is_simulated'] is not True:raise ValueError('Synthetic scoped source required')
        data=dict(contract_version=CONTRACT,tenant_id='native-demo',company_id=company,source=source,candidate_transaction_ids=[source['tables']['transactions'][-1]['transaction_id']]);encoded=canonical(data);case_id=item['case_id'];(samples/(case_id+'.json')).write_bytes(encoded)
        draft=store.upload(scope,encoded,case_id+'.json',case_id+'-upload');preview=store.preview(scope,draft['import_id'],1)
        request={k:preview[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')};request.update(expected_revision=preview['revision'],acknowledge=True)
        saved=store.commit(scope,draft['import_id'],request,case_id+'-commit');result=analyze_snapshot(store,scope,saved['snapshot']['snapshot_id'],source['as_of'],technical=True)
        if len(result['catalogue'])!=35 or result['row_count']!=1:raise AssertionError('Lost rule/candidate')
        reference=score_rules(deepcopy(source['tables']));parity=digest(canonical(reference))==result['native_reference_sha256']
        expected=item['expected'];codes=expected.get('rule_ids',[expected.get('rule_id')])
        direct_stats=[d for d in monthly_diagnostics(source['tables'],'phase4') if d['cutoff_at']<=source['as_of']] if len(codes)>1 else []
        for code in codes:
            entry=next(r for r in result['catalogue_results'] if r['rule_id']==code)
            if code.startswith('D'):
                direct=[d for d in direct_stats if d['rule_id']==code];parity=parity and canonical(direct)==canonical(entry['statistics'])
                target=[d for d in entry['statistics'] if d['cutoff_at']==expected['cutoff_at']];actual=any(d.get('signal') is True for d in target);ready=any(d['status']=='evaluated' for d in target)
            else:actual=entry['matched'];ready=entry['available']
            checks.append(dict(case_id=case_id,company_id=company,rule_id=code,expected_signal=expected['expected_signal'],actual_signal=actual,available=ready,native_parity=parity,passed=ready and actual==expected['expected_signal'] and parity,source_sha256=digest(encoded),snapshot_id=saved['snapshot']['snapshot_id']))
        # Public evidence contains the target rules, not unrelated raw metadata.
        (output/(case_id+'.result.json')).write_bytes(canonical(dict(analysis_id=result['analysis_id'],snapshot=result['snapshot'],as_of=result['as_of'],catalogue_rules=len(result['catalogue']),target_results=[r for r in result['catalogue_results'] if r['rule_id'] in codes],native_reference_sha256=result['native_reference_sha256'],aggregate=result['aggregate'],he_execution=False)))
        print(json.dumps(dict(case=case_id,passed=all(c['passed'] for c in checks[-len(codes):]))),flush=True)
    report=dict(status='passed' if len(checks)==140 and all(c['passed'] for c in checks) else 'failed',implemented_rules=len(RULE_NAMES),snapshot_source_packages=120,positive_control_checks=len(checks),checks=checks,seconds=time.monotonic()-started,he_execution=False,model_fit_performed=False,accuracy=None,live_services_changed=False)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='checks'}));return report['status']=='passed'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,default=ROOT/'.runtime/native_rules_demo_20261114');p.add_argument('--output',type=Path,required=True);a=p.parse_args();raise SystemExit(0 if run(a.inputs.resolve(),a.output.resolve()) else 1)
