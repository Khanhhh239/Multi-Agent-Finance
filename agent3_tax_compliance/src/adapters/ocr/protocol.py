from typing import Annotated, Literal, Any
from pydantic import Field, model_validator

from ...domain.base import Contract, Identifier, Stamped
from ...domain.envelope import Sha256
from ...domain.evidence import Evidence, Unit
from ...ingestion.models import Geometry

Finite = Annotated[float, Field(allow_inf_nan=False)]
Score = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class OCRConfig(Contract):
    version: Identifier = 'tesseract-v1-psm3'
    model_id: Identifier = 'tesseract'
    language: Literal['vie+eng'] = 'vie+eng'
    psm: Literal[3, 6, 11] = 3
    preprocess_version: Literal['render-identity-v1'] = 'render-identity-v1'
    timeout_seconds: int = Field(default=30, ge=1, le=900)
    memory_mb: int = Field(default=512, ge=64, le=8192)
    parameters: dict[str, Any] = {}
    max_output_bytes: int = Field(default=4*1024*1024, ge=1024, le=16*1024*1024)
    max_attempts: int = Field(default=2, ge=1, le=3)


class OCRBridgeRequest(Stamped):
    protocol_version: Literal['ocr-bridge-1'] = 'ocr-bridge-1'
    accepted_result_version: Literal['1.1'] = '1.1'
    request_id: Identifier
    source_id: Identifier
    document_id: Identifier
    page_id: Identifier
    page_index: int = Field(ge=0)
    image_hash: Sha256
    image_path: str
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    model_config_version: Identifier
    runtime_sha256: Sha256
    model_id: Identifier = 'tesseract'
    timeout_seconds: int = Field(ge=1, le=900)


class Detection(Contract):
    polygon: tuple[tuple[Finite, Finite], ...] = Field(min_length=3, max_length=64)
    text_raw: str = Field(max_length=200000)
    confidence: Score | None = None
    block_type: str | None = None
    source_id: str | None = None


class BenchmarkResult(Contract):
    schema_version: Literal['1.1']
    run_id: str
    model_id: str
    output_mode: Literal['boxes_and_text', 'full_page_text', 'structured_document']
    image_id: str
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    load_time_ms: Finite = Field(ge=0)
    inference_time_ms: Finite = Field(ge=0)
    document_text_raw: str = Field(default='', max_length=200000)
    detections: tuple[Detection, ...] = Field(default=(), max_length=20000)
    structured_blocks: tuple[dict[str, Any], ...] = ()
    error: str | None = None
    metadata: dict[str, Any] = {}


class OCRIssue(Contract):
    code: Literal['MODEL_UNAVAILABLE','BAD_INPUT','PROTOCOL_ERROR','WORKER_TIMEOUT',
                  'WORKER_CRASH','TRANSIENT_IO','OUTPUT_LIMIT','OCR_FAILED']
    retryable: bool = False
    message: str


class OCRError(Exception):
    def __init__(self, code, message, retryable=False):
        self.issue=OCRIssue(code=code, message=message, retryable=retryable)
        super().__init__(message)


class OCRBridgeResponse(Stamped):
    protocol_version: Literal['ocr-bridge-1'] = 'ocr-bridge-1'
    request_id: Identifier
    source_id: Identifier
    document_id: Identifier
    page_id: Identifier
    page_index: int = Field(ge=0)
    image_hash: Sha256
    model_config_version: Identifier
    runtime_sha256: Sha256
    engine_versions: dict[str, str]
    result: BenchmarkResult | None = None
    issue: OCRIssue | None = None

    @model_validator(mode='after')
    def exclusive(self):
        if (self.result is None)==(self.issue is None):
            raise ValueError('exactly one of result or issue is required')
        if self.result and self.result.error:
            raise ValueError('failed benchmark result must use typed issue')
        return self


class BlockOrigin(Contract):
    method: Literal['NATIVE_TEXT','OCR']
    source_block_id: str
    raw_score: Score | None = None
    score_semantics: Literal['ENGINE_HEURISTIC_NOT_CALIBRATED','UNAVAILABLE'] = 'UNAVAILABLE'
    score_kind: Literal['ENGINE_AGGREGATE','DETECTION','UNAVAILABLE'] = 'ENGINE_AGGREGATE'
    response_sha256: Sha256 | None = None


