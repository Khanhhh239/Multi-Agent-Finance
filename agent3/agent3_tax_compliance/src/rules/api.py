from fastapi import APIRouter, Request, Query, HTTPException
from ..domain.base import Identifier
from ..ingestion.auth import authenticate
from ..persistence.repository import RevisionConflict
from .contracts import ComplianceResult
from .repository import ExecutionRepository

router=APIRouter(prefix='/v1')


@router.post('/rule-plans/{evaluation_id}/executions',response_model=ComplianceResult)
def create(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier):
    settings=request.app.state.settings
    ctx=authenticate(settings,request.headers.get('authorization'))
    try:
        return ExecutionRepository(settings).work(ctx,taxpayer_id,evaluation_id)
    except RevisionConflict:
        raise HTTPException(status_code=409,detail={'code':'EXECUTION_RUNNING','next_action':'Retry after the current run completes.'}) from None


@router.get('/rule-executions/{execution_id}',response_model=ComplianceResult)
def get(request:Request,execution_id:Identifier,taxpayer_id:Identifier):
    settings=request.app.state.settings
    ctx=authenticate(settings,request.headers.get('authorization'))
    return ExecutionRepository(settings).get(ctx,taxpayer_id,execution_id)


@router.get('/rule-executions/{execution_id}/attempts')
def attempts(request:Request,execution_id:Identifier,taxpayer_id:Identifier,offset:int=Query(default=0,ge=0),limit:int=Query(default=50,ge=1,le=200)):
    settings=request.app.state.settings
    ctx=authenticate(settings,request.headers.get('authorization'))
    rows=ExecutionRepository(settings).attempts(ctx,taxpayer_id,execution_id)
    return dict(total=len(rows),offset=offset,limit=limit,items=rows[offset:offset+limit])
