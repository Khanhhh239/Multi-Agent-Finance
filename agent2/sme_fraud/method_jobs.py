"""Offline per-company fit and separate inference CLI; no HTTP fit/active switch."""
import argparse
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import tempfile

from finance_input.json_io import loads
from .auth import AuthError, FileAuthorizer
from .import_files import canonical, digest, fail, ImportFailure
from .method_adapters import (METHODS, _versions, fit_local_reference, score_snapshot, UnavailableArtifact, LocalArtifact)
from .method_preprocess import POLICIES
from .method_store import MethodStore, require_fit
from .snapshots import SnapshotStore
from .rule_snapshot_features import SOURCE_CONTRACT as RULE_SOURCE_CONTRACT, build_from_rule_snapshot, feature_contract as rule_feature_contract
from .snapshot_features import build_from_snapshot, feature_contract, utc

CONFIG_VERSION='company-fit-config/1.0.0'
PERIODS=('history_start','history_end','reference_start','reference_end','evaluation_start')


def validate_config(value):
    required={'version','snapshot_id','method_id','missing_policy','minimum_history','profile_id','evaluation_mode',*PERIODS}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'selected_columns'}:
        raise ValueError('Fit config requires exact version/snapshot/method/profile/missing policy and five period boundaries')
    if value['version']!=CONFIG_VERSION or value['method_id'] not in METHODS or value['missing_policy'] not in POLICIES:
        raise ValueError('Unsupported fit config version/method/missing policy')
    if not isinstance(value['snapshot_id'],str) or re.fullmatch(r'snp_[a-f0-9]{32}',value['snapshot_id']) is None:
        raise ValueError('A snapshot ID from the current input store is required')
    if value['evaluation_mode'] not in ('backtest','prospective') or type(value['minimum_history']) is not int or value['minimum_history']<5:
        raise ValueError('Explicit evaluation_mode and minimum_history >=5 required')
    if not isinstance(value['profile_id'],str) or not value['profile_id'].strip():
        raise ValueError('Explicit profile_id required; demo settings are not production approval')
    result=copy.deepcopy(value)
    for name in PERIODS:
        if not isinstance(value[name],str):raise ValueError('Period boundaries must be explicit aware timestamp strings')
        result[name]=utc(value[name]).isoformat()
    history_start,history_end,reference_start,reference_end,evaluation_start=(utc(result[k]) for k in PERIODS)
    if not history_start<history_end<=reference_start<reference_end<=evaluation_start:
        raise ValueError('Require history_start < history_end <= reference_start < reference_end <= evaluation_start')
    columns=result.setdefault('selected_columns',list(feature_contract()['columns']))
    if not isinstance(columns,list) or not columns or not all(isinstance(c,str) for c in columns) or len(set(columns))!=len(columns) or any(c not in feature_contract()['columns'] for c in columns):
        raise ValueError('Selected columns must come from the current snapshot feature contract')
    return result


def _window(frame,start,end):
    start,end=utc(start),utc(end)
    indexes=[i for i,row in enumerate(frame['rows']) if start<=utc(row['event_at'])<end and start<=utc(row['as_of'])<end]
    result=dict(frame)
    for name in ('rows','features','missing','evidence'):result[name]=[copy.deepcopy(frame[name][i]) for i in indexes]
    for i,(row,evidence) in enumerate(zip(result['rows'],result['evidence'])):row['row_index']=evidence['row_index']=i
    return result


