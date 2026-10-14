import json
import sys
import tempfile
import importlib.metadata
from pathlib import Path
from ..ingestion.sandbox import run_bounded
from ..ingestion.models import IngestionError
from .models import validate_model
from .trace import parse_response

APP = Path(__file__).resolve().parents[2]


class EngineFailure(Exception):
    def __init__(self, code, retryable=False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def evaluate(model, context, policy):
    validate_model(model)
    if model.publication != 'APPROVED_TECHNICAL' or context.planning_eligibility != 'ELIGIBLE':
        raise EngineFailure('EXECUTION_NOT_APPROVED_OR_ELIGIBLE')
    if context.model_sha256 != model.jdm_sha256:
        raise EngineFailure('MODEL_CONTEXT_MISMATCH')
    try:
        if importlib.metadata.version('zen-engine') != '0.53.0':
            raise EngineFailure('ENGINE_VERSION_MISMATCH')
    except importlib.metadata.PackageNotFoundError:
        raise EngineFailure('ENGINE_UNAVAILABLE') from None
    with tempfile.TemporaryDirectory(prefix='agent3-zen-') as directory:
        output = Path(directory) / 'result.json'
        payload = json.dumps(dict(facts=context.facts(), jdm_json=model.jdm_json,
            output_path=str(output), max_response_bytes=policy.max_response_bytes)).encode()
        try:
            run_bounded([sys.executable, '-m', 'src.rules.worker'], payload, policy.timeout_seconds,
                        policy.memory_mb, APP, max_processes=2)
        except IngestionError as exc:
            code = 'ENGINE_TIMEOUT' if exc.issue.code == 'WORKER_TIMEOUT' else 'ENGINE_WORKER_ERROR'
            raise EngineFailure(code, retryable=code == 'ENGINE_TIMEOUT') from None
        if not output.is_file() or output.stat().st_size > policy.max_response_bytes:
            raise EngineFailure('ENGINE_RESPONSE_LIMIT_OR_MISSING')
        raw = output.read_text(encoding='utf-8')
    try:
        return parse_response(raw, model, context)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise EngineFailure('ENGINE_RESPONSE_CONTRACT_ERROR') from None
