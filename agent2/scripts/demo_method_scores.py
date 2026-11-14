"""Synthetic normalized-output demo. No labels, release, active config or queue."""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical
from sme_fraud.method_adapters import fit_local_reference, native_inputs, score_batch, score_snapshot
from sme_fraud.rule_audit_cases import Case
from sme_fraud.snapshot_features import build_from_snapshot
from sme_fraud.snapshots import SnapshotStore

VN = timezone(timedelta(hours=7))


def canonical_source():
    source = json.loads((ROOT/'tests/fixtures/r1_feature_replay_v1.json').read_text('utf-8'))
    for table, rows in source.items():
        if isinstance(rows, list): source[table] = [r for r in rows if r['company_id'] == 'C001']
    tx_template = next(t for t in source['transactions'] if t['record_id'] == 'T001')
    alloc_template = next(a for a in source['payment_allocations'] if a['record_id'] == 'A_T001')
    source['transactions'] = []; source['payment_allocations'] = []
    source['approvals'] = []; source['supporting_documents'] = []
    for prefix, count, origin in (('H',10,datetime(2026,9,2,11,tzinfo=VN)),
                                  ('R',5,datetime(2026,9,15,11,tzinfo=VN)),
                                  ('T',5,datetime(2026,10,1,11,tzinfo=VN))):
        for index in range(count):
            identity = prefix+str(index)
            at = (origin+timedelta(days=index)).isoformat()
            amount = 1000003+index*17239 if prefix != 'T' else 1100003+index*17239
            if prefix == 'T' and index == 4: amount = 9000007
            tx = copy.deepcopy(tx_template)
            tx.update(record_id=identity, effective_at=at, observed_at=at, amount_vnd=amount,
                      description='Synthetic method-output demo '+identity,
                      accounting_lines=[dict(account='331',debit_vnd=amount,credit_vnd=0),dict(account='112',debit_vnd=0,credit_vnd=amount)])
            tx['source']['record_id'] = identity
            allocation = copy.deepcopy(alloc_template)
            allocation.update(record_id='A_'+identity,effective_at=at,observed_at=at,amount_vnd=amount,
                              transaction_ref=dict(record_id=identity,revision=1))
            allocation['source']['record_id'] = 'A_'+identity
            source['transactions'].append(tx); source['payment_allocations'].append(allocation)
    return source


def subset(frame, prefix):
    result = copy.deepcopy(frame)
    indexes = [i for i,r in enumerate(frame['rows']) if r['record_id'].startswith(prefix)]
    for channel in ('features','missing','rows','evidence'):
        result[channel] = [result[channel][i] for i in indexes]
    for index, (row,evidence) in enumerate(zip(result['rows'],result['evidence'])):
        row['row_index'] = evidence['row_index'] = index
    return result