class ExtractionBlock(Contract):
    block_id: Identifier
    text_raw: str
    geometry_status: Literal['AVAILABLE','UNAVAILABLE']
    evidence: Evidence | None = None
    polygon: Annotated[tuple[tuple[Unit, Unit], ...], Field(min_length=3,max_length=64)] | None = None
    block_type: str | None = None
    reading_order: int = Field(ge=0)
    origins: tuple[BlockOrigin, ...] = Field(min_length=1)
    conflict_with: tuple[Identifier, ...] = ()

    @model_validator(mode='after')
    def geometry(self):
        if (self.geometry_status=='AVAILABLE') != (self.evidence is not None):
            raise ValueError('geometry availability and evidence mismatch')
        if self.geometry_status=='UNAVAILABLE' and self.polygon is not None:
            raise ValueError('unavailable geometry cannot have polygon')
        if self.polygon is not None:
            xs,ys=zip(*self.polygon)
            if any(abs(a-b)>1e-9 for a,b in zip((min(xs),min(ys),max(xs),max(ys)),self.evidence.bbox)):
                raise ValueError('polygon and evidence bbox mismatch')
        return self


class NormalizedPageExtraction(Stamped):
    page_id: Identifier
    page_index: int = Field(ge=0)
    image_hash: Sha256
    geometry: Geometry
    route: Literal['NATIVE_TEXT','OCR','HYBRID','UNSUPPORTED']
    status: Literal['COMPLETE','FAILED']
    blocks: tuple[ExtractionBlock, ...] = ()
    raw_responses: tuple[OCRBridgeResponse, ...] = ()
    table_candidates: tuple[Identifier, ...] = ()
    issue: OCRIssue | None = None

    @model_validator(mode='after')
    def state(self):
        if (self.status=='FAILED') != (self.issue is not None):
            raise ValueError('page failure needs issue')
        if len({b.block_id for b in self.blocks})!=len(self.blocks): raise ValueError('duplicate block IDs')
        for response in self.raw_responses:
            if (response.page_id,response.page_index,response.image_hash)!=(self.page_id,self.page_index,self.image_hash):
                raise ValueError('response/page identity mismatch')
        return self


class NormalizedDocumentExtraction(Stamped):
    tenant_id: Identifier
    taxpayer_id: Identifier
    taxpayer_master_revision: int = Field(ge=1)
    ingestion_id: Identifier
    source_id: Identifier
    document_id: Identifier
    input_sha256: Sha256
    document_artifact_sha256: Sha256
    runtime_sha256: Sha256
    ocr_config: OCRConfig
    status: Literal['COMPLETE','PARTIAL','FAILED']
    pages: tuple[NormalizedPageExtraction, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def complete(self):
        if [p.page_index for p in self.pages]!=list(range(len(self.pages))):
            raise ValueError('pages must be contiguous and ordered')
        good=sum(p.status=='COMPLETE' for p in self.pages)
        expected='COMPLETE' if good==len(self.pages) else 'PARTIAL' if good else 'FAILED'
        if self.status!=expected: raise ValueError('document completeness mismatch')
        for page in self.pages:
            for response in page.raw_responses:
                if (response.source_id,response.document_id,response.runtime_sha256,response.model_config_version)!=(
                        self.source_id,self.document_id,self.runtime_sha256,self.ocr_config.version):
                    raise ValueError('raw response/document identity mismatch')
                if response.result and response.result.model_id!=self.ocr_config.model_id:
                    raise ValueError('raw result engine mismatch')
            for block in page.blocks:
                ev=block.evidence
                if ev and (ev.source_id,ev.document_id,ev.page_index,ev.transform_id)!=(
                        self.source_id,self.document_id,page.page_index,page.geometry.transform_id):
                    raise ValueError('evidence ownership mismatch')
        return self


class OCRJobView(Stamped):
    ingestion_id: Identifier
    config_key: Sha256
    status: Literal['QUEUED','PROCESSING','COMPLETE','PARTIAL','FAILED']
    attempts: int = Field(ge=0)
    issue: OCRIssue | None = None
    result: NormalizedDocumentExtraction | None = None


def correlate(request: OCRBridgeRequest, response: OCRBridgeResponse):
    for name in ('request_id','source_id','document_id','page_id','page_index','image_hash',
                 'model_config_version','runtime_sha256'):
        if getattr(request,name)!=getattr(response,name):
            raise OCRError('PROTOCOL_ERROR',f'Response correlation mismatch: {name}')
    if response.result and (response.result.image_width,response.result.image_height)!=(request.image_width,request.image_height):
        raise OCRError('PROTOCOL_ERROR','Response dimensions mismatch')
    if response.result and (response.result.image_id!=__import__('pathlib').Path(request.image_path).name
                            or response.result.model_id!=request.model_id or response.result.run_id!=request.request_id):
        raise OCRError('PROTOCOL_ERROR','Benchmark result identity mismatch')
