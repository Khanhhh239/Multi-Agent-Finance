"""Attested synthetic ML cache beside the small review fixture; no truth inputs."""
import csv
from datetime import datetime, timedelta
import io
import json

import numpy as np

from sme_fraud.feature_contract import cache_contract, current_contract, sha
from sme_fraud.generate import write_csv
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_store import ReviewStore
from test_review import make_fixture

CHIEF = ReviewPrincipal('SIM_CHIEF', 'SIM_P1', 'MÔ PHỎNG · Kế toán trưởng', 'chief_accountant', ('C001','C002'))
ACCOUNTANT = ReviewPrincipal('SIM_ACC', 'SIM_P2', 'MÔ PHỎNG · Kế toán viên', 'accountant', ('C001',))


def bind_cache(data):
    files = {name:dict(sha256=sha(data/name)) for name in ('transactions.csv','features.csv')}
    files.update({name:dict(sha256='MUST_NOT_READ') for name in ('labels.csv','splits.csv')})
    manifest = dict(version='synthetic-company-ml-test-v1', is_synthetic=True, role='reporting',
                    files=files, feature_columns=current_contract()['columns'], feature_contract=cache_contract(files))
    (data/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')


def fixture(root):
    data, report = make_fixture(root)
    with (data/'transactions.csv').open(encoding='utf-8-sig',newline='') as stream:
        records = list(csv.DictReader(stream))
    base = dict(records[0]); start = datetime.fromisoformat('2024-01-01T12:00:00+07:00')
    for company in ('C001','C002'):
        for i in range(30):
            records.append(dict(base, transaction_id=f'{company}_SIM_{i}', company_id=company,
                                posted_at=(start+timedelta(days=i)).isoformat(), journal_document_id='', is_financial_entry=0))
    write_csv(data/'transactions.csv', records)
    columns = current_contract()['columns']; rng = np.random.RandomState(12)
    features = [dict(transaction_id=r['transaction_id'], **dict(zip(columns,rng.normal(size=len(columns))))) for r in records]
    write_csv(data/'features.csv', features); bind_cache(data)
    store = ReviewStore(root/'data', root/'reports', root/'review.sqlite3',
                        clock=lambda: datetime.fromisoformat('2026-11-04T10:00:00+07:00'))
    store.prepare()
    return store, data, records


def label_text(records, company='C001'):
    stream=io.StringIO(); fields=['company_id','transaction_id','label','reviewer_id','reviewed_at','evidence_ref','verified']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for i,r in enumerate(row for row in records if row['company_id']==company):
        writer.writerow(dict(company_id=company,transaction_id=r['transaction_id'],label=i%2,
            reviewer_id='SIM_REVIEWER', reviewed_at=(datetime.fromisoformat(r['posted_at'])+timedelta(hours=1)).isoformat(),
            evidence_ref='SIM_DOCUMENT_'+r['transaction_id'],verified=1))
    return stream.getvalue()
