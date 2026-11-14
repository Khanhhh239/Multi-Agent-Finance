"""Whole native score/hit/exception/diagnostic parity on the same raw sources."""
import copy
import json
from pathlib import Path
import unittest
import jsonschema
from sme_fraud.import_files import canonical,digest,ImportFailure
from sme_fraud.method_adapters import native_inputs,score_batch
from rule_parity_support import compare_native,prepared_case,company_tables
from finance_input import AccessScope

SCHEMA=json.loads((Path(__file__).resolve().parents[1]/'sme_fraud/method_scores.schema.json').read_text('utf-8'))


class NativeRuleParityTests(unittest.TestCase):
    def check_case(self,kind):
        case=prepared_case(kind);checked,adapted,baseline,raw,frame=compare_native(case.tables,case.config)
        jsonschema.validate(adapted,SCHEMA)
        self.assertTrue(all(checked['checks'].values()),checked)
        return case,checked,adapted,baseline,raw,frame

    def test_simultaneous_invoice_warning_is_retained_as_batch_evidence(self):
        _,checked,adapted,baseline,_,_=self.check_case('batch_overpayment')
        self.assertTrue(any(e['rule_id']=='P1' and e['signal'] is True for e in baseline['batch_events']))
        self.assertTrue(checked['checks']['all_transactions_retained'])
        self.assertTrue(checked['checks']['native_diagnostics_equal'])
        self.assertEqual(adapted['native_rule_diagnostics']['output']['batch_events'],baseline['batch_events'])

    def test_five_default_rows_include_zero_scores(self):
        _,checked,_,_,_,_=self.check_case('five_default')
        self.assertEqual(checked['counts']['input_rows'],5)
        self.assertGreater(checked['counts']['zero_score_rows'],0)

    def test_pinned_legacy_profile_is_compared_without_switching_to_defaults(self):
        _,checked,_,_,_,_=self.check_case('five_legacy')
        self.assertEqual(checked['config']['noise_policy'],'legacy')

    def test_self_approval_alert_and_lawful_exception_both_survive(self):
        _,checked,_,baseline,_,_=self.check_case('self_approval')
        hits=[h for h in baseline['hits'] if h['rule_id']=='C2']
        self.assertTrue(any(h['suppressed_reason'] and h['points']==0 and h['hard_trigger']==0 for h in hits))
        self.assertTrue(any(not h['suppressed_reason'] and h['points']==20 and h['hard_trigger']==1 for h in hits))
        self.assertGreater(checked['counts']['operational_alerts'],0)

    def test_bound_installment_exceptions_are_not_filtered_out(self):
        _,checked,_,_,_,_=self.check_case('installments')
        self.assertGreater(checked['counts']['suppressed_by_rule'].get('A1',0),0)
        self.assertGreater(checked['counts']['suppressed_by_rule'].get('A2',0),0)

    def test_callback_known_later_preserves_before_and_after_results(self):
        _,checked,_,baseline,_,_=self.check_case('bank_callback_revision')
        hits=[h for h in baseline['hits'] if h['rule_id']=='B7']
        self.assertTrue(any(h['points']>0 for h in hits))
        self.assertGreater(checked['counts']['suppressed_by_rule'].get('B7',0),0)

    def test_paid_leave_keeps_hr_exception_evidence(self):
        _,checked,_,_,_,_=self.check_case('paid_leave')
        self.assertGreater(checked['counts']['suppressed_by_rule'].get('E1',0),0)

    def test_explicit_authority_matrix_keeps_permitted_exception(self):
        _,_,_,baseline,_,_=self.check_case('authority_matrix')
        hit=next(h for h in baseline['hits'] if h['rule_id']=='C2')
        self.assertEqual(hit['evidence']['authority_check']['mode'],'authority_matrix')
        self.assertEqual(hit['points'],0);self.assertTrue(hit['suppressed_reason'])

    def test_batch_installment_exception_is_retained_once_in_diagnostics(self):
        _,checked,adapted,baseline,_,_=self.check_case('batch_installment_exception')
        self.assertGreater(checked['counts']['batch_exceptions'],0)
        ids=[e['event_id'] for e in adapted['native_rule_diagnostics']['output']['batch_events']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(ids),len(baseline['batch_events']))

    def test_missing_one_engine_row_returns_five_results_and_one_unavailable(self):
        _,_,_,_,raw,frame=self.check_case('five_default')
        missing=raw['result']['scores'].pop(2)['transaction_id']
        scope=AccessScope('parity-demo',frozenset({'C001'}),'parity-review',frozenset({'data.import'}))
        result=score_batch(frame,scope,methods=(),rule_output=raw)
        jsonschema.validate(result,SCHEMA);self.assertEqual(result['row_count'],5)
        rule=next(r['methods']['rules'] for r in result['rows'] if r['record_id']==missing)
        self.assertFalse(rule['available']);self.assertIsNone(rule['score']);self.assertIsNone(rule['raw_score'])
        self.assertEqual(rule['reason']['code'],'rule_result_missing')

    def test_returned_objects_do_not_alias_input_engine_output(self):
        _,_,adapted,_,raw,_=self.check_case('self_approval');before=digest(canonical(raw))
        adapted['rows'][0]['methods']['rules']['details']['native_score']['rule_score']=999
        adapted['rows'][0]['methods']['rules']['details']['hits'].clear()
        adapted['native_rule_diagnostics']['output']['config']['operational_score']=999
        self.assertEqual(digest(canonical(raw)),before)

    def test_foreign_diagnostics_and_out_of_input_batch_participants_are_rejected(self):
        _,_,_,_,raw,frame=self.check_case('batch_overpayment')
        scope=AccessScope('parity-demo',frozenset({'C001'}),'parity-review',frozenset({'data.import'}))
        foreign=copy.deepcopy(raw);foreign['result']['batch_events'][0]['company_id']='C002'
        with self.assertRaises(ImportFailure):score_batch(frame,scope,methods=(),rule_output=foreign)
        unrelated=copy.deepcopy(raw);unrelated['result']['batch_events'][0]['transaction_ids'].append('NOT_IN_INPUT')
        with self.assertRaises(ValueError):score_batch(frame,scope,methods=(),rule_output=unrelated)

    def test_input_permutation_and_duplicate_ids_are_not_silent_row_filters(self):
        case=prepared_case('five_default');case.tables['transactions'].reverse()
        checked,_,_,_,_=compare_native(case.tables,case.config)
        self.assertTrue(all(checked['checks'].values()))
        tables=company_tables(case.tables);tables['transactions'].append(copy.deepcopy(tables['transactions'][0]))
        scope=AccessScope('parity-demo',frozenset({'C001'}),'parity-review',frozenset({'data.import'}))
        with self.assertRaises(ValueError):native_inputs(tables,scope,config=case.config)


if __name__=='__main__':unittest.main()
