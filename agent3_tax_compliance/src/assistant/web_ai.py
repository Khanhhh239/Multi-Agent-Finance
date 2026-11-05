"""HTTP endpoints of the controlled AI layer, the explanation dossier and law alerts. Imported at the end of web.py.

One model job at a time (the laptop GPU has 6 GB): jobs run in a background thread under a lock, and the page polls status.
Every AI output is stored with model and version under ws/ai/, and becomes a finding only through a deterministic rule
or a person's decision.
"""
import csv
import io
import json
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from ..lawbase import rag
from ..lawbase.store import Corpus
from . import ai as ai_mod
from .web import LAW_DB, _as_of, _json, _run, app, ws_path

_jobs: dict = {}
_gpu = threading.Lock()


def _report(ws: Path) -> dict:
    p = ws / 'out' / 'report.json'
    if not p.exists():
        raise HTTPException(409, 'chưa chạy phân tích; bấm Chạy phân tích trước')
    return json.loads(p.read_text(encoding='utf-8'))


def _read(path: Path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    tmp.replace(path)


def _start(wid: str, task: str, work):
    job = _jobs.get(wid)
    if job and job['running']:
        raise HTTPException(409, f'đang chạy việc {job["task"]}; chờ xong rồi thử lại')
    job = _jobs[wid] = dict(task=task, running=True, done=0, total=0, error=None, started=datetime.now().isoformat(timespec='seconds'))

    def run():
        try:
            with _gpu:
                work(job)
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
    labels = _read(ws / 'ai' / 'line_labels.json', {})
    flagged = sum(1 for r in labels.values() if ai_mod.flagged(r['labels']))
    return _json(dict(job=_jobs.get(wid), model=ai_mod.MODEL, labelled_invoices=len(labels), flagged_invoices=flagged,
                      proposals=_read(ws / 'ai' / 'bank_links.json', [])))


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
    industry = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))['profile'].get('industry', [])
    invs = [i for i in rep['invoices'] if i['role'] == 'PURCHASE' and not i.get('duplicate_of') and i.get('descriptions')]

    def work(job):
        job['total'] = len(invs)
        model = ai_mod.AI()
        path = ws / 'ai' / 'line_labels.json'
        labels = _read(path, {})
        for n, inv in enumerate(invs, 1):
            labels[inv['key']] = ai_mod.classify_lines(model, inv, industry)
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
    props = _read(ws / 'ai' / 'bank_links.json', [])
    prop = next((p for p in props if p['txn_id'] == d.get('txn_id') and p['invoice_key'] == d.get('invoice_key')), None)
    if not prop:
        raise HTTPException(404, 'không có đề xuất này')
    if d.get('accept'):
        if not (d.get('by') or '').strip():
            raise HTTPException(422, 'cần tên người duyệt')
        path = ws / 'decisions.json'
        items = [x for x in _read(path, []) if x['invoice_key'] != prop['invoice_key']]
        items.append(dict(invoice_key=prop['invoice_key'], action='PAYMENT_EVIDENCE_ATTACHED', by=d['by'].strip(), at=date.today().isoformat(),
                          evidence=f'Giao dịch {prop["source"]} ngày {prop["booked"]}, nội dung "{prop["description"]}" '
                                   f'(mô hình đề xuất theo cụm "{prop["name_in_text"]}", người duyệt xác nhận)'))
        _write(path, items)
    else:
        rej = _read(ws / 'ai' / 'bank_rejected.json', [])
        rej.append(dict(txn_id=prop['txn_id'], invoice_key=prop['invoice_key'], by=d.get('by'), at=date.today().isoformat()))
        _write(ws / 'ai' / 'bank_rejected.json', rej)
    _write(ws / 'ai' / 'bank_links.json', [p for p in props if p is not prop])
    rep = _run(ws)
    return _json(dict(ok=True, totals=rep.totals))


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
        z.writestr('04_quyet_dinh_nguoi_duyet.json', json.dumps([d for d in _read(ws / 'decisions.json', []) if d['invoice_key'] in keys], ensure_ascii=False, indent=1))
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
# Title words that make a change relevant to a small or medium enterprise, and words of public-sector topics that do not.
SME_TOPICS = ('thue gia tri gia tang', 'thu nhap doanh nghiep', 'thu nhap ca nhan', 'hoa don', 'chung tu', 'quan ly thue', 'ho kinh doanh',
              'giam thue', 'mien thue', 'gia han', 'khau tru', 'hoan thue', 'xu phat', 'ke toan doanh nghiep', 'che do ke toan',
              'doanh nghiep nho va vua', 'nop thue', 'khai thue', 'thuong mai dien tu', 'tieu thu dac biet')
