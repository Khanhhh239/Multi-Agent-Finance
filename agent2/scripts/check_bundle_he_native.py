"""Isolated real Concrete/HTTP -> bundle -> case budget -> review/report acceptance.

Provisions fresh DPAPI enterprise keys, never modifies live services or state.
Only P1 key is provisioned by default: other profiles must remain unavailable.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT/'scripts'),str(ROOT.parent)]
from test_bundle_he import Fixture
import test_release_shadow_plan as support
from verify_he_full_flow import _free_port,_wsl_worker_start,_wsl_worker_stop
from experiments.he4 import bundle
from experiments.he4.windows_bridge import CryptoBridge,linux_path
import experiments.he4.coordinator as coord
from experiments.he_inference.protocol import canonical,public_hex
from experiments.he_inference.http_common import ServiceError
from sme_fraud.import_files import ImportFailure
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.bundle_he import BundleHE


def run(output,companies):
    output.mkdir(parents=True,exist_ok=False);owner=unittest.TestCase();worker=None;started=time.monotonic()
    report=dict(status='running',synthetic=True,live_deployed=False,actual_fhe=False)
    support.ShadowPlanTests.setUpClass()
    try:
        f=Fixture(owner,workers=1)
        f.bridge=CryptoBridge(f.he.root/'private',f.he.state_key)
        f.node.jobs.bridge=f.bridge
        port=_free_port();f.settings.config['worker_url']=f'http://127.0.0.1:{port}'
        f.node.worker_url=f.settings.config['worker_url']
        public=output/'public-worker';bundle.build(public)
        signing=f.he.root/'worker-signing.hex';signing.write_text(f.he.worker_key.private_bytes_raw().hex())
        grants=f.he.root/'grants.json';grants.write_bytes(canonical(dict(version='he-worker-grants/1.0.0',grants=[
            dict(tenant_id='demo',company_id=c,node_verify_key=public_hex(f.he.prov_key),active=True) for c in companies])))
        config=f.he.root/'public-worker.json';config.write_bytes(canonical(dict(version='he4-worker/0.1.0',
            state_dir=linux_path(f.he.root/'cloud-state'),grants_file=linux_path(grants),signing_key_file=linux_path(signing),
            builds={k:linux_path(v) for k,v in f.settings.config['builds'].items()})))
        worker=_wsl_worker_start(public,config,port,output/'worker.log')
        print('Real ciphertext worker ready; provisioning fresh enterprise P1 keys.',flush=True)
        results=[];uploads=[];routes=[];dropped=[False];original_post=coord.post;original_upload=coord.upload
        def observe_upload(url,scope,key,verify,path,kind):
            assert kind in ('ciphertext','public_evaluation_keys')
            sha=original_upload(url,scope,key,verify,path,kind)
            uploads.append(dict(company=next(iter(scope.company_ids)),kind=kind,sha256=sha,bytes=Path(path).stat().st_size))
            return sha
        def observe_post(url,route,packet,timeout=30):
            routes.append(dict(route=route,company=packet['payload']['company_id']))
            response=original_post(url,route,packet,timeout=timeout)
            if route=='/v1/evaluate' and not dropped[0]:
                dropped[0]=True;raise ServiceError(503,'WORKER_CONNECTION_UNAVAILABLE')
            return response
        for company in companies:
            scope=f.he.auth.authorize(f.header,company)
            meta=f.bridge.provision(scope,f.settings.config['builds']['rules'])
            b=f.activate(company)
            print(company+': HE bundle approved for staging; submitting one immutable snapshot.',flush=True)
            with ExitStack() as stack:
                stack.enter_context(patch('experiments.he4.coordinator.post',side_effect=observe_post))
                stack.enter_context(patch('experiments.he4.coordinator.upload',side_effect=observe_upload))
                stack.enter_context(patch.object(f.svc,'_execute',side_effect=AssertionError('No clear executor during HE request')))
                deadline=time.monotonic()+1200;value=None;pending=0;last_phase=None
                while time.monotonic()<deadline:
                    try:value=f.run(company=company);break
                    except ImportFailure as error:
                        if error.code!='PIPELINE_RUN_PENDING':raise
                        pending+=1
                        for job in f.jobs():
                            try:row,_=f.node.jobs.store.get(scope,job)
                            except ServiceError:continue
                            if row['phase']!=last_phase:
                                last_phase=row['phase'];print(company+': '+last_phase,flush=True)
                        time.sleep(2)
                if value is None:raise AssertionError('Real FHE run did not finish within acceptance limit')
            r=value['result'];target=next(x for x in r['rows'] if x['transaction_id']=='AUDIT_0000')
            p1=next(x for x in target['rule_coverage']['rules'] if x['rule_id']=='P1')
            # Independent arithmetic oracle: prior 6m + current 6m > invoice 10m.
            assert p1['status']==('evaluated_hit' if company=='C001' else 'evaluated_no_hit'),p1
            assert p1['score']==(20 if company=='C001' else 0)
            assert all(not row['branches'][name]['available'] for row in r['rows'] for name in ('statistics','ml'))
            assert r['he_execution'] and r['pipeline']['he_execution'] and not r['execution']['plaintext_cloud_upload']
            assert r['he_provenance']['key_epochs_by_profile']['rules']==meta['key_epoch']
            saved=f.svc.workspace.report(scope,value['run_id'])
            assert all(saved[k]==value[k] for k in ('snapshot_id','run_id','bundle_id'))
            assert saved['he_execution'] and not saved['training_eligible']
            before=len(routes)
            restarted=ReleaseService(ReleaseStore(f.store.path,b's'*32),f.svc.snapshots,f.svc.resources,f.svc.case_queue)
            restarted.he_executor=BundleHE(f.backend)
            again=restarted.run(scope,value['run_id'],'staging',f.sids[company],f.data[company]['source']['as_of'],lambda:scope,
                                execution_mode='cloud_ciphertext_only',he_header=f.header)
            assert again==value and len(routes)==before
            (output/(company+'-business-report.json')).write_bytes(canonical(saved))
            results.append(dict(company=company,snapshot_id=value['snapshot_id'],run_id=value['run_id'],bundle_id=b['bundle_id'],
                he_job_id=r['execution']['cloud_he']['job_id'],p1_status=p1['status'],p1_score=p1['score'],rows=r['row_count'],
                queue_cases=r['pipeline']['queue']['counts'],review_cases=len(saved['cases']),
                restart_reuses_exact_observation=True,pending_polls=pending))
            print(company+': real FHE -> common shadow queue/review/report passed.',flush=True)
        assert dropped[0] and any(x['route']=='/v1/results' for x in routes)
        report=dict(status='pass',actual_fhe=True,authenticated_http=True,synthetic=True,live_deployed=False,
            companies=results,profiles_executed=['rules'],other_profile_keys_not_provisioned=True,
            response_loss_after_worker_commit_recovered=True,enterprise_restart_exact_observation=True,
            plaintext_cloud_upload=False,transport_uploads=uploads,transport_routes=routes,
            cloud_boundary='ciphertext and public evaluation keys only; source/decrypt/policy/cases stay enterprise',
            complete_35_rule_he=False,native_33_feature_he=False,production_approved=False,
            seconds=round(time.monotonic()-started,3))
        return report
    except Exception as error:
        report.update(status='fail',error_type=type(error).__name__,error=str(error));raise
    finally:
        _wsl_worker_stop(worker,kill_pattern=linux_path(config) if worker is not None else None)
        owner.doCleanups();support.ShadowPlanTests.tearDownClass()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--companies',nargs='+',choices=('C001','C002'),default=['C001','C002']);a=parser.parse_args()
    print(json.dumps(run(a.output.resolve(),a.companies),ensure_ascii=True,indent=2))
