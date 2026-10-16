from datetime import date, datetime
from typing import Literal
from pydantic import Field, StrictBool, field_validator, model_validator
from ..domain.base import Contract, Identifier
from ..domain.envelope import Sha256
from ..domain.money import ExactDecimal
from ..domain.cfr import TaxCode
from ..planning.contracts import DailyPurchases


class DocumentProof(Contract):
    evidence_id: Identifier
    relative_path: str = Field(min_length=1, max_length=512)
    sha256: Sha256
    kind: Literal['INVOICE','PRODUCT_CATALOGUE','CONTRACT','BANK_STATEMENT','CASH_RECEIPT','OTHER']


class InvoiceReview(Contract):
    invoice_kind: Literal['VAT','SALE','OTHER']
    form: Literal['ORDINARY','SPECIAL','UNKNOWN']
    vat_method: Literal['DEDUCTION','DIRECT'] | None = None
    claim_input_vat: StrictBool | None = None
    seller_tax_id_observed: Literal['PRESENT_VALUE','CONFIRMED_ABSENT','UNKNOWN'] = 'UNKNOWN'
    document_complete: StrictBool = False
    evidence_ids: tuple[Identifier,...] = Field(min_length=1)


class ProductReview(Contract):
    """Record-specific classification; printed VAT is deliberately not a classification input."""
    item_id: Identifier
    product_code: str = Field(min_length=1, max_length=256)
    effective_from: date
    effective_to: date
    base_vat_rate: ExactDecimal = Field(ge=0, le=1)
    annex_i: Literal['EXCLUDED','NOT_EXCLUDED','UNKNOWN']
    annex_ii: Literal['EXCLUDED','NOT_EXCLUDED','UNKNOWN']
    legal_context_checked: StrictBool = False
    classification_rationale: str = Field(min_length=20, max_length=4000)
    evidence_ids: tuple[Identifier,...] = Field(min_length=1)

    @model_validator(mode='after')
    def interval(self):
        if self.effective_to<=self.effective_from:raise ValueError('exclusive interval required')
        # Annex II changes on this boundary: one review cannot silently span both versions.
        if self.effective_from<date(2026,1,1)<self.effective_to:
            raise ValueError('split product review at Annex II year boundary')
        return self


class PaymentReview(Contract):
    case: Literal['STANDARD','SPECIAL','UNKNOWN']
    settlement: Literal['VERIFIED_NON_CASH','VERIFIED_CASH','UNSETTLED','UNKNOWN'] = 'UNKNOWN'
    method: Literal['BANK_TRANSFER','CARD','CASH','CASH_DEPOSIT_TO_SELLER','UNKNOWN'] = 'UNKNOWN'
    seller_tax_id: TaxCode
    buyer_tax_id: TaxCode
    currency: Literal['VND'] = 'VND'
    amount: ExactDecimal = Field(ge=0)
    execution_confirmed: StrictBool = False
    full_settlement: StrictBool = False
    evidence_ids: tuple[Identifier,...] = Field(min_length=1)


class DailyReview(Contract):
    ledger: DailyPurchases
    evidence_ids: tuple[Identifier,...] = Field(min_length=1)


class ReviewDossier(Contract):
    schema_version: Literal['business-review-v1'] = 'business-review-v1'
    review_id: Identifier
    tenant_id: Identifier
    taxpayer_id: Identifier
    record_id: Identifier
    record_revision: int = Field(strict=True, ge=1)
    record_sha256: Sha256
    reviewer_id: Identifier
    reviewed_at: datetime
    review_reference: str = Field(min_length=1, max_length=512)
    documents: tuple[DocumentProof,...] = Field(min_length=1, max_length=100)
    invoice: InvoiceReview | None = None
    products: tuple[ProductReview,...] = Field(default=(), max_length=1000)
    payment: PaymentReview | None = None
    daily: DailyReview | None = None

    @field_validator('reviewed_at')
    @classmethod
    def aware(cls,value):
        if value.utcoffset() is None:raise ValueError('timezone required')
        return value

    @model_validator(mode='after')
    def refs(self):
        ids={d.evidence_id for d in self.documents}
        if len(ids)!=len(self.documents):raise ValueError('duplicate evidence')
        if len({p.item_id for p in self.products})!=len(self.products):raise ValueError('duplicate product review')
        for part in (self.invoice,self.payment,self.daily,*self.products):
            if part and (len(set(part.evidence_ids))!=len(part.evidence_ids) or not set(part.evidence_ids)<=ids):
                raise ValueError('unknown or duplicate evidence reference')
        return self
