"""Agent 3 web application: local API plus the static interface built from webui/.

  python -m src.assistant.web            # http://127.0.0.1:8640

Binds to 127.0.0.1 only. Files are sent as raw request bodies (no multipart dependency). Every enterprise has its own
workspace folder under data/workspaces/<id> with the layout described in pipeline.py.
"""
import dataclasses
import json
import os
import re
import shutil
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..lawbase.store import Corpus
from ..lawbase.sync import DEFAULT_DB as LAW_DB, running_sync, sync as law_sync
from . import pipeline, qa, report as report_mod
from .input_schema import FILES, guide
from . import inbox
from .intake import IntakeError, extract_zip, suggest_mapping
from .sources import read_bank_statement
from .rules import load_ruleset, param
from .pack import PackError, load_pack
from .synth import generate as generate_demo

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACES = Path(os.environ.get('AGENT3_WORKSPACES') or PROJECT / 'data/workspaces')   # the override is only for interface tests
STATIC = Path(__file__).resolve().parent / 'static'
ID = re.compile(r'^[a-z0-9][a-z0-9-]{1,40}$')

app = FastAPI(title='Agent 3 - Trợ lý thuế')
from . import admin as _admin  # noqa: E402
_admin.install(app)


def _warm_up():
    """Load the question router (embeddings of the example questions, classifier head) and the small routing model in the
    background at start, so the first question does not wait for them."""
    try:
        from .chat import engine
        r = engine.router()
        r._head()
        r._ask_model('khởi động', [next(iter(r.domains))])
    except Exception:  # noqa: BLE001 - the first question will retry and report any real failure
        pass


threading.Thread(target=_warm_up, daemon=True).start()
_law_job = dict(running=False, done=0, last='', result=None, error=None)
_lock = threading.Lock()


def _json(obj, status=200):
    return JSONResponse(json.loads(json.dumps(obj, default=report_mod._default, ensure_ascii=False)), status_code=status)


def ws_path(wid: str) -> Path:
    if not ID.match(wid):
        raise HTTPException(400, 'mã không gian làm việc không hợp lệ')
    p = WORKSPACES / wid
    if not p.exists():
        raise HTTPException(404, 'không có không gian làm việc này')
    return p


def _pack_data(ws: Path) -> dict:
    return json.loads((ws / 'pack.json').read_text(encoding='utf-8'))


def _pack_diff(old: dict, new: dict) -> list[str]:
    labels = dict(profile='hồ sơ', bank_formats='mẫu sao kê', thresholds='ngưỡng nội bộ', policies='chính sách nội bộ',
                  reference_lists='danh sách rủi ro', portal_columns='cột bảng kê cổng thuế', days_off='ngày nghỉ',
                  ai_categories='nhóm hàng riêng cho AI')
    return [labels.get(k, k) for k in sorted(set(old) | set(new)) if k not in ('pack_version',) and old.get(k) != new.get(k)]


def _save_pack(ws: Path, data: dict, by: str = ''):
    old = json.loads((ws / 'pack.json').read_text(encoding='utf-8')) if (ws / 'pack.json').exists() else {}
    tmp = ws / 'pack.json.tmp'
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        load_pack(tmp)                                   # the same invariants as the pipeline: tighten only, add flags only
    except PackError as e:
        tmp.unlink()
        raise HTTPException(422, str(e))
    tmp.replace(ws / 'pack.json')
    changed = _pack_diff(old, data)
    if changed:                                          # who changed which part of the configuration, and when
        hist_path = ws / 'pack_history.json'
        hist = json.loads(hist_path.read_text(encoding='utf-8')) if hist_path.exists() else []
        hist.append(dict(at=datetime.now().isoformat(timespec='seconds'), by=by or 'không ghi', changed=changed,
                         created=not old))
        hist_path.write_text(json.dumps(hist[-200:], ensure_ascii=False, indent=1), encoding='utf-8')


def _as_of(ws: Path) -> date:
    labels = ws / 'labels.json'
    if labels.exists():
        return date.fromisoformat(json.loads(labels.read_text(encoding='utf-8'))['as_of'])
    return date.today()


# ----------------------------------------------------------------------------- input guide and workspaces
@app.get('/api/schema')
def schema():
    return guide()


