from fastapi import APIRouter,Request
from ..domain.base import Identifier
from ..ingestion.auth import authenticate
from ..ingestion.models import IngestionError
from .repository import QualityRepository
from .contracts import QualityAssessment
router=APIRouter(prefix='/v1')

@router.get('/quality-assessments/{assessment_id}',response_model=QualityAssessment)
def assessment(request:Request,assessment_id:Identifier,taxpayer_id:Identifier):
    settings=request.app.state.settings;ctx=authenticate(settings,request.headers.get('authorization'))
    try: return QualityRepository(settings).get(ctx,taxpayer_id,assessment_id)
    except KeyError: raise IngestionError('NOT_FOUND','Quality assessment not found.',status=404)
