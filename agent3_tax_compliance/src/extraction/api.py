from fastapi import APIRouter,Request
from ..domain.base import Identifier
from ..ingestion.auth import authenticate
from ..ingestion.models import IngestionError
from .repository import ExtractionRepository
from .contracts import ExtractionArtifact
from .evidence import resolve

router=APIRouter(prefix='/v1')

@router.get('/cfr-extractions/{artifact_id}',response_model=ExtractionArtifact)
def artifact(request:Request,artifact_id:Identifier,taxpayer_id:Identifier):
    settings=request.app.state.settings;ctx=authenticate(settings,request.headers.get('authorization'))
    try: return ExtractionRepository(settings).get(ctx,taxpayer_id,artifact_id)
    except KeyError: raise IngestionError('NOT_FOUND','Extraction not found.',status=404)

@router.get('/cfr-extractions/{artifact_id}/evidence/{candidate_id}')
def evidence(request:Request,artifact_id:Identifier,candidate_id:Identifier,taxpayer_id:Identifier):
    settings=request.app.state.settings;ctx=authenticate(settings,request.headers.get('authorization'))
    repo=ExtractionRepository(settings)
    try:
        result=repo.get(ctx,taxpayer_id,artifact_id)
        with repo.ingestion.db() as db:
            row=db.execute('SELECT ocr_config_key FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',
                (ctx.tenant_id,taxpayer_id,artifact_id)).fetchone()
        normalized=repo.ocr.get(ctx,taxpayer_id,result.ingestion_id,row['ocr_config_key'])['result']
        document=repo.ingestion.document(ctx,taxpayer_id,result.ingestion_id)
        return resolve(result,candidate_id,normalized,document)
    except KeyError: raise IngestionError('NOT_FOUND','Evidence not found.',status=404)
