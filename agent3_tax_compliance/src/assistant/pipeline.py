"""Run the whole assistant pipeline on one enterprise workspace. Same inputs and ruleset give the same report.

Workspace layout (all files are exported by the enterprise itself; nothing connects to a bank or the tax portal):
  pack.json                       enterprise adaptive pack (profile, bank formats, thresholds, policies, reference lists)
  invoices/purchase/*.xml         purchase invoices (enterprise is the buyer)
  invoices/sales/*.xml            optional sales invoices
  bank/*.csv | *.xlsx             bank statements exported from internet banking
  portal/purchase_list.csv        optional invoice list exported from the e-invoice portal
  decisions.json                  optional reviewer decisions (evidence attached, not claimed)
"""
import calendar as cal
import hashlib
import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .intake import is_mt940, read_mt940
from .matching import match_payments
from .models import Report
from .pack import load_decisions, load_pack
from .rules import evaluate, load_ruleset, param, totals
from .sources import read_bank_statement, read_invoices, read_portal_list

DEFAULT_RULESET = Path(__file__).resolve().parents[2] / 'configs/assistant/ruleset_2026_11_draft.json'
STATUS_ORDER = {'AT_RISK': 0, 'REVIEW': 1, 'OPPORTUNITY': 2, 'INFO': 3}


def input_digest(ws: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in ws.rglob('*') if x.is_file() and 'out' not in x.relative_to(ws).parts and x.name != 'labels.json'):
        h.update(str(p.relative_to(ws)).replace('\\', '/').encode() + b'\0' + p.read_bytes())
    return h.hexdigest()


# Fixed public holidays (Tết and yearly substitute days off are announced each year; the pack may list them in days_off).
FIXED_DAYS_OFF = {(1, 1), (4, 30), (5, 1), (9, 2)}


