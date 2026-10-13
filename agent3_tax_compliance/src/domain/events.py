from typing import Annotated, Literal

from pydantic import Field

from .base import Identifier, Stamped
from .envelope import Sha256


class AuditEvent(Stamped):
    event_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    actor_id: Identifier
    record_id: Identifier | None = None
    record_revision: Annotated[int, Field(strict=True, ge=1)] | None = None
    event_type: Literal['TAXPAYER_STORED', 'SOURCE_STORED', 'RECORD_CREATED', 'RECORD_REVISED', 'ARTIFACT_STORED', 'JOB_CREATED']
    input_sha256: Sha256
    reason: str = Field(min_length=1)
