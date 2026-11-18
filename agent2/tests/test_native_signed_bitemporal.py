"""Independent accounting arithmetic and two-clock boundary regressions."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from sme_fraud.import_files import canonical, digest
from sme_fraud.native_rule_demo import scenario
from sme_fraud.native_rule_node import evaluate_bundle, validate_bundle
from sme_fraud.native_rule_execution import monthly_point_in_time
from sme_fraud.rules import score_rules
from sme_fraud.rule_snapshot import validate
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_native_rule_node import scope, rehash
from test_rule_snapshot import wrap, save, scope as snapshot_scope


def set_cutoff(bundle, at):
    bundle['as_of'] = at
    for claim in bundle['coverage'].values():
        claim.update(observed_at=at, covered_through=at)


def tx_copy(row, identity, at, amount, *, observed=None):
    result = deepcopy(row)
    result.update(transaction_id=identity, amount_vnd=amount)
    for field in ('created_at', 'approved_at', 'posted_at'):
        result[field] = at
    result['observed_at'] = observed or at
    return result


def entry(result, identity, code):
    return next(r for r in result['row_rules'][identity] if r['rule_id'] == code)


class SignedBitemporal(unittest.TestCase):
    def payment_source(self, company='C001'):
        bundle, _ = scenario('P1', True, company)
        base = deepcopy(bundle['tables']['transactions'][0])
        for name in ('journal_documents','journal_lines','transaction_documents'):
            bundle['tables'][name] = []
            rehash(bundle, name)
        return bundle, base

    def test_negative_manual_adjustment_keeps_sign_and_can_trigger_materiality(self):
        for company in ('C001', 'C002'):
            bundle, _ = scenario('F1', True, company)
            tx = bundle['tables']['transactions'][0]
            tx['amount_vnd'] = -30_000_000
            for row in bundle['tables']['journal_lines']:
                row['debit_vnd'] = -row['debit_vnd']
                row['credit_vnd'] = -row['credit_vnd']
            for name in ('transactions','journal_lines'):
                rehash(bundle, name)
            before = canonical(bundle)
            self.assertEqual(validate_bundle(bundle,scope(company))['status'], 'accepted')
            result = evaluate_bundle(bundle,scope(company))
            f1 = entry(result,tx['transaction_id'],'F1')
            self.assertTrue(f1['matched'])
            self.assertEqual(f1['hits'][0]['evidence']['amount_vnd'], -30_000_000)
            self.assertEqual(canonical(bundle), before)
            # Legacy callers retain their original nonnegative contract.
            with self.assertRaises(ValueError):
                score_rules(bundle['tables'])

    def test_unapproved_negative_amount_policies_are_unavailable_not_no_hit(self):
        bundle, _ = scenario('C2', True)
        tx = bundle['tables']['transactions'][0]
        tx['amount_vnd'] = -3_000_000
        rehash(bundle,'transactions')
        result = evaluate_bundle(bundle,scope())
        r = entry(result,tx['transaction_id'],'C2')
        self.assertFalse(r['available'])
        self.assertIsNone(r['matched'])
        self.assertIsNone(r['score'])
        self.assertIn('signed_amount_policy_not_supported',{g['reason'] for g in r['gaps']})
        self.assertTrue(entry(result,tx['transaction_id'],'C1')['available'])

    def test_p1_signed_history_uses_net_amount_without_abs_or_zero(self):
        for total, expected in ((90_000_000,False),(110_000_000,True)):
            bundle, base = self.payment_source()
            base['invoice_gross_vnd'] = 100_000_000
            rows = [tx_copy(base,'PAY','2025-08-10T11:00:00+07:00',80_000_000),
                    tx_copy(base,'ADJUST','2025-08-11T11:00:00+07:00',-20_000_000),
                    tx_copy(base,'NOW','2025-08-12T11:00:00+07:00',total-60_000_000)]
            bundle['tables']['transactions'] = rows
            rehash(bundle,'transactions')
            r = entry(evaluate_bundle(bundle,scope()),'NOW','P1')
            self.assertTrue(r['available'])
            self.assertEqual(r['matched'],expected)
            if expected:
                self.assertEqual(r['hits'][0]['evidence']['cumulative_paid_vnd'],total)
                self.assertEqual(r['hits'][0]['evidence']['excess_vnd'],10_000_000)

    def test_late_history_does_not_change_past_but_is_used_after_arrival(self):
        bundle, base = self.payment_source()
        base['invoice_gross_vnd'] = 100_000_000
        late = tx_copy(base,'LATE','2025-08-10T11:00:00+07:00',80_000_000,
                       observed='2025-08-12T10:00:00+07:00')
        before = tx_copy(base,'BEFORE','2025-08-11T11:00:00+07:00',30_000_000)
        after = tx_copy(base,'AFTER','2025-08-12T11:00:00+07:00',10_000_000)
        bundle['tables']['transactions'] = [late,before,after]
        rehash(bundle,'transactions')
        original = canonical(bundle)
        result = evaluate_bundle(bundle,scope())
        self.assertFalse(entry(result,'BEFORE','P1')['matched'])
        r = entry(result,'AFTER','P1')
        self.assertTrue(r['matched'])
        self.assertEqual(r['hits'][0]['evidence']['cumulative_paid_vnd'],120_000_000)
        without = deepcopy(bundle)
        without['tables']['transactions'].remove(late)
        rehash(without,'transactions')
        self.assertEqual(entry(result,'BEFORE','P1'),entry(evaluate_bundle(without,scope()),'BEFORE','P1'))
        self.assertEqual(canonical(bundle),original)
        receipts=result['execution_provenance']['receipts']
        self.assertEqual(next(r for r in receipts if r['candidate_ids']==['BEFORE'])['history_identity_sha256'],digest(canonical([])))
        self.assertEqual(next(r for r in receipts if r['candidate_ids']==['AFTER'])['history_identity_sha256'],digest(canonical(['BEFORE','LATE'])))

    def test_late_target_keeps_original_clocks_and_is_scored_when_visible(self):
        bundle, _ = scenario('C1',True)
        tx=bundle['tables']['transactions'][0]
        tx['observed_at']=(datetime.fromisoformat(tx['posted_at'])+timedelta(hours=1)).isoformat()
        set_cutoff(bundle,tx['observed_at'])
        rehash(bundle,'transactions')
        result=evaluate_bundle(bundle,scope())
        self.assertTrue(entry(result,tx['transaction_id'],'C1')['matched'])
        self.assertEqual(result['execution_provenance']['receipts'][0]['event_at'],tx['posted_at'])
        self.assertEqual(result['execution_provenance']['receipts'][0]['knowledge_at'],tx['observed_at'])

    def test_late_bound_proof_is_unavailable_for_affected_rule_only(self):
        bundle,_=scenario('F1',True)
        tx=bundle['tables']['transactions'][0]
        for table in ('journal_audit_log','journal_lines'):
            for r in bundle['tables'][table]:
                r['observed_at']=(datetime.fromisoformat(tx['posted_at'])+timedelta(hours=1)).isoformat()
            rehash(bundle,table)
        set_cutoff(bundle,bundle['tables']['journal_lines'][0]['observed_at'])
        result=evaluate_bundle(bundle,scope())
        f1=entry(result,tx['transaction_id'],'F1')
        self.assertFalse(f1['available'])
        self.assertIsNone(f1['matched'])
        self.assertIn('bound_evidence_not_known_at_event',{g['reason'] for g in f1['gaps']})
        self.assertTrue(entry(result,tx['transaction_id'],'C1')['available'])

    def test_signed_and_late_sources_survive_snapshot_route_with_all_rows(self):
        bundle,_=scenario('F1',True)
        tx=bundle['tables']['transactions'][0]
        tx['amount_vnd']=-30_000_000
        tx['observed_at']=(datetime.fromisoformat(tx['posted_at'])+timedelta(hours=1)).isoformat()
        set_cutoff(bundle,tx['observed_at'])
        rehash(bundle,'transactions')
        data=wrap(bundle)
        with tempfile.TemporaryDirectory() as tmp:
            store=SnapshotStore(Path(tmp)/'source.sqlite3')
            saved,_,_=save(store,data)
            result=analyze_snapshot(store,snapshot_scope(),saved['snapshot']['snapshot_id'],bundle['as_of'],technical=True)
            row=result['rows'][0]
            self.assertEqual(row['amount_vnd'],-30_000_000)
            self.assertEqual(row['feature_evidence']['signed_amount_vnd'],-30_000_000)
            self.assertEqual(row['event_at'],tx['posted_at'])
            self.assertEqual(row['knowledge_at'],tx['observed_at'])
            self.assertEqual(len(row['rule_coverage']['rules']),35)
            self.assertEqual(next(r for r in row['rule_coverage']['rules'] if r['rule_id']=='F1')['status'],'evaluated_hit')
            self.assertTrue(result['rule_execution_provenance']['receipts'])
            self.assertEqual(store.get_snapshot(snapshot_scope(),saved['snapshot']['snapshot_id'],data=True),canonical(data))

    def test_missing_invoice_is_per_candidate_not_copied_to_other_rows(self):
        bundle,base=self.payment_source()
        bad=tx_copy(base,'MISSING','2025-08-10T11:00:00+07:00',10_000_000)
        bad.update(invoice_number='OTHER',invoice_gross_vnd=0)
        good=tx_copy(base,'GOOD','2025-08-12T11:00:00+07:00',10_000_000)
        bundle['tables']['transactions']=[bad,good]
        rehash(bundle,'transactions')
        result=evaluate_bundle(bundle,scope())
        self.assertFalse(entry(result,'MISSING','P1')['available'])
        self.assertTrue(entry(result,'GOOD','P1')['available'])

    def test_invalid_signed_scalars_still_rejected(self):
        for amount in (True,-1.5,-10**18):
            bundle,_=scenario('F1',True)
            bundle['tables']['transactions'][0]['amount_vnd']=amount
            rehash(bundle,'transactions')
            self.assertEqual(validate_bundle(bundle,scope())['status'],'rejected')

    def test_simultaneous_payments_use_prior_signed_total_once_and_are_order_invariant(self):
        bundle,base=self.payment_source()
        base['invoice_gross_vnd']=100_000_000
        bundle['tables']['transactions']=[tx_copy(base,'CREDIT','2025-08-11T11:00:00+07:00',-20_000_000),
                                           tx_copy(base,'A','2025-08-12T11:00:00+07:00',70_000_000),
                                           tx_copy(base,'B','2025-08-12T11:00:00+07:00',70_000_000)]
        rehash(bundle,'transactions')
        result=evaluate_bundle(bundle,scope())
        # Individual rows each see -20 + 70 = 50m, not the other same-time row.
        for identity in ('A','B'):
            self.assertFalse(entry(result,identity,'P1')['matched'])
        p1=next(r for r in result['rules'] if r['rule_id']=='P1')
        group=next(g for g in p1['groups'] if set(g['transaction_ids'])=={'A','B'})
        self.assertEqual(group['evidence']['cumulative_paid_vnd'],120_000_000)
        self.assertEqual(group['evidence']['excess_vnd'],20_000_000)
        reverse=deepcopy(bundle)
        reverse['tables']['transactions'].reverse()
        rehash(reverse,'transactions')
        reversed_result=evaluate_bundle(reverse,scope())
        self.assertEqual(result['row_rules'],reversed_result['row_rules'])

    def test_closed_month_statistic_excludes_records_learned_after_its_cutoff(self):
        bundle,base=self.payment_source()
        rows=[tx_copy(base,'KNOWN','2025-08-10T11:00:00+07:00',5_000_001),
              tx_copy(base,'LATE','2025-08-11T11:00:00+07:00',6_000_002,observed='2025-09-02T11:00:00+07:00'),
              tx_copy(base,'SEPT','2025-09-10T11:00:00+07:00',7_000_003)]
        diagnostics=monthly_point_in_time(dict(transactions=rows),'2025-10-01T00:00:00+07:00')
        sept=next(r for r in diagnostics if r['rule_id']=='D1' and r['cutoff_at'].startswith('2025-09-01'))
        october=next(r for r in diagnostics if r['rule_id']=='D1' and r['cutoff_at'].startswith('2025-10-01'))
        self.assertEqual(sept['rows'],1)
        self.assertEqual(october['rows'],3)

    def test_missing_source_stays_local_to_rule_and_candidate_on_snapshot_route(self):
        bundle,base=self.payment_source()
        bad=tx_copy(base,'BAD','2025-08-10T11:00:00+07:00',10_000_000)
        bad.update(invoice_number='OTHER',invoice_gross_vnd=0)
        good=tx_copy(base,'GOOD','2025-08-12T11:00:00+07:00',10_000_000)
        bundle['tables']['transactions']=[bad,good]
        rehash(bundle,'transactions')
        data=wrap(bundle,['BAD','GOOD'])
        with tempfile.TemporaryDirectory() as tmp:
            store=SnapshotStore(Path(tmp)/'source.sqlite3')
            saved,_,_=save(store,data)
            r=analyze_snapshot(store,snapshot_scope(),saved['snapshot']['snapshot_id'],bundle['as_of'],technical=True)
            first,second=r['rows']
            self.assertFalse(next(e for e in first['rule_coverage']['rules'] if e['rule_id']=='P1')['available'])
            self.assertTrue(next(e for e in second['rule_coverage']['rules'] if e['rule_id']=='P1')['available'])
            self.assertTrue(next(e for e in first['rule_coverage']['rules'] if e['rule_id']=='C1')['available'])

    def test_company_not_known_at_event_is_not_a_no_hit(self):
        bundle,_=scenario('C1',True)
        tx=bundle['tables']['transactions'][0]
        for r in bundle['tables']['companies']:
            r['recorded_at']=r['observed_at']='2025-08-13T00:00:00+07:00'
        tx['observed_at']='2025-08-13T01:00:00+07:00'
        set_cutoff(bundle,'2025-08-13T02:00:00+07:00')
        for name in ('companies','transactions'):
            rehash(bundle,name)
        r=entry(evaluate_bundle(bundle,scope()),tx['transaction_id'],'C1')
        self.assertEqual(r['status'],'unavailable')
        self.assertIsNone(r['matched'])
        self.assertIn('company_not_known_at_event',{g['reason'] for g in r['gaps']})

    def test_future_bound_proof_does_not_change_past_rule_result(self):
        bundle,_=scenario('F1',True)
        tx=bundle['tables']['transactions'][0]
        later=deepcopy(bundle['tables']['journal_audit_log'][0])
        later['audit_id']='FUTURE_AUDIT'
        later['observed_at']='2025-09-01T00:00:00+07:00'
        later['entry_origin']='automatic'
        earlier=evaluate_bundle(bundle,scope())
        bundle['tables']['journal_audit_log'].append(later)
        rehash(bundle,'journal_audit_log')
        set_cutoff(bundle,'2025-09-01T00:00:00+07:00')
        after=evaluate_bundle(bundle,scope())
        self.assertEqual(entry(earlier,tx['transaction_id'],'F1'),entry(after,tx['transaction_id'],'F1'))

    def test_malformed_signed_journal_cannot_bypass_source_validation(self):
        bundle,_=scenario('F1',True)
        row=bundle['tables']['journal_lines'][0]
        row.update(debit_vnd=-1_000,credit_vnd=1_000)
        rehash(bundle,'journal_lines')
        report=validate_bundle(bundle,scope())
        self.assertEqual(report['status'],'rejected')
        self.assertTrue(any(e['path'].endswith('.credit_vnd') for e in report['errors']))


if __name__=='__main__':
    unittest.main()
