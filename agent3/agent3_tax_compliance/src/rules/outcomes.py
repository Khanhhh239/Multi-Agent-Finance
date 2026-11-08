"""Reject invalid terminal outcomes as a whole, never silently filter them."""
from ..canonicalization.derive import sha
from .contracts import RuleOutcome
from .context import key_for
from .trace import parse_response


def token(key):
    return (key.evaluation_id, key.record_revision, key.rule_id, key.rule_version, key.unit_type, key.unit_id)


def validate(plan, outcomes, package):
    from .contracts import ModelPackage
    package=ModelPackage.model_validate_json(package.model_dump_json())
    eligible = {token(key_for(plan, e)): e for e in plan.entries if e.eligibility == 'ELIGIBLE'}
    models = {(m.rule_id, m.rule_version, m.unit_type): m for m in package.models}
    package_hash = sha(package.model_dump(mode='json'))
    indexed = {}
    execution_ids = set()
    for raw in outcomes:
        outcome = RuleOutcome.model_validate_json(raw.model_dump_json())
        key = token(outcome.key)
        execution_ids.add(outcome.execution_id)
        if key not in eligible or key in indexed:
            raise ValueError('Duplicate, stale, unexpected or non-eligible outcome')
        if (outcome.tenant_id, outcome.taxpayer_id) != (plan.tenant_id, plan.taxpayer_id):
            raise ValueError('Outcome tenant scope differs from plan')
        if outcome.package_sha256 != package_hash:
            raise ValueError('Outcome package version/hash mismatch')
        model = models.get((outcome.key.rule_id, outcome.key.rule_version, outcome.key.unit_type))
        if model is not None and outcome.model_sha256 not in (model.jdm_sha256, None):
            raise ValueError('Outcome model hash differs from package')
        if outcome.context is not None and (outcome.context.plan_sha256 != sha(plan.model_dump(mode='json')) or outcome.context.record_sha256 != plan.record_sha256):
            raise ValueError('Context bound to stale plan/record')
        if outcome.execution_status == 'SUCCEEDED':
            if model is None or model.publication != 'APPROVED_TECHNICAL' or model.legal_basis != eligible[key].legal_basis:
                raise ValueError('Successful outcome lacks approved pinned model/legal basis')
            result, trace = parse_response(outcome.trace.raw_response_json, model, outcome.context)
            if result != outcome.result or trace != outcome.trace:
                raise ValueError('Successful outcome differs from raw trace/model')
        indexed[key] = outcome
    if len(execution_ids) > 1:
        raise ValueError('Outcomes mixed across execution runs')
    return indexed


def terminal_attempts(attempts):
    groups = {}
    ids = set()
    for attempt in attempts:
        if attempt.attempt_id in ids:
            raise ValueError('Duplicate attempt id')
        ids.add(attempt.attempt_id)
        groups.setdefault(token(attempt.key), []).append(attempt)
    terminal = []
    for group in groups.values():
        group.sort(key=lambda a: a.attempt_number)
        if [a.attempt_number for a in group] != list(range(1, len(group) + 1)):
            raise ValueError('Attempt sequence must be contiguous')
        if len({a.execution_id for a in group}) != 1:
            raise ValueError('Attempt run mismatch')
        if any(a.execution_status != 'ERROR' or not a.error.retryable for a in group[:-1]):
            raise ValueError('Retry after terminal/nonretryable outcome')
        terminal.append(group[-1])
    return tuple(sorted(terminal, key=lambda a: token(a.key)))
