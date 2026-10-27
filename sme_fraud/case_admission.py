"""Human-review admission is distinct from numeric risk and hard triggers."""
from .cash_limit_priority import POLICY, handling_priority
SPLIT_PATTERN_POLICY = 'split_patterns_v1'
SPLIT_REVIEW_RULES = frozenset({'A2', 'A4'})


def admission(hits, score, hard, config):
    """Use already evaluated, unsuppressed predicates; never infer from labels.

    A2/A4 identify multi-payment patterns with their own count, window, identity
    and exception checks. They require review even when correlated-family
    scoring leaves them below the ordinary numeric threshold.
    """
    enabled = (config.get('split_pattern_policy') == SPLIT_PATTERN_POLICY
               and config.get('noise_policy') == 'phase2')
    rules = sorted({hit['rule_id'] for hit in hits
                    if enabled and hit['rule_id'] in SPLIT_REVIEW_RULES
                    and hit['points'] > 0 and not hit.get('suppressed_reason')
                    and hit.get('status', 'evaluated') == 'evaluated'
                    and hit.get('signal', True) is True
                    and hit.get('evidence', {}).get('evidence_status') != 'information_gap'})
    basis = ('hard_trigger' if hard else 'score_threshold' if score >= config.get('operational_score', 7)
             else 'split_pattern' if rules else '')
    priority = ('cao_nhat' if hard else 'cao' if score >= 14 else 'trung_binh' if basis else 'thap')
    priority, detail = handling_priority(hits, score, hard, config, priority, bool(rules))
    if detail and not basis:
        basis = 'verified_internal_breach'
    return dict(operational_alert=int(bool(basis)), priority=priority,
                admission_basis=basis, review_rule_ids='|'.join(rules),
                **(detail or dict(handling_priority_policy=config.get('cash_limit_priority_policy', POLICY),
                                 independent_rule_score=score, priority_basis='existing_rule_priority')))
