from fastapi import APIRouter,Request,Query
from ..domain.base import Identifier
from ..ingestion.auth import authenticate
from .contracts import RulePlan
from .repository import PlanningRepository

router=APIRouter(prefix='/v1')


@router.post('/records/{record_id}/rule-plans',response_model=RulePlan)
def create(request:Request,record_id:Identifier,taxpayer_id:Identifier,revision:int=Query(ge=1)):
    settings=request.app.state.settings;ctx=authenticate(settings,request.headers.get('authorization'))
    return PlanningRepository(settings).work(ctx,taxpayer_id,record_id,revision)


@router.get('/rule-plans/{evaluation_id}',response_model=RulePlan)
def get(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier):
    settings=request.app.state.settings;ctx=authenticate(settings,request.headers.get('authorization'))
    return PlanningRepository(settings).get(ctx,taxpayer_id,evaluation_id)
