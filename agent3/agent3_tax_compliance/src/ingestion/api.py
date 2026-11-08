from typing import Annotated

from fastapi import APIRouter, Header, Path as PathParam, Query, Request
from fastapi.responses import Response

from ..domain.base import Identifier
from .auth import authenticate
from .models import DocumentArtifact, IngestionError, IngestionView
from .service import IngestionService
from .upload import StagedUpload

router=APIRouter(prefix='/v1')


def service_and_context(request):
    settings=request.app.state.settings
    return IngestionService(settings),authenticate(settings,request.headers.get('authorization'))


@router.post('/ingestions',response_model=IngestionView,status_code=202)
async def upload(request:Request,taxpayer_id:Identifier,master_revision:Annotated[int,Query(ge=1)],
                 idempotency_key:Annotated[Identifier,Header(alias='Idempotency-Key')],
                 filename:Annotated[str|None,Header(alias='X-Filename')]=None):
    from starlette.concurrency import run_in_threadpool
    import asyncio
    from time import monotonic
    service,ctx=service_and_context(request)
    await run_in_threadpool(service.authorize_upload,ctx,taxpayer_id,master_revision)
    length=request.headers.get('content-length')
    if length is not None:
        try: declared=int(length)
        except ValueError: raise IngestionError('FORMAT_MISMATCH','Invalid content length.',status=400) from None
        if declared<0 or declared>service.settings.max_upload_bytes:
            raise IngestionError('LIMIT_EXCEEDED','Declared upload exceeds byte limit.',status=413)
    with StagedUpload(service.settings) as staged:
        stream=request.stream().__aiter__(); deadline=monotonic()+service.settings.max_upload_seconds
        while True:
            try:
                chunk=await asyncio.wait_for(stream.__anext__(),timeout=max(0,deadline-monotonic()))
            except StopAsyncIteration: break
            except asyncio.TimeoutError:
                raise IngestionError('UPLOAD_TIMEOUT','Upload exceeded its wall-time limit.',retryable=True,status=408,
                                     next_action='Retry the upload on a stable connection.') from None
            await run_in_threadpool(staged.write,chunk)
        return await run_in_threadpool(service.accept_staged,ctx,taxpayer_id,master_revision,idempotency_key,staged,
                                      request.headers.get('content-type','application/octet-stream'),filename)


@router.get('/ingestions/{ingestion_id}',response_model=IngestionView)
def status(request:Request,ingestion_id:Identifier,taxpayer_id:Identifier):
    service,ctx=service_and_context(request)
    return service.repository.get(ctx,taxpayer_id,ingestion_id)


@router.post('/ingestions/{ingestion_id}/retry',response_model=IngestionView,status_code=202)
def retry(request:Request,ingestion_id:Identifier,taxpayer_id:Identifier):
    service,ctx=service_and_context(request)
    return service.repository.retry(ctx,taxpayer_id,ingestion_id)


@router.get('/ingestions/{ingestion_id}/document',response_model=DocumentArtifact)
def document(request:Request,ingestion_id:Identifier,taxpayer_id:Identifier):
    service,ctx=service_and_context(request)
    return service.repository.document(ctx,taxpayer_id,ingestion_id)


@router.get('/ingestions/{ingestion_id}/pages/{page_index}/image')
def page_image(request:Request,ingestion_id:Identifier,page_index:Annotated[int,PathParam(ge=0)],taxpayer_id:Identifier):
    service,ctx=service_and_context(request)
    if page_index<0: raise IngestionError('NOT_FOUND','Page index is invalid.',status=404)
    return Response(service.repository.render(ctx,taxpayer_id,ingestion_id,page_index),media_type='image/png',
                    headers={'Cache-Control':'private, no-store'})


@router.get('/sources/{source_id}/raw')
def raw_source(request:Request,source_id:Identifier,taxpayer_id:Identifier):
    service,ctx=service_and_context(request)
    try: envelope,raw=service.repository.base.source(ctx,taxpayer_id,source_id)
    except KeyError: raise IngestionError('NOT_FOUND','Source not found.',status=404) from None
    return Response(raw,media_type='application/octet-stream',headers={
        'Content-Disposition':f'attachment; filename="{source_id}.bin"','Cache-Control':'private, no-store',
        'X-Content-Type-Options':'nosniff'})
