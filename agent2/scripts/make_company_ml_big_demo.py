"""Build a LARGER demo workspace for the company ML page (synthetic data, no labels, no splits).

The small repository fixture fills its ML cache with random features. This starts from that same fixture (so the review
reports stay valid) and ADDS real generated transactions and their real 194 features for companies C001 and C002, so the
algorithms, including `bag_injection` (which needs 60+ training rows), have something real to learn from. Labels and
splits of the generated world are never copied; the cache is attested with the helper the tests use.

  $env:PYTHONPATH = "$PWD;$PWD/tests"
  python -B scripts/make_company_ml_big_demo.py --root .runtime/demo_big
  python -B -m sme_fraud.review_server --data-root .runtime/demo_big/data --reports-root .runtime/demo_big/reports `
      --database .runtime/demo_big/review.sqlite3 --port 8765 --qa --demo-ml-manager
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

from company_ml_fixture import bind_cache, fixture          # tests/ must be on PYTHONPATH
from sme_fraud.generate import generate, write_csv

COMPANIES = ('C001', 'C002')


def read(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--rows', type=int, default=12_000)
    p.add_argument('--seed', type=int, default=20261108)
    a = p.parse_args()
    if a.root.exists():
        sys.exit(f'{a.root} exists; choose a new folder so existing work is never overwritten.')
    store, data, records = fixture(a.root)                    # valid reports plus the small random-feature cache
    world = a.root / '_world'
    generate(world, n=a.rows, rate=.005, seed=a.seed, companies=3)
    real_tx = [r for r in read(world / 'transactions.csv') if r['company_id'] in COMPANIES]
    ids = {r['transaction_id'] for r in real_tx}
    base = dict(records[0])
    added = [dict(base, transaction_id='W_' + r['transaction_id'], company_id=r['company_id'], posted_at=r['posted_at'],
                  journal_document_id='', is_financial_entry=0) for r in real_tx]
    features = read(data / 'features.csv')
    columns = [c for c in features[0] if c != 'transaction_id']
    for row in read(world / 'features.csv'):                   # the real 194 features; labels are never opened
        if row['transaction_id'] in ids:
            features.append(dict(row, transaction_id='W_' + row['transaction_id']))
    shutil.rmtree(world)                                       # the labelled copy does not stay in the workspace
    write_csv(data / 'transactions.csv', records + added)
    write_csv(data / 'features.csv', features, ['transaction_id'] + columns)
    bind_cache(data)
    store.prepare()
    print(f'ready: {a.root}  (+{len(added)} real transactions for {", ".join(COMPANIES)})')


if __name__ == '__main__':
    main()
