"""Isolated QA review work; the source frozen packet and other demos remain untouched."""
import argparse
import json
from pathlib import Path
import threading

from sme_fraud.company_ml import CompanyML
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore
from company_ml_fixture import CHIEF,ACCOUNTANT
from test_data_import import import_fixture
from test_ml_review_web import packet_fixture

ROOT=Path(__file__).resolve().parents[1]


def serve(port=8857):
    work=ROOT/'.runtime/ml_reviews_demo_20261105';marker=work/'demo.json'
    source=ROOT/'.runtime/company_ml_comparison_20261104/run_02'
    if work.exists():
        if not marker.is_file() or json.loads(marker.read_text()).get('kind')!='ml-reviews-qa-v1':raise ValueError('Unknown demo workspace')
        store=ReviewStore(work/'data',work/'reports',work/'review.sqlite3');store.prepare()
    else:
        work.mkdir(parents=True);store,_=import_fixture(work);store.prepare()
        if not source.is_dir():source=packet_fixture(work/'packet_source')
        marker.write_text(json.dumps(dict(kind='ml-reviews-qa-v1',is_synthetic=True,source=str(source))),encoding='utf-8')
    source=Path(json.loads(marker.read_text())['source']);servers=[]
    try:
        for offset,person in enumerate((CHIEF,ACCOUNTANT)):
            server=make_server(store,port=port+offset,qa=True,identity_provider=lambda r,p=person:p,ml_review_roots=[source])
            servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f'{person.role}: http://127.0.0.1:{port+offset}/ml-reviews',flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:
        for server in servers:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8857);serve(parser.parse_args().port)
