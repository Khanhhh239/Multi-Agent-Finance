"""Plain data records shared by the assistant pipeline. Money is always Decimal."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BankTxn:
    txn_id: str             # stable id: source file + row number
    booked: date
    amount: Decimal         # positive number
    direction: str          # OUT (money leaves the company) | IN
    counterparty_account: str | None
    counterparty_name: str | None
    description: str
    source: str             # file:row, for the reviewer


@dataclass
class InvoiceFact:
    key: str                # seller tax id | template+symbol | number without leading zeros
    file: str
    role: str               # PURCHASE (we are buyer) | SALE (we are seller)
    seller_tax_id: str | None
    seller_name: str | None
    seller_account: str | None
    buyer_tax_id: str | None
    buyer_name: str | None
    buyer_address: str | None
    template: str | None
    symbol: str | None
    number: str | None
    issue_date: date | None
    currency: str | None
    net: Decimal | None
    vat: Decimal | None
    gross: Decimal | None
    payment_label: str | None
    descriptions: tuple[str, ...]
    guard_errors: tuple[str, ...]           # XML_CHECK_* codes with status ERROR
    signed: bool                            # seller signature verified
    related: dict | None = None             # replacement / adjustment reference
    duplicate_of: str | None = None         # file of the first copy, when this file repeats an invoice

    @property
    def display(self) -> str:
        return f'{(self.template or "")}{self.symbol or ""}/{self.number or "?"}'


@dataclass(frozen=True)
class Match:
    invoice_keys: tuple[str, ...]
    txn_ids: tuple[str, ...]
    status: str             # MATCHED | AMBIGUOUS
    method: str             # ACCOUNT | NAME_OR_TAX_ID | INVOICE_NUMBER | SPLIT_PAYMENTS | COMBINED_PAYMENT | AMOUNT_ONLY | DECISION
    note: str = ''


@dataclass
class RiskItem:
    code: str
    status: str             # AT_RISK | REVIEW | INFO | OPPORTUNITY
    title: str
    invoice_keys: tuple[str, ...]
    amount: Decimal         # VAT at risk (AT_RISK, REVIEW) or VAT possibly unclaimed (OPPORTUNITY); 0 when not money
    basis: tuple[str, ...]
    action: str
    detail: str = ''
    evidence: tuple[str, ...] = ()


@dataclass
class Report:
    meta: dict
    invoices: list[InvoiceFact]
    transactions: list[BankTxn]
    matches: list[Match]
    items: list[RiskItem]
    totals: dict
    calendar: list[dict] = field(default_factory=list)
    policy_flags: list[RiskItem] = field(default_factory=list)
