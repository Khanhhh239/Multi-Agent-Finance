"""Reproduce the user-approved selection trial on public C001/C002 demo evidence.

No model fitting, new HE computation, Portal login or live feedback writes.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT)]
from sme_fraud.import_files import canonical,digest
from sme_fraud.selection_comparison import make_plan,report_for


def run(output):
    evidence=ROOT.parent/'Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113'
    manifest=json.loads((evidence/'evidence-manifest.json').read_text('utf-8'));hashes={f['path']:f['sha256'] for f in manifest['files']}
    output.mkdir(parents=True,exist_ok=False);summary=[]
    for company in ('C001','C002'):
        files={}
        for kind in ('result','review-packet','source'):
            name=company+'-'+kind+'.json';payload=(evidence/name).read_bytes();assert hashlib.sha256(payload).hexdigest()==hashes[name],name;files[kind]=json.loads(payload)
        result=files['result'];packet=files['review-packet'];source=files['source']
        assert result['run_id']==packet['run_id'] and result['snapshot_id']==packet['snapshot_id'] and result['as_of']==packet['as_of'] and result['company_id']==packet['company_id']==company
        assert packet['training_eligible'] is False and all(e['simulated'] and not e['original_verified'] for c in packet['cases'] for e in c['evidence'])
        assert all(c['review']['feedback'] is None for c in packet['cases']),'expected untouched archived demo packet'
        checksum=digest(canonical(source));plan=make_plan(result,packet['cases'],dict(checksum=checksum),dict(result_plan_sha256=result['plan_sha256'],source='archived native result, no independent model metadata export'))
        report=report_for(plan,packet['cases']);report.update(plan_id='cmp_'+digest(canonical([company,result['run_id'],plan['policy'],5])),plan_sha256=digest(canonical(plan)),evidence_source='archived public synthetic native results; no new scoring or live review reads')
        report.pop('report_sha256');report['report_sha256']=digest(canonical(report))
        (output/(company+'-plan.json')).write_bytes(canonical(plan));(output/(company+'-comparison.json')).write_bytes(canonical(report))
        summary.append(dict(company_id=company,run_id=result['run_id'],baseline=[r['record_id'] for r in report['baseline']['transactions']],combined=[r['record_id'] for r in report['combined']['transactions']],added=[dict(record_id=r['record_id'],rule_state=r['rule_state']) for r in report['added']],removed=report['removed'],reviewed=0,declared_incremental_usefulness=None,status=report['status']))
    value=dict(status='technical_only',budget_per_arm_per_company=5,policy='rules_first_fill/1.0.0',data='C001/C002 synthetic archived native runs already observed',prospective=False,companies=summary,accuracy=None,live_services_changed=False,new_model_fit=False,new_he_scoring=False)
    (output/'summary.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(value,ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output.resolve())
