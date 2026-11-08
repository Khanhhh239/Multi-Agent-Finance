from typing import Literal
from datetime import date
import json
from pydantic import Field, StrictBool, StrictStr, model_validator
from ..domain.base import Contract, Stamped, Identifier
from ..domain.envelope import Sha256
from ..domain.field import FieldObject
from ..planning.contracts import LegalBasis
from ..quality.contracts import FieldQuality


class EvaluationKey(Contract):
    evaluation_id: Identifier
    record_revision: int = Field(ge=1)
    rule_id: Identifier
    rule_version: Identifier
    unit_type: Literal['RECORD', 'ITEM', 'VAT_GROUP']
    unit_id: Identifier


class Binding(Contract):
    condition_id: Identifier
    operation: Literal['NONEMPTY', 'EQUALS', 'OBSERVATION_PRESENT', 'PAYMENT_NON_CASH']
    path: str
    value_type: Literal['TEXT', 'DECIMAL', 'BOOL'] = 'TEXT'
    expected: StrictStr | StrictBool | None = None

    @model_validator(mode='after')
    def valid(self):
        if self.operation == 'EQUALS':
            if self.value_type == 'DECIMAL':
                from .money_boundary import checked
                checked(self.expected)
            elif self.value_type == 'BOOL' and type(self.expected) is not bool:
                raise ValueError('Expected strict boolean')
            elif self.value_type == 'TEXT' and not isinstance(self.expected, str):
                raise ValueError('Expected text')
        if self.operation == 'PAYMENT_NON_CASH' and self.path != 'payment.non_cash_evidence':
            raise ValueError('Payment proof binding path required')
        return self


class RuleModel(Contract):
    model_id: Identifier
    version: Identifier
    rule_id: Identifier
    rule_version: Identifier
    family: Literal['INVOICE_CONTENT', 'VAT_RATE', 'PAYMENT_EVIDENCE']
    unit_type: Literal['RECORD', 'ITEM', 'VAT_GROUP']
    effective_from: date
    effective_to: date
    publication: Literal['DRAFT', 'APPROVED_TECHNICAL'] = 'DRAFT'
    review_reference: str | None = None
    legal_basis: tuple[LegalBasis, ...] = Field(min_length=1)
    bindings: tuple[Binding, ...] = Field(min_length=1)
    review_condition_id: Identifier | None = None
    jdm_json: str
    jdm_sha256: Sha256
    no_hit_policy: Literal['ERROR'] = 'ERROR'

    @model_validator(mode='after')
    def valid(self):
        from ..persistence.repository import digest
        if digest(self.jdm_json.encode()) != self.jdm_sha256:
            raise ValueError('Model hash mismatch')
        if self.effective_to <= self.effective_from:
            raise ValueError('Exclusive model interval required')
        if self.publication == 'APPROVED_TECHNICAL' and not self.review_reference:
            raise ValueError('Explicit model review required')
        if len({b.condition_id for b in self.bindings}) != len(self.bindings):
            raise ValueError('Duplicate condition id')
        json.loads(self.jdm_json)
        return self