def native_frame(at, scope, *, trigger=False):
    case = Case(); case.vendor['name'] = 'Orchid marine instruments'
    for i in range(5):
        event = at+timedelta(days=7*i)
        values = dict(created_at=event.isoformat(),approved_at=(event+timedelta(minutes=5)).isoformat())
        if trigger and i == 0: values['approver_id'] = case.maker['employee_id']
        case.pay(event,int(case.maker['self_approval_limit_vnd'])+1 if trigger and i == 0 else 500003+137*i,
                 transaction_id=f'NATIVE_{at:%Y%m%d}_{i}',**values)
    case.score()
    return native_inputs(case.tables,scope,config=case.config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'.runtime/method_demo/output.json'))
    parser.add_argument('--database',default=str(ROOT/'.runtime/method_demo/snapshots.sqlite3'))
    args = parser.parse_args()
    token = secrets.token_urlsafe(32); run = uuid.uuid4().hex
    store = SnapshotStore(args.database)
    with tempfile.TemporaryDirectory(prefix='r2_method_demo_') as temporary:
        policy = Path(temporary)/'policy.json'
        policy.write_bytes(canonical(dict(policy_version='1.0.0',principals=[dict(actor_id='method-demo',tenant_id='demo',
            token_sha256=hashlib.sha256(token.encode()).hexdigest(),status='active',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            memberships=[dict(company_id='C001',role='accountant',status='active',permissions=['data.import'])])])))
        auth = FileAuthorizer(policy); header = 'Bearer '+token
        scope = auth.authorize(header,'C001'); recheck = lambda:auth.authorize(header,'C001')
        source = canonical_source()
        draft = store.upload(scope,canonical(source),'method-demo.json',run+'-upload',recheck)
        preview = store.preview(scope,draft['import_id'],1,recheck)
        body = {k:preview[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')}
        body.update(expected_revision=1,acknowledge=True)
        snapshot_id = store.commit(scope,draft['import_id'],body,run+'-commit',recheck)['snapshot']['snapshot_id']
        history = build_from_snapshot(store,scope,snapshot_id,'2026-09-12T00:00:00+07:00',recheck)
        reference = subset(build_from_snapshot(store,scope,snapshot_id,'2026-09-20T00:00:00+07:00',recheck),'R')
        methods = ('ecod','robust_z')
        artifacts = {m:fit_local_reference(history,reference,scope,m,
            selected_columns=['log_abs_amount','amount_negative','event_hour_sin','kind_payment'],
            minimum_history=5,profile_id='synthetic-technical-demo-only-not-D03-production') for m in methods}
        canonical_result = score_snapshot(store,scope,snapshot_id,'2026-10-06T00:00:00+07:00',
            artifacts=artifacts,methods=methods,recheck=recheck)
        native_history,_,_ = native_frame(datetime(2025,1,7,11,tzinfo=VN),scope)
        native_reference,_,_ = native_frame(datetime(2025,6,3,11,tzinfo=VN),scope)
        native_test,rules,graphs = native_frame(datetime(2025,8,12,11,tzinfo=VN),scope,trigger=True)
        native_artifacts = {m:fit_local_reference(native_history,native_reference,scope,m,
            selected_columns=['log_amount','amount_limit_ratio','hour_sin'],minimum_history=5,
            profile_id='native-technical-routing-only') for m in methods}
        native_result = score_batch(native_test,scope,artifacts=native_artifacts,methods=methods,rule_output=rules,graphs=graphs)
        new_rows = [r for r in canonical_result['rows'] if r['record_id'].startswith('T')]
        no_hit = [r for r in native_result['rows'] if r['methods']['rules']['score'] == 0]
        assert len(new_rows) == 5 and all(r['methods']['ecod']['available'] for r in new_rows)
        assert no_hit and all(r['methods']['ecod']['available'] for r in native_result['rows'])
        output = dict(data_kind='synthetic_technical_demo_not_accuracy',canonical=canonical_result,native=native_result,
            fit_manifests={a.artifact_id:json.loads(a.manifest) for a in [*artifacts.values(),*native_artifacts.values()]},
            limitations=['Canonical rules need a faithful source bridge; unavailable is not a zero rule score.',
                         'Local fit bundles are in-memory only; persistent worker/registry and benchmark remain R2 work.',
                         'All old rows remain in output; this newer artifact cannot score its own past.',
                         'Midranks are not fraud probabilities. No labels or active delivery.'])
        path = Path(args.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(canonical(output))
        print('Dữ liệu mô phỏng, chưa đánh giá độ chính xác ML.')
        print('Snapshot:',snapshot_id,'| tổng dòng trả về:',canonical_result['row_count'],'| giao dịch mới được ML chấm:',len(new_rows))
        for row in native_result['rows']:
            print(row['record_id'],'| điểm luật:',row['methods']['rules']['score'],'| ML khả dụng:',row['methods']['ecod']['available'],'| điểm ML:',row['methods']['ecod']['score'])
        print('Có',len(no_hit),'dòng điểm luật bằng 0 vẫn được ML chấm.')
        print('Kết quả:',path.resolve())
    return 0


if __name__=='__main__':raise SystemExit(main())
