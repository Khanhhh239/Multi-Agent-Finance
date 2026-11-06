"""QA-only form eligibility demo, isolated from all existing company snapshots."""
import argparse
import base64
import csv
from datetime import datetime
import io
import json
from pathlib import Path
import threading

from sme_fraud.company_ml import CompanyML
from sme_fraud.data_import import DataImport
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore
from company_ml_fixture import CHIEF, ACCOUNTANT, label_text
from test_data_import import import_fixture, upload_rows, csv_bytes

ROOT=Path(__file__).resolve().parents[1]/'.runtime/company_ml_readiness_demo_20261105'


def seed():
    store,_=import_fixture(ROOT);ml=CompanyML(store);importer=DataImport(ml)
    # C002 starts with a model from the connected-cache format.
    state=ml.update_data('003','C002',CHIEF,expected_revision=None)
    revision=state['data']['revision']
    state=ml.evaluate('003','C002',CHIEF,expected_revision=revision,algorithm='ecod',alert_budget=.1,
                      train_end='2024-01-20T00:00:00+07:00',calibration_end='2024-01-25T00:00:00+07:00')
    ml.activate('003','C002',CHIEF,expected_revision=revision,expected_active=None,version_id=state['versions'][0]['version_id'])
    for company in ('C001','C002'):
        before=ml.status('003',company,CHIEF)
        preview=importer.preview('003',company,CHIEF,filename='SIMULATED.csv',
            content_base64=base64.b64encode(csv_bytes(upload_rows(company,count=30))).decode(),
            expected_revision=before['data']['revision'] if before['data'] else None)
        state=importer.commit('003',company,CHIEF,token=preview['token'],acknowledge=True)['status']
        with store.connection() as db:records=ml._data(db,company)[2]
        rows=list(csv.DictReader(io.StringIO(label_text(records if company=='C001' else records[:1],company))))
        if company=='C001':rows[0]['reviewed_at']='2024-01-12T12:00:00+07:00'
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
        state=ml.update_labels('003',company,CHIEF,expected_revision=state['data']['revision'],labels_text=stream.getvalue())
        if company=='C001':
            revision=state['data']['revision']
            state=ml.evaluate('003',company,CHIEF,expected_revision=revision,algorithm='isolation_forest',alert_budget=.1,
                              **state['data']['suggested_windows'])
            ml.activate('003',company,CHIEF,expected_revision=revision,expected_active=None,version_id=state['versions'][0]['version_id'])
    return store


def serve(port=8855):
    marker=ROOT/'demo.json'
    if ROOT.exists():
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')).get('kind')!='company-ml-readiness-demo-v1':
            raise ValueError('Refusing to reuse unknown workspace')
        store=ReviewStore(ROOT/'data',ROOT/'reports',ROOT/'review.sqlite3',clock=lambda:datetime.fromisoformat('2026-11-05T10:00:00+07:00'))
        store.prepare()
    else:
        ROOT.mkdir(parents=True);store=seed()
        marker.write_text(json.dumps(dict(kind='company-ml-readiness-demo-v1',is_synthetic=True)),encoding='utf-8')
    servers=[]
    try:
        for offset,principal in enumerate((CHIEF,ACCOUNTANT)):
            server=make_server(store,port=port+offset,qa=True,identity_provider=lambda r,p=principal:p)
            servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f'{principal.role}: http://127.0.0.1:{port+offset}/company-ml',flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:
        for server in servers:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8855)
    serve(parser.parse_args().port)