def filing_calendar(pack, invoices, ruleset, as_of: date) -> list[dict]:
    periods = sorted({(i.issue_date.year, i.issue_date.month) for i in invoices if i.issue_date})
    out = []
    if pack.filing_period == 'MONTH':
        day, basis = param(ruleset, 'VAT_RETURN_DUE_MONTHLY_DAY', as_of)
        for y, m in periods:
            ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
            out.append(dict(period=f'Tháng {m:02d}/{y}', due=date(ny, nm, int(day)), basis=basis))
    else:
        _, basis = param(ruleset, 'VAT_RETURN_DUE_QUARTERLY', as_of)
        for y, q in sorted({(y, (m - 1) // 3 + 1) for y, m in periods}):
            ny, first = (y + 1, 1) if q == 4 else (y, q * 3 + 1)
            out.append(dict(period=f'Quý {q}/{y}', due=date(ny, first, cal.monthrange(ny, first)[1]), basis=basis))
    for e in out:
        e['period'] = f'Tờ khai thuế GTGT {e["period"].lower()}'
    # Corporate income tax: quarterly provisional payment and the annual finalization (calendar-year fiscal period assumed).
    prov = param(ruleset, 'CIT_PROVISIONAL_DUE', as_of) if 'CIT_PROVISIONAL_DUE' in ruleset['parameters'] else None
    fin = param(ruleset, 'CIT_FINALIZATION_DUE', as_of) if 'CIT_FINALIZATION_DUE' in ruleset['parameters'] else None
    if prov:
        for y, q in sorted({(y, (m - 1) // 3 + 1) for y, m in periods}):
            ny, first = (y + 1, 1) if q == 4 else (y, q * 3 + 1)
            e = dict(period=f'Tạm nộp thuế TNDN quý {q}/{y}', due=date(ny, first, cal.monthrange(ny, first)[1]), basis=prov[1])
            if (y, q) in ((2026, 2), (2026, 3)):
                e['extension'] = ('Có thể được gia hạn (quý II/2026: 03 tháng, quý III/2026: 02 tháng) nếu thuộc đối tượng của '
                                  'Nghị định 245/2026/NĐ-CP, khoản 2 Điều 2; phải nộp giấy đề nghị gia hạn')
            out.append(e)
    if fin:
        for y in sorted({y for y, _ in periods}):
            out.append(dict(period=f'Quyết toán thuế TNDN năm {y}', due=date(y + 1, 3, 31), basis=fin[1]))
    shift = param(ruleset, 'DEADLINE_DAY_OFF_SHIFT', as_of) if 'DEADLINE_DAY_OFF_SHIFT' in ruleset['parameters'] else None
    extra_days_off = {date.fromisoformat(d) for d in getattr(pack, 'days_off', ())}
    for e in out:
        if shift:
            legal = e['due']
            while legal.weekday() >= 5 or (legal.month, legal.day) in FIXED_DAYS_OFF or legal in extra_days_off:
                legal += timedelta(days=1)
            if legal != e['due']:
                e['moved_from'], e['due'] = e['due'], legal
                e['basis'] += f'; {shift[1]}'
    out.sort(key=lambda e: e['due'])
    for e in out:
        days = (e['due'] - as_of).days
        e['status'] = f'còn {days} ngày' if days >= 0 else f'hạn đã qua {-days} ngày, kiểm tra đã nộp chưa'
        e['note'] = ((f'Dời từ {e["moved_from"]:%d/%m/%Y} vì trùng ngày nghỉ. ' if e.get('moved_from') else '')
                     + 'Đã tính thứ Bảy, Chủ nhật và các ngày lễ cố định; nghỉ Tết và nghỉ bù hằng năm cần nhập trong gói'
                     + (f'. {e["extension"]}' if e.get('extension') else ''))
    return out


def purpose_items(ws: Path, invoices: list, ruleset: dict) -> list:
    """R12 from recorded AI line labels (ws/ai/line_labels.json, written by the classify job). The labels are an input
    with model and version recorded; only verified labels saying "not business use" become review items, never money."""
    from .ai import flagged
    from .rules import _item
    path = ws / 'ai' / 'line_labels.json'
    if not path.exists():
        return []
    labels = json.loads(path.read_text(encoding='utf-8'))
    out = []
    for inv in invoices:
        rec = labels.get(inv.key)
        if inv.role != 'PURCHASE' or not rec or inv.duplicate_of:
            continue
        hits = flagged(rec['labels'])
        if hits:
            out.append(_item(ruleset, 'R12_ITEM_PURPOSE', 'REVIEW', [inv], Decimal(0),
                             [f'Phân loại dòng hàng bằng mô hình {rec["model"]} chạy trên máy ({rec["version"]}), đã qua kiểm tra nhãn; người duyệt quyết định',
                              'Điểm a khoản 1 Điều 14 Luật Thuế GTGT 48/2024/QH15: khấu trừ thuế đầu vào của hàng hóa, dịch vụ sử dụng cho sản xuất, kinh doanh hàng hóa, dịch vụ chịu thuế; điểm a khoản 1 Điều 9 Luật Thuế TNDN 67/2025/QH15: khoản chi được trừ phải thực tế phát sinh, liên quan đến hoạt động sản xuất kinh doanh (văn bản gốc, vbpl.vn)'],
                             detail='; '.join(f'{h["line"]}: {h["reason"]}' for h in hits)))
    return out


def apply_not_claimed(items: list, decisions: dict) -> list:
    """An invoice the reviewer decided not to claim carries no deduction risk. Its items stay in the report as INFO with
    the decision written into the detail, so the audit trail shows who decided and why; they leave the totals."""
    out = []
    for it in items:
        ds = [decisions.get(k) for k in it.invoice_keys]
        if it.status != 'INFO' and ds and all(d and d['action'] == 'NOT_CLAIMED' for d in ds):
            note = '; '.join(f'{d["evidence"]} (quyết định của {d["by"]})' for d in ds)
            it = replace(it, status='INFO', amount=Decimal(0),
                         detail=f'{it.detail} Đã quyết định không kê khai khấu trừ: {note}.'.strip())
        out.append(it)
    return out


def run(workspace: Path, ruleset_path: Path = DEFAULT_RULESET, as_of: date | None = None, extra_decisions: dict | None = None) -> Report:
    ws = Path(workspace)
    as_of = as_of or date.today()
    pack = load_pack(ws / 'pack.json')
    ruleset = load_ruleset(ruleset_path)
    decisions = load_decisions(ws / 'decisions.json')
    decisions.update(extra_decisions or {})
    purchases, bad1 = read_invoices(ws / 'invoices' / 'purchase', 'PURCHASE', as_of)
    sales, bad2 = read_invoices(ws / 'invoices' / 'sales', 'SALE', as_of)
    invoices = purchases + sales
    txns = []
    for p in sorted((ws / 'bank').glob('*')) if (ws / 'bank').exists() else []:
        raw = p.read_bytes() if p.is_file() else b''
        if p.suffix.lower() in ('.sta', '.mt940') or (p.suffix.lower() == '.txt' and is_mt940(raw)):
            txns.extend(read_mt940(raw, p.name))
        elif p.suffix.lower() in ('.csv', '.xlsx'):
            txns.extend(read_bank_statement(p, pack))
    portal_file = ws / 'portal' / 'purchase_list.csv'
    portal = read_portal_list(portal_file, pack) if portal_file.exists() else None
    matches = match_payments(invoices, txns, pack.thresholds, decisions)
    items, flags = evaluate(invoices, matches, pack, ruleset, bad1 + bad2, portal)
    items += purpose_items(ws, invoices, ruleset)
    items = apply_not_claimed(items, decisions)
    items.sort(key=lambda it: (STATUS_ORDER[it.status], -it.amount, it.code, it.invoice_keys))
    dates = [i.issue_date for i in invoices if i.issue_date]
    meta = dict(workspace=ws.name, company=pack.legal_name, tax_code=pack.tax_code, simulated=pack.simulated, as_of=as_of,
                pack_version=pack.version, ruleset_version=ruleset['version'], ruleset_status=ruleset['status'],
                ruleset_note=ruleset.get('status_note', ''), period=(min(dates), max(dates)) if dates else None,
                counts=dict(purchase_invoices=len(purchases), sales_invoices=len(sales), bank_transactions=len(txns),
                            portal_rows=len(portal) if portal is not None else None, decisions=len(decisions)),
                unreadable=bad1 + bad2, input_sha256=input_digest(ws),
                limitations=['Luật ở trạng thái nháp, chưa có chuyên gia thuế duyệt',
                             'Chứng từ thanh toán chỉ tìm trong sao kê đã nạp; tiền mặt và sao kê thiếu sẽ hiện là chưa có chứng từ',
                             'Không có dữ liệu trực tiếp của cơ quan thuế (tình trạng người bán, thông báo phát hành)',
                             'Ước tính phạt là mức tối đa nếu bị xác định khai sai, chưa gồm tiền chậm nộp'])
    return Report(meta=meta, invoices=invoices, transactions=txns, matches=matches, items=items,
                  totals=totals(items, ruleset, as_of), calendar=filing_calendar(pack, invoices, ruleset, as_of), policy_flags=flags)
