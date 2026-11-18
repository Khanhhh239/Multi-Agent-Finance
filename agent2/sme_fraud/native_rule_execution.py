"""Bounded, source-preserving replay for signed and late-known native rows.

Each row uses strictly earlier posting history visible at its knowledge cutoff.
Rule evidence retains its event/action clock; later proof cannot authorize an
exception retroactively. No source clock/amount is rewritten for the old engine.
"""
from copy import deepcopy

from .benford import monthly_diagnostics
from .import_files import canonical, digest, fail
from .rules import DEFAULT_CONFIG, score_rules, invoice_payment_key

VERSION = 'native-signed-bitemporal/1.0.0'
# These predicates/exception policies were defined for positive disbursements.
# Accepting a negative source value is not permission to reinterpret the policy.
SIGNED_UNSUPPORTED = set('A1 A2 A3 A4 A5 A6 B3 B6 C2 C3 E1 E2 F2 P2 T1 T2'.split())


def requires_replay(tables):
    events={r['transaction_id']:r['posted_at'] for r in tables['transactions']}
    first_event=min(events.values())
    return (any(r['amount_vnd'] < 0 or r['observed_at'] > r['posted_at'] for r in tables['transactions'])
            or any(r['observed_at'] > r['posted_at'] for name in ('journal_documents', 'journal_lines')
                   for r in tables.get(name, []))
            or any(r.get('debit_vnd',0)<0 or r.get('credit_vnd',0)<0 for r in tables.get('journal_lines',[]))
            or len(tables.get('companies',[]))>1
            or any(r['observed_at']>first_event for name in ('companies','calendar') for r in tables.get(name,[]))
            or any(r.get('transaction_id') in events and r['observed_at']>events[r['transaction_id']]
                   for name,rows in tables.items() if name!='transactions' for r in rows))


def monthly_point_in_time(tables, as_of):
    """Do not rebuild a historical monthly statistic from later observations."""
    return [r for r in monthly_diagnostics(tables,'phase4',point_in_time=True) if r['cutoff_at']<=as_of]


def _row_gaps(bundle, tx, tables, omitted):
    from .native_rule_node import REQUIRED, HISTORY_RULES
    gaps = {code: [] for code in REQUIRED}
    documents={r['document_id'] for r in tables.get('journal_documents',[])
               if r.get('transaction_id')==tx['transaction_id']}
    for code, names in REQUIRED.items():
        if not any(r['recorded_at']<=tx['posted_at'] and r['observed_at']<=tx['posted_at']
                   for r in tables.get('companies',[])):
            gaps[code].append(dict(table='companies',record_id=tx['company_id'],reason='company_not_known_at_event'))
        if tx['amount_vnd'] < 0 and code in SIGNED_UNSUPPORTED:
            gaps[code].append(dict(table='transactions', record_id=tx['transaction_id'],
                                   reason='signed_amount_policy_not_supported'))
        if code in HISTORY_RULES and omitted:
            gaps[code].append(dict(table='transactions', reason='historical_actor_source_unavailable', record_ids=omitted))
        negative_payments=[r for r in tables['transactions'] if r['amount_vnd']<0
                           and r['txn_type']=='vendor_payment']
        relevant_negative=(any(r['vendor_id']==tx['vendor_id'] for r in negative_payments) if code in {'B3','B6'}
                           else any(r['creator_id']==tx['creator_id'] for r in negative_payments) if code in {'A2','A4'}
                           else any(r['recipient_account']==tx['recipient_account'] and r.get('recipient_bank_code')==tx.get('recipient_bank_code') for r in negative_payments) if code=='A1'
                           else bool(negative_payments) if code=='A3' else False)
        if relevant_negative:
            gaps[code].append(dict(table='transactions', reason='signed_history_policy_not_supported'))
        # Missingness is determined from visible proof only. Inspecting the
        # existence of a future revision would itself change a past result.
        bindings={'F1':('journal_audit_log',),'A5':('journal_documents','journal_lines'),
                  'E2':('payroll_settlements',)}.get(code,())
        for name in bindings:
            known=[r for r in tables.get(name,[])
                   if r['observed_at']<=tx['posted_at'] and (r.get('transaction_id')==tx['transaction_id']
                      or name=='journal_lines' and r.get('document_id') in documents)]
            if not known:
                gaps[code].append(dict(table=name,record_id=tx['transaction_id'],reason='bound_evidence_not_known_at_event'))
        if code=='A5' and any((r.get('transaction_id')==tx['transaction_id'] or r.get('document_id') in documents)
                              and (r.get('debit_vnd',0)<0 or r.get('credit_vnd',0)<0)
                              for r in tables.get('journal_lines',[])):
            gaps[code].append(dict(table='journal_lines',record_id=tx['transaction_id'],reason='signed_ledger_outside_positive_upper_tail_domain'))
    key=invoice_payment_key(tx)
    if key:
        prior=[r for r in tables['transactions'] if r['posted_at']<tx['posted_at'] and invoice_payment_key(r)==key]
        if any(not r.get('invoice_gross_vnd') or r['invoice_gross_vnd']!=tx['invoice_gross_vnd'] for r in prior):
            gaps['P1'].append(dict(table='transactions',record_id=tx['transaction_id'],reason='invoice_history_value_unavailable_or_conflicting'))
    return gaps


