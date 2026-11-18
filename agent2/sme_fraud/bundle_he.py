"""Enterprise bundle bridge to durable Concrete workers. No clear scoring fallback.

Cloud receives the existing HE4 ciphertext/evaluation-key protocol only. Source
planning, decryption, policy, coalescing, budgeting and review stay at the DN.
"""
from copy import deepcopy
from .import_files import canonical,digest,ImportFailure
from .pipeline_release_store import ensure
from .snapshot_features import utc

MODE='cloud_ciphertext_only'
VERSION='bundle-he4-native/1.1.0'
PROFILES=('rules','c3','graph','statistics')
COVERED_RULES=['P1','A6','C2','C3','B1','B5','E4']


class BundleHE:
    def __init__(self,backend):
        self.backend=backend
        self.jobs=backend.node.jobs

    def capture(self,scope):
        from experiments.he_inference.protocol import HEUnavailable
        from experiments.he_inference.http_common import ServiceError
        ensure(hasattr(self.jobs,'submit_bound') and self.jobs.settings.supports_rule_snapshot,
               'PIPELINE_HE_UNAVAILABLE','Chưa cấu hình worker HE cho snapshot nguồn 35 luật.',503)
        try:
            context=self.jobs.settings.capture(scope)
            keys={}
            for name in PROFILES:
                if name not in context['programs']:
                    keys[name]=None;continue
                try:keys[name]=self.jobs.bridge.public_context(scope,context['programs'][name]['path'])
                except HEUnavailable as error:
                    if error.code!='he4_key_not_provisioned':raise
                    keys[name]=None
            ensure(any(keys.get(n) for n in ('rules','c3','graph')),'PIPELINE_HE_KEYS_UNAVAILABLE','Doanh nghiệp chưa có khóa HE đã cấp cho các mạch được hỗ trợ.',503)
            return dict(version=VERSION,source_contract='agent2-rule-snapshot/1.0.0',context=context,key_contexts=keys,
                covered_rules=list(COVERED_RULES),
                feature_models='statistics_2col_robust_z_he_supported; 33_feature_ml_unavailable',
                cloud_payload='ciphertext_and_public_evaluation_keys_only',postprocessing='enterprise_after_decryption',
                quality_approved=False)
        except (HEUnavailable,ServiceError,OSError,ValueError,KeyError) as error:
            raise ImportFailure(503,'PIPELINE_HE_CONFIGURATION','Chưa ghim được build và khóa HE đã cấp cho doanh nghiệp.',
                                'Kiểm tra cấu hình worker và cấp khóa trước khi chuẩn bị bundle HE.') from error

    def check(self,scope,component):
        ensure(component==self.capture(scope),'PIPELINE_HE_CONTEXT_CHANGED',
               'Build, khóa hoặc cấu hình HE đã đổi; không thay phiên đang lưu. Cần kiểm tra hoặc qualification bundle mới.')

    def execute(self,service,scope,pin,values,manifest,data,as_of,header,recheck):
        from experiments.he_inference.http_common import ServiceError
        from experiments.he_inference.protocol import HEUnavailable
        component=values.get('he')
        ensure(component is not None,'PIPELINE_HE_UNAVAILABLE','Bundle chưa ghim executor HE; không chạy dữ liệu rõ thay thế.')
        ensure(pin['actor_id']==scope.actor_id,'PIPELINE_HE_OWNER','Chỉ tài khoản đã gửi được tiếp tục yêu cầu HE đang chạy.',403)
        ensure(header is not None,'PIPELINE_HE_AUTH_REQUIRED','Cần phiên đăng nhập hiện hành để tiếp tục HE.',401)
        ensure(manifest['contract_version']==component['source_contract'] and utc(as_of)==utc(data['source']['as_of']),
               'PIPELINE_HE_SOURCE','HE chỉ nhận đúng contract và mốc nguồn snapshot đã khóa.')
        self.check(scope,component)
        stat_art=values.get('models',{}).get('selection',{}).get('statistics_artifact_id')
        binding=dict(tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids)),
            **{k:pin[k] for k in ('run_id','pin_id','bundle_id')},snapshot_id=manifest['snapshot_id'],
            snapshot_checksum=manifest['checksum'],data_checksum=manifest['data_checksum'],as_of=data['source']['as_of'],
            statistics_artifact_id=stat_art,he_component_sha256=digest(canonical(component)))
        store=service.store;link=None
        with store.tx(scope,recheck,write=False) as c:
            for row in c.execute('SELECT object_id FROM audit WHERE owner=? AND kind=?',(store.owner(scope),'he_job')).fetchall():
                found=store.read(c,scope,row['object_id'],'he_job')
                if found['pin_id']==pin['pin_id']:link=found;break
        company=next(iter(scope.company_ids))
        try:
            if link is None:
                child=self.jobs.submit_bound(company,header,'bundle:'+pin['pin_id'],
                    dict(artifact_id=None,snapshot_id=manifest['snapshot_id'],as_of=data['source']['as_of']),
                    expected_context=component['context'],bundle_binding=binding,key_contexts=component['key_contexts'])
                link=dict(pin_id=pin['pin_id'],job_id=child['job_id'],binding=binding)
                # Child admission is idempotent by pin even if DN dies before this commit.
                with store.tx(scope,recheck) as c:
                    service._compatible(c,scope,pin['bundle_id'],recheck)
                    store.put(c,scope,'he_job',link)
            ensure(link['binding']==binding,'PIPELINE_HE_BINDING','Yêu cầu HE không khớp nguồn đã ghim.',503)
            row,saved=self.jobs.store.get(scope,link['job_id'])
            ensure(saved['request'].get('bundle_binding')==binding and saved['request']['he4_context']==component['context']
                   and saved['request'].get('bundle_key_contexts')==component['key_contexts'],
                   'PIPELINE_HE_BINDING','Phiên HE không khớp bundle, model/build hoặc khóa.',503)
            if row['phase'] not in ('completed','failed','expired'):
                self.jobs.resume(company,header,link['job_id'])
            status,result=self.jobs.result(company,header,link['job_id'])
            if status!=200:
                ensure(status!=409,'PIPELINE_HE_FAILED','Worker HE chưa hoàn tất: '+str(result.get('reason') or result.get('phase'))+'. Giữ nguyên yêu cầu.',503)
                raise ImportFailure(409,'PIPELINE_RUN_PENDING','Yêu cầu HE đang chạy ('+str(result.get('phase'))+').',
                                    'Bấm Tiếp tục yêu cầu đã lưu; giữ nguyên doanh nghiệp, snapshot và chế độ HE.')
            self.check(scope,component)
            ensure(result.get('bundle_binding')==binding,'PIPELINE_HE_BINDING','Kết quả HE không thuộc yêu cầu đã ghim.',503)
            provenance=result.get('provenance',{})
            expected_builds={name:{k:info[k] for k in ('circuit_sha256','specs_sha256')} for name,info in component['context']['programs'].items()}
            ensure(result.get('run_id')==link['job_id'] and provenance.get('builds')==expected_builds and
                   provenance.get('implementation_sha256')==component['context']['implementation_sha256'] and
                   all(component['key_contexts'].get(name) is not None and
                       value==component['key_contexts'][name]['key_epoch'] for name,value in provenance.get('key_epochs_by_profile',{}).items()) and
                   all(component['key_contexts'].get(name) is not None and
                       value==component['key_contexts'][name]['evaluation_keys_sha256'] for name,value in provenance.get('evaluation_keys_sha256_by_profile',{}).items()),
                   'PIPELINE_HE_RESULT_BINDING','Provenance kết quả HE không khớp build/khóa/triển khai đã ghim.',503)
            analysis=adapt(scope,manifest,data,values,result)
            stat_ok=any(r['branches']['statistics']['available'] for r in analysis['rows'])
            analysis['execution']=dict(location=MODE,cloud_he=dict(available=analysis['he_execution'],job_id=link['job_id'],
                covered_rules=component['covered_rules'],statistics_he_available=stat_ok,complete_catalogue=False),
                cloud_branches={name:dict(available=any(r['branches'][name]['available'] for r in analysis['rows']),
                    status=('available' if stat_ok else 'unavailable') if name=='statistics' else ('partial' if name in ('rules','graph') else 'unavailable'),
                    reason=('bounded_2col_robust_z_he' if stat_ok else 'statistics_he_unavailable') if name=='statistics' else ('native_33_feature_he_unsupported' if name=='ml' else 'bounded_native_he_profiles'))
                    for name in ('rules','statistics','graph','ml')},plaintext_cloud_upload=False,
                enterprise_postprocessing=['decode','frozen_policy','coalesce','case_budget','queue_delivery','review_report'])
            return analysis
        except (ServiceError,HEUnavailable) as error:
            raise ImportFailure(getattr(error,'status',503),'PIPELINE_HE_TRANSPORT',
                                'Chưa hoàn tất HE: '+error.code+'.','Tiếp tục đúng yêu cầu đã lưu; không tạo phiên hoặc chấm rõ thay thế.') from error


