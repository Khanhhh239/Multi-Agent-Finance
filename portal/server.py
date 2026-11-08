"""Platform shell for the four agents: one company profile, one data inbox, one layout.

Standard library only, so it runs with any Python 3.10+. Each agent keeps its own code, process and storage; the shell
starts them, shows their pages inside one frame, and sends the files it receives to the agents that can read them:

  agent1  cash flow       CSV or XLSX tables (invoices, payments, outflows, bank, statements, actions)
  agent2  review          transaction CSV in the Agent 2 template
  agent3  tax             e-invoice XML, ZIP of XML, bank statements, tax portal lists (Agent 3 classifies them itself)
  agent4  questions       synthetic warehouse only; it takes no uploads yet

Files are checked first (each agent's own preview) and written only when the person presses "Ghi vào agent".

  python portal/server.py            then open http://127.0.0.1:8800
"""
from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
import zipfile
from base64 import b64encode
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / 'portal'
STATIC = PORTAL / 'static'
CHAT = ROOT / 'agent4_chat'
HOST = '127.0.0.1'


# ----------------------------------------------------------------------------------------------------------- config
def load_config():
    local = PORTAL / 'config.local.json'
    cfg = json.loads((local if local.exists() else PORTAL / 'config.example.json').read_text(encoding='utf-8'))
    cfg.setdefault('port', 8800)
    return cfg


CFG = load_config()
ORIGIN = f'http://{HOST}:{CFG["port"]}'
ORIGINS = (ORIGIN, f'http://localhost:{CFG["port"]}')       # the page may be opened under either name
WORK = (ROOT / CFG.get('workspace', 'portal/workspace')).resolve()
PENDING = WORK / 'pending'
LOGS = WORK / 'logs'
for folder in (PENDING, LOGS):
    folder.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
AGENT4_TOKEN = secrets.token_urlsafe(24)          # lives only as long as this shell; the chat never sees it


def path_of(value, default):
    p = Path(value or default)
    return p if p.is_absolute() else (ROOT / p)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(path)


# ----------------------------------------------------------------------------------------------------------- company
COMPANY_FILE = WORK / 'company.json'
COMPANY_FIELDS = {
    'code': '', 'legal_name': '', 'tax_code': '', 'registered_address': '', 'industry': '',
    'vat_method': 'DEDUCTION', 'filing_period': 'MONTH', 'fiscal_year_end_month': 12,
    'date_format': 'dmy', 'number_format': 'vi-VN', 'agent2_company': '',
}


def mst_ok(tax_code):
    """Vietnamese tax code checksum on the first ten digits (same rule Agent 3 enforces)."""
    digits = re.sub(r'[^0-9]', '', tax_code or '')
    if len(digits) not in (10, 13):
        return False
    weights = (31, 29, 23, 19, 17, 13, 7, 5, 3)
    check = 10 - sum(int(d) * w for d, w in zip(digits[:9], weights)) % 11
    return check == int(digits[9])


def company():
    return {**COMPANY_FIELDS, **read_json(COMPANY_FILE, {})}


def save_company(body):
    data = {k: body.get(k, v) for k, v in COMPANY_FIELDS.items()}
    data['code'] = str(data['code']).strip().upper()
    problems = []
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,63}', data['code']):
        problems.append('Mã doanh nghiệp chỉ gồm chữ không dấu, số, gạch ngang hoặc gạch dưới, tối đa 64 ký tự.')
    if not str(data['legal_name']).strip():
        problems.append('Cần tên doanh nghiệp.')
    if data['tax_code'] and not mst_ok(data['tax_code']):
        problems.append('Mã số thuế không đúng chữ số kiểm tra.')
    try:
        data['fiscal_year_end_month'] = int(data['fiscal_year_end_month'])
        assert 1 <= data['fiscal_year_end_month'] <= 12
    except (ValueError, AssertionError):
        problems.append('Tháng kết thúc năm tài chính phải từ 1 đến 12.')
    if problems:
        raise ValueError(' '.join(problems))
    previous = company()
    data['updated_at'] = time.strftime('%Y-%m-%d %H:%M')
    write_json(COMPANY_FILE, data)
    return data, previous.get('code') != data['code']


