"""Read a Vietnamese e-invoice XML (Decision 1450/QD-TCT) and run deterministic guards V1-V8 plus QR cross-check.

Every extracted value records its XPath so reviewers can trace it to the signed source.
Checks return ERROR (blocks automatic use), WARN or UNCHECKED; nothing defaults silently.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .xml_signature import SignatureResult, safe_parse, verify_invoice_signatures

VAT_RATES = ('0%', '5%', '8%', '10%', 'KCT', 'KKKNT')
FIDELITY_SIGNED = 'xml-signed-v1'
FIDELITY_UNSIGNED = 'xml-unsigned-v1'
WEIGHTS = (31, 29, 23, 19, 17, 13, 7, 5, 3)
UNITS = {'không': 0, 'một': 1, 'mốt': 1, 'hai': 2, 'ba': 3, 'bốn': 4, 'tư': 4, 'năm': 5, 'lăm': 5, 'nhăm': 5,
         'sáu': 6, 'bảy': 7, 'bẩy': 7, 'tám': 8, 'chín': 9}
SCALES = {'nghìn': 10**3, 'ngàn': 10**3, 'triệu': 10**6, 'tỷ': 10**9, 'tỉ': 10**9}


@dataclass(frozen=True)
class Check:
    code: str
    status: str  # PASS | ERROR | WARN | UNCHECKED | NA
    note: str = ''


@dataclass
class XmlField:
    value: object
    xpath: str


@dataclass
class XmlInvoice:
    fields: dict[str, XmlField]
    items: list[dict[str, XmlField]]
    vat_groups: list[dict[str, XmlField]]
    checks: list[Check]
    signatures: dict[str, SignatureResult]
    fidelity_policy: str
    invoice_id: str | None = None

    @property
    def errors(self):
        return [c for c in self.checks if c.status == 'ERROR']


def _dec(s):
    try:
        return Decimal(s) if s not in (None, '') else None
    except InvalidOperation:
        return None


def mst_checksum_ok(code) -> bool:
    c = (code or '').replace('-', '')
    if c.isdigit() and len(c) == 12:
        return True  # personal ID number replaces the tax code since 2025-07-01
    if not c.isdigit() or len(c) not in (10, 13):
        return False
    check = (10 - sum(int(d) * w for d, w in zip(c[:9], WEIGHTS)) % 11) % 11
    return check != 10 and check == int(c[9])


def words_to_int(text: str):
    """Vietnamese amount in words to an integer; None when any token is not understood."""
    t = re.sub(r'[.,;]', ' ', text.lower())
    t = re.sub(r'\b(đồng|chẵn|việt nam|vnd)\b', ' ', t)
    total = hundreds = tens = 0
    digit = None
    for w in t.split():
        if w in UNITS:
            digit = UNITS[w]
        elif w == 'trăm':
            hundreds, digit = (digit or 0), None
        elif w == 'mười':
            tens, digit = 10, None
        elif w == 'mươi':
            tens, digit = (digit or 0) * 10, None
        elif w in ('linh', 'lẻ'):
            pass
        elif w in SCALES:
            total += (hundreds * 100 + tens + (digit or 0)) * SCALES[w]
            hundreds = tens = 0
            digit = None
        else:
            return None
    return total + hundreds * 100 + tens + (digit or 0)


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def parse_qr(s: str) -> dict:
    out, i = {}, 0
    while i + 4 <= len(s):
        if s[i:i + 4] == '9999':  # custom tag, 4-digit length, carries the tax-authority lookup code
            tag, ln, head = '9999', s[i + 4:i + 8], 8
        else:
            tag, ln, head = s[i:i + 2], s[i + 2:i + 4], 4
        if not ln.isdigit():
            break
        out[tag] = s[i + head:i + head + int(ln)]
        i += head + int(ln)
    return out


def _f(el, base, tag):
    node = el.find(tag) if el is not None else None
    value = node.text.strip() if node is not None and node.text and node.text.strip() else None
    return XmlField(value, f'{base}/{tag}')


def extract(raw: bytes, today: date | None = None) -> XmlInvoice:
    today = today or date.today()
    root = safe_parse(raw)
    if root.tag != 'HDon' or root.find('DLHDon') is None:
        raise ValueError('not a Vietnamese e-invoice (HDon/DLHDon missing)')
    d = root.find('DLHDon')
    tt, nb, nm, tot = d.find('TTChung'), d.find('NDHDon/NBan'), d.find('NDHDon/NMua'), d.find('NDHDon/TToan')
    if None in (tt, nb, nm, tot):
        raise ValueError('invoice sections TTChung/NBan/NMua/TToan are incomplete')
    P = 'HDon/DLHDon'
    fields = {}
    for key, el, base, tag in (('template', tt, f'{P}/TTChung', 'KHMSHDon'), ('symbol', tt, f'{P}/TTChung', 'KHHDon'),
                               ('number', tt, f'{P}/TTChung', 'SHDon'), ('issue_date', tt, f'{P}/TTChung', 'NLap'),
                               ('currency', tt, f'{P}/TTChung', 'DVTTe'), ('payment_method', tt, f'{P}/TTChung', 'HTTToan'),
                               ('form_name', tt, f'{P}/TTChung', 'THDon'), ('provider_tax_id', tt, f'{P}/TTChung', 'MSTTCGP'),
                               ('seller_name', nb, f'{P}/NDHDon/NBan', 'Ten'), ('seller_tax_id', nb, f'{P}/NDHDon/NBan', 'MST'),
                               ('seller_address', nb, f'{P}/NDHDon/NBan', 'DChi'), ('seller_bank_account', nb, f'{P}/NDHDon/NBan', 'STKNHang'),
                               ('buyer_name', nm, f'{P}/NDHDon/NMua', 'Ten'), ('buyer_tax_id', nm, f'{P}/NDHDon/NMua', 'MST'),
                               ('net_total', tot, f'{P}/NDHDon/TToan', 'TgTCThue'), ('vat_total', tot, f'{P}/NDHDon/TToan', 'TgTThue'),
                               ('gross_total', tot, f'{P}/NDHDon/TToan', 'TgTTTBSo'), ('gross_words', tot, f'{P}/NDHDon/TToan', 'TgTTTBChu')):
        fields[key] = _f(el, base, tag)
    items = []
    for i, h in enumerate(d.findall('NDHDon/DSHHDVu/HHDVu'), 1):
        b = f'{P}/NDHDon/DSHHDVu/HHDVu[{i}]'
        items.append({k: _f(h, b, t) for k, t in (('line', 'STT'), ('description', 'THHDVu'), ('unit', 'DVTinh'),
                      ('quantity', 'SLuong'), ('unit_price', 'DGia'), ('discount', 'STCKhau'), ('net', 'ThTien'), ('rate', 'TSuat'))})
    groups = []
    for i, g in enumerate(tot.findall('THTTLTSuat/LTSuat'), 1):
        b = f'{P}/NDHDon/TToan/THTTLTSuat/LTSuat[{i}]'
        groups.append({k: _f(g, b, t) for k, t in (('rate', 'TSuat'), ('base', 'ThTien'), ('vat', 'TThue'))})

    sigs = verify_invoice_signatures(root)
    seller_sig = sigs['seller']
    checks = _guards(root, d, fields, items, groups, sigs, today)
    fidelity = FIDELITY_SIGNED if seller_sig.verified and not [c for c in checks if c.code.startswith('XML_CHECK_SIGNATURE') and c.status == 'ERROR'] \
        else FIDELITY_UNSIGNED
    return XmlInvoice(fields, items, groups, checks, sigs, fidelity, d.get('Id'))


def _guards(root, d, fl, items, groups, sigs, today) -> list[Check]:
    v = lambda k: fl[k].value  # noqa: E731
    res = []

    def add(code, ok, note='', level='ERROR'):
        res.append(Check(code, 'PASS' if ok else level, note))

    one = Decimal(1)
    # V2 arithmetic
    for it in items:
        q, p, disc, net = (_dec(it[k].value) for k in ('quantity', 'unit_price', 'discount', 'net'))
        if q is None or p is None or net is None:
            res.append(Check('XML_CHECK_ARITH_LINE', 'UNCHECKED', f"line {it['line'].value}: quantity/price/amount missing"))
        else:
            add('XML_CHECK_ARITH_LINE', abs(q * p - (disc or 0) - net) <= one, f"line {it['line'].value}")
    net_total, vat_total, gross = _dec(v('net_total')), _dec(v('vat_total')), _dec(v('gross_total'))
    if None in (net_total, vat_total, gross):
        res.append(Check('XML_CHECK_TOTALS_PRESENT', 'ERROR', 'a total is missing or unreadable'))
        return res
    line_nets = [_dec(i['net'].value) for i in items]
    add('XML_CHECK_ARITH_SUM', None not in line_nets and sum(line_nets) == net_total, 'sum of lines vs pre-tax total')
    for g in groups:
        rate = (g['rate'].value or '').rstrip('%')
        base, vat = _dec(g['base'].value), _dec(g['vat'].value)
        if rate.replace('.', '', 1).isdigit() and base is not None and vat is not None:
            add('XML_CHECK_ARITH_VAT_GROUP', abs(base * Decimal(rate) / 100 - vat) <= one, f"group {g['rate'].value}")
    group_vats = [_dec(g['vat'].value) for g in groups]
    if groups:
        add('XML_CHECK_ARITH_VAT_SUM', None not in group_vats and sum(group_vats) == vat_total, 'sum of group VAT vs VAT total')
    add('XML_CHECK_ARITH_GROSS', net_total + vat_total == gross, 'pre-tax + VAT vs payable total')
    # V1 amount in words vs number
    words = words_to_int(v('gross_words') or '') if v('gross_words') else None
    if words is None:
        res.append(Check('XML_CHECK_WORDS', 'ERROR', 'amount in words missing or not readable'))
    else:
        add('XML_CHECK_WORDS', Decimal(words) == gross, f'words {words} vs number {gross}')
    # V4 tax codes
    for who, key in (('seller', 'seller_tax_id'), ('buyer', 'buyer_tax_id')):
        if v(key):
            add('XML_CHECK_TAX_ID_CHECKSUM', mst_checksum_ok(v(key)), who)
        elif who == 'seller':
            res.append(Check('XML_CHECK_TAX_ID_CHECKSUM', 'ERROR', 'seller tax id missing'))
    # V6 symbol, V7 date
    sym = v('symbol') or ''
    m = re.fullmatch(r'([CK])(\d{2})([A-Z])([A-Z0-9]{2})', sym)
    add('XML_CHECK_SYMBOL', bool(m), sym)
    try:
        issued = datetime.strptime(v('issue_date') or '', '%Y-%m-%d').date()
    except ValueError:
        issued = None
    add('XML_CHECK_DATE', issued is not None and issued <= today, 'issue date missing, unreadable or in the future')
    if m and issued:
        add('XML_CHECK_SYMBOL_YEAR', int(m.group(2)) == issued.year % 100, f'{m.group(2)} vs {issued.year}')
    add('XML_CHECK_NUMBER', (v('number') or '').isdigit(), v('number') or '')
    # V8 rates
    for it in items:
        add('XML_CHECK_VAT_RATE', it['rate'].value in VAT_RATES, f"line {it['line'].value}: {it['rate'].value}")
    # authority code on coded invoices
    mc = root.find('MCCQT')
    code_len = len(mc.text.strip()) if mc is not None and mc.text else 0
    if sym.startswith('C'):
        add('XML_CHECK_AUTHORITY_CODE', code_len == 34, f'{code_len} characters')
    # QR cross-check
    qr = root.find('DLQRCode')
    if qr is not None and qr.text:
        q = qr.text.strip()
        tl = parse_qr(q)
        add('XML_CHECK_QR_CRC', q[-4:].upper() == f'{crc16_ccitt(q[:-4].encode()):04X}')
        add('XML_CHECK_QR_SELLER', tl.get('01') == v('seller_tax_id'))
        add('XML_CHECK_QR_NUMBER', tl.get('03') == sym and tl.get('04') == str(int(v('number') or 0)) if (v('number') or '').isdigit() else False)
        add('XML_CHECK_QR_DATE', tl.get('05') == (v('issue_date') or '').replace('-', ''))
        add('XML_CHECK_QR_TOTAL', _dec(tl.get('06')) == gross, f"{tl.get('06')} vs {gross}")
    # signatures
    s = sigs['seller']
    if not s.present:
        res.append(Check('XML_CHECK_SIGNATURE_SELLER', 'ERROR', 'seller signature absent'))
    else:
        add('XML_CHECK_SIGNATURE_SELLER', s.verified, '; '.join(s.notes))
        add('XML_CHECK_SIGNATURE_SIGNER', s.signer_tax_id is not None and s.signer_tax_id.replace('-', '')[:10] == (v('seller_tax_id') or '').replace('-', '')[:10],
            f'certificate tax id {s.signer_tax_id}')
        if s.signing_time and s.not_before and s.not_after:
            add('XML_CHECK_SIGNATURE_VALIDITY', s.not_before <= s.signing_time <= s.not_after, 'signing time within certificate validity')
        else:
            res.append(Check('XML_CHECK_SIGNATURE_VALIDITY', 'ERROR', 'signing time or validity missing'))
        if issued and s.signing_time:
            add('XML_CHECK_SIGNATURE_DATE', s.signing_time.date() >= issued, 'signed before issue date')
    if sym.startswith('C'):
        c = sigs['tax_authority']
        add('XML_CHECK_SIGNATURE_AUTHORITY', c.verified, 'authority signature absent or invalid' if not c.verified else '')
    res.append(Check('XML_CHECK_CERT_CHAIN', 'UNCHECKED', 'certificate chain and revocation are not verified'))
    res.append(Check('XML_CHECK_SELLER_STATUS', 'UNCHECKED', 'seller status on the tax portal is not verified'))
    return res
