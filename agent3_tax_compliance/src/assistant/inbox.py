"""One drop zone for everything, file-by-file status, editable bank mapping preview, and a coverage check before analysis.

Classification is deterministic:
* .xml: an e-invoice (has HDon). The seller tax id equal to the profile's -> sales; the buyer tax id equal -> purchase;
  neither -> rejected with the reason (an invoice of another company).
* .sta, .mt940, or .txt in MT940 layout -> bank statement.
* .csv, .xlsx: the portal purchase list if its header matches the portal columns of the pack; a bank statement if a
  header row with a date column and an amount column is found; otherwise rejected.
* .zip: every member is classified the same way (paths flattened, size and count limits of extract_zip).
"""
import shutil
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

from lxml import etree

from ..extraction.xml_context import similarity

from .intake import IntakeError, extract_zip, is_mt940, read_mt940, suggest_mapping
from .pack import BankFormat, Pack
from .sources import (DEFAULT_PORTAL_COLUMNS, SourceError, _find_header, parse_amount, parse_date, read_bank_statement, read_invoices,
                      read_portal_list, read_table)

KIND_FOLDER = {'purchase_xml': 'invoices/purchase', 'sales_xml': 'invoices/sales', 'bank': 'bank', 'portal_list': 'portal'}
KIND_LABEL = {'purchase_xml': 'Hóa đơn mua vào', 'sales_xml': 'Hóa đơn bán ra', 'bank': 'Sao kê ngân hàng', 'portal_list': 'Bảng kê cổng thuế'}
ACCEPT = ('.xml', '.csv', '.xlsx', '.sta', '.mt940', '.txt')


def _xml_parties(raw: bytes) -> tuple:
    root = etree.fromstring(raw, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False))
    if not root.xpath('//*[local-name()="HDon"]') and etree.QName(root).localname != 'HDon':
        raise IntakeError('tệp XML không phải hóa đơn điện tử (không có thẻ HDon)')
    get = lambda party, tag: (root.xpath(f'string(//*[local-name()="{party}"]/*[local-name()="{tag}"])') or '').strip() or None  # noqa: E731
    return get('NBan', 'MST'), get('NMua', 'MST'), get('NBan', 'Ten'), get('NMua', 'Ten')


def classify(path: Path, tax_code: str, pack: Pack) -> tuple[str | None, str]:
    """(kind, reason). kind None means the file is not used, and the reason says why."""
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == '.xml':
        try:
            seller, buyer, seller_name, buyer_name = _xml_parties(raw)
        except (etree.XMLSyntaxError, IntakeError) as e:
            return None, f'không đọc được XML hóa đơn: {str(e)[:120]}'
        if seller == tax_code:
            return 'sales_xml', 'người bán là doanh nghiệp này'
        if buyer == tax_code:
            return 'purchase_xml', 'người mua là doanh nghiệp này'
        # A wrong tax id on an invoice addressed to this company is itself a risk (R07): load it so the rule can flag it.
        if buyer_name and similarity(buyer_name, pack.legal_name) >= 0.8:
            return 'purchase_xml', f'tên người mua trùng doanh nghiệp nhưng mã số thuế ghi {buyer}; vẫn nạp để kiểm tra'
        if seller_name and similarity(seller_name, pack.legal_name) >= 0.8:
            return 'sales_xml', f'tên người bán trùng doanh nghiệp nhưng mã số thuế ghi {seller}; vẫn nạp để kiểm tra'
        return None, f'hóa đơn không có mã số thuế {tax_code} ở người bán ({seller}) hay người mua ({buyer})'
    if suffix in ('.sta', '.mt940') or (suffix == '.txt' and is_mt940(raw)):
        return 'bank', 'sao kê định dạng MT940'
    if suffix in ('.csv', '.xlsx'):
        try:
            rows = read_table(path)
        except Exception as e:  # noqa: BLE001
            return None, f'không đọc được bảng: {type(e).__name__}'
        portal = BankFormat(name='portal', columns=pack.portal_columns or DEFAULT_PORTAL_COLUMNS)
        if _find_header(rows, portal)[0] is not None:
            return 'portal_list', 'tiêu đề cột khớp bảng kê hóa đơn của cổng thuế'
        try:
            suggest_mapping(path)
            return 'bank', 'có dòng tiêu đề với cột ngày và cột số tiền'
        except (IntakeError, ValueError):
            return None, 'không nhận ra là sao kê hay bảng kê: không có dòng tiêu đề với cột ngày và số tiền'
    return None, f'không nhận loại tệp {suffix or "không đuôi"}'


