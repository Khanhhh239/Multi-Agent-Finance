from pathlib import Path
from typing import Annotated,Literal
from fastapi import APIRouter,Request,Header,Query,Path as PathParam
from fastapi.responses import FileResponse,Response
from pydantic import Field
from ..domain.base import Contract,Identifier
from ..ingestion.auth import authenticate
from ..jobs.service import CaptureJobs
from .repository import ReviewRepository,envelope
from .correction_service import CorrectionService
from .contracts import CorrectionCommand,ReviewError,TaskAction,CorrectionResult,TaskPage

router=APIRouter()
STATIC=Path(__file__).with_name('static')

def context(request): return authenticate(request.app.state.settings,request.headers.get('authorization'))
def repository(request): return ReviewRepository(request.app.state.settings)

@router.get('/review',include_in_schema=False)
def client(): return FileResponse(STATIC/'index.html',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'"})

@router.get('/review-assets/{name}',include_in_schema=False)
def asset(name:str):
    if name not in ('app.js','style.css','compliance.js','compliance.css','explanation.js','business.js','business.css','workflow.js','workflow.css','automation.js','region.js'): raise ReviewError('NOT_FOUND','Asset not found.',404)
    return FileResponse(STATIC/name)

@router.get('/v1/records')
def records(request:Request,taxpayer_id:Identifier,cursor:str|None=None,limit:Annotated[int,Query(ge=1,le=100)]=25):
    return repository(request).page(context(request),taxpayer_id,'records',cursor=cursor,limit=limit)

@router.get('/v1/records/{record_id}')
def record(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    return repository(request).view(context(request),taxpayer_id,record_id)

@router.get('/v1/records/{record_id}/revisions')
def revisions(request:Request,record_id:Identifier,taxpayer_id:Identifier,cursor:str|None=None,limit:Annotated[int,Query(ge=1,le=100)]=25):
    repo=repository(request);ctx=context(request);repo.base.record(ctx,taxpayer_id,record_id)
    return repo.page(ctx,taxpayer_id,'revisions',record_id=record_id,cursor=cursor,limit=limit)

@router.get('/v1/records/{record_id}/audit')
def audit(request:Request,record_id:Identifier,taxpayer_id:Identifier,cursor:str|None=None,limit:Annotated[int,Query(ge=1,le=100)]=25):
    repo=repository(request);ctx=context(request);repo.base.record(ctx,taxpayer_id,record_id)
    return repo.page(ctx,taxpayer_id,'audit',record_id=record_id,cursor=cursor,limit=limit)

@router.get('/v1/records/{record_id}/revisions/{revision}')
def revision_content(request:Request,record_id:Identifier,revision:Annotated[int,PathParam(ge=1)],taxpayer_id:Identifier):
    repo=repository(request);record=repo.base.record(context(request),taxpayer_id,record_id,revision)
    return envelope(record=record.model_dump(mode='json'),immutable=True)

@router.post('/v1/records/{record_id}/audit-replay')
def replay(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    return repository(request).rebuild(context(request),taxpayer_id,record_id)

@router.get('/v1/records/{record_id}/export')
def export(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    return repository(request).export(context(request),taxpayer_id,record_id)

@router.post('/v1/records/{record_id}/review-tasks')
def build(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    return repository(request).ensure_tasks(context(request),taxpayer_id,record_id)

@router.get('/v1/review-tasks',response_model=TaskPage)
def tasks(request:Request,taxpayer_id:Identifier,record_id:Identifier|None=None,status:str|None=None,revision:Annotated[int|None,Query(ge=1)]=None,cursor:str|None=None,limit:Annotated[int,Query(ge=1,le=100)]=25):
    return repository(request).page(context(request),taxpayer_id,'tasks',record_id=record_id,status=status,revision=revision,cursor=cursor,limit=limit)

@router.post('/v1/review-tasks/{task_id}/actions')
def task_action(request:Request,task_id:Identifier,taxpayer_id:Identifier,command:TaskAction):
    return repository(request).task_action(context(request),taxpayer_id,task_id,command)

@router.post('/v1/corrections',response_model=CorrectionResult)
def correct(request:Request,taxpayer_id:Identifier,command:CorrectionCommand,
            idempotency_key:Annotated[Identifier,Header(alias='Idempotency-Key')]):
    return CorrectionService(request.app.state.settings).correct(context(request),taxpayer_id,command,idempotency_key)

@router.post('/v1/cfr-extractions/{artifact_id}/evidence-grants')
def evidence_grant(request:Request,artifact_id:Identifier,taxpayer_id:Identifier,page_index:Annotated[int,Query(ge=0)],ttl:Annotated[int,Query(ge=1,le=300)]=120):
    return repository(request).grant(context(request),taxpayer_id,artifact_id,page_index,ttl)

class EvidenceToken(Contract):
    token: str=Field(min_length=1,max_length=4096)

@router.post('/v1/evidence-image')
def evidence_image(request:Request,taxpayer_id:Identifier,command:EvidenceToken):
    return Response(repository(request).redeem(context(request),taxpayer_id,command.token),media_type='image/png',
        headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.post('/v1/capture-jobs',status_code=202)
def enqueue(request:Request,taxpayer_id:Identifier,ingestion_id:Identifier):
    return CaptureJobs(request.app.state.settings).enqueue(context(request),taxpayer_id,ingestion_id)

@router.get('/v1/jobs/{job_id}')
def job(request:Request,taxpayer_id:Identifier,job_id:Identifier):
    return CaptureJobs(request.app.state.settings).get(context(request),taxpayer_id,job_id)

class Recovery(Contract):
    action: Literal['RETRY','REQUEST_DATA','OPERATOR']
    reason: str=Field(min_length=1,max_length=2000)

@router.post('/v1/jobs/{job_id}/recover')
def recover(request:Request,taxpayer_id:Identifier,job_id:Identifier,command:Recovery):
    return CaptureJobs(request.app.state.settings).recover(context(request),taxpayer_id,job_id,command.action,command.reason)

@router.post('/v1/jobs/{job_id}/complete')
def complete(request:Request,taxpayer_id:Identifier,job_id:Identifier):
    jobs=CaptureJobs(request.app.state.settings);ctx=context(request);ctx.require(ctx.tenant_id,taxpayer_id,'WRITE')
    job=jobs.get(ctx,taxpayer_id,job_id)
    if not job.get('record_id'): raise ReviewError('REVIEW_SPLIT','Document boundaries need operator review.',409)
    record,artifact,q=jobs.head_context(ctx,taxpayer_id,job['record_id'])
    with jobs.ingestion.db() as db:
        db.execute('BEGIN IMMEDIATE');row=jobs.row(db,ctx,taxpayer_id,job_id)
        head=db.execute('SELECT head FROM records WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',(ctx.tenant_id,taxpayer_id,record.record_id)).fetchone()[0]
        pending=db.execute("SELECT 1 FROM review_tasks WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=? AND status IN ('OPEN','WAITING_DATA','OPERATOR')",(ctx.tenant_id,taxpayer_id,record.record_id,head)).fetchone()
        if head!=record.revision or pending or any(i.severity!='INFO' for i in q.issues):
            raise ReviewError('REVIEW_PENDING','Resolve current issues before completing manual capture.',409,head)
        from ..jobs.state import validate_transition
        validate_transition(row['state'],'COMPLETED')
        db.execute("UPDATE capture_jobs SET state='COMPLETED' WHERE tenant_id=? AND taxpayer_id=? AND job_id=?",(ctx.tenant_id,taxpayer_id,job_id))
        jobs.ingestion._event(db,ctx,taxpayer_id,artifact.ingestion_id,'CAPTURE_MANUALLY_COMPLETED',q.input_sha256,{'job_id':job_id,'record_revision':head})
    return jobs.get(ctx,taxpayer_id,job_id)
