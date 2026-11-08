from typing import Annotated,Literal
from fastapi import APIRouter,Request,Header,Query
from fastapi.responses import Response
from urllib.parse import unquote
from ..domain.base import Identifier
from ..ingestion.auth import authenticate
from .repository import BusinessReviewRepository
from .web import WebReviews,SaveCommand

router=APIRouter(prefix='/v1')


@router.get('/records/{record_id}/business-readiness')
def readiness(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    ctx=authenticate(request.app.state.settings,request.headers.get('authorization'))
    return BusinessReviewRepository(request.app.state.settings).assess(ctx,taxpayer_id,record_id)


def resources(request):
    return WebReviews(request.app.state.settings),authenticate(request.app.state.settings,request.headers.get('authorization'))


@router.get('/records/{record_id}/business-review')
def editor(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    service,ctx=resources(request);return service.editor(ctx,taxpayer_id,record_id)


@router.post('/records/{record_id}/business-reviews')
def save(request:Request,record_id:Identifier,taxpayer_id:Identifier,command:SaveCommand,
         idempotency_key:Annotated[Identifier,Header(alias='Idempotency-Key')]):
    service,ctx=resources(request);return service.save(ctx,taxpayer_id,record_id,command,idempotency_key)


@router.post('/records/{record_id}/business-documents')
async def upload(request:Request,record_id:Identifier,taxpayer_id:Identifier,
                 expected_record_revision:Annotated[int,Query(ge=1)],
                 kind:Literal['PRODUCT_CATALOGUE','CONTRACT','BANK_STATEMENT','CASH_RECEIPT','OTHER'],
                 filename:Annotated[str,Header(alias='X-File-Name',max_length=1024)]='tai-lieu'):
    service,ctx=resources(request)
    ctx.require(ctx.tenant_id,taxpayer_id,'WRITE')
    length=request.headers.get('content-length')
    if length:
        try:size=int(length)
        except ValueError:raise ValueError('invalid content length') from None
        if size<0:raise ValueError('invalid content length')
        if size>request.app.state.settings.max_upload_bytes:
            from ..review.contracts import ReviewError
            raise ReviewError('BUSINESS_DOCUMENT_TOO_LARGE','Tài liệu vượt giới hạn dung lượng.',413)
    class StreamFile:
        def __init__(self):self.filename=unquote(filename);self.stream=request.stream().__aiter__()
        async def read(self,size):
            try:return await self.stream.__anext__()
            except StopAsyncIteration:return b''
    return await service.upload(ctx,taxpayer_id,record_id,expected_record_revision,kind,StreamFile())


@router.get('/records/{record_id}/business-documents/{document_id}')
def download(request:Request,record_id:Identifier,taxpayer_id:Identifier,document_id:Identifier):
    service,ctx=resources(request)
    raw=service.download(ctx,taxpayer_id,record_id,document_id)
    return Response(raw,media_type='application/octet-stream',headers={
        'Content-Disposition':'attachment; filename="'+document_id+'.bin"','X-Content-Type-Options':'nosniff'})


@router.get('/records/{record_id}/business-daily-candidates')
def candidates(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    service,ctx=resources(request);return service.candidates(ctx,taxpayer_id,record_id)
