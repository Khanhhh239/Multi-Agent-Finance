from datetime import date
from typing import Literal, Annotated
from pydantic import Field, model_validator, StrictBool, StrictStr
from ..domain.base import Contract, Stamped, Identifier
from ..domain.envelope import Sha256, SourceFormat
from ..domain.field import FieldObject
from ..domain.money import ExactDecimal
from ..quality.contracts import FieldQuality

Tri = Literal['MATCH','NO_MATCH','UNKNOWN']
CapabilityState = Literal['SUPPORTED','UNSUPPORTED','UNKNOWN']
Eligibility = Literal['ELIGIBLE','NOT_EVALUATED_MISSING_INPUT','NOT_EVALUATED_LOW_CONFIDENCE',
    'NOT_EVALUATED_INVALID_EXTRACTION','OUT_OF_SCOPE_FOR_SOURCE','NOT_APPLICABLE','REVIEW_REQUIRED',
    'NOT_EVALUATED_UNKNOWN_APPLICABILITY','NOT_EVALUATED_PLANNING_ERROR']


class FieldRequirement(Contract):
    path: str
    min_confidence: float = Field(default=.99,ge=0,le=1)
    allowed_validity: tuple[Literal['VALID','INVALID_SOURCE_CONTENT'],...] = ('VALID',)
    source_issue_codes: tuple[str,...] = ()
    source_fidelity_policy: Identifier | None = None

    @model_validator(mode='after')
    def invalid_source_policy(self):
        if 'INVALID_SOURCE_CONTENT' in self.allowed_validity and (not self.source_issue_codes or not self.source_fidelity_policy):
            raise ValueError('invalid source content needs scoped issue/fidelity policy')
        return self


class Predicate(Contract):
    requirement: FieldRequirement
    operator: Literal['EQ','GTE'] = 'EQ'
    value: StrictStr | StrictBool

    @model_validator(mode='after')
    def numeric_literal(self):
        if self.operator == 'GTE':
            from decimal import Decimal, InvalidOperation
            try:
                if not isinstance(self.value, str) or not Decimal(self.value).is_finite():
                    raise ValueError('GTE needs a finite decimal string')
            except InvalidOperation as exc:
                raise ValueError('GTE needs a finite decimal string') from exc
        return self


class LegalBasis(Contract):
    document_id: Identifier
    locator: str = Field(min_length=1)


class ObservationRequirement(Contract):
    field_path: str
    fidelity_policy: Identifier
    accepts: tuple[Literal['PRESENT_VALUE','CONFIRMED_ABSENT'],...] = ('PRESENT_VALUE','CONFIRMED_ABSENT')


class RuleVersion(Contract):
    rule_id: Identifier
    version: Identifier
    family: Literal['INVOICE_CONTENT','VAT_RATE','PAYMENT_EVIDENCE']
    effective_from: date
    effective_to: date
    date_field: Literal['invoice.issue_date','context.obligation_date'] = 'invoice.issue_date'
    unit_type: Literal['RECORD','ITEM','VAT_GROUP'] = 'RECORD'
    legal_basis: tuple[LegalBasis,...] = Field(min_length=1)
    publication: Literal['DRAFT','APPROVED_TECHNICAL'] = 'DRAFT'
    review_reference: str | None = None
    predicates: tuple[Predicate,...] = ()
    required_fields: tuple[FieldRequirement,...] = ()
    required_observations: tuple[ObservationRequirement,...] = ()
    non_cash_policy: Literal['non-cash-scope-v1'] | None = None
    inclusive_threshold: ExactDecimal | None = None

    @model_validator(mode='after')
    def valid(self):
        if self.effective_to <= self.effective_from: raise ValueError('exclusive interval required')
        if self.publication=='APPROVED_TECHNICAL' and not self.review_reference:
            raise ValueError('approved rule needs explicit review reference')
        if self.non_cash_policy and self.family!='PAYMENT_EVIDENCE':raise ValueError('non-cash is a payment policy')
        if self.non_cash_policy and (self.inclusive_threshold is None or self.inclusive_threshold<=0):
            raise ValueError('non-cash policy requires a positive configured threshold')
        if len({f.path for f in self.required_fields})!=len(self.required_fields):raise ValueError('duplicate requirement')
        return self


