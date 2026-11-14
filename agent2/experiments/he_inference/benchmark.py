"""Same saved company model/snapshot: plaintext vs durable native HE scoring.

Read-only source stores; fresh private node/worker state; no Portal restart,
refit, threshold change or plaintext fallback. Only synthetic prepared packets.
"""
from contextlib import ExitStack, closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import secrets
import sqlite3
import tempfile
import time
from unittest.mock import patch

import numpy as np

from sme_fraud.auth import FileAuthorizer
from sme_fraud.he_workbench import HEWorkbench
from sme_fraud.import_files import digest
from sme_fraud.method_preprocess import row_values
from sme_fraud.snapshot_features import build_from_snapshot
from .comparison_metrics import compare_rows, timing_summary, recovery_summary
from .enterprise_server import load_node
from .prepared_demo import private_folder, worker_service, write, VERSION as PREPARED_VERSION
from .protocol import read_json
from .registry_demo import database_dump
from .registry_export import ReadOnlySnapshots, _load_model

VERSION='he-plaintext-comparison/1.0.0'
MODES=('disconnect_before_claim','controlled_restart_during_compute','hard_crash_during_compute')


class Trial:
    def __init__(self,packet,private):
        self.packet=packet;self.private=private;self.worker=None;self.node=None
        self.worker_state=private/'worker';self.node_state=private/'node'
        self.config=read_json(packet/'enterprise/node.json')
        self.config['state_dir']=str(self.node_state)
        token=secrets.token_urlsafe(32);self.header='Bearer '+token
        policy=private/'auth.json'
        write(policy,dict(policy_version='1.0.0',principals=[dict(actor_id='he-comparison',tenant_id='demo',
            token_sha256=digest(token.encode()),status='active',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            memberships=[dict(company_id=c,role='accountant',status='active',permissions=['data.import']) for c in ('C001','C002')])]))
        self.auth=FileAuthorizer(policy)

    def start_worker(self):
        assert self.worker is None
        manager=worker_service(self.packet,self.worker_state)
        url=manager.__enter__();self.worker=manager;self.config['worker_url']=url
        if self.node is not None:self.node.worker_url=url

    def stop_worker(self):
        manager,self.worker=self.worker,None
        if manager is not None:manager.__exit__(None,None,None)

    def start_node(self):
        assert self.node is None
        self.node=load_node(self.config,self.auth)
        self.web=HEWorkbench(self.node,self.packet/'enterprise/he-ui-bindings.json')

    def stop_node(self):
        node,self.node=self.node,None
        if node is not None:node.jobs.close()

    def close(self):
        try:self.stop_node()
        finally:self.stop_worker()

    def worker_jobs(self,company):
        path=self.worker_state/'jobs.sqlite3'
        if not path.exists():return []
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
            return c.execute('SELECT session,nonce,state FROM jobs WHERE company=?',(company,)).fetchall()

    def submit(self,info,key):
        company=info['company_id'];scope=self.auth.authorize(self.header,company)
        return self.web.submit(scope,lambda:self.auth.authorize(self.header,company),company,self.header,key,
                               dict(snapshot_id=info['evaluation_snapshot_id']))

    def wait(self,company,job,phases,seconds=45):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            state=self.node.jobs.status(company,self.header,job)
            if state['phase'] in phases:return state
            if state['phase'] in ('failed','expired'):raise RuntimeError('unexpected terminal phase: '+str(state['reason']))
            time.sleep(.005)
        raise RuntimeError('timed out waiting for '+','.join(phases))

    def he_run(self,info,key):
        started=time.perf_counter();state=self.submit(info,key);job=state['job_id'];company=info['company_id']
        self.wait(company,job,{'completed'})
        code,result=self.node.jobs.result(company,self.header,job)
        elapsed=(time.perf_counter()-started)*1000
        assert code==200 and result['company_id']==company and result['snapshot_id']==info['evaluation_snapshot_id']
        return result,elapsed

    def clear_run(self,info,as_of):
        started=time.perf_counter();company=info['company_id'];scope=self.auth.authorize(self.header,company)
        check=lambda:self.auth.authorize(self.header,company)
        _,manifest,model=_load_model(self.config['model_db'],scope,info['artifact_id'],check)
        frame=build_from_snapshot(ReadOnlySnapshots(self.config['snapshot_db']),scope,info['evaluation_snapshot_id'],as_of,check)
        prepared=[]
        for features in frame['features']:
            values,missing,reason=row_values(frame,features,manifest['preprocess'])
            if reason is not None:raise ValueError('plaintext input unavailable: '+str(reason))
            prepared.append(values)
        values=np.asarray(prepared,dtype=float)
        core=time.perf_counter();scores=model.score(values);core_ms=(time.perf_counter()-core)*1000
        rows=[dict(record_id=r['record_id'],revision=r['revision'],available=True,score=float(s)) for r,s in zip(frame['rows'],scores)]
        return rows,(time.perf_counter()-started)*1000,core_ms,manifest,frame

    def recovery_case(self,info,reference,mode,number):
        company=info['company_id'];key='recovery-'+company+'-'+mode+'-'+str(number)
        before={(s,n) for s,n,_ in self.worker_jobs(company)}
        state=self.submit(info,key);job=state['job_id'];injection=False;observed=None
        started=time.perf_counter()
        if mode=='disconnect_before_claim':
            self.wait(company,job,{'preparing'})
            self.stop_worker()
            added=[r for r in self.worker_jobs(company) if r[:2] not in before]
            injection=not added;observed='preparing_no_worker_claim' if injection else 'claim_race'
            if injection:self.wait(company,job,{'retryable'})
        else:
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                added=[r for r in self.worker_jobs(company) if r[:2] not in before]
                if any(r[2]=='running' for r in added):
                    observed='worker_running';injection=True;break
                if any(r[2]=='done' for r in added):observed='completed_before_injection';break
                time.sleep(.002)
            if mode=='controlled_restart_during_compute':
                # Production Jobs.close shutdown: let in-flight native compute
                # finish/commit, then reopen the same protected node/worker state.
                self.stop_node();self.stop_worker()
            else:
                self.stop_worker()
                added=[r for r in self.worker_jobs(company) if r[:2] not in before]
                # A kill that lost the race with commit is not a crash trial.
                injection=injection and any(r[2]=='running' for r in added)
                if not injection:observed='completed_before_kill'
        recovery_started=time.perf_counter();self.start_worker()
        if self.node is None:self.start_node()
        self.node.jobs.resume(company,self.header,job)
        terminal=self.wait(company,job,{'completed','failed','expired'})
        elapsed=(time.perf_counter()-recovery_started)*1000
        again=self.submit(info,key);same_job=again['job_id']==job
        after=[r for r in self.worker_jobs(company) if r[:2] not in before]
        recovered=False;parity=None
        if terminal['phase']=='completed':
            code,result=self.node.jobs.result(company,self.header,job)
            parity=compare_rows(reference,result['rows'])
            recovered=code==200 and same_job and len(after)==1 and parity['all_scores_within_tolerance']
        return dict(company_id=company,mode=mode,trial=number,job_id=job,observed=observed,
            injection_confirmed=injection,recovered=bool(recovered),same_job=same_job,new_worker_jobs=len(after),
            phase=terminal['phase'],reason=terminal['reason'],recovery_ms=elapsed if recovered else None,
            observed_terminal_ms=elapsed,total_case_ms=(time.perf_counter()-started)*1000,
            parity=parity)


