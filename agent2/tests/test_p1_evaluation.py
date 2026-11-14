"""P1 business totals, signed corrections, causality and retained-native parity."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jsonschema

from sme_fraud.imports import validate_input
from sme_fraud.import_files import canonical
from sme_fraud.p1_inputs import export_manifest
from sme_fraud.rule_sources import _resolve
from sme_fraud.rule_evaluation import _evaluate
from sme_fraud.snapshot_features import build_feature_rows,feature_contract
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import score_rules
from test_p1_inputs import p1_bundle
from test_snapshot_features import scope,committed

SCHEMA=json.loads((Path(__file__).parents[1]/'sme_fraud/rule_results.schema.json').read_text('utf-8'))
DAY=lambda n:f'2026-10-{n:02d}T09:00:00+07:00'


def payments(rows,cap=10_000_000):
    data=p1_bundle();tx_template=copy.deepcopy(data['transactions'][0]);alloc_template=copy.deepcopy(data['payment_allocations'][0])
    data['transactions']=[];data['payment_allocations']=[];data['supporting_documents']=[];data['approvals']=[]
    data['invoices'][0]['amount_vnd']=cap
    for index,item in enumerate(rows):
        identity,amount,at,*options=item;options=options[0] if options else {}
        tx=copy.deepcopy(tx_template);tx.update(record_id=identity,amount_vnd=amount,effective_at=at,observed_at=at)
        tx['source']['record_id']=identity;tx.update({k:v for k,v in options.items() if k not in ('adjusts','allocated')})
        alloc=copy.deepcopy(alloc_template);alloc.update(record_id='A_'+identity,amount_vnd=options.get('allocated',amount),
            effective_at=at,observed_at=tx['observed_at'],transaction_ref=dict(record_id=identity,revision=1))
        alloc['source']['record_id']=alloc['record_id']
        if 'adjusts' in options:
            target=options['adjusts'];tx.update(kind='adjustment',adjusts_ref=dict(record_id=target,revision=1),adjustment_reason='Điều chỉnh có nguồn')
            alloc.update(kind='adjustment',adjusts_ref=dict(record_id='A_'+target,revision=1),adjustment_reason='Phân bổ điều chỉnh có nguồn')
        data['transactions'].append(tx);data['payment_allocations'].append(alloc)
    refresh(data)
    return data


def refresh(data):
    template=p1_bundle()['payment_history_coverage'][0];claims={}
    # One complete source export per availability group, never infer this in production.
    for tx in data['transactions']:
        known=max(tx['effective_at'],tx['observed_at'])
        if known not in claims:
            claim=copy.deepcopy(template);identity='COV_'+str(len(claims))
            claim.update(record_id=identity,observed_at=known,covered_through=known,export_id='EXPORT_'+identity,
                invoice_refs=[dict(record_id=r['record_id'],revision=r['revision']) for r in data['invoices'] if r['observed_at']<=known])
            claim['source']['record_id']=identity;claims[known]=claim
    data['payment_history_coverage']=list(claims.values())
    for claim in claims.values():claim['manifest']=export_manifest(data,claim)


def evaluate(data,identity,as_of='2026-10-30T00:00:00+07:00',authority=None):
    authority=authority or scope();frame=build_feature_rows(data,authority,as_of)
    private,public=_resolve(data,frame,authority)
    meta=next(r for r in frame['rows'] if r['record_id']==identity)
    result=_evaluate(private[(identity,meta['revision'])],public[(identity,meta['revision'])],authority,meta)
    jsonschema.validate(result,SCHEMA)
    return next(r for r in result['rules'] if r['rule_id']=='P1')


class P1EvaluationTests(unittest.TestCase):
    def test_prior_payment_uses_all_history_cash_and_bank_and_preserves_weight(self):
        data=payments([('OLD',4_000_000,DAY(1),{'payment_channel':'cash'}),('NEW',7_000_000,DAY(20))])
        self.assertFalse(validate_input(data,scope())['errors'])
        old=evaluate(data,'OLD');new=evaluate(data,'NEW')
        self.assertEqual((old['status'],old['score']),('evaluated_no_hit',0))
        self.assertEqual((new['status'],new['score'],new['intrinsic_points']),('evaluated_hit',20,20))
        check=new['details']['invoice_checks'][0]
        self.assertEqual((check['prior_paid_vnd'],check['cumulative_paid_vnd'],check['excess_vnd']),(4_000_000,11_000_000,1_000_000))

    def test_exact_cap_and_one_vnd_tolerance_and_first_payment_match_native_policy(self):
        for current,expected in ((6_000_000,False),(6_000_001,False),(6_000_002,True)):
            with self.subTest(current=current):
                self.assertEqual(evaluate(payments([('OLD',4_000_000,DAY(1)),('NEW',current,DAY(2))]),'NEW')['matched'],expected)
        first=evaluate(payments([('NEW',11_000_000,DAY(1))]),'NEW')
        self.assertFalse(first['matched']);self.assertFalse(first['details']['invoice_checks'][0]['previous_payment'])

    def test_simultaneous_group_does_not_pollute_row_history_or_repeat_points(self):
        data=payments([('OLD',4_000_000,DAY(1)),('A',4_000_000,DAY(2)),('B',4_000_000,DAY(2))])
        a=evaluate(data,'A');b=evaluate(data,'B')
        for row in (a,b):
            self.assertEqual((row['status'],row['score']),('evaluated_no_hit',0))
            self.assertEqual(row['details']['invoice_checks'][0]['prior_paid_vnd'],4_000_000)
        group,=a['details']['simultaneous_checks'];self.assertEqual(group,b['details']['simultaneous_checks'][0])
        self.assertEqual((group['matched'],group['points'],group['cumulative_paid_vnd']),(True,20,12_000_000))
        self.assertEqual(group['score_role'],'group_only_not_row_contribution')
        before=copy.deepcopy(a);data['transactions'].reverse();data['payment_allocations'].reverse()
        self.assertEqual(evaluate(data,'A'),before)

    def test_simultaneous_below_cap_and_row_hit_remain_distinct(self):
        data=payments([('OLD',4_000_000,DAY(1)),('A',2_000_000,DAY(2)),('B',2_000_000,DAY(2))])
        self.assertFalse(evaluate(data,'A')['details']['simultaneous_checks'][0]['matched'])
        data=payments([('OLD',9_000_000,DAY(1)),('A',2_000_000,DAY(2)),('B',2_000_000,DAY(2))])
        row=evaluate(data,'A');self.assertEqual(row['score'],20)
        self.assertEqual(row['details']['simultaneous_checks'][0]['points'],20)

    def test_same_availability_excluded_from_history_even_when_events_differ(self):
        data=payments([('A',6_000_000,DAY(1),{'observed_at':DAY(3)}),('B',6_000_000,DAY(2),{'observed_at':DAY(3)})])
        row=evaluate(data,'B');self.assertEqual(row['score'],0)
        self.assertEqual(row['details']['invoice_checks'][0]['prior_paid_vnd'],0)
        self.assertTrue(row['details']['simultaneous_checks'][0]['matched'])
        self.assertEqual(evaluate(data,'A')['details']['simultaneous_checks'],[])

    def test_valid_signed_adjustment_reduces_prior_once_without_rewriting_past(self):
        data=payments([('OLD',12_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD'}),('NEW',1_000_000,DAY(3))],cap=12_000_000)
        before=canonical(data);row=evaluate(data,'NEW')
        self.assertEqual((row['status'],row['score']),('evaluated_no_hit',0))
        self.assertEqual(row['details']['invoice_checks'][0]['prior_paid_vnd'],10_000_000)
        self.assertEqual(evaluate(data,'REDUCE')['status'],'not_applicable')
        self.assertEqual(canonical(data),before)

    def test_negative_correction_in_same_group_stays_separate_from_prior(self):
        data=payments([('OLD',10_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD'}),('NEW',1_000_000,DAY(2))])
        row=evaluate(data,'NEW');self.assertTrue(row['matched'])
        check=row['details']['simultaneous_checks'][0]
        self.assertEqual(check['cumulative_paid_vnd'],9_000_000);self.assertFalse(check['matched'])

    def test_late_correction_and_later_global_asof_do_not_rewrite_old_row(self):
        data=payments([('OLD',12_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD','observed_at':DAY(4)}),('NEW',1_000_000,DAY(3))],cap=12_000_000)
        before=evaluate(data,'NEW',DAY(3));after=evaluate(data,'NEW',DAY(20))
        self.assertTrue(before['matched']);self.assertEqual(before,after)

    def test_missing_partial_stale_coverage_and_unknown_channel_stay_null(self):
        base=payments([('OLD',4_000_000,DAY(1)),('NEW',7_000_000,DAY(2))])
        for kind in ('missing','partial','stale','channel'):
            with self.subTest(kind=kind):
                data=copy.deepcopy(base)
                if kind=='missing':data['payment_history_coverage']=[]
                elif kind=='partial':data['payment_history_coverage'][-1]['coverage_status']='partial'
                elif kind=='stale':data['payment_history_coverage']=data['payment_history_coverage'][:1]
                else:
                    data['transactions'][0]['payment_channel']='unknown';refresh(data)
                row=evaluate(data,'NEW');self.assertEqual(row['status'],'unavailable')
                self.assertIsNone(row['score']);self.assertIsNone(row['matched']);self.assertTrue(row['gaps'])

    def test_bad_adjustment_link_over_reversal_and_sign_mismatch_are_unavailable(self):
        for kind in ('link','over','sign','unbound'):
            with self.subTest(kind=kind):
                data=payments([('OLD',10_000_000,DAY(1)),('OTHER',5_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD'}),('NEW',1_000_000,DAY(3))])
                a=data['payment_allocations'][2]
                if kind=='link':a['adjusts_ref']['record_id']='A_OTHER'
                elif kind=='over':a['amount_vnd']=-11_000_000;data['transactions'][2]['amount_vnd']=-11_000_000
                elif kind=='sign':a['amount_vnd']=2_000_000
                else:
                    a['kind']='allocation';a['amount_vnd']=2_000_000;data['transactions'][2]['amount_vnd']=2_000_000
                refresh(data);row=evaluate(data,'NEW')
                self.assertEqual(row['status'],'unavailable');self.assertIsNone(row['score'])
                self.assertTrue(row['reason']['code'].startswith('p1_'))

    def test_known_correction_without_allocation_does_not_silently_disappear(self):
        data=payments([('OLD',10_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD'}),('NEW',1_000_000,DAY(3))])
        data['payment_allocations'].pop(1);refresh(data)
        row=evaluate(data,'NEW');self.assertIsNone(row['score'])
        self.assertTrue(any(g['code']=='p1_adjustment_allocation_missing' for g in row['gaps']))

    def test_allocation_revision_replaces_old_amount_not_added_twice(self):
        data=payments([('OLD',6_000_000,DAY(1)),('NEW',6_000_000,DAY(3))])
        revised=copy.deepcopy(data['payment_allocations'][0]);revised.update(revision=2,amount_vnd=5_000_000,observed_at=DAY(2))
        data['payment_allocations'].append(revised);refresh(data)
        row=evaluate(data,'NEW');self.assertEqual(row['details']['invoice_checks'][0]['prior_paid_vnd'],5_000_000)
        self.assertEqual(row['score'],20)

    def test_stale_transaction_revision_link_is_unavailable(self):
        data=payments([('OLD',6_000_000,DAY(1)),('NEW',6_000_000,DAY(3))])
        revised=copy.deepcopy(data['transactions'][0]);revised.update(revision=2,amount_vnd=5_000_000,observed_at=DAY(2))
        data['transactions'].append(revised);refresh(data)
        row=evaluate(data,'NEW');self.assertIsNone(row['score'])
        self.assertEqual(row['reason']['code'],'p1_allocation_revision_unresolved')

    def test_partial_allocation_not_full_transaction_amount_and_overallocation_is_unavailable(self):
        data=payments([('OLD',4_000_000,DAY(1)),('NEW',12_000_000,DAY(2),{'allocated':6_000_000})])
        row=evaluate(data,'NEW');self.assertEqual(row['score'],0)
        self.assertEqual(row['details']['invoice_checks'][0]['current_allocated_vnd'],6_000_000)
        data['payment_allocations'][-1]['amount_vnd']=13_000_000;refresh(data)
        self.assertEqual(evaluate(data,'NEW')['reason']['code'],'p1_allocated_exceeds_payment')

    def test_erp_aliases_share_cap_without_doubling_invoice_value(self):
        data=payments([('OLD',6_000_000,DAY(1)),('NEW',6_000_000,DAY(2))])
        alias=copy.deepcopy(data['invoices'][0]);alias.update(record_id='I_ALIAS',number='0000-123');alias['source']['record_id']='I_ALIAS'
        data['invoices'].append(alias);data['payment_allocations'][-1]['invoice_ref']['record_id']='I_ALIAS';refresh(data)
        row=evaluate(data,'NEW');self.assertEqual(row['score'],20)
        self.assertEqual(row['details']['invoice_checks'][0]['invoice_gross_vnd'],10_000_000)
        data['invoices'][-1]['amount_vnd']=11_000_000;refresh(data)
        self.assertEqual(evaluate(data,'NEW')['reason']['code'],'p1_invoice_value_conflict')

    def test_invoice_credit_note_reduces_cap_using_explicit_source_chain(self):
        data=payments([('OLD',4_000_000,DAY(1)),('NEW',5_000_000,DAY(3))])
        note=copy.deepcopy(data['invoices'][0]);note.update(record_id='CREDIT',number='CN-1',kind='credit_note',amount_vnd=-2_000_000,
            effective_at=DAY(2),observed_at=DAY(2),adjusts_ref=dict(record_id='I001',revision=1),adjustment_reason='Giảm nghĩa vụ theo chứng từ')
        note['source']['record_id']='CREDIT';data['invoices'].append(note);refresh(data)
        row=evaluate(data,'NEW');self.assertEqual(row['score'],20)
        self.assertEqual(row['details']['invoice_checks'][0]['invoice_gross_vnd'],8_000_000)

    def test_multi_invoice_allocation_never_reuses_full_transaction_for_each_cap(self):
        data=payments([('OLD',4_000_000,DAY(1)),('NEW',12_000_000,DAY(2),{'allocated':6_000_000})])
        invoice=copy.deepcopy(data['invoices'][0]);invoice.update(record_id='I_TWO',number='INV-TWO');invoice['source']['record_id']='I_TWO'
        data['invoices'].append(invoice)
        alloc=copy.deepcopy(data['payment_allocations'][-1]);alloc.update(record_id='A_NEW_TWO',invoice_ref=dict(record_id='I_TWO',revision=1))
        alloc['source']['record_id']='A_NEW_TWO';data['payment_allocations'].append(alloc);refresh(data)
        row=evaluate(data,'NEW');self.assertEqual(row['score'],0)
        self.assertEqual(len(row['details']['invoice_checks']),2)
        self.assertEqual(sorted(c['cumulative_paid_vnd'] for c in row['details']['invoice_checks']),[6_000_000,10_000_000])

    def test_alias_missing_coverage_is_not_treated_as_zero_prior(self):
        data=payments([('OLD',6_000_000,DAY(1)),('NEW',6_000_000,DAY(2))])
        alias=copy.deepcopy(data['invoices'][0]);alias.update(record_id='I_ALIAS');alias['source']['record_id']='I_ALIAS'
        data['invoices'].append(alias);data['payment_allocations'][-1]['invoice_ref']['record_id']='I_ALIAS';refresh(data)
        for claim in data['payment_history_coverage']:
            claim['invoice_refs']=[dict(record_id='I_ALIAS',revision=1)];claim['manifest']=export_manifest(data,claim)
        row=evaluate(data,'NEW');self.assertIsNone(row['score']);self.assertTrue(row['gaps'])

    def test_adjustment_chain_deltas_are_counted_once(self):
        data=payments([('OLD',10_000_000,DAY(1)),('DOWN',-3_000_000,DAY(2),{'adjusts':'OLD'}),
            ('UNDO_PART',1_000_000,DAY(3),{'adjusts':'DOWN'}),('NEW',2_000_000,DAY(4))])
        row=evaluate(data,'NEW');self.assertEqual(row['score'],0)
        self.assertEqual(row['details']['invoice_checks'][0]['prior_paid_vnd'],8_000_000)

    def test_future_invoice_revision_does_not_change_past_cap(self):
        data=payments([('OLD',4_000_000,DAY(1)),('NEW',7_000_000,DAY(2))])
        before=evaluate(data,'NEW')
        revised=copy.deepcopy(data['invoices'][0]);revised.update(revision=2,amount_vnd=99_000_000,observed_at=DAY(4))
        data['invoices'].append(revised);refresh(data)
        self.assertEqual(evaluate(data,'NEW'),before)

    def test_correction_allocated_only_to_other_invoice_cannot_be_ignored(self):
        data=payments([('OLD',10_000_000,DAY(1)),('REDUCE',-2_000_000,DAY(2),{'adjusts':'OLD'}),('NEW',1_000_000,DAY(3))])
        invoice=copy.deepcopy(data['invoices'][0]);invoice.update(record_id='I_OTHER',number='OTHER');invoice['source']['record_id']='I_OTHER'
        data['invoices'].append(invoice);data['payment_allocations'][1]['invoice_ref']['record_id']='I_OTHER';refresh(data)
        row=evaluate(data,'NEW');self.assertIsNone(row['score'])
        self.assertTrue(any(g['code']=='p1_adjustment_allocation_missing' for g in row['gaps']))

    def test_large_signed_vnd_totals_are_exact_integers(self):
        cap=90_071_992_547_409_932
        data=payments([('OLD',cap-2,DAY(1)),('NEW',4,DAY(2))],cap=cap)
        row=evaluate(data,'NEW');self.assertEqual(row['score'],20)
        self.assertEqual(row['details']['invoice_checks'][0]['excess_vnd'],2)

    def test_native_positive_single_invoice_parity_including_simultaneous_groups(self):
        from datetime import timedelta
        for amounts,days in (((4_000_000,7_000_000),(0,1)),((4_000_000,6_000_001),(0,1)),((4_000_000,4_000_000,4_000_000),(0,1,1))):
            case=Case();native_rows=[]
            for index,(amount,day) in enumerate(zip(amounts,days)):
                native_rows.append(case.pay(case.at+timedelta(days=day),amount,invoice_number='0000123',invoice_gross_vnd=10_000_000,payment_channel='cash',credit_account='111',recipient_account=''))
            case.score();native=score_rules(case.tables,features=case.features)
            data=payments([(f'T{i}',amount,DAY(day+1),{'payment_channel':'cash'}) for i,(amount,day) in enumerate(zip(amounts,days))])
            for index,native_row in enumerate(native_rows):
                expected=[h for h in native['hits'] if h['rule_id']=='P1' and h['transaction_id']==native_row['transaction_id'] and h['points']>0]
                row=evaluate(data,f'T{index}');self.assertEqual(row['matched'],bool(expected))
                self.assertEqual(row['score'],expected[0]['points'] if expected else 0)
            group=[e for e in native['batch_events'] if e['rule_id']=='P1' and e['signal']]
            actual=[g for g in evaluate(data,f'T{len(amounts)-1}')['details']['simultaneous_checks'] if g['matched']]
            self.assertEqual(len(actual),len(group))
            if group:self.assertEqual(actual[0]['cumulative_paid_vnd'],group[0]['evidence']['cumulative_paid_vnd'])

    def test_snapshot_keeps_every_row_no_fit_and_aggregate_unavailable(self):
        data=payments([('OLD',4_000_000,DAY(1)),('NEW',7_000_000,DAY(2))])
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshots.sqlite3');sid=committed(store,data=data)
            with patch('sme_fraud.method_adapters.fit_local_reference',side_effect=AssertionError('implicit fit')):
                result=score_snapshot(store,scope(),sid,DAY(5),methods=('ecod',))
            self.assertEqual(result['row_count'],2);self.assertEqual(result['feature_contract_fingerprint'],feature_contract()['fingerprint'])
            for row in result['rows']:
                self.assertIsNone(row['methods']['rules']['score'])
                self.assertEqual(row['methods']['ecod']['reason']['code'],'artifact_missing')
                self.assertEqual(row['methods']['rules']['details']['rule_results']['aggregate']['reason']['code'],'rules_incomplete')


if __name__=='__main__':unittest.main()
