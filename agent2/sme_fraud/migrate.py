"""Correct accounting representation while preserving existing scored IDs and labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from .accounting import enrich_accounting,SOURCES
from .audit_accounting import check_accounting
from .generate import save_dataset

INT_FIELDS={'is_fraud','saturday_operations','is_holiday','approval_limit_vnd','self_approval_limit_vnd',
            'contract_on_file','days_worked_observed','approved_leave_days','alternative_work_evidence',
            'credit_terms_days','support_doc_count','goods_receipt_verified','is_financial_entry',
            'callback_verified','evidence_on_file'}


def migrate(source: Path,output: Path):
    meta=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    if meta['version']!='1.0':
        raise ValueError('Migration expects the original v1 dataset. Use generate for fresh v2 data.')
    tables={}
    for name in meta['files']:
        if name=='features.csv':
            continue
        with (source/name).open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        for row in rows:
            for field,value in row.items():
                if value and (field.endswith('_vnd') or field in INT_FIELDS):
                    row[field]=int(value)
                elif value and field=='amount_scale':
                    row[field]=float(value)
        tables[Path(name).stem]=rows
    before={r['transaction_id']:(r['debit_account'],r['credit_account'],r['txn_type'],r['payment_channel'],r['recipient_account']) for r in tables['transactions']}
    before_counts=Counter(f'{r[0]}/{r[1]}' for r in before.values())
    enrich_accounting(tables,meta['seed'])
    audit=check_accounting(tables)
    new_meta=save_dataset(output,tables,meta['requested_rows'],meta['requested_fraud_rate'],meta['seed'],meta['companies'])
    unchanged={name:hashlib.sha256((source/name).read_bytes()).hexdigest()==hashlib.sha256((output/name).read_bytes()).hexdigest()
               for name in ('labels.csv','splits.csv')}
    assert all(unchanged.values()),'Labels/splits changed during accounting migration'
    new_meta['migrated_from']=dict(version='1.0',source=str(source),preserved_file_bytes=unchanged)
    (output/'manifest.json').write_text(json.dumps(new_meta,ensure_ascii=False,indent=2),encoding='utf-8')
    changes=[]
    for row in tables['transactions']:
        old=before[row['transaction_id']]
        new=(row['debit_account'],row['credit_account'],row['txn_type'],row['payment_channel'],row['recipient_account'])
        if old!=new:
            changes.append(dict(transaction_id=row['transaction_id'],before_pair=f'{old[0]}/{old[1]}',
                                after_pair=f'{new[0]}/{new[1]}',before_type=old[2],after_type=new[2]))
    report=dict(status='corrected',version='2.0',scored_rows=len(tables['transactions']),changed_observations=len(changes),
        labels_and_splits_byte_identical=unchanged,before_pairs=dict(before_counts),
        after_pairs=dict(Counter(r['account_pair'] for r in tables['transactions'])),example_changes=changes[:25],
        notes=['641/642 mapped by company framework; ML combines expense group 642.',
               'Input/output VAT represented in multi-line journals; payment never books input VAT twice.',
               'WIP 154 receives materials/labour; manufacturing cogs uses 155, service cogs uses 154.',
               'Expense accrual uses 335; 1388/141 is reclassification, actual writeoff credits 1388.',
               'Noncash accruals/issues no longer show a bank beneficiary; customer receipt uses the company bank.',
               'Auxiliary accounting documents are separate from the 100000 scored observation denominator.'],sources=SOURCES)
    (output/'accounting_validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'accounting_change_log.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:report[k] for k in ('status','scored_rows','changed_observations','labels_and_splits_byte_identical')}


def repair_counterparty_metadata(directory):
    """Keep derived party descriptions consistent with final accounting retypes."""
    from .generate import write_csv
    with (directory/'transactions.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    with (directory/'customers.csv').open(encoding='utf-8-sig',newline='') as f:
        customers={r['customer_id']:r for r in csv.DictReader(f)}
    count=0
    for row in rows:
        role='vendor' if row['vendor_id'] else 'customer' if row['customer_id'] else 'employee' if row['employee_id'] else 'none'
        account='' if role=='none' else customers[row['customer_id']]['bank_account'] if role=='customer' else row['counterparty_account']
        if (row['counterparty_type'],row['counterparty_account'])!=(role,account):
            row['counterparty_type'],row['counterparty_account']=role,account
            count+=1
    if count:
        write_csv(directory/'transactions.csv',rows)
        meta=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        meta['files']['transactions.csv']['sha256']=hashlib.sha256((directory/'transactions.csv').read_bytes()).hexdigest()
        meta['migrated_from']['original_archive']='outputs/sme_fraud_v1.zip'
        (directory/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    change_log=json.loads((directory/'accounting_change_log.json').read_text(encoding='utf-8'))
    change_log['sources']=SOURCES
    change_log['counterparty_descriptions_corrected']=count
    (directory/'accounting_change_log.json').write_text(json.dumps(change_log,ensure_ascii=False,indent=2),encoding='utf-8')
    return count


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(migrate(args.source,args.output),indent=2))


if __name__=='__main__':
    main()