def _unique(folder: Path, name: str) -> Path:
    dest, n = folder / name, 1
    while dest.exists():
        dest = folder / f'{Path(name).stem}_{n}{Path(name).suffix}'
        n += 1
    return dest


def ingest(ws: Path, name: str, raw: bytes, tax_code: str, pack: Pack) -> list[dict]:
    """Classify and store one upload (a single file or a zip). Returns one record per file."""
    tmp = Path(tempfile.mkdtemp(prefix='inbox_', dir=ws))
    try:
        if Path(name).suffix.lower() == '.zip':
            names = extract_zip(raw, tmp, suffixes=ACCEPT)
        else:
            (tmp / name).write_bytes(raw)
            names = [name]
        out = []
        for n in names:
            p = tmp / n
            kind, reason = classify(p, tax_code, pack)
            rec = dict(file=n, kind=kind, label=KIND_LABEL.get(kind, 'Không dùng'), reason=reason)
            if kind:
                folder = ws / KIND_FOLDER[kind]
                folder.mkdir(parents=True, exist_ok=True)
                dest = folder / 'purchase_list.csv' if kind == 'portal_list' and p.suffix.lower() == '.csv' else (
                    folder / f'purchase_list{p.suffix.lower()}' if kind == 'portal_list' else _unique(folder, n))
                shutil.move(str(p), dest)
                rec['saved_as'] = dest.name
            out.append(rec)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------- file-by-file status
def file_details(ws: Path, kind: str, pack: Pack, as_of: date) -> list[dict]:
    folder = ws / KIND_FOLDER[kind]
    if not folder.exists():
        return []
    if kind in ('purchase_xml', 'sales_xml'):
        invoices, bad = read_invoices(folder, 'PURCHASE' if kind == 'purchase_xml' else 'SALE', as_of)
        out = [dict(file=i.file, ok=not i.guard_errors, number=f'{i.template or ""}{i.symbol or ""}/{i.number or ""}', date=i.issue_date,
                    party=i.seller_name if kind == 'purchase_xml' else i.buyer_name, gross=i.gross, vat=i.vat,
                    errors=list(i.guard_errors), duplicate=bool(getattr(i, 'duplicate_of', None))) for i in invoices]
        out += [dict(file=b.split(':', 1)[0], ok=False, errors=[f'không đọc được: {b.split(":", 1)[1].strip()}']) for b in bad]
        return sorted(out, key=lambda r: r['file'])
    out = []
    for p in sorted(folder.glob('*')):
        try:
            if kind == 'bank':
                raw = p.read_bytes()
                txns = read_mt940(raw, p.name) if p.suffix.lower() in ('.sta', '.mt940') or is_mt940(raw) else read_bank_statement(p, pack)
                days = sorted(t.booked for t in txns)
                out.append(dict(file=p.name, ok=True, rows=len(txns), first=days[0] if days else None, last=days[-1] if days else None,
                                out_count=sum(t.direction == 'OUT' for t in txns)))
            else:
                rows = read_portal_list(p, pack)
                out.append(dict(file=p.name, ok=True, rows=len(rows)))
        except (SourceError, IntakeError, ValueError) as e:
            hint = ' Bấm Nhận dạng cột rồi lưu mẫu sao kê.' if kind == 'bank' and 'no bank format' in str(e) else ''
            out.append(dict(file=p.name, ok=False, errors=[f'{str(e)[:160]}{hint}']))
    return out


# ----------------------------------------------------------------------------- editable mapping
def preview_with(path: Path, fmt: dict, rows_wanted: int = 8) -> dict:
    """Read a statement with a mapping the user edited; the same parser the pipeline uses."""
    bf = BankFormat(**{k: v for k, v in fmt.items() if k in BankFormat.__dataclass_fields__})
    rows = read_table(path, bf.delimiter)
    head, idx = _find_header(rows, bf)
    if head is None:
        raise IntakeError('không tìm thấy dòng tiêu đề chứa đủ các cột đã chọn')
    preview, errors = [], 0
    for r in rows[head + 1:]:
        if len(preview) >= rows_wanted:
            break
        cell = lambda k: r[idx[k]] if k in idx and idx[k] < len(r) else ''  # noqa: E731
        if not str(cell('date')).strip():
            continue
        try:
            preview.append(dict(date=str(parse_date(cell('date'), bf.date_format)),
                                debit=str(parse_amount(cell('debit'), bf.thousands, bf.decimal) or ''),
                                credit=str(parse_amount(cell('credit'), bf.thousands, bf.decimal) or '') if 'credit' in idx else '',
                                description=str(cell('description'))[:80], counterparty=str(cell('counterparty_name'))[:60]))
        except ValueError as e:
            errors += 1
            preview.append(dict(error=str(e)[:100]))
    return dict(header_row=head + 1, preview=preview, errors=errors)