# ----------------------------------------------------------------------------------------------------------- agents
AGENTS = {
    'agent1': dict(name='Dòng tiền', summary='Dự báo thu chi theo tuần, kịch bản thu chậm, xuất Excel.',
                   default_root='agent1', port=8011, health='/health', page='/workspace'),
    'agent2': dict(name='Soát giao dịch', summary='Luật cứng, ngưỡng xác suất, đồ thị quan hệ và túi phương pháp ML.',
                   default_root='agent2', port=8766, health='/api/health', page='/'),
    'agent3': dict(name='Thuế GTGT', summary='Đọc hóa đơn XML, đối chiếu sao kê và bảng kê, căn cứ điều luật.',
                   default_root='agent3/agent3_tax_compliance', port=8640, health='/api/schema', page='/'),
    'agent4': dict(name='Hỏi đáp số liệu', summary='Hỏi chỉ tiêu tài chính bằng tiếng Việt, trả lời có nguồn.',
                   default_root='agent4', port=8040, health='/health/live', page=None),
}
PROCS: dict[str, subprocess.Popen] = {}


def agent_cfg(aid):
    return CFG.get('agents', {}).get(aid, {})


def agent_root(aid):
    return path_of(agent_cfg(aid).get('root'), AGENTS[aid]['default_root']).resolve()


def agent_port(aid):
    return int(agent_cfg(aid).get('port', AGENTS[aid]['port']))


def agent_python(aid):
    configured = agent_cfg(aid).get('python')
    if configured:
        return str(path_of(configured, configured))
    venv = agent_root(aid) / '.venv' / 'Scripts' / 'python.exe'
    return str(venv) if venv.exists() else sys.executable


def agent_url(aid, path=''):
    return f'http://{HOST}:{agent_port(aid)}{path}'


def agent1_storage():
    code = company()['code'] or 'SME'
    name = '.state-business' if code == 'SME' else f'.state-business-firm-{code}-data'
    root = agent_root('agent1')
    return root / name, root / (name + '-keys')


def launch_spec(aid):
    root, port, c = agent_root(aid), agent_port(aid), company()
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    if aid == 'agent1':
        state, keys = agent1_storage()
        code = c['code'] or 'SME'
        env.update(AGENT1_THREADS='4', OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1', AGENT1_STATE_DIR=str(state),
                   AGENT1_KEY_DIR=str(keys), AGENT1_FIRM_ID=code, AGENT1_RESEARCH_MODE='0',
                   AGENT1_DEMO_TRAINING='1' if code.startswith('DEMO_') else '0', AGENT1_FRAME_ANCESTORS=' '.join(ORIGINS))
        if code.startswith('DEMO_'):
            keys.mkdir(parents=True, exist_ok=True)
            password = keys / 'report-password.txt'
            if not password.exists():
                password.write_text(secrets.token_urlsafe(32), encoding='utf-8')
            env.update(AGENT1_REPORT_PASSWORD_FILE=str(password),
                       AGENT1_REPORT_DIR=env.get('AGENT1_REPORT_DIR', str(root / 'outputs' / 'private-training-reports')))
        cmd = ['-m', 'uvicorn', 'agent1_service.main:app', '--host', HOST, '--port', str(port)]
    elif aid == 'agent2':
        a = agent_cfg(aid)
        run = root / '.runtime' / 'platform'
        cmd = ['-B', '-m', 'sme_fraud.review_server',
               '--data-root', str(path_of(a.get('data_root'), run / 'data')),
               '--reports-root', str(path_of(a.get('reports_root'), run / 'reports')),
               '--database', str(path_of(a.get('database'), run / 'review.sqlite3')),
               '--port', str(port), '--qa', '--demo-ml-manager']
        env.update(SOSOAT_FRAME_ANCESTORS=' '.join(ORIGINS), PYTHONDONTWRITEBYTECODE='1')
    elif aid == 'agent3':
        cmd = ['-m', 'src.assistant.web']
        env.update(AGENT3_PORT=str(port))
    else:
        cmd = ['-m', 'uvicorn', 'agent4.text2sql.api:create_app', '--factory', '--host', HOST, '--port', str(port)]
        env.update(AGENT4_DEMO_TOKEN=AGENT4_TOKEN)
    env.update({k: str(path_of(v, v)) if k.endswith(('_DIR', '_STORE', 'WORKSPACES')) else str(v)
                for k, v in agent_cfg(aid).get('env', {}).items()})
    return [agent_python(aid), *cmd], root, env


def port_open(port):
    with socket.socket() as s:
        s.settimeout(.3)
        return s.connect_ex((HOST, port)) == 0


def health(aid):
    try:
        with urlopen(agent_url(aid, AGENTS[aid]['health']), timeout=1.5) as r:
            return 200 <= r.status < 300
    except (URLError, OSError, ValueError):
        return False


