"""Monthly as-of aggregate diagnostics; never transaction fraud scores."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime

from .generate import parse

SOURCE = 'https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chisquare.html'


def bh_adjust(values):
    """Benjamini-Hochberg, independently for the tests available at a cutoff."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    adjusted, running = [1.] * len(values), 1.
    for rank in range(len(order), 0, -1):
        i = order[rank - 1]
        running = min(running, values[i] * len(order) / rank)
        adjusted[i] = min(1., running)
    return adjusted


def digits_test(amounts, kind, min_rows=300):
    positive = [int(x) for x in amounts if int(x) > 0]
    reasons = []
    if len(positive) < min_rows:
        reasons.append(f'need_at_least_{min_rows}_positive_rows')
    if len(set(positive)) < 100:
        reasons.append('fewer_than_100_distinct_amounts')
    if positive and max(positive) / min(positive) < 100:
        reasons.append('range_less_than_two_orders_of_magnitude')
    if positive and Counter(positive).most_common(1)[0][1] / len(positive) > .2:
        reasons.append('dominant_fixed_amount_over_20_percent')
    categories = list(range(1, 10)) if kind == 'first' else list(range(10)) if kind == 'second' else list(range(10, 100))
    if kind == 'first':
        probabilities = [math.log10(1 + 1 / d) for d in categories]
        observed = Counter(int(str(x)[0]) for x in positive)
    elif kind == 'second':
        positive = [x for x in positive if x >= 10]
        probabilities = [sum(math.log10(1 + 1 / (10 * d + k)) for d in range(1, 10)) for k in categories]
        observed = Counter(int(str(x)[1]) for x in positive)
    else:
        positive = [x for x in positive if x >= 10]
        probabilities = [math.log10(1 + 1 / d) for d in categories]
        observed = Counter(int(str(x)[:2]) for x in positive)
    expected = [p * len(positive) for p in probabilities]
    if not expected or min(expected) < 5:
        reasons.append('expected_cell_count_less_than_5')
    result = dict(status='not_evaluable' if reasons else 'evaluated', rows=len(positive), kind=kind,
                  skip_reasons=reasons, applicability='heuristic_screen_only_not_proof_of_benford_population')
    if reasons:
        return result
    from scipy.stats import chisquare
    counts = [observed[c] for c in categories]
    # Numerical normalisation only: all expected cells sum to the observed N.
    total = sum(expected)
    expected = [x * len(positive) / total for x in expected]
    statistic, pvalue = chisquare(counts, expected)
    result.update(statistic=float(statistic), pvalue=float(pvalue),
                  mad=sum(abs(count / len(positive) - p) for count, p in zip(counts, probabilities)) / len(categories),
                  categories=categories, observed_counts=counts, expected_counts=expected)
    return result


