"""Đọc XML có namespace theo QĐ 1450/QĐ-TCT & QĐ 1510/QĐ-TCT; hỗ trợ đa thuế suất & suy luận hạn thanh toán."""
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree as ET
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
import pandas as pd
from .dates import local_dates
from .invoices import validate_invoices
from .money import SCALES, major, minor

_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$')
_VN_DATE_RE = re.compile(r'^\d{1,2}[/-]\d{1,2}[/-]\d{4}$')
_TERM_DAYS_RE = re.compile(
    r'(?:trong\s*(?:vong\s*)?|net\s*|sau\s*|thoi\s*han(?:\s*thanh\s*toan)?\s*:?\s*|han\s*thanh\s*toan\s*:?\s*)?'
    r'(\d{1,4})\s*(?:ngay|days?)\b'
    r'|\bnet\s*(\d{1,4})\b',
    re.IGNORECASE,
)
_INLINE_DUE_DATE_RE = re.compile(
    r'(?:han\s*thanh\s*toan|ngay\s*den\s*han|due\s*date)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b',
    re.IGNORECASE,
)
_DUE_FIELD_KEYS = {
    'hanthanhtoan', 'ngaydenhan', 'ngaydaohan', 'duedate', 'hthanhtoan',
    'thoihanthanhtoan', 'dieukhoanthanhtoan', 'paymentterms', 'songayno',
    'hanmua', 'kyhanthanhtoan',
}
_IMMEDIATE_TERMS = ('thanh toan ngay', 'tra ngay', 'tien mat ngay', 'immediate', 'cod')
_CASH_ONLY_METHODS = {'tm', 'tien mat', 'tienmat', 'cash'}
_STANDARD_VAT_RATES = {
    '0%': Decimal('0'),
    '5%': Decimal('0.05'),
    '8%': Decimal('0.08'),
    '10%': Decimal('0.10'),
    'KCT': Decimal('0'),
    'KKKNT': Decimal('0'),
}
_KHAC_RATE_RE = re.compile(r'^KHAC\s*:\s*([0-9]+(?:[.,][0-9]+)?)\s*%?$', re.IGNORECASE)


def _fold_ascii(value: str) -> str:
    folded = unicodedata.normalize('NFKD', str(value or '').casefold().replace('đ', 'd'))
    return ''.join(ch for ch in folded if not unicodedata.combining(ch))