# ----------------------------------------------------------------------------- coverage before analysis
def coverage(ws: Path, pack: Pack, as_of: date, threshold) -> list[dict]:
    """Concrete warnings about missing data. Each: level (warning|info), title, detail."""
    out = []
    purchases, _ = read_invoices(ws / KIND_FOLDER['purchase_xml'], 'PURCHASE', as_of)
    sales_files = list((ws / KIND_FOLDER['sales_xml']).glob('*.xml')) if (ws / KIND_FOLDER['sales_xml']).exists() else []
    if not purchases:
        out.append(dict(level='warning', title='Chưa có hóa đơn mua vào', detail='Đây là dữ liệu bắt buộc; thả tệp XML hoặc tệp nén vào ô Nạp nhanh.'))
        return out
    month = lambda d: f'{d.month:02d}/{d.year}'  # noqa: E731
    need = Counter(month(i.issue_date) for i in purchases if i.issue_date and i.gross is not None and i.gross >= threshold)
    banked = set()
    bank_dir = ws / KIND_FOLDER['bank']
    unread = []
    for p in sorted(bank_dir.glob('*')) if bank_dir.exists() else []:
        try:
            raw = p.read_bytes()
            txns = read_mt940(raw, p.name) if p.suffix.lower() in ('.sta', '.mt940') or is_mt940(raw) else read_bank_statement(p, pack)
            banked |= {month(t.booked) for t in txns}
        except (SourceError, IntakeError, ValueError):
            unread.append(p.name)
    if unread:
        out.append(dict(level='warning', title=f'{len(unread)} tệp sao kê chưa đọc được', detail=f'{", ".join(unread[:5])}: mở bước Sao kê ngân hàng, bấm Nhận dạng cột, kiểm tra rồi lưu mẫu.'))
    missing = sorted((m for m in need if m not in banked), key=lambda m: (m[3:], m[:2]))
    if missing:
        n = sum(need[m] for m in missing)
        out.append(dict(level='warning', title=f'Thiếu sao kê cho tháng {", ".join(missing)}',
                        detail=f'{n} hóa đơn từ {int(threshold):,} đồng trong các tháng này sẽ bị báo là chưa có chứng từ thanh toán. Nạp sao kê của mọi tài khoản đã dùng để trả tiền.'.replace(',', '.')))
    portal = ws / KIND_FOLDER['portal_list']
    if not portal.exists() or not any(portal.glob('purchase_list.*')):
        out.append(dict(level='info', title='Chưa có bảng kê hóa đơn mua vào từ cổng thuế',
                        detail='Có bảng kê thì hệ thống phát hiện được hóa đơn có trên cổng nhưng doanh nghiệp chưa có tệp (có thể đang bỏ sót khấu trừ).'))
    else:
        try:
            rows = read_portal_list(next(portal.glob('purchase_list.*')), pack)
            keys = {i.key for i in purchases}
            only_portal = [r for r in rows if r['key'] not in keys]
            if only_portal:
                out.append(dict(level='warning', title=f'{len(only_portal)} hóa đơn có trên cổng thuế nhưng chưa có tệp XML',
                                detail='Tải các hóa đơn này từ cổng hóa đơn điện tử để không bỏ sót khấu trừ.'))
        except (SourceError, ValueError) as e:
            out.append(dict(level='warning', title='Bảng kê cổng thuế chưa đọc được', detail=str(e)[:160]))
    if not sales_files:
        out.append(dict(level='info', title='Chưa có hóa đơn bán ra', detail='Không bắt buộc; có thì đối chiếu được thuế đầu ra.'))
    if not pack.industry:
        out.append(dict(level='info', title='Hồ sơ chưa ghi ngành nghề', detail='Ghi ngành nghề để hệ thống nhận ra hàng hóa không khớp hoạt động kinh doanh.'))
    return out
