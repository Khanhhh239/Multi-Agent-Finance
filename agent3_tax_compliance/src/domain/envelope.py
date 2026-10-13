from enum import Enum
from typing import Annotated

from pydantic import Field

from .base import Identifier, Stamped

Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class SourceFormat(str, Enum):
    PDF = 'PDF'
    IMAGE = 'IMAGE'
    INVOICE_XML = 'INVOICE_XML'
    EXCEL_TABULAR = 'EXCEL_TABULAR'
    EXCEL_GENERIC = 'EXCEL_GENERIC'
    BANK_STATEMENT = 'BANK_STATEMENT'
    ERP_API = 'ERP_API'
    UNKNOWN_XML = 'UNKNOWN_XML'
    UNKNOWN = 'UNKNOWN'


class SourceEnvelope(Stamped):
    tenant_id: Identifier
    taxpayer_id: Identifier
    taxpayer_master_revision: Annotated[int, Field(strict=True, ge=1)]
    request_id: Identifier
    source_id: Identifier
    sha256: Sha256
    size_bytes: Annotated[int, Field(strict=True, gt=0)]
    declared_mime: str
    detected_format: SourceFormat = SourceFormat.UNKNOWN
    adapter_version: Identifier
    profile_version: Identifier
