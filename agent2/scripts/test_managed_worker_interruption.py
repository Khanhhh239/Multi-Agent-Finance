"""Exercise actual interruptions after a ciphertext worker claims a native job.

Reports controlled-stop recovery separately from abrupt native-process death.
All Portal, node, model, keys and source data are isolated synthetic fixtures.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests_he'),str(ROOT/'tests'),str(ROOT.parent)]
from test_managed_worker import ManagedHarness
from portal import server as portal
from portal.agent2_runtime import stop_owned
from experiments.he_inference.registry_demo import database_dump


def rows(path):
    with closing(sqlite3.connect(path)) as c:
        return c.execute('SELECT company,state FROM jobs').fetchall()


def run(output):
    output.mkdir(parents=True,exist_ok=False);checks=[];cases=[]
    with ManagedHarness() as f:
        original={k:database_dump(f.pair.env[k]) for k in ('snapshot_db','model_db')}
        keys=[f.pair.node_key_path.read_bytes(),f.pair.state_key_path.read_bytes()]
        for company,mode in [('C001','controlled_stop'),('C002','hard_crash')]:
            code,state=f.h.request('/api/agents/agent2/start',{});assert code==200,state
            worker=portal.HE_RUNTIME.process
            error=[];observed={};seen=threading.Event()
            def interrupt():
                try:
                    end=time.monotonic()+40
                    while time.monotonic()<end:
                        if (company,'running') in rows(f.pair.worker_root/'state/jobs.sqlite3'):
                            observed.update(company=company,worker_state='running',mode=mode)
                            seen.set()
                            if mode=='controlled_stop':f.stop()
                            else:stop_owned(worker)
                            return
                        time.sleep(.002)
                    raise AssertionError('native running state not observed; no injection made')
                except Exception as exc:error.append(str(exc));seen.set()
            thread=threading.Thread(target=interrupt,daemon=True);thread.start()
            headers={'Idempotency-Key':'native-interruption-'+mode}
            body=dict(snapshot_id=f.pair.env['queries'][company])
            code,state=f.h.request(f.h.url('he/jobs',company),body,headers=headers)
            assert code==202,state
            job=state['job_id'];assert seen.wait(40)
            thread.join(35);assert not thread.is_alive() and not error,error
            assert observed['worker_state']=='running'
            print('INJECTED '+mode+' '+job,flush=True)
            code,state=f.h.request('/api/agents/agent2/recover',{});assert code==200,state
            path=f.h.url('he/jobs/'+job,company)
            code,state=f.h.request(path+'/resume',{});assert code==202,state
            deadline=time.monotonic()+50
            while time.monotonic()<deadline:
                code,state=f.h.request(path)
                assert code==200,state
                if state['phase'] in ('completed','failed','expired'):break
                time.sleep(.1)
            code,again=f.h.request(f.h.url('he/jobs',company),body,headers=headers)
            assert code==202 and again['job_id']==job,again
            if mode=='controlled_stop':
                assert state['phase']=='completed',state
                code,result=f.h.request(path+'/result');assert code==200,result
                assert result['row_count']==5 and all(r['available'] for r in result['rows'])
                checks.append(dict(check='controlled Portal stop during native compute resumes same job with 5 rows',passed=True))
            else:
                assert state['phase']=='completed',state
                code,result=f.h.request(path+'/result');assert code==200,result
                assert result['row_count']==5 and all(r['available'] for r in result['rows'])
                checks.append(dict(check='hard native crash resumes the same job with five rows and one logical worker job',passed=True))
            worker_rows=rows(f.pair.worker_root/'state/jobs.sqlite3')
            assert sum(c==company for c,s in worker_rows)==1,worker_rows
            cases.append(dict(**observed,job_id=job,phase_after_recovery=state['phase'],reason=state['reason'],
                same_job=True,worker_rows=1,resumable=state['phase']=='completed'))
            print(json.dumps(cases[-1]),flush=True)
            f.stop()
        assert original=={k:database_dump(f.pair.env[k]) for k in original}
        assert keys==[f.pair.node_key_path.read_bytes(),f.pair.state_key_path.read_bytes()]
        checks.append(dict(check='source models, snapshots and protected keys unchanged',passed=True))
    report=dict(status='passed',harness_checks_passed=True,acceptance_passed=True,checks=checks,cases=cases,
        acceptance='controlled stop and hard native crash both resume the same request within its TTL',
        live_services_changed=False,data='isolated synthetic fixtures',real_native_he=True)
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],checks=len(checks))),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args();run(args.output_dir.resolve())
