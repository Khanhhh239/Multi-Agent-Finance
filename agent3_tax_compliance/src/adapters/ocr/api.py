from fastapi import APIRouter, Request
from ...domain.base import Identifier
from ...domain.envelope import Sha256
from ...ingestion.auth import authenticate
from ...ingestion.models import IngestionError
from .repository import OCRRepository
from .protocol import OCRJobView

router=APIRouter(prefix='/v1')


@router.get('/ingestions/{ingestion_id}/extractions/{config_key}',response_model=OCRJobView)
def extraction(request:Request,ingestion_id:Identifier,config_key:Sha256,taxpayer_id:Identifier):
    settings=request.app.state.settings
    ctx=authenticate(settings,request.headers.get('authorization'))
    result=OCRRepository(settings).get(ctx,taxpayer_id,ingestion_id,config_key)
    if result is None: raise IngestionError('NOT_FOUND','OCR job not found.',status=404)
    return result
