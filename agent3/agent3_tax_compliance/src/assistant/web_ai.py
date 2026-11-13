"""HTTP endpoints of the controlled AI layer, the explanation dossier and law alerts. Imported at the end of web.py.

One model job at a time (the laptop GPU has 6 GB): jobs run in a background thread under a lock, and the page polls status.
Every AI output is stored with model and version under ws/ai/, and becomes a finding only through a deterministic rule
or a person's decision.
"""
import csv
import io
import json
import threading
import contextvars
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from ..lawbase import rag
from ..lawbase.store import Corpus
from . import ai as ai_mod
from . import accounting, decisions as decision_store
from .web import LAW_DB, _as_of, _json, _run, app, ws_path
from . import web as _web
from .platform_context import LOCK_HELD, writing

_jobs: dict = {}
_gpu = threading.Lock()


def _report(ws: Path) -> dict:
    p = ws / 'out' / 'report.json'
    if not p.exists():
        raise HTTPException(409, 'chưa chạy phân tích; bấm Chạy phân tích trước')
    report = json.loads(p.read_text(encoding='utf-8'))
    if report.get('meta', {}).get('schema_version') != 2:
        raise HTTPException(409, 'Báo cáo phiên bản cũ được giữ nguyên; chạy phân tích lại trước khi dùng chức năng này.')
    return report


def _read(path: Path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def _write(path: Path, data):
    with writing():
        _web.bridge.require()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
        _web.bridge.require()
        tmp.replace(path)


def _start(wid: str, task: str, work):
    context = contextvars.copy_context()
    revision = _web.bridge.require(wid)['profile_revision']
    job = _jobs.get(wid)
    if job and job['running']:
        raise HTTPException(409, f'đang chạy việc {job["task"]}; chờ xong rồi thử lại')
    job = _jobs[wid] = dict(task=task, profile_revision=revision, running=True, done=0, total=0, error=None, started=datetime.now().isoformat(timespec='seconds'))

    def run():
        try:
            with _gpu:
                def guarded():
                    LOCK_HELD.set(False)  # The request releases its lock before this background job writes.
                    _web.bridge.require(wid)
                    work(job)
                    _web.bridge.require(wid)
                context.run(guarded)
        except Exception as e:  # noqa: BLE001 - shown to the user
            job['error'] = f'{type(e).__name__}: {str(e)[:300]}'
        finally:
            job['running'] = False
    threading.Thread(target=run, daemon=True).start()
    return job


# ----------------------------------------------------------------------------- status
@app.get('/api/workspaces/{wid}/ai')
def ai_status(wid: str):
    ws = ws_path(wid)
    job = _jobs.get(wid)
    if job and job.get('profile_revision') != _web.bridge.require(wid)['profile_revision']:
        job = None
    labels = _read(ws / 'ai' / 'line_labels.json', {})
    flagged = sum(1 for r in labels.values() if ai_mod.flagged(r['labels']))
    return _json(dict(job=job, model=ai_mod.MODEL, labelled_invoices=len(labels), flagged_invoices=flagged,
                      proposals=_proposals(ws)))


def _proposals(ws):
    report = _read(ws / 'out/report.json', {})
    used = {t for m in report.get('matches', []) if m['status'] == 'MATCHED' for t in m['txn_ids']}
    rejected = {(r['txn_id'], r['invoice_key']) for r in _read(ws / 'ai/bank_rejected.json', [])}
    rejected.update((r['txn_id'], r['invoice_key']) for r in decision_store.history(ws) if r['action'] == 'REJECT_BANK_PROPOSAL')
    return [p for p in _read(ws / 'ai/bank_links.json', []) if p['txn_id'] not in used and (p['txn_id'], p['invoice_key']) not in rejected]


# ----------------------------------------------------------------------------- A4
@app.post('/api/workspaces/{wid}/ai/explain')
async def ai_explain(wid: str, request: Request):
    ws = ws_path(wid)
    rep = _report(ws)
    idx = (await request.json()).get('index')
    if not isinstance(idx, int) or not 0 <= idx < len(rep['items']):
        raise HTTPException(400, 'không có việc này')
    item = rep['items'][idx]
    inv = next((i for i in rep['invoices'] if item['invoice_keys'] and i['key'] == item['invoice_keys'][0]), None)
    if inv:
        inv = dict(inv, display=f'{inv.get("template") or ""}{inv.get("symbol") or ""}/{inv.get("number") or ""}')
    if not _gpu.acquire(timeout=1):
        return _json(ai_mod.explain(None, item, inv).__dict__ | dict(note='mô hình đang bận với việc khác; dùng câu mẫu'))
    try:
        return _json(ai_mod.explain(ai_mod.AI(), item, inv).__dict__)
    finally:
        _gpu.release()


# ----------------------------------------------------------------------------- A1
@app.post('/api/workspaces/{wid}/ai/classify')
def ai_classify(wid: str):
    ws = ws_path(wid)
    rep = _report(ws)
    pack_data = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))
    industry = pack_data['profile'].get('industry', [])
    extra = tuple((c['name'], c['description']) for c in pack_data.get('ai_categories', []))
    invs = [i for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i.get('duplicate_of') and i.get('descriptions')]

    def work(job):
        job['total'] = len(invs)
        model = ai_mod.AI()
        path = ws / 'ai' / 'line_labels.json'
        labels = _read(path, {})
        for n, inv in enumerate(invs, 1):
            labels[inv['key']] = ai_mod.classify_lines(model, inv, industry, extra)
            job['done'] = n
            if n % 5 == 0 or n == len(invs):
                _write(path, labels)
        _run(ws)
        job['result'] = dict(flagged=sum(1 for r in labels.values() if ai_mod.flagged(r['labels'])))
    return _start(wid, 'phân loại dòng hàng', work)