def run_fit_job(snapshots,models,authorizer,authorization,company,config,key):
    scope=authorizer.authorize(authorization,company);require_fit(scope)
    recheck=lambda:authorizer.authorize(authorization,company)
    config=validate_config(config)
    snapshot=snapshots.get_snapshot(scope,config['snapshot_id'],recheck)
    binding={k:snapshot[k] for k in ('snapshot_id','tenant_id','company_id','checksum','data_checksum','contract_version')}
    is_rule_profile=snapshot['contract_version']==RULE_SOURCE_CONTRACT
    contract=rule_feature_contract() if is_rule_profile else feature_contract()
    request=dict(version='company-fit-job/1.0.0',config=config,snapshot=binding,feature_contract=contract,versions=_versions(),
                 job_implementation_sha256=digest(Path(__file__).read_bytes()))
    job,claimed=models.begin_fit(scope,request,key,recheck)
    if not claimed:
        artifact=models.get_artifact(scope,job['artifact_id'],recheck) if job['status']=='succeeded' else None
        return dict(job=job,manifest=loads(artifact.manifest) if artifact else None,reused=True)
    try:
        context=dict(job_id=job['job_id'],request_hash=job['request_hash'],created_at=job['created_at'],actor_id=scope.actor_id,
                     evaluation_mode=config['evaluation_mode'],evaluation_start=config['evaluation_start'],config=config,
                     job_implementation_sha256=request['job_implementation_sha256'])
        if config['evaluation_mode']=='prospective' and utc(job['created_at'])>=utc(config['evaluation_start']):
            raise ValueError('Prospective job must start before evaluation period; use explicit backtest for retrospective analysis')
        # Replay independently: a later transaction revision cannot replace a
        # version that was the one known at the end of the training window.
        def _build(end_at):
            if is_rule_profile:
                return build_from_rule_snapshot(snapshots,scope,config['snapshot_id'],end_at,recheck,candidates_only=False,require_exact_source_cutoff=False)
            return build_from_snapshot(snapshots,scope,config['snapshot_id'],end_at,recheck)
        history=_build((utc(config['history_end'])-timedelta(microseconds=1)).isoformat())
        reference=_build((utc(config['reference_end'])-timedelta(microseconds=1)).isoformat())
        history=_window(history,config['history_start'],config['history_end'])
        reference=_window(reference,config['reference_start'],config['reference_end'])
        artifact=fit_local_reference(history,reference,scope,config['method_id'],selected_columns=config['selected_columns'],
            minimum_history=config['minimum_history'],profile_id=config['profile_id'],missing_policy=config['missing_policy'],fit_context=context)
        manifest=loads(artifact.manifest)
        manifest['fit_context']=dict(context,job_started_at=job['created_at'],created_at=models._now())
        if config['evaluation_mode']=='prospective' and utc(manifest['fit_context']['created_at'])>=utc(config['evaluation_start']):
            raise ValueError('Fit finished after the prospective evaluation period started')
        encoded=canonical(manifest);artifact=LocalArtifact('mth_'+digest(encoded),encoded,artifact.payload)
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trong khi fit.','Chưa công bố artifact; chạy lại theo quyền hiện hành.')
        finished=models.publish(scope,job['job_id'],artifact,recheck)
        return dict(job=finished,manifest=loads(artifact.manifest),reused=False)
    except Exception as error:
        code=getattr(error,'code','FIT_DATA_INVALID' if isinstance(error,ValueError) else 'FIT_FAILED')
        try:failed=models.fail_job(scope,job['job_id'],code,recheck)
        except (ImportFailure,AuthError):failed=None  # revocation must not authorize even a status write
        if isinstance(error,(ImportFailure,AuthError)):raise
        message=str(error) if isinstance(error,ValueError) else 'Fit gặp lỗi nội bộ: '+type(error).__name__
        return dict(job=failed or job,manifest=None,reused=False,error=dict(code=code,message=message))