@app.get('/api/workspaces')
def list_workspaces():
    WORKSPACES.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(WORKSPACES.iterdir()):
        if (p / 'pack.json').exists():
            d = _pack_data(p)
            files = {f['key']: len(list((p / f['folder']).glob('*'))) if f['folder'] and (p / f['folder']).exists() else 0 for f in FILES}
            out.append(dict(id=p.name, name=d['profile']['legal_name'], tax_code=d['profile']['tax_code'], simulated=d.get('simulated', False),
                            files=files, has_report=(p / 'out' / 'report.json').exists()))
    return out


@app.post('/api/workspaces')
async def create_workspace(request: Request):
    body = await request.json()
    wid = re.sub(r'[^a-z0-9-]', '-', (body.get('id') or body.get('profile', {}).get('tax_code') or '').lower()).strip('-')
    if not ID.match(wid):
        raise HTTPException(400, 'cần mã số thuế hoặc mã không gian làm việc')
    p = WORKSPACES / wid
    if p.exists():
        raise HTTPException(409, 'đã có không gian làm việc này')
    p.mkdir(parents=True)
    data = dict(pack_version=1, profile=body['profile'], bank_formats=body.get('bank_formats', []), thresholds=body.get('thresholds', {}),
                policies=body.get('policies', []), reference_lists=body.get('reference_lists', []), days_off=body.get('days_off', []),
                ai_categories=body.get('ai_categories', []))
    src_id = body.get('copy_from')
    if src_id:                                           # reuse another enterprise's set-up; profile and decisions stay its own
        src = ws_path(src_id)
        sd = _pack_data(src)
        for k in ('bank_formats', 'thresholds', 'policies', 'reference_lists', 'portal_columns', 'ai_categories', 'days_off'):
            if sd.get(k) and not body.get(k):
                data[k] = sd[k]
    try:
        _save_pack(p, data, body.get('by', ''))
    except HTTPException:
        shutil.rmtree(p)
        raise
    return dict(id=wid)


@app.post('/api/demo')
def create_demo():
    p = WORKSPACES / 'mo-phong-minh-an'
    generate_demo(p)
    return dict(id=p.name)


@app.get('/api/workspaces/{wid}/pack')
def get_pack(wid: str):
    return _pack_data(ws_path(wid))


@app.put('/api/workspaces/{wid}/pack')
async def put_pack(wid: str, request: Request, by: str = ''):
    ws = ws_path(wid)
    _save_pack(ws, await request.json(), by)
    return dict(ok=True)


@app.get('/api/workspaces/{wid}/pack/history')
def pack_history(wid: str):
    p = ws_path(wid) / 'pack_history.json'
    return list(reversed(json.loads(p.read_text(encoding='utf-8')))) if p.exists() else []


@app.post('/api/workspaces/{wid}/portal/suggest')
def portal_suggest(wid: str):
    """Header row of the loaded portal list, so the user can map its columns when the portal changes its layout."""
    from .sources import DEFAULT_PORTAL_COLUMNS, read_table
    ws = ws_path(wid)
    files = sorted((ws / 'portal').glob('purchase_list.*')) if (ws / 'portal').exists() else []
    if not files:
        raise HTTPException(404, 'chưa nạp bảng kê cổng thuế')
    rows = read_table(files[0])
    head = max(rows[:30], key=lambda r: sum(bool(str(c).strip()) for c in r), default=[])
    current = _pack_data(ws).get('portal_columns') or DEFAULT_PORTAL_COLUMNS
    return dict(headers=[str(c) for c in head if str(c).strip()], current=current,
                fields=dict(seller_tax_id='Mã số thuế người bán', template='Ký hiệu mẫu số', symbol='Ký hiệu hóa đơn', number='Số hóa đơn',
                            issue_date='Ngày lập', vat='Tổng tiền thuế', gross='Tổng tiền thanh toán'))


def _industry_codes(industry: list[str]) -> set[str]:
    return {m.group(1)[:2] for x in industry or [] for m in [re.match(r'\s*(\d{2,5})', str(x))] if m}


@app.get('/api/presets')
def presets(industry: str = ''):
    """Spending-policy presets from the shared catalog (configs/assistant/catalog/policy_presets.json, edited on the
    protected settings page). A preset is recommended when it fits one of the enterprise's industry codes, or is marked
    recommended for everyone."""
    from .catalog import policy_presets
    codes = _industry_codes([x for x in industry.split(';') if x.strip()])
    out = []
    for p in policy_presets():
        fit = bool(set(p.get('for', [])) & codes)
        out.append(dict(p, recommended=fit or bool(p.get('recommended')), industry_fit=fit))
    out.sort(key=lambda p: (not p['industry_fit'], not p['recommended']))
    return dict(policies=out, industry_codes=sorted(codes))