class RuleFamily(Contract):
    rule_id: Identifier
    supported_from: date
    supported_to: date
    versions: tuple[RuleVersion,...] = Field(min_length=1)

    @model_validator(mode='after')
    def valid(self):
        if self.supported_to<=self.supported_from:raise ValueError('invalid support interval')
        if any(v.rule_id!=self.rule_id for v in self.versions):raise ValueError('cross-rule version')
        if len({v.version for v in self.versions})!=len(self.versions):raise ValueError('duplicate rule version')
        if len({v.family for v in self.versions})!=1 or len({v.date_field for v in self.versions})!=1:
            raise ValueError('family and date policy must be consistent')
        return self


class RuleSet(Contract):
    version: Identifier
    families: tuple[RuleFamily,...]

    @model_validator(mode='after')
    def unique(self):
        if len({f.rule_id for f in self.families})!=len(self.families):raise ValueError('duplicate family')
        return self


class CapabilityProfile(Contract):
    profile_id: Identifier
    version: Identifier
    adapter_id: Identifier
    adapter_version: Identifier
    source_formats: tuple[SourceFormat,...]
    supported_families: tuple[str,...]
    unsupported_families: tuple[str,...] = ()
    absence_fidelity_policies: tuple[Identifier,...] = ()

    @model_validator(mode='after')
    def disjoint(self):
        if set(self.supported_families)&set(self.unsupported_families):raise ValueError('contradictory capabilities')
        return self


class ContextValue(Contract):
    path: Literal['context.vat_method','context.claim_input_vat','context.invoice_kind',
                  'context.payment_case','context.obligation_date']
    field: FieldObject[StrictStr | StrictBool]
    quality: FieldQuality
    verification_reference: str = Field(min_length=1)

    @model_validator(mode='after')
    def typed(self):
        if self.quality.field_path!=self.path or self.quality.field_status!=self.field.status:
            raise ValueError('context quality mismatch')
        value=self.field.value
        allowed={'context.vat_method':('DEDUCTION','DIRECT'), 'context.invoice_kind':('VAT','SALE','OTHER'),
                 'context.payment_case':('STANDARD','SPECIAL')}
        if value is not None:
            if self.path=='context.claim_input_vat' and type(value) is not bool:raise ValueError('strict boolean required')
            if self.path in allowed and value not in allowed[self.path]:raise ValueError('unknown context enum')
            if self.path=='context.obligation_date':date.fromisoformat(value)
        return self


class PurchaseEvidence(Contract):
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    revision: int = Field(ge=1)
    input_sha256: Sha256
    issue_date: date
    seller_tax_id: str = Field(pattern=r'^[0-9]{10}(?:[0-9]{3})?$')
    currency: Literal['VND'] = 'VND'
    gross: ExactDecimal = Field(ge=0)


class DailyPurchases(Contract):
    version: Identifier
    complete: bool = Field(strict=True)
    verification_reference: str = Field(min_length=1)
    purchases: tuple[PurchaseEvidence,...]

    @model_validator(mode='after')
    def unique(self):
        if len({p.record_id for p in self.purchases})!=len(self.purchases):raise ValueError('duplicate daily invoice')
        return self


class FieldObservation(Contract):
    observation_id: Identifier
    field_path: str
    kind: Literal['PRESENT_VALUE','CONFIRMED_ABSENT','UNKNOWN']
    fidelity_policy: Identifier
    validator_version: Identifier
    method: Literal['COMPLETE_PARSE','HUMAN_REVIEW','OCR']
    evidence_reference: str = Field(min_length=1)
    document_complete: bool = Field(strict=True)
    source_id: Identifier
    source_record_id: Identifier
    source_revision: int = Field(ge=1)
    profile_id: Identifier
    profile_version: Identifier
    verification_reference: str | None = None


