from .contracts import Aggregate, UnitCounts, UnitIssue
from .context import key_for
from .outcomes import validate, token


def aggregate(plan, outcomes, package):
    entries = plan.entries
    in_scope = [e for e in entries if e.applicability == 'MATCH' and e.capability == 'SUPPORTED' and e.eligibility != 'NOT_APPLICABLE']
    excluded = [e for e in entries if e.eligibility == 'OUT_OF_SCOPE_FOR_SOURCE']
    na = [e for e in entries if e.eligibility == 'NOT_APPLICABLE']
    unresolved = [e for e in entries if e.eligibility != 'NOT_APPLICABLE' and (e.applicability == 'UNKNOWN' or e.capability == 'UNKNOWN')]
    discovery = [e for e in entries if e.unit.discovery != 'COMPLETE']
    contract_errors = []
    try:
        if not entries:
            raise ValueError('EMPTY_RULESET_CONFIGURATION')
        indexed = validate(plan, outcomes, package)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        indexed = {}
        contract_errors = [str(exc)]
    succeeded = {k: v for k, v in indexed.items() if v.execution_status == 'SUCCEEDED'}
    blocked = [e for e in in_scope if not e.rule_version or token(key_for(plan, e)) not in succeeded]
    operational = []
    for outcome in indexed.values():
        if outcome.execution_status == 'ERROR':
            operational.append(UnitIssue(key=outcome.key, rule_id=outcome.key.rule_id, unit_id=outcome.key.unit_id,
                code=outcome.error.code, next_action=outcome.error.next_action))
    for e in entries:
        if e.eligibility == 'NOT_EVALUATED_PLANNING_ERROR':
            operational.append(UnitIssue(rule_id=e.rule_id, unit_id=e.unit.unit_id, code='PLANNING_ERROR', next_action='OPERATOR'))
        if e.eligibility == 'ELIGIBLE' and token(key_for(plan, e)) not in indexed:
            operational.append(UnitIssue(key=key_for(plan, e), rule_id=e.rule_id, unit_id=e.unit.unit_id,
                code='MISSING_TERMINAL_OUTCOME', next_action='RETRY'))
    incomplete = bool(blocked or unresolved or discovery or operational or contract_errors)
    coverage = 'NONE' if not succeeded else 'PARTIAL' if incomplete else 'FULL'
    review_required = any(e.review_required for e in entries) or any(o.result == 'REVIEW' for o in succeeded.values())
    results = [o.result for o in succeeded.values()]
    reasons = []
    if contract_errors:
        verdict = None
        reasons.append('OUTCOME_CONTRACT_ERROR')
    elif 'FAIL' in results:
        verdict = 'FAIL'
    elif review_required:
        verdict = 'REVIEW'
    elif incomplete or not in_scope:
        verdict = 'NO_VERDICT'
    else:
        verdict = 'PASS_WITHIN_SCOPE' if excluded else 'PASS'
    if not in_scope:
        reasons.append('NO_APPLICABLE_RULE' if len(na) == len(entries) and entries else 'NO_IN_SCOPE_UNIT')
    if blocked: reasons.append('BLOCKED_IN_SCOPE_UNITS')
    if unresolved: reasons.append('UNRESOLVED_SCOPE_OR_APPLICABILITY')
    if discovery: reasons.append('INCOMPLETE_UNIT_DISCOVERY')
    if operational: reasons.append('OPERATIONAL_ERRORS')
    if verdict in ('PASS', 'PASS_WITHIN_SCOPE'): reasons.append('ALL_IN_SCOPE_UNITS_PASS')
    if excluded: reasons.append('CONFIRMED_SCOPE_EXCLUSIONS')
    def issue(e):
        return UnitIssue(key=key_for(plan, e) if e.rule_version else None, rule_id=e.rule_id,
            unit_id=e.unit.unit_id, code=e.reasons[0] if e.reasons else 'PLANNING_BLOCKER', next_action=e.next_action)
    counts = UnitCounts(selected=len(entries), not_applicable=len(na), in_scope=len(in_scope),
        eligible=sum(e.eligibility == 'ELIGIBLE' for e in entries), evaluated=len(succeeded), blocked=len(blocked),
        out_of_scope=len(excluded), unknown_applicability=sum(e.applicability == 'UNKNOWN' for e in unresolved),
        unknown_capability=sum(e.capability == 'UNKNOWN' for e in unresolved), unresolved=len(unresolved),
        discovery_blockers=len(discovery), passed=results.count('PASS'), failed=results.count('FAIL'),
        review=results.count('REVIEW'), errors=sum(o.execution_status == 'ERROR' for o in indexed.values()))
    return Aggregate(processing_status='ERROR' if contract_errors else 'PARTIAL_ERROR' if operational else 'SUCCESS',
        coverage=coverage, verdict=verdict, review_required=review_required, counts=counts,
        distinct_rules_selected=len({e.rule_id for e in entries}),
        distinct_rules_evaluated=len({o.key.rule_id for o in succeeded.values()}),
        scope_exclusions=tuple(map(issue, excluded)), blocked_units=tuple(map(issue, blocked)),
        operational_errors=tuple(operational), unresolved=tuple(map(issue, unresolved)),
        discovery_blockers=tuple(map(issue, discovery)), contract_errors=tuple(contract_errors), reasons=tuple(reasons))
