"""Bounded extraction recovery from immutable OCR; never overwrites a reviewed record."""
from fastapi import APIRouter, Request
from pydantic import Field, StrictInt
from ..domain.base import Contract, Identifier
from ..ingestion.auth import authenticate
from ..review.repository import ReviewRepository, envelope
from ..review.contracts import ReviewError

router = APIRouter(prefix='/v1')
from .regions import RegionCommand, RegionRecovery
from .automation import AutomationReview,AutoCommand


@router.get('/records/{record_id}/automation-review')
def inspect_automation(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    ctx=authenticate(request.app.state.settings,request.headers.get('authorization'))
    record,plan,key,latest=AutomationReview(request.app.state.settings).inspect(ctx,taxpayer_id,record_id)
    from ..explanation_v2.guide import build_guide
    return envelope(record_id=record_id,record_revision=record.revision,plan=plan,plan_key=key,latest=latest,user_guide=build_guide(record).model_dump(mode='json'))


@router.post('/records/{record_id}/automation-review')
def run_automation(request:Request,record_id:Identifier,taxpayer_id:Identifier,command:AutoCommand):
    ctx=authenticate(request.app.state.settings,request.headers.get('authorization'))
    return AutomationReview(request.app.state.settings).run(ctx,taxpayer_id,record_id,command)


@router.post('/records/{record_id}/reread-region')
def reread_region(request:Request,record_id:Identifier,taxpayer_id:Identifier,command:RegionCommand):
    ctx=authenticate(request.app.state.settings,request.headers.get('authorization'))
    return RegionRecovery(request.app.state.settings).read(ctx,taxpayer_id,record_id,command)


class ReextractCommand(Contract):
    expected_record_revision: StrictInt = Field(ge=1)
    reason: str = Field(min_length=3,max_length=512)


def reextract(settings,ctx,payer,record_id,command):
    ctx.require(ctx.tenant_id,payer,'WRITE')
    repo=ReviewRepository(settings)
    record,old,_=repo.head_context(ctx,payer,record_id)
    if record.revision!=command.expected_record_revision:
        raise ReviewError('REVISION_CONFLICT','Hóa đơn đã đổi. Tải lại trước khi trích xuất lại.',409,record.revision)
    with repo.ingestion.db() as db:
        row=db.execute('SELECT ocr_config_key FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',
                       (ctx.tenant_id,payer,old.artifact_id)).fetchone()
    # The extraction cache binds immutable OCR, profile, taxpayer master and
    # implementation hash. Repeating this request cannot allocate more records.
    new=repo.extraction.work(ctx,payer,old.ingestion_id,row['ocr_config_key'],old.profile)
    if new.artifact_id==old.artifact_id:
        return envelope(status='NO_CHANGE',record_id=record_id,record_revision=record.revision,
                        previous_record_id=record_id,previous_revision=record.revision,
                        extraction_artifact_id=old.artifact_id,item_count=len(record.items),
                        message='Bộ trích xuất hiện tại đã được dùng. Cần nguồn khác hoặc xử lý riêng.')
    if not new.record:
        return envelope(status='REVIEW_SPLIT',record_id=None,previous_record_id=record_id,
                        previous_revision=record.revision,extraction_artifact_id=new.artifact_id,item_count=0)
    repo.quality.work(ctx,payer,new.artifact_id)
    repo.ensure_tasks(ctx,payer,new.record.record_id)
    # A concurrent review can advance the old record. Never silently replace
    # that revision in the UI; return the actual head so the operator can compare.
    head=repo.base.record(ctx,payer,record_id)
    with repo.ingestion.db() as db:
        repo.ingestion._event(db,ctx,payer,old.ingestion_id,'EXTRACTION_RECOVERY',new.input_sha256,
            {'previous_record_id':record_id,'previous_revision':record.revision,
             'new_record_id':new.record.record_id,'new_artifact_id':new.artifact_id,
             'reason':command.reason})
    return envelope(status='RECOVERED' if new.record.items else 'NEEDS_REVIEW',
                    record_id=new.record.record_id,record_revision=repo.base.record(ctx,payer,new.record.record_id).revision,
                    previous_record_id=record_id,previous_revision=record.revision,
                    previous_current_revision=head.revision,extraction_artifact_id=new.artifact_id,
                    item_count=len(new.record.items),review_required=True)


@router.post('/records/{record_id}/reextract')
def recover(request:Request,record_id:Identifier,taxpayer_id:Identifier,command:ReextractCommand):
    ctx=authenticate(request.app.state.settings,request.headers.get('authorization'))
    return reextract(request.app.state.settings,ctx,taxpayer_id,record_id,command)
