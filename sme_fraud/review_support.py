"""Read-only supporting source projection for case explanations, never scoring."""
import json
from pathlib import Path
from .case_identity import digest

TABLES=('invoices','invoice_versions','document_links','supplier_payment_agreements',
        'recurring_payments','transaction_documents','payment_requests')


def linked_returns(rows,links,required):
    by_id={r['transaction_id']:r for r in rows}
    by_doc={r.get('journal_document_id'):r for r in rows if r.get('journal_document_id')}
    pairs=[]
    for row in rows:
        original=by_id.get(row.get('original_transaction_id'))
        if original and original['company_id']==row['company_id']:
            pairs.append((original,row))
    for link in links:
        if link.get('link_type') not in {'cash_return_of','reversal_of'}:
            continue
        left,right=by_doc.get(link.get('source_document_id')),by_doc.get(link.get('target_document_id'))
        if left and right and left['company_id']==right['company_id'] and link.get('company_id',left['company_id']) in {'',left['company_id']}:
            pairs.append((left,right))
    selected=set(required)
    adjacency={}
    for left,right in pairs:
        a,b=left['transaction_id'],right['transaction_id']
        adjacency.setdefault(a,set()).add(b)
        adjacency.setdefault(b,set()).add(a)
    pending=list(required)
    while pending:
        current=pending.pop()
        for related in adjacency.get(current,set())-selected:
            selected.add(related)
            pending.append(related)
    return [r for r in rows if r['transaction_id'] in selected-required]


def cache(db,scenario,data,report,csv_rows,all_transactions):
    for table in TABLES:
        path=Path(data)/(table+'.csv')
        if path.is_file():
            for row in csv_rows(path):
                db.execute('INSERT OR IGNORE INTO review_support_rows VALUES(?,?,?,?,?)',
                    (scenario,table,digest(row),row.get('company_id',''),json.dumps(row,ensure_ascii=False)))
    for row in all_transactions:
        db.execute('INSERT OR IGNORE INTO review_support_rows VALUES(?,?,?,?,?)',
            (scenario,'context_transactions',digest(row),row['company_id'],json.dumps(row,ensure_ascii=False)))
    scores=Path(report)/'rule_scores.csv'
    if scores.is_file():
        for row in csv_rows(scores):
            db.execute('INSERT OR IGNORE INTO review_support_rows VALUES(?,?,?,?,?)',
                (scenario,'rule_scores',digest(row),row['company_id'],json.dumps(row,ensure_ascii=False)))


def case_support(db,scenario,case,transactions,hits):
    groups={}
    for saved in db.execute('SELECT source_name,data FROM review_support_rows WHERE scenario=? AND (company_id=? OR company_id=?)',
                           (scenario,case['company_id'],'')):
        groups.setdefault(saved['source_name'],[]).append(json.loads(saved['data']))
    ids={r['transaction_id'] for r in transactions}
    context=groups.get('context_transactions',[])
    returns=linked_returns(context,groups.get('document_links',[]),ids)
    rows=[*transactions,*returns]
    tids={r['transaction_id'] for r in rows}
    docs={r.get('journal_document_id') for r in rows if r.get('journal_document_id')}
    invoices={r.get('invoice_id') for r in rows if r.get('invoice_id')}
    agreements=set()
    patterns=set()
    for hit in hits:
        proof=hit.get('evidence',{})
        if proof.get('recurring_pattern_id'):
            patterns.add(proof['recurring_pattern_id'])
        checks=[proof.get('installment_check') or {},*proof.get('excluded_independent_obligations',[])]
        agreements.update(p['agreement_id'] for p in checks if p.get('agreement_id'))
    result=dict(transactions=rows,
        invoices=[r for r in groups.get('invoices',[]) if r.get('invoice_id') in invoices],
        invoice_versions=[r for r in groups.get('invoice_versions',[]) if r.get('invoice_id') in invoices],
        document_links=[r for r in groups.get('document_links',[]) if r.get('source_document_id') in docs and r.get('target_document_id') in docs],
        recurring_payments=[r for r in groups.get('recurring_payments',[]) if r.get('pattern_id') in patterns],
        supplier_payment_agreements=[r for r in groups.get('supplier_payment_agreements',[]) if r.get('agreement_id') in agreements],
        transaction_documents=[r for r in groups.get('transaction_documents',[]) if r.get('transaction_id') in tids],
        payment_requests=[r for r in groups.get('payment_requests',[]) if r.get('transaction_id') in tids],
        rule_scores=[r for r in groups.get('rule_scores',[]) if r.get('transaction_id') in ids],
        cutoff_at=case['last_seen_at'],source_projection='read_only_no_rescoring')
    return result