class PlanningContext(Contract):
    version: Identifier = 'planning-context-v1'
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    record_revision: int = Field(ge=1)
    values: tuple[ContextValue,...] = ()
    daily: DailyPurchases | None = None
    observations: tuple[FieldObservation,...] = ()
    classifications: tuple['ItemClassification',...] = ()

    @model_validator(mode='after')
    def unique(self):
        if len({v.path for v in self.values})!=len(self.values):raise ValueError('duplicate context value')
        if len({o.field_path for o in self.observations})!=len(self.observations):raise ValueError('duplicate observation')
        if len({c.item_id for c in self.classifications})!=len(self.classifications):raise ValueError('duplicate classification')
        if self.daily and any((p.tenant_id,p.taxpayer_id)!=(self.tenant_id,self.taxpayer_id) for p in self.daily.purchases):
            raise ValueError('cross-tenant daily purchase evidence')
        if any((o.source_record_id,o.source_revision)!=(self.record_id,self.record_revision) for o in self.observations):
            raise ValueError('stale or cross-record observation')
        return self


class ItemClassification(Contract):
    item_id: Identifier
    item_code: str | None = None
    category: FieldObject[StrictStr]
    quality: FieldQuality
    mapping_id: Identifier | None = None
    evidence_kind: Literal['CATALOGUE','CONTRACT','HUMAN_CLASSIFICATION']
    verification_reference: str = Field(min_length=1)


PlanningContext.model_rebuild()


class PredicateTrace(Contract):
    policy: str
    field_paths: tuple[str,...] = ()
    state: Tri
    reason: str
    evidence_refs: tuple[str,...] = ()


class EvaluationUnit(Contract):
    unit_type: Literal['RECORD','ITEM','VAT_GROUP']
    unit_id: Identifier
    item_refs: tuple[Identifier,...] = ()
    discovery: Literal['COMPLETE','INCOMPLETE','UNKNOWN']


class RulePlanEntry(Contract):
    rule_id: Identifier
    rule_version: Identifier | None
    unit: EvaluationUnit
    selection: Tri
    applicability: Tri
    capability: CapabilityState
    eligibility: Eligibility
    reasons: tuple[str,...]
    next_action: Literal['NONE','HUMAN_REVIEW','REQUEST_DATA','REEXTRACT','RETRY','OPERATOR','COLLECT_OTHER_SOURCE']
    review_required: bool
    traces: tuple[PredicateTrace,...] = ()
    legal_basis: tuple[LegalBasis,...] = ()

    @model_validator(mode='after')
    def gates(self):
        if self.eligibility=='ELIGIBLE' and (self.rule_version is None or self.selection!='MATCH'
            or self.applicability!='MATCH' or self.capability!='SUPPORTED' or self.unit.discovery!='COMPLETE' or not self.legal_basis):
            raise ValueError('eligible entry lacks planning gates')
        if self.eligibility=='NOT_APPLICABLE' and self.applicability!='NO_MATCH':raise ValueError('unproven exclusion')
        if self.eligibility=='OUT_OF_SCOPE_FOR_SOURCE' and (self.applicability!='MATCH' or self.capability!='UNSUPPORTED'):
            raise ValueError('unproven source scope exclusion')
        return self


class VersionPin(Contract):
    name: str
    version: str
    sha256: Sha256


class RulePlan(Stamped):
    evaluation_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    record_revision: int = Field(ge=1)
    taxpayer_master_revision: int = Field(ge=1)
    record_sha256: Sha256
    implementation_sha256: Sha256
    pins: tuple[VersionPin,...]
    entries: tuple[RulePlanEntry,...]
    engine_calls: Literal[0] = 0
    technical_only: Literal[True] = True

    @model_validator(mode='after')
    def keys(self):
        keys=[(e.rule_id,e.rule_version,e.unit.unit_type,e.unit.unit_id) for e in self.entries]
        if len(keys)!=len(set(keys)):raise ValueError('duplicate evaluation key')
        return self
