"""Convenient intake: safe zip extraction, MT940 statements, and a suggested column mapping for unknown bank layouts."""
import io
import re
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path, PurePosixPath

from ..extraction.xml_context import fold
from .input_schema import BANK_SYNONYMS
from .models import BankTxn
from .sources import parse_amount, parse_date, read_table

MAX_ZIP_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 5000, 5 * 1024 * 1024, 300 * 1024 * 1024


class IntakeError(ValueError):
    pass


def extract_zip(raw: bytes, target: Path, suffixes=('.xml',)) -> list[str]:
    """Extract only the wanted files, flattening paths (no zip-slip), with count and size limits."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    out, total = [], 0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = [i for i in z.infolist() if not i.is_dir() and PurePosixPath(i.filename).suffix.lower() in suffixes]
        if len(infos) > MAX_ZIP_FILES:
            raise IntakeError(f'tệp nén có {len(infos)} tệp, vượt giới hạn {MAX_ZIP_FILES}')
        for i in infos:
            if i.file_size > MAX_FILE_BYTES:
                raise IntakeError(f'{i.filename} lớn hơn {MAX_FILE_BYTES // 1024 // 1024} MB')
            total += i.file_size
            if total > MAX_TOTAL_BYTES:
                raise IntakeError('tổng dung lượng giải nén vượt giới hạn')
            name = re.sub(r'[^\w.\-]', '_', PurePosixPath(i.filename).name)
            dest = target / name
            n = 1
            while dest.exists():
                dest = target / f'{dest.stem}_{n}{dest.suffix}'
                n += 1
            data = z.read(i)
            if len(data) != i.file_size:
                raise IntakeError(f'{i.filename}: kích thước giải nén không khớp')
            dest.write_bytes(data)
            out.append(dest.name)
    return out


# ----------------------------------------------------------------------------- MT940 (SWIFT customer statement)
TAG = re.compile(r'^:(\d{2}[A-Z]?):(.*)$')
F61 = re.compile(r'^(?P<vd>\d{6})(?P<ed>\d{4})?(?P<dc>R?[CD])(?P<fc>[A-Z])?(?P<amt>\d+(?:,\d*)?)(?P<rest>.*)$')


def is_mt940(raw: bytes) -> bool:
    head = raw[:4000].decode('utf-8', 'replace')
    return ':20:' in head and ':61:' in raw.decode('utf-8', 'replace') and (':60F:' in head or ':60M:' in head or ':25:' in head)


def read_mt940(raw: bytes, source: str) -> list[BankTxn]:
    """Fields :61: (statement line) and :86: (information to account owner). Field :86: content is bank specific
    and kept as the description; counterparty account and name are taken from it when they are marked."""
    text = raw.decode('utf-8', 'replace').replace('\r\n', '\n')
    lines, cur = [], None
    for line in text.split('\n'):
        m = TAG.match(line)
        if m:
            cur = [m.group(1), m.group(2)]
            lines.append(cur)
        elif cur is not None and line and not line.startswith('-}'):
            cur[1] += '\n' + line
    out, last = [], None
    for n, (tag, val) in enumerate(lines):
        if tag == '61':
            m = F61.match(val.split('\n')[0])
            if not m:
                raise IntakeError(f'{source}: dòng :61: không đọc được: {val[:40]}')
            vd = m.group('vd')
            booked = date(2000 + int(vd[:2]), int(vd[2:4]), int(vd[4:6]))
            amount = Decimal(m.group('amt').replace(',', '.'))
            reversal = m.group('dc').startswith('R')
            debit = m.group('dc').endswith('D') != reversal
            last = dict(booked=booked, amount=amount, direction='OUT' if debit else 'IN', desc=m.group('rest').strip(), n=n)
            out.append(last)
        elif tag == '86' and last is not None:
            last['desc'] = (last['desc'] + ' ' + val.replace('\n', ' ')).strip()
    txns = []
    for t in out:
        acc = re.search(r'(?:TK|ACC|ACCOUNT|/ACCT/|SO TK)[:\s/]*([\d\-]{6,20})', t['desc'], re.I)
        name = re.search(r'(?:/NAME/|TEN|BENEFICIARY)[:\s/]*([^/]{3,80})', t['desc'], re.I)
        txns.append(BankTxn(txn_id=f'{source}:{t["n"]}', booked=t['booked'], amount=t['amount'], direction=t['direction'],
                            counterparty_account=re.sub(r'\D', '', acc.group(1)) if acc else None,
                            counterparty_name=name.group(1).strip() if name else None, description=t['desc'], source=f'{source} (MT940)'))
    return txns


# ----------------------------------------------------------------------------- unknown bank layouts
def suggest_mapping(path: Path, preview_rows: int = 5) -> dict:
    """Find the header row and match columns by synonyms; return a bank format the user confirms, plus a preview."""
    rows = read_table(path)
    best = None
    for i, row in enumerate(rows[:40]):
        cells = [fold(str(c)).strip() for c in row]
        found = {}
        for field, names in BANK_SYNONYMS.items():
            for j, cell in enumerate(cells):
                if cell and any(cell == nm or (len(nm) > 3 and nm in cell) for nm in names) and j not in found.values():
                    found[field] = j
                    break
        score = len(found) + (2 if {'date', 'debit', 'credit'} <= set(found) or {'date', 'debit'} <= set(found) else 0)
        if best is None or score > best[0]:
            best = (score, i, found, row)
    if not best or not {'date', 'debit'} <= set(best[2]):
        raise IntakeError('không tìm thấy dòng tiêu đề có cột ngày và số tiền; hãy chọn cột thủ công')
    _, head, found, header = best
    sample = [str(r[found['debit']]) for r in rows[head + 1:head + 30] if len(r) > found['debit'] and str(r[found['debit']]).strip()]
    thousands, decimal = ('.', ',') if any(re.fullmatch(r'\d{1,3}(\.\d{3})+(,\d+)?', s) for s in sample) else (',', '.')
    dates = [str(r[found['date']]) for r in rows[head + 1:head + 30] if len(r) > found['date'] and str(r[found['date']]).strip()]
    date_format = '%Y-%m-%d' if dates and re.match(r'\d{4}-\d{2}-\d{2}', dates[0]) else '%d/%m/%Y'
    fmt = dict(name=Path(path).stem, columns={k: str(header[j]) for k, j in found.items()}, date_format=date_format,
               thousands=thousands, decimal=decimal, delimiter=',')
    preview = []
    for r in rows[head + 1:head + 1 + preview_rows]:
        get = lambda k: r[found[k]] if k in found and found[k] < len(r) else ''  # noqa: E731
        try:
            preview.append(dict(date=str(parse_date(get('date'), date_format)), debit=str(parse_amount(get('debit'), thousands, decimal) or ''),
                                credit=str(parse_amount(get('credit'), thousands, decimal) or '') if 'credit' in found else '',
                                description=str(get('description'))[:80]))
        except ValueError as e:
            preview.append(dict(error=str(e)[:80]))
    return dict(format=fmt, header_row=head + 1, missing=sorted(set(BANK_SYNONYMS) - set(found)), preview=preview,
                headers=[str(c) for c in header if str(c).strip()])