def agent_state(aid):
    proc = PROCS.get(aid)
    owned = proc is not None and proc.poll() is None
    up = health(aid)
    if up:
        state = 'running'
    elif owned:
        state = 'starting'
    elif port_open(agent_port(aid)):
        state = 'busy-port'
    else:
        state = 'stopped'
    info = AGENTS[aid]
    return dict(id=aid, number=int(aid[-1]), name=info['name'], summary=info['summary'], state=state, owned=owned,
                port=agent_port(aid), url=(agent_url(aid, info['page']) if info['page'] else '/agent4/'),
                root=str(agent_root(aid)), log=f'/api/agents/{aid}/log',
                exit_code=(proc.returncode if proc is not None and proc.poll() is not None else None))


def start_agent(aid):
    with LOCK:
        if agent_state(aid)['state'] in ('running', 'starting'):
            return agent_state(aid)
        if port_open(agent_port(aid)):
            raise ValueError(f'Cổng {agent_port(aid)} đang bị chương trình khác dùng. Đổi cổng trong portal/config.local.json.')
        cmd, cwd, env = launch_spec(aid)
        if not Path(cmd[0]).exists():
            raise ValueError(f'Không thấy Python cho {aid}: {cmd[0]}. Khai báo "python" trong portal/config.local.json.')
        log = open(LOGS / f'{aid}.log', 'ab')
        log.write(f'\n--- {time.strftime("%Y-%m-%d %H:%M:%S")} {" ".join(cmd)}\n'.encode())
        log.flush()
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        PROCS[aid] = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, creationflags=flags)
        return agent_state(aid)


def stop_agent(aid):
    with LOCK:
        proc = PROCS.pop(aid, None)
        if proc is None or proc.poll() is not None:
            raise ValueError('Portal không khởi động agent này nên không dừng nó.')
        proc.terminate()
        try:
            proc.wait(8)
        except subprocess.TimeoutExpired:
            proc.kill()
        return agent_state(aid)


def stop_all():
    for aid in list(PROCS):
        try:
            stop_agent(aid)
        except ValueError:
            pass


def agent1_key():
    _, keys = agent1_storage()
    try:
        return (keys / 'api-token.txt').read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def log_tail(aid, lines=60):
    try:
        text = (LOGS / f'{aid}.log').read_bytes()[-20000:].decode('utf-8', 'replace')
    except OSError:
        return ''
    return '\n'.join(text.splitlines()[-lines:])


# ----------------------------------------------------------------------------------------------------------- http client
def call(method, url, body=None, headers=None, timeout=120):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body, ensure_ascii=False).encode('utf-8')
    head = dict(headers or {})
    if body is not None and not isinstance(body, bytes):
        head['Content-Type'] = 'application/json'
    try:
        with urlopen(Request(url, data=data, method=method, headers=head), timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b'{', b'[') else raw.decode('utf-8', 'replace'))
    except HTTPError as e:
        raw = e.read()
        try:
            detail = json.loads(raw)
            detail = detail.get('detail') or detail.get('error') or detail
        except ValueError:
            detail = raw.decode('utf-8', 'replace')[:300]
        return e.code, {'error': detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)[:400]}
    except (URLError, OSError) as e:
        return 0, {'error': f'Không kết nối được agent ({e}). Bật agent ở trang Tổng quan rồi thử lại.'}


def multipart(fields, file_field, filename, content):
    boundary = 'platform' + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
    out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
              f'Content-Type: application/octet-stream\r\n\r\n'.encode('utf-8'))
    out.write(content)
    out.write(f'\r\n--{boundary}--\r\n'.encode())
    return out.getvalue(), f'multipart/form-data; boundary={boundary}'


