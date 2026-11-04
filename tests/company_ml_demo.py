"""Standalone synthetic web demo; fixed QA identities, isolated database, no external delivery."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import threading

from sme_fraud.company_ml import CompanyML
from company_ml_fixture import fixture, label_text, CHIEF, ACCOUNTANT
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore

ROOT=Path(__file__).resolve().parents[1]
DEMO=ROOT/'.runtime/company_ml_demo_20261104'


def serve(port=8851):
    marker=DEMO/'demo.json'
    if DEMO.exists():
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')).get('kind')!='company-ml-synthetic-demo-v1':
            raise ValueError('Refusing to reuse an unknown workspace')
        store=ReviewStore(DEMO/'data',DEMO/'reports',DEMO/'review.sqlite3',
                          clock=lambda:datetime.fromisoformat('2026-11-04T10:00:00+07:00'))
        store.prepare()
    else:
        DEMO.mkdir(parents=True)
        store,_,records=fixture(DEMO)
        (DEMO/'SIMULATED_reviewed_labels_C001.csv').write_text(label_text(records),encoding='utf-8')
        marker.write_text(json.dumps(dict(kind='company-ml-synthetic-demo-v1',is_synthetic=True,
            independent_reviews=0,actual_review_minutes=None)),encoding='utf-8')
    servers=[]
    try:
        for offset,(label,principal) in enumerate((('chief',CHIEF),('accountant_readonly',ACCOUNTANT))):
            server=make_server(store,port=port+offset,qa=True,identity_provider=lambda request,p=principal:p)
            servers.append(server)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f'{label}: http://127.0.0.1:{server.server_port}/company-ml',flush=True)
        print('Simulated CSV labels: '+str(DEMO/'SIMULATED_reviewed_labels_C001.csv'),flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8851)
    serve(parser.parse_args().port)
