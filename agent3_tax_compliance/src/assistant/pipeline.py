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
from datetime import date
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
        days = (e['due'] - as_of).days
        e['status'] = f'còn {days} ngày' if days >= 0 else f'hạn đã qua {-days} ngày, kiểm tra đã nộp chưa'
        e['note'] = 'Chưa dời hạn khi trùng ngày nghỉ'
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
