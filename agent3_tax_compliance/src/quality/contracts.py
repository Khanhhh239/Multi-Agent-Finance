from typing import Literal,Annotated
from pydantic import Field,model_validator
from ..domain.base import Contract,Stamped,Identifier
from ..domain.envelope import Sha256
from ..domain.evidence import Evidence,Unit

Count=Annotated[int,Field(strict=True,ge=0)]

class QualityProfile(Contract):
    version: Identifier
    record_type: Literal['INVOICE','RECEIPT']
    expected_fields: tuple[str,...]
    critical_fields: tuple[str,...]
    item_fields: tuple[str,...] = ()

    @model_validator(mode='after')
    def fields(self):
        if len(set(self.expected_fields))!=len(self.expected_fields): raise ValueError('duplicate expectation')
        if not set(self.critical_fields)<=set(self.expected_fields): raise ValueError('critical fields must be expected')
        return self

class QualityPolicy(Contract):
    version: Identifier
    auto_accept_enabled: Literal[False] = False
    threshold_status: Literal['TBD_INSUFFICIENT_DATA'] = 'TBD_INSUFFICIENT_DATA'
    threshold_owner: str
    thresholds: dict[str,Unit|None]
    fidelity_policies: tuple[Identifier,...] = ()
    profiles: tuple[QualityProfile,...]

    @model_validator(mode='after')
    def versions(self):
        if len({p.record_type for p in self.profiles})!=len(self.profiles): raise ValueError('duplicate profile type')
        if any(v is not None for v in self.thresholds.values()): raise ValueError('TBD thresholds cannot enable automatic acceptance')
        return self

class CalibrationScope(Contract):
    field_family: str
    document_family: Identifier
    engine_id: Identifier
    engine_config_version: Identifier
    engine_runtime_sha256: Sha256
    preprocess_version: Identifier
    extractor_sha256: Sha256
    score_kind: Literal['RECOGNITION','EXTRACTOR','DETECTION','UNAVAILABLE']

class ScoreSample(Contract):
    sample_id: Identifier
    logical_document_id: Identifier
    group_id: Identifier
    source_sha256: Sha256
    split: Literal['FIT','HOLDOUT','TEST','DEVELOPMENT']
    scope: CalibrationScope
    raw_score: Unit
    correct: bool = Field(strict=True)
    use_permitted: bool = False
    independently_reviewed: bool = False
    split_frozen: bool = False
    synthetic: bool = True
    evidence_reference: str

class CalibrationBin(Contract):
    index: Count
    count: Count
    correct: Count
    probability: Unit

class CalibrationArtifact(Stamped):
    version: Identifier
    scope: CalibrationScope
    status: Literal['UNAVAILABLE','FUNCTIONAL_ONLY','VALIDATED']
    method: Literal['equal-width-smoothed-bins-v1'] = 'equal-width-smoothed-bins-v1'
    dataset_sha256: Sha256
    fit_count: Count = 0
    holdout_count: Count = 0
    fit_group_ids: tuple[Identifier,...] = ()
    holdout_group_ids: tuple[Identifier,...] = ()
    bin_count: int = Field(default=5,ge=1,le=20)
    bins: tuple[CalibrationBin,...] = ()
    brier: Unit|None = None
    ece: Unit|None = None
    reliability: tuple[dict,...] = ()
    reasons: tuple[str,...] = ()

    @model_validator(mode='after')
    def consistency(self):
        if set(self.fit_group_ids)&set(self.holdout_group_ids): raise ValueError('calibration group leakage')
        if self.status=='UNAVAILABLE' and self.bins: raise ValueError('unavailable calibration has no mapping')
        if len({b.index for b in self.bins})!=len(self.bins): raise ValueError('duplicate bin')
        for b in self.bins:
            if b.index>=self.bin_count or b.correct>b.count or b.count==0: raise ValueError('invalid calibration bin')
            if abs(b.probability-(b.correct+1)/(b.count+2))>1e-12: raise ValueError('invalid bin probability')
        if self.status!='UNAVAILABLE' and (not self.fit_count or not self.holdout_count or sum(b.count for b in self.bins)!=self.fit_count or self.brier is None or self.ece is None):
            raise ValueError('trained calibration requires counts and holdout metrics')
        return self

