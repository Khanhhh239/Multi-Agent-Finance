from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from pydantic import Field,model_validator
from ..domain.base import Contract,Identifier
from ..domain.envelope import Sha256


class LegalRelationship(Contract):
    target_id: Identifier
    relation: str
    scope: str = Field(min_length=1)
    effective_from: date
    evidence_locator: str = Field(min_length=1)


class LegalDocument(Contract):
    document_id: Identifier
    official_url: str
    pdf_url: str | None = None
    sha256: Sha256 | None = None
    effective_from: date
    effective_to: date | None = None
    source_status: str
    verified_locators: tuple[str,...] = ()
    relationships: tuple[LegalRelationship,...] = ()
    transitional_policy: str
    signature_status: str = 'NOT_VERIFIED'

    @model_validator(mode='after')
    def valid(self):
        host=urlparse(self.official_url).hostname or ''
        if not (host=='chinhphu.vn' or host.endswith('.chinhphu.vn')):raise ValueError('official source required')
        if self.source_status=='PDF_REVIEWED' and (not self.sha256 or not self.verified_locators):
            raise ValueError('reviewed source requires hash and locators')
        if self.effective_to and self.effective_to<=self.effective_from:raise ValueError('invalid legal interval')
        return self


class LegalRegistry(Contract):
    version: Identifier
    checked_on: date
    documents: tuple[LegalDocument,...]

    @model_validator(mode='after')
    def valid(self):
        ids={d.document_id for d in self.documents}
        if len(ids)!=len(self.documents):raise ValueError('duplicate legal document')
        if any(r.target_id not in ids for d in self.documents for r in d.relationships):raise ValueError('dangling relationship')
        return self

    def verified(self,bases):
        docs={d.document_id:d for d in self.documents}
        return all(b.document_id in docs and docs[b.document_id].source_status=='PDF_REVIEWED'
                   and b.locator in docs[b.document_id].verified_locators for b in bases)


def load_registry(path=None):
    path=path or Path(__file__).resolve().parents[2]/'rules/registry/legal_registry_v1.json'
    return LegalRegistry.model_validate_json(Path(path).read_text(encoding='utf-8'))
