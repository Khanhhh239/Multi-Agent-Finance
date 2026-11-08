"""Typed module boundaries; implementations belong to PLAN_02 onward."""
from typing import Annotated, Generic, Literal, Protocol, TypeVar

from pydantic import Field, model_validator

from .base import Contract, Identifier, Stamped
from .cfr import CanonicalFinancialRecord
from .envelope import Sha256, SourceEnvelope, SourceFormat
from .evidence import PageTransform
from .field import FieldObject
from .taxpayer import TaxpayerMaster

T = TypeVar('T')


class StageError(Contract):
    code: Literal['INVALID_INPUT', 'UNSUPPORTED', 'ACCESS_DENIED', 'REVISION_CONFLICT', 'PROCESSING_ERROR']
    retryable: bool
    message: str


class StageResponse(Stamped, Generic[T]):
    request_id: Identifier
    input_sha256: Sha256
    status: Literal['SUCCEEDED', 'ERROR']
    data: T | None = None
    error: StageError | None = None

    @model_validator(mode='after')
    def outcome(self):
        if self.status == 'SUCCEEDED' and (self.data is None or self.error is not None):
            raise ValueError('success requires typed data and no error')
        if self.status == 'ERROR' and (self.data is not None or self.error is None):
            raise ValueError('error requires typed error and null data')
        return self


class DetectedSource(Contract):
    envelope: SourceEnvelope
    detected_format: SourceFormat
    detection_status: Literal['SUPPORTED', 'UNSUPPORTED', 'UNKNOWN']


class DocumentPage(Contract):
    page_index: Annotated[int, Field(strict=True, ge=0)]
    kind: Literal['NATIVE_TEXT', 'SCAN', 'IMAGE']
    transform: PageTransform


class Document(Stamped):
    source_id: Identifier
    document_id: Identifier
    input_sha256: Sha256
    pages: tuple[DocumentPage, ...] = Field(min_length=1)


class Extraction(Stamped):
    source_id: Identifier
    document_id: Identifier
    input_sha256: Sha256
    fields: dict[str, FieldObject[str]]


class Assessment(Stamped):
    record_id: Identifier
    record_revision: Annotated[int, Field(strict=True, ge=1)]
    input_sha256: Sha256
    review_required: bool
    issue_codes: tuple[str, ...]


class Correction(Stamped):
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    expected_revision: Annotated[int, Field(strict=True, ge=1)]
    task_id: Identifier
    field_path: str = Field(min_length=1)
    item_id: Identifier | None = None
    selected_candidate_id: Identifier | None = None
    new_value: str | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode='after')
    def selection(self):
        if (self.selected_candidate_id is None) == (self.new_value is None):
            raise ValueError('choose exactly one candidate or replacement value')
        return self


class Detector(Protocol):
    def detect(self, envelope: SourceEnvelope) -> StageResponse[DetectedSource]: ...


class Extractor(Protocol):
    def extract(self, document: Document) -> StageResponse[Extraction]: ...


class Canonicalizer(Protocol):
    def canonicalize(self, extraction: Extraction, master_revision: TaxpayerMaster) -> StageResponse[tuple[CanonicalFinancialRecord, ...]]: ...


class Assessor(Protocol):
    def assess(self, cfr: CanonicalFinancialRecord) -> StageResponse[Assessment]: ...


class Reviewer(Protocol):
    """PLAN_06 must rederive Layer 5 before quality; repository is not a review service."""
    def review(self, correction: Correction) -> StageResponse[CanonicalFinancialRecord]: ...
