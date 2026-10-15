"""Window-level intervention truth, distinct from transaction fraud labels."""
import math
import random
from datetime import datetime, timedelta

from .generate import TZ

PATTERNS = ('natural', 'first_digit_shift', 'second_digit_shift', 'near_limit_shift',
            'suffix_shift', 'far_below_limit_pairs', 'small_sample', 'fixed_legitimate')


def window_case(seed, pattern, size=3000):
    rng = random.Random(seed)
    rows = []
    older = datetime(2025, 6, 10, 12, tzinfo=TZ)
    recent = datetime(2025, 9, 1, 12, tzinfo=TZ)
    size = 100 if pattern == 'small_sample' else size
    for phase, start, days in [('baseline', older, 80), ('current', recent, 29)]:
        for i in range(size):
            amount = int(10**rng.uniform(5, 8))
            suffix = rng.choice((0,500,999)) if rng.random() < .3 else rng.randrange(1000)
            amount = amount//1000*1000 + suffix
            manipulated = phase == 'current' and rng.random() < .6
            if manipulated:
                if pattern == 'first_digit_shift':
                    remainder = int((str(amount)[1:]+'000000')[:6])
                    amount = (9_000_000+remainder)//1000*1000 + amount%1000
                elif pattern == 'second_digit_shift':
                    first = rng.choices(range(1,10), weights=[math.log10(1+1/d) for d in range(1,10)])[0]
                    amount = first*1_000_000+900_000+rng.randrange(100000)
                elif pattern == 'near_limit_shift':
                    amount = rng.randrange(98_000_000,100_000_000)
                elif pattern == 'far_below_limit_pairs':
                    amount = rng.randrange(98_000,100_000)
                elif pattern == 'suffix_shift':
                    amount = amount//1000*1000
            if pattern == 'fixed_legitimate':
                amount = 17_000_000
            row = dict(company_id='C001', transaction_id=f'{phase}_{i}', creator_id='E_CONTROL',
                posted_at=(start+timedelta(days=i%days, seconds=i)).isoformat(), amount_vnd=amount,
                approval_limit_vnd=100_000_000, is_financial_entry=1, payment_channel='bank', txn_type='vendor_payment',
                department='sales' if i%2 else 'operations', project_id='P1' if i%2 else 'P2')
            rows.append(row)
    cutoff = '2025-10-01T00:00:00+07:00'
    # These labels identify a deliberate intervention affecting a statistic,
    # not financial fraud or membership of any suspicious transaction.
    expected = dict(D1=False, D2=False, D3=False, D4=False, D5=False, D6=False)
    if pattern in {'first_digit_shift', 'near_limit_shift', 'far_below_limit_pairs'}:
        expected.update(D1=True, D5=True, D6=True)
    if pattern in {'near_limit_shift', 'far_below_limit_pairs'}:
        expected['D2'] = True
    elif pattern == 'second_digit_shift':
        expected['D2'] = True
    elif pattern == 'suffix_shift':
        expected['D4'] = True
    if pattern == 'near_limit_shift':
        expected['D3'] = True
    if pattern in {'small_sample','fixed_legitimate'}:
        expected = {code: None for code in expected}
    truth = [dict(rule_id=code, cutoff_at=cutoff, scope='creator:E_CONTROL' if code in {'D3','D6'} else 'company',
        expected_signal=value, truth_unit='window_intervention_not_transaction_fraud', pattern=pattern) for code,value in expected.items()]
    return {'transactions': sorted(rows, key=lambda r: (r['posted_at'], r['transaction_id']))}, truth