def replay(bundle, tables, candidate_ids=None):
    from .native_rule_node import TABLES, _rule_results
    requested = set(candidate_ids) if candidate_ids is not None else {r['transaction_id'] for r in tables['transactions']}
    targets = [r for r in tables['transactions'] if r['transaction_id'] in requested]
    contexts = {(r['posted_at'], max(r['posted_at'], r['observed_at'])) for r in targets}
    if len(contexts) > 200:
        fail(422, 'NATIVE_REPLAY_LIMIT', 'Tối đa 200 nhóm thời điểm ứng viên cho một lượt replay.',
             'Chọn tối đa 200 ứng viên; giữ toàn bộ lịch sử trong nguồn, không cắt lịch sử.')
    combined = dict(scores=[], hits=[], batch_events=[], evidence_findings=[])
    row_rules, receipts = {}, []
    for event, knowledge in sorted(contexts):
        cohort = [r for r in targets if (r['posted_at'], max(r['posted_at'], r['observed_at'])) == (event, knowledge)]
        context = {name: [deepcopy(r) for r in tables.get(name, [])
                          if r['observed_at'] <= event] for name in TABLES if name != 'transactions'}
        context['companies'].sort(key=lambda r:r['recorded_at'])
        # Earlier postings received after this knowledge cutoff are absent.
        # Same-posting peers stay a batch, never individual history.
        history = [r for r in tables['transactions'] if r['posted_at'] <= event and r['observed_at'] <= knowledge]
        staff = context['employees']
        usable, omitted = [], []
        for row in history:
            known_actor = any(s['employee_id'] == row['creator_id'] and s['recorded_at'] <= row['posted_at']
                              for s in staff)
            if known_actor:
                usable.append(deepcopy(row))
            else:
                omitted.append(row['transaction_id'])
        context['transactions'] = usable
        visible_ids = {r['transaction_id'] for r in usable}
        # Explicit relational bindings must not point at an excluded future tx.
        for name in ('journal_documents', 'journal_lines'):
            context[name] = [r for r in context[name] if r['posted_at'] <= event
                             and (not r.get('transaction_id') or r['transaction_id'] in visible_ids)]
        reference = (score_rules(context, config=deepcopy(DEFAULT_CONFIG), signed_amounts=True)
                     if usable and context['companies'] else dict(scores=[], hits=[], batch_events=[], evidence_findings=[]))
        cohort_ids = {r['transaction_id'] for r in cohort}
        combined['scores'].extend(r for r in reference['scores'] if r['transaction_id'] in cohort_ids)
        combined['hits'].extend(r for r in reference['hits'] if r['transaction_id'] in cohort_ids)
        combined['batch_events'].extend(r for r in reference['batch_events'] if r['detected_at'] == event)
        combined['evidence_findings'].extend(reference['evidence_findings'])
        context_hash = digest(canonical(context))
        for tx in cohort:
            # Coverage is checked against the full immutable export; only the
            # row's own invoice facts can affect its per-row availability.
            row_bundle = dict(bundle, tables=dict(bundle['tables'], transactions=[tx]))
            row_reference = dict(reference, hits=[h for h in reference['hits'] if h['transaction_id']==tx['transaction_id']])
            entries = _rule_results(row_bundle, row_reference, [])
            row_gaps = _row_gaps(bundle, tx, context, [i for i in omitted if i != tx['transaction_id']])
            for entry in entries:
                code = entry['rule_id']
                entry['hits'] = [h for h in entry['hits'] if h['transaction_id'] == tx['transaction_id']]
                if code.startswith('D') or code == 'F4':
                    continue
                gaps = entry['gaps'] + row_gaps[code]
                if tx['transaction_id'] not in visible_ids:
                    gaps.append(dict(table='employees', record_id=tx['creator_id'], reason='actor_not_known_at_event'))
                if gaps:
                    entry.update(available=False, status='unavailable', matched=None, score=None,
                                 reason='source_or_domain_unavailable', gaps=gaps, hits=[], groups=[])
                else:
                    matched = any(not h.get('suppressed_reason') for h in entry['hits'])
                    entry.update(available=True, matched=matched, status='evaluated_hit' if matched else 'evaluated_no_hit')
            row_rules[tx['transaction_id']] = entries
        prior_ids=sorted(r['transaction_id'] for r in usable if r['posted_at']<event)
        receipts.append(dict(event_at=event, knowledge_at=knowledge, candidate_ids=sorted(cohort_ids),
                             context_sha256=context_hash, reference_sha256=digest(canonical(reference)),
                             history_record_count=len(prior_ids), history_identity_sha256=digest(canonical(prior_ids))))
    # Scope findings/events may be repeated across independent row replays.
    for key in ('batch_events', 'evidence_findings'):
        combined[key] = list({digest(canonical(r)): r for r in combined[key]}.values())
    return combined, row_rules, dict(version=VERSION, source_sha256=digest(canonical(bundle)),
                                     amount_policy='preserve_signed_vnd', receipts=receipts)