class ModelPackage(Contract):
    package_id: Identifier
    version: Identifier
    engine_version: Literal['0.53.0'] = '0.53.0'
    models: tuple[RuleModel, ...]

    @model_validator(mode='after')
    def unique(self):
        keys = [(m.rule_id, m.rule_version, m.unit_type) for m in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError('Ambiguous model selection')
        return self


class ExecutionPolicy(Contract):
    version: Identifier = 'zen-execution-v1'
    timeout_seconds: float = Field(default=10, gt=0, le=60)
    memory_mb: int = Field(default=256, ge=64, le=1024)
    max_attempts: int = Field(default=2, ge=1, le=3)
    max_units: int = Field(default=1000, ge=1, le=10000)
    max_response_bytes: int = Field(default=2_000_000, ge=1024, le=16_000_000)


class PaymentProof(Contract):
    """Trusted backend sidecar, never an HTTP caller assertion or invoice TM/CK label."""
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    record_revision: int = Field(ge=1)
    record_sha256: Sha256
    field: FieldObject[StrictBool]
    quality: FieldQuality
    verification_reference: str = Field(min_length=1)
    policy_version: Literal['verified-payment-proof-v1'] = 'verified-payment-proof-v1'


class ConditionTrace(Contract):
    condition_id: Identifier
    value: StrictBool
    origin: Literal['ADAPTER'] = 'ADAPTER'
    policy_version: Literal['decimal-facts-v1'] = 'decimal-facts-v1'
    field_paths: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_json: str
    expected_json: str


class EngineContext(Contract):
    planning_eligibility: Literal['ELIGIBLE']
    key: EvaluationKey
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_sha256: Sha256
    plan_sha256: Sha256
    model_sha256: Sha256
    conditions: tuple[ConditionTrace, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def unique(self):
        if len({c.condition_id for c in self.conditions}) != len(self.conditions):
            raise ValueError('Duplicate context condition')
        return self

    def facts(self):
        return {c.condition_id: c.value for c in self.conditions}


class ExecutionError(Contract):
    code: Identifier
    message: str
    retryable: StrictBool = False
    next_action: Literal['RETRY', 'OPERATOR', 'COLLECT_OTHER_SOURCE'] = 'OPERATOR'


class ExecutionTrace(Contract):
    raw_response_json: str
    raw_sha256: Sha256
    matched_row_id: Identifier
    row_origin: Literal['ENGINE'] = 'ENGINE'
    conditions: tuple[ConditionTrace, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def valid(self):
        from ..persistence.repository import digest
        if digest(self.raw_response_json.encode()) != self.raw_sha256:
            raise ValueError('Raw trace hash mismatch')
        json.loads(self.raw_response_json)
        return self


class RuleOutcome(Stamped):
    key: EvaluationKey
    execution_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    attempt_id: Identifier
    attempt_number: int = Field(ge=1, le=3)
    context: EngineContext | None = None
    context_sha256: Sha256 | None = None
    package_sha256: Sha256
    model_sha256: Sha256 | None = None
    engine_version: Literal['0.53.0'] = '0.53.0'
    execution_status: Literal['SUCCEEDED', 'ERROR']
    result: Literal['PASS', 'FAIL', 'REVIEW'] | None = None
    error: ExecutionError | None = None
    trace: ExecutionTrace | None = None

    @model_validator(mode='after')
    def valid(self):
        from ..canonicalization.derive import sha
        if self.execution_status == 'SUCCEEDED':
            if self.result is None or self.error is not None or self.trace is None or self.context is None or self.model_sha256 is None:
                raise ValueError('Successful outcome requires result, context, model and trace only')
        elif self.result is not None or self.error is None or self.trace is not None:
            raise ValueError('ERROR has null result and explicit error, no successful trace')
        if self.context is not None:
            if self.context.key != self.key or (self.context.tenant_id, self.context.taxpayer_id) != (self.tenant_id, self.taxpayer_id):
                raise ValueError('Context key/scope mismatch')
            if self.context_sha256 != sha(self.context.model_dump(mode='json')) or self.context.model_sha256 != self.model_sha256:
                raise ValueError('Context/model hash mismatch')
        elif self.context_sha256 is not None:
            raise ValueError('Orphan context hash')
        if self.trace is not None and self.trace.conditions != self.context.conditions:
            raise ValueError('Normalized trace differs from evaluated conditions')
        return self


class UnitCounts(Contract):
    selected: int = Field(ge=0)
    not_applicable: int = Field(ge=0)
    in_scope: int = Field(ge=0)
    eligible: int = Field(ge=0)
    evaluated: int = Field(ge=0)
    blocked: int = Field(ge=0)
    out_of_scope: int = Field(ge=0)
    unknown_applicability: int = Field(ge=0)
    unknown_capability: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    discovery_blockers: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    review: int = Field(ge=0)
    errors: int = Field(ge=0)

    @model_validator(mode='after')
    def invariants(self):
        if self.in_scope != self.evaluated + self.blocked:
            raise ValueError('Coverage partition mismatch')
        if self.evaluated != self.passed + self.failed + self.review or self.evaluated > self.eligible:
            raise ValueError('Successful outcome counters mismatch')
        return self


class UnitIssue(Contract):
    key: EvaluationKey | None = None
    rule_id: Identifier
    unit_id: Identifier
    code: Identifier
    next_action: str


class Aggregate(Contract):
    processing_status: Literal['SUCCESS', 'PARTIAL_ERROR', 'ERROR']
    coverage: Literal['FULL', 'PARTIAL', 'NONE']
    verdict: Literal['PASS', 'PASS_WITHIN_SCOPE', 'FAIL', 'REVIEW', 'NO_VERDICT'] | None
    review_required: StrictBool
    counts: UnitCounts
    distinct_rules_selected: int = Field(ge=0)
    distinct_rules_evaluated: int = Field(ge=0)
    scope_exclusions: tuple[UnitIssue, ...] = ()
    blocked_units: tuple[UnitIssue, ...] = ()
    operational_errors: tuple[UnitIssue, ...] = ()
    unresolved: tuple[UnitIssue, ...] = ()
    discovery_blockers: tuple[UnitIssue, ...] = ()
    contract_errors: tuple[str, ...] = ()
    reasons: tuple[str, ...]

    @model_validator(mode='after')
    def valid(self):
        if self.processing_status == 'ERROR' and self.verdict is not None:
            raise ValueError('Fatal processing error cannot publish a verdict')
        if self.verdict == 'REVIEW' and not self.review_required:
            raise ValueError('REVIEW requires review flag')
        if self.verdict in ('PASS', 'PASS_WITHIN_SCOPE') and (self.coverage != 'FULL' or self.counts.blocked or self.unresolved or self.operational_errors or self.discovery_blockers or self.contract_errors or not self.counts.evaluated):
            raise ValueError('PASS cannot contain unresolved blockers')
        return self


class ComplianceResult(Stamped):
    execution_id: Identifier
    evaluation_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    record_revision: int = Field(ge=1)
    plan_sha256: Sha256
    package_sha256: Sha256
    policy_sha256: Sha256
    implementation_sha256: Sha256
    technical_only: Literal[True] = True
    outcomes: tuple[RuleOutcome, ...]
    attempts: tuple[RuleOutcome, ...]
    aggregate: Aggregate

    @model_validator(mode='after')
    def scope(self):
        if any(a.execution_id != self.execution_id or a.key.evaluation_id != self.evaluation_id
               or a.key.record_revision != self.record_revision
               or (a.tenant_id,a.taxpayer_id) != (self.tenant_id,self.taxpayer_id)
               or a.package_sha256 != self.package_sha256 for a in self.attempts + self.outcomes):
            raise ValueError('Execution result contains foreign scope/revision/package')
        return self
