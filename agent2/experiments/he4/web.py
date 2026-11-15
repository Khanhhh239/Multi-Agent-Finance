"""Opt-in four-branch adapter on the existing authenticated Portal routes."""
import secrets
from sme_fraud.he_workbench import HEWorkbench
from experiments.he_inference.protocol import verify
from experiments.he_inference.http_common import post
from .client_transport import envelope
from .coordinator import FourJobs,Settings


class FourWorkbench(HEWorkbench):
    def __init__(self,node,bindings,config):
        self.settings=Settings(config)
        self.legacy=node.jobs
        node.jobs=FourJobs(node,self.settings)
        super().__init__(node,bindings)

    def selection(self,scope):
        binding=self.settings.capture(scope)['binding']
        return binding.get('ml_artifact_id') or super().selection(scope)

    def submit(self,scope,recheck,company,header,key,body):
        with self.settings.mutation_lock:
            import re
            from finance_input.json_io import loads
            from sme_fraud.import_files import fail
            from experiments.he_inference.registry_export import ReadOnlySnapshots
            if not isinstance(body,dict) or set(body)!={'snapshot_id'} or not isinstance(body['snapshot_id'],str) or not re.fullmatch('snp_[a-f0-9]{32}',body['snapshot_id']):fail(400,'HE_REQUEST_FIELDS','Chọn đúng một bản dữ liệu đã lưu.','Không gửi model hoặc khóa từ trình duyệt.')
            manifest=ReadOnlySnapshots(self.node.snapshot_db).get_snapshot(scope,body['snapshot_id'],recheck)
            if manifest.get('contract_version')=='agent2-rule-snapshot/1.0.0':
                if not getattr(self.settings,'supports_rule_snapshot',False):fail(422,'HE_PROFILE_UNSUPPORTED','Bản dữ liệu nguồn 35 luật chưa hỗ trợ phân tích mã hóa HE.','Dùng cấu hình he4-enterprise/1.1.0 đã nối P1, C3, B1 và B5/E4.')
                data=loads(ReadOnlySnapshots(self.node.snapshot_db).get_snapshot(scope,body['snapshot_id'],recheck,data=True))
                if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
                return self.node.jobs.submit(company,header,key,dict(artifact_id=None,snapshot_id=body['snapshot_id'],as_of=data['source']['as_of']))
            if self.selection(scope) is not None:return super().submit(scope,recheck,company,header,key,body)
            if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
            return self.node.jobs.submit(company,header,key,dict(artifact_id=None,snapshot_id=body['snapshot_id'],as_of=manifest['created_at']))

    def datasets(self,scope,recheck):
        from finance_input.json_io import loads
        from finance_input.validation import stamp
        from experiments.he_inference.registry_export import ReadOnlySnapshots
        value=super().datasets(scope,recheck)
        context=self.settings.capture(scope)
        try:
            request=envelope(scope,self.node.provisioning_key,dict(challenge=secrets.token_hex(32)))
            p=verify(post(context['worker_url'],'/v1/readiness',request),context['worker_verify_key'])
            expected=dict(request['payload'],worker_verify_key=context['worker_verify_key'],builds={k:v['circuit_sha256'] for k,v in context['programs'].items()})
            if p!=expected:raise ValueError('worker build/challenge mismatch')
            value['worker_ready']=bool(value['worker_ready'])
        except Exception:value['worker_ready']=False
        if getattr(self.settings,'supports_rule_snapshot',False):
            store=ReadOnlySnapshots(self.node.snapshot_db)
            rule_rows=[]
            with store._transaction(scope,recheck) as conn:
                tenant,company,_=store._scope(scope)
                ids=[r[0] for r in conn.execute('SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? ORDER BY rowid DESC',(tenant,company))]
                for sid in ids:
                    manifest,raw=store._read_snapshot(conn,scope,sid)
                    if manifest.get('contract_version')!='agent2-rule-snapshot/1.0.0':continue
                    data=loads(raw);txs=data['source']['tables'].get('transactions',[])
                    events=sorted((str(t['posted_at']) for t in txs if t.get('posted_at')),key=stamp)
                    rule_rows.append(dict(snapshot_id=sid,created_at=manifest['created_at'],checksum=manifest['checksum'],
                        contract_version='agent2-rule-snapshot/1.0.0',record_count=len(data['candidate_transaction_ids']),
                        period_start=events[0] if events else data['source']['as_of'],period_end=events[-1] if events else data['source']['as_of'],
                        as_of=data['source']['as_of'],simulated_records=sum(bool(t.get('is_simulated')) for t in txs),
                        he_supported_rules=['P1','C3','B1','B5','E4']))
                    if len(rule_rows)>=100:break
            if rule_rows:
                merged=sorted(list(value['datasets'])+rule_rows,key=lambda d:(str(d.get('created_at','')),d.get('snapshot_id','')),reverse=True)
                if len(merged)>100:value['limited']=True
                value['datasets']=merged[:100]
            value['rule_snapshot_he_supported']=True
            value['he_covered_rules']=['P1','C3','B1','B5','E4']
        absent=self.selection(scope) is None
        has_rule_snap=any(d.get('contract_version')=='agent2-rule-snapshot/1.0.0' for d in value['datasets'])
        value['available']=(value['model_available'] or absent or (getattr(self.settings,'supports_rule_snapshot',False) and has_rule_snap)) and value['worker_ready']
        value['analysis_mode']='rule_snapshot_and_four_branches' if getattr(self.settings,'supports_rule_snapshot',False) else 'four_encrypted_branches'
        if not value['worker_ready']:value['message']='Chưa kết nối đủ bộ xử lý phân tích. Kết nối lại để tiếp tục yêu cầu đã lưu.'
        elif getattr(self.settings,'supports_rule_snapshot',False) and has_rule_snap and absent:value['message']='Sẵn sàng chạy HE 4 nhóm luật (P1, C3, B1, B5/E4) trên snapshot 35 luật; nhánh ML chưa cấu hình model.'
        elif absent:value['message']='Nhánh ML chưa có model được chọn. Các nhánh còn lại vẫn phân tích theo nguồn khả dụng; không tự fit model.'
        elif value['model_available']:value['message']=''
        if recheck()!=scope:raise ValueError('auth context changed')
        return value
