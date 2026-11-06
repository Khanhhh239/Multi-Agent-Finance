"""Isolated synthetic CSV/XLSX import demo; never changes the older ML demo."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import threading

from sme_fraud.company_ml import CompanyML  # scientific environment before legacy helpers
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore
from company_ml_fixture import CHIEF, ACCOUNTANT
from test_data_import import import_fixture, upload_rows, csv_bytes, xlsx_bytes

ROOT=Path(__file__).resolve().parents[1]/'.runtime/data_import_demo_20261104'


def serve(port=8853,root=None):
    root=Path(root).resolve() if root is not None else ROOT
    marker=root/'demo.json'
    if root.exists():
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')).get('kind')!='synthetic-data-import-demo-v1':
            raise ValueError('Refusing to reuse an unknown workspace')
        store=ReviewStore(root/'data',root/'reports',root/'review.sqlite3',
                          clock=lambda:datetime.fromisoformat('2026-11-04T10:00:00+07:00'))
        store.prepare()
    else:
        root.mkdir(parents=True)
        store,_=import_fixture(root)
        marker.write_text(json.dumps(dict(kind='synthetic-data-import-demo-v1',is_synthetic=True)),encoding='utf-8')
        for company in ('C001','C002'):
            rows=upload_rows(company,count=30)
            (root/f'SIMULATED_{company}.csv').write_bytes(csv_bytes(rows))
            (root/f'SIMULATED_{company}.xlsx').write_bytes(xlsx_bytes(rows))
        rows=upload_rows();rows[1]['transaction_id']=rows[0]['transaction_id'];rows[2]['created_at']='invalid'
        (root/'SIMULATED_errors.csv').write_bytes(csv_bytes(rows))
    servers=[]
    packet=ROOT.parent/'company_ml_comparison_20261104/run_02'
    packets=[packet] if root==ROOT and (packet/'manifest.json').is_file() else []
    try:
        for offset,principal in enumerate((CHIEF,ACCOUNTANT)):
            server=make_server(store,port=port+offset,qa=True,identity_provider=lambda r,p=principal:p,ml_review_roots=packets)
            servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f'{principal.role}: http://127.0.0.1:{port+offset}/data-import',flush=True)
        print('Synthetic sample files: '+str(root),flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:
        for server in servers:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8853)
    parser.add_argument('--root',type=Path,help='Use a separate workspace for destructive import QA')
    args=parser.parse_args();serve(args.port,args.root)
