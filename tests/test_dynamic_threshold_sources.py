"""Accounting units, source binding and rule-engine integration for rolling thresholds."""
import copy
from datetime import timedelta
import unittest

from sme_fraud.threshold_sources import extract_observations
from sme_fraud.rule_audit_cases import Case
from test_dynamic_thresholds import NOW


def transaction(identity='T1', **values):
    return dict(dict(transaction_id=identity, company_id='C001', posted_at=NOW.isoformat(),
        amount_vnd=11_000_000, currency='VND', is_financial_entry=1, debit_account='6421',
        credit_account='1121', payment_channel='bank', txn_type='cash_expense'), **values)


def line(identity, account='6421', debit=0, credit=0, **values):
    return dict(dict(line_id=identity, document_id='D1', company_id='C001',
        transaction_id='T1', posted_at=NOW.isoformat(), account_code=account,
        debit_vnd=debit, credit_vnd=credit), **values)


class ThresholdSourcesTest(unittest.TestCase):
    def test_document_account_debits_aggregate_without_vat_assets_or_credit_netting(self):
        tables = dict(transactions=[transaction()], journal_lines=[line('L1', debit=6_000_000),
            line('L2', debit=4_000_000), line('L3', '1331', debit=1_000_000),
            line('L4', '1121', credit=11_000_000), line('L5', '6421', credit=2_000_000),
            line('L6', '211', debit=3_000_000), line('L7', '6422', debit=500_000)])
        rows, summary = extract_observations(tables)
        expense = {r['account_code']: r for r in rows if r['measurement'] == 'expense_debit'}
        self.assertEqual({k:r['amount_vnd'] for k,r in expense.items()}, {'6421': 10_000_000, '6422': 500_000})
        self.assertEqual(next(r for r in rows if r['measurement'] == 'cash_outflow')['amount_vnd'], 11_000_000)
        self.assertTrue(summary['ledger_available'])
        self.assertFalse(any(r['measurement'] == 'transaction_amount' for r in rows))

    def test_payroll_and_payable_settlements_do_not_create_another_expense(self):
        for purpose, account in (('payroll', '334'), ('vendor_payment', '331')):
            tables = dict(transactions=[transaction(txn_type=purpose, debit_account=account)],
                journal_documents=[dict(company_id='C001', document_id='D1', transaction_id='',
                    purpose='salary_accrual' if purpose == 'payroll' else 'invoice_accrual', posted_at=NOW.isoformat())],
                journal_lines=[line('ACCRUAL', '622', debit=10_000_000, transaction_id='')])
            rows, _ = extract_observations(tables)
            self.assertEqual(len(rows), 2)
            expense = next(r for r in rows if r['measurement'] == 'expense_debit')
            self.assertEqual(expense['source_transaction_id'], '')
            payment = next(r for r in rows if r['measurement'] == 'cash_outflow')
            self.assertEqual(payment['account_code'], account)
            self.assertEqual(payment['family'], 'payroll' if purpose == 'payroll' else 'payables')

    def test_without_ledger_fallback_is_separately_named_and_nonfinancial_events_are_excluded(self):
        rows, summary = extract_observations(dict(transactions=[transaction(), transaction('T2', is_financial_entry=0)]))
        self.assertFalse(summary['ledger_available'])
        self.assertEqual({r['measurement'] for r in rows}, {'transaction_amount', 'cash_outflow'})
        self.assertTrue(all(r['source_transaction_id'] == 'T1' for r in rows))

    def test_knowledge_time_is_latest_header_line_or_bound_transaction(self):
        later = (NOW+timedelta(days=2)).isoformat()
        rows, _ = extract_observations(dict(transactions=[transaction(observed_at=later)],
            journal_lines=[line('L', debit=10_000_000)]))
        self.assertTrue(all(r['observed_at'] == later for r in rows))

    def test_ambiguous_duplicate_cross_company_and_mismatched_dates_fail(self):
        source = dict(transactions=[transaction()], journal_lines=[line('L', debit=1_000_000)])
        invalid = []
        duplicate = copy.deepcopy(source)
        duplicate['journal_lines'].append(duplicate['journal_lines'][0].copy())
        invalid.append(duplicate)
        for values in ({'company_id': 'OTHER'}, {'posted_at': (NOW+timedelta(days=1)).isoformat()},
                       {'debit_vnd': -1}, {'credit_vnd': 1}):
            bad = copy.deepcopy(source)
            bad['journal_lines'][0].update(values)
            invalid.append(bad)
        for tables in invalid:
            with self.subTest(tables=tables), self.assertRaises(ValueError):
                extract_observations(tables)

    def test_default_engine_uses_rolling_account_and_emits_replayable_a5_evidence(self):
        case = Case()
        for index in range(6):
            case.pay(case.at-timedelta(days=index+1), 1_000_000, kind='cash_expense')
        current = case.pay(amount=15_000_000, kind='cash_expense')
        case.config = dict(noise_policy='phase2', amount_baseline='rolling_account',
                           dynamic_min_samples=2, dynamic_cycle_enabled=False)
        result = case.score()
        hit = next(r for r in result['hits'] if r['rule_id'] == 'A5' and r['transaction_id'] == current['transaction_id'])
        evidence = hit['evidence']
        self.assertEqual(evidence['method'], 'rolling_account')
        self.assertEqual(evidence['selected_parameter']['sample_count'], 6)
        self.assertEqual(evidence['threshold_vnd'], 1_000_000)
        self.assertTrue(evidence['selected_parameter']['parameter_id'])
        self.assertEqual(result['dynamic_policy']['windows'], [30, 60, 90])
        self.assertTrue(result['dynamic_parameters'])
        self.assertFalse(hit.get('hard_trigger', False))


if __name__ == '__main__':
    unittest.main()
