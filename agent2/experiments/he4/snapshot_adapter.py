"""Enterprise-only, source-bound snapshot -> encrypted branch input plans.

No fit or branch score executes here. Keys, source identifiers and evidence
stay outside the cloud numerical input arrays.
"""
from copy import deepcopy
import io
from pathlib import Path
import pickle
import joblib
import numpy as np
from finance_input.json_io import loads
from sme_fraud.import_files import canonical,digest,fail,ImportFailure
from sme_fraud.snapshot_features import build_from_snapshot,feature_contract,utc
from sme_fraud.rule_sources import _resolve
from sme_fraud import p1_evaluation
from sme_fraud.p1_inputs import _identity
from sme_fraud.entity_graph import normalized,FIELDS
from sme_fraud.method_adapters import _frame,_versions,ARTIFACT_VERSION
from sme_fraud.method_preprocess import validate_preprocess,row_values,VERSION as PREPROCESS
from sme_fraud.method_store import MethodStore
from sme_fraud.method_jobs import validate_config
from sme_fraud.unsupervised_statistics import RobustZ
from .inputs import payment,statistics,graph,InputUnavailable

VERSION='he4-snapshot-plans/1.0.0'


def unavailable(code,**detail):return dict(available=False,status='unavailable',reason=code,requests=[],**detail)
def packed(values):return [np.asarray(value).tolist() for value in values]


def p1_plan(sources,diagnostic,meta):
    entry=next(p for p in diagnostic['rules'] if p['rule_id']=='P1')
    evidence=deepcopy(entry['evidence_refs'])
    if entry['source_status']=='not_applicable':return dict(unavailable('rule_not_applicable',evidence_refs=evidence),status='not_applicable')
    if entry['source_status']!='ready' or entry['gaps']:return unavailable('rule_sources_unavailable',gaps=deepcopy(entry['gaps']),evidence_refs=evidence)
    bound=p1_evaluation.prepare(sources,meta)
    if 'error' in bound:return unavailable(bound['error'][0],evidence_refs=evidence)
    requests=[]
    try:
        for key,parts in sorted(bound['groups'].items()):
            if not parts['current']:continue
            prior,current,simultaneous=(parts[k] for k in ('prior','current','simultaneous'))
            # Several source invoice IDs may represent one obligation. The
            # retained engine validates equal base values and counts one base.
            base=sorted(bound['bases'][key],key=lambda r:(r['record_id'],r['revision']))[0]
            invoices=[base,*bound['corrections'][key]]
            prior_kinds=[bound['by_tx'][_identity(a['transaction_ref'])]['kind'] for a in prior]
            modes=[('row',current)]
            if len({_identity(a['transaction_ref']) for a in current+simultaneous})>=2:modes.append(('simultaneous_group',current+simultaneous))
            for mode,rows in modes:
                values=payment([r['amount_vnd'] for r in prior],[r['amount_vnd'] for r in rows],
                    [r['amount_vnd'] for r in invoices],prior_kinds,tolerance=p1_evaluation.TOLERANCE_VND,group=mode!='row')
                requests.append(dict(profile='rules',role=mode,obligation=list(key),values=packed(values),
                    source_refs=dict(prior=[_identity(r) for r in prior],current=[_identity(r) for r in rows],invoices=[_identity(r) for r in invoices])))
    except (InputUnavailable,ValueError) as error:return unavailable(getattr(error,'code','he_p1_input_out_of_domain'),evidence_refs=evidence)
    if not requests:return unavailable('p1_current_allocation_unresolved',evidence_refs=evidence)
    return dict(available=True,status='ready',reason=None,requests=requests,evidence_refs=evidence,
        rule_id='P1',other_rules_status='unavailable',coverage='P1 only; no full-catalog rule aggregate')


def graph_plan(sources):
    entities=[];refs=[];identities=[]
    for table in ('vendors','employees'):
        for row in sources[table]:
            item={}
            for field in FIELDS:
                source_field='tax_id' if field=='tax_code' else field
                value=row.get(source_field)
                if value is not None:
                    item[field]=normalized(value,field,row.get('bank_code',''))
            entities.append(item);identities.append(dict(table=table,record_id=row['record_id'],revision=row['revision']))
            refs.append(dict(table=table,record_id=row['record_id'],revision=row['revision'],effective_at=row['effective_at'],observed_at=row['observed_at']))
    try:values=graph(entities)
    except (InputUnavailable,ValueError) as error:return unavailable(getattr(error,'code','he_graph_attribute_invalid'),evidence_refs=refs)
    return dict(available=True,status='ready',reason=None,requests=[dict(profile='graph',role='graph',values=packed(values))],
        entities=identities,evidence_refs=refs,profile='master attributes only; no entity-link events in input contract')


