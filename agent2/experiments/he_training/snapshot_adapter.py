"""Read-only committed snapshot -> explicitly selected bounded HE training rows.

Selects two existing binary predictors losslessly. No rule flags/labels/scores,
no learned scaling/imputation, no first-four selection or silent row filtering.
All provenance stays at the enterprise; the cloud still receives only ciphertext.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import math
from numbers import Real
from pathlib import Path
import sqlite3

from finance_input.json_io import loads
from sme_fraud.import_files import canonical,digest,fail
from sme_fraud.snapshots import SnapshotStore,APPLICATION_ID
from sme_fraud.snapshot_features import build_from_snapshot,utc
from sme_fraud.rule_snapshot_features import build_from_rule_snapshot,SOURCE_CONTRACT
from .protocol import require,fields,TrainingError

VERSION='snapshot-he-training-adapter/0.1.0'
MAPPING_VERSION='existing-binary-pair/1.0.0'
COLUMNS=('round_million','creator_equals_approver')
REQUEST_FIELDS={'version','snapshot_id','as_of','training_start','training_end','rows'}
TEXT={
    'ROW_NOT_AVAILABLE_AT_AS_OF':('Giao dịch/phiên bản chưa khả dụng tại as_of.','Chọn đúng phiên bản đã được biết tại thời điểm này; không lùi thời gian nguồn.'),
    'ROW_OUTSIDE_TRAINING_WINDOW':('Giao dịch nằm ngoài kỳ train đã chọn.','Chọn lại danh sách hoặc kỳ train rồi kiểm tra lại.'),
    'FEATURE_MISSING':('Thiếu nguồn để xác định feature.','Bổ sung nguồn hợp lệ, tạo snapshot mới và kiểm tra lại; không điền 0.'),
    'FEATURE_OUT_OF_DOMAIN':('Feature không phải số 0/1 chính xác trong miền circuit.','Kiểm tra nguồn/mapping hoặc dùng circuit khác; không làm tròn hay cắt giá trị.'),
    'MIXED_SOURCE_MODES':('Tập train trộn nguồn mô phỏng và nguồn thật.','Tách thành các phiên riêng; không xác nhận nhãn thật cho nguồn mô phỏng.'),
    'SOURCE_MODE_UNAVAILABLE':('Chưa xác định được chế độ nguồn cho tập train.','Chọn các bản ghi đã khả dụng trong snapshot rồi kiểm tra lại.'),
    'FEATURE_SOURCE_NOT_KNOWN_AT_AS_OF':('Khai báo phạm vi nguồn chưa được biết tại as_of.','Dùng bản xuất có phạm vi được xác nhận đúng thời điểm; không lùi ngày khai báo.'),
}


class ReadOnlySnapshots(SnapshotStore):
    """Reuse checksum/scope readers without opening/migrating a writable DB."""
    def __init__(self,path):
        self.path=Path(path).resolve();self.clock=lambda:datetime.now(timezone.utc)
        if not self.path.is_file():fail(404,'SNAPSHOT_NOT_FOUND','Chưa có kho snapshot.','Chọn kho đã lưu, không tạo DB khi tạo đầu vào train.')

    def _connect(self):
        c=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,isolation_level=None);c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON');return c

    @contextmanager
    def _transaction(self,scope,recheck=None):
        self._scope(scope);c=self._connect()
        try:
            c.execute('BEGIN')
            if recheck is not None and recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Kiểm tra lại quyền và yêu cầu.')
            if c.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or c.execute('PRAGMA user_version').fetchone()[0]!=1:fail(503,'STORAGE_VERSION','Kho không đúng phiên bản snapshot.','Chọn đúng kho hiện có.')
            yield c
            if recheck is not None and recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Kiểm tra lại quyền và yêu cầu.')
            c.commit()
        finally:c.close()


def mapping_contract(feature_contract):
    result=dict(version=MAPPING_VERSION,columns=list(COLUMNS),source_contract_version=feature_contract['version'],source_contract_fingerprint=feature_contract['fingerprint'],output_dtype='int64',domains=[[0,1],[0,1]],operation='identity; exact binary numeric -> integer representation only',missing_policy='reject_entire_training_batch; no imputation',
        descriptions={'round_million':'Existing feature: signed VND amount modulo 1,000,000 equals zero.',
                      'creator_equals_approver':'Existing feature: known creator equals the unique known approver; unknown remains missing.'},
        labels_and_identifiers_are_predictors=False,training_batch_rows=4)
    result['fingerprint']=digest(canonical(result));return result


def validate_request(request):
    fields(request,REQUEST_FIELDS);require(request['version']==VERSION,'TRAINING_REQUEST_VERSION')
    require(isinstance(request['snapshot_id'],str) and len(request['snapshot_id'])==36 and request['snapshot_id'].startswith('snp_'),'SNAPSHOT_ID_INVALID')
    as_of,start,end=(utc(request[k]) for k in ('as_of','training_start','training_end'))
    require(start<end<=as_of,'TRAINING_WINDOW_INVALID')
    require(isinstance(request['rows'],list) and len(request['rows'])==4,'TRAINING_ROWS_REQUIRED_EXACTLY_FOUR')
    seen=set()
    for row in request['rows']:
        fields(row,{'record_id','revision'})
        require(isinstance(row['record_id'],str) and 0<len(row['record_id'])<=100,'TRAINING_ROW_ID_INVALID')
        require(type(row['revision']) is int and row['revision']>=1,'TRAINING_REVISION_INVALID')
        require(row['record_id'] not in seen,'DUPLICATE_TRAINING_TRANSACTION');seen.add(row['record_id'])
    return as_of,start,end


def _source_modes(raw,frame,row):
    if raw.get('contract_version')==SOURCE_CONTRACT:return {raw['source']['is_simulated']}
    refs=frame['evidence'][row['row_index']]['records']
    # Only provenance used by these two predictors; do not infer a source mode
    # from unrelated future documents, unused history or the caller's assertion.
    eligible={(r['table'],r['record_id'],r['revision']) for r in refs}
    tx=next(r for r in raw['transactions'] if r['company_id']==row['company_id'] and r['record_id']==row['record_id'] and r['revision']==row['revision'])
    wanted={('transactions',row['record_id'],row['revision'])}
    if tx.get('created_by_ref'):wanted.add(('employees',tx['created_by_ref']['record_id'],tx['created_by_ref']['revision']))
    for approval in raw.get('approvals',[]):
        key=('approvals',approval['record_id'],approval['revision'])
        if approval['company_id']==row['company_id'] and key in eligible and approval['transaction_ref']==dict(record_id=row['record_id'],revision=row['revision']):
            wanted.add(key);wanted.add(('employees',approval['employee_ref']['record_id'],approval['employee_ref']['revision']))
    wanted &= eligible
    return {record['source']['is_simulated'] for table in ('transactions','employees','approvals') for record in raw.get(table,[]) if record['company_id']==row['company_id'] and (table,record['record_id'],record['revision']) in wanted}


def prepare_snapshot_training(store,scope,request,recheck=None):
    """Return ready/rejected preview. Rejected keeps every requested row; no x export."""
    SnapshotStore._scope(scope);as_of,start,end=validate_request(request)
    if recheck is not None and recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.','Kiểm tra lại yêu cầu.')
    manifest=store.get_snapshot(scope,request['snapshot_id'],recheck)
    raw=loads(store.get_snapshot(scope,request['snapshot_id'],recheck,data=True))
    if manifest['contract_version']==SOURCE_CONTRACT:
        frame=build_from_rule_snapshot(store,scope,request['snapshot_id'],request['as_of'],recheck,candidates_only=False,require_exact_source_cutoff=False)
    else:frame=build_from_snapshot(store,scope,request['snapshot_id'],request['as_of'],recheck)
    columns=frame['contract']['columns'];require(all(name in columns for name in COLUMNS),'FEATURE_CONTRACT_INCOMPATIBLE')
    coverage_known=True
    if manifest['contract_version']==SOURCE_CONTRACT:
        coverage=raw['source']['coverage'].get('transactions')
        coverage_known=bool(coverage and utc(coverage['observed_at'])<=as_of)
    contract=mapping_contract(frame['contract']);index={(r['record_id'],r['revision']):r for r in frame['rows']}
    rows=[];issues=[];vectors=[];modes=set()
    for number,wanted in enumerate(request['rows'],1):
        row=index.get((wanted['record_id'],wanted['revision']));entry=dict(row=number,**wanted,available=True,features=None);errors=[]
        def issue(code,field=None,reason=None):
            message,action=TEXT[code];error=dict(row=number,record_id=wanted['record_id'],revision=wanted['revision'],field=field,code=code,reason=reason,message=message,action=action);errors.append(error);issues.append(error)
        if row is None:issue('ROW_NOT_AVAILABLE_AT_AS_OF')
        else:
            require(row['tenant_id']==scope.tenant_id and row['company_id']==next(iter(scope.company_ids)),'FRAME_COMPANY_MISMATCH')
            entry.update(event_at=row['event_at'],knowledge_at=row['as_of'])
            if not start<=utc(row['event_at'])<end or utc(row['as_of'])>as_of:issue('ROW_OUTSIDE_TRAINING_WINDOW')
            at=row['row_index'];values=[]
            for name in COLUMNS:
                col=columns.index(name);value=frame['features'][at][col]
                if not coverage_known:issue('FEATURE_SOURCE_NOT_KNOWN_AT_AS_OF',name)
                elif frame['missing'][at][col] or value is None:issue('FEATURE_MISSING',name,frame['evidence'][at]['missing_reasons'].get(name))
                elif isinstance(value,bool) or not isinstance(value,Real) or not math.isfinite(value) or value not in (0,1):issue('FEATURE_OUT_OF_DOMAIN',name)
                else:values.append(int(value))
            modes.update(_source_modes(raw,frame,row))
            if not errors:entry['features']=values;vectors.append(values)
        entry['available']=not errors;entry['issues']=errors;rows.append(entry)
    if len(modes)!=1:
        code='MIXED_SOURCE_MODES' if modes else 'SOURCE_MODE_UNAVAILABLE';message,action=TEXT[code];issues.append(dict(row=None,record_id=None,revision=None,field='source.is_simulated',code=code,reason=None,message=message,action=action))
    implementation={name:digest(path.read_bytes()) for name,path in [('adapter',Path(__file__)),('canonical_features',Path(__file__).resolve().parents[2]/'sme_fraud/snapshot_features.py'),('rule_snapshot_features',Path(__file__).resolve().parents[2]/'sme_fraud/rule_snapshot_features.py')]}
    result=dict(version=VERSION,status='rejected' if issues else 'ready',tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids)),snapshot={k:manifest[k] for k in ('snapshot_id','tenant_id','company_id','checksum','data_checksum','contract_version')},
        as_of=as_of.isoformat(),training_window=dict(start_inclusive=start.isoformat(),end_exclusive=end.isoformat()),mapping=contract,source_feature_contract=frame['contract'],implementation=implementation,
        requested_rows=request['rows'],rows=rows,row_count=len(rows),issues=issues,simulated=next(iter(modes)) if len(modes)==1 else None,
        x=vectors if not issues else None,row_ids=[r['record_id'] for r in request['rows']],labels_included=False,training_performed=False,source_changed=False)
    result['plan_sha256']=digest(canonical(result))
    if recheck is not None and recheck()!=scope:fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi khi tạo đầu vào train.','Kiểm tra lại quyền và yêu cầu.')
    return result