# ----------------------------------------------------------------------------------------------------------- classify
def plain(text):
    text = unicodedata.normalize('NFD', str(text)).replace('đ', 'd').replace('Đ', 'D')
    return re.sub(r'\s+', ' ', ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')).lower().replace('_', ' ').strip()


A1_TABLES = {   # column names and aliases as Agent 1 accepts them (agent1/adaptive/data.py), required ones first
    'invoices': ('Hóa đơn bán', {'invoice id': ['ma hoa don', 'so hoa don'], 'customer id': ['ma khach hang', 'khach hang'],
                                 'issue date': ['ngay lap', 'ngay hoa don'], 'due date': ['han thanh toan', 'ngay den han'],
                                 'amount': ['so tien', 'tong thanh toan', 'amount gross']}),
    'payments': ('Tiền khách trả', {'payment id': ['ma thanh toan', 'ma giao dich', 'txn id'], 'invoice id': ['ma hoa don', 'so hoa don'],
                                    'payment date': ['ngay thanh toan', 'ngay tien ve', 'value date'], 'amount': ['so tien']}),
    'outflows': ('Khoản chi', {'expense id': ['ma khoan chi'], 'date': ['ngay chi'], 'amount': ['so tien'],
                               'category': ['loai chi'], 'known at': ['ngay ghi nhan']}),
    'bank': ('Dòng sao kê (dòng tiền)', {'bank id': ['ma dong sao ke'], 'account': ['tai khoan'], 'date': ['ngay giao dich'],
                                         'direction': ['thu chi'], 'amount': ['so tien']}),
    'statements': ('Kỳ sao kê', {'statement id': ['ma ky sao ke'], 'account': ['tai khoan'], 'start date': ['tu ngay'],
                                 'end date': ['den ngay'], 'opening balance': ['so du dau ky'], 'closing balance': ['so du cuoi ky']}),
    'actions': ('Hứa trả và nhắc nợ', {'event id': ['ma su kien'], 'invoice id': ['ma hoa don'], 'date': ['ngay su kien'],
                                       'kind': ['hanh dong']}),
}
A2_REQUIRED = {plain(c) for c in ('transaction_id', 'posted_at', 'created_at', 'approved_at', 'txn_type', 'amount_vnd',
               'approval_limit_vnd', 'creator_id', 'approver_id', 'is_financial_entry', 'debit_account', 'credit_account',
               'journal_signature', 'accounting_purpose', 'recognised_input_vat_vnd', 'recognised_output_vat_vnd',
               'writeoff_provision_vnd', 'production_cost_vnd')}


def xlsx_header(raw):
    """First non-empty row of the first sheet, read with zipfile only."""
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ElementTree.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns):
                shared.append(''.join(t.text or '' for t in si.iter(f'{{{ns["m"]}}}t')))
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n))
        if not sheets:
            return []
        for row in ElementTree.fromstring(z.read(sheets[0])).iter(f'{{{ns["m"]}}}row'):
            values = []
            for cell in row.findall('m:c', ns):
                v = cell.find('m:v', ns)
                text = ''.join(t.text or '' for t in cell.iter(f'{{{ns["m"]}}}t')) if cell.get('t') == 'inlineStr' else (v.text if v is not None else '')
                if cell.get('t') == 's' and text:
                    text = shared[int(text)]
                values.append(text or '')
            if any(x.strip() for x in values):
                return values
    return []


def csv_header(raw):
    text = raw[:65536].decode('utf-8-sig', 'replace')
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    delimiter = max((',', ';', '\t'), key=lines[0].count)
    return next(csv.reader([lines[0]], delimiter=delimiter))


def classify(name, raw):
    ext = Path(name).suffix.lower()
    base = dict(kind='unknown', label='Chưa nhận dạng được', targets=[], note='')
    if ext == '.zip':
        return dict(base, kind='zip', label='Tệp nén hóa đơn', targets=['agent3'], note='Agent 3 mở tệp nén và phân loại từng tệp.')
    if ext == '.xml':
        if b'HDon' in raw[:200000]:
            return dict(base, kind='invoice_xml', label='Hóa đơn điện tử XML', targets=['agent3'])
        return dict(base, note='Tệp XML không có thẻ HDon nên không phải hóa đơn điện tử.')
    if ext not in ('.csv', '.xlsx', '.txt'):
        return dict(base, note='Chỉ nhận CSV, XLSX, XML hoặc ZIP.')
    try:
        header = xlsx_header(raw) if ext == '.xlsx' else csv_header(raw)
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, IndexError, ValueError):
        return dict(base, note='Không đọc được dòng tiêu đề của tệp.')
    cols = {plain(c) for c in header if str(c).strip()}
    if A2_REQUIRED <= cols:
        return dict(base, kind='transactions', label='Sổ giao dịch', targets=['agent2'], columns=len(cols))
    for kind, (label, spec) in A1_TABLES.items():
        if all(canon in cols or any(a in cols for a in aliases) for canon, aliases in spec.items()):
            return dict(base, kind=f'a1:{kind}', label=label, targets=['agent1'], columns=len(cols))
    return dict(base, kind='statement_or_list', label='Sao kê hoặc bảng kê', targets=['agent3'], columns=len(cols),
                note='Không khớp mẫu Agent 1 hay Agent 2; gửi Agent 3 tự nhận dạng sao kê ngân hàng hoặc bảng kê cổng thuế.')


