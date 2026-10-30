from typing import Annotated, Literal
from pydantic import Field, model_validator

from ..domain.base import Contract, Identifier, Stamped
from ..domain.envelope import Sha256, SourceFormat
from ..domain.evidence import Evidence, Unit


class IngestionIssue(Contract):
    code: Literal['EMPTY_FILE','UPLOAD_TIMEOUT','LIMIT_EXCEEDED','FORMAT_MISMATCH','UNSUPPORTED_FORMAT','CORRUPT_DOCUMENT',
                  'ENCRYPTED_PDF','WORKER_TIMEOUT','WORKER_RESOURCE_ERROR','PROCESSING_ERROR',
                  'IDEMPOTENCY_CONFLICT','ACCESS_DENIED','NOT_FOUND','RETRY_NOT_ALLOWED']
    retryable: bool = False
    message: str
    next_action: str


class IngestionError(Exception):
    def __init__(self, code, message, *, retryable=False, next_action='Correct the input and submit with a new key.', status=422):
        self.issue=IngestionIssue(code=code,message=message,retryable=retryable,next_action=next_action)
        self.status=status
        super().__init__(message)


class RoutePolicy(Contract):
    version: Identifier = 'route-v1.3'
    min_alphanumeric: int = Field(default=20,ge=1)
    min_valid_glyph_ratio: float = Field(default=0.98,ge=0,le=1)
    min_text_coverage: float = Field(default=0.0005,ge=0,le=1)
    hybrid_image_coverage: float = Field(default=0.20,ge=0,le=1)


class AuthGrant(Contract):
    token_sha256: Sha256
    actor_id: Identifier
    tenant_id: Identifier
    taxpayer_ids: frozenset[Identifier]
    permissions: frozenset[Literal['READ','WRITE','ADMIN']]


class TextBlock(Contract):
    block_id: Identifier
    text: str
    source_order: int = Field(ge=0)
    reading_order: int = Field(ge=0)
    original_bbox: tuple[float,float,float,float]
    evidence: Evidence


class Geometry(Contract):
    transform_id: Identifier
    version: Identifier = 'geometry-v1'
    original_space: Literal['PDF_UNROTATED_CROP_TOP_LEFT','IMAGE_RAW_PIXELS']
    crop_origin: tuple[float,float] = (0,0)
    original_to_render: tuple[float,float,float,float,float,float]
    render_to_original: tuple[float,float,float,float,float,float]
    render_to_processed: tuple[float,float,float,float,float,float] = (1,0,0,1,0,0)
    processed_to_render: tuple[float,float,float,float,float,float] = (1,0,0,1,0,0)

    @model_validator(mode='after')
    def reversible(self):
        import math
        from .preprocess import IDENTITY, compose, inverse
        for forward,backward in ((self.original_to_render,self.render_to_original),
                                 (self.render_to_processed,self.processed_to_render)):
            inverse(forward); inverse(backward)
            if not all(math.isfinite(v) and abs(v-target)<1e-6 for v,target in zip(compose(forward,backward),IDENTITY)):
                raise ValueError('transform/inverse mismatch')
        return self


class PageArtifact(Stamped):
    source_id: Identifier
    input_sha256: Sha256
    document_id: Identifier
    page_id: Identifier
    page_index: int = Field(ge=0)
    original_width: float = Field(gt=0)
    original_height: float = Field(gt=0)
    render_width: int = Field(gt=0)
    render_height: int = Field(gt=0)
    rotation: Literal[0,90,180,270] = 0
    exif_orientation: int = Field(default=1,ge=1,le=8)
    geometry: Geometry
    render_sha256: Sha256
    route: Literal['NATIVE_TEXT','OCR','HYBRID','UNSUPPORTED']
    route_policy_version: Identifier
    route_reasons: tuple[str,...]
    valid_glyph_ratio: float = Field(ge=0,le=1)
    text_coverage: float = Field(ge=0,le=1)
    image_coverage: float = Field(ge=0,le=1)
    invisible_text_spans: int = Field(ge=0)
    table_structure_present: bool = False
    ocr_regions: tuple[tuple[Unit,Unit,Unit,Unit],...] = ()
    native_blocks: tuple[TextBlock,...] = ()
    deduplication_required: bool = False

    @model_validator(mode='after')
    def evidence_and_route(self):
        for block in self.native_blocks:
            evidence=block.evidence
            if (evidence.source_id,evidence.document_id,evidence.page_index,evidence.transform_id)!=(
                    self.source_id,self.document_id,self.page_index,self.geometry.transform_id):
                raise ValueError('block evidence ownership/transform mismatch')
        if any(r[0]>=r[2] or r[1]>=r[3] for r in self.ocr_regions):
            raise ValueError('OCR region must have positive area')
        if self.route=='NATIVE_TEXT' and (not self.native_blocks or self.ocr_regions):
            raise ValueError('native route requires text and no OCR regions')
        if self.route in ('OCR','HYBRID') and not self.ocr_regions:
            raise ValueError('OCR route requires regions')
        if self.route=='HYBRID' and (not self.native_blocks or not self.deduplication_required):
            raise ValueError('hybrid route requires native evidence and deduplication')
        return self


class DocumentArtifact(Stamped):
    tenant_id: Identifier
    taxpayer_id: Identifier
    taxpayer_master_revision: int = Field(ge=1)
    ingestion_id: Identifier
    source_id: Identifier
    document_id: Identifier
    input_sha256: Sha256
    source_format: SourceFormat
    reader_elapsed_ms: float = Field(ge=0)
    pages: tuple[PageArtifact,...] = Field(min_length=1)

    @model_validator(mode='after')
    def page_ownership(self):
        if [p.page_index for p in self.pages]!=list(range(len(self.pages))):
            raise ValueError('document pages must be complete, unique and ordered')
        for page in self.pages:
            if (page.source_id,page.document_id,page.input_sha256)!=(self.source_id,self.document_id,self.input_sha256):
                raise ValueError('page ownership/hash mismatch')
        return self


class IngestionView(Stamped):
    ingestion_id: Identifier
    source_id: Identifier
    document_id: Identifier
    input_sha256: Sha256
    status: Literal['STORED','QUEUED','PROCESSING','SUCCEEDED','FAILED']
    attempts: int = Field(ge=0)
    issue: IngestionIssue | None = None
    extraction_status: Literal['NOT_QUEUED','QUEUED'] = 'NOT_QUEUED'
