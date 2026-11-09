"""Validate exports with each agent's native code and create isolated runtime state."""
import argparse
import base64
import csv
import json
import shutil
import sys
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def a1(folder):
    sys.path.insert(0, str(REPO / 'agent1'))
    import pandas as pd
    from cryptography.fernet import Fernet
    from agent1.adaptive.data import SCHEMAS, parse_rows, suggested_mapping, validate_dataset, fingerprint
    from agent1_service.store import Store
    root = folder / 'runtime/a1'; root.mkdir(parents=True, exist_ok=True)
    data = {kind: [] for kind in SCHEMAS}
    for kind in SCHEMAS:
        for path in sorted((folder / 'inputs/a1').rglob('*_'+kind+'.csv')):
            raw = pd.read_csv(path, dtype=str, keep_default_na=False)
            rows, errors, warnings = parse_rows(raw, kind, suggested_mapping(raw.columns, kind), '%Y-%m-%d', 'plain')
            if errors: raise ValueError((str(path), errors[:5]))
            data[kind].extend(rows)
        print(kind, len(data[kind]), flush=True)
    assert len(data['invoices']) == 50000
    validate_dataset(data)
    keys = root / 'keys'; keys.mkdir(exist_ok=True)
    keyfile = keys / 'encryption.key'
    if not keyfile.exists(): keyfile.write_bytes(Fernet.generate_key())
    store = Store(root / 'state/agent1.db', keyfile.read_bytes())
    version = fingerprint(data)
    counts = {k: len(v) for k,v in data.items()}
    store.put_many('MPX10', {'company_datasets': [dict(id=version, data=data, created_at=datetime.now(timezone.utc).isoformat())],
                           'company_dataset_active': [dict(id='active', version=version, counts=counts)]})
    store.connection.close()
    save(root / 'validation.json', dict(passed=True, counts=counts, version=version))


def a2(folder):
    sys.path.insert(0, str(REPO / 'agent2'))
    from sme_fraud.review_store import ReviewStore
    from sme_fraud.company_ml import CompanyML
    from sme_fraud.data_import import DataImport
    from sme_fraud.review_roles import ReviewPrincipal
    from sme_fraud.rules import score_rules, INPUT_TABLES, OPTIONAL_INPUT_TABLES
    from sme_fraud.features import build_features
    from sme_fraud.case_queue import review_queue
    from sme_fraud.generate import write_csv
    root = folder / 'runtime/a2'; source = root / 'data/sme_fraud_003'; report = root / 'reports/sme_fraud_003'
    source.mkdir(parents=True, exist_ok=True); report.mkdir(parents=True, exist_ok=True)
    for path in (folder / 'inputs/a2').glob('*.csv'):
        shutil.copy2(path, source / ('transactions.csv' if path.name=='transactions_full.csv' else path.name))
    store = ReviewStore(root/'data', root/'reports', root/'review.sqlite3', scenarios=['003'])
    company = next(csv.DictReader((source/'companies.csv').open(encoding='utf-8-sig')))
    with store.connection() as db:
        db.execute('INSERT OR REPLACE INTO companies VALUES(?,?,?)', ('003','MPX10',json.dumps(company)))
    importer = DataImport(CompanyML(store))
    principal = ReviewPrincipal('dataset-generator','dataset-generator','Nạp dữ liệu mô phỏng','director',('MPX10',))
    with store.connection() as db:
        row = db.execute('SELECT revision FROM company_ml_data WHERE company_id=?',('MPX10',)).fetchone()
    preview = importer.preview('003','MPX10',principal,filename='transactions.csv',
        content_base64=base64.b64encode((source/'transactions.csv').read_bytes()).decode(), expected_revision=row[0] if row else None)
    save(root/'preview.json', {k:v for k,v in preview.items() if k!='token'})
    if not preview['valid']: raise ValueError(preview['errors'][:5])
    records = importer.pending[preview['token']]['records']
    tables = {}
    for name in (*INPUT_TABLES,*OPTIONAL_INPUT_TABLES):
        path=source/(name+'.csv')
        tables[name]=list(csv.DictReader(path.open(encoding='utf-8-sig'))) if path.exists() else []
    tables['transactions']=records
    print('A2 native preview passed; computing rules',flush=True)
    features=build_features(tables)
    result=score_rules(tables,features=features)
    cases,events=review_queue(result,tables)
    write_csv(report/'rule_scores.csv',[{k:v for k,v in r.items() if k!='known_risky_prior_ids'} for r in result['scores']])
    write_csv(report/'case_queue.csv',cases,list(cases[0]) if cases else ['case_id','company_id','status','owner_id','priority','explanation_vi'])
    write_csv(report/'case_events.csv',events,['case_id','event_at','event','transaction_id','rule_score','priority'])
    for name,rows in [('rule_hits',result['hits']),('batch_events',result['batch_events'])]:
        (report/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    save(report/'rule_coverage.json',result['coverage']);save(report/'rule_config.json',result['config'])
    if result.get('dynamic_policy'):
        from sme_fraud.a5_coverage import write_coverage
        from sme_fraud.threshold_artifacts import write_parameters
        write_coverage(report,result)
        write_parameters(report,result['dynamic_parameters'],result['dynamic_policy'],result['dynamic_source_summary'])
    # Persist normalized rows so the review cache and ML snapshot share exactly one source.
    write_csv(source/'transactions.csv',records)
    store.prepare()
    importer.commit('003','MPX10',principal,token=preview['token'],acknowledge=True)
    save(root/'validation.json',dict(passed=True,transactions=len(records),cases=len(cases),rule_hits=len(result['hits'])))


def a3(folder):
    sys.path.insert(0,str(REPO/'agent3/agent3_tax_compliance'))
    from src.assistant import pipeline, report
    root=folder/'runtime/a3';root.mkdir(parents=True,exist_ok=True)
    pack=json.loads((folder/'inputs/a3/pack.json').read_text(encoding='utf-8'))
    ws=root/pack['profile']['tax_code'];ws.mkdir(exist_ok=True)
    shutil.copy2(folder/'inputs/a3/pack.json',ws/'pack.json')
    save(ws/'labels.json',dict(as_of='2026-10-14'))
    for path in sorted((folder/'inputs/a3').rglob('*.zip')):
        role=path.stem.split('_')[0];dest=ws/'invoices'/role;dest.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if Path(name).name!=name or not name.endswith('.xml'):raise ValueError(name)
                (dest/name).write_bytes(z.read(name))
    (ws/'bank').mkdir(exist_ok=True)
    for path in sorted((folder/'inputs/a3').rglob('bank.csv')):
        shutil.copy2(path,ws/'bank'/(path.parent.name+'.csv'))
    rows=[]
    for path in sorted((folder/'inputs/a3').rglob('purchase_portal.csv')):
        rows.extend(csv.DictReader(path.open(encoding='utf-8-sig')))
    (ws/'portal').mkdir(exist_ok=True)
    with (ws/'portal/purchase_list.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('A3 staged; running native pipeline',flush=True)
    rep=pipeline.run(ws,as_of=date(2026,10,14))
    report.write(rep,ws/'out')
    save(root/'validation.json',dict(passed=not rep.meta.get('unreadable'),meta=rep.meta))
    assert rep.meta['counts']['purchase_invoices']==2500 and rep.meta['counts']['sales_invoices']==2500


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('agent',choices=['a1','a2','a3']);a=p.parse_args()
    globals()[a.agent](a.folder.resolve())
