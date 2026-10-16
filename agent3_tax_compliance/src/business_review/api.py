from fastapi import APIRouter,Request
from ..domain.base import Identifier
from ..ingestion.auth import authenticate
from .repository import BusinessReviewRepository

router=APIRouter(prefix='/v1')


@router.get('/records/{record_id}/business-readiness')
def readiness(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    ctx=authenticate(request.app.state.settings,request.headers.get('authorization'))
    return BusinessReviewRepository(request.app.state.settings).assess(ctx,taxpayer_id,record_id)
