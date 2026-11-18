"""Native source boundary: real engine, missingness, chronology and company scope."""
from copy import deepcopy
from datetime import datetime,timedelta
import unittest
from unittest.mock import patch
from finance_input import AccessScope
from sme_fraud.import_files import canonical,digest,ImportFailure
from sme_fraud.native_rule_demo import scenario
from sme_fraud.native_rule_node import validate_bundle,evaluate_bundle,REQUIRED
from sme_fraud.rules import RULE_NAMES,score_rules


def scope(company='C001',actor='native-test'):return AccessScope('native-demo',frozenset({company}),actor,frozenset({'data.import'}))


def rehash(bundle,table):
    bundle['coverage'][table].update(record_count=len(bundle['tables'][table]),records_sha256=digest(canonical(bundle['tables'][table])))


class NativeRuleNode(unittest.TestCase):
    def test_all_transaction_rules_positive_control_and_independent_native_parity(self):
        for code in RULE_NAMES:
            if code.startswith('D'):continue
            for positive in (True,False):
                with self.subTest(rule=code,positive=positive):
                    bundle,_=scenario(code,positive);before=canonical(bundle);result=evaluate_bundle(bundle,scope());entry=next(r for r in result['rules'] if r['rule_id']==code)
                    self.assertTrue(entry['available']);self.assertEqual(entry['matched'],positive);self.assertEqual(len(result['rules']),35)
                    self.assertEqual(result['native_reference_sha256'],digest(canonical(score_rules(deepcopy(bundle['tables'])))))
                    self.assertEqual(before,canonical(bundle));self.assertIsNone(result['accuracy']);self.assertIsNone(result['aggregate_score']);self.assertFalse(result['he_execution']);self.assertFalse(result['model_fit_performed'])

    def test_missing_or_incomplete_manifest_is_unavailable_not_zero(self):
        for code in RULE_NAMES:
            if code.startswith('D'):continue
            bundle,_=scenario(code,True);table=REQUIRED[code][-1];bundle['coverage'].pop(table)
            with self.subTest(rule=code):
                result=evaluate_bundle(bundle,scope());r=next(r for r in result['rules'] if r['rule_id']==code)
                self.assertFalse(r['available']);self.assertIsNone(r['matched']);self.assertIsNone(r['score']);self.assertTrue(any(g['reason']=='source_coverage_missing' for g in r['gaps']))
        bundle,_=scenario('A1',True);bundle['coverage']['transactions']['history_basis']='bounded_period'
        r=next(r for r in evaluate_bundle(bundle,scope())['rules'] if r['rule_id']=='A1');self.assertFalse(r['available']);self.assertTrue(any(g['reason']=='history_before_window_unknown' for g in r['gaps']))

    def test_stale_manifest_duplicate_or_changed_source_rejected_before_engine(self):
        original,_=scenario('C2',True)
        for change in ('amount','duplicate','timestamp'):
            bundle=deepcopy(original)
            if change=='amount':bundle['tables']['transactions'][0]['amount_vnd']+=1
            elif change=='duplicate':bundle['tables']['transactions'].append(deepcopy(bundle['tables']['transactions'][0]));rehash(bundle,'transactions')
            else:bundle['coverage']['employees']['observed_at']='not-a-timestamp'
            with self.subTest(change=change),patch('sme_fraud.native_rule_node.score_rules',side_effect=AssertionError('must not score')):
                self.assertEqual(validate_bundle(bundle,scope())['status'],'rejected')
                with self.assertRaises(ImportFailure):evaluate_bundle(bundle,scope())

    def test_cross_company_and_missing_permission_denied_before_private_data(self):
        bundle,_=scenario('B1',True)
        for s in (scope('C002'),AccessScope('other',frozenset({'C001'}),'reader',frozenset({'data.import'})),AccessScope('native-demo',frozenset({'C001'}),'reader',frozenset())):
            with self.assertRaises(ImportFailure) as error:evaluate_bundle(bundle,s)
            self.assertEqual(error.exception.status,403)
        mixed=deepcopy(bundle);mixed['tables']['vendors'][0]['company_id']='C002'
        with self.assertRaises(ImportFailure) as error:validate_bundle(mixed,scope())
        self.assertEqual(error.exception.status,403)

    def test_same_transaction_ids_in_two_companies_stay_separate(self):
        results=[]
        for company in ('C001','C002'):
            bundle,_=scenario('B1',True,company);result=evaluate_bundle(bundle,scope(company));results.append(result)
            self.assertEqual(result['company_id'],company);self.assertTrue(next(r for r in result['rules'] if r['rule_id']=='B1')['matched'])
        self.assertEqual(results[0]['record_ids'],results[1]['record_ids']);self.assertNotEqual(results[0]['source_sha256'],results[1]['source_sha256'])

    def test_late_bank_evidence_cannot_change_past_result(self):
        bundle,_=scenario('B7',True);event=bundle['tables']['bank_account_changes'][0];event['observed_at']='2025-09-01T10:00:00+07:00';rehash(bundle,'bank_account_changes')
        future=evaluate_bundle(bundle,scope());without=deepcopy(bundle);without['tables']['bank_account_changes']=[];rehash(without,'bank_account_changes');past=evaluate_bundle(without,scope())
        a=next(r for r in future['rules'] if r['rule_id']=='B7');b=next(r for r in past['rules'] if r['rule_id']=='B7')
        self.assertEqual(a,b);self.assertFalse(a['matched'])

    def test_late_posted_source_accepted_without_rewriting_observation_time(self):
        bundle,_=scenario('A1',True);row=bundle['tables']['transactions'][0];row['observed_at']='2025-09-01T10:00:00+07:00';rehash(bundle,'transactions');before=canonical(bundle)
        result=validate_bundle(bundle,scope());self.assertEqual(result['status'],'accepted');self.assertEqual(before,canonical(bundle))
        r=evaluate_bundle(bundle,scope());self.assertIn(row['transaction_id'],[x['record_id'] for x in r['unavailable_transactions']]);self.assertEqual(before,canonical(bundle))

    def test_labels_features_and_expected_results_never_enter_input(self):
        for kind in ('labels','features','expected_signal'):
            bundle,_=scenario('A1',True);bundle['tables']['transactions'][0]['untrusted_metadata']={kind:True};rehash(bundle,'transactions')
            self.assertEqual(validate_bundle(bundle,scope())['status'],'rejected')

    def test_small_statistical_population_is_unavailable_not_no_hit(self):
        bundle,_=scenario('A1',True);bundle['as_of']='2025-09-01T00:00:00+07:00'
        for claim in bundle['coverage'].values():claim['covered_through']=bundle['as_of'];claim['observed_at']=bundle['as_of']
        result=evaluate_bundle(bundle,scope())
        for r in result['rules']:
            if r['rule_id'].startswith('D'):
                self.assertFalse(r['available']);self.assertIsNone(r['matched']);self.assertIsNone(r['score'])

    def test_e4_is_alias_of_b5_and_never_a_second_aggregate_score(self):
        bundle,_=scenario('E4',True);result=evaluate_bundle(bundle,scope());r=next(r for r in result['rules'] if r['rule_id']=='E4')
        self.assertTrue(r['matched']);self.assertTrue(all(h['source_rule_id']=='B5' for h in r['hits']));self.assertIsNone(result['aggregate_score'])

    def test_negative_native_amount_is_not_silently_abs_or_zero(self):
        bundle,_=scenario('F1',True);row=bundle['tables']['transactions'][0];row['amount_vnd']=-1000;rehash(bundle,'transactions')
        report=validate_bundle(bundle,scope());self.assertEqual(report['status'],'accepted');self.assertEqual(row['amount_vnd'],-1000)

    def test_missing_invoice_value_and_bank_identity_are_not_no_hit(self):
        for code,field,value,reason in [('P1','invoice_gross_vnd',0,'invoice_value_unavailable'),('B1','recipient_bank_code','','recipient_bank_identity_incomplete')]:
            # Zero is supplied by this source fixture, never imputed by adapter.
            bundle,_=scenario(code,True);bundle['tables']['transactions'][0][field]=value;rehash(bundle,'transactions')
            result=evaluate_bundle(bundle,scope());rule=next(r for r in result['rules'] if r['rule_id']==code)
            self.assertFalse(rule['available']);self.assertIsNone(rule['matched']);self.assertTrue(any(g['reason']==reason for g in rule['gaps']))

    def test_future_transactions_remain_listed_with_unavailable_reason(self):
        bundle,_=scenario('A1',True);row=deepcopy(bundle['tables']['transactions'][0]);row['transaction_id']='FUTURE_ONLY'
        for field in ('created_at','approved_at','posted_at','observed_at'):row[field]='2026-01-01T10:00:00+07:00'
        bundle['tables']['transactions'].append(row);rehash(bundle,'transactions');result=evaluate_bundle(bundle,scope())
        self.assertIn('FUTURE_ONLY',result['record_ids']);self.assertEqual(result['row_count'],result['processed_row_count']+1)
        self.assertEqual(result['unavailable_transactions'],[dict(record_id='FUTURE_ONLY',reason='not_known_or_posted_after_as_of')])

    def test_missing_payroll_context_and_master_unknown_at_action_are_rejected(self):
        bundle,_=scenario('E2',True);bundle['tables']['transactions'][0]['payroll_period']='';rehash(bundle,'transactions')
        self.assertEqual(validate_bundle(bundle,scope())['status'],'rejected')
        bundle,_=scenario('B1',True)
        for row in bundle['tables']['employees']:row['recorded_at']=row['observed_at']='2025-12-01T00:00:00+07:00'
        rehash(bundle,'employees');self.assertEqual(validate_bundle(bundle,scope())['status'],'rejected')

    def test_invalid_reference_types_and_transaction_revisions_rejected_cleanly(self):
        for field in ('creator_id','vendor_id'):
            bundle,_=scenario('B1',True);bundle['tables']['transactions'][0][field]=['bad'];rehash(bundle,'transactions')
            self.assertEqual(validate_bundle(bundle,scope())['status'],'rejected')
        bundle,_=scenario('B1',True);row=deepcopy(bundle['tables']['transactions'][0]);row['recorded_at']=row['observed_at']='2025-01-01T00:00:00+07:00'
        bundle['tables']['transactions'].append(row);rehash(bundle,'transactions');self.assertEqual(validate_bundle(bundle,scope())['status'],'rejected')


if __name__=='__main__':unittest.main()
