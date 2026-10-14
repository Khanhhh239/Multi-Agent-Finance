"""Independent execution, pinned planning replay, finite attempts and immutable results."""
from pathlib import Path
from datetime import date
from ..canonicalization.derive import sha
from ..domain.base import utcnow
from ..planning.repository import replay
from ..planning.contracts import RulePlan
from .contracts import RuleOutcome, ExecutionError, ComplianceResult, ModelPackage, ExecutionPolicy
from .context import build, key_for
from .models import validate_model
from .zen_adapter import evaluate, EngineFailure
from .outcomes import terminal_attempts
from .aggregator import aggregate
from .trace import parse_response
from .outcomes import validate


def implementation_sha():
    root = Path(__file__).resolve().parent
    return sha({p.name: p.read_bytes().hex() for p in sorted(root.glob('*.py'))})


def run_id(plan, package, policy, payment):
    return 'execution-' + sha([plan.model_dump(mode='json'), package.model_dump(mode='json'),
        policy.model_dump(mode='json'), payment.model_dump(mode='json') if payment else None, implementation_sha()])[:32]


def execute(plan, inputs, package, policy=None, payment=None, *, runner=None, created_at=None, on_attempt=None, initial_attempts=()):
    plan = RulePlan.model_validate_json(plan.model_dump_json())
    package = ModelPackage.model_validate_json(package.model_dump_json())
    policy = policy or ExecutionPolicy()
    # No fields/facts from a newer record, metadata or context may reach the engine.
    replay(inputs, plan)
    if len(plan.entries) > policy.max_units:
        raise ValueError('Execution unit budget exceeded')
    package_hash = sha(package.model_dump(mode='json'))
    execution_id = run_id(plan, package, policy, payment)
    stamp = created_at or utcnow()
    attempts = list(initial_attempts)
    for attempt in attempts:
        if attempt.execution_id != execution_id:
            raise ValueError('Resume attempt belongs to a different run')
        validate(plan,(attempt,),package)
        if attempt.attempt_number > policy.max_attempts:
            raise ValueError('Resume attempt exceeds configured budget')
        if attempt.context is not None:
            entry=next(e for e in plan.entries if e.eligibility=='ELIGIBLE' and key_for(plan,e)==attempt.key)
            model=next(m for m in package.models if (m.rule_id,m.rule_version,m.unit_type)==(entry.rule_id,entry.rule_version,entry.unit.unit_type))
            if build(plan,entry,model,inputs,payment)!=attempt.context:
                raise ValueError('Resume facts differ from pinned inputs')
    terminal_attempts(attempts)
    runner = runner or evaluate
    for entry in sorted(plan.entries, key=lambda e: (e.rule_id, e.rule_version or '', e.unit.unit_type, e.unit.unit_id)):
        if entry.eligibility != 'ELIGIBLE':
            continue
        key = key_for(plan, entry)
        previous = sorted((a for a in attempts if a.key == key),key=lambda a:a.attempt_number)
        if previous and (previous[-1].execution_status == 'SUCCEEDED' or not previous[-1].error.retryable):
            continue
        for number in range(len(previous) + 1, policy.max_attempts + 1):
            model = None
            context = None
            error = None
            result = trace = None
            try:
                found = [m for m in package.models if (m.rule_id, m.rule_version, m.unit_type) == (entry.rule_id, entry.rule_version, entry.unit.unit_type)]
                if len(found) != 1:
                    raise ValueError('Pinned model unavailable')
                model = validate_model(found[0])
                if model.publication != 'APPROVED_TECHNICAL' or model.legal_basis != entry.legal_basis:
                    raise ValueError('Model/legal basis not approved or mismatched')
                family = next(f for f in inputs['ruleset']['families'] if f['rule_id'] == entry.rule_id)
                rule = next(r for r in family['versions'] if r['version'] == entry.rule_version)
                policy_date = inputs['record']['invoice']['issue_date']['value'] if rule['date_field'] == 'invoice.issue_date' else next(v['field']['value'] for v in inputs['context']['values'] if v['path'] == rule['date_field'])
                if (rule['family'] != model.family or model.effective_from > date.fromisoformat(policy_date)
                    or date.fromisoformat(policy_date) >= model.effective_to):
                    raise ValueError('Model date/family policy mismatch')
                context = build(plan, entry, model, inputs, payment)
                result, trace = runner(model, context, policy)
                observed_result,observed_trace=parse_response(trace.raw_response_json,model,context)
                if result != observed_result or trace != observed_trace:
                    raise EngineFailure('ENGINE_RESPONSE_CONTRACT_ERROR')
            except EngineFailure as exc:
                error = ExecutionError(code=exc.code, message='ZEN execution could not complete safely.', retryable=exc.retryable,
                    next_action='RETRY' if exc.retryable and number < policy.max_attempts else 'OPERATOR')
            except Exception:
                error = ExecutionError(code='EXECUTION_INPUT_OR_MODEL_ERROR', message='Pinned model, context or runtime violates execution requirements.')
            outcome = RuleOutcome(config_version='zen-execution-v1', creator='rule-executor', stage='rules', created_at=stamp,
                key=key, execution_id=execution_id, tenant_id=plan.tenant_id, taxpayer_id=plan.taxpayer_id,
                attempt_id='attempt-' + sha([execution_id, key.model_dump(mode='json'), number])[:32], attempt_number=number,
                context=context, context_sha256=sha(context.model_dump(mode='json')) if context else None,
                package_sha256=package_hash, model_sha256=model.jdm_sha256 if model else None,
                execution_status='ERROR' if error else 'SUCCEEDED', result=None if error else result,
                error=error, trace=None if error else trace)
            attempts.append(outcome)
            if on_attempt:
                on_attempt(outcome)
            if error is None or not error.retryable:
                break
    outcomes = terminal_attempts(attempts)
    summary = aggregate(plan, outcomes, package)
    return ComplianceResult(config_version='zen-execution-v1', creator='rule-executor', stage='rules', created_at=stamp,
        execution_id=execution_id, evaluation_id=plan.evaluation_id, tenant_id=plan.tenant_id, taxpayer_id=plan.taxpayer_id,
        record_id=plan.record_id, record_revision=plan.record_revision, plan_sha256=sha(plan.model_dump(mode='json')),
        package_sha256=package_hash, policy_sha256=sha(policy.model_dump(mode='json')), implementation_sha256=implementation_sha(),
        outcomes=outcomes, attempts=tuple(attempts), aggregate=summary)
