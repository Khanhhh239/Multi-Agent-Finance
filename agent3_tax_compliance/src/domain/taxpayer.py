from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import Contract, Identifier, Stamped
from .cfr import TaxCode


class TaxpayerMaster(Stamped):
    tenant_id: Identifier
    taxpayer_id: Identifier
    revision: Annotated[int, Field(strict=True, ge=1)]
    tax_code: TaxCode
    effective_from: date
    effective_to: date | None = None
    provenance_reference: str = Field(min_length=1)

    @model_validator(mode='after')
    def interval(self):
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError('effective_to must follow effective_from (exclusive)')
        return self


class BranchRelation(Contract):
    tenant_id: Identifier
    parent_tax_code: TaxCode
    branch_tax_code: TaxCode
    effective_from: date
    effective_to: date | None = None
    evidence_reference: str = Field(min_length=1)

    @model_validator(mode='after')
    def interval(self):
        if self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError('invalid relation interval')
        return self


def identity_match(observed: str, master: TaxpayerMaster, on_date: date | None,
                   relations: tuple[BranchRelation, ...] = ()) -> str:
    if on_date is None:
        return 'UNKNOWN'
    if on_date < master.effective_from or (master.effective_to and on_date >= master.effective_to):
        return 'UNKNOWN'
    if observed == master.tax_code:
        return 'MATCH'
    for relation in relations:
        if (relation.tenant_id == master.tenant_id
                and relation.parent_tax_code == master.tax_code
                and relation.branch_tax_code == observed
                and on_date >= relation.effective_from
                and (relation.effective_to is None or on_date < relation.effective_to)):
            return 'MATCH'
    # A prefix is insufficient evidence of a legal identity relationship.
    if observed.replace('-', '')[:10] == master.tax_code.replace('-', '')[:10]:
        return 'UNKNOWN'
    return 'NO_MATCH'


class AccessContext(Contract):
    actor_id: Identifier
    tenant_id: Identifier
    taxpayer_ids: frozenset[Identifier]
    permissions: frozenset[Literal['READ', 'WRITE', 'ADMIN']] = frozenset({'READ'})

    def require(self, tenant_id: str, taxpayer_id: str, action: str = 'READ'):
        if (tenant_id != self.tenant_id or taxpayer_id not in self.taxpayer_ids
                or (action not in self.permissions and 'ADMIN' not in self.permissions)):
            raise PermissionError('access denied')
