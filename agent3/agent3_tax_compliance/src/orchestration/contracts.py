from typing import Literal
from pydantic import Field, StrictInt, model_validator
from ..domain.base import Contract, Stamped, Identifier
from ..domain.envelope import Sha256
from ..domain.evidence import Evidence
from ..rules.contracts import Aggregate, EvaluationKey, ExecutionError, ExecutionTrace
from ..planning.contracts import VersionPin


class EvaluationCommand(Contract):
    expected_record_revision: StrictInt = Field(ge=1)
    version_policy: Literal['CURRENT_VERSIONS'] = 'CURRENT_VERSIONS'
    reason: str = Field(default='User requested scoped technical evaluation',min_length=1,max_length=2000)


class LegalCitation(Contract):
    document_id: Identifier
    locator: str
    official_url: str
    sha256: Sha256 | None = None
    locator_reviewed: bool


class SourceLink(Contract):
    field_path: str
    evidence: tuple[Evidence,...] = ()
    reference: str


class RuleResultView(Contract):
    evaluation_id: Identifier
    result_id: Identifier
    planning_evaluation_id: Identifier
    rule_id: Identifier
    rule_version: Identifier | None
    unit_type: Literal['RECORD','ITEM','VAT_GROUP']
    unit_id: Identifier
    item_refs: tuple[Identifier,...]
    eligibility: str
    applicability: str
    capability: str
    review_required: bool
    execution_status: Literal['NOT_RUN','SUCCEEDED','ERROR']
    result: Literal['PASS','FAIL','REVIEW'] | None = None
    error: ExecutionError | None = None
    attempt_id: Identifier | None = None
    outcome_key: EvaluationKey | None = None
    reasons: tuple[str,...]
    next_action: str
    explanation: str
    citations: tuple[LegalCitation,...] = ()
    sources: tuple[SourceLink,...] = ()
    trace: ExecutionTrace | None = None


class Explanation(Contract):
    template_version: Identifier
    title: str
    text: str
    scope: str
    verdict: Literal['PASS','PASS_WITHIN_SCOPE','FAIL','REVIEW','NO_VERDICT'] | None
    notices: tuple[str,...]
    next_actions: tuple[str,...]


class EvaluationReport(Stamped):
    evaluation_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    record_revision: int = Field(ge=1)
    planning_evaluation_id: Identifier
    execution_id: Identifier
    extraction_artifact_id: Identifier
    assessment_id: Identifier
    record_sha256: Sha256
    source_sha256: Sha256
    package_sha256: Sha256
    template_sha256: Sha256
    implementation_sha256: Sha256
    pins: tuple[VersionPin,...]
    aggregate: Aggregate
    explanation: Explanation
    technical_only: Literal[True] = True
    rule_results_total: int = Field(ge=0)
    attempts_total: int = Field(ge=0)
    stage_seconds: dict[str,float]

    @model_validator(mode='after')
    def consistent(self):
        import math
        if self.explanation.verdict!=self.aggregate.verdict:raise ValueError('Template cannot change verdict')
        if any(not math.isfinite(v) or v<0 for v in self.stage_seconds.values()):raise ValueError('Invalid stage timing')
        return self


class EvaluationArtifact(Contract):
    report: EvaluationReport
    rule_results: tuple[RuleResultView,...]

    @model_validator(mode='after')
    def bound(self):
        if self.report.rule_results_total!=len(self.rule_results):raise ValueError('Rule result count mismatch')
        if len({r.result_id for r in self.rule_results})!=len(self.rule_results):raise ValueError('Duplicate rule result id')
        if any(r.evaluation_id!=self.report.evaluation_id or r.planning_evaluation_id!=self.report.planning_evaluation_id for r in self.rule_results):
            raise ValueError('Rule view evaluation scope mismatch')
        return self


class EvaluationState(Contract):
    evaluation_id: Identifier
    record_id: Identifier
    record_revision: int
    status: Literal['RUNNING','FAILED','COMPLETED']
    stage: str
    latest_record_revision: int
    is_current_revision: bool
    report: EvaluationReport | None = None
    error: ExecutionError | None = None
