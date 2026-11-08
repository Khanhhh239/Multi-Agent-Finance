"""Isolated release QA against the attested integrated snapshot; loopback only.

Fixed synthetic principals are test identities, not an authentication system.
The source, model, historical UAT and detector commitments are read-only.
"""
import argparse
import csv
import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import shutil
import threading

from sme_fraud.feature_contract import sha
from sme_fraud.integrated_rehearsal import fake_people, dry_config
from sme_fraud.notifications import Notifications
from sme_fraud.p2_controls_server import SOURCE, REPORT
from sme_fraud.p2_controls_web import P2Controls
from sme_fraud.review_server import make_server
from sme_fraud.review_store import ReviewStore
from sme_fraud.review_workflow import TwoStageReview

ROOT = Path(__file__).resolve().parents[1]
INTEGRATED = ROOT/'reports/integrated_rehearsal_20261028_v2'
QA = ROOT/'.runtime/release_acceptance_20261029/workspace'
EVIDENCE = ROOT/'reports/release_acceptance_20261029'
NOW = '2026-10-29T10:00:00+07:00'
PORT = 8841


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def prepare():
    if QA.exists():
        raise FileExistsError('Refusing to overwrite a QA workspace')
    QA.mkdir(parents=True)
    for tag in ('001','003'):
        source = INTEGRATED/'baseline'/('sme_fraud_'+tag)
        target = QA/'snapshots'/source.name
        target.mkdir(parents=True)
        for name in json.loads((source/'predictions_frozen.json').read_text(encoding='utf-8'))['files']:
            shutil.copyfile(source/name, target/name)
    write(QA/'marker.json', dict(kind='release-acceptance-20261029', is_synthetic=True,
        source_root=str(INTEGRATED/'source'), source_commitment_sha256=sha(INTEGRATED/'commitment.json'),
        simulated_clock=NOW, independent_reviews=0, actual_review_minutes=None,
        external_messages_sent=0, real_accounts_created=0))
    store, workflow, companies = stores()
    with (ROOT/'reports/browser_acceptance_20261020/sample_results.csv').open(encoding='utf-8-sig',newline='') as stream:
        samples = list(csv.DictReader(stream))
    with store.connection() as db:
        cases = {(r['scenario'],r['case_id']) for r in db.execute('SELECT scenario,case_id FROM cases')}
    for row in samples:
        if row['kind']=='case' and (row['scenario'], row['case_id']) not in cases:
            raise AssertionError('Historical sample not in integrated snapshot: '+row['sample_id'])
        row['current_url'] = f'http://127.0.0.1:{PORT}/'+(
            'p2-controls#control='+row['control_id'] if row['kind']=='p2_control'
            else '#scenario='+row['scenario']+'&case='+row['case_id'])
    write(EVIDENCE/'sample_plan.json', samples)
    write(EVIDENCE/'workspace.json', dict(workspace=str(QA), source_root=str(INTEGRATED/'source'),
        cases=len(cases), companies=companies, fake_roles=['accountant','chief_accountant','director','anonymous','accountant_C001'],
        ports=list(range(PORT,PORT+5)), simulated=True, independent_reviews=0, actual_review_minutes=None))
    print(json.dumps(dict(cases=len(cases),historical_samples=len(samples),workspace=str(QA))))


def stores():
    marker=json.loads((QA/'marker.json').read_text(encoding='utf-8'))
    if marker['kind']!='release-acceptance-20261029' or marker['is_synthetic'] is not True:
        raise ValueError('Not an isolated synthetic QA workspace')
    store=ReviewStore(INTEGRATED/'source', QA/'snapshots', QA/'review.sqlite3',scenarios=['001','003'],
        clock=lambda:datetime.fromisoformat(NOW))
    store.prepare()
    companies=sorted(r['company_id'] for r in store.metadata()['companies'])
    return store,TwoStageReview(store),companies


def serve():
    store,workflow,companies=stores()
    config=dry_config(companies,PORT)
    controls=P2Controls(SOURCE,REPORT,QA/'p2_uat.sqlite3')
    actors=[replace(actor,company_ids=tuple(companies)) for actor in fake_people('C001')]
    actors += [None, fake_people('C001')[0]]
    servers=[]
    try:
        for offset,actor in enumerate(actors):
            # Each fake identity has its own loopback origin. Production has
            # one origin and real login; a QA link must not switch fake roles.
            notifications=Notifications(store,{**config,'case_url':f'http://127.0.0.1:{PORT+offset}/'})
            server=make_server(store,port=PORT+offset,qa=True,instance_id='RELEASE_QA_20261029',
                notifications=notifications,p2_controls=controls,review_workflow=workflow,
                identity_provider=lambda request,p=actor:p)
            servers.append(server)
        write(QA/'server.json',dict(pid=os.getpid(),ports=[s.server_port for s in servers],
            started_at=datetime.now().astimezone().isoformat(),synthetic=True))
        for server in servers:
            threading.Thread(target=server.serve_forever,daemon=True).start()
        print('Synthetic release acceptance: ports 8841 accountant, 8842 chief, 8843 director, 8844 readonly, 8845 C001 accountant',flush=True)
        threading.Event().wait()
    finally:
        for server in servers:
            server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','serve'])
    args=parser.parse_args()
    (prepare if args.command=='prepare' else serve)()
