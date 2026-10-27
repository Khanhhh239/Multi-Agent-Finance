"""Versioned RR09 handling priority; the verified breach and its points remain."""
POLICY = 'rr09-v1'
LEGACY_POLICY = 'legacy_high_v1'
PRIORITIES = {'thap': 0, 'trung_binh': 1, 'cao': 2, 'cao_nhat': 3}
SLA_HOURS = {'cao_nhat': 24, 'cao': 48, 'trung_binh': 168, 'thap': 720}


def limit_priority(amount, limit):
    """Integer VND comparisons, including exact ratio boundaries and zero limits."""
    if type(amount) is not int or type(limit) is not int or limit < 0 or amount <= limit:
        raise ValueError('RR09 needs integer VND and an exceeded nonnegative limit')
    excess = amount-limit
    priority = ('cao' if limit == 0 or excess >= 1_000_000 or 10*excess >= limit else
                'thap' if excess < 100_000 and 100*excess < limit else 'trung_binh')
    return dict(version=POLICY, limit_vnd=limit, excess_vnd=excess,
                excess_ratio=None if limit == 0 else excess/limit,
                ratio_numerator_vnd=excess, ratio_denominator_vnd=limit,
                materiality_basis='per_payment_excess_vnd_and_limit_ratio',
                high_excess_vnd_inclusive=1_000_000, high_ratio_inclusive='1/10',
                low_excess_vnd_exclusive=100_000, low_ratio_exclusive='1/100',
                tier_priority=priority, score_policy='retain_verified_breach_14_points')


def family_score(hits):
    families = {}
    for hit in hits:
        group = 'master_duplicate' if hit['rule_id'] in {'B5', 'E4', 'E3'} else hit['rule_id'][0]
        families[group] = max(families.get(group, 0), hit['points'])
    return sum(families.values())


def handling_priority(hits, score, hard, config, default, split_review=False):
    """Exclude P2 from the independent score; retain recurrence and hard rules."""
    if config.get('cash_limit_priority_policy', POLICY) != POLICY:
        return default, None
    breaches = [h for h in hits if h['rule_id'] == 'P2' and h['points'] > 0
                and not h.get('suppressed_reason')
                and h.get('evidence', {}).get('limit_priority', {}).get('version') == POLICY]
    if not breaches:
        return default, None
    independent = family_score([h for h in hits if h['rule_id'] != 'P2'])
    independent += max(0, score-family_score(hits))
    other_priority = ('cao_nhat' if hard else 'cao' if independent >= 14 else
                      'trung_binh' if independent >= config.get('operational_score', 7) or split_review else 'thap')
    final = max([other_priority, *(h['evidence']['review_priority'] for h in breaches)], key=PRIORITIES.get)
    return final, dict(handling_priority_policy=POLICY, independent_rule_score=independent,
                       priority_basis='maximum_of_rr09_tier_vat_floor_and_independent_signals')
