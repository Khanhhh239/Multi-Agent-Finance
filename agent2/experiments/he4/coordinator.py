"""Enterprise-owned durable four-branch orchestration. No plaintext fallback."""
from copy import deepcopy
import json
from pathlib import Path
import queue
import threading
import uuid

import numpy as np
from finance_input.json_io import loads
from sme_fraud.auth import AuthError
from sme_fraud.import_files import ImportFailure,canonical,digest
from sme_fraud.snapshots import SnapshotStore
from experiments.he_inference.registry_export import ReadOnlySnapshots
from experiments.he_inference.node_jobs import Jobs
from experiments.he_inference.node_job_store import JobStore,TERMINAL
from experiments.he_inference.key_manager import PROVIDER
from experiments.he_inference.http_common import ServiceError,post,worker_address
from experiments.he_inference.protocol import HEUnavailable,verify,sha,canonical as wire
from .snapshot_adapter import prepare_snapshot
from .windows_bridge import CryptoBridge
from .client_transport import upload,download,envelope
from .inputs import decode_payment
from . import FRESH_ADMISSION


class Settings:
    def __init__(self,config):
        required={'version','state_dir','enterprise_root','state_key_file','worker_url','worker_verify_key','builds','bindings_file','linux_distro','linux_python'}
        if set(config)!=required or config['version']!='he4-enterprise/1.0.0':raise ValueError('HE4 enterprise configuration')
        worker_address(config['worker_url']);self.config=deepcopy(config);self.mutation_lock=threading.RLock()
        if set(config['builds'])!={'rules','statistics','graph'}:raise ValueError('three Concrete circuits required')
        if not isinstance(config['worker_verify_key'],str) or len(bytes.fromhex(config['worker_verify_key']))!=32:raise ValueError('worker key')

    def capture(self,scope):
        c=self.config;value=loads(Path(c['bindings_file']).read_bytes())
        if set(value)!={'version','bindings'} or value['version'] not in {'he4-company-bindings/1.0.0','he4-company-bindings/1.1.0'} or not isinstance(value['bindings'],list) or len(value['bindings'])>256:raise HEUnavailable('he4_bindings_invalid')
        found=None;seen=set()
        import re
        for row in value['bindings']:
            if not isinstance(row,dict) or set(row)-{'tenant_id','company_id','statistics_artifact_id','ml_artifact_id'} or not {'tenant_id','company_id','statistics_artifact_id'}<=set(row) or value['version']=='he4-company-bindings/1.0.0' and 'ml_artifact_id' in row:raise HEUnavailable('he4_bindings_invalid')
            identity=row['tenant_id'],row['company_id']
            if identity in seen or not all(isinstance(v,str) for v in identity):raise HEUnavailable('he4_bindings_invalid')
            seen.add(identity)
            if row['statistics_artifact_id'] is not None and (not isinstance(row['statistics_artifact_id'],str) or not re.fullmatch('mth_[a-f0-9]{64}',row['statistics_artifact_id'])):raise HEUnavailable('he4_bindings_invalid')
            if 'ml_artifact_id' in row and (not isinstance(row['ml_artifact_id'],str) or not re.fullmatch('mth_[a-f0-9]{64}',row['ml_artifact_id'])):raise HEUnavailable('he4_bindings_invalid')
            if identity==(scope.tenant_id,next(iter(scope.company_ids))):found=row
        if found is None:raise HEUnavailable('he4_company_not_configured')
        programs={}
        for profile,path in c['builds'].items():
            root=Path(path).resolve();manifest=loads((root/'manifest.json').read_bytes())
            if manifest['version']!='he4-circuit-build/0.1.0' or manifest['profile']!=profile:raise HEUnavailable('he4_build_incompatible')
            from .blob_store import BlobStore
            for name in ('server.zip','client.specs.json'):
                if BlobStore.digest(root/name)!=manifest['files'][name]:raise HEUnavailable('he4_build_integrity')
            programs[profile]=dict(path=str(root),circuit_sha256=manifest['files']['server.zip'],specs_sha256=manifest['files']['client.specs.json'])
        from . import snapshot_adapter,inputs
        from sme_fraud import p1_evaluation,p1_inputs,rule_sources,snapshot_features
        return dict(binding=found,programs=programs,worker_url=c['worker_url'],worker_verify_key=c['worker_verify_key'],
                    implementation_sha256=digest(b''.join(Path(p).read_bytes() for p in
                        (__file__,snapshot_adapter.__file__,inputs.__file__,p1_evaluation.__file__,p1_inputs.__file__,rule_sources.__file__,snapshot_features.__file__,
                         Path(__file__).with_name('enterprise_helper.py'),Path(__file__).with_name('windows_bridge.py')))))


