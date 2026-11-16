"""Generate measured release/rollback smoke reports from isolated C001/C002.

Requires a passing focused regression report. This does not run or approve the
full R6 benchmark, cloud HE, production quality study or business SLA.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import secrets
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT.parent)]
from training_snapshot_support import scope,native,commit
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.import_files import canonical,digest
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore


def run(output,test_report):
    tests=json.loads(test_report.read_bytes())
    if tests['failures'] or tests['errors'] or tests['skipped']:raise ValueError('Acceptance requires passing regression with skip=0')
    output.mkdir(parents=True,exist_ok=False)
    comparisons=[];rollbacks=[];gates=[];metrics=[]
    with tempfile.TemporaryDirectory(dir=output) as temp:
        root=Path(temp);snap=SnapshotStore(root/'snapshots.db')
        store=ReleaseStore(root/'releases.db',secrets.token_bytes(32));svc=ReleaseService(store,snap)
        for company in ('C001','C002'):
            sc=scope(company);data=native(company);sid=commit(snap,data,sc,'acceptance-'+company);cutoff=data['source']['as_of']
            before=digest(snap.get_snapshot(sc,sid,data=True))
            versions=[]
            for name in ('baseline','candidate'):
                b=svc.prepare(sc,sid,company+' '+name,'prepare-'+company+'-'+name)
                g=svc.qualify(sc,b['bundle_id'],'staging')
                a=svc.approve(sc,b['bundle_id'],g['gate_id'],'staging','Synthetic technical staging acceptance')
                versions.append(dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id']))
            def switch(index,revision,action):
                return svc.switch(sc,dict(versions[index],lane='staging',expected_revision=revision,reason='Synthetic acceptance '+action,action=action),company+'-'+str(revision)+'-'+action)
            first=switch(0,0,'activate');baseline=svc.run(sc,'baseline-'+company,'staging',sid,cutoff)
            store.pin(sc,'interrupted-'+company,'staging',dict(snapshot_id=sid,as_of=cutoff))
            second=switch(1,1,'activate');candidate=svc.run(sc,'candidate-'+company,'staging',sid,cutoff)
            resumed=svc.run(sc,'interrupted-'+company,'staging',sid,cutoff)
            assert resumed['bundle_id']==versions[0]['bundle_id']
            rollback=switch(0,2,'rollback')
            assert digest(snap.get_snapshot(sc,sid,data=True))==before
            assert svc.run(sc,'baseline-'+company,'staging',sid,cutoff)==baseline
            prod=svc.qualify(sc,versions[0]['bundle_id'],'production');assert not prod['production_ready']
            comparisons.append(dict(company_id=company,snapshot_id=sid,as_of=cutoff,data_sha256=before,
                baseline_bundle_id=versions[0]['bundle_id'],candidate_bundle_id=versions[1]['bundle_id'],
                baseline_rows=len(baseline['result']['rows']),candidate_rows=len(candidate['result']['rows']),
                baseline_result_sha256=digest(canonical(baseline['result'])),candidate_result_sha256=digest(canonical(candidate['result'])),
                result_equal=baseline['result']==candidate['result'],comparison_kind='metadata_only_bundle_change_same_detector_pins',
                review_budget=None,precision=None,recall=None,review_minutes=None,
                conclusion='Configuration replay smoke only; no approved quality comparison or verified business labels'))
            rollbacks.append(dict(company_id=company,first=first,second=second,rollback=rollback,
                old_run_unchanged=True,interrupted_run_resumed_original_bundle=True,snapshot_unchanged=True,
                business_store_preservation_evidence='test_pipeline_release.ReleaseTests.test_rollback_keeps_real_queue_budget_outbox_task_and_labels',
                no_database_restore=True))
            gates.append(dict(company_id=company,gate=prod))
            metrics.append(dict(company_id=company,bundle_id=baseline['bundle_id'],metrics=baseline['metrics']))
    reports={
      'comparison_report':dict(spec_version='2.1',status='technical_only',companies=comparisons,business_quality_status='blocked_D09_no_independent_study'),
      'release_gate':dict(spec_version='2.1',status='BLOCKED',production_approved=False,staging_metadata_ready_for_review=True,companies=gates),
      'rollback_report':dict(spec_version='2.1',status='technical_only',scope='enterprise staging pointer only; not full HE/delivery release',companies=rollbacks),
      'monitoring_report':dict(spec_version='2.1',status='partial',companies=metrics,
          missing=['approved drift reference and trigger policy','queue/fallback/review metric attribution to full release bundle'],auto_training=False,auto_activation=False),
      'regression_summary':dict(count=tests['count'],failures=0,errors=0,skipped=0,source_sha256=digest(test_report.read_bytes()),tests=tests['tests'])}
    now=datetime.now(timezone.utc).isoformat()
    for name,value in reports.items():
        value.update(created_at=now,synthetic=True,cloud_he_executed=False,live_deployed=False)
        (output/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(status='READY_FOR_REVIEW_TECHNICAL',production='BLOCKED',companies=2,tests=tests['count'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--test-report',type=Path,required=True)
    args=p.parse_args();print(json.dumps(run(args.output.resolve(),args.test_report.resolve())))