@app.get('/api/check-tax-id')
def check_tax_id(mst: str):
    """Offline check of a tax code: format and check digit. Whether it is registered and active can only be looked up on the
    tax authority's portal, which this local application does not call."""
    from ..extraction.xml_invoice import mst_checksum_ok
    raw = (mst or '').strip()
    digits = raw.replace('-', '')
    if not digits:
        return dict(ok=False, reason='Chưa nhập mã số thuế')
    if not digits.isdigit():
        return dict(ok=False, reason='Mã số thuế chỉ gồm chữ số (chi nhánh có thêm dấu gạch: 0123456789-001)')
    if len(digits) == 12:
        return dict(ok=True, reason='Đúng dạng số định danh cá nhân 12 số (dùng thay mã số thuế cá nhân, hộ kinh doanh)', kind='personal')
    if len(digits) not in (10, 13):
        return dict(ok=False, reason=f'Mã số thuế doanh nghiệp có 10 số, chi nhánh 13 số; bạn nhập {len(digits)} số')
    if not mst_checksum_ok(digits):
        return dict(ok=False, reason='Sai số kiểm tra (chữ số thứ 10): có thể gõ nhầm một chữ số')
    kind = 'branch' if len(digits) == 13 else 'enterprise'
    return dict(ok=True, kind=kind, reason=('Đúng định dạng và số kiểm tra' + (' (mã chi nhánh)' if kind == 'branch' else '')
                                            + '. Muốn chắc mã đang hoạt động, tra cứu trên cổng của cơ quan thuế.'))



@app.put('/api/workspaces/{wid}/files/{kind}')
async def upload(wid: str, kind: str, name: str, request: Request):
    ws = ws_path(wid)
    spec = next((f for f in FILES if f['key'] == kind and f['folder']), None)
    if not spec:
        raise HTTPException(400, 'loại tệp không hợp lệ')
    clean = re.sub(r'[^\w.\-]', '_', Path(name).name)
    suffix = Path(clean).suffix.lower()
    if suffix not in spec['accept']:
        raise HTTPException(415, f'chỉ nhận {", ".join(spec["accept"])}')
    raw = await request.body()
    if len(raw) > 300 * 1024 * 1024:
        raise HTTPException(413, 'tệp quá lớn')
    folder = ws / spec['folder']
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if suffix == '.zip':
            names = extract_zip(raw, folder)
        else:
            target = folder / ('purchase_list' + suffix if kind == 'portal_list' else clean)
            target.write_bytes(raw)
            names = [target.name]
    except IntakeError as e:
        raise HTTPException(422, str(e))
    return dict(saved=names)


@app.get('/api/workspaces/{wid}/files/{kind}')
def list_files(wid: str, kind: str):
    ws = ws_path(wid)
    spec = next((f for f in FILES if f['key'] == kind and f['folder']), None)
    if not spec:
        raise HTTPException(400, 'loại tệp không hợp lệ')
    folder = ws / spec['folder']
    return sorted(p.name for p in folder.glob('*')) if folder.exists() else []