# ----------------------------------------------------------------------------- A2
@app.post('/api/workspaces/{wid}/ai/bank')
def ai_bank(wid: str):
    ws = ws_path(wid)
    rep = _report(ws)
    used = {t for m in rep['matches'] if m['status'] == 'MATCHED' for t in m['txn_ids']}
    settled = {k for m in rep['matches'] if m['status'] == 'MATCHED' for k in m['invoice_keys']}
    rejected = {(r['txn_id'], r['invoice_key']) for r in _read(ws / 'ai' / 'bank_rejected.json', [])}
    purchases = [i for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i.get('duplicate_of')]

    def work(job):
        job['total'] = len(rep['transactions'])
        props = ai_mod.bank_proposals(ai_mod.AI(), rep['transactions'], purchases, used, settled)
        props = [p for p in props if (p['txn_id'], p['invoice_key']) not in rejected]
        _write(ws / 'ai' / 'bank_links.json', props)
        job['done'] = job['total']
        job['result'] = dict(proposals=len(props))
    return _start(wid, 'đọc nội dung chuyển khoản', work)


@app.post('/api/workspaces/{wid}/ai/bank/decide')
async def ai_bank_decide(wid: str, request: Request):
    ws = ws_path(wid)
    d = await request.json()
    if not isinstance(d, dict) or type(d.get('accept')) is not bool:
        raise HTTPException(422, 'Cần quyết định xác nhận hoặc bác bỏ hợp lệ.')
    if not request.headers.get('If-Match') or not d.get('request_id') or not d.get('report_revision'):
        raise HTTPException(428, 'Cần phiên bản quyết định, báo cáo và mã yêu cầu.')
    d.update(action='PAYMENT_EVIDENCE_ATTACHED' if d.get('accept') else 'REJECT_BANK_PROPOSAL',
             txn_ids=[d.get('txn_id')] if d.get('accept') else [],
             evidence=d.get('evidence') or 'Người duyệt kiểm tra đề xuất ghép ngân hàng')
    if not decision_store.retry(ws, d):
        prop = next((p for p in _proposals(ws) if p['txn_id'] == d.get('txn_id') and p['invoice_key'] == d.get('invoice_key')), None)
        if not prop:
            raise HTTPException(404, 'Không có đề xuất đang chờ này.')
    return await _web.save_decisions(wid, request, d)