# ----------------------------------------------------------------------------------------------------------- inbox
def pending():
    out = []
    for meta in sorted(PENDING.glob('*.json')):
        record = read_json(meta, None)
        if record:
            out.append(record)
    return sorted(out, key=lambda r: r['added_at'])


def history():
    return read_json(WORK / 'history.json', [])


def add_file(name, raw):
    clean = re.sub(r'[^\w.\-]', '_', Path(name).name)[:120] or 'tep'
    fid = uuid.uuid4().hex[:12]
    (PENDING / f'{fid}.bin').write_bytes(raw)
    record = dict(id=fid, name=clean, size=len(raw), added_at=time.strftime('%Y-%m-%d %H:%M:%S'), **classify(clean, raw))
    record['checks'] = {aid: check(aid, record, raw) for aid in record['targets']}
    write_json(PENDING / f'{fid}.json', record)
    return record


def recheck(fid):
    record = read_json(PENDING / f'{fid}.json', None)
    if record is None:
        raise KeyError('Không còn tệp này trong hàng chờ.')
    raw = (PENDING / f'{fid}.bin').read_bytes()
    record['checks'] = {aid: check(aid, record, raw) for aid in record['targets']}
    write_json(PENDING / f'{fid}.json', record)
    return record


def remove_file(fid):
    for suffix in ('.json', '.bin'):
        (PENDING / f'{fid}{suffix}').unlink(missing_ok=True)


def agent2_session():
    status, meta = call('GET', agent_url('agent2', '/api/meta'))
    if status != 200:
        raise ConnectionError(meta.get('error') if isinstance(meta, dict) else 'Agent 2 chưa sẵn sàng.')
    return {'X-CSRF-Token': meta['csrf_token']}


def agent2_company():
    c = company()
    return c.get('agent2_company') or c['code']


def check(aid, record, raw):
    """Run the agent's own preview; nothing is written to the agent here."""
    c = company()
    if not health(aid):
        return dict(state='offline', message='Agent chưa bật. Bật ở trang Tổng quan rồi bấm Kiểm tra lại.')
    if aid == 'agent1':
        key = agent1_key()
        body, ctype = multipart(dict(kind=record['kind'].split(':', 1)[1], mapping='{}',
                                     date_format='%Y-%m-%d' if c['date_format'] == 'iso' else '%d/%m/%Y',
                                     number_format=c['number_format']), 'file', record['name'], raw)
        status, res = call('POST', agent_url('agent1', '/v1/imports/preview'), body,
                           {'Authorization': f'Bearer {key}', 'Content-Type': ctype})
        if status != 200:
            return dict(state='error', message=res.get('error', f'Lỗi {status}'))
        ok = res.get('can_commit')
        return dict(state='ready' if ok else 'error', preview=res.get('id'), rows=res.get('valid_rows'),
                    errors=res.get('error_count', 0),
                    message=f'{res.get("valid_rows", 0)} dòng hợp lệ' + (f', {res.get("error_count")} lỗi' if res.get('error_count') else ''),
                    detail=[f'Dòng {e.get("row")}, cột {e.get("column")}: {e.get("message")}' for e in res.get('errors', [])[:5]])
    if aid == 'agent2':
        try:
            head = agent2_session()
        except ConnectionError as e:
            return dict(state='error', message=str(e))
        company_id = agent2_company()
        status, ctx = call('GET', agent_url('agent2', f'/api/data-import/context?company={quote(company_id)}'), headers=head)
        if status != 200:
            return dict(state='error', message=f'Agent 2 không có doanh nghiệp "{company_id}": {ctx.get("error", status)}. '
                                               'Đặt "Mã doanh nghiệp ở Agent 2" trong Cấu hình.')
        revision = ((ctx.get('status') or {}).get('data') or {}).get('revision')
        status, res = call('POST', agent_url('agent2', '/api/data-import/preview'),
                           dict(company_id=company_id, filename=record['name'], content_base64=b64encode(raw).decode(),
                                expected_revision=revision, date_order='iso' if c['date_format'] == 'iso' else 'dmy'), head)
        if status != 200:
            return dict(state='error', message=res.get('error', f'Lỗi {status}'))
        summary = res.get('summary') or {}
        issues = res.get('issues') or res.get('errors') or []
        ok = bool(res.get('token')) and not issues
        return dict(state='ready' if ok else 'error', preview=res.get('token'), rows=summary.get('rows'),
                    message=(f'{summary.get("rows", "?")} giao dịch, thay cho {summary.get("previous_rows", 0)} giao dịch đang có'
                             if ok else f'{len(issues)} lỗi cần sửa'),
                    detail=[f'Dòng {i.get("row")}, {i.get("column")}: {i.get("message")}' for i in issues[:5] if isinstance(i, dict)],
                    warning='Agent 2 thay toàn bộ giao dịch của doanh nghiệp bằng tệp này.')
    if aid == 'agent3':
        wid = agent3_workspace()
        if not wid:
            return dict(state='error', message='Cần mã số thuế hợp lệ trong Cấu hình để Agent 3 tạo không gian làm việc.')
        return dict(state='ready', message='Agent 3 tự phân loại khi ghi; tệp trùng nội dung không bị nạp hai lần.')
    return dict(state='error', message='Agent này chưa nhận tệp.')


