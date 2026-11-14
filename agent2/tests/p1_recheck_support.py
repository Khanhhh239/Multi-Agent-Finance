"""Independent P1 acceptance examples; preserve raw native discrepancies."""
import copy
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import score_rules,INPUT_TABLES,OPTIONAL_INPUT_TABLES
from sme_fraud.imports import validate_input
from sme_fraud.import_files import canonical,digest
from test_p1_evaluation import payments,refresh,evaluate,DAY
from test_p1_inputs import p1_bundle
from test_snapshot_features import scope

SCENARIOS=('below','exceeded','missing_history','late_invoice','late_allocation','late_attachment','simultaneous')


def run_case(name):
    if name not in SCENARIOS:raise ValueError(name)
    if name=='below':amounts,days,target=[4_000_000,5_000_000],[0,1],'T1'
    elif name=='simultaneous':amounts,days,target=[4_000_000,4_000_000,4_000_000],[0,1,1],'T1'
    elif name=='late_invoice':amounts,days,target=[6_000_000,6_000_000,1_000_000],[0,1,4],'T1'
    else:amounts,days,target=[4_000_000,7_000_000],[0,1],'T1'
    data=payments([(f'T{i}',amount,DAY(day+1),dict(payment_channel='cash')) for i,(amount,day) in enumerate(zip(amounts,days))])
    case=Case();native_rows=[]
    for index,(amount,day) in enumerate(zip(amounts,days)):
        at=case.at+timedelta(days=day)
        values=dict(invoice_number='0000123',invoice_gross_vnd=10_000_000,payment_channel='cash',credit_account='111',recipient_account='',
            invoice_issued_at=stamp(case.at-timedelta(days=30)),invoice_observed_at=stamp(case.at-timedelta(days=1)))
        if name=='late_invoice':values['invoice_observed_at']=stamp(case.at+timedelta(days=3))
        native_rows.append(case.pay(at,amount,**values))
    if name=='missing_history':data['payment_history_coverage']=[]
    elif name=='late_invoice':
        data['invoices'][0]['observed_at']=DAY(4);refresh(data)
        # No premature scope claims for an invoice the exporter has not seen.
        data['payment_history_coverage']=[c for c in data['payment_history_coverage'] if c['invoice_refs']]
    elif name=='late_allocation':
        data['payment_allocations'][-1]['observed_at']=DAY(4);refresh(data)
    elif name=='late_attachment':
        doc=copy.deepcopy(p1_bundle()['supporting_documents'][0]);doc.update(record_id='DOC_LATE',effective_at=DAY(2),observed_at=DAY(4))
        doc['source']['record_id']='DOC_LATE';doc['subject_refs']=[dict(table='transactions',record_id='T1',revision=1)]
        data['supporting_documents']=[doc]
    report=validate_input(data,scope());assert report['status']!='rejected',report['errors']
    source_before=digest(canonical(data));actual=evaluate(data,target);assert digest(canonical(data))==source_before
    case.score();native=score_rules(case.tables,features=case.features)
    index=int(target[1:]);native_id=native_rows[index]['transaction_id']
    hits=[h for h in native['hits'] if h['rule_id']=='P1' and h['transaction_id']==native_id]
    native_points=sum(h['points'] for h in hits)
    summary=dict(scenario=name,target=target,input_rows=len(data['transactions']),
        canonical_status=actual['status'],canonical_points=actual['score'],canonical_matched=actual['matched'],
        native_points=native_points,native_positive_hit=any(h['points']>0 for h in hits),
        native_availability='not_expressed_by_legacy_hit_list',classification=None,checks={},findings=[])
    evidence=dict(canonical_source=data,validation=report,canonical_target_result=actual,
        native_input={t:case.tables[t] for t in dict.fromkeys(INPUT_TABLES+OPTIONAL_INPUT_TABLES) if t in case.tables},
        native_target_hits=hits,native_P1_batch_events=[g for g in native['batch_events'] if g['rule_id']=='P1'],
        native_config=native['config'],source_data_kind='synthetic_not_accuracy')
    if name in ('below','exceeded','late_attachment','simultaneous'):
        expected=0 if name in ('below','simultaneous') else 20
        assert actual['score']==native_points==expected
        assert actual['available'] and actual['matched']==(expected>0)
        summary['classification']='shared_domain_parity'
        summary['checks']['row_points_and_signal_match']=True
        if hits:
            hit,=hits;check,=actual['details']['invoice_checks']
            assert hit['hard_trigger']==1 and not hit['suppressed_reason']
            assert hit['evidence']['cumulative_paid_vnd']==check['cumulative_paid_vnd']==11_000_000
            assert hit['evidence']['excess_vnd']==check['excess_vnd']==1_000_000
            assert hit['evidence']['invoice_gross_vnd']==check['invoice_gross_vnd']==10_000_000
            assert hit['related_transaction_ids']==[native_rows[0]['transaction_id']]
            assert check['related_transaction_refs']==[dict(record_id='T0',revision=1)]
            summary['checks']['totals_excess_cap_prior_and_hard_trigger_match']=True
    if name=='simultaneous':
        peer=evaluate(data,'T2');groups=actual['details']['simultaneous_checks'];events=evidence['native_P1_batch_events']
        group,=groups;event,=events
        assert groups==peer['details']['simultaneous_checks']
        assert actual['score']==peer['score']==0 and group['points']==event['points']==20
        assert group['cumulative_paid_vnd']==event['evidence']['cumulative_paid_vnd']==12_000_000
        assert group['excess_vnd']==event['evidence']['excess_vnd']==2_000_000
        assert group['prior_paid_vnd']==4_000_000
        assert group['transaction_refs']==[dict(record_id='T1',revision=1),dict(record_id='T2',revision=1)]
        assert event['transaction_ids']==[native_rows[1]['transaction_id'],native_rows[2]['transaction_id']]
        assert event['related_transaction_ids']==[native_rows[0]['transaction_id']]
        summary.update(canonical_group_points=20,native_group_points=20,unique_group_checks=len({g['group_id'] for g in groups+peer['details']['simultaneous_checks']}))
        summary['checks']['group_total_members_prior_match_without_row_point_duplication']=True
        evidence['canonical_peer_result']=peer
    if name in ('missing_history','late_invoice','late_allocation'):
        assert actual['status']=='unavailable' and actual['score'] is None and actual['matched'] is None
        assert actual['gaps'] and actual['reason']['code']=='rule_sources_unavailable'
        assert native_points==(0 if name=='late_invoice' else 20)
        summary['checks']['canonical_missing_is_null_not_zero']=True
        summary['classification']='legacy_representation_limit'
    if name in ('late_invoice','late_allocation','late_attachment'):
        earlier=evaluate(data,target,DAY(2));assert earlier==actual
        summary['checks']['later_global_asof_does_not_rewrite_past']=True
    if name=='late_invoice':
        summary['classification']='native_temporal_fix_verified'
        assert len(hits)==1 and hits[0]['status']=='information_gap' and hits[0]['signal'] is None
        assert hits[0]['hard_trigger']==0 and hits[0]['evidence']['reason']=='invoice_not_available_at_cutoff'
        assert 'invoice_gross_vnd' not in hits[0]['evidence']
        summary['resolved_findings']=[dict(code='P1-NATIVE-LATE-INVOICE',status='FIXED_IN_TESTED_SCOPE',
            native_before_points=20,native_after_points=0,native_after_status='information_gap',
            note='Zero-point information request is not an evaluated no-hit; canonical remains unavailable/null.')]
        summary['checks']['native_gap_blocks_future_invoice_values']=True
        later=evaluate(data,'T2');assert later['score']==20
        later_hits=[h for h in native['hits'] if h['rule_id']=='P1' and h['transaction_id']==native_rows[2]['transaction_id']]
        assert later_hits[0]['points']==later['score']
        evidence['canonical_later_transaction_result']=later
        summary['checks']['later_transaction_can_use_now_known_invoice']=True
    if name=='late_attachment':
        without=copy.deepcopy(data);without['supporting_documents']=[]
        assert evaluate(without,target)==actual
        assert all(r['table']!='supporting_documents' for r in actual['evidence_refs'])
        summary['checks']['unrequired_late_attachment_does_not_disable_P1_or_leak_into_evidence']=True
    if name=='missing_history':
        assert any(g['code']=='p1_history_scope_missing' for g in actual['gaps'])
    if name=='late_allocation':
        assert any(g['code']=='p1_current_allocation_missing' for g in actual['gaps'])
    summary['canonical_assertions_pass']=True
    return summary,evidence
