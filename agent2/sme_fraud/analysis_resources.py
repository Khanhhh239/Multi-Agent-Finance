"""Scoped, pinned inference artifacts. Never discovers latest, writes, or fits."""
from pathlib import Path
import re
import sqlite3

from finance_input.json_io import loads
from .import_files import canonical,digest,ImportFailure,fail

VERSION='analysis-bindings/1.0.0'
ID=re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')
ARTIFACT=re.compile(r'mth_[a-f0-9]{64}\Z')
ML_IDS=('isolation_forest','autoencoder','ecod','lof')


class AnalysisResources:
    def __init__(self,model_db=None,bindings_file=None):
        self.model_db=Path(model_db) if model_db else None
        self.bindings_file=Path(bindings_file) if bindings_file else None

    def selection(self,scope):
        tenant,company=scope.tenant_id,next(iter(scope.company_ids))
        missing=dict(version=VERSION,tenant_id=tenant,company_id=company,statistics_artifact_id=None,ml_artifacts={})
        if self.bindings_file is None:return missing,'binding_missing'
        try:
            with self.bindings_file.open('rb') as stream:raw=stream.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('binding size')
            value=loads(raw)
            if not isinstance(value,dict) or set(value)!={'version','bindings'} or value['version']!=VERSION or not isinstance(value['bindings'],list) or len(value['bindings'])>1024:raise ValueError('bindings contract')
            seen=set();selected=None
            for row in value['bindings']:
                if not isinstance(row,dict) or set(row)!={'tenant_id','company_id','statistics_artifact_id','ml_artifacts'}:raise ValueError('binding fields')
                if not all(isinstance(row[k],str) and ID.fullmatch(row[k]) for k in ('tenant_id','company_id')):raise ValueError('binding identity')
                key=row['tenant_id'],row['company_id']
                if key in seen:raise ValueError('duplicate binding')
                seen.add(key)
                if row['statistics_artifact_id'] is not None and (not isinstance(row['statistics_artifact_id'],str) or not ARTIFACT.fullmatch(row['statistics_artifact_id'])):raise ValueError('statistics ID')
                models=row['ml_artifacts']
                if not isinstance(models,dict) or any(m not in ML_IDS or not isinstance(a,str) or not ARTIFACT.fullmatch(a) for m,a in models.items()):raise ValueError('ML IDs')
                if key==(tenant,company):selected=dict(version=VERSION,**row)
            return (selected,None) if selected else (missing,'binding_missing')
        except FileNotFoundError:return missing,'binding_missing'
        except (OSError,ValueError,TypeError,KeyError,RecursionError,OverflowError):return missing,'binding_invalid'

    def load(self,scope,recheck=None):
        from .method_adapters import METHODS,UnavailableArtifact,LocalArtifact,_scope
        _scope(scope)
        if recheck is not None and recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Gửi lại theo quyền hiện hành.')
        selected,error=self.selection(scope)
        pinned=dict(robust_z=selected['statistics_artifact_id'],**selected['ml_artifacts'])
        methods=('robust_z',*sorted(selected['ml_artifacts'])) if selected['ml_artifacts'] else METHODS
        artifacts={};resource_state={}
        store=None;store_error=None
        if self.model_db is not None and any(pinned.values()):
            try:
                from .method_store import MethodStore
                store=MethodStore(self.model_db,read_only=True)
            except (ImportFailure,sqlite3.Error,OSError):store_error='model_store_unavailable'
        for method in methods:
            identity=pinned.get(method)
            reason=error or ('artifact_not_pinned' if identity is None else store_error or ('model_store_unconfigured' if store is None else None))
            if reason is None:
                try:artifacts[method]=store.get_artifact(scope,identity,recheck)
                except ImportFailure as failure:
                    if failure.code in ('MODEL_ARTIFACT_NOT_FOUND','MODEL_ARTIFACT_INTEGRITY','MODEL_STORAGE_VERSION'):
                        reason={'MODEL_ARTIFACT_NOT_FOUND':'artifact_missing','MODEL_ARTIFACT_INTEGRITY':'artifact_invalid','MODEL_STORAGE_VERSION':'model_store_unavailable'}[failure.code]
                    else:raise
                except (sqlite3.Error,OSError):reason='model_store_unavailable'
            if reason:artifacts[method]=UnavailableArtifact(reason,'Chưa có phiên bản đã fit, được chỉ định và tương thích để chấm; không tự huấn luyện trong yêu cầu này.')
            artifact=artifacts[method]
            resource_state[method]=dict(artifact_id=artifact.artifact_id,manifest_sha256=digest(artifact.manifest),payload_sha256=digest(artifact.payload)) if isinstance(artifact,LocalArtifact) else dict(reason=artifact.code)
        binding=dict(selection=selected,error=error,resources=resource_state)
        return dict(methods=methods,artifacts=artifacts,selected=selected,binding=binding,binding_hash=digest(canonical(dict(selection=selected,error=error))))

    def recheck(self,scope,loaded):
        selected,error=self.selection(scope)
        if digest(canonical(dict(selection=selected,error=error)))!=loaded['binding_hash']:
            fail(409,'ANALYSIS_BINDING_CHANGED','Phiên bản phân tích đã đổi trong lúc chạy.','Chạy lại để dùng đúng phiên bản đã được chỉ định.')

    def recheck_id(self,scope,context_id):
        self.recheck(scope,dict(binding_hash=context_id.removeprefix('actx_')))