def adapt(scope,manifest,data,values,result):
    """Project verified/decrypted HE output, never call rule engine or model scorer."""
    from .rules import RULE_NAMES
    from .rule_snapshot import catalogue,SCOPE_RULES
    expected=data['candidate_transaction_ids'];rows=result.get('rows') or []
    ensure(result.get('version')=='he-rule-snapshot-groups-result/1.0.0' and
           result.get('company_id')==manifest['company_id'] and result.get('tenant_id')==scope.tenant_id and
           all(result.get(k)==manifest[k] for k in ('snapshot_id','data_checksum')) and
           result.get('snapshot_checksum')==manifest['checksum'] and utc(result['as_of'])==utc(data['source']['as_of']) and
           len(rows)==len(expected) and {r['transaction_id'] for r in rows}==set(expected),
           'PIPELINE_HE_RESULT_BINDING','Kết quả HE thiếu/thừa giao dịch hoặc không khớp snapshot.',503)
    txs={r['transaction_id']:r for r in data['source']['tables']['transactions']};projected=[];batch={}
    group_for={'P1':'p1','A6':'a6','C2':'c2','C3':'c3','B1':'b1','B5':'b5_e4','E4':'b5_e4'}
    pinned_stat_id=None
    for row in rows:
        tx=txs[row['transaction_id']];known=bool(row['known_at_cutoff']);entries=[]
        ensure(row['revision']==tx.get('revision',1),'PIPELINE_HE_RESULT_BINDING','Phiên bản giao dịch HE không khớp.',503)
        for code,name in RULE_NAMES.items():
            check=row['groups'].get(group_for.get(code)) if code in group_for else None
            status=check['status'] if known and check else 'unavailable'
            if known and code in SCOPE_RULES:status='not_applicable'
            ready=status in ('evaluated_hit','evaluated_no_hit');hits=[]
            if ready and check.get('matched'):
                hits=[dict(rule_id=code,transaction_id=tx['transaction_id'],points=check.get('score') or 0,
                    hard_trigger=code in ('P1','C2') or bool(check.get('hard_trigger')),suppressed_reason=None,
                    evidence=deepcopy(check),related_transaction_ids=[])]
            entries.append(dict(rule_id=code,name=name,status=status,available=ready,matched=check.get('matched') if ready else None,
                score=check.get('score') if ready else None,hits=hits,
                reason=check.get('reason') if known and check else 'transaction_not_known_at_cutoff' if not known else 'he_rule_unsupported',
                gaps=deepcopy(check.get('gaps',[])) if check else [],scope_result_ref=code if code in SCOPE_RULES else None))
        p1=row['groups']['p1']
        for group in p1.get('simultaneous_checks',[]):
            if not group.get('matched'):continue
            event_id='hegrp_'+digest(canonical(group['group_scope']))
            batch[event_id]=dict(event_id=event_id,status='evaluated',signal=True,points=20,hard_trigger=True,
                suppressed_reason=None,transaction_ids=group['group_scope']['transaction_ids'],related_transaction_ids=[],evidence=deepcopy(group))
        counts={s:sum(e['status']==s for e in entries) for s in ('evaluated_hit','evaluated_no_hit','unavailable','not_applicable')}
        unavailable_ml=dict(available=False,status='unavailable',score=None,raw_score=None,reason=dict(code='native_33_feature_he_unsupported'))
        stat_in=(row.get('branches') or {}).get('statistics') or {}
        if stat_in.get('available') is True:
            pinned_stat_id=stat_in.get('artifact_id')
            stat_method=dict(method_id='robust_z',raw_score=stat_in['raw_score'],score=stat_in['score'],score_kind='empirical_midrank',
                available=True,status='available',reason=None,missing_features=list(stat_in.get('missing_features') or []),
                artifact_id=stat_in.get('artifact_id'),preprocess_version=stat_in.get('preprocess_version'),
                reference_version=stat_in.get('reference_version'),feature_contract_fingerprint=stat_in.get('feature_contract_fingerprint'),
                evidence_refs=[],details=dict(he_quantization=stat_in.get('quantization',1024),selected_columns=list(stat_in.get('selected_columns') or [])))
            stat_branch=dict(available=True,status='available',score=stat_in['score'],raw_score=stat_in['raw_score'],reason=None,
                artifact_id=stat_in.get('artifact_id'),reference_version=stat_in.get('reference_version'))
        else:
            stat_rc=stat_in.get('reason') or 'native_33_feature_he_unsupported'
            if isinstance(stat_rc,dict):stat_rc=stat_rc.get('code') or 'native_33_feature_he_unsupported'
            stat_method=dict(available=False,status='unavailable',score=None,raw_score=None,reason=dict(code=str(stat_rc)))
            stat_branch=deepcopy(stat_method)
        graph=dict(available=any(row['groups'][g]['available'] for g in ('b1','b5_e4')),links=[],findings=[],he_groups={g:deepcopy(row['groups'][g]) for g in ('b1','b5_e4')})
        methods_map={'robust_z':stat_method,**{m:deepcopy(unavailable_ml) for m in values['models']['selection']['ml_artifacts']}}
        projected.append(dict(transaction_id=tx['transaction_id'],revision=row['revision'],amount_vnd=tx['amount_vnd'],
            event_at=tx['posted_at'],knowledge_at=tx['observed_at'],kind=tx['txn_type'],description=tx.get('business_purpose',''),
            availability=dict(available=known,reason=None if known else dict(code='transaction_not_known_at_cutoff')),
            rule_coverage=dict(summary=counts,rules=entries),
            branches=dict(rules=dict(available=known and counts['evaluated_hit']+counts['evaluated_no_hit']>0,status='partial' if known else 'unavailable',
                evaluated_count=counts['evaluated_hit']+counts['evaluated_no_hit'],unavailable_count=counts['unavailable'],total_count=35),
                statistics=stat_branch,ml=deepcopy(unavailable_ml),graph=dict(graph,status='partial' if graph['available'] else 'unavailable')),
            methods=methods_map,
            graph=graph,feature_evidence=dict(records=[]),feature_missing_reasons=dict(he='native_33_feature_ml_he_unsupported')))
    provenance=result['provenance']
    scoped=[dict(rule_id=code,status='unavailable',available=False,reason='he_rule_unsupported',hits=[],groups=[]) for code in sorted(SCOPE_RULES)]
    pins={'robust_z':pinned_stat_id,**{m:None for m in values['models']['selection']['ml_artifacts']}}
    return dict(version='snapshot-rule-analysis/1.0.0',view='technical',analysis_id='ana_'+digest(canonical(result)),
        as_of=result['as_of'],snapshot={k:manifest[k] for k in ('snapshot_id','company_id','checksum','data_checksum','contract_version')},
        rows=projected,row_count=len(projected),catalogue=catalogue(),supported_checks=['retained_catalogue_35'],
        catalogue_results=[dict(rule_id='P1',groups=list(batch.values())),*scoped],scope_results=scoped,groups=[],
        aggregate=dict(available=False,score=None),execution_mode=MODE,he_execution=bool(provenance.get('evaluation_keys_sha256_by_profile')),he_provenance=deepcopy(provenance),
        bridge_provenance=dict(model_pins=pins),
        feature_generation=dict(available=pinned_stat_id is not None,reason=None if pinned_stat_id is not None else 'native_33_feature_he_unsupported'),source_limits=[],
        coverage_message='HE P1/A6/C2/C3/B1/B5/E4 và thống kê RobustZ 2 biến theo nguồn/miền khả dụng; 28 luật còn lại và ML 33 biến chưa hỗ trợ HE.')
