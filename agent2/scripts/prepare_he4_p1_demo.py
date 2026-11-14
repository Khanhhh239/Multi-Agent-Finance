"""Build P1 source examples and optionally append them to the local demo store.

No fit, key rotation, credential, role, worker restart or queue mutation.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from experiments.he4.p1_demo import VERSION,source,save_snapshot,inspect
from sme_fraud.import_files import canonical,digest
from sme_fraud.snapshots import SnapshotStore


def prepare(output,state,publish=False):
    output=output.resolve();state=state.resolve()
    if output.exists():raise ValueError('new example directory required')
    if state.exists():raise ValueError('new evidence/state directory required')
    output.mkdir(parents=True);state.mkdir(parents=True)
    store=SnapshotStore(state/'snapshots.sqlite3');reports=[];published=[]
    for company in ('C001','C002'):
        data=source(company);(output/(company+'_P1_5_ca_8_ban_ghi.json')).write_bytes(canonical(data))
        sid=save_snapshot(store,company,data);report,_=inspect(store,company,sid);reports.append(report)
        (state/(company+'-engine-comparison.json')).write_bytes(canonical(report))
    if publish:
        # A narrow explicit operator import into the existing simulated demo.
        # The ordinary snapshot API still checks all source/mapping manifests.
        node_path=ROOT/'.runtime/he-company-demo/enterprise/node.json';node=json.loads(node_path.read_bytes())
        database=Path(node['snapshot_db']).resolve();expected=ROOT/'.runtime/he-company-demo/enterprise/snapshots.sqlite3'
        if database!=expected.resolve() or not database.is_file():raise ValueError('only the configured existing local demo database may be extended')
        backup=state/'before-live-import.sqlite3'
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as old,sqlite3.connect(backup) as copy:old.backup(copy)
        live=SnapshotStore(database)
        for company in ('C001','C002'):
            data=source(company);sid=save_snapshot(live,company,data);report,_=inspect(live,company,sid)
            published.append(dict(company_id=company,snapshot_id=sid,row_count=8,checksum=digest(canonical(data))))
    manifest=dict(version=VERSION,created_at=datetime.now(timezone.utc).isoformat(),data_kind='synthetic_only',
        scenario_count=5,rows_per_company=8,history_and_adjustments_retained=True,expected_results_not_in_source=True,
        source_files={p.name:digest(p.read_bytes()) for p in output.glob('*.json')},
        checks=[dict(company_id=r['company_id'],statuses=r['statuses'],manual_expected_parity=True,retained_engine_parity=True,plain_circuit_parity=True) for r in reports],
        actual_fhe=False,published_snapshots=published,model_fit_performed=False,keys_changed=False,permissions_changed=False,queue_written=False)
    (state/'report.json').write_bytes(canonical(manifest));(output/'demo_manifest.json').write_bytes(canonical(manifest))
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--publish-local-demo',action='store_true');a=p.parse_args();prepare(a.output,a.state,a.publish_local_demo)
