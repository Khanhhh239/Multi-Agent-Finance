from fastapi import APIRouter,Request,Query
from ...domain.base import Identifier
from .evaluations import resources

router=APIRouter(prefix='/v1')


@router.get('/evaluations/{evaluation_id}/rule-results')
def results(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier,cursor:str|None=Query(default=None,max_length=4096),limit:int=Query(default=25,ge=1,le=100)):
    workflow,ctx=resources(request)
    return workflow.page(ctx,taxpayer_id,evaluation_id,'rules',cursor,limit)


@router.get('/evaluations/{evaluation_id}/attempts')
def attempts(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier,cursor:str|None=Query(default=None,max_length=4096),limit:int=Query(default=25,ge=1,le=100)):
    workflow,ctx=resources(request)
    return workflow.page(ctx,taxpayer_id,evaluation_id,'attempts',cursor,limit)


@router.get('/evaluations/{evaluation_id}/rule-results/{result_id}')
def detail(request:Request,evaluation_id:Identifier,result_id:Identifier,taxpayer_id:Identifier):
    workflow,ctx=resources(request)
    artifact=workflow.artifact(ctx,taxpayer_id,evaluation_id)
    row=next((r for r in artifact.rule_results if r.result_id==result_id),None)
    if row is None:raise KeyError('Rule unit not found in evaluation')
    return row