def load_statistics(model_db,scope,artifact_id,recheck):
    if artifact_id is None:return None,'artifact_not_pinned'
    try:
        store=MethodStore(model_db,read_only=True);artifact=store.get_artifact(scope,artifact_id,recheck)
        m=loads(artifact.manifest)
        if artifact.artifact_id!='mth_'+digest(artifact.manifest) or m['payload_sha256']!=digest(artifact.payload) or m['model_version']!='mdl_'+digest(artifact.payload):raise ValueError('artifact digest')
        if (m['tenant_id'],m['company_id'])!=(scope.tenant_id,next(iter(scope.company_ids))):raise ValueError('artifact scope')
        if m['method_id']!='robust_z' or m['version']!=ARTIFACT_VERSION or m['feature_contract']!=feature_contract() or m['feature_contract_fingerprint']!=feature_contract()['fingerprint'] or m['versions']!=_versions() or m['preprocess_version']!=PREPROCESS:return None,'artifact_incompatible'
        pre=m['preprocess'];validate_preprocess(dict(contract=feature_contract()),pre)
        if pre['policy']!='strict' or len(m['selected_columns'])!=2 or pre['output_columns']!=m['selected_columns'] or pre['selected_columns']!=m['selected_columns'] or digest(canonical(pre))!=m['preprocess_sha256']:return None,'artifact_incompatible'
        context=m['fit_context'];config=validate_config(context['config'])
        from sme_fraud import method_jobs
        if config['method_id']!='robust_z' or config['selected_columns']!=m['selected_columns'] or config['missing_policy']!='strict' or context['job_implementation_sha256']!=digest(Path(method_jobs.__file__).read_bytes()):return None,'artifact_incompatible'
        if not utc(m['train_end'])<utc(m['reference_start'])<=utc(m['reference_end'])<utc(config['evaluation_start']) or m['history_rows']<config['minimum_history'] or m['reference_rows']<1:raise ValueError('fit periods')
        if config['evaluation_mode']=='prospective' and utc(context['created_at'])>=utc(config['evaluation_start']):raise ValueError('publication period')
        with store._transaction(scope,recheck) as conn:
            job=store._job(conn,scope,context['job_id']);request=loads(job['request_json'])
            if job['status']!='succeeded' or job['artifact_id']!=artifact_id or job['request_hash']!=context['request_hash'] or request['config']!=config or request['versions']!=m['versions'] or request['feature_contract']!=m['feature_contract'] or request['snapshot']!=m['history_binding'] or request['snapshot']!=m['reference_binding'] or request['job_implementation_sha256']!=context['job_implementation_sha256']:raise ValueError('fit receipt')
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Mở lại từ Portal.')
        # Trusted immutable local registry only; never a browser-uploaded model.
        model,reference=joblib.load(io.BytesIO(artifact.payload))
        if type(model) is not RobustZ or not reference or len(reference)!=m['reference_rows'] or sorted(reference)!=reference or not np.isfinite(reference).all() or digest(canonical(reference))!=m['reference_version']:raise ValueError('model/reference')
        if any(np.asarray(v).shape!=(2,) or not np.isfinite(v).all() for v in (model.med_,model.scale_)) or np.any(model.scale_<=0):raise ValueError('model domain')
        return dict(manifest=m,model=model,artifact_id=artifact_id),None
    except ImportFailure as error:
        if error.status in (403,409):raise
        return None,'artifact_missing' if error.status==404 else 'artifact_invalid'
    except (ValueError,KeyError,TypeError,EOFError,OSError,pickle.UnpicklingError,AttributeError,ImportError):return None,'artifact_invalid'


def statistics_plan(frame,index,loaded,reason):
    if loaded is None:return unavailable(reason)
    m=loaded['manifest'];row=frame['rows'][index];context=m['fit_context'];cutoff=min(utc(row['event_at']),utc(row['as_of']))
    if utc(m['reference_end'])>=cutoff:return unavailable('artifact_from_future')
    if digest(canonical(row['record_id'])) in m['fitted_identity_hashes']:return unavailable('artifact_training_overlap')
    if utc(context['evaluation_start'])>cutoff:return unavailable('before_evaluation_period')
    if context['evaluation_mode']=='prospective' and utc(context['created_at'])>=cutoff:return unavailable('artifact_not_yet_created')
    values,missing,unavailable_reason=row_values(frame,frame['features'][index],m['preprocess'])
    if unavailable_reason:return unavailable(unavailable_reason,missing_features=missing)
    try:args=statistics(values,loaded['model'].med_,loaded['model'].scale_)
    except InputUnavailable as error:return unavailable(error.code)
    return dict(available=True,status='ready',reason=None,requests=[dict(profile='statistics',role='statistics',values=packed(args))],
        artifact_id=loaded['artifact_id'],model_version=m['model_version'],reference_version=m['reference_version'],
        quantization=1024,absolute_score_error_bound=1/1024)


def prepare_snapshot(store,scope,snapshot_id,as_of,*,model_db=None,statistics_artifact=None,recheck=None):
    check=recheck or (lambda:scope)
    if check()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Gửi lại theo quyền hiện hành.')
    frame=build_from_snapshot(store,scope,snapshot_id,as_of,check);_frame(frame,scope)
    data=loads(store.get_snapshot(scope,snapshot_id,check,data=True));private,public=_resolve(data,frame,scope)
    loaded,reason=load_statistics(model_db,scope,statistics_artifact,check)
    rows=[]
    for i,meta in enumerate(frame['rows']):
        identity=meta['record_id'],meta['revision'];sources=private[identity]
        rows.append(dict(record_id=identity[0],revision=identity[1],event_at=meta['event_at'],as_of=meta['as_of'],
            branches=dict(rules=p1_plan(sources,public[identity],meta),graph=graph_plan(sources),statistics=statistics_plan(frame,i,loaded,reason))))
    plan=dict(version=VERSION,snapshot=frame['snapshot'],as_of=frame['as_of'],feature_contract=frame['contract'],rows=rows,
        implementation={name:digest(Path(path).read_bytes()) for name,path in [('adapter',__file__),('p1',p1_evaluation.__file__)]})
    plan['plan_sha256']=digest(canonical(plan))
    if check()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trước khi lập kế hoạch.','Gửi lại theo quyền hiện hành.')
    return plan
