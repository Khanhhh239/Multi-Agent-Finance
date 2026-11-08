"""Fresh, synthetic label-merge QA server; never reuses or changes another demo."""
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
from company_ml_fixture import CHIEF, ACCOUNTANT, label_text
from test_data_import import import_fixture, upload_rows, csv_bytes


def serve(root,port):
    root=Path(root).resolve()
    if root.exists():raise FileExistsError('Use a fresh QA directory; existing data will not be reset.')
    root.mkdir(parents=True)
    store,_=import_fixture(root);ml=CompanyML(store);importer=DataImport(ml)
    for company in ('C001','C002'):
        preview=importer.preview('003',company,CHIEF,filename='SIM.csv',expected_revision=None,
            content_base64=base64.b64encode(csv_bytes(upload_rows(company,count=30))).decode())
        state=importer.commit('003',company,CHIEF,token=preview['token'],acknowledge=True)['status']
        with store.connection() as db:records=ml._data(db,company)[2]
        rows=list(csv.DictReader(io.StringIO(label_text(records,company))))
        state=ml.update_labels('003',company,CHIEF,expected_revision=state['data']['revision'],
                              labels_text=csv_bytes(rows[:15] if company=='C001' else rows[:1]).decode('utf-8-sig'))
        revision=state['data']['revision']
        state=ml.evaluate('003',company,CHIEF,expected_revision=revision,algorithm='ecod',alert_budget=.1,
                          **state['data']['suggested_windows'])
        ml.activate('003',company,CHIEF,expected_revision=revision,expected_active=None,version_id=state['versions'][0]['version_id'])
        if company=='C001':
            for name,values in dict(identical=rows[:1],new=rows[15:16],
                conflicts=[dict(rows[0],label='1' if rows[0]['label']=='0' else '0',evidence_ref='SIM_NEW_EVIDENCE'),rows[16]],
                invalid=[dict(rows[0],company_id='C002')]).items():
                (root/f'SIM_{name}.csv').write_bytes(csv_bytes(values))
            (root/'SIM_all_labels.csv').write_bytes(csv_bytes(rows))
    (root/'demo.json').write_text(json.dumps(dict(kind='company-ml-labels-demo-v1',is_synthetic=True)),encoding='utf-8')
    servers=[]
    try:
        for offset,principal in enumerate((CHIEF,ACCOUNTANT)):
            server=make_server(store,port=port+offset,qa=True,identity_provider=lambda request,p=principal:p)
            servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f'{principal.role}: http://127.0.0.1:{port+offset}/company-ml',flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:
        for server in servers:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8859)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'.runtime/company_ml_labels_demo_20261106')
    args=parser.parse_args();serve(args.root,args.port)