class SourceCheck(Contract):
    field_path: str
    raw_value: str
    fidelity_policy_version: Identifier
    verification_reference: str = Field(min_length=1)
    evidence: tuple[Evidence,...] = Field(min_length=1)

class QualityIssue(Contract):
    code: str
    field_path: str|None = None
    severity: Literal['INFO','WARNING','ERROR']
    classification: Literal['INVALID_EXTRACTION','INVALID_SOURCE_CONTENT','UNKNOWN','QUALITY']
    evidence: tuple[Evidence,...] = ()
    source_block_refs: tuple[Identifier,...] = ()
    action: Literal['VERIFY_SOURCE','REQUEST_DATA','REEXTRACT','SELECT_CANDIDATE','CONFIRM_VALUE','REVIEW_SPLIT']
    message: str

class FieldQuality(Contract):
    field_path: str
    field_status: str
    validation: Literal['VALID','INVALID_SOURCE_CONTENT','UNKNOWN','NOT_CHECKED','NOT_APPLICABLE']
    reliability: Literal['CALIBRATED','DETERMINISTIC_VERIFIED','HUMAN_CONFIRMED','UNAVAILABLE']
    probability: Unit|None = None
    critical: bool
    eligible_within_policy: bool = False
    auto_accepted: Literal[False] = False

class Coverage(Contract):
    expected: Count
    denominator: Count
    present: Count
    excluded_not_applicable: Count
    excluded_not_provided: Count
    ratio: Unit|None

    @model_validator(mode='after')
    def counts(self):
        if self.expected!=self.denominator+self.excluded_not_applicable+self.excluded_not_provided or self.present>self.denominator:
            raise ValueError('invalid completeness counts')
        expected=self.present/self.denominator if self.denominator else None
        if self.ratio!=expected: raise ValueError('invalid completeness ratio')
        return self

class ConfidenceSummary(Contract):
    present_count: Count
    calibrated_count: Count
    calibrated_coverage: Unit|None
    mean: Unit|None
    minimum: Unit|None

    @model_validator(mode='after')
    def counts(self):
        if self.calibrated_count>self.present_count: raise ValueError('invalid confidence count')
        if self.calibrated_count==0 and (self.mean is not None or self.minimum is not None): raise ValueError('confidence without support')
        if self.calibrated_count and (self.mean is None or self.minimum is None or self.minimum>self.mean): raise ValueError('invalid confidence summary')
        if self.calibrated_coverage!=(self.calibrated_count/self.present_count if self.present_count else None): raise ValueError('confidence coverage mismatch')
        return self

class ReviewRecommendation(Contract):
    recommendation_id: Identifier
    reason: str
    field_path: str|None
    action: str
    issue_refs: tuple[int,...]

class QualityAssessment(Stamped):
    assessment_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    extraction_artifact_id: Identifier
    extraction_sha256: Sha256
    record_id: Identifier|None
    record_revision: int|None = Field(ge=1)
    input_sha256: Sha256
    implementation_sha256: Sha256
    policy_version: Identifier
    policy_sha256: Sha256
    profile_version: Identifier|None
    calibration_versions: tuple[Identifier,...] = ()
    calibration_sha256: Sha256
    completeness: Coverage
    critical_completeness: Coverage
    confidence: ConfidenceSummary
    fields: tuple[FieldQuality,...]
    issues: tuple[QualityIssue,...]
    recommendations: tuple[ReviewRecommendation,...]
    review_required: Literal[True] = True
    disposition: Literal['REVIEW','REQUEST_DATA','REEXTRACT','REVIEW_SPLIT']
    auto_accept_enabled: Literal[False] = False

    @model_validator(mode='after')
    def shape(self):
        if (self.record_id is None)!=(self.record_revision is None): raise ValueError('record/revision pair required')
        if len({f.field_path for f in self.fields})!=len(self.fields): raise ValueError('duplicate field assessment')
        for recommendation in self.recommendations:
            if any(index>=len(self.issues) or index<0 for index in recommendation.issue_refs): raise ValueError('bad issue ref')
        return self