# ----------------------------------------------------------------------------- A3 + F5: explanation letter and dossier
@app.post('/api/workspaces/{wid}/dossier')
async def dossier(wid: str, request: Request):
    ws = ws_path(wid)
    rep = _report(ws)
    body = await request.json()
    keys = [k for k in body.get('invoice_keys', []) if any(i['key'] == k for i in rep['invoices'])]
    if not keys:
        raise HTTPException(422, 'chọn ít nhất một hóa đơn')
    request_text = (body.get('request_text') or '').strip()
    company = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))['profile']
    facts = ai_mod.letter_facts(rep, keys)
    passages = []
    if LAW_DB.exists():
        query = request_text or ' '.join(it['title'] for it in rep['items'] if set(it['invoice_keys']) & set(keys))
        c = Corpus(LAW_DB)
        try:
            passages = [p.__dict__ for p in rag.pack(c, query or 'khấu trừ thuế giá trị gia tăng đầu vào', _as_of(ws), k=4, budget_tokens=2200)]
        finally:
            c.close()
    with _gpu:
        letter = ai_mod.draft_letter(ai_mod.AI(), company, facts, passages, request_text)
    _web.bridge.require(ws.name)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = ws / 'out' / 'dossier'
    out.mkdir(parents=True, exist_ok=True)
    name = f'ho_so_giai_trinh_{stamp}.zip'
    invs = {i['key']: i for i in rep['invoices']}
    txns = {t['txn_id']: t for t in rep['transactions']}
    md = [f'# Bản nháp thư giải trình ({"mô hình soạn, đã kiểm tra" if letter["mode"] == "AI_VERIFIED" else "thư mẫu"})', '',
          f'Doanh nghiệp: {company.get("legal_name")}, mã số thuế {company.get("tax_code")}', '']
    if request_text:
        md += ['## Nội dung công văn', '', request_text, '']
    md += ['## Thư', ''] + [f'{p["text"]}  \n<sub>Căn cứ: {", ".join(p["fact_ids"] + p["passage_ids"]) or "không"}</sub>\n' for p in letter['paragraphs']]
    md += ['## Dữ kiện (F)', ''] + [f'- {f["id"]}: {f["text"]}' for f in facts]
    md += ['', '## Điều khoản (P)', ''] + [f'- {p["pid"]}: {p["path"]} ({p["url"]})\n\n  > {p["text"][:1500]}' for p in passages]
    md += ['', 'Bản nháp do hệ thống tạo trên máy; người có thẩm quyền phải đọc, sửa và ký trước khi gửi.']
    with zipfile.ZipFile(out / name, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('01_thu_giai_trinh_ban_nhap.md', '\n'.join(md))
        for k in keys:
            inv = invs[k]
            folder = ws / ('invoices/purchase' if inv['role'] == 'PURCHASE' else 'invoices/sales')
            if (folder / inv['file']).exists():
                z.write(folder / inv['file'], f'02_hoa_don/{inv["file"]}')
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['hóa đơn', 'ngày giao dịch', 'số tiền', 'nội dung', 'đối ứng', 'nguồn', 'cách ghép'])
        for m in rep['matches']:
            if set(m['invoice_keys']) & set(keys):
                for tid in m['txn_ids']:
                    t = txns.get(tid, {})
                    w.writerow([';'.join(m['invoice_keys']), t.get('booked'), t.get('amount'), t.get('description'), t.get('counterparty_name'), t.get('source'), m.get('method')])
                if not m['txn_ids']:
                    w.writerow([';'.join(m['invoice_keys']), '', '', m.get('note'), '', 'quyết định của người duyệt', m.get('method')])
        z.writestr('03_chung_tu_thanh_toan.csv', '﻿' + buf.getvalue())
        z.writestr('04_quyet_dinh_nguoi_duyet.json', json.dumps([d for d in decision_store.history(ws) if d.get('invoice_key') in keys], ensure_ascii=False, indent=1))
        z.writestr('05_ket_qua_ra_soat.json', json.dumps([it for it in rep['items'] if set(it['invoice_keys']) & set(keys)], ensure_ascii=False, indent=1, default=str))
    return _json(dict(letter=letter, facts=facts, passages=[dict(pid=p['pid'], path=p['path'], url=p['url']) for p in passages], file=name))


@app.get('/api/workspaces/{wid}/dossier/{name}')
def dossier_file(wid: str, name: str):
    ws = ws_path(wid)
    p = ws / 'out' / 'dossier' / Path(name).name
    if not p.exists() or p.suffix != '.zip':
        raise HTTPException(404, 'không có tệp')
    return FileResponse(p, media_type='application/zip', filename=p.name)


# ----------------------------------------------------------------------------- A5: law alerts
@app.get('/api/law/alerts')
def law_alerts(days_back: int = 150, days_ahead: int = 180):
    """Relevance by meaning against the topics of the shared catalog (law_topics.json, admin page)."""
    if not LAW_DB.exists():
        return []
    from .catalog import law_alerts as alerts
    return _json(alerts(LAW_DB, date.today(), days_back, days_ahead))


@app.post('/api/law/alerts/{doc_id}/summary')
def law_alert_summary(doc_id: str):
    if not LAW_DB.exists():
        raise HTTPException(404, 'chưa có kho luật')
    c = Corpus(LAW_DB)
    try:
        d = c.db.execute('SELECT eff_from, issue_date FROM documents WHERE doc_id=?', (doc_id,)).fetchone()
        if not d:
            raise HTTPException(404, 'không có văn bản')
        day = max(date.today(), date.fromisoformat(d['eff_from'] or d['issue_date'] or date.today().isoformat()))
        q = ('Doanh nghiệp nhỏ và vừa cần biết gì: đối tượng áp dụng, nghĩa vụ kê khai, nộp thuế, hóa đơn, khấu trừ, thời hạn, '
             'mức phạt, ngày có hiệu lực')
        with _gpu:
            res = rag.answer(c, q, day, None, min_coverage=0.0, k=6, budget_tokens=5000, doc_ids=[doc_id])
        return _json(res.to_dict())
    finally:
        c.close()


