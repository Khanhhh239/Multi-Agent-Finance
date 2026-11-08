"""Verify exact stored bytes separately from deterministic decision replay."""
from ..canonicalization.derive import sha
from ..planning.repository import replay as replay_plan
from .context import build, key_for
from .executor import implementation_sha, run_id
from .outcomes import terminal_attempts, validate
from .aggregator import aggregate
from .contracts import ComplianceResult


def verify(result, plan, inputs, package, policy, payment=None):
    result = ComplianceResult.model_validate_json(result.model_dump_json())
    replay_plan(inputs, plan)
    if (result.execution_id != run_id(plan, package, policy, payment)
        or result.implementation_sha256 != implementation_sha()
        or result.policy_sha256 != sha(policy.model_dump(mode='json'))
        or result.plan_sha256 != sha(plan.model_dump(mode='json'))
        or result.package_sha256 != sha(package.model_dump(mode='json'))
        or (result.tenant_id,result.taxpayer_id,result.record_id,result.record_revision,result.evaluation_id) != (
            plan.tenant_id,plan.taxpayer_id,plan.record_id,plan.record_revision,plan.evaluation_id)):
        raise ValueError('Replay version, hash or scope mismatch')
    for outcome in result.attempts:
        validate(plan, (outcome,), package)
        if outcome.execution_id != result.execution_id or outcome.attempt_number > policy.max_attempts:
            raise ValueError('Attempt run/budget mismatch')
        if outcome.context is not None:
            entry = next(e for e in plan.entries if e.eligibility == 'ELIGIBLE' and key_for(plan,e) == outcome.key)
            model = next(m for m in package.models if (m.rule_id,m.rule_version,m.unit_type) == (entry.rule_id,entry.rule_version,entry.unit.unit_type))
            if build(plan,entry,model,inputs,payment) != outcome.context:
                raise ValueError('Facts differ from pinned source evidence')
    if terminal_attempts(result.attempts) != result.outcomes or aggregate(plan,result.outcomes,package) != result.aggregate:
        raise ValueError('Terminal selection or aggregate replay differs')
    return result