def agent3_workspace():
    tax = re.sub(r'[^0-9-]', '', company()['tax_code'] or '')
    return tax if tax and mst_ok(tax) else ''


def agent3_admin_cookie(password):
    """Log in to Agent 3 (or set its first admin password) and return the session cookie. The password is not kept."""
    status, info = call('GET', agent_url('agent3', '/api/admin/status'))
    if status != 200:
        raise ValueError('Agent 3 chưa bật.')
    action = 'login' if info.get('configured') else 'setup'
    req = Request(agent_url('agent3', f'/api/admin/{action}'), method='POST',
                  data=json.dumps({'password': password}).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=20) as r:
            cookie = r.headers.get('Set-Cookie', '').split(';', 1)[0]
    except HTTPError as e:
        try:
            detail = json.loads(e.read()).get('detail')
        except ValueError:
            detail = None
        raise ValueError(f'Agent 3: {detail or e.code}') from None
    if not cookie:
        raise ValueError('Agent 3 không cấp phiên quản trị.')
    return cookie, action


def ensure_agent3_workspace(password=None):
    c = company()
    wid = agent3_workspace()
    if not wid:
        return dict(state='skipped', message='Chưa có mã số thuế hợp lệ.')
    status, listing = call('GET', agent_url('agent3', '/api/workspaces'))
    if status != 200:
        return dict(state='offline', message='Agent 3 chưa bật; sẽ tạo khi bật và lưu lại cấu hình.')
    if any(w.get('id') == wid for w in listing):
        return dict(state='ok', message=f'Đã có không gian {wid} ở Agent 3.', id=wid)
    profile = dict(tax_code=c['tax_code'], legal_name=c['legal_name'], registered_address=c['registered_address'] or None,
                   vat_method=c['vat_method'], filing_period=c['filing_period'],
                   industry=[x.strip() for x in re.split(r'[;\n]', str(c['industry'])) if x.strip()],
                   fiscal_year_end_month=c['fiscal_year_end_month'])
    if not password:
        return dict(state='needs_admin', message='Agent 3 cần mật khẩu quản trị để tạo doanh nghiệp. Nhập bên dưới; '
                                                 'lần đầu, mật khẩu này trở thành mật khẩu quản trị của Agent 3.')
    cookie, action = agent3_admin_cookie(password)
    status, res = call('POST', agent_url('agent3', '/api/workspaces'), dict(id=wid, profile=profile, by='portal'), {'Cookie': cookie})
    call('POST', agent_url('agent3', '/api/admin/logout'), b'', {'Cookie': cookie})
    if status != 200:
        return dict(state='error', message=f'Agent 3 từ chối hồ sơ: {res.get("error", status)}')
    extra = ' Đã đặt mật khẩu quản trị Agent 3.' if action == 'setup' else ''
    return dict(state='ok', message=f'Đã tạo doanh nghiệp {wid} ở Agent 3.{extra}', id=wid)


