"""Pinned release qualification and staging execution; no production-policy defaults.

The supported executor is an enterprise, read-only detector shadow. It is NOT
the HE cloud executor or a case-delivery pipeline. Open governance decisions
and that missing production executor deliberately block production activation.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import time
from finance_input.json_io import loads
from .import_files import canonical,digest,ImportFailure
from .pipeline_release_store import ensure
from .analysis_resources import AnalysisResources,VERSION as BINDING_VERSION
from . import release_shadow_plan as shadow_plan

VERSION='pipeline-release-bundle/1.0.0'
PROFILE='snapshot_detector_shadow/1.0.0'
SLOTS=('rules','graph','feature_contract','preprocess','models','reference','normalization','calibration',
       'ensemble','fallback','grouping','thresholds','budget','mandatory_routing','backlog','documents','runtime','he')
OPEN_DECISIONS=('D-04','D-05','D-06','D-07','D-09','D-17','D-18','D-19')
ROOT=Path(__file__).parent


def runtime_signature():
    import finance_input
    import sqlite3
    from importlib.metadata import version
    from .method_adapters import _versions
    # This conservative signature includes transitively used business/feature/release
    # modules. A code update requires a new qualification; never just a git branch.
    code={p.name:digest(p.read_bytes()) for p in sorted(ROOT.glob('*.py'))}
    shared=Path(finance_input.__file__).parent
    shared_code={p.relative_to(shared).as_posix():digest(p.read_bytes()) for p in sorted(shared.rglob('*')) if p.suffix in ('.py','.json')}
    schemas={p.name:digest(p.read_bytes()) for p in sorted(ROOT.glob('*.schema.json'))}
    return dict(profile=PROFILE,code=code,schemas=schemas,shared_input=shared_code,method_runtime=_versions(),
                metadata_runtime=dict(cryptography=version('cryptography'),sqlite=sqlite3.sqlite_version),
                key_requirement='none: enterprise clear shadow; no key or HE fallback',
                state_migrations='none; release store is separate from business stores')


def feature_contract(native):
    if native:from .rule_snapshot_features import feature_contract as contract
    else:from .snapshot_features import feature_contract as contract
    return contract()


def rule_parameters(native):
    # native_rule_node.evaluate_bundle executes DEFAULT_CONFIG, not source config.
    if native:
        from .rules import DEFAULT_CONFIG
        return loads(canonical(DEFAULT_CONFIG))
    return {}


class FrozenResources(AnalysisResources):
    def __init__(self,model_db,selection):
        super().__init__(model_db);self.frozen=loads(canonical(selection))

    def selection(self,scope):
        ensure((scope.tenant_id,next(iter(scope.company_ids)))==(self.frozen['tenant_id'],self.frozen['company_id']),
               'RELEASE_SCOPE','Model binding nằm ngoài doanh nghiệp.',403)
        return loads(canonical(self.frozen)),None


class ReleaseService:
    def __init__(self,store,snapshots,resources=None,case_queue=None):
        self.store=store;self.snapshots=snapshots;self.resources=resources or AnalysisResources();self.case_queue=case_queue
        from .bundle_reviews import BundleWorkspace
        self.workspace=BundleWorkspace(self)

    def register_plan(self,scope,package,key,recheck=None):
        """Trusted enterprise producer/CLI only. No HTTP upload of scores or policies."""
        selected=package.get('model_selection',{});contract=feature_contract(True)
        ensure(isinstance(selected,dict) and set(selected)=={'version','tenant_id','company_id','statistics_artifact_id','ml_artifacts'} and
               selected['version']==BINDING_VERSION and (selected['tenant_id'],selected['company_id'])==(scope.tenant_id,next(iter(scope.company_ids))),
               'RELEASE_SCOPE','Model selection của gói ngoài phạm vi hoặc không đúng contract.',403)
        models,_,_=self._models(scope,selected,contract,recheck)
        shadow_plan.validate_package(package,scope,models,contract)
        from .validation_study import _check_manifest_pins
        from .snapshot_features import utc
        manifests={}
        for s in package['evaluation_plan']['snapshots']:
            manifest,data=self._snapshot(scope,s['snapshot_id'],recheck)
            ensure('source' in data and utc(data['source']['as_of'])==utc(s['as_of']),'RELEASE_STUDY_CUTOFF','Cutoff validation không khớp nguồn snapshot bất biến.')
            manifests[s['split']]=dict(manifest,as_of=data['source']['as_of'])
        _check_manifest_pins(package['evaluation_plan'],manifests)
        request_hash=digest(canonical(dict(action='register_plan',package=package)))
        with self.store.tx(scope,recheck) as c:
            prior=self.store.receipt(c,scope,key,request_hash)
            if prior:return prior
            oid=self.store.put(c,scope,'artifact',dict(slot='validation_study',value=package))
            value=dict(plan_id=oid,study_result_sha256=package['study']['study_result_sha256'],production_ready=False)
            self.store.receipt(c,scope,key,request_hash,value)
        return value

    @classmethod
    def from_config(cls,path,snapshots,resources):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from experiments.he_inference.key_manager import PROVIDER,load_key
        from .pipeline_release_store import ReleaseStore
        cfg=loads(Path(path).read_bytes())
        ensure(isinstance(cfg,dict) and set(cfg)=={'version','release_db','node_state_key_file'} and
               cfg['version']=='pipeline-release-runtime/1.0.0','RELEASE_CONFIG','Cấu hình release server không hợp lệ.',503)
        wrapping=load_key(cfg['node_state_key_file'],required_provider=PROVIDER).material
        job_keys=HKDF(algorithm=hashes.SHA256(),length=64,salt=b'he-node-jobs-v1',info=b'enterprise-storage-and-idempotency').derive(wrapping)
        key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-pipeline-release-v1',info=b'enterprise-release-storage').derive(job_keys[32:])
        return cls(ReleaseStore(cfg['release_db'],key),snapshots,resources)

    def _snapshot(self,scope,sid,recheck=None):
        ensure(self.snapshots is not None,'RELEASE_SNAPSHOTS_UNAVAILABLE','Chưa cấu hình kho snapshot.',503)
        m=self.snapshots.get_snapshot(scope,sid,recheck)
        raw=self.snapshots.get_snapshot(scope,sid,recheck,data=True)
        ensure(digest(raw)==m['data_checksum'],'RELEASE_SNAPSHOT_INTEGRITY','Checksum snapshot không khớp.',503)
        return m,loads(raw)

    def _models(self,scope,selection,contract,recheck=None):
        from .method_store import MethodStore
        from .method_adapters import _versions,ARTIFACT_VERSION
        from .method_preprocess import VERSION as PREPROCESS
        from .method_preprocess import validate_preprocess
        pins=dict(robust_z=selection['statistics_artifact_id'],**selection['ml_artifacts'])
        models={};preprocess={};reference={}
        for method,identity in pins.items():
            if identity is None:continue
            ensure(self.resources.model_db is not None,'RELEASE_MODEL_STORE','Chưa cấu hình kho model đã ghim.',503)
            artifact=MethodStore(self.resources.model_db,read_only=True).get_artifact(scope,identity,recheck)
            m=loads(artifact.manifest)
            ensure(m['version']==ARTIFACT_VERSION and m['method_id']==method and m['feature_contract']==contract
                   and m['versions']==_versions() and m['preprocess_version']==PREPROCESS,
                   'RELEASE_MODEL_INCOMPATIBLE','Model không khớp feature contract hoặc runtime đã chọn.')
            # Validate preprocessing metadata without deserializing any HTTP model.
            ensure(m['preprocess']['selected_columns']==m['selected_columns'] and
                   digest(canonical(m['preprocess']))==m['preprocess_sha256'],
                   'RELEASE_MODEL_INCOMPATIBLE','Preprocess model không toàn vẹn.')
            try:validate_preprocess(dict(contract=contract),m['preprocess'])
            except (ValueError,TypeError,KeyError):ensure(False,'RELEASE_MODEL_INCOMPATIBLE','Preprocess model không đúng contract đã khóa.')
            models[method]=dict(artifact_id=identity,manifest_sha256=digest(artifact.manifest),payload_sha256=digest(artifact.payload),
                                model_version=m['model_version'],feature_contract_fingerprint=m['feature_contract_fingerprint'])
            preprocess[method]=m['preprocess']
            reference[method]={k:m[k] for k in ('reference_version','reference_binding','reference_start','reference_end')}
        return models,preprocess,reference

    def prepare(self,scope,snapshot_id,name,key,recheck=None,*,plan_id=None):
        ensure(isinstance(name,str) and 1<=len(name.strip())<=160,'RELEASE_NAME','Tên phiên bản dài tối đa 160 ký tự.',400)
        request_hash=digest(canonical(dict(action='prepare',snapshot_id=snapshot_id,name=name,plan_id=plan_id)))
        # Resolve only trusted snapshots/MethodStore, never accept arbitrary binaries,
        # paths, executable configuration, secrets or caller asserted gate results.
        with self.store.tx(scope,recheck) as c:
            prior=self.store.receipt(c,scope,key,request_hash)
            if prior:return dict(bundle_id=prior['bundle_id'],bundle=self.store.read(c,scope,prior['bundle_id'],'bundle'))
        manifest,data=self._snapshot(scope,snapshot_id,recheck)
        native='source' in data
        contract=feature_contract(native)
        selected,error=self.resources.selection(scope)
        package=None
        if plan_id is not None:
            artifact=self.store.get(scope,plan_id,'artifact',recheck)
            ensure(artifact['slot']=='validation_study','RELEASE_PLAN_CONTRACT','Artifact không phải validation/policy plan.')
            ensure(native,'RELEASE_PLAN_SOURCE','Profile case shadow cần snapshot nguồn 35 luật.')
            package=artifact['value'];selected=package['model_selection'];error=None
        ensure(error in (None,'binding_missing'),'RELEASE_BINDING_INVALID','Cấu hình ghim model không hợp lệ.')
        models,preprocess,reference=self._models(scope,selected,contract,recheck)
        if package is not None:shadow_plan.validate_package(package,scope,models,contract)
        rules=dict(profile='native_35_rules' if native else 'canonical_P1_E3',
                   parameters=rule_parameters(native),
                   source_contract=manifest['contract_version'])
        values=dict(rules=rules,graph=dict(profile='point_in_time_entity_graph',implementation='method_adapters._graph / rule_snapshot_features.build_rule_entity_graphs',
                    routing='context_and_evidence_only'),feature_contract=contract,preprocess=preprocess,models=dict(selection=selected,artifacts=models),
                    reference=reference,runtime=runtime_signature())
        reasons={
            'normalization':'Empirical ranks của từng model nằm trong manifest đã ghim; chưa chuẩn hóa điểm chung.',
            'calibration':'Chưa có calibration được phê duyệt; điểm chỉ dùng ưu tiên, không là xác suất gian lận.',
            'ensemble':'Chưa có ensemble qua validation và phê duyệt nghiệp vụ.',
            'fallback':'Giữ unavailable và lý do từng nhánh; không tự chọn model khác hoặc tự fit.',
            'grouping':'Executor này không tạo hoặc gộp vụ nghiệp vụ.',
            'thresholds':'Không áp ngưỡng phát hành cảnh báo trong shadow này.',
            'budget':'Không tiêu ngân sách, không đổi quota hoặc ledger giao nhận.',
            'mandatory_routing':'Chưa có chính sách bắt buộc được duyệt cho executor này.',
            'backlog':'Không ghi hoặc gửi lại backlog từ shadow này.',
            'documents':'Chứng từ nguồn thuộc snapshot bất biến; không thay chính sách R4.',
            'he':'Không chạy cloud/HE trong executor staging này; không gửi dữ liệu rõ lên cloud.'}
        if package is not None:
            compiled=shadow_plan.compile_values(package);values.update(compiled)
            reasons={k:v for k,v in reasons.items() if k not in compiled}
        with self.store.tx(scope,recheck) as c:
            prior=self.store.receipt(c,scope,key,request_hash)
            if prior:return dict(bundle_id=prior['bundle_id'],bundle=self.store.read(c,scope,prior['bundle_id'],'bundle'))
            components={slot:dict(artifact_id=self.store.put(c,scope,'artifact',dict(slot=slot,value=value))) for slot,value in values.items()}
            components.update({s:dict(unused=True,reason=r) for s,r in reasons.items()})
            bundle=dict(version='pipeline-release-bundle/1.1.0' if package else VERSION,name=name,score_semantics='ranking_only',components=components,
                        tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids)),profile=shadow_plan.PROFILE if package else PROFILE,
                        qualification_snapshot={k:manifest[k] for k in ('snapshot_id','checksum','data_checksum','contract_version')},
                        created_at=self.store.now(),created_by=scope.actor_id)
            oid=self.store.put(c,scope,'bundle',bundle)
            self.store.receipt(c,scope,key,request_hash,dict(bundle_id=oid))
            return dict(bundle_id=oid,bundle=bundle)

    def _values(self,c,scope,bundle_id):
        bundle=self.store.read(c,scope,bundle_id,'bundle')
        linked=bundle['profile']==shadow_plan.PROFILE
        ensure(bundle['version']==('pipeline-release-bundle/1.1.0' if linked else VERSION) and bundle['profile'] in (PROFILE,shadow_plan.PROFILE)
               and set(bundle['components'])==set((*SLOTS,'validation_study') if linked else SLOTS),
               'RELEASE_BUNDLE_CONTRACT','Bundle không đúng contract hoặc executor.')
        ensure(bundle['tenant_id']==scope.tenant_id and bundle['company_id']==next(iter(scope.company_ids)),
               'RELEASE_SCOPE','Bundle nằm ngoài doanh nghiệp.',403)
        values={}
        for slot,item in bundle['components'].items():
            if 'artifact_id' in item:
                artifact=self.store.read(c,scope,item['artifact_id'],'artifact')
                ensure(artifact['slot']==slot,'RELEASE_COMPONENT_SLOT','Thành phần bị gắn sai vị trí.')
                values[slot]=artifact['value']
        return bundle,values

    def _revocation(self,c,scope,ids):
        for identity in ids:
            ensure(c.execute('SELECT 1 FROM revoked WHERE owner=? AND id=?',(self.store.owner(scope),identity)).fetchone() is None,
                   'RELEASE_REVOKED','Bundle, thành phần, gate hoặc phê duyệt đã bị thu hồi.')

    def _compatible(self,c,scope,bundle_id,recheck=None):
        bundle,values=self._values(c,scope,bundle_id)
        self._revocation(c,scope,[bundle_id,*[v['artifact_id'] for v in bundle['components'].values() if 'artifact_id' in v]])
        ensure(values['runtime']==runtime_signature(),'RELEASE_RUNTIME_CHANGED','Code/runtime đã đổi; cần qualification bundle mới.')
        contract=feature_contract(values['rules']['profile']=='native_35_rules')
        ensure(contract==values['feature_contract'],'RELEASE_FEATURE_CHANGED','Feature contract đã đổi.')
        models,prep,refs=self._models(scope,values['models']['selection'],contract,recheck)
        ensure(models==values['models']['artifacts'] and prep==values['preprocess'] and refs==values['reference'],
               'RELEASE_MODEL_CHANGED','Model, reference hoặc preprocess không khớp checksum đã ghim.')
        if bundle['profile']==shadow_plan.PROFILE:
            shadow_plan.validate_package(values['validation_study'],scope,models,contract)
            for slot,value in shadow_plan.compile_values(values['validation_study']).items():
                ensure(values.get(slot)==value,'RELEASE_PLAN_BINDING','Policy/validation component không khớp gói đã khóa.')
        return bundle,values

    def _execute(self,scope,bundle,values,snapshot_id,as_of,recheck=None):
        manifest,data=self._snapshot(scope,snapshot_id,recheck)
        native='source' in data
        ensure(manifest['contract_version']==values['rules']['source_contract'] and
               native==(values['rules']['profile']=='native_35_rules') and
               rule_parameters(native)==values['rules']['parameters'],
               'RELEASE_SOURCE_CONFIG_MISMATCH','Nguồn hoặc tham số luật không khớp bundle đã ghim.')
        from .snapshot_analysis import analyze_snapshot
        result=analyze_snapshot(self.snapshots,scope,snapshot_id,as_of,technical=True,recheck=recheck,
                               resources=FrozenResources(self.resources.model_db,values['models']['selection']))
        if native:
            candidates=set(data['candidate_transaction_ids'])
            expected={(r['transaction_id'],r.get('revision',1)) for r in data['source']['tables']['transactions'] if r['transaction_id'] in candidates}
        else:
            from .snapshot_features import build_from_snapshot
            frame=build_from_snapshot(self.snapshots,scope,snapshot_id,as_of,recheck)
            expected={(r['record_id'],r['revision']) for r in frame['rows']}
        ensure(len(result['rows'])==len(expected) and {(r['transaction_id'],r['revision']) for r in result['rows']}==expected,
               'RELEASE_ROW_COMPLETENESS','Executor không trả đủ định danh giao dịch.')
        if bundle['profile']==shadow_plan.PROFILE:
            result['pipeline']=shadow_plan.score_and_coalesce(scope,result,manifest,data,values['validation_study'],
                'rbun_'+digest(canonical(bundle)))
        return result

    def qualify(self,scope,bundle_id,lane,recheck=None,*,key=None):
        ensure(lane in ('staging','production'),'RELEASE_LANE','Chọn staging hoặc production.',400)
        receipt_hash=digest(canonical(dict(action='qualify',bundle_id=bundle_id,lane=lane)))
        if key is not None:
            with self.store.tx(scope,recheck,write=False) as c:
                prior=self.store.receipt(c,scope,key,receipt_hash)
                if prior:return dict(gate_id=prior['gate_id'],**self.store.read(c,scope,prior['gate_id'],'gate'))
        gates=[]
        def add(name,expected,observed,status,evidence=None):
            gates.append(dict(name=name,expected=expected,observed=observed,status=status,evidence=evidence or [],approver=None))
        compatible=False;values=None;bundle=None
        with self.store.tx(scope,recheck,write=False) as c:
            try:bundle,values=self._compatible(c,scope,bundle_id,recheck);compatible=True
            except ImportFailure as error:
                # Unknown/cross-company IDs must be 404, not an oracle gate report.
                if error.status in (403,404):raise
                add('compatibility','Exact code, feature, model, reference and component checksums',error.code,'fail')
        if compatible:add('compatibility','Exact code, feature, model, reference and component checksums','All configured pins match','pass',[bundle_id])
        technical=None;elapsed=None
        if compatible:
            try:
                sid=bundle['qualification_snapshot']['snapshot_id'];manifest,data=self._snapshot(scope,sid,recheck)
                ensure(all(manifest[k]==v for k,v in bundle['qualification_snapshot'].items()),'RELEASE_SOURCE_CHANGED','Snapshot qualification không khớp.')
                # Canonical snapshot cutoff is explicitly taken from supplied source
                # records. This is a smoke check, not an out-of-time quality study.
                as_of=data['source']['as_of'] if 'source' in data else max(r['observed_at'] for r in data['transactions'])
                started=time.monotonic();technical=self._execute(scope,bundle,values,sid,as_of,recheck);elapsed=time.monotonic()-started
                add('technical','Real enterprise detector smoke: return every candidate, preserve unavailable',
                    dict(rows=len(technical['rows']),analysis_id=technical['analysis_id'],elapsed_seconds=elapsed,
                         result_sha256=digest(canonical(technical)),scope='smoke_only; not R1-R5 regression',
                         preview_case_count=len(technical.get('pipeline',{}).get('cases',[])),queue_written=False), 'pass',[sid])
            except ImportFailure as error:add('technical','Real enterprise detector smoke',error.code,'fail')
        else:add('technical','Compatible immutable bundle','Compatibility failed','blocked')
        study=values.get('validation_study',{}).get('study') if values else None
        add('quality','Approved D-09 study: same snapshot/period/budget, verified outcomes and uncertainty',
            dict(status='unapproved_study_linked' if study else 'unknown',precision=None,recall=None,useful_increment=None,review_minutes=None,
                 study_result_sha256=study['study_result_sha256'] if study else None,
                 selected_arm=study['detector_validation']['selected_arm_id'] if study else None,
                 measured_shadow_comparison=study['sealed_future_test']['selected_arm_summary'] if study else None,
                 reason='Linked study is not a production approval; synthetic outcomes do not prove business effectiveness'), 'blocked',
            [bundle['components']['validation_study']['artifact_id']] if study else [])
        add('operations','Restart-safe release metadata; full delivery/recovery/HE evidence required for production',
            dict(release_store='AES-GCM; durable SQLite CAS/receipts/pins',
                 full_pipeline_recovery='not_qualified',he_executor='not_used',scope='release_metadata_only'),
            ('pass' if not study or self.case_queue is not None else 'fail') if lane=='staging' else 'blocked')
        add('approval','Explicit unexpired director approval of exact bundle, lane and gate',
            'Approval must be created separately; shared workspace login does not identify a named reviewer','blocked')
        add('production_policy','Closed D-04/05/06/07/09/17/18/19 and approved full production executor',
            dict(open_decisions=list(OPEN_DECISIONS),executor=bundle['profile'] if bundle else PROFILE,production_executor=False), 'blocked')
        report=dict(version='pipeline-release-gate/1.0.0',bundle_id=bundle_id,lane=lane,created_at=self.store.now(),
                    requested_by=scope.actor_id,gates=gates,technical_ready=all(g['status']=='pass' for g in gates if g['name'] in ('compatibility','technical','operations')),
                    production_ready=False,scope='enterprise_detector_staging_only')
        with self.store.tx(scope,recheck) as c:
            if key is not None:
                prior=self.store.receipt(c,scope,key,receipt_hash)
                if prior:return dict(gate_id=prior['gate_id'],**self.store.read(c,scope,prior['gate_id'],'gate'))
            oid=self.store.put(c,scope,'gate',report)
            if key is not None:self.store.receipt(c,scope,key,receipt_hash,dict(gate_id=oid))
        return dict(gate_id=oid,**report)

    def approve(self,scope,bundle_id,gate_id,lane,reason,recheck=None,*,key=None):
        ensure(lane=='staging','RELEASE_PRODUCTION_BLOCKED','Chưa có gate/policy đủ để duyệt production.')
        ensure(isinstance(reason,str) and 10<=len(reason.strip())<=1000,'RELEASE_REASON','Cần lý do phê duyệt rõ ràng.',400)
        receipt_hash=digest(canonical(dict(action='approve',bundle_id=bundle_id,gate_id=gate_id,lane=lane,reason=reason)))
        with self.store.tx(scope,recheck) as c:
            if key is not None:
                prior=self.store.receipt(c,scope,key,receipt_hash)
                if prior:return dict(approval_id=prior['approval_id'],**self.store.read(c,scope,prior['approval_id'],'approval'))
            self._compatible(c,scope,bundle_id,recheck);gate=self.store.read(c,scope,gate_id,'gate')
            ensure(gate['bundle_id']==bundle_id and gate['lane']==lane and gate['technical_ready'],
                   'RELEASE_GATE_BLOCKED','Gate không đạt hoặc không thuộc đúng bundle/lane.')
            self._revocation(c,scope,[gate_id])
            now=self.store.clock().astimezone(timezone.utc)
            ensure(now-datetime.fromisoformat(gate['created_at'])<=timedelta(hours=24),'RELEASE_GATE_EXPIRED','Gate quá 24 giờ; cần kiểm lại.')
            value=dict(bundle_id=bundle_id,gate_id=gate_id,lane=lane,actor_id=scope.actor_id,reason=reason,
                       created_at=now.isoformat(),expires_at=(now+timedelta(hours=24)).isoformat(),
                       identity_assurance='server_authorized_director; may be shared workspace',scope='technical_staging_only')
            oid=self.store.put(c,scope,'approval',value)
            if key is not None:self.store.receipt(c,scope,key,receipt_hash,dict(approval_id=oid))
        return dict(approval_id=oid,**value)

    def switch(self,scope,body,key,recheck=None):
        lane=body['lane'];bundle_id=body['bundle_id'];gate_id=body['gate_id'];approval_id=body['approval_id']
        def guard(c):
            ensure(lane=='staging','RELEASE_PRODUCTION_BLOCKED','Production còn thiếu gate nghiệp vụ và executor đầy đủ.')
            target,target_values=self._compatible(c,scope,bundle_id,recheck)
            active=self.store.pointer(c,scope,lane)
            if active.get('bundle_id'):
                previous,previous_values=self._values(c,scope,active['bundle_id'])
                if target['profile']==previous['profile']==shadow_plan.PROFILE:
                    ensure(target_values['budget']['period_kind']==previous_values['budget']['period_kind'],
                           'RELEASE_BUDGET_PERIOD_MIGRATION','Đổi loại kỳ ngân sách cần kế hoạch chuyển kỳ riêng; không được reset quota bằng release/rollback.')
            self._revocation(c,scope,[gate_id,approval_id])
            gate=self.store.read(c,scope,gate_id,'gate');approval=self.store.read(c,scope,approval_id,'approval')
            ensure(gate['bundle_id']==bundle_id and gate['lane']==lane and gate['technical_ready'] and
                   all(approval[k]==v for k,v in dict(bundle_id=bundle_id,gate_id=gate_id,lane=lane).items()),
                   'RELEASE_APPROVAL_MISMATCH','Phê duyệt/gate không khớp bundle/lane.')
            now=self.store.clock().astimezone(timezone.utc)
            ensure(now<datetime.fromisoformat(approval['expires_at']) and
                   now-datetime.fromisoformat(gate['created_at'])<=timedelta(hours=24),
                   'RELEASE_APPROVAL_EXPIRED','Phê duyệt hoặc gate hết hạn; cần kiểm lại và duyệt mới.')
        return self.store.switch(scope,lane,bundle_id,approval_id,gate_id,body['expected_revision'],body['reason'],key,body['action'],guard,recheck)

    def run(self,scope,run_id,lane,snapshot_id,as_of,recheck=None,*,execution_mode='enterprise_local_only',require_case_profile=False):
        ensure(lane=='staging','RELEASE_PRODUCTION_BLOCKED','Executor này chỉ chạy shadow tại doanh nghiệp.')
        # This bundle executor is explicitly local. Cloud HE remains a separate
        # authenticated, build-pinned runtime until a compatible bundle adapter
        # exists; never route a ciphertext request into analyze_snapshot/joblib.
        ensure(execution_mode=='enterprise_local_only','PIPELINE_HE_UNAVAILABLE',
               'Bundle này chưa có executor HE tương thích; không chấm dữ liệu rõ thay cho yêu cầu cloud mã hóa.')
        request=dict(snapshot_id=snapshot_id,as_of=as_of)
        pin=self.store.pin(scope,run_id,lane,request,recheck)
        # A successful retry returns the exact stored result, never recomputes with
        # a new pointer or creates delivery/budget side effects.
        with self.store.tx(scope,recheck,write=False) as c:
            prior=c.execute('SELECT object_id FROM audit WHERE owner=? AND kind=? ORDER BY seq DESC',(self.store.owner(scope),'observation')).fetchall()
            for row in prior:
                value=self.store.read(c,scope,row['object_id'],'observation')
                if value['pin_id']==pin['pin_id']:return dict(observation_id=row['object_id'],**value)
            bundle,values=self._compatible(c,scope,pin['bundle_id'],recheck)
            ensure(not require_case_profile or bundle['profile']==shadow_plan.PROFILE,'PIPELINE_CASE_PROFILE_REQUIRED','Phiên bản đang chọn chưa có luồng gộp vụ và phiếu rà.')
        # Commit deterministic execution BEFORE any queue reservation. This bridges
        # two SQLite stores using immutable checkpoint + queue idempotency receipt.
        execution=None
        with self.store.tx(scope,recheck,write=False) as c:
            for row in c.execute('SELECT object_id FROM audit WHERE owner=? AND kind=?',(self.store.owner(scope),'execution')).fetchall():
                saved=self.store.read(c,scope,row['object_id'],'execution')
                if saved['pin_id']==pin['pin_id']:execution=saved;break
        if execution is None:
            started=time.monotonic();result=self._execute(scope,bundle,values,snapshot_id,as_of,recheck)
            execution=dict(pin_id=pin['pin_id'],result=result,elapsed_seconds=time.monotonic()-started)
            with self.store.tx(scope,recheck) as c:
                self._compatible(c,scope,pin['bundle_id'],recheck)
                for row in c.execute('SELECT object_id FROM audit WHERE owner=? AND kind=?',(self.store.owner(scope),'execution')).fetchall():
                    saved=self.store.read(c,scope,row['object_id'],'execution')
                    if saved['pin_id']==pin['pin_id']:execution=saved;break
                else:self.store.put(c,scope,'execution',execution)
        result=loads(canonical(execution['result']));elapsed=execution['elapsed_seconds']
        result['execution']=dict(location=execution_mode,cloud_he=dict(available=False,reason='bundle_he_executor_unavailable'),
            cloud_branches={name:dict(available=False,status='unavailable',reason='bundle_he_executor_unavailable') for name in ('rules','statistics','graph','ml')},
            plaintext_cloud_upload=False)
        if 'pipeline' in result:
            ensure(self.case_queue is not None,'RELEASE_QUEUE_UNAVAILABLE','Chưa cấu hình kho case shadow.',503)
            with self.store.tx(scope,recheck,write=False) as c:self._compatible(c,scope,pin['bundle_id'],recheck)
            pipeline=result['pipeline'];pipeline['case_bundle']['snapshot_binding'].update(run_id=run_id);queue_started=time.monotonic()
            pipeline['queue']=self.case_queue.evaluate_and_enqueue(scope,pipeline['case_bundle'],mode='shadow',period_key=pipeline['period_key'],
                policy=pipeline['case_policy'],idempotency_key='release-'+pin['pin_id'],recheck=recheck)
            pipeline['queue_processing_seconds']=time.monotonic()-queue_started
        # Recheck pinned artifacts, not the active pointer, before committing result.
        with self.store.tx(scope,recheck) as c:
            self._compatible(c,scope,pin['bundle_id'],recheck)
            if 'pipeline' in result:
                from .bundle_reviews import build_packet
                manifest,data=self._snapshot(scope,snapshot_id,recheck)
                packet=build_packet(scope,pin,result,manifest,data)
                result['pipeline']['review_packet_id']=self.store.put(c,scope,'review_packet',packet)
            metrics=self.metrics(result,elapsed)
            value=dict(pin_id=pin['pin_id'],run_id=run_id,bundle_id=pin['bundle_id'],lane=lane,snapshot_id=snapshot_id,
                       as_of=as_of,created_at=self.store.now(),metrics=metrics,result=result)
            # Serialize concurrent completions and return the first persisted result.
            for row in c.execute('SELECT object_id FROM audit WHERE owner=? AND kind=?',(self.store.owner(scope),'observation')).fetchall():
                old=self.store.read(c,scope,row['object_id'],'observation')
                if old['pin_id']==pin['pin_id']:return dict(observation_id=row['object_id'],**old)
            oid=self.store.put(c,scope,'observation',value)
        return dict(observation_id=oid,**value)

    @staticmethod
    def metrics(result,elapsed):
        rows=result['rows'];branches={}
        for name in ('rules','statistics','graph','ml'):
            available=sum(r.get('branches',{}).get(name,{}).get('available') is True for r in rows)
            branches[name]=dict(available=available,total=len(rows),availability_rate=available/len(rows) if rows else None)
        pipeline=result.get('pipeline');queue=(pipeline or {}).get('queue',{});decisions=queue.get('decisions',[])
        all_35_ok=0;partial_35=0;unavail_35=0;alert_35=0
        for r in rows:
            cov=(r.get('rule_coverage') or {}).get('summary')
            if isinstance(cov,dict):
                has_hit=cov.get('evaluated_hit',0)>0;has_eval=(cov.get('evaluated_hit',0)+cov.get('evaluated_no_hit',0))>0
                if has_hit:alert_35+=1
                if cov.get('unavailable',0)==0 and has_eval:all_35_ok+=1
                elif has_eval:partial_35+=1
                else:unavail_35+=1
        p_rows=(pipeline or {}).get('rows') or []
        fb_counts={};unavail_reasons={}
        for pr in p_rows:
            fid=pr.get('fallback_id')
            if fid:fb_counts[fid]=fb_counts.get(fid,0)+1
            if not pr.get('available'):
                rc=str(((pr.get('reason') or {}).get('code')) or 'unavailable')
                unavail_reasons[rc]=unavail_reasons.get(rc,0)+1
        return dict(elapsed_seconds=elapsed,branches=branches,
                    rule35_coverage=dict(total_rows=len(rows),all_applicable_evaluated_rows=all_35_ok,
                                         partial_source_gap_rows=partial_35,all_unavailable_rows=unavail_35,
                                         actionable_alert_rows=alert_35),
                    fallback_summary=dict(total_rows=len(p_rows),
                                          selected_arm_complete_count=sum(bool(r.get('is_selected_arm_complete')) for r in p_rows),
                                          fallback_used_count=sum(r.get('fallback_id') is not None for r in p_rows),
                                          unavailable_count=sum(not r.get('available') for r in p_rows),
                                          fallback_ids=fb_counts,unavailable_reasons=unavail_reasons),
                    fallback_rate=sum(r['fallback_id'] is not None for r in pipeline['rows'])/len(pipeline['rows']) if pipeline and pipeline['rows'] else None,
                    backlog=queue.get('counts',{}).get('backlog_waiting'),queue_counts=queue.get('counts'),
                    deferred_count=sum(d['decision']=='budget_deferred' for d in decisions) if pipeline else None,
                    fallback_count=sum(r['fallback_id'] is not None for r in pipeline['rows']) if pipeline else None,
                    fallback_denominator=len(pipeline['rows']) if pipeline else None,
                    queue_processing_seconds=pipeline.get('queue_processing_seconds') if pipeline else None,
                    budget_status=queue.get('budget_status'),queue_latency_seconds=None,
                    verified_precision=None,review_minutes=None,drift=None,
                    missing_reason='Verified review outcomes, waiting latency and approved drift reference are not linked' if pipeline else
                        'No ensemble fallback, delivery/backlog, verified review outcomes or approved drift reference in this executor',
                    investigation_required=any(v['available']<v['total'] for v in branches.values()),
                    trigger='branch_unavailable: investigate source/model coverage; never auto-fit or activate')

    def overview(self,scope,recheck=None):
        datasets=[]
        if self.snapshots is not None:
            with self.snapshots._transaction(scope,recheck) as c:
                ids=[r[0] for r in c.execute('SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? ORDER BY rowid DESC LIMIT 100',
                     (scope.tenant_id,next(iter(scope.company_ids))))]
                for sid in ids:
                    m,raw=self.snapshots._read_snapshot(c,scope,sid);data=loads(raw);native='source' in data
                    rows=data['source']['tables']['transactions'] if native else data['transactions']
                    datasets.append(dict(snapshot_id=sid,created_at=m['created_at'],checksum=m['checksum'],
                        candidate_count=len(data['candidate_transaction_ids']) if native else len(rows),
                        as_of=data['source']['as_of'] if native else m['created_at'],
                        source_kind='simulated' if (data['source']['is_simulated'] if native else all(r['source']['is_simulated'] for r in rows)) else 'source_export'))
        observations=self.store.list(scope,'observation',recheck)
        completed={r['value']['pin_id'] for r in observations}
        pending=[dict(pin_id=p['id'],**{k:p['value'][k] for k in ('run_id','lane','bundle_id','request','at')})
                 for p in self.store.list(scope,'pin',recheck) if p['id'] not in completed]
        plans=[dict(plan_id=r['id'],study_sha256=r['value']['value']['study']['study_result_sha256'],selected_arm_id=r['value']['value']['study']['detector_validation']['selected_arm_id'],
                    execution_location='enterprise_local_only') for r in self.store.list(scope,'artifact',recheck) if r['value']['slot']=='validation_study']
        return dict(version=VERSION,profile=PROFILE,production_ready=False,open_decisions=list(OPEN_DECISIONS),plans=plans,
                    datasets=datasets,dataset_limit=100,
                    pending_runs=pending,
                    pointers={lane:self.store.current(scope,lane,recheck) for lane in ('staging','production')},
                    bundles=self.store.list(scope,'bundle',recheck),gates=self.store.list(scope,'gate',recheck),
                    approvals=self.store.list(scope,'approval',recheck),history=self.store.list(scope,'activation',recheck),
                    revocations=self.store.list(scope,'revocation',recheck),
                    runs=[dict(id=r['id'],value={k:v for k,v in r['value'].items() if k!='result'}) for r in observations],
                    revocation_note='Activation/rollback always recheck revocation and current artifact/runtime integrity.')

    def diff(self,scope,left,right,recheck=None):
        a=self.store.get(scope,left,'bundle',recheck);b=self.store.get(scope,right,'bundle',recheck)
        return dict(left=left,right=right,changed=[s for s in sorted(set(a['components'])|set(b['components'])) if a['components'].get(s)!=b['components'].get(s)],
                    names=dict(left=a['name'],right=b['name']))

    def require_new_delivery(self,scope,recheck=None):
        # No executor for an approved full bundle exists yet. Protect legacy queue
        # entry points on a release-enabled node too; staging cannot bypass this
        # by sending a fixture policy or an already scored body. Old pending
        # deliveries/reviews are deliberately not rewritten or cancelled here.
        with self.store.tx(scope,recheck,write=False):
            ensure(False,'RELEASE_PRODUCTION_BLOCKED','Chưa có bundle production và executor đầy đủ được duyệt để đưa vụ mới vào hàng đợi active.')
