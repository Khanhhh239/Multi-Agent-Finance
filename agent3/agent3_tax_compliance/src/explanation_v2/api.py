from typing import Annotated
from fastapi import APIRouter, Header, Request
from pydantic import Field, StrictInt
from ..domain.base import Contract, Identifier
from ..ingestion.auth import authenticate
from .contracts import ExplanationArtifact
from .service import ExplanationService, load_config, implementation_sha
from ..canonicalization.derive import sha

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
    item=service.latest(ctx,taxpayer_id,evaluation_id)
    policy,corpus=load_config()
    cache_valid=bool(item and item.config_sha256==sha(policy.model_dump(mode='json'))
                     and item.corpus_sha256==sha(corpus.model_dump(mode='json'))
                     and item.implementation_sha256==implementation_sha())
    if item and item.mode=='TEMPLATE' and (str(item.fallback_reason).startswith('PROVIDER_')
            or item.fallback_reason in ('CLAIM_VALIDATION_FAILED','MODEL_MANIFEST_UNAVAILABLE','OUTPUT_TRUNCATED')):
        cache_valid=False
    return dict(explanation=item,cache_valid=cache_valid,is_current_revision=state.is_current_revision,
                latest_record_revision=state.latest_record_revision)