def _field_key(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', _fold_ascii(value))


def _parse_explicit_date(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    s = value.strip()
    if _ISO_DATE_RE.fullmatch(s):
        parsed = local_dates(pd.Series([s]), dayfirst=False).iloc[0]
        return None if pd.isna(parsed) else parsed
    if _VN_DATE_RE.fullmatch(s):
        parsed = local_dates(pd.Series([s]), dayfirst=True).iloc[0]
        return None if pd.isna(parsed) else parsed
    return None


def _parse_payment_term_days(value: str | None, *, allow_bare_int: bool = False) -> int | None:
    if not value:
        return None
    folded = ' '.join(_fold_ascii(value).split())
    if not folded:
        return None
    if allow_bare_int and folded.isdigit():
        days = int(folded)
        return days if 0 <= days <= 3650 else None
    if any(phrase in folded for phrase in _IMMEDIATE_TERMS):
        return 0
    match = _TERM_DAYS_RE.search(folded)
    if match:
        days = int(match.group(1) or match.group(2))
        return days if 0 <= days <= 3650 else None
    return None


def _resolve_due_date(root, issue_ts: pd.Timestamp, default_days: int) -> tuple[pd.Timestamp, bool]:
    for path in (
        'DLHDon/TTChung/HThanhToan',
        'DLHDon/TTChung/HanThanhToan',
        'DLHDon/TTChung/NgayDenHan',
        'DLHDon/NDHDon/TToan/HThanhToan',
        'DLHDon/TTChung/THopDong',
    ):
        raw = root.findtext(path)
        if not raw or not raw.strip():
            continue
        explicit_ts = _parse_explicit_date(raw)
        if explicit_ts is not None:
            return explicit_ts, False
        days = _parse_payment_term_days(raw, allow_bare_int=path.endswith(('SoNgayNo',)))
        if days is not None:
            return issue_ts + pd.Timedelta(days=days), False

    term_days_hint = None
    for field in root.findall('.//TTin'):
        key = _field_key(field.findtext('TTruong') or '')
        val = (field.findtext('DLieu') or '').strip()
        if not val:
            continue
        if key in _DUE_FIELD_KEYS:
            explicit_ts = _parse_explicit_date(val)
            if explicit_ts is not None:
                return explicit_ts, False
            days = _parse_payment_term_days(val, allow_bare_int=(key == 'songayno'))
            if days is not None and term_days_hint is None:
                term_days_hint = days
        else:
            folded = _fold_ascii(val)
            inline_date = _INLINE_DUE_DATE_RE.search(folded)
            if inline_date:
                explicit_ts = _parse_explicit_date(inline_date.group(1))
                if explicit_ts is not None:
                    return explicit_ts, False
            if 'thanh toan' in folded or 'han tra' in folded:
                days = _parse_payment_term_days(val)
                if days is not None and term_days_hint is None:
                    term_days_hint = days

    if term_days_hint is not None:
        return issue_ts + pd.Timedelta(days=term_days_hint), False

    htt_raw = (root.findtext('DLHDon/TTChung/HTTToan') or '').strip()
    htt_folded = ' '.join(_fold_ascii(htt_raw).split())
    if htt_folded in _CASH_ONLY_METHODS:
        return issue_ts, True
    return issue_ts + pd.Timedelta(days=default_days), True


def _normalize_xml_vat_rate(raw: str) -> tuple[str, Decimal]:
    token = raw.strip().upper().replace(' ', '')
    if token in _STANDARD_VAT_RATES:
        return token, _STANDARD_VAT_RATES[token]
    if token in {'KHONGCHIUTHUE', 'KHAC:KCT'}:
        return 'KCT', Decimal('0')
    if token in {'KHONGKEKHAI', 'KHONGKEKHAINOPTHUE', 'KHAC:KKKNT'}:
        return 'KKKNT', Decimal('0')
    khac = _KHAC_RATE_RE.fullmatch(token)
    if khac:
        try:
            pct = Decimal(khac.group(1).replace(',', '.'))
        except InvalidOperation as exc:
            raise ValueError(f'Thuế suất GTGT không hợp lệ: {raw}') from exc
        if pct < 0 or pct > 10:
            raise ValueError(f'Thuế suất GTGT vượt khung cho phép: {raw}')
        normalized_pct = int(pct) if pct == pct.to_integral_value() else pct.normalize()
        label = f'{normalized_pct}%' if f'{normalized_pct}%' in _STANDARD_VAT_RATES else f'KHAC:{normalized_pct}%'
        return label, pct / Decimal('100')
    cleaned = token[:-1] if token.endswith('%') else token
    try:
        num = Decimal(cleaned.replace(',', '.'))
    except InvalidOperation as exc:
        raise ValueError(f'Thuế suất GTGT không hợp lệ: {raw}') from exc
    if not token.endswith('%') and Decimal('0') < num <= Decimal('0.10'):
        num = num * Decimal('100')
    for label, rate_dec in (('0%', Decimal('0')), ('5%', Decimal('0.05')), ('8%', Decimal('0.08')), ('10%', Decimal('0.10'))):
        if num == rate_dec * Decimal('100'):
            return label, rate_dec
    raise ValueError(f'Thuế suất GTGT không hợp lệ: {raw}')


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    try:
        dec = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return dec if dec.is_finite() else None


def _canonical_money_str(value: str | None, currency: str) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    cur = str(currency or '').strip().upper()
    if cur in SCALES:
        try:
            return major(minor(s, cur), cur)
        except ValueError:
            return s
    return s


def read_invoice_xml(content, firm_id, *, validate=True, default_payment_terms_days=None):
    default_days = (
        int(os.environ.get('AGENT1_DEFAULT_PAYMENT_TERMS_DAYS', '30'))
        if default_payment_terms_days is None
        else int(default_payment_terms_days)
    )
    if type(default_days) is not int or default_days < 0 or default_days > 3650:
        raise ValueError('default_payment_terms_days phải là số nguyên từ 0 đến 3650')
    content = content if isinstance(content, bytes) else Path(content).read_bytes()
    if len(content) > 10_000_000 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('XML có khai báo thực thể hoặc vượt giới hạn')
    try:
        root = SafeET.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ET.ParseError) as error:
        raise ValueError('XML không hợp lệ hoặc chứa DTD/thực thể bị cấm') from error
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    version = (root.findtext('.//TTChung/PBan') or '').strip() or None
    if version not in {'2.0.0', '2.0.1', '2.1.0'}:
        raise ValueError(f'Chưa hỗ trợ PBan={version}')

    def get(path):
        val = root.findtext(path)
        return val.strip() if val is not None and val.strip() != '' else None

    dl = root.find('DLHDon')
    if dl is None:
        raise ValueError('XML thiếu phần tử DLHDon')

    issue_raw = get('DLHDon/TTChung/NLap')
    if not issue_raw:
        raise ValueError('XML thiếu ngày lập hóa đơn NLap')
    issue_ts = local_dates(pd.Series([issue_raw]), dayfirst=False).iloc[0]
    if pd.isna(issue_ts):
        raise ValueError('Ngày lập hóa đơn NLap không hợp lệ')
    due_ts, due_inferred = _resolve_due_date(root, issue_ts, default_days)

    currency = get('DLHDon/TTChung/DVTTe') or 'VND'
    currency_upper = currency.upper()
    tol = Decimal('1000') if currency_upper in {'VND', 'JPY'} else Decimal('0.05')

    vat_labels: list[str] = []
    lt_nodes = root.findall('DLHDon/NDHDon/TToan/THTTLTSuat/LTSuat')
    lt_net_sum = Decimal('0')
    lt_vat_sum = Decimal('0')
    has_lt_amounts = False
    for lt in lt_nodes:
        raw_rate = (lt.findtext('TSuat') or '').strip()
        if raw_rate:
            label, rate_dec = _normalize_xml_vat_rate(raw_rate)
            if label not in vat_labels:
                vat_labels.append(label)
        else:
            rate_dec = Decimal('0')
        lt_net = _decimal_or_none(lt.findtext('ThTien'))
        lt_vat = _decimal_or_none(lt.findtext('TThue'))
        if lt_net is not None:
            has_lt_amounts = True
            actual_lt_vat = lt_vat if lt_vat is not None else Decimal('0')
            if abs(lt_net * rate_dec - actual_lt_vat) > tol:
                raise ValueError('Tổng thuế theo thuế suất LTSuat không khớp tiền trước thuế × thuế suất')
            lt_net_sum += lt_net
            lt_vat_sum += actual_lt_vat

    line_net_sum = Decimal('0')
    has_line_net = False
    for line in root.findall('DLHDon/NDHDon/DSHHDVu/HHDVu'):
        raw_rate = (line.findtext('TSuat') or '').strip()
        if raw_rate:
            label, _ = _normalize_xml_vat_rate(raw_rate)
            if label not in vat_labels:
                vat_labels.append(label)
        line_net = _decimal_or_none(line.findtext('ThTien'))
        if line_net is not None:
            has_line_net = True
            line_net_sum += line_net

    amount_net = get('DLHDon/NDHDon/TToan/TgTCThue')
    vat = get('DLHDon/NDHDon/TToan/TgTThue')
    amount_gross = get('DLHDon/NDHDon/TToan/TgTTTBSo')
    if vat is None and (amount_gross is not None or has_lt_amounts):
        vat = str(lt_vat_sum) if has_lt_amounts else '0'
    if amount_net is None:
        if has_lt_amounts:
            amount_net = str(lt_net_sum)
        elif has_line_net:
            amount_net = str(line_net_sum)
        elif amount_gross is not None and vat is not None:
            gross_dec = _decimal_or_none(amount_gross)
            vat_dec = _decimal_or_none(vat)
            if gross_dec is not None and vat_dec is not None:
                amount_net = str(gross_dec - vat_dec)

    if has_lt_amounts:
        net_dec = _decimal_or_none(amount_net)
        vat_dec = _decimal_or_none(vat)
        if net_dec is not None and abs(lt_net_sum - net_dec) > tol:
            raise ValueError('Tổng tiền trước thuế THTTLTSuat không khớp TgTCThue')
        if vat_dec is not None and abs(lt_vat_sum - vat_dec) > tol:
            raise ValueError('Tổng tiền thuế THTTLTSuat không khớp TgTThue')

    amount_net = _canonical_money_str(amount_net, currency)
    vat = _canonical_money_str(vat, currency)
    amount_gross = _canonical_money_str(amount_gross, currency)

    seller_mst = get('DLHDon/NDHDon/NBan/MST')
    buyer_mst = (
        get('DLHDon/NDHDon/NMua/MST')
        or get('DLHDon/NDHDon/NMua/CCCDan')
        or get('DLHDon/NDHDon/NMua/MDVQHNSach')
    )
    buyer_name = get('DLHDon/NDHDon/NMua/Ten') or get('DLHDon/NDHDon/NMua/HVTNMHang')
    invoice_key = (dl.get('Id') or '').strip() or None
    symbol = get('DLHDon/TTChung/KHHDon')
    invoice_no = get('DLHDon/TTChung/SHDon')

    row = dict(
        invoice_key=invoice_key,
        symbol=symbol,
        invoice_no=invoice_no,
        issue_date=issue_ts,
        currency=currency,
        seller_mst=seller_mst,
        buyer_mst=buyer_mst,
        buyer_name=buyer_name,
        amount_net=amount_net,
        vat=vat,
        amount_gross=amount_gross,
        due_date=due_ts,
    )
    row['firm_id'] = firm_id
    row['invoice_id'] = row.pop('invoice_key') or f"{row['seller_mst']}-{row['symbol']}-{row['invoice_no']}"
    row['customer_id'] = str(row['buyer_mst'])
    row['document_version'] = version
    if vat_labels:
        row['vat_rates'] = ','.join(vat_labels)
    if due_inferred:
        row['due_date_inferred'] = True

    related = root.find('.//TTChung/TTHDLQuan')
    nature = (related.findtext('TCHDon') or '').strip() if related is not None and related.findtext('TCHDon') is not None else None
    if nature not in (None, '1', '2'):
        raise ValueError(f'Chưa hỗ trợ tính chất hóa đơn TCHDon={nature}')
    row['adjustment_type'] = {'1': 'replacement', '2': 'adjustment'}.get(nature)
    if nature:
        row['adjusts_symbol'] = (related.findtext('KHHDCLQuan') or '').strip() or None
        row['adjusts_invoice_no'] = (related.findtext('SHDCLQuan') or '').strip() or None
        row['adjusts_issue_date'] = (related.findtext('NLHDCLQuan') or '').strip() or None
        if not row['adjusts_symbol'] or not row['adjusts_invoice_no'] or not row['adjusts_issue_date']:
            raise ValueError('Hóa đơn liên quan thiếu ký hiệu, số hoặc ngày lập')

    row['term_days'] = (row['due_date'] - row['issue_date']).days if pd.notna(row['due_date']) else 0
    if validate:
        row['available_on'] = pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').date().isoformat()
        validate_invoices([row], source='xml', today=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None).normalize())
    return row