def commit(fids):
    results = []
    for fid in fids:
        record = read_json(PENDING / f'{fid}.json', None)
        if record is None:
            continue
        raw = (PENDING / f'{fid}.bin').read_bytes()
        outcome = {}
        for aid in record['targets']:
            chk = record.get('checks', {}).get(aid, {})
            if chk.get('state') != 'ready':
                outcome[aid] = dict(state='skipped', message='Chưa qua kiểm tra nên không ghi.')
                continue
            if aid == 'agent1':
                chk = check('agent1', record, raw)          # fresh preview: an earlier write in this batch changes the base
                if chk.get('state') != 'ready':
                    outcome[aid] = dict(state='error', message=chk.get('message', 'Kiểm tra lại không đạt.'))
                    continue
                status, res = call('POST', agent_url('agent1', f'/v1/imports/{chk["preview"]}/commit'), b'',
                                   {'Authorization': f'Bearer {agent1_key()}'})
                outcome[aid] = (dict(state='done', message=f'Đã ghi {res.get("accepted")} dòng.') if status == 200
                                else dict(state='error', message=res.get('error', f'Lỗi {status}')))
            elif aid == 'agent2':
                try:
                    head = agent2_session()
                    status, res = call('POST', agent_url('agent2', '/api/data-import/commit'),
                                       dict(company_id=agent2_company(), token=chk['preview'], acknowledge=True), head)
                except ConnectionError as e:
                    status, res = 0, {'error': str(e)}
                outcome[aid] = (dict(state='done', message='Đã thay dữ liệu giao dịch.') if status == 200
                                else dict(state='error', message=res.get('error', f'Lỗi {status}')))
            elif aid == 'agent3':
                ws = ensure_agent3_workspace()
                if ws['state'] == 'needs_admin':
                    ws['message'] = 'Chưa có doanh nghiệp này ở Agent 3. Vào Cấu hình, nhập mật khẩu quản trị Agent 3 để tạo.'
                if ws['state'] != 'ok':
                    outcome[aid] = dict(state='error', message=ws['message'])
                    continue
                status, res = call('PUT', agent_url('agent3', f'/api/workspaces/{ws["id"]}/inbox?name={quote(record["name"])}'), raw,
                                   {'Content-Type': 'application/octet-stream'}, timeout=600)
                if status == 200:
                    used = [f for f in res.get('files', []) if f.get('label') != 'Không dùng']
                    outcome[aid] = dict(state='done' if used else 'skipped',
                                        message=(f'Đã nạp {len(used)} tệp: ' + ', '.join(sorted({f["label"] for f in used})))
                                        if used else 'Agent 3 không dùng tệp này.')
                else:
                    outcome[aid] = dict(state='error', message=res.get('error', f'Lỗi {status}'))
        entry = dict(id=fid, name=record['name'], label=record['label'], size=record['size'],
                     at=time.strftime('%Y-%m-%d %H:%M:%S'), results=outcome)
        results.append(entry)
        if all(v['state'] in ('done', 'skipped') for v in outcome.values()):
            remove_file(fid)
    with LOCK:
        write_json(WORK / 'history.json', (results + history())[:200])
    # Files that failed only because they point at rows written just now (payments after invoices) pass on a new check.
    for record in pending():
        if any(c.get('state') != 'ready' for c in record.get('checks', {}).values()):
            recheck(record['id'])
    return results


# ----------------------------------------------------------------------------------------------------------- agent 4
def agent4_query(question):
    body = dict(api_version='v1', question=question, locale='vi-VN', session_id=None,
                options=dict(include_table=True, explain_metrics=True))
    status, res = call('POST', agent_url('agent4', '/v1/query'), body, {'Authorization': f'Bearer {AGENT4_TOKEN}'}, timeout=60)
    if status != 200:
        return dict(status='error', answer=res.get('error', f'Lỗi {status}') if isinstance(res, dict) else str(res), warnings=[])
    return res


def agent4_metrics():
    status, res = call('GET', agent_url('agent4', '/v1/metrics'), headers={'Authorization': f'Bearer {AGENT4_TOKEN}'})
    return res if status == 200 else {'error': res.get('error') if isinstance(res, dict) else str(res)}