class FourJobs(Jobs):
    def __init__(self,node,settings,*,workers=2,bridge=None):
        self.node=node;self.legacy=node.jobs;self.settings=settings
        c=settings.config
        self.store=JobStore(c['state_dir'],c['state_key_file'],required_provider=PROVIDER)
        self.bridge=bridge or CryptoBridge(c['enterprise_root'],c['state_key_file'],distro=c['linux_distro'],python=c['linux_python'])
        self.operations=Path(c['enterprise_root']).resolve()/'operations';self.operations.mkdir(parents=True,exist_ok=True)
        self.queue=queue.Queue(16);self.active=set();self.tickets={};self.timers=[]
        self.lock=threading.Lock();self.stopping=threading.Event()
        if workers not in (0,1,2):raise ValueError('workers')
        self.threads=[threading.Thread(target=self._loop,daemon=True) for _ in range(workers)]
        for thread in self.threads:thread.start()

    def close(self):
        super().close()
        self.legacy.close()

    def status(self,company,header,job_id):
        try:return super().status(company,header,job_id)
        except ServiceError as error:
            if error.code!='NODE_JOB_NOT_FOUND':raise
            return self.legacy.status(company,header,job_id)

    def result(self,company,header,job_id):
        try:return super().result(company,header,job_id)
        except ServiceError as error:
            if error.code!='NODE_JOB_NOT_FOUND':raise
            return self.legacy.result(company,header,job_id)

    def resume(self,company,header,job_id):
        try:return super().resume(company,header,job_id)
        except ServiceError as error:
            if error.code!='NODE_JOB_NOT_FOUND':raise
            return self.legacy.resume(company,header,job_id)

    def submit(self,company,header,key,body):
        import re
        scope=self._scope(header,company)
        if not isinstance(body,dict) or set(body)!={'artifact_id','snapshot_id','as_of'} or not isinstance(key,str) or not re.fullmatch('[A-Za-z0-9_.:-]{8,128}',key):raise ServiceError(400,'HE4_REQUEST_FIELDS')
        if (body['artifact_id'] is not None and (not isinstance(body['artifact_id'],str) or not re.fullmatch('mth_[a-f0-9]{64}',body['artifact_id']))) or not isinstance(body['snapshot_id'],str) or not re.fullmatch('snp_[a-f0-9]{32}',body['snapshot_id']):raise ServiceError(400,'HE4_REQUEST_FIELDS')
        from sme_fraud.snapshot_features import utc
        # Activation and admission share one mutex; a new request cannot slip
        # between the pending-run check and the atomic model binding switch.
        with self.settings.mutation_lock:
            context=self.settings.capture(scope)
            if context['binding'].get('ml_artifact_id',body['artifact_id'])!=body['artifact_id']:raise ServiceError(409,'HE4_MODEL_SELECTION_CHANGED')
            request=dict(body,as_of=utc(body['as_of']).isoformat(),he4_context=context)
            job=self.store.create(scope,key,request)
        self.schedule(scope,header,job)
        return self.status(company,header,job)

    def _save(self,scope,job,data,phase,reason=None):
        self.guard(job,scope);self.store.save(scope,job,data,phase,reason)

    def _process(self,scope,job):
        row,data=self.store.get(scope,job)
        if row['phase'] in TERMINAL:return False
        try:
            _,header=self.guard(job,scope);r=data['request'];context=r['he4_context'];company=next(iter(scope.company_ids))
            if context!=self.settings.capture(scope):raise HEUnavailable('he4_configuration_changed')
            data['attempts']+=1
            if r['artifact_id'] is None:pass  # independent branch absence, never implicit fit
            elif data.get('legacy_job') is None:
                child=self.legacy.submit(company,header,'four:'+job,{k:r[k] for k in ('artifact_id','snapshot_id','as_of')})
                data['legacy_job']=child['job_id'];self._save(scope,job,data,'preparing')
            else:
                # Both stores lose in-memory authorization tickets on a DN
                # crash. Re-authorize the saved child; never submit a new one.
                self.legacy.resume(company,header,data['legacy_job'])
            if data['pending'] is None:
                plan=prepare_snapshot(ReadOnlySnapshots(self.node.snapshot_db),scope,r['snapshot_id'],r['as_of'],model_db=self.node.model_db,
                    statistics_artifact=context['binding']['statistics_artifact_id'],recheck=lambda:self.guard(job,scope)[0])
                tasks=[];dedup={}
                for row_index,planned in enumerate(plan['rows']):
                    for branch_name,branch in planned['branches'].items():
                        branch['task_indexes']=[]
                        for request_index,request in enumerate(branch['requests']):
                            signature=digest(canonical(dict(profile=request['profile'],program=context['programs'][request['profile']],values=request['values'])))
                            if signature not in dedup:
                                dedup[signature]=len(tasks);tasks.append(dict(profile=request['profile'],values=request['values'],context=None,packet=None,response=None,result=None))
                            branch['task_indexes'].append(dedup[signature])
                data['pending']=dict(plan=plan,tasks=tasks,cursor=0)
                self._save(scope,job,data,'ready')
            pending=data['pending'];tasks=pending['tasks']
            for index in range(pending['cursor'],len(tasks)):
                self.guard(job,scope);task=tasks[index];profile=task['profile'];program=context['programs'][profile]
                root=self.operations/job/str(index);root.mkdir(parents=True,exist_ok=True)
                try:
                    if task['context'] is None:
                        task['context']=self.bridge.encrypt(scope,program['path'],task['values'],root/'input',recover_uncommitted=True)
                        self._save(scope,job,data,'ready')
                    if task['response'] is None:
                        if task['packet'] is None:
                            self.guard(job,scope)
                            upload(context['worker_url'],scope,self.node.provisioning_key,context['worker_verify_key'],self.bridge.public_key(scope,program['path']),'public_evaluation_keys')
                            for i,expected in enumerate(task['context']['arguments_sha256']):
                                actual=upload(context['worker_url'],scope,self.node.provisioning_key,context['worker_verify_key'],root/'input'/f'argument-{i}.cipher','ciphertext')
                                if actual!=expected:raise HEUnavailable('he4_checkpoint_integrity')
                            task['packet']=envelope(scope,self.node.provisioning_key,dict(profile=profile,circuit_sha256=program['circuit_sha256'],
                                evaluation_keys_sha256=task['context']['evaluation_keys_sha256'],arguments_sha256=task['context']['arguments_sha256'],session_id=job+'_t'+str(index),nonce='n_'+uuid.uuid4().hex))
                            # Write-ahead envelope/context before evaluation is sent.
                            self._save(scope,job,data,'sending')
                            task['response']=post(context['worker_url'],'/v1/evaluate',task['packet'],timeout=600)
                        else:
                            original=task['packet']['payload'];retrieval=envelope(scope,self.node.provisioning_key,{k:original[k] for k in ('session_id','nonce')}|dict(request_sha256=sha(wire(task['packet']))))
                            try:task['response']=post(context['worker_url'],'/v1/results',retrieval)
                            except ServiceError as error:
                                if error.code not in ('RESULT_NOT_READY','SESSION_NOT_REGISTERED','WORKER_IN_PROGRESS'):raise
                                try:task['response']=post(context['worker_url'],'/v1/resume',envelope(scope,self.node.provisioning_key,dict(request=task['packet'])),timeout=600)
                                except ServiceError as resume_error:
                                    if resume_error.code not in ('HE4_REQUEST_NOT_ADMITTED','SESSION_NOT_REGISTERED'):raise
                                    # The exact saved packet may never have been
                                    # admitted before a long authorization pause.
                                    # A fresh, purpose-bound wrapper authorizes
                                    # admission without replacing its nonce/hash.
                                    task['response']=post(context['worker_url'],'/v1/admit',envelope(scope,self.node.provisioning_key,dict(request=task['packet'],purpose=FRESH_ADMISSION)),timeout=600)
                        self._save(scope,job,data,'received')
                    signed=verify(task['response'],context['worker_verify_key']);original=task['packet']['payload']
                    expected=dict(version='he4-worker/0.1.0',tenant_id=scope.tenant_id,company_id=company,session_id=original['session_id'],nonce=original['nonce'],
                        request_sha256=sha(wire(task['packet'])),circuit_sha256=program['circuit_sha256'],result_sha256=signed.get('result_sha256'))
                    if signed!=expected or not isinstance(signed.get('result_sha256'),str):raise HEUnavailable('he4_response_binding')
                    self.guard(job,scope)
                    download(context['worker_url'],scope,self.node.provisioning_key,signed['result_sha256'],root/'result.cipher')
                    task['result']=self.bridge.decrypt(scope,program['path'],root/'result.cipher',signed['result_sha256'],root/'result.sealed',task['context'])
                except HEUnavailable as error:
                    if error.code=='he4_key_not_provisioned':
                        task['unavailable']=error.code
                    elif error.code=='he4_helper_unavailable':raise ServiceError(503,error.code)
                    else:raise
                pending['cursor']=index+1;self._save(scope,job,data,'ready')
            if r['artifact_id'] is None:
                status,legacy=200,dict(company_id=company,rows=[dict(record_id=row['record_id'],revision=row['revision'],available=False,status='unavailable',reason='artifact_missing',score=None,raw_score=None) for row in pending['plan']['rows']])
            else:status,legacy=self.legacy.result(company,header,data['legacy_job'])
            if status!=200:
                if status==409:raise HEUnavailable('he4_ml_child_failed')
                self._save(scope,job,data,'waiting_worker');return True
            data['result']=self.assemble(job,r,pending,legacy);data['pending']=None
            self._save(scope,job,data,'completed');return False
        except AuthError:
            self.store.save(scope,job,data,'waiting_authorization','AUTH_REQUIRED');return False
        except ServiceError as error:
            retry=error.status in (409,429,503) or error.code in ('WORKER_CONNECTION_UNAVAILABLE','WORKER_IN_PROGRESS','WORKER_BUSY','HE4_EXPIRED')
            self._save(scope,job,data,'retryable' if retry else 'failed',error.code);return retry
        except (HEUnavailable,ImportFailure) as error:
            self._save(scope,job,data,'failed',error.code);return False
        except Exception:
            self._save(scope,job,data,'failed','HE4_PIPELINE_INTEGRITY');return False

    @staticmethod
    def assemble(job,request,pending,legacy):
        plan=pending['plan'];ml={(r['record_id'],r['revision']):r for r in legacy['rows']}
        if set(ml)!={(r['record_id'],r['revision']) for r in plan['rows']}:raise HEUnavailable('he4_ml_row_binding')
        rows=[]
        for row in plan['rows']:
            result=deepcopy(ml[row['record_id'],row['revision']]);result['branches']={}
            for name,branch in row['branches'].items():
                public={k:deepcopy(v) for k,v in branch.items() if k not in ('requests','task_indexes')}
                executed=[pending['tasks'][i] for i in branch['task_indexes']]
                missing=next((t['unavailable'] for t in executed if t.get('unavailable')),None)
                if missing:public.update(available=False,status='unavailable',reason=missing)
                elif branch['available']:
                    public['status']='available'
                    if name=='rules':
                        outputs=[dict(role=r['role'],obligation=r['obligation'],**decode_payment(t['result'])) for r,t in zip(branch['requests'],executed)]
                        public.update(status='partial',invoice_checks=[o for o in outputs if o['role']=='row'],simultaneous_checks=[o for o in outputs if o['role']=='simultaneous_group'],matched=any(o['matched'] for o in outputs if o['role']=='row'),catalog_complete=False)
                    elif name=='statistics':
                        value=executed[0]['result']
                        if type(value) is not int or not 0<=value<=20480:raise HEUnavailable('he4_statistics_output')
                        public.update(raw_score=value/1024,score_kind='sum_clipped_robust_z',probability=False)
                    else:
                        value=np.asarray(executed[0]['result'])
                        if value.shape!=(80,) or not np.isin(value,[0,1]).all():raise HEUnavailable('he4_graph_output')
                        public.update(links_by_field=value[:64].reshape(4,4,4).tolist(),strong_reachability=value[64:].reshape(4,4).tolist())
                result['branches'][name]=public
            result['branches']['ml']=dict(available=result['available'],status='available' if result['available'] else 'unavailable',reason=result['reason'],raw_score=result['score'],model='Mahalanobis',probability=False)
            rows.append(result)
        return dict(version='he-four-branch-result/1.0.0',run_id=job,company_id=legacy['company_id'],snapshot_id=request['snapshot_id'],as_of=request['as_of'],
            status='completed',row_count=len(rows),rows=rows,plan_sha256=plan['plan_sha256'],
            aggregation=dict(available=False,score=None,reason='No approved ensemble weights or mandatory routing; four independent branches.'))
