from typing import Annotated
from fastapi import APIRouter, Header, Request
from pydantic import Field, StrictInt
from ..domain.base import Contract, Identifier
from ..ingestion.auth import authenticate
from .contracts import ExplanationArtifact
from .service import ExplanationService

router = APIRouter(prefix='/v1')


class ExplanationCommand(Contract):
    expected_record_revision: StrictInt = Field(ge=1)


@router.post('/evaluations/{evaluation_id}/explanations', response_model=ExplanationArtifact)
def create(request: Request, evaluation_id: Identifier, taxpayer_id: Identifier, command: ExplanationCommand,
           idempotency_key: Annotated[Identifier, Header(alias='Idempotency-Key')]):
    ctx = authenticate(request.app.state.settings, request.headers.get('authorization'))
    return ExplanationService(request.app.state.settings).create(ctx, taxpayer_id, evaluation_id,
        command.expected_record_revision, idempotency_key)


@router.get('/evaluations/{evaluation_id}/explanations')
def latest(request: Request, evaluation_id: Identifier, taxpayer_id: Identifier):
    ctx = authenticate(request.app.state.settings, request.headers.get('authorization'))
    service = ExplanationService(request.app.state.settings)
    state = service.workflow.get(ctx, taxpayer_id, evaluation_id)
    return dict(explanation=service.latest(ctx, taxpayer_id, evaluation_id), is_current_revision=state.is_current_revision,
                latest_record_revision=state.latest_record_revision)
