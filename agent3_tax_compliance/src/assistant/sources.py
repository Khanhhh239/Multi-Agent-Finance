"""Step 1-3 of the pipeline: read enterprise files into normalized records.

Bank statements: CSV or XLSX exported from internet banking; column names come from the enterprise pack
because every bank exports a different layout. XLSX is read with the standard library (no extra dependency).
Invoices: signed XML read by the fixed-core extractor, which also runs the data guards.
"""
import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..extraction.xml_context import fold
from ..extraction.xml_invoice import FIDELITY_SIGNED, extract, is_note
from ..extraction.xml_signature import safe_parse
from .models import BankTxn, InvoiceFact
from .pack import BankFormat, Pack

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


class SourceError(ValueError):
    pass


# ----------------------------------------------------------------------------- spreadsheets
def _col_index(ref: str) -> int:
    letters = re.match(r'[A-Z]+', ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(raw: bytes) -> list[list]:
    """First worksheet as rows of values: str for text, Decimal for numbers."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in safe_parse(z.read('xl/sharedStrings.xml')).iter(f'{NS}si'):
                shared.append(''.join(t.text or '' for t in si.iter(f'{NS}t')))
        sheet = sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))[0]
        rows = []
        for row in safe_parse(z.read(sheet)).iter(f'{NS}row'):
            values = {}
            for c in row.iter(f'{NS}c'):
                kind, v = c.get('t'), c.find(f'{NS}v')
                if kind == 's':
                    values[_col_index(c.get('r'))] = shared[int(v.text)]
                elif kind == 'inlineStr':
                    values[_col_index(c.get('r'))] = ''.join(t.text or '' for t in c.iter(f'{NS}t'))
                elif v is not None and v.text is not None:
                    values[_col_index(c.get('r'))] = Decimal(v.text) if kind in (None, 'n') else v.text
            rows.append([values.get(i, '') for i in range(max(values) + 1)] if values else [])
        return rows


def read_table(path: Path, delimiter=',') -> list[list]:
    raw = Path(path).read_bytes()
    if raw[:2] == b'PK':
        return read_xlsx(raw)
    text = raw.decode('utf-8-sig')
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def parse_amount(value, thousands='.', decimal=',') -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    s = re.sub(r'[^\d,.\-]', '', str(value or ''))
    if not s or s in ('-', '.', ','):
        return None
    s = s.replace(thousands, '').replace(decimal, '.') if thousands else s.replace(decimal, '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        raise SourceError(f'amount not readable: {value!r}')


def parse_date(value, fmt) -> date:
    if isinstance(value, Decimal):          # Excel serial day number
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value).strip()
    for f in (fmt, '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.strptime(text, f).date()
        except ValueError:
            continue
    raise SourceError(f'date not readable: {value!r}')


# ----------------------------------------------------------------------------- bank statements
def _find_header(rows, fmt: BankFormat):
    wanted = {k: fold(v) for k, v in fmt.columns.items() if v}
    for i, row in enumerate(rows[:40]):
        cells = [fold(str(c)) for c in row]
        if all(w in cells for w in wanted.values()):
            return i, {k: cells.index(w) for k, w in wanted.items()}
    return None, None


def read_bank_statement(path: Path, pack: Pack) -> list[BankTxn]:
    errors = []
    for fmt in pack.bank_formats:
        rows = read_table(path, fmt.delimiter)
        head, idx = _find_header(rows, fmt)
        if head is None:
            errors.append(fmt.name)
            continue
        out = []
        for n, row in enumerate(rows[head + 1:], head + 2):
            if not any(str(c).strip() for c in row):
                continue
            cell = lambda k: row[idx[k]] if k in idx and idx[k] < len(row) else ''  # noqa: E731
            if not str(cell('date')).strip():
                continue                      # footer and subtotal rows carry no transaction date
            debit = parse_amount(cell('debit'), fmt.thousands, fmt.decimal) or Decimal(0)
            credit = parse_amount(cell('credit'), fmt.thousands, fmt.decimal) or Decimal(0)
            if debit and credit:
                raise SourceError(f'{path.name}:{n} has both debit and credit')
            if not debit and not credit:
                continue
            out.append(BankTxn(
                txn_id=f'{path.name}:{n}', booked=parse_date(cell('date'), fmt.date_format),
                amount=debit or credit, direction='OUT' if debit else 'IN',
                counterparty_account=re.sub(r'\D', '', str(cell('counterparty_account'))) or None,
                counterparty_name=str(cell('counterparty_name')).strip() or None,
                description=str(cell('description')).strip(), source=f'{path.name} dòng {n} ({fmt.name})'))
        return out
    raise SourceError(f'{path.name}: no bank format in the pack matches its header (tried {errors})')


# ----------------------------------------------------------------------------- invoices
def invoice_key(seller_tax_id, template, symbol, number) -> str:
    n = str(int(number)) if number and number.isdigit() else (number or '?')
    return f'{seller_tax_id or "?"}|{template or ""}{symbol or ""}|{n}'


def _dec(v):
    try:
        return Decimal(v) if v not in (None, '') else None
    except InvalidOperation:
        return None


def read_invoices(folder: Path, role: str, as_of: date) -> tuple[list[InvoiceFact], list[str]]:
    facts, unreadable, seen = [], [], {}
    for path in sorted(Path(folder).glob('*.xml')) if Path(folder).exists() else []:
        try:
            inv = extract(path.read_bytes(), today=as_of)
        except Exception as e:  # noqa: BLE001 - a broken file is reported, never guessed
            unreadable.append(f'{path.name}: {type(e).__name__}')
            continue
        f = {k: v.value for k, v in inv.fields.items()}
        issued = None
        try:
            issued = date.fromisoformat(f['issue_date']) if f['issue_date'] else None
        except ValueError:
            pass
        related = None
        if f.get('related_nature'):
            related = dict(nature=f['related_nature'], key=invoice_key(f['seller_tax_id'], f['related_template'], f['related_symbol'],
                                                                       f['related_number']), date=f['related_date'])
        fact = InvoiceFact(
            key=invoice_key(f['seller_tax_id'], f['template'], f['symbol'], f['number']), file=path.name, role=role,
            seller_tax_id=f['seller_tax_id'], seller_name=f['seller_name'], seller_account=re.sub(r'\D', '', f['seller_bank_account'] or '') or None,
            buyer_tax_id=f['buyer_tax_id'], buyer_name=f['buyer_name'], buyer_address=f['buyer_address'],
            template=f['template'], symbol=f['symbol'], number=f['number'], issue_date=issued, currency=f['currency'],
            net=_dec(f['net_total']), vat=_dec(f['vat_total']), gross=_dec(f['gross_total']), payment_label=f['payment_method'],
            descriptions=tuple(r['description'].value for r in inv.items if r['description'].value and not is_note(r)),
            guard_errors=tuple(sorted({c.code for c in inv.errors})), signed=inv.fidelity_policy == FIDELITY_SIGNED, related=related)
        if fact.key in seen:
            fact.duplicate_of = seen[fact.key]
            fact.key = f'{fact.key}#dup:{path.name}'   # each file keeps its own identity in the report
        else:
            seen[fact.key] = path.name
        facts.append(fact)
    return facts, unreadable


# ----------------------------------------------------------------------------- portal list (bảng kê tải từ cổng hóa đơn điện tử)
DEFAULT_PORTAL_COLUMNS = {'seller_tax_id': 'MST người bán', 'template': 'Ký hiệu mẫu số', 'symbol': 'Ký hiệu hóa đơn',
                          'number': 'Số hóa đơn', 'issue_date': 'Ngày lập', 'vat': 'Tổng tiền thuế', 'gross': 'Tổng tiền thanh toán'}


def read_portal_list(path: Path, pack: Pack) -> list[dict]:
    """The real portal export layout is not verified; column names live in the pack (portal_columns)."""
    cols = pack.portal_columns or DEFAULT_PORTAL_COLUMNS
    rows = read_table(path)
    fmt = BankFormat(name='portal', columns=cols)
    head, idx = _find_header(rows, fmt)
    if head is None:
        raise SourceError(f'{Path(path).name}: portal list header not found; set portal_columns in the pack')
    out = []
    for n, row in enumerate(rows[head + 1:], head + 2):
        if not any(str(c).strip() for c in row):
            continue
        get = lambda k: str(row[idx[k]]).strip() if idx[k] < len(row) else ''  # noqa: E731
        out.append(dict(key=invoice_key(get('seller_tax_id'), get('template'), get('symbol'), get('number')),
                        issue_date=get('issue_date'), vat=parse_amount(get('vat')) if 'vat' in idx else None,
                        gross=parse_amount(get('gross')) if 'gross' in idx else None, source=f'{Path(path).name} dòng {n}'))
    return out