# ----------------------------------------------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = 'Platform/1'

    def log_message(self, fmt, *args):
        pass

    def send(self, status, body, ctype='application/json; charset=utf-8', extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                         f"img-src 'self' data:; frame-src http://{HOST}:* http://localhost:*; frame-ancestors 'self'; base-uri 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def static(self, folder, rel):
        target = (folder / (rel or 'index.html')).resolve()
        if folder.resolve() not in target.parents and target != folder.resolve() or not target.is_file():
            return self.send(404, {'error': 'Không có trang này.'})
        ctype = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript',):
            ctype += '; charset=utf-8'
        self.send(200, target.read_bytes(), ctype)

    def body(self, limit):
        length = int(self.headers.get('Content-Length', 0))
        if not 0 <= length <= limit:
            raise ValueError('Tệp hoặc nội dung quá lớn.')
        return self.rfile.read(length)

    def json_body(self):
        raw = self.body(1_000_000)
        return json.loads(raw or b'{}')

    def guard(self):
        """State-changing calls only from this page (same origin) with a JSON or file body."""
        origin = self.headers.get('Origin')
        if origin and origin not in ORIGINS:
            raise PermissionError('Yêu cầu không đến từ trang portal.')
        if self.headers.get('X-Platform') != '1':
            raise PermissionError('Thiếu tiêu đề X-Platform.')

    def route(self, method):
        url = urlsplit(self.path)
        path, query = url.path, {k: v[-1] for k, v in parse_qs(url.query).items()}
        if method == 'GET':
            if path == '/api/state':
                return self.send(200, dict(company=company(), agents=[agent_state(a) for a in AGENTS],
                                           pending=pending(), history=history()[:30], origin=ORIGIN))
            if path == '/api/agents/agent1/key':
                return self.send(200, dict(key=agent1_key()))
            m = re.fullmatch(r'/api/agents/(agent[1-4])/log', path)
            if m:
                return self.send(200, dict(log=log_tail(m.group(1))))
            if path == '/api/agent4/metrics':
                return self.send(200, agent4_metrics())
            if path.startswith('/agent4/') or path == '/agent4':
                return self.static(CHAT, path[len('/agent4/'):])
            if path.startswith('/api/'):
                return self.send(404, {'error': 'Không có địa chỉ này.'})
            return self.static(STATIC, path.lstrip('/') if '.' in path.rsplit('/', 1)[-1] else '')
        self.guard()
        if method == 'PUT' and path == '/api/company':
            data, code_changed = save_company(self.json_body())
            sync = dict(agent3=ensure_agent3_workspace() if health('agent3') else dict(state='offline', message='Agent 3 chưa bật.'))
            if code_changed and PROCS.get('agent1') and PROCS['agent1'].poll() is None:
                stop_agent('agent1')
                start_agent('agent1')
                sync['agent1'] = dict(state='ok', message='Đã khởi động lại Agent 1 với mã doanh nghiệp mới.')
            return self.send(200, dict(company=data, sync=sync))
        if method == 'POST' and path == '/api/agent3/workspace':
            password = str(self.json_body().get('password', ''))
            if not password:
                raise ValueError('Nhập mật khẩu quản trị Agent 3.')
            return self.send(200, ensure_agent3_workspace(password))
        m = re.fullmatch(r'/api/agents/(agent[1-4])/(start|stop)', path)
        if method == 'POST' and m:
            aid, action = m.groups()
            return self.send(200, start_agent(aid) if action == 'start' else stop_agent(aid))
        if method == 'POST' and path == '/api/inbox':
            name = query.get('name', '')
            if not name:
                raise ValueError('Thiếu tên tệp.')
            return self.send(200, add_file(name, self.body(300 * 1024 * 1024)))
        m = re.fullmatch(r'/api/inbox/([0-9a-f]{12})/(check|delete)', path)
        if method == 'POST' and m:
            fid, action = m.groups()
            if action == 'delete':
                remove_file(fid)
                return self.send(200, dict(ok=True))
            return self.send(200, recheck(fid))
        if method == 'POST' and path == '/api/inbox/commit':
            ids = [i for i in self.json_body().get('ids', []) if re.fullmatch(r'[0-9a-f]{12}', str(i))]
            return self.send(200, dict(results=commit(ids)))
        if method == 'POST' and path == '/api/agent4/query':
            question = str(self.json_body().get('question', '')).strip()[:2000]
            if not question:
                raise ValueError('Nhập câu hỏi.')
            return self.send(200, agent4_query(question))
        self.send(404, {'error': 'Không có địa chỉ này.'})

    def handle_one(self, method):
        try:
            self.route(method)
        except PermissionError as e:
            self.send(403, {'error': str(e)})
        except (ValueError, KeyError) as e:
            self.send(400, {'error': str(e).strip("'")})
        except Exception as e:  # noqa: BLE001
            self.send(500, {'error': f'Lỗi máy chủ portal: {e}'})

    def do_GET(self):
        self.handle_one('GET')

    def do_POST(self):
        self.handle_one('POST')

    def do_PUT(self):
        self.handle_one('PUT')


def main():
    autostart = '--start-all' in sys.argv
    server = ThreadingHTTPServer((HOST, CFG['port']), Handler)
    print(f'Portal: {ORIGIN}  (Ctrl+C để dừng; các agent do portal bật sẽ dừng theo)')
    if autostart:
        for aid in AGENTS:
            try:
                start_agent(aid)
            except ValueError as e:
                print(f'{aid}: {e}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


if __name__ == '__main__':
    main()
