from datetime import date
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from .base import Contract, Identifier, Stamped
from .envelope import SourceFormat
from .field import FieldObject
from .money import ExactDecimal

TaxCode = Annotated[str, Field(pattern=r'^[0-9]{10}(?:[0-9]{3}|-[0-9]{3})?$')]
Currency = Annotated[str, Field(pattern=r'^[A-Z]{3}$')]


def parse_date(value):
    if type(value) is date:
        return value
    if isinstance(value, str) and len(value) == 10:
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ValueError('date requires YYYY-MM-DD or date; numeric epochs/localized dates are not accepted')


ISODate = Annotated[date, BeforeValidator(parse_date)]


class Party(Contract):
    name: FieldObject[str] | None = None
    tax_id: FieldObject[TaxCode] | None = None
    address: FieldObject[str] | None = None


class Parties(Contract):
    seller: Party | None = None
    buyer: Party | None = None


class Invoice(Contract):
    number: FieldObject[str] | None = None
    series: FieldObject[str] | None = None
    issue_date: FieldObject[ISODate] | None = None


class Totals(Contract):
    net: FieldObject[ExactDecimal] | None = None
    vat: FieldObject[ExactDecimal] | None = None
    gross: FieldObject[ExactDecimal] | None = None


class Item(Contract):
    item_id: Identifier
    line_number: Annotated[int, Field(strict=True, ge=1)]
    description: FieldObject[str] | None = None
    quantity: FieldObject[ExactDecimal] | None = None
    unit_price: FieldObject[ExactDecimal] | None = None
    net: FieldObject[ExactDecimal] | None = None
    vat_treatment: FieldObject[Literal['TAXABLE_RATE', 'KCT', 'KKKNT']] | None = None
    vat_rate: FieldObject[ExactDecimal] | None = None

    @model_validator(mode='after')
    def vat_semantics(self):
        treatment = self.vat_treatment.value if self.vat_treatment else None
        rate = self.vat_rate.value if self.vat_rate else None
        if treatment in ('KCT', 'KKKNT') and rate is not None:
            raise ValueError('KCT/KKKNT cannot carry a taxable rate')
        if rate is not None and not 0 <= rate <= 1:
            raise ValueError('VAT rate must be within [0,1]')
        return self


class BankTransaction(Contract):
    account_owner: Party
    counterparty: Party | None = None
    amount: FieldObject[ExactDecimal]
    booking_date: FieldObject[ISODate] | None = None
    reference: FieldObject[str] | None = None


class Derived(Contract):
    invoice_direction: FieldObject[Literal['INPUT', 'OUTPUT']]
    counterparty: Party | None = None
    totals: Totals = Field(default_factory=Totals)


class CanonicalFinancialRecord(Stamped):
    record_id: Identifier
    revision: Annotated[int, Field(strict=True, ge=1)]
    tenant_id: Identifier
    taxpayer_id: Identifier
    taxpayer_master_revision: Annotated[int, Field(strict=True, ge=1)]
    source_id: Identifier
    source_format: SourceFormat
    record_type: Literal['INVOICE', 'RECEIPT', 'BANK_TRANSACTION']
    document_id: Identifier
    parties: Parties
    invoice: Invoice | None = None
    currency: FieldObject[Currency] | None = None
    totals: Totals = Field(default_factory=Totals)
    items: tuple[Item, ...] = ()
    item_discovery_status: Literal['COMPLETE', 'INCOMPLETE', 'UNKNOWN'] = 'UNKNOWN'
    bank_transaction: BankTransaction | None = None
    derived: Derived

    @model_validator(mode='after')
    def shape(self):
        if self.record_type == 'BANK_TRANSACTION':
            if self.bank_transaction is None or self.invoice is not None or self.items:
                raise ValueError('bank records require bank_transaction, no invoice/items')
            if self.parties.seller is not None or self.parties.buyer is not None:
                raise ValueError('bank uses account_owner/counterparty, not seller/buyer')
            if self.derived.invoice_direction.value is not None:
                raise ValueError('bank has no invoice direction')
        elif self.bank_transaction is not None or self.parties.seller is None or self.parties.buyer is None:
            raise ValueError('invoice/receipt requires seller and buyer objects (may be partial)')
        ids = [item.item_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError('item IDs must be unique')
        return self
