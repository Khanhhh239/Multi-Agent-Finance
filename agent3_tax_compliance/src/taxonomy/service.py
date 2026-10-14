from datetime import date
from typing import Literal
from pydantic import Field,model_validator
from ..domain.base import Contract,Identifier
from ..planning.contracts import LegalBasis


class CategoryDefinition(Contract):
    category_id: Identifier
    description: str
    legal_basis: tuple[LegalBasis,...] = Field(min_length=1)


class CategoryMapping(Contract):
    mapping_id: Identifier
    item_code: str
    category_id: Identifier
    effective_from: date
    effective_to: date
    evidence_reference: str = Field(min_length=1)
    review_reference: str = Field(min_length=1)
    evidence_kind: Literal['CATALOGUE','CONTRACT','HUMAN_CLASSIFICATION']


class Taxonomy(Contract):
    version: Identifier
    effective_from: date
    effective_to: date
    categories: tuple[CategoryDefinition,...]
    mappings: tuple[CategoryMapping,...] = ()

    @model_validator(mode='after')
    def valid(self):
        ids={c.category_id for c in self.categories}
        if self.effective_to<=self.effective_from or len(ids)!=len(self.categories):raise ValueError('bad taxonomy')
        if any(m.category_id not in ids or m.effective_to<=m.effective_from for m in self.mappings):raise ValueError('bad category mapping')
        if len({m.mapping_id for m in self.mappings})!=len(self.mappings):raise ValueError('duplicate mapping')
        return self

    def resolve(self,item_code,on_date):
        if on_date is None or not self.effective_from<=on_date<self.effective_to:return None
        found=[m for m in self.mappings if m.item_code==item_code and m.effective_from<=on_date<m.effective_to]
        return found[0] if len(found)==1 else None