@app.post('/api/workspaces/{wid}/bank/suggest')
def bank_suggest(wid: str, name: str):
    ws = ws_path(wid)
    path = ws / 'bank' / re.sub(r'[^\w.\-]', '_', Path(name).name)
    if not path.exists():
        raise HTTPException(404, 'không có tệp sao kê này')
    try:
        return suggest_mapping(path)
    except (IntakeError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.post('/api/workspaces/{wid}/bank/formats')
async def bank_save_format(wid: str, request: Request):
    ws = ws_path(wid)
    fmt = await request.json()
    data = _pack_data(ws)
    data['bank_formats'] = [f for f in data.get('bank_formats', []) if f['name'] != fmt['name']] + [fmt]
    _save_pack(ws, data)
    return dict(ok=True, formats=len(data['bank_formats']))


@app.put('/api/workspaces/{wid}/inbox')
async def inbox_upload(wid: str, name: str, request: Request):
    """One drop zone: the file (or every member of a zip) is classified and stored where it belongs."""
    ws = ws_path(wid)
    raw = await request.body()
    if len(raw) > 300 * 1024 * 1024:
        raise HTTPException(413, 'tệp quá lớn')
    clean = re.sub(r'[^\w.\-]', '_', Path(name).name)
    pack = load_pack(ws / 'pack.json')
    try:
        files = inbox.ingest(ws, clean, raw, pack.tax_code, pack)
    except IntakeError as e:
        raise HTTPException(422, str(e))
    for rec in files:
        if rec.get('kind') == 'bank' and rec.get('saved_as'):
            _auto_bank_format(ws, rec)
    return dict(files=files)


def _auto_bank_format(ws: Path, rec: dict):
    """A statement of a bank the pack has no layout for: recognise the columns from the header and save the layout, so the
    person does not have to. Only when the date, the money and the description columns are found and the first rows
    parse; otherwise nothing is saved and the file shows the manual 'Nhận dạng cột' step. The saved layout is named after
    the file, listed under the pack's bank layouts and visible in the history."""
    path = ws / 'bank' / rec['saved_as']
    pack = load_pack(ws / 'pack.json')
    try:
        if path.suffix.lower() in ('.sta', '.mt940'):
            return
        read_bank_statement(path, pack)
        return                                           # already readable with a known layout
    except Exception as e:  # noqa: BLE001
        if 'chưa có mẫu sao kê' not in str(e):
            return
    try:
        sug = suggest_mapping(path)
    except Exception:  # noqa: BLE001
        return
    cols = sug['format']['columns']
    ok_rows = [r for r in sug['preview'] if 'error' not in r]
    if not ({'date', 'debit', 'description'} <= set(cols)) or 'credit' not in cols or len(ok_rows) < len(sug['preview']) or not ok_rows:
        return
    fmt = dict(sug['format'], name=f'Tự nhận dạng: {Path(rec["saved_as"]).stem}'[:60])
    data = _pack_data(ws)
    data['bank_formats'] = [f for f in data.get('bank_formats', []) if f['name'] != fmt['name']] + [fmt]
    try:
        _save_pack(ws, data, by='tự nhận dạng khi nạp tệp')
    except HTTPException:
        return
    rec['auto_format'] = dict(name=fmt['name'], columns=cols, missing=sug['missing'])


@app.get('/api/workspaces/{wid}/details/{kind}')
def file_details(wid: str, kind: str):
    ws = ws_path(wid)
    if kind not in inbox.KIND_FOLDER:
        raise HTTPException(400, 'loại tệp không hợp lệ')
    return _json(inbox.file_details(ws, kind, load_pack(ws / 'pack.json'), _as_of(ws)))


@app.post('/api/workspaces/{wid}/bank/preview')
async def bank_preview(wid: str, name: str, request: Request):
    ws = ws_path(wid)
    path = ws / 'bank' / re.sub(r'[^\w.\-]', '_', Path(name).name)
    if not path.exists():
        raise HTTPException(404, 'không có tệp sao kê này')
    try:
        return inbox.preview_with(path, await request.json())
    except (IntakeError, ValueError, TypeError) as e:
        raise HTTPException(422, str(e))


@app.get('/api/workspaces/{wid}/coverage')
def coverage(wid: str):
    ws = ws_path(wid)
    as_of = _as_of(ws)
    pack = load_pack(ws / 'pack.json')
    threshold = pack.thresholds.get('non_cash_threshold_override') or param(load_ruleset(pipeline.DEFAULT_RULESET), 'NON_CASH_THRESHOLD', as_of)[0]
    return _json(inbox.coverage(ws, pack, as_of, Decimal(str(threshold))))


# ----------------------------------------------------------------------------- analysis, review, questions
_REPORTS = {}


def _cached_report(ws: Path):
    """The analysis result for the current inputs. Recomputed only when a file of the workspace, the ruleset, the shared
    catalogs or the analysis date changes; with hundreds of invoices a rerun takes seconds, a cache hit milliseconds."""
    from . import catalog
    key = (str(ws), pipeline.input_digest(ws), str(_as_of(ws)), pipeline.DEFAULT_RULESET.stat().st_mtime,
           catalog.path('holidays').stat().st_mtime)
    hit = _REPORTS.get(str(ws))
    if hit and hit[0] == key:
        return hit[1], True
    rep = pipeline.run(ws, pipeline.DEFAULT_RULESET, _as_of(ws))
    _REPORTS[str(ws)] = (key, rep)
    return rep, False


def _run(ws: Path):
    try:
        rep, cached = _cached_report(ws)
        if cached and (ws / 'out' / 'report.json').exists():
            return rep
    except Exception as e:  # noqa: BLE001 - shown to the user, never hidden
        raise HTTPException(422, f'{type(e).__name__}: {e}')
    report_mod.write(rep, ws / 'out')
    return rep


@app.post('/api/workspaces/{wid}/run')
def run(wid: str):
    rep = _run(ws_path(wid))
    return _json(dataclasses.asdict(rep))


@app.get('/api/workspaces/{wid}/freshness')
def freshness(wid: str):
    """Whether the last analysis still reflects the files and decisions on disk."""
    ws = ws_path(wid)
    p = ws / 'out' / 'report.json'
    if not p.exists():
        return dict(analysed=False, stale=True)
    meta = json.loads(p.read_text(encoding='utf-8'))['meta']
    return dict(analysed=True, stale=meta.get('input_sha256') != pipeline.input_digest(ws), as_of=meta.get('as_of'))


@app.get('/api/workspaces/{wid}/report')
def get_report(wid: str):
    p = ws_path(wid) / 'out' / 'report.json'
    if not p.exists():
        raise HTTPException(404, 'chưa chạy phân tích')
    return JSONResponse(json.loads(p.read_text(encoding='utf-8')))


@app.get('/api/workspaces/{wid}/report.html')
def get_report_html(wid: str):
    p = ws_path(wid) / 'out' / 'report.html'
    if not p.exists():
        raise HTTPException(404, 'chưa chạy phân tích')
    return FileResponse(p, media_type='text/html')


@app.post('/api/workspaces/{wid}/decisions')
async def add_decision(wid: str, request: Request):
    ws = ws_path(wid)
    d = await request.json()
    if d.get('action') not in ('PAYMENT_EVIDENCE_ATTACHED', 'NOT_CLAIMED', 'CONFIRMED_OK') or not d.get('evidence') or not d.get('by') or not d.get('invoice_key'):
        raise HTTPException(422, 'cần mã hóa đơn, thao tác, chứng từ và người duyệt')
    path = ws / 'decisions.json'
    items = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    items = [x for x in items if x['invoice_key'] != d['invoice_key']] + [dict(invoice_key=d['invoice_key'], action=d['action'],
                                                                               evidence=d['evidence'], by=d['by'], at=date.today().isoformat())]
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    if d['action'] == 'CONFIRMED_OK':
        from .web_ai import _remember_confirmed
        _remember_confirmed(ws, [d['invoice_key']], d['action'])
    rep = _run(ws)
    return _json(dict(totals=rep.totals, decisions=len(items)))


@app.post('/api/workspaces/{wid}/ask')
async def ask(wid: str, request: Request):
    ws = ws_path(wid)
    body = await request.json()
    from .chat import engine
    rep = _run(ws)
    ctx = engine.ChatContext(ws, pipeline.DEFAULT_RULESET, _as_of(ws), rep, LAW_DB if LAW_DB.exists() else None)
    q = str(body.get('question', '')).strip()[:500]
    if not q:
        raise HTTPException(422, 'câu hỏi rỗng')
    try:
        return engine.answer(q, ctx, body.get('domain'))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get('/api/chat/guide')
def chat_guide():
    from .chat import engine
    return engine.guide()


@app.get('/api/workspaces/{wid}/chat/suggestions')
def chat_suggestions(wid: str):
    from .chat import engine
    ws = ws_path(wid)
    rep = _run(ws)
    return engine.suggestions(engine.ChatContext(ws, pipeline.DEFAULT_RULESET, _as_of(ws), rep, None))


# ----------------------------------------------------------------------------- legal corpus
@app.get('/api/law/status')
def law_status():
    if not LAW_DB.exists():
        return dict(stats=None, job=_law_job)
    c = Corpus(LAW_DB)
    try:
        job = dict(_law_job)
        other = running_sync(LAW_DB)
        if other and not job['running']:                 # a sync started from the command line or another process
            job.update(running=True, external=True, done=other.get('done', 0), last=other.get('last') or '')
        return _json(dict(stats=c.stats(), job=job,
                          changes=[dict(r) for r in c.db.execute('SELECT ch.snapshot_id, ch.kind, ch.detail, d.doc_num FROM changes ch '
                                                                 'LEFT JOIN documents d USING(doc_id) ORDER BY snapshot_id DESC LIMIT 30')]))
    finally:
        c.close()


@app.get('/api/law/search')
def law_search(q: str, as_of: str | None = None, k: int = 10):
    if not LAW_DB.exists():
        raise HTTPException(404, 'chưa có kho luật; hãy đồng bộ')
    c = Corpus(LAW_DB)
    try:
        return [dict(doc_id=r['doc_id'], doc_num=r['doc_num'], doc_type=r['doc_type'], path=r['path'], text=c.unit_text(r['doc_id'], r['prov_id']),
                     eff_from=r['eff_from'], status=r['status_name'], score=round(r['rank'], 3), url=c.db.execute(
                         'SELECT url FROM documents WHERE doc_id=?', (r['doc_id'],)).fetchone()[0])
                for r in c.search(q, date.fromisoformat(as_of) if as_of else date.today(), k)]
    finally:
        c.close()


@app.get('/api/law/docs')
def law_docs(q: str = ''):
    c = Corpus(LAW_DB)
    try:
        rows = c.db.execute("SELECT d.doc_id, d.doc_num, d.doc_type, d.title, d.issue_date, d.eff_from, d.eff_to, d.status_name, d.n_provisions, "
                            "d.n_chunks, d.structure, d.url, d.indexed, d.core, v.eff_to AS ended_on, v.by_doc_num AS ended_by "
                            "FROM documents d LEFT JOIN validity v USING(doc_id) WHERE (d.doc_num LIKE ? OR d.title LIKE ?) "
                            "ORDER BY d.indexed DESC, d.issue_date DESC LIMIT 400", (f'%{q}%', f'%{q}%'))
        return [dict(r) for r in rows]
    finally:
        c.close()


@app.get('/api/law/docs/{doc_id}')
def law_doc(doc_id: str):
    c = Corpus(LAW_DB)
    try:
        d = c.db.execute('SELECT * FROM documents WHERE doc_id=?', (doc_id,)).fetchone()
        if not d:
            raise HTTPException(404, 'không có văn bản')
        provs = [dict(r) for r in c.db.execute('SELECT prov_id, level, label, heading, text FROM provisions WHERE doc_id=? ORDER BY ord', (doc_id,))]
        v = c.db.execute('SELECT v.*, (SELECT path FROM chunks k WHERE k.doc_id=v.by_doc_id AND k.prov_id=v.by_prov_id LIMIT 1) AS by_path '
                         'FROM validity v WHERE v.doc_id=?', (doc_id,)).fetchone()
        notes = [dict(r) for r in c.db.execute('SELECT by_doc_num, kind, quote FROM validity_notes WHERE doc_id=?', (doc_id,))]
        return dict(doc=dict(d), provisions=provs, ended=dict(v) if v else None, validity_notes=notes)
    finally:
        c.close()


@app.post('/api/law/sync')
def law_sync_start(core_only: bool = False):
    with _lock:
        if _law_job['running']:
            return _law_job
        if running_sync(LAW_DB):
            raise HTTPException(409, 'một lần đồng bộ khác đang chạy (từ dòng lệnh); chờ xong rồi thử lại')
        _law_job.update(running=True, done=0, last='', result=None, error=None)

    def work():
        try:
            rep = law_sync(core_only=core_only, progress=lambda n, m: _law_job.update(done=n, last=f'{m["doc_type"]} {m["doc_num"]}'))
            _law_job['result'] = dict(fetched=rep.fetched, unchanged=rep.unchanged, failed=len(rep.failed), changes=len(rep.changes))
        except Exception as e:  # noqa: BLE001
            _law_job['error'] = f'{type(e).__name__}: {e}'
        finally:
            _law_job['running'] = False
    threading.Thread(target=work, daemon=True).start()
    return _law_job


# ----------------------------------------------------------------------------- static interface
if STATIC.exists():
    app.mount('/assets', StaticFiles(directory=STATIC / 'assets'), name='assets')


@app.get('/')
def index():
    page = STATIC / 'index.html'
    if not page.exists():
        return JSONResponse(dict(error='chưa dựng giao diện: cd webui && npm install && npm run build'), status_code=503)
    return FileResponse(page, headers={'Cache-Control': 'no-cache'})


from . import web_ai  # noqa: E402,F401  (registers the AI, dossier and law-alert endpoints)

if __name__ == '__main__':
    import uvicorn
    # Load by module name: run as __main__, this file is a second copy of the module and web_ai attaches to the named one.
    import os
    uvicorn.run('src.assistant.web:app', host='127.0.0.1', port=int(os.environ.get('AGENT3_PORT', 8640)))
