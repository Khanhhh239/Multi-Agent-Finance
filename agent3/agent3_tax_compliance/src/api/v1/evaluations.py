from typing import Annotated
from fastapi import APIRouter,Request,Header,Query
from ...domain.base import Identifier
from ...ingestion.auth import authenticate
from ...persistence.repository import RevisionConflict
from ...review.contracts import ReviewError
from ...orchestration.workflow import Workflow
from ...orchestration.contracts import EvaluationCommand,EvaluationState

router=APIRouter(prefix='/v1')


def resources(request):
    return Workflow(request.app.state.settings),authenticate(request.app.state.settings,request.headers.get('authorization'))


@router.post('/records/{record_id}/evaluations',response_model=EvaluationState)
def create(request:Request,record_id:Identifier,taxpayer_id:Identifier,command:EvaluationCommand,
           idempotency_key:Annotated[Identifier,Header(alias='Idempotency-Key')]):
    workflow,ctx=resources(request)
    try:return workflow.work(ctx,taxpayer_id,record_id,command,idempotency_key)
    except RevisionConflict:raise ReviewError('EVALUATION_RUNNING','An evaluation or rule execution is already running; retry after its lease is released.',409) from None


@router.get('/records/{record_id}/evaluations')
def latest(request:Request,record_id:Identifier,taxpayer_id:Identifier,revision:int=Query(ge=1)):
    workflow,ctx=resources(request)
    return dict(items=workflow.latest(ctx,taxpayer_id,record_id,revision),revision=revision)


@router.get('/evaluations/{evaluation_id}',response_model=EvaluationState)
def get(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier):
    workflow,ctx=resources(request)
    return workflow.get(ctx,taxpayer_id,evaluation_id)


@router.post('/evaluations/{evaluation_id}/replay')
def replay(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier):
    workflow,ctx=resources(request)
    ctx.require(ctx.tenant_id,taxpayer_id,'WRITE')
    return workflow.replay(ctx,taxpayer_id,evaluation_id)


@router.post('/evaluations/{evaluation_id}/resume',response_model=EvaluationState)
def resume(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier):
    workflow,ctx=resources(request)
    try:return workflow.resume(ctx,taxpayer_id,evaluation_id)
    except RevisionConflict:raise ReviewError('EVALUATION_RUNNING','Wait for the active execution lease before resuming.',409) from None


@router.get('/evaluations/{evaluation_id}/export')
def export(request:Request,evaluation_id:Identifier,taxpayer_id:Identifier):
    workflow,ctx=resources(request)
    state=workflow.get(ctx,taxpayer_id,evaluation_id)
    artifact=workflow.artifact(ctx,taxpayer_id,evaluation_id)
    record=workflow.base.record(ctx,taxpayer_id,state.record_id,state.record_revision)
    return dict(schema_version='1.0.0',record=record,report=artifact.report,rule_results=artifact.rule_results,
        is_current_revision=state.is_current_revision,latest_record_revision=state.latest_record_revision)