def monthly_diagnostics(tables, definition_policy='legacy'):
    """Only records posted strictly before each calendar-month cutoff participate.

    First/second digit tests use one positive scored financial disbursement per
    observation, excluding fixed payroll/rent and journal lines to avoid duplicates.
    Historical empirical suffix baseline is frozen before the current window.
    """
    if definition_policy not in {'legacy', 'phase4'}:
        raise ValueError('Unknown aggregate definition policy')
    phase4 = definition_policy == 'phase4'
    rows = sorted(tables['transactions'], key=lambda r: (r['posted_at'], r['transaction_id']))
    if not rows:
        return []
    companies = sorted({r['company_id'] for r in rows})
    payments = [r for r in rows if int(r['is_financial_entry']) and r['payment_channel'] in {'bank', 'cash'}
                and r['txn_type'] not in {'customer_receipt', 'payroll', 'rent'} and int(r['amount_vnd']) > 0]
    cutoffs = sorted({(parse(r['posted_at']).year + (parse(r['posted_at']).month == 12),
                       parse(r['posted_at']).month % 12 + 1) for r in rows})
    results = []
    for year, month in cutoffs:
        cutoff = datetime(year, month, 1, tzinfo=parse(rows[0]['posted_at']).tzinfo)
        prior = [r for r in payments if parse(r['posted_at']) < cutoff]
        window = [r for r in prior if (cutoff - parse(r['posted_at'])).total_seconds() <= 90 * 86400]
        period_results = []
        for cid in companies:
            company_rows = [r for r in window if r['company_id'] == cid]
            def record(code, scope, observations, kind, minimum):
                test = digits_test([r['amount_vnd'] for r in observations], kind, minimum)
                out = dict(rule_id=code, company_id=cid, cutoff_at=cutoff.isoformat(), window_days=90,
                           scope=scope, **test, action='aggregate_review_only', adds_transaction_score=False)
                period_results.append(out)
                return out
            first = record('D1', 'company', company_rows, 'first', 300)
            record('D2', 'company', company_rows, 'second', 1000)
            mad = dict(first, rule_id='D5', mad_threshold=.015)
            # MAD is descriptive, not an independent hypothesis test.
            mad.pop('pvalue', None)
            mad['signal'] = first.get('mad', 0) > .015 if first['status'] == 'evaluated' else None
            period_results.append(mad)
            by_maker = defaultdict(list)
            for r in company_rows:
                by_maker[r['creator_id']].append(r)
            for maker, observations in sorted(by_maker.items()):
                segmented = record('D6', f'creator:{maker}', observations, 'first', 300)
                segmented['segmentation'] = 'creator'
                near_test = record('D3', f'creator:{maker}', observations, 'first_two', 1000)
                if near_test['status'] == 'evaluated':
                    # Approval tiers must be homogeneous for this comparison.
                    limits = {int(r['approval_limit_vnd']) for r in observations}
                    if len(limits) != 1:
                        near_test.update(status='not_evaluable', skip_reasons=['mixed_approval_limits'])
                        near_test.pop('pvalue', None)
                    else:
                        limit = next(iter(limits))
                        leading = int(str(limit)[:2])
                        candidate_digits = [98, 99] if leading == 10 else sorted({max(10, leading - 2), max(10, leading - 1)})
                        excess = []
                        for digit in candidate_digits:
                            index = near_test['categories'].index(digit)
                            expected = near_test['expected_counts'][index]
                            actual_near = sum(.8 <= int(r['amount_vnd']) / limit < 1 and int(str(r['amount_vnd'])[:2]) == digit for r in observations)
                            count = actual_near if phase4 else near_test['observed_counts'][index]
                            if count > expected * 1.2:
                                excess.append(digit)
                        near_test.update(approval_limit_vnd=limit, excess_leading_pairs=excess,
                            definition_policy=definition_policy, actual_near_limit_rows=sum(.8 <= int(r['amount_vnd'])/limit < 1 for r in observations),
                            comparison_note='Global first-two-digit test plus conservative actual-near-amount screen; not proof of threshold evasion.')
            if phase4:
                for field in ('department', 'project_id'):
                    segments = defaultdict(list)
                    for r in company_rows:
                        if r.get(field):
                            segments[r[field]].append(r)
                    for key, observations in sorted(segments.items()):
                        segmented = record('D6', f'{field}:{key}', observations, 'first', 300)
                        segmented['segmentation'] = field
            recent = [r for r in company_rows if (cutoff - parse(r['posted_at'])).total_seconds() <= 30 * 86400]
            older = [r for r in prior if r['company_id'] == cid and 30 * 86400 < (cutoff - parse(r['posted_at'])).total_seconds() <= 120 * 86400]
            suffixes = (0, 500, 999)
            suffix = dict(rule_id='D4', company_id=cid, cutoff_at=cutoff.isoformat(), scope='company',
                          window_days=30, rows=len(recent), baseline_rows=len(older),
                          status='evaluated' if len(recent) >= 300 and len(older) >= 300 else 'not_evaluable',
                          skip_reasons=[] if len(recent) >= 300 and len(older) >= 300 else ['need_300_rows_in_each_window'],
                          action='aggregate_review_only', adds_transaction_score=False, baseline='past_empirical_not_uniform')
            if suffix['status'] == 'evaluated':
                ratios = []
                for ending in suffixes:
                    current = sum(int(r['amount_vnd']) % 1000 == ending for r in recent) / len(recent)
                    previous = sum(int(r['amount_vnd']) % 1000 == ending for r in older) / len(older)
                    ratios.append(dict(suffix=f'{ending:03}', current_rate=current, baseline_rate=previous,
                                       signal=(current > previous * 2 if previous > 0 else None) if phase4 else previous > 0 and current > previous * 2,
                                       note='zero_baseline_rate_not_evaluable' if phase4 and previous == 0 else ''))
                suffix['suffix_comparison'] = ratios
                suffix['signal'] = any(r['signal'] for r in ratios)
                if phase4 and any(r['signal'] is None for r in ratios):
                    suffix.update(status='partial', skip_reasons=['zero_rate_for_at_least_one_suffix'])
            period_results.append(suffix)
        tested = [r for r in period_results if r['status'] == 'evaluated' and 'pvalue' in r]
        for item, adjusted in zip(tested, bh_adjust([r['pvalue'] for r in tested])):
            item['pvalue_bh'] = adjusted
            corrected = min(1., adjusted * sum(1/i for i in range(1,len(tested)+1))) if phase4 else adjusted
            item.update(pvalue_corrected=corrected, correction_method='BY' if phase4 else 'BH')
            item['signal'] = corrected < .05 and (bool(item.get('excess_leading_pairs')) if item['rule_id'] == 'D3' else True)
        results.extend(period_results)
    return results
