"""Measured synthetic C001/C002 bundle/policy/queue/rollback acceptance.

Uses the real MethodStore and validation engine through an explicitly synthetic
fixture. Does not execute HE, approve business quality, or change live services.
"""
from copy import deepcopy
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT.parent)]
from test_release_shadow_plan import ShadowPlanTests
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.import_files import canonical,digest


def run(output):
    output.mkdir(parents=True,exist_ok=False);comparisons=[];rollbacks=[];gates=[]
    ShadowPlanTests.setUpClass()
    try:
        f=ShadowPlanTests.fixture
        with tempfile.TemporaryDirectory(dir=output) as temp:
            root=Path(temp);store=ReleaseStore(root/'releases.db',b'd'*32);queue=CaseQueueStore(root/'queue.db')
            svc=ReleaseService(store,f.snapshots,AnalysisResources(f.models.path),queue)
            for company in ('C001','C002'):
                scope=f.company_ctx[company]['scope'];package=deepcopy(ShadowPlanTests.packages[company])
                sid=f.company_ctx[company]['manifests']['sealed_future_test']['snapshot_id'];cutoff=package['evaluation_plan']['splits']['sealed_future_test']['as_of']
                snapshot_hash=digest(f.snapshots.get_snapshot(scope,sid,data=True));versions=[]
                for label in ('baseline','candidate'):
                    p=deepcopy(package)
                    if label=='candidate':p['case_policy']['policy_version']='fixture-release-candidate';p['case_policy']['scoring']['ml_weight']=4
                    reg=svc.register_plan(scope,p,company+'-register-'+label)
                    b=svc.prepare(scope,sid,company+' '+label,company+'-prepare-'+label,plan_id=reg['plan_id'])
                    g=svc.qualify(scope,b['bundle_id'],'staging');assert g['technical_ready']
                    a=svc.approve(scope,b['bundle_id'],g['gate_id'],'staging','Synthetic technical linked-shadow acceptance')
                    versions.append(dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id']))
                def switch(index,revision,action):
                    return svc.switch(scope,dict(versions[index],lane='staging',expected_revision=revision,reason='Synthetic linked-shadow '+action,action=action),company+'-switch-'+str(revision))
                switch(0,0,'activate');first=svc.run(scope,company+'-baseline-run','staging',sid,cutoff)
                switch(1,1,'activate');second=svc.run(scope,company+'-candidate-run','staging',sid,cutoff)
                back=switch(0,2,'rollback');third=svc.run(scope,company+'-rollback-run','staging',sid,cutoff)
                assert svc.run(scope,company+'-baseline-run','staging',sid,cutoff)==first
                assert digest(f.snapshots.get_snapshot(scope,sid,data=True))==snapshot_hash
                budgets=[r['metrics']['budget_status']['reserved_count'] for r in (first,second,third)]
                assert budgets==[budgets[0]]*3
                assert queue.get_queue_state(scope,mode='active')['items']==[]
                comparisons.append(dict(company_id=company,snapshot_id=sid,as_of=cutoff,data_checksum=snapshot_hash,
                    study_sha256=package['study']['study_result_sha256'],selected_arm_id=package['study']['detector_validation']['selected_arm_id'],
                    baseline=dict(bundle_id=first['bundle_id'],metrics=first['metrics']),candidate=dict(bundle_id=second['bundle_id'],metrics=second['metrics']),
                    change='Explicit fixture case policy version and ML score weight only; no model refit',
                    production_quality_evidence=False,precision=None,recall=None,review_minutes=None,
                    limitation='Shadow queue mechanics comparison, not validation of an optimal case policy or real-world fraud effectiveness'))
                rollbacks.append(dict(company_id=company,rollback=back,budget_reserved_before_after=budgets,
                    old_observation_identical=True,snapshot_unchanged=True,new_rollback_run_bundle_id=third['bundle_id'],
                    active_queue_empty=True,queue_periods=[r['result']['pipeline']['period_key'] for r in (first,second,third)]))
                gates.append(dict(company_id=company,gate=svc.qualify(scope,versions[0]['bundle_id'],'production')))
    finally:ShadowPlanTests.tearDownClass()
    for name,value in [('comparison_report',dict(companies=comparisons)),('rollback_report',dict(companies=rollbacks)),('release_gate',dict(companies=gates))]:
        value.update(spec_version='2.1',status='technical_only' if name!='release_gate' else 'BLOCKED',
            created_at=datetime.now(timezone.utc).isoformat(),synthetic=True,he_execution=False,cloud_plaintext_sent=False,live_deployed=False)
        (output/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    return dict(companies=2,status='READY_FOR_REVIEW_TECHNICAL',production='BLOCKED')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(p.parse_args().output.resolve())))
