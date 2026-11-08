from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, validate_default=True)


class Stamped(Contract):
    schema_version: Literal['1.0.0'] = '1.0.0'
    config_version: Identifier
    creator: Identifier
    stage: Identifier
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator('created_at')
    @classmethod
    def aware_timestamp(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('timestamp must include timezone')
        return value
