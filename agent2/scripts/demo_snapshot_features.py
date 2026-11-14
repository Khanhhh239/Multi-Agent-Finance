"""Synthetic snapshot -> authenticated feature job; no Portal or model required."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sme_fraud.auth import FileAuthorizer
from sme_fraud.feature_pipeline import run_job,read_artifact
from sme_fraud.import_files import canonical
from sme_fraud.snapshots import SnapshotStore


def main():
    source=json.loads((ROOT/'tests/fixtures/r1_feature_replay_v1.json').read_text('utf-8'))
    for table,rows in source.items():
        if isinstance(rows,list):source[table]=[r for r in rows if r['company_id']=='C001']
    token=secrets.token_urlsafe(32);run=uuid.uuid4().hex
    store=SnapshotStore(ROOT/'.runtime/feature_demo/snapshots.sqlite3')
    with tempfile.TemporaryDirectory(prefix='agent2_feature_demo_') as temporary:
        policy=Path(temporary)/'policy.json'
        policy.write_bytes(canonical(dict(policy_version='1.0.0',principals=[dict(actor_id='feature-demo',tenant_id='demo',
            token_sha256=hashlib.sha256(token.encode()).hexdigest(),status='active',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            memberships=[dict(company_id='C001',role='accountant',status='active',permissions=['data.import'])])])))
        auth=FileAuthorizer(policy);header='Bearer '+token
        scope=auth.authorize(header,'C001');recheck=lambda:auth.authorize(header,'C001')
        draft=store.upload(scope,canonical(source),'feature-demo.json',run+'-upload',recheck)
        preview=store.preview(scope,draft['import_id'],1,recheck)
        body={k:preview[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')}
        body.update(expected_revision=1,acknowledge=True)
        snapshot=store.commit(scope,draft['import_id'],body,run+'-commit',recheck)['snapshot']
        saved=run_job(store,auth,header,'C001',snapshot['snapshot_id'],'2026-10-10T11:00:00+07:00',ROOT/'.runtime/feature_demo/features')
        artifact=read_artifact(saved['directory']);columns=artifact['contract']['columns']
        print('Demo dữ liệu mô phỏng; chỉ tạo feature, không fit/chấm ML.')
        print('Snapshot:',snapshot['snapshot_id'])
        print('Đã tạo:',len(artifact['rows']),'dòng ·',len(columns),'biến dự báo')
        for row,evidence in zip(artifact['rows'],artifact['evidence']):
            if row['record_id'] in ('T001','T002'):
                print(row['record_id']+': cùng nhìn',evidence['history_type_record_count'],'giao dịch trước nhóm')
        later=run_job(store,auth,header,'C001',snapshot['snapshot_id'],'2026-10-13T00:00:00+07:00',ROOT/'.runtime/feature_demo/features')
        later_artifact=read_artifact(later['directory'])
        first={r['record_id']:artifact['features'][r['row_index']] for r in artifact['rows']}
        second={r['record_id']:later_artifact['features'][r['row_index']] for r in later_artifact['rows']}
        assert first['T001']==second['T001'] and first['T002']==second['T002']
        print('Chạy as_of muộn hơn: feature quá khứ T001/T002 giữ nguyên.')
        print('Biến dự báo: features.json; mã dòng: rows.json; nguồn đối chiếu: evidence.json.')
        print('Artifact:',saved['directory'])
        print('Checksum:',saved['manifest']['checksum'])
    return 0


if __name__=='__main__':raise SystemExit(main())
