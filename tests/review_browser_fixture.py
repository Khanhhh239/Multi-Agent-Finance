"""Loopback-only browser QA with fixed simulated identities and a fresh fixture.

This is a test launcher, not an authentication implementation. No role/name
from a browser request is trusted. Real application data cannot be selected.
"""
import argparse
import json
import threading
from datetime import datetime
from pathlib import Path

from sme_fraud.generate import write_csv
from sme_fraud.notifications import Notifications
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_workflow import TwoStageReview
from test_review import make_fixture

ROOT=Path(__file__).resolve().parents[1]
QA_ROOT=ROOT/'.runtime/browser_workflow_20261027'
ACTORS={
    'accountant':ReviewPrincipal('SIM_ACC01','SIM_PERSON01','MÔ PHỎNG · Kế toán viên An','accountant',('C001',)),
    'chief':ReviewPrincipal('SIM_CHIEF02','SIM_PERSON02','MÔ PHỎNG · Kế toán trưởng Bình','chief_accountant',('C001',)),
    'director':ReviewPrincipal('SIM_DIR03','SIM_PERSON03','MÔ PHỎNG · Giám đốc Chi','director',('C001',)),
    'anonymous':None,
}


def prepare_workspace(workspace):
    workspace=Path(workspace).resolve()
    if workspace==QA_ROOT.resolve() or not workspace.is_relative_to(QA_ROOT.resolve()):
        raise ValueError('Browser QA must use a separate child of its dedicated .runtime folder')
    for path in (workspace,*workspace.parents):
        if path==ROOT.parent:break
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('Linked QA workspace rejected')
    marker=workspace/'browser_qa.json'
    if workspace.exists():
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')).get('kind')!='synthetic-browser-review-v1':
            raise ValueError('Refusing to serve a non-QA workspace')
    else:
        workspace.mkdir(parents=True)
        data,_=make_fixture(workspace)
        # Pleasant sample names; this workspace never imports a saved dataset.
        write_csv(data/'vendors.csv',[dict(vendor_id='V01',company_id='C001',name='Công ty minh hoạ An Phú',
            recorded_at='2023-01-01T00:00:00+07:00',bank_account='BANK01',phone='PHONE2')])
        marker.write_text(json.dumps(dict(kind='synthetic-browser-review-v1',is_synthetic=True,
            accounts_created=0,independent_reviews=0),indent=2),encoding='utf-8')
    store=ReviewStore(workspace/'data',workspace/'reports',workspace/'review.sqlite3',
                      clock=lambda:datetime.fromisoformat('2026-10-27T10:00:00+07:00'))
    store.prepare();store.set_budget(10)
    return store,TwoStageReview(store)


def serve(workspace,base_port=8791):
    if type(base_port) is not int or not 1024<=base_port<=65532:raise ValueError('Invalid test port range')
    store,workflow=prepare_workspace(workspace)
    servers=[]
    try:
        for offset,(role,actor) in enumerate(ACTORS.items()):
            port=base_port+offset
            server=make_server(store,port=port,qa=True,instance_id='browser-workflow-qa-'+role,
                notifications=Notifications(store,dict(dry_run=True,case_url=f'http://127.0.0.1:{port}/')),
                review_workflow=workflow,identity_provider=lambda request,person=actor:person)
            servers.append(server)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            print(f'{role}: http://127.0.0.1:{port}/#scenario=003&case=RC_1',flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=QA_ROOT/'fixture')
    parser.add_argument('--base-port',type=int,default=8791)
    options=parser.parse_args();serve(options.workspace,options.base_port)