def run(packet,output,repetitions=5,recovery_repetitions=1,budget=5):
    packet=Path(packet).resolve();output=Path(output).resolve()
    if not 1<=repetitions<=20 or not 1<=recovery_repetitions<=5:raise ValueError('trial counts outside supported limits')
    if output==packet or output.is_relative_to(packet):raise ValueError('report must be outside the protected source packet')
    output.mkdir(parents=True,exist_ok=False)
    prepared=read_json(packet/'prepared.json')
    if prepared['version']!=PREPARED_VERSION or prepared['status']!='prepared' or prepared['data']!='synthetic_only':
        raise ValueError('requires the prepared synthetic packet')
    infos=prepared['companies']
    if {i['company_id'] for i in infos}!={'C001','C002'}:raise ValueError('requires C001/C002')
    for name,expected in prepared['source_sha256'].items():
        path=(packet/name).resolve()
        if not path.is_relative_to(packet) or digest(path.read_bytes())!=expected:raise ValueError('source integrity mismatch')
    config=read_json(packet/'enterprise/node.json')
    before={k:database_dump(config[k]) for k in ('model_db','snapshot_db')}
    key_before={k:digest(Path(config[k]).read_bytes()) for k in ('state_key_file','provisioning_key_file')}
    companies=[];recoveries=[];references={}
    # Every process/state below is private to this measurement. Live services
    # and live session stores are not reused or stopped.
    with tempfile.TemporaryDirectory(prefix='he-comparison-') as temp, ExitStack() as stack:
        private=private_folder(Path(temp)/'private')
        t=Trial(packet,private);stack.callback(t.close)
        # Hard guards: even an accidental scoring refactor cannot fit/publish.
        for target in ('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit',
                       'sme_fraud.ml_estimators.CompanyEstimator.fit',
                       'sme_fraud.method_store.MethodStore.begin_fit','sme_fraud.method_store.MethodStore.publish'):
            stack.enter_context(patch(target,side_effect=AssertionError('fit/publish forbidden during comparison')))
        t.start_worker();t.start_node()
        for info in infos:
            company=info['company_id'];scope=t.auth.authorize(t.header,company)
            store=ReadOnlySnapshots(config['snapshot_db']);snapshot=store.get_snapshot(scope,info['evaluation_snapshot_id'])
            if snapshot['checksum']!=info['evaluation_checksum']:raise ValueError('snapshot checksum mismatch')
            source=read_json(packet/info['evaluation_file'])
            if len(source['transactions'])!=5 or not all(r['company_id']==company and r['source']['is_simulated'] for r in source['transactions']):
                raise ValueError('requires exactly five synthetic rows per company')
            as_of=snapshot['created_at']
            reference,_,_,manifest,frame=t.clear_run(info,as_of)
            warm,_=t.he_run(info,'warmup-'+company)
            assert compare_rows(reference,warm['rows'],budget)['all_scores_within_tolerance']
            references[company]=reference
            trials=[]
            for i in range(repetitions):
                key='measurement-'+company+'-'+str(i)
                if i%2==0:
                    clear,plain_ms,core_ms,_,_=t.clear_run(info,as_of)
                    he,he_ms=t.he_run(info,key)
                else:
                    he,he_ms=t.he_run(info,key)
                    clear,plain_ms,core_ms,_,_=t.clear_run(info,as_of)
                assert clear==reference,'plaintext reference changed'
                parity=compare_rows(clear,he['rows'],budget)
                trials.append(dict(trial=i+1,job_id=he['run_id'],plaintext_pipeline_ms=plain_ms,
                    plaintext_core_ms=core_ms,he_pipeline_ms=he_ms,metrics=parity))
            row=dict(company_id=company,artifact_id=info['artifact_id'],model_version=manifest['model_version'],
                snapshot_id=info['evaluation_snapshot_id'],snapshot_checksum=snapshot['checksum'],as_of=as_of,
                selected_columns=manifest['selected_columns'],feature_contract_fingerprint=frame['contract']['fingerprint'],
                row_count=len(reference),repetitions=repetitions,warmup_runs=1,review_budget=budget,
                plaintext_pipeline=timing_summary([v['plaintext_pipeline_ms'] for v in trials]),
                plaintext_core=timing_summary([v['plaintext_core_ms'] for v in trials]),
                he_pipeline=timing_summary([v['he_pipeline_ms'] for v in trials]),
                maximum_absolute_error=max(v['metrics']['maximum_absolute_error'] for v in trials),
                all_scores_within_tolerance=all(v['metrics']['all_scores_within_tolerance'] for v in trials),
                exact_order_equal_all_trials=all(v['metrics']['exact_order_equal'] for v in trials),
                material_pair_inversions=sum(v['metrics']['material_pair_inversions'] for v in trials),
                trials=trials)
            row['he_to_plaintext_median_ratio']=row['he_pipeline']['median_ms']/row['plaintext_pipeline']['median_ms']
            companies.append(row)
            print(json.dumps(dict(company=company,phase='scores',max_abs_error=row['maximum_absolute_error'],
                                 plaintext_ms=row['plaintext_pipeline']['median_ms'],he_ms=row['he_pipeline']['median_ms'])),flush=True)
        for info in infos:
            for mode in MODES:
                for i in range(recovery_repetitions):
                    case=t.recovery_case(info,references[info['company_id']],mode,i+1)
                    recoveries.append(case)
                    print(json.dumps({k:case[k] for k in ('company_id','mode','injection_confirmed','recovered','phase','reason')}),flush=True)
        worker_counts={c:len(t.worker_jobs(c)) for c in ('C001','C002')}
        expected=repetitions+1+len(MODES)*recovery_repetitions
        assert all(n==expected for n in worker_counts.values()),'unexpected duplicate/missing worker jobs'
    assert before=={k:database_dump(config[k]) for k in before},'source databases changed'
    assert key_before=={k:digest(Path(config[k]).read_bytes()) for k in key_before},'source protected keys changed'
    score_ok=all(c['all_scores_within_tolerance'] and not c['material_pair_inversions'] for c in companies)
    recovery_ok=all(c['injection_confirmed'] and c['recovered'] for c in recoveries)
    report=dict(version=VERSION,status='passed' if score_ok and recovery_ok else 'partial',
        measured_at=datetime.now(timezone.utc).isoformat(),data='synthetic_only',model='saved per-company Mahalanobis; 2 selected features / 33-feature contract',
        score_parity_passed=score_ok,full_recovery_passed=recovery_ok,companies=companies,
        recovery_cases=recoveries,recovery_summary=recovery_summary(recoveries),worker_jobs=worker_counts,
        source_models_snapshots_keys_unchanged=True,live_services_changed=False,
        measurement=dict(repetitions=repetitions,recovery_repetitions_per_company_mode=recovery_repetitions,
            clock='time.perf_counter',warmup='one plaintext + one fresh HE run per company, excluded',
            plaintext_pipeline='scope check, read/validate saved model, snapshot features, preprocessing, score',
            he_pipeline='HEWorkbench.submit to decrypted durable result; includes signed readiness, model/features, encryption, checkpoints, worker HTTP and polling',
            excluded='worker/node startup for normal timing, offline fit, Portal/browser and public-cloud network',
            timing_order='alternating plaintext first and HE first; each HE run uses a fresh request, never cache',
            recovery_start='restart of worker/node begins; includes worker process startup; reports observed time to terminal separately',
            controlled_restart='Jobs.close drains native compute before restarting node/worker; prior Portal acceptance separately exercises actual UI stop'),
        limitations=['Five synthetic transactions per company; not fraud detection accuracy.',
            'Top-5 covers all five rows and cannot demonstrate candidate-selection benefit.',
            'Small sample recovery fractions are observations, not an SLA or a population reliability estimate.',
            'Local loopback timings do not predict public-cloud latency; p95 is descriptive with only five default trials.',
            'Recovery only covers the identical managed request within its original TTL and intact state; legacy burned nonces and terminal failures are not reopened.'],
        environment=dict(python=platform.python_version(),platform=platform.platform()))
    (output/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    from .comparison_report import render
    render(report,output)
    return report
