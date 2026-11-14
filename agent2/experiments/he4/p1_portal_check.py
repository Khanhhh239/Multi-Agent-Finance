"""Read-only reconciliation of Portal HE results and locked simulated records."""
from sme_fraud.import_files import canonical,digest
from sme_fraud.review_api import display_record
from sme_fraud.snapshot_features import utc


def amount(value):
    if type(value) is int:return value
    if isinstance(value,str) and value.removeprefix('-').isdigit():return int(value)
    raise AssertionError('money must be an exact integer/string')


def reconcile(company,source,result,packet,reference):
    if source['tenant_id']!='demo' or result['company_id']!=company or packet['company_id']!=company:raise AssertionError('company binding')
    if (packet['run_id'],packet['snapshot_id'],packet['as_of'])!=(result['run_id'],result['snapshot_id'],result['as_of']):raise AssertionError('review/run binding')
    sources={(table,r['record_id'],r['revision']):r for table,records in source.items() if isinstance(records,list) for r in records}
    if not all(r['company_id']==company and r['tenant_id']=='demo' and r['source']['is_simulated'] for r in sources.values()):raise AssertionError('prepared synthetic sources only')
    txs={r['record_id']:r for r in source['transactions']};rows={r['record_id']:r for r in result['rows']};cases={r['record_id']:r for r in packet['cases']};refs={r['record_id']:r for r in reference['rows']}
    if set(txs)!=set(rows) or set(txs)!=set(cases) or set(txs)!=set(refs) or len(txs)!=8:raise AssertionError('all eight rows must remain')
    output=[]
    for identity,tx in txs.items():
        row,case,ref=rows[identity],cases[identity],refs[identity];branch=row['branches']['rules'];event=utc(tx['effective_at']);cutoff=max(event,utc(tx['observed_at']))
        if amount(case['amount_vnd'])!=tx['amount_vnd'] or utc(case['event_at'])!=event or utc(case['as_of'])!=cutoff:raise AssertionError('transaction clocks/money')
        evidence={}
        for item in case['evidence']:
            key=item['table'],item['record']['record_id'],item['record']['revision'];record=sources.get(key)
            if record is None or item['record']!=display_record(record):raise AssertionError('evidence differs from locked source')
            if not item['simulated'] or item['original_verified']:raise AssertionError('simulation must not become verified original')
            if utc(record['observed_at'])>cutoff or utc(record['effective_at'])>event:raise AssertionError('future evidence exposed')
            if item['evidence_id']!='ev_'+digest(canonical(record)) or key in evidence:raise AssertionError('evidence identity/deduplication')
            evidence[key]=item['evidence_id']
        record=dict(record_id=identity,engine_status=ref['status'],reference_row_points=ref['row_score'],portal_branch_status=branch['status'],manual_checks=[],evidence_ids=list(evidence.values()))
        if ref['status'].startswith('evaluated_'):
            if not branch['available'] or branch['matched']!=ref['matched']:raise AssertionError('P1 status mismatch')
            if len(branch['invoice_checks'])!=len(ref['invoice_checks']) or len(branch['simultaneous_checks'])!=len(ref['simultaneous_checks']):raise AssertionError('P1 checks missing/extra')
            for live,engine in zip(branch['invoice_checks'],ref['invoice_checks']):
                if live['obligation']!=[engine['vendor_id'],engine['normalized_invoice_number']]:raise AssertionError('invoice obligation binding')
                for name in ('prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd'):
                    if amount(live[name])!=engine[name]:raise AssertionError(identity+': '+name)
                if live['matched']!=engine['matched'] or live['previous_payment']!=engine['previous_payment']:raise AssertionError('P1 flags')
                def records(table,references):
                    found=[]
                    for item in references:
                        key=table,item['record_id'],item['revision']
                        if key not in evidence:raise AssertionError('required P1 document not visible on review')
                        found.append(sources[key])
                    return found
                invoices=records('invoices',engine['invoice_refs']);prior=records('payment_allocations',engine['prior_allocation_refs']);current=records('payment_allocations',engine['current_allocation_refs'])
                paid=sum(a['amount_vnd'] for a in prior);now=sum(a['amount_vnd'] for a in current);cap=sum(i['amount_vnd'] for i in invoices)
                if (paid,now,cap,paid+now,max(0,paid+now-cap))!=tuple(amount(live[k]) for k in ('prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd')):raise AssertionError('manual source sums')
                invoice_ids={i['record_id'] for i in invoices}
                covered=[c for c in source['payment_history_coverage'] if invoice_ids<={i['record_id'] for i in c['invoice_refs']} and c['coverage_status']=='complete' and c['history_basis']=='since_inception' and utc(c['observed_at'])<=cutoff and utc(c['covered_through'])>=cutoff]
                if not covered:raise AssertionError('required history declaration absent')
                active=max(covered,key=lambda c:utc(c['observed_at']));records('payment_history_coverage',[active])
                record['manual_checks'].append(dict(invoice_ids=sorted(invoice_ids),history_declaration=active['record_id'],prior_allocations=[a['record_id'] for a in prior],current_allocations=[a['record_id'] for a in current],prior_sum_vnd=paid,current_sum_vnd=now,invoice_sum_vnd=cap,cumulative_vnd=paid+now,excess_vnd=max(0,paid+now-cap),matched=live['matched']))
            for live,engine in zip(branch['simultaneous_checks'],ref['simultaneous_checks']):
                for key in ('prior_paid_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd'):
                    if amount(live[key])!=engine[key]:raise AssertionError('simultaneous '+key)
                if amount(live['current_allocated_vnd'])!=engine['group_allocated_vnd'] or live['matched']!=engine['matched']:raise AssertionError('group totals/flag')
                for table,refs_key in (('transactions','transaction_refs'),('payment_allocations','allocation_refs')):
                    for item in engine[refs_key]:
                        if (table,item['record_id'],item['revision']) not in evidence:raise AssertionError('concurrent member document omitted')
                total=sum(sources['payment_allocations',r['record_id'],r['revision']]['amount_vnd'] for r in engine['allocation_refs'])
                if total!=amount(live['current_allocated_vnd']):raise AssertionError('manual concurrent sum')
                record['group_check']=dict(members=engine['transaction_refs'],group_allocated_vnd=total,matched=live['matched'],reference_group_points=engine['points'],row_points_exclude_group=True)
        elif ref['status']=='not_applicable':
            if branch['status']!='not_applicable' or branch['available'] or tx['kind']!='adjustment' or tx['amount_vnd']>=0:raise AssertionError('adjustment wrongly treated as payment')
            parent=tx['adjusts_ref'];key='transactions',parent['record_id'],parent['revision']
            if key not in evidence:raise AssertionError('adjustment parent missing')
            record['adjustment']=dict(amount_vnd=tx['amount_vnd'],parent=parent)
        else:
            if branch['available'] or branch['status']!='unavailable' or branch.get('matched') is not None or branch.get('score') is not None:raise AssertionError('missing history became no-hit/zero')
            if not any(g['code']=='p1_history_scope_missing' for g in branch['gaps']):raise AssertionError('missing history reason absent')
            record['missing_reason']='p1_history_scope_missing'
        output.append(record)
    return dict(company_id=company,run_id=result['run_id'],snapshot_id=result['snapshot_id'],as_of=result['as_of'],source_sha256=digest(canonical(source)),row_count=8,all_rows_match=True,rows=output,simulated_documents=True,original_documents_verified=False,human_review_feedback_written=False,training_eligible=False)
