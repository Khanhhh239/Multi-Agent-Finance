from typing import Annotated, Literal

from pydantic import Field

from .base import Identifier, Stamped
from .envelope import Sha256


class Artifact(Stamped):
    artifact_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    record_revision: Annotated[int, Field(strict=True, ge=1)]
    input_sha256: Sha256
    artifact_kind: Identifier
    content: str


class Job(Stamped):
    job_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    source_id: Identifier
    input_sha256: Sha256
    status: Literal['QUEUED'] = 'QUEUED'
