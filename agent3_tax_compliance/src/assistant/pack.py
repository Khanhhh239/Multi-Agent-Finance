"""Enterprise adaptive pack: data the enterprise creates and keeps. It can only make the core stricter.

Invariants enforced at load time:
  * thresholds may only be tightened relative to the core defaults;
  * internal policies only add flags (they never remove or soften a rule result);
  * reference lists must carry an as-of date, shown on every warning that uses them.
"""
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from ..extraction.xml_invoice import mst_checksum_ok

# Core defaults. "Stricter" direction per key: 'lower' means the pack may only lower the value.
CORE_THRESHOLDS = {
    'match_days_before_invoice': (7, 'lower'),      # prepayment window; a smaller window matches less, flags more
    'match_days_after_invoice': (90, 'lower'),
    'non_cash_threshold_override': (None, 'lower'), # optional, may only be below the legal threshold
    'split_payment_max_parts': (4, 'lower'),
}


class PackError(ValueError):
    pass


@dataclass
class BankFormat:
    name: str
    columns: dict            # date, debit, credit, description, counterparty_account, counterparty_name (header text)
    date_format: str = '%d/%m/%Y'
    thousands: str = '.'
    decimal: str = ','
    delimiter: str = ','
    header_contains: str | None = None   # text that identifies the header row


@dataclass
class Policy:
    policy_id: str
    flag: str
    min_gross: Decimal | None = None
    description_contains: tuple[str, ...] = ()
    seller_tax_ids: tuple[str, ...] = ()


@dataclass
class ReferenceList:
    name: str
    as_of: date
    tax_ids: frozenset
    source: str


@dataclass
class Pack:
    version: int
    tax_code: str
    legal_name: str
    registered_address: str | None
    industry: tuple[str, ...]
    vat_method: str
    filing_period: str           # MONTH | QUARTER
    bank_formats: list[BankFormat]
    thresholds: dict
    policies: list[Policy] = field(default_factory=list)
    reference_lists: list[ReferenceList] = field(default_factory=list)
    portal_columns: dict | None = None
    simulated: bool = False


def _threshold(values: dict, key: str):
    default, direction = CORE_THRESHOLDS[key]
    if key not in values or values[key] is None:
        return default
    value = values[key]
    if default is not None and direction == 'lower' and value > default:
        raise PackError(f'ngưỡng {key}={value} lỏng hơn mặc định {default}; gói của doanh nghiệp chỉ được làm chặt hơn')
    return value


def load_pack(path: Path) -> Pack:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    prof = data.get('profile') or {}
    allowed = {'tax_code', 'legal_name', 'registered_address', 'vat_method', 'filing_period', 'industry'}
    if set(prof) - allowed:
        raise PackError(f'hồ sơ có trường không xác định: {sorted(set(prof) - allowed)}')
    if not mst_checksum_ok(str(prof.get('tax_code', ''))):
        raise PackError('mã số thuế không đúng (sai số kiểm tra hoặc độ dài)')
    if not str(prof.get('legal_name', '')).strip():
        raise PackError('cần tên doanh nghiệp đúng như trên giấy đăng ký thuế')
    if prof.get('vat_method', 'DEDUCTION') not in ('DEDUCTION', 'DIRECT'):
        raise PackError('phương pháp tính thuế giá trị gia tăng phải là DEDUCTION (khấu trừ) hoặc DIRECT (trực tiếp)')
    if prof.get('filing_period', 'MONTH') not in ('MONTH', 'QUARTER'):
        raise PackError('kỳ khai phải là MONTH (tháng) hoặc QUARTER (quý)')
    unknown = set(data.get('thresholds', {})) - set(CORE_THRESHOLDS)
    if unknown:
        raise PackError(f'ngưỡng không xác định: {sorted(unknown)}')
    thresholds = {k: _threshold(data.get('thresholds', {}), k) for k in CORE_THRESHOLDS}
    if thresholds['non_cash_threshold_override'] is not None:
        thresholds['non_cash_threshold_override'] = Decimal(str(thresholds['non_cash_threshold_override']))
    for p in data.get('policies', []):
        if set(p) - {'id', 'flag', 'min_gross', 'description_contains', 'seller_tax_ids'}:
            raise PackError(f'chính sách {p.get("id")} dùng trường không được phép; chính sách chỉ được thêm cờ')
    lists = []
    for r in data.get('reference_lists', []):
        if not r.get('as_of'):
            raise PackError(f'danh sách tham chiếu {r.get("name")} thiếu ngày (as_of)')
        lists.append(ReferenceList(r['name'], date.fromisoformat(r['as_of']), frozenset(r['tax_ids']), r.get('source', '')))
    return Pack(
        version=int(data.get('pack_version', 1)), tax_code=prof['tax_code'], legal_name=prof['legal_name'],
        registered_address=prof.get('registered_address'), industry=tuple(prof.get('industry', ())),
        vat_method=prof.get('vat_method', 'DEDUCTION'), filing_period=prof.get('filing_period', 'MONTH'),
        bank_formats=[BankFormat(**b) for b in data.get('bank_formats', [])], thresholds=thresholds,
        policies=[Policy(p['id'], p['flag'], Decimal(str(p['min_gross'])) if p.get('min_gross') is not None else None,
                         tuple(p.get('description_contains', ())), tuple(p.get('seller_tax_ids', ()))) for p in data.get('policies', [])],
        reference_lists=lists, portal_columns=data.get('portal_columns'), simulated=bool(data.get('simulated', False)))


def load_decisions(path: Path) -> dict:
    """Human decisions recorded by the reviewer: invoice key -> decision record (evidence reference is mandatory)."""
    if not Path(path).exists():
        return {}
    out = {}
    for d in json.loads(Path(path).read_text(encoding='utf-8')):
        if d.get('action') not in ('PAYMENT_EVIDENCE_ATTACHED', 'NOT_CLAIMED', 'CONFIRMED_OK') or not d.get('evidence') or not d.get('by'):
            raise PackError(f'decision for {d.get("invoice_key")} needs action, evidence and by')
        out[d['invoice_key']] = d
    return out