def run_score_job(snapshots,models,authorizer,authorization,company,snapshot_id,as_of,artifact_ids,*,methods=None):
    scope=authorizer.authorize(authorization,company)
    recheck=lambda:authorizer.authorize(authorization,company)
    if not isinstance(artifact_ids,dict) or any(m not in METHODS or not isinstance(a,str) for m,a in artifact_ids.items()):
        raise ValueError('Artifact mapping must contain supported method IDs and explicit artifact IDs')
    methods=(tuple(artifact_ids) or METHODS) if methods is None else tuple(methods)
    if not methods or any(m not in METHODS for m in methods):raise ValueError('Request explicit supported methods')
    artifacts={}
    for method in methods:
        identity=artifact_ids.get(method)
        if identity is None:continue
        try:artifacts[method]=models.get_artifact(scope,identity,recheck)
        except ImportFailure as error:
            if error.code=='MODEL_ARTIFACT_NOT_FOUND':continue
            if error.code=='MODEL_ARTIFACT_INTEGRITY':
                artifacts[method]=UnavailableArtifact('artifact_invalid','Artifact lưu bị lỗi checksum/metadata; không nạp model hoặc tự fit lại.')
            else:raise
    manifest=snapshots.get_snapshot(scope,snapshot_id,recheck)
    if manifest['contract_version']==RULE_SOURCE_CONTRACT:
        from .method_adapters import score_batch
        frame=build_from_rule_snapshot(snapshots,scope,snapshot_id,as_of,recheck,candidates_only=True,require_exact_source_cutoff=False)
        result=score_batch(frame,scope,artifacts=artifacts,methods=methods)
    else:
        result=score_snapshot(snapshots,scope,snapshot_id,as_of,artifacts=artifacts,methods=methods,recheck=recheck)
    if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trước khi trả điểm.','Chạy lại theo quyền hiện hành.')
    return result


def _write_result(path,result,recheck,scope):
    if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trước khi ghi kết quả.','Chạy lại theo quyền hiện hành.')
    path=Path(path).resolve();raw=canonical(result)
    path.parent.mkdir(parents=True,exist_ok=True)
    # Publish a complete file atomically without replacing an older run.
    descriptor,temporary=tempfile.mkstemp(prefix='.method-result-',dir=path.parent)
    temporary=Path(temporary)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trước công bố kết quả.','Chạy lại theo quyền hiện hành.')
        os.link(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('fit','score','job'))
    for name in ('snapshot-db','model-db','auth-file','token-file','company','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--config');parser.add_argument('--idempotency-key');parser.add_argument('--job-id')
    parser.add_argument('--snapshot-id');parser.add_argument('--as-of');parser.add_argument('--artifacts-file')
    parser.add_argument('--method',action='append',choices=METHODS)
    args=parser.parse_args()
    try:
        auth=FileAuthorizer(args.auth_file);header='Bearer '+Path(args.token_file).read_text('utf-8').strip()
        scope=auth.authorize(header,args.company)
        if args.mode in ('fit','job'):require_fit(scope)
        # No business DB or config data is opened before authorization.
        snapshots=SnapshotStore(args.snapshot_db);models=MethodStore(args.model_db,read_only=args.mode!='fit')
        if args.mode=='fit':
            if not args.config or not args.idempotency_key:raise ValueError('fit needs --config and --idempotency-key')
            result=run_fit_job(snapshots,models,auth,header,args.company,loads(Path(args.config).read_bytes()),args.idempotency_key)
        elif args.mode=='score':
            if not args.snapshot_id or not args.as_of or not args.artifacts_file:raise ValueError('score needs snapshot/as-of/artifacts-file')
            result=run_score_job(snapshots,models,auth,header,args.company,args.snapshot_id,args.as_of,loads(Path(args.artifacts_file).read_bytes()),methods=args.method)
        else:
            if not args.job_id:raise ValueError('job needs --job-id')
            result=models.get_job(scope,args.job_id,lambda:auth.authorize(header,args.company))
        _write_result(args.output,result,lambda:auth.authorize(header,args.company),scope)
        print('Đã ghi kết quả:',Path(args.output).resolve())
        return 1 if args.mode=='fit' and result['job']['status']=='failed' else 0
    except (AuthError,ImportFailure) as error:
        print(error.code+': '+error.message+' '+error.action);return 1
    except (OSError,ValueError,TypeError) as error:
        print('MODEL_JOB_INVALID: Kiểm tra cấu hình, kỳ, policy thiếu và đường dẫn; '+str(error));return 1


if __name__=='__main__':raise SystemExit(main())
