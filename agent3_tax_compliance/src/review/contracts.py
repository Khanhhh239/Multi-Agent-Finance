from typing import Literal, Annotated
from pydantic import Field, model_validator
from ..domain.base import Contract, Identifier, Stamped
from ..domain.envelope import Sha256
from ..extraction.contracts import DerivationManifest

class FieldCorrection(Contract):
    field_path: str
    before: dict | str | None
    after: dict | str

class CorrectionEvent(Stamped):
    event_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    actor_id: Identifier
    task_id: Identifier
    reason: str=Field(min_length=1)
    before_revision: Annotated[int,Field(strict=True,ge=1)]
    after_revision: Annotated[int,Field(strict=True,ge=2)]
    before_sha256: Sha256
    after_sha256: Sha256
    changes: tuple[FieldCorrection,...]=Field(min_length=1)
    record_stamp: dict
    derivation: DerivationManifest
    affected_nodes: tuple[str,...]
    assessment_id: Identifier
    completeness_proof: dict | None

    @model_validator(mode='after')
    def consecutive(self):
        if self.after_revision!=self.before_revision+1: raise ValueError('nonconsecutive correction')
        if len({c.field_path for c in self.changes})!=len(self.changes): raise ValueError('duplicate event field')
        return self

class CorrectionResult(Contract):
    schema_version: Literal['1.0.0']='1.0.0'
    event_id: Identifier
    record_revision: int
    assessment_id: Identifier
    replayed: bool

class ReviewTask(Stamped):
    config_version: Identifier='review-task-v1'
    creator: Identifier='review-task-builder'
    stage: Identifier='review'
    tenant_id: Identifier
    taxpayer_id: Identifier
    task_id: Identifier
    record_id: Identifier
    revision: int
    assessment_id: Identifier
    reason: str
    field_path: str
    action: str
    status: Literal['OPEN','RESOLVED','SUPERSEDED','WAITING_DATA','OPERATOR']
    previous_ids: tuple[Identifier,...]

class TaskPage(Contract):
    schema_version: Literal['1.0.0']='1.0.0'
    items: tuple[ReviewTask,...]
    next_cursor: str | None

class Change(Contract):
    field_path: str = Field(min_length=1,max_length=180)
    operation: Literal['SET','CONFIRM','CLEAR'] = 'SET'
    new_value: Annotated[str,Field(strict=True,max_length=10000)] | None = None
    selected_candidate_id: Identifier | None = None

    @model_validator(mode='after')
    def shape(self):
        if self.operation=='SET' and (self.new_value is None)==(self.selected_candidate_id is None):
            raise ValueError('SET requires exactly one value or candidate')
        if self.operation!='SET' and (self.new_value is not None or self.selected_candidate_id is not None):
            raise ValueError('CONFIRM/CLEAR take no value or candidate')
        if self.new_value is not None and not self.new_value.strip(): raise ValueError('empty value')
        return self

class ItemOperation(Contract):
    operation: Literal['ADD','DELETE']
    item_id: Identifier
    page_index: Annotated[int,Field(strict=True,ge=0)] | None = None
    bbox: tuple[Annotated[float,Field(ge=0,le=1,allow_inf_nan=False)],
                Annotated[float,Field(ge=0,le=1,allow_inf_nan=False)],
                Annotated[float,Field(ge=0,le=1,allow_inf_nan=False)],
                Annotated[float,Field(ge=0,le=1,allow_inf_nan=False)]] | None = None
    values: dict[str,Annotated[str,Field(strict=True,min_length=1,max_length=10000)]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def shape(self):
        allowed={'description','quantity','unit_price','net','vat_treatment','vat_rate'}
        if self.operation=='DELETE':
            if self.values or self.page_index is not None or self.bbox is not None: raise ValueError('DELETE takes only item_id')
        else:
            if self.page_index is None or self.bbox is None or not self.values.get('description','').strip():
                raise ValueError('ADD requires source page, region and printed description')
            if not self.values.keys()<=allowed or any(not v.strip() for v in self.values.values()):raise ValueError('invalid item fields')
            if self.bbox[0]>=self.bbox[2] or self.bbox[1]>=self.bbox[3]:raise ValueError('positive region required')
        return self


class CorrectionCommand(Contract):
    record_id: Identifier
    expected_revision: Annotated[int,Field(strict=True,ge=1)]
    task_id: Identifier
    reason: str = Field(min_length=1,max_length=2000)
    changes: tuple[Change,...] = Field(default=(),max_length=32)
    item_operations: tuple[ItemOperation,...] = Field(default=(),max_length=10)
    confirm_items_complete: bool = False
    expected_item_count: Annotated[int,Field(strict=True,ge=1)] | None = None
    verified_pages: tuple[Annotated[int,Field(strict=True,ge=0)],...] = ()

    @model_validator(mode='after')
    def meaningful(self):
        if not self.reason.strip(): raise ValueError('reason required')
        if not self.changes and not self.item_operations and not self.confirm_items_complete: raise ValueError('no correction')
        ids=[o.item_id for o in self.item_operations]
        if ids and self.changes:raise ValueError('save row operations separately from field edits')
        if len(set(ids))!=len(ids):raise ValueError('duplicate item operation')
        if any(c.field_path.startswith('items.'+i+'.') for i in ids for c in self.changes):raise ValueError('item operation conflicts with field change')
        if len({c.field_path for c in self.changes})!=len(self.changes): raise ValueError('duplicate field')
        if not self.confirm_items_complete and (self.expected_item_count is not None or self.verified_pages):
            raise ValueError('row/page proof requires completeness confirmation')
        return self

class TaskAction(Contract):
    action: Literal['REQUEST_DATA','OPERATOR','REOPEN']
    reason: str = Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.reason.strip(): raise ValueError('reason required')
        return self

class ReviewError(Exception):
    def __init__(self,code,message,status=422,latest_revision=None):
        self.code=code;self.message=message;self.status=status;self.latest_revision=latest_revision
