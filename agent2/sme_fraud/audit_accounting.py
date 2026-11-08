"""Audit multi-line journals, framework coding, VAT arithmetic and document links."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter,defaultdict
from pathlib import Path

from .accounting import account_supported,pair_supported,normalise_account,SOURCES


def check_accounting(tables):
    tx={r['transaction_id']:r for r in tables['transactions']}
    companies={r['company_id']:r for r in tables['companies']}
    documents={r['document_id']:r for r in tables['journal_documents']}
    by_document=defaultdict(list)
    edges=defaultdict(list)
    primary={}
    for line in tables['journal_lines']:
        assert line['document_id'] in documents,'Journal document FK'
        by_document[line['document_id']].append(line)
        assert (int(line['debit_vnd'])>0) != (int(line['credit_vnd'])>0),'Exactly one positive line side'
    for edge in tables['account_flow_edges']:
        edges[edge['document_id']].append(edge)
        doc=documents[edge['document_id']]
        assert edge['company_id']==doc['company_id'] and edge['observed_at']==doc['posted_at'],'Flow chronology/company'
        assert pair_supported(edge['target_account'],edge['source_account'],doc['purpose'],doc['accounting_framework']),f'Unsupported scenario pair {doc["document_id"]}'
    for docid,doc in documents.items():
        company=companies[doc['company_id']]
        assert doc['accounting_framework']==company['accounting_framework'],'Framework mismatch'
        ls=by_document[docid]
        assert ls and all(account_supported(l['account_code'],doc['accounting_framework']) for l in ls),'Account outside framework'
        total_debit=sum(int(l['debit_vnd']) for l in ls)
        total_credit=sum(int(l['credit_vnd']) for l in ls)
        assert total_debit==total_credit==int(doc['amount_vnd']),'Document not balanced to gross'
        assert sum(int(e['amount_vnd']) for e in edges[docid])==total_debit,'Flow totals'
        for account in {l['account_code'] for l in ls}:
            assert sum(int(e['amount_vnd']) for e in edges[docid] if e['target_account']==account)==sum(int(l['debit_vnd']) for l in ls if l['account_code']==account),'Flow-debit reconciliation'
            assert sum(int(e['amount_vnd']) for e in edges[docid] if e['source_account']==account)==sum(int(l['credit_vnd']) for l in ls if l['account_code']==account),'Flow-credit reconciliation'
        if int(doc['is_scored_observation']):
            tid=doc['transaction_id']
            assert tid in tx and tid not in primary,'Primary document transaction FK/duplicate'
            primary[tid]=doc
            assert tx[tid]['journal_document_id']==docid and tx[tid]['posted_at']==doc['posted_at'],'Primary time/id'
            assert int(tx[tid]['amount_vnd'])==total_debit,'Observation amount != journal gross'
        else:
            assert not doc['transaction_id'],'Auxiliary document must not create a scored observation'
        if doc['vat_account']:
            net,vat,gross=map(int,(doc['invoice_net_vnd'],doc['invoice_vat_vnd'],doc['invoice_gross_vnd']))
            assert net+vat==gross,'VAT arithmetic'
            assert abs(round(net*float(doc['vat_rate']))-vat)<=1,'VAT rounding'
            vat_side='credit_vnd' if doc['vat_account']=='3331' else 'debit_vnd'
            assert sum(int(l[vat_side]) for l in ls if l['account_code']==doc['vat_account'])==vat,'VAT journal does not match invoice'
    incoming=defaultdict(list)
    for link in tables['document_links']:
        source,target=documents[link['source_document_id']],documents[link['target_document_id']]
        assert source['company_id']==target['company_id'],'Cross-company accounting link'
        assert source['posted_at']<=link['observed_at'] and target['posted_at']<=link['observed_at'],'Future document link leakage'
        incoming[link['target_document_id']].append(source)
    for tid,r in tx.items():
        assert r['accounting_framework']==companies[r['company_id']]['accounting_framework'],'Observation framework mismatch'
        expected_party='vendor' if r['vendor_id'] else 'customer' if r['customer_id'] else 'employee' if r['employee_id'] else 'none'
        assert r['counterparty_type']==expected_party,'Counterparty description not updated after accounting reclassification'
        if expected_party=='none':
            assert not r['counterparty_account'],'Internal accounting movement incorrectly assigned an external counterparty'
        if not int(r['is_financial_entry']):
            assert tid not in primary and not r['journal_document_id'],'Nonfinancial review has journal'
            continue
        assert tid in primary,'Missing primary document'
        assert pair_supported(r['debit_account'],r['credit_account'],r['accounting_purpose'],r['accounting_framework']),'Unsupported primary scenario'
        if r['txn_type']=='payroll':
            assert r['employee_id'] and not r['vendor_id'],'Payroll entity'
            assert any(d['purpose']=='salary_accrual' and d['employee_id']==r['employee_id'] for d in incoming[r['journal_document_id']]),'Payroll not linked to accrued salary'
        if r['txn_type']=='advance_issue':
            assert r['employee_id'] and not r['vendor_id'] and r['debit_account']=='141','Advance entity'
        if r['txn_type']=='advance_writeoff':
            assert r['credit_account']=='1388','Reclassification misnamed as writeoff'
            assert any(d['purpose']=='advance_reclassification' for d in incoming[r['journal_document_id']]),'No prior receivable'
            event=next(e for e in tables['advance_events'] if e['transaction_id']==tid and e['event_type']=='writeoff')
            assert int(r['evidence_on_file'])==int(event['evidence_on_file']) and event['observed_at']==r['posted_at'],'Writeoff evidence timing'
        if r['txn_type']=='equipment_purchase':
            assert int(r['invoice_net_vnd'])>=30_000_000 and r['debit_account']=='211','Standalone equipment incorrectly capitalised'
        if r['txn_type']=='tools_purchase':
            assert int(r['invoice_net_vnd'])<30_000_000 and r['debit_account']=='153','Tool classification'
        if r['txn_type']=='vendor_payment':
            assert not any(l['account_code'].startswith('133') for l in by_document[r['journal_document_id']]),'VAT booked again on payment'
            assert any(d['purpose']=='invoice_accrual' for d in incoming[r['journal_document_id']]),'Missing prior invoice accrual'
        if r['txn_type'] not in {'vendor_payment','payroll','advance_issue','rent','selling_expense','cash_expense','customer_receipt','tax_payment'}:
            assert r['payment_channel']=='journal' and not r['recipient_account'],'Noncash event shown as a bank transfer'
        if r['txn_type']=='customer_receipt':
            assert r['recipient_account']==companies[r['company_id']]['bank_account'],'Receipt credited to customer rather than own bank'
    for invoice in tables['invoices']:
        assert int(invoice['net_amount_vnd'])+int(invoice['vat_amount_vnd'])==int(invoice['gross_amount_vnd']),'Invoice net+VAT != gross'
    counts=Counter((companies[d['company_id']]['accounting_framework'],d['purpose']) for d in documents.values())
    return dict(status='passed',version='2.0',scored_observations=len(tx),primary_financial_documents=len(primary),
        auxiliary_documents=len(documents)-len(primary),journal_documents=len(documents),journal_lines=len(tables['journal_lines']),
        account_flow_edges=len(tables['account_flow_edges']),accounting_frameworks={k:v['accounting_framework'] for k,v in companies.items()},
        by_framework_and_purpose={f'{f}/{p}':n for (f,p),n in sorted(counts.items())},
        sources=SOURCES,scope='Scenario-specific historical 2024-2025 TT133/TT200 templates; balanced books do not establish authenticity or tax deductibility')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/sme_fraud_003'))
    args=parser.parse_args()
    tables={}
    for name in ('transactions','companies','journal_documents','journal_lines','account_flow_edges','document_links','advance_events','invoices'):
        with (args.data/f'{name}.csv').open(encoding='utf-8-sig',newline='') as f:
            tables[name]=list(csv.DictReader(f))
    report=check_accounting(tables)
    (args.data/'accounting_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','scored_observations','journal_documents','journal_lines','auxiliary_documents')},indent=2))


if __name__=='__main__':
    main()
