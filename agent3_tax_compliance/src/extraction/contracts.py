from typing import Literal
from pydantic import Field, model_validator
from ..domain.base import Contract, Identifier, Stamped
from ..domain.envelope import Sha256
from ..domain.evidence import Evidence,Unit
from ..domain.cfr import CanonicalFinancialRecord
from ..domain.field import FieldObject
from ..domain.money import ExactDecimal


class ExtractionProfile(Contract):
    version: Identifier = 'invoice-vi-v1'
    number_locale: Literal['AUTO','VI','EN'] = 'AUTO'
    date_order: Literal['AUTO','DMY','MDY'] = 'DMY'
    default_currency: str | None = None
    currency_policy_reference: str | None = None

    @model_validator(mode='after')
    def currency_policy(self):
        if bool(self.default_currency)!=bool(self.currency_policy_reference):
            raise ValueError('currency default requires explicit profile evidence')
        if self.default_currency and (len(self.default_currency)!=3 or not self.default_currency.isupper()):
            raise ValueError('currency must be a three-letter code')
        return self


class RawScore(Contract):
    block_id: Identifier
    value: Unit | None
    kind: str
    semantics: Literal['ENGINE_HEURISTIC_NOT_CALIBRATED','UNAVAILABLE']


class ExtractionCandidate(Contract):
    candidate_id: Identifier
    semantic_field: str
    raw_value: str
    normalized_value: str
    evidence_refs: tuple[Evidence,...] = ()
    block_refs: tuple[Identifier,...] = ()
    method_version: Identifier = 'label-region-v1'
    raw_scores: tuple[RawScore,...] = ()
    selection_reason: Literal['UNIQUE_VALUE','COMPETING_VALUE','PROFILE_POLICY']


class ExtractionIssue(Contract):
    code: str
    field_path: str | None = None
    message: str
    block_refs: tuple[Identifier,...] = ()


class IdentityEntry(Contract):
    anchor_id: Identifier
    item_id: Identifier


class ItemLineage(Contract):
    operation: Literal['SPLIT','MERGE']
    previous_ids: tuple[Identifier,...] = Field(min_length=1)
    new_ids: tuple[Identifier,...] = Field(min_length=1)
    reason: str = Field(min_length=1)


class IdentityMap(Contract):
    version: Literal['item-identity-v1'] = 'item-identity-v1'
    entries: tuple[IdentityEntry,...] = ()
    lineage: tuple[ItemLineage,...] = ()

    @model_validator(mode='after')
    def unique(self):
        if len({e.anchor_id for e in self.entries})!=len(self.entries) or len({e.item_id for e in self.entries})!=len(self.entries):
            raise ValueError('identity mapping must be one-to-one')
        return self


class DerivationNode(Contract):
    path: str
    inputs: tuple[str,...]


class DerivationManifest(Contract):
    version: Literal['derive-v1'] = 'derive-v1'
    observed_sha256: Sha256
    master_sha256: Sha256
    relations_sha256: Sha256
    profile_version: Identifier
    nodes: tuple[DerivationNode,...]

    @model_validator(mode='after')
    def acyclic(self):
        graph={n.path:n.inputs for n in self.nodes}
        if len(graph)!=len(self.nodes): raise ValueError('duplicate derivation node')
        def visit(path,active):
            if path in active: raise ValueError('circular derivation')
            for parent in graph.get(path,()): visit(parent,active|{path})
        for path in graph: visit(path,set())
        return self


class VATGroup(Contract):
    group_id: Identifier
    item_refs: tuple[Identifier,...] = Field(min_length=1)
    treatment: str | None
    rate: ExactDecimal | None
    category: FieldObject[str]
    net: FieldObject[ExactDecimal]
    discovery_status: Literal['COMPLETE','INCOMPLETE','UNKNOWN']


class Segmentation(Contract):
    status: Literal['SINGLE_CANDIDATE','REVIEW_SPLIT']
    page_groups: tuple[tuple[int,...],...] = ()
    reason: str


class ExtractionArtifact(Stamped):
    artifact_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    ingestion_id: Identifier
    source_id: Identifier
    document_id: Identifier
    input_sha256: Sha256
    normalized_input_sha256: Sha256
    extractor_sha256: Sha256
    profile: ExtractionProfile
    segmentation: Segmentation
    record: CanonicalFinancialRecord | None
    candidates: tuple[ExtractionCandidate,...] = ()
    identity_map: IdentityMap
    vat_groups: tuple[VATGroup,...] = ()
    derivation: DerivationManifest | None
    issues: tuple[ExtractionIssue,...] = ()
    review_required: Literal[True] = True

    @model_validator(mode='after')
    def ownership(self):
        if (self.segmentation.status=='REVIEW_SPLIT')!=(self.record is None):
            raise ValueError('unconfirmed multi-invoice boundaries cannot produce a merged record')
        if self.record:
            if (self.record.tenant_id,self.record.taxpayer_id,self.record.source_id,self.record.document_id)!=(
                    self.tenant_id,self.taxpayer_id,self.source_id,self.document_id): raise ValueError('record ownership mismatch')
            ids={i.item_id for i in self.record.items}
            if ids!={e.item_id for e in self.identity_map.entries}: raise ValueError('item identity mismatch')
            refs=[ref for g in self.vat_groups for ref in g.item_refs]
            if len(refs)!=len(set(refs)) or set(refs)!=ids: raise ValueError('invalid VAT group item partition')
            if self.derivation is None: raise ValueError('record requires derivation manifest')
        for c in self.candidates:
            for e in c.evidence_refs:
                if (e.source_id,e.document_id)!=(self.source_id,self.document_id): raise ValueError('candidate ownership mismatch')
        return self