# ----------------------------------------------------------------------------- F3: VAT figures per period (reference table)
@app.get('/api/workspaces/{wid}/vat-summary')
def vat_summary(wid: str):
    ws = ws_path(wid)
    profile = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))['profile']
    return _json(accounting.vat_summary(_report(ws), profile, _read(ws / 'declared.json', {})))



# ----------------------------------------------------------------------------- F6: risk list from a file
@app.put('/api/workspaces/{wid}/risk-list')
async def risk_list(wid: str, name: str, as_of: str, request: Request, source: str = ''):
    import re
    from .pack import mst_checksum_ok
    from .web import _pack_data, _save_pack
    ws = ws_path(wid)
    try:
        date.fromisoformat(as_of)
    except ValueError:
        raise HTTPException(422, 'ngày của danh sách không hợp lệ (YYYY-MM-DD)')
    text = (await request.body()).decode('utf-8-sig', 'replace')
    found = list(dict.fromkeys(re.findall(r'(?<!\d)(\d{10}(?:-\d{3})?)(?!\d)', text)))
    good = [t for t in found if mst_checksum_ok(t)]
    if not good:
        raise HTTPException(422, 'không thấy mã số thuế hợp lệ nào trong tệp')
    data = _pack_data(ws)
    data['reference_lists'] = [r for r in data.get('reference_lists', []) if r['name'] != name] + [dict(name=name, as_of=as_of, source=source, tax_ids=good)]
    _save_pack(ws, data)
    return dict(ok=True, tax_ids=len(good), rejected=[t for t in found if t not in good][:20])


# ----------------------------------------------------------------------------- A3: exposure per item
@app.get('/api/workspaces/{wid}/exposure')
def exposure(wid: str):
    from .rules import load_ruleset
    from .pipeline import DEFAULT_RULESET
    return _json(accounting.exposure(_report(ws_path(wid)), load_ruleset(DEFAULT_RULESET)))



# ----------------------------------------------------------------------------- A1: declared figures versus invoices
@app.get('/api/workspaces/{wid}/declared')
def declared_get(wid: str):
    return _read(ws_path(wid) / 'declared.json', {})


@app.put('/api/workspaces/{wid}/declared')
async def declared_put(wid: str, request: Request):
    ws = ws_path(wid)
    body = await request.json()
    clean = {}
    for period, v in body.items():
        row = {}
        for k in ('output_vat', 'input_vat'):
            if v.get(k) not in (None, ''):
                try:
                    row[k] = int(str(v[k]).replace('.', '').replace(',', '').strip())
                except ValueError:
                    raise HTTPException(422, f'{period}: số không hợp lệ ở {k}')
        if row:
            clean[period] = row
    _write(ws / 'declared.json', clean)
    _run(ws)
    return dict(ok=True, periods=len(clean))


# ----------------------------------------------------------------------------- B1: bulk decisions
@app.post('/api/workspaces/{wid}/decisions/bulk')
async def decisions_bulk(wid: str, request: Request):
    return await _web.save_decisions(wid, request)


def _remember_confirmed(ws: Path, keys: list, action: str):
    """C3: a line a reviewer confirmed as business use is not flagged by the AI again, on any invoice."""
    if action != 'CONFIRMED_OK':
        return
    labels = _read(ws / 'ai' / 'line_labels.json', {})
    lines = {h['line'] for k in keys for h in ai_mod.flagged(labels.get(k, {}).get('labels', []))}
    if lines:
        path = ws / 'ai' / 'confirmed_lines.json'
        _write(path, sorted(set(_read(path, [])) | lines))


