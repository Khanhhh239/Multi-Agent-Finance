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
            if self.selection(scope) is not None:return super().submit(scope,recheck,company,header,key,body)
            import re
            from sme_fraud.import_files import fail
            from experiments.he_inference.registry_export import ReadOnlySnapshots
            if not isinstance(body,dict) or set(body)!={'snapshot_id'} or not isinstance(body['snapshot_id'],str) or not re.fullmatch('snp_[a-f0-9]{32}',body['snapshot_id']):fail(400,'HE_REQUEST_FIELDS','Chọn đúng một bản dữ liệu đã lưu.','Không gửi model hoặc khóa từ trình duyệt.')
            manifest=ReadOnlySnapshots(self.node.snapshot_db).get_snapshot(scope,body['snapshot_id'],recheck)
            if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
            return self.node.jobs.submit(company,header,key,dict(artifact_id=None,snapshot_id=body['snapshot_id'],as_of=manifest['created_at']))

    def datasets(self,scope,recheck):
        value=super().datasets(scope,recheck)
        context=self.settings.capture(scope)
        try:
            request=envelope(scope,self.node.provisioning_key,dict(challenge=secrets.token_hex(32)))
            p=verify(post(context['worker_url'],'/v1/readiness',request),context['worker_verify_key'])
            expected=dict(request['payload'],worker_verify_key=context['worker_verify_key'],builds={k:v['circuit_sha256'] for k,v in context['programs'].items()})
            if p!=expected:raise ValueError('worker build/challenge mismatch')
            value['worker_ready']=bool(value['worker_ready'])
        except Exception:value['worker_ready']=False
        absent=self.selection(scope) is None
        value['available']=(value['model_available'] or absent) and value['worker_ready']
        value['analysis_mode']='four_encrypted_branches'
        if not value['worker_ready']:value['message']='Chưa kết nối đủ bộ xử lý phân tích. Kết nối lại để tiếp tục yêu cầu đã lưu.'
        elif absent:value['message']='Nhánh ML chưa có model được chọn. Các nhánh còn lại vẫn phân tích theo nguồn khả dụng; không tự fit model.'
        elif value['model_available']:value['message']=''
        if recheck()!=scope:raise ValueError('auth context changed')
        return value
