import unittest
from datetime import datetime, timedelta, timezone

# Reuse evaluate's supported workspace dependency bootstrap before scipy is needed.
from sme_fraud.evaluate import threshold_metrics
from sme_fraud.benford import digits_test, monthly_diagnostics


class BenfordTest(unittest.TestCase):
    def test_log_uniform_population_and_future_records(self):
        amounts = [int(10 ** (3 + 4 * i / 1600)) for i in range(1600)]
        result = digits_test(amounts, 'first')
        self.assertEqual(result['status'], 'evaluated')
        self.assertGreater(result['pvalue'], .05)
        self.assertAlmostEqual(sum(result['expected_counts']), len(amounts), places=6)
        start = datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=7)))
        rows = [dict(company_id='C1', creator_id='E1', approval_limit_vnd=100_000_000,
                     transaction_id=f'T{i:05}', posted_at=(start + timedelta(days=i % 25, minutes=i)).isoformat(),
                     amount_vnd=value, is_financial_entry=1, payment_channel='bank', txn_type='vendor_payment')
                for i, value in enumerate(amounts)]
        original = monthly_diagnostics({'transactions': rows})
        future = [dict(r, posted_at=(start + timedelta(days=140 + i % 25, minutes=i)).isoformat(), transaction_id=f'future{i}')
                  for i, r in enumerate(rows)]
        expanded = monthly_diagnostics({'transactions': rows + future})
        self.assertEqual(original, [r for r in expanded if r['cutoff_at'] <= original[-1]['cutoff_at']])
        self.assertTrue(all(not r['adds_transaction_score'] for r in original))
        test = next(r for r in original if r['rule_id'] == 'D3')
        self.assertEqual(test['status'], 'evaluated')
        self.assertTrue(set(test['excess_leading_pairs']) <= {98, 99})


if __name__ == '__main__':
    unittest.main()