SME_NOISE = ('thi hanh an', 'ngan sach nha nuoc', 'kho bac', 'du tru quoc gia', 'quoc phong', 'oda', 'hanh chinh su nghiep', 'vay, tra no',
             'vay tra no', 'cong chuc', 'trang phuc', 'phu hieu', 'ngan hang nha nuoc', 'to chuc tin dung', 'boi duong')


@app.get('/api/law/alerts')
def law_alerts(days_back: int = 150, days_ahead: int = 180):
    if not LAW_DB.exists():
        return []
    today = date.today()
    lo, hi = (today - timedelta(days=days_back)).isoformat(), (today + timedelta(days=days_ahead)).isoformat()
    c = Corpus(LAW_DB)
    try:
        new = [dict(r, kind='EFFECTIVE') for r in c.db.execute(
            """SELECT d.doc_id, d.doc_type, d.doc_num, d.title, d.eff_from AS day, d.url FROM documents d
               WHERE d.indexed=1 AND d.doc_type IN ('Luật','Nghị định','Thông tư','Nghị quyết') AND d.eff_from BETWEEN ? AND ?
               ORDER BY d.eff_from DESC""", (lo, hi))]
        ended = [dict(r, kind='ENDED') for r in c.db.execute(
            """SELECT d.doc_id, d.doc_type, d.doc_num, d.title, v.eff_to AS day, d.url, v.by_doc_num FROM validity v JOIN documents d USING(doc_id)
               WHERE v.eff_to BETWEEN ? AND ? AND d.doc_type NOT LIKE 'Văn bản hợp nhất%' ORDER BY v.eff_to DESC""", (lo, hi))]
        from ..extraction.xml_context import fold
        def relevant(r):
            t = fold(r['title'])
            if any(w in t for w in SME_NOISE):
                return 0
            return sum(w in t for w in SME_TOPICS)
        rows = [dict(r, relevance=relevant(r)) for r in new + ended]
        return sorted([r for r in rows if r['relevance'] > 0], key=lambda r: (-r['relevance'], r['day']), reverse=False)
    finally:
        c.close()


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
    """Per filing period: output VAT from sales invoices; input VAT split into at risk, needs review and the rest.
    A reference table for preparing the return, not the official form: the indicator codes of the current form are not
    read from the corpus yet, so none are printed."""
    from decimal import Decimal
    ws = ws_path(wid)
    rep = _report(ws)
    period_kind = json.loads((ws / 'pack.json').read_text(encoding='utf-8'))['profile'].get('filing_period', 'MONTH')
    key = lambda d: (f'Quý {(int(d[5:7]) - 1) // 3 + 1}/{d[:4]}' if period_kind == 'QUARTER' else f'Tháng {d[5:7]}/{d[:4]}')  # noqa: E731
    risk, review = {}, {}
    for it in rep['items']:
        k = it['invoice_keys'][0] if it['invoice_keys'] else None
        if not k:
            continue
        target = risk if it['status'] == 'AT_RISK' else review if it['status'] == 'REVIEW' else None
        if target is not None:
            target[k] = max(target.get(k, Decimal(0)), Decimal(str(it['amount'])))
    rows = {}
    for i in rep['invoices']:
        if i.get('duplicate_of') or not i.get('issue_date') or i.get('vat') is None:
            continue
        r = rows.setdefault(key(i['issue_date']), dict(output_vat=Decimal(0), sales=0, input_vat=Decimal(0), purchases=0, at_risk=Decimal(0), review=0))
        vat = Decimal(str(i['vat']))
        if i['role'] == 'SALE':
            r['output_vat'] += vat
            r['sales'] += 1
        else:
            r['input_vat'] += vat
            r['purchases'] += 1
            r['at_risk'] += risk.get(i['key'], Decimal(0))
            r['review'] += int(i['key'] in review and i['key'] not in risk)
    out = []
    for p, r in sorted(rows.items(), key=lambda kv: (kv[0][-4:], kv[0])):
        safe = r['input_vat'] - r['at_risk']
        out.append(dict(period=p, **r, input_safe=safe, net=r['output_vat'] - safe))
    return _json(dict(period_kind=period_kind, rows=out, note='Bảng số liệu tham khảo để lập tờ khai; chưa ghi mã chỉ tiêu vì mẫu tờ khai hiện hành chưa được đọc từ kho luật. '
                      'Thuế đầu vào an toàn = tổng thuế đầu vào trừ phần có nguy cơ bị loại; phần cần xem vẫn tính vào an toàn cho tới khi người duyệt quyết định. Bản nhập trùng của một hóa đơn không được tính, nên tổng có nguy cơ ở đây không gồm thuế của bản trùng.'))


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