@app.get('/api/workspaces/{wid}/decisions/suggest')
def decisions_suggest(wid: str, key: str, code: str):
    """A decision proposed from the reviewer's own earlier decisions: same rule family, and the same seller or (for item
    purpose) a line that reads alike. Only prefills the form; the reviewer still checks the evidence and saves."""
    from ..extraction.xml_context import fold, similarity
    ws = ws_path(wid)
    rep = _report(ws)
    past = decision_store.history(ws)
    if not past:
        return dict(suggestion=None)
    invs = {i['key']: i for i in rep['invoices']}
    target = invs.get(key)
    if not target:
        return dict(suggestion=None)
    fam = code.split('_')[0]
    codes_of = {}
    for it in rep['items']:
        for k in it['invoice_keys']:
            codes_of.setdefault(k, set()).add(it['code'].split('_')[0])
    best, why = None, ''
    for d in reversed(past):
        k = d.get('invoice_key')
        if k == key or k not in invs or fam not in codes_of.get(k, set()):
            continue
        other = invs[k]
        if other.get('seller_tax_id') and other.get('seller_tax_id') == target.get('seller_tax_id'):
            best, why = d, f'cùng người bán {other.get("seller_name")}, cùng loại cảnh báo'
            break
        if fam == 'R12':
            a = ' '.join(other.get('descriptions') or [])
            b = ' '.join(target.get('descriptions') or [])
            if a and b and similarity(fold(a), fold(b)) >= 0.6:
                best, why = d, 'tên hàng gần giống, cùng loại cảnh báo'
                break
    if not best:
        return dict(suggestion=None)
    o = invs[best['invoice_key']]
    return dict(suggestion=dict(action=best['action'], evidence=best.get('evidence', ''), by=best.get('by', ''),
                                because=f'Giống quyết định cho hóa đơn {o.get("number")} của {o.get("seller_name")} '
                                        f'({best.get("at", "")}): {why}. Kiểm tra chứng từ của hóa đơn này trước khi lưu.'))


@app.post('/api/workspaces/{wid}/decisions/remember')
async def decisions_remember(wid: str, request: Request):
    raise HTTPException(410, 'Use scoped decisions endpoint.')


# ----------------------------------------------------------------------------- B2: Excel export
@app.get('/api/workspaces/{wid}/export/{kind}.xlsx')
def export_xlsx(wid: str, kind: str):
    from .synth import _write_xlsx
    ws = ws_path(wid)
    rep = _report(ws)
    invs = {i['key']: i for i in rep['invoices']}
    if kind == 'viec-can-xu-ly':
        rows = [['Trạng thái', 'Mã', 'Việc', 'Hóa đơn', 'Ngày', 'Người bán', 'MST người bán', 'Số thuế (đồng)', 'Chi tiết', 'Việc cần làm', 'Căn cứ']]
        for it in rep['items']:
            i = invs.get(it['invoice_keys'][0]) if it['invoice_keys'] else {}
            i = i or {}
            rows.append([it['status'], it['code'], it['title'], f'{i.get("template") or ""}{i.get("symbol") or ""}/{i.get("number") or ""}' if i else '',
                         i.get('issue_date') or '', i.get('seller_name') or '', i.get('seller_tax_id') or '', Decimal(str(it['amount'])),
                         it.get('detail', ''), it.get('action', ''), ' | '.join(it.get('basis', []))])
    elif kind == 'hoa-don':
        rows = [['Vai trò', 'Hóa đơn', 'Ngày', 'Người bán', 'MST người bán', 'Người mua', 'Tiền hàng', 'Thuế', 'Tổng thanh toán', 'Lỗi kiểm tra', 'Tệp']]
        for i in rep['invoices']:
            rows.append(['Mua vào' if i['role'] == 'PURCHASE' else 'Bán ra', f'{i.get("template") or ""}{i.get("symbol") or ""}/{i.get("number") or ""}',
                         i.get('issue_date') or '', i.get('seller_name') or '', i.get('seller_tax_id') or '', i.get('buyer_name') or '',
                         Decimal(str(i['net'])) if i.get('net') is not None else '', Decimal(str(i['vat'])) if i.get('vat') is not None else '',
                         Decimal(str(i['gross'])) if i.get('gross') is not None else '', ', '.join(i.get('guard_errors', [])), i['file']])
    elif kind == 'quyet-dinh':
        rows = [['Hóa đơn', 'Thao tác', 'Chứng từ hoặc lý do', 'Người duyệt', 'Ngày ghi']]
        for d in decision_store.history(ws):
            i = invs.get(d.get('invoice_key'), {})
            rows.append([f'{i.get("template") or ""}{i.get("symbol") or ""}/{i.get("number") or ""} {i.get("seller_name") or ""}'.strip() or d.get('invoice_key', d.get('subject', '')),
                         d['action'], d['evidence'], d['by'], d.get('at', '')])
    else:
        raise HTTPException(404, 'không có bảng này')
    out = ws / 'out' / f'{kind}.xlsx'
    _web.bridge.require(ws.name)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_xlsx(out, [[str(c) if not isinstance(c, (int, float, Decimal)) else c for c in r] for r in rows])
    return FileResponse(out, filename=f'{kind}.xlsx', media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
