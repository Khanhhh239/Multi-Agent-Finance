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
import hashlib
import hmac
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
import base64
import math
from base64 import b64encode

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

if __package__:
    from . import bank_intake
else:
    import bank_intake

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / 'portal'
STATIC = PORTAL / 'static'
CHAT = ROOT / 'agent4_chat'
DESIGN = ROOT / 'design'
HOST = '127.0.0.1'


# ----------------------------------------------------------------------------------------------------------- config
def load_config():
    override = os.environ.get('MAF_PORTAL_CONFIG')
    local = Path(override).resolve() if override else PORTAL / 'config.local.json'
    if override and not local.is_file():
        raise FileNotFoundError(local)
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
AGENT3_TOKEN = secrets.token_urlsafe(32)          # backend bridge only; never returned in portal state


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




class AuthError(Exception):
    """The intake is locked: no valid password session."""


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


def agent1_profile_file(data):
    """Publish only the company settings Agent 1 consumes, separately for each firm."""
    profile = {key: data[key] for key in ('code', 'date_format', 'number_format')}
    profile['code'] = profile['code'] or 'SME'
    path = WORK / 'agent1_profiles' / (profile['code'] + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, profile)
    return path


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
    if data['date_format'] not in ('dmy', 'iso'):
        problems.append('Chọn định dạng ngày trong tệp hợp lệ.')
    if data['number_format'] not in ('vi-VN', 'plain'):
        problems.append('Chọn định dạng số tiền trong tệp hợp lệ.')
    try:
        data['fiscal_year_end_month'] = int(data['fiscal_year_end_month'])
        assert 1 <= data['fiscal_year_end_month'] <= 12
    except (ValueError, AssertionError):
        problems.append('Tháng kết thúc năm tài chính phải từ 1 đến 12.')
    if problems:
        raise ValueError(' '.join(problems))
    previous = company()
    data['updated_at'] = time.strftime('%Y-%m-%d %H:%M')
    agent1_profile_file(data)
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
    root = path_of(agent_cfg('agent1').get('storage_root'), agent_root('agent1'))
    return root / name, root / (name + '-keys')


def launch_spec(aid):
    root, port, c = agent_root(aid), agent_port(aid), company()
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    if aid == 'agent1':
        state, keys = agent1_storage()
        code = c['code'] or 'SME'
        env.update(AGENT1_THREADS='4', OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='1', AGENT1_STATE_DIR=str(state),
                   AGENT1_KEY_DIR=str(keys), AGENT1_FIRM_ID=code, AGENT1_RESEARCH_MODE='0',
                   AGENT1_COMPANY_PROFILE_FILE=str(agent1_profile_file(c)),
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
    if aid == 'agent3':
        env.update(AGENT3_COMPANY_PROFILE_FILE=str(COMPANY_FILE), AGENT3_PORTAL_URL=ORIGIN,
                   AGENT3_PLATFORM_TOKEN=AGENT3_TOKEN,
                   AGENT3_DEMO_COMPANY=json.dumps(CFG.get('demo_company')))
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
    listening = port_open(agent_port(aid))
    if listening and health(aid):
        state = 'running'
    elif owned:
        state = 'starting'
    elif listening:
        state = 'busy-port'
    else:
        state = 'stopped'
    info = AGENTS[aid]
    url = agent_url(aid, info['page']) if info['page'] else '/agent4/'
    if aid == 'agent3' and (workspace := agent3_workspace()):
        url += '#/?dn=' + quote(workspace)
    return dict(id=aid, number=int(aid[-1]), name=info['name'], summary=info['summary'], state=state, owned=owned,
                port=agent_port(aid), url=url,
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
        LOGS.mkdir(parents=True, exist_ok=True)
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


def agent1_connect_link(expected_company, origin):
    code = company()['code'] or 'SME'
    if expected_company != code:
        raise ValueError('Doanh nghiệp đã đổi. Tải lại trang rồi mở tab mới.')
    if origin not in ORIGINS:
        raise PermissionError('Yêu cầu không đến từ trang portal.')
    key = agent1_key()
    if not key:
        raise ValueError('Agent 1 chưa sẵn sàng kết nối. Bật Agent 1 rồi thử lại.')
    status, result = call('POST', agent_url('agent1', '/v1/portal-connect/tickets'),
                          dict(company=code), {'Authorization': 'Bearer ' + key}, timeout=10)
    if not isinstance(result, dict):
        raise ValueError('Agent 1 chưa hỗ trợ kết nối tab riêng. Khởi động lại Agent 1 rồi thử lại.')
    if status != 201:
        detail = result.get('detail') or result.get('error')
        raise ValueError(detail if isinstance(detail, str) else 'Không tạo được kết nối tab riêng. Kiểm tra Agent 1 đã được khởi động lại với code mới.')
    ticket = result.get('ticket', '')
    if result.get('company') != code or not isinstance(ticket, str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,128}', ticket):
        raise ValueError('Mã kết nối không khớp doanh nghiệp. Tải lại trang rồi thử lại.')
    url = agent_url('agent1', '/workspace') + '?' + urlencode({'portal': origin}) + '#portal-connect=' + ticket
    return dict(url=url, company=code, expires_in=60)


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
    'outflows': ('Lịch cố định T5', {'expense id': ['ma khoan chi'], 'date': ['ngay chi'], 'amount': ['so tien'],
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


def xlsx_rows(raw, *, header_only=False):
    """Read the first worksheet while keeping text identifiers and exact numeric values."""
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sum(member.file_size for member in z.infolist()) > 64 * 1024 * 1024:
            raise ValueError('Excel vượt 64 MB sau khi giải nén')
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in ElementTree.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns):
                shared.append(''.join(t.text or '' for t in si.iter(f'{{{ns["m"]}}}t')))
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n))
        if not sheets:
            return
        seen_header = False
        for row in ElementTree.fromstring(z.read(sheets[0])).iter(f'{{{ns["m"]}}}row'):
            cells = {}
            for cell in row.findall('m:c', ns):
                column = re.match(r'[A-Z]+', cell.get('r', ''))
                if not column:
                    raise ValueError('Vị trí ô Excel không hợp lệ')
                idx = 0
                for letter in column[0]:
                    idx = idx * 26 + ord(letter) - 64
                if idx > 16384:
                    raise ValueError('Vị trí cột Excel không hợp lệ')
                if not header_only and cell.find('m:f', ns) is not None:
                    raise ValueError('Sao kê Excel không được có công thức; xuất lại dưới dạng giá trị')
                v = cell.find('m:v', ns)
                text = ''.join(t.text or '' for t in cell.iter(f'{{{ns["m"]}}}t')) if cell.get('t') == 'inlineStr' else (v.text if v is not None else '')
                if cell.get('t') == 's' and text:
                    text = shared[int(text)]
                elif text and cell.get('t') in (None, 'n') and not header_only:
                    text = Decimal(text)
                cells[idx - 1] = text if text is not None else ''
            values = [cells.get(i, '') for i in range(max(cells, default=-1) + 1)]
            if seen_header or any(str(x).strip() for x in values):
                yield values
                seen_header = True
                if header_only:
                    return


def xlsx_header(raw):
    return next(xlsx_rows(raw, header_only=True), [])


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
    try:
        if bank_intake.columns(header, plain):
            return dict(base, kind='shared_bank', label='Sao kê dùng chung', targets=['agent1', 'agent3'],
                        note='Một tệp gốc, hệ thống tự chuẩn hóa cho dòng tiền và thuế GTGT.')
    except ValueError as exc:
        return dict(base, note=str(exc))
    for kind, (label, spec) in A1_TABLES.items():
        if all(canon in cols or any(a in cols for a in aliases) for canon, aliases in spec.items()):
            return dict(base, kind=f'a1:{kind}', label=label, targets=['agent1'], columns=len(cols))
    return dict(base, kind='statement_or_list', label='Sao kê hoặc bảng kê', targets=['agent3'], columns=len(cols),
                note='Không khớp mẫu Agent 1 hay Agent 2; gửi Agent 3 tự nhận dạng sao kê ngân hàng hoặc bảng kê cổng thuế.')


# ----------------------------------------------------------------------------------------------------------- intake security
SECURITY_FILE = WORK / 'intake_security.json'
AUDIT_FILE = WORK / 'audit.jsonl'
BATCH_FILE = WORK / 'batches.json'
SESSIONS: dict[str, float] = {}
SESSION_TTL = 20 * 60
FAILS = {'n': 0, 'until': 0.0}


def _scrypt(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def configured():
    return SECURITY_FILE.exists()


def audit(event, detail=None):
    """Append-only log; each line carries the hash of the previous one, so edits or deletions are detectable."""
    with LOCK:
        lines = AUDIT_FILE.read_text(encoding='utf-8').splitlines() if AUDIT_FILE.exists() else []
        prev = json.loads(lines[-1])['hash'] if lines else '0' * 64
        entry = dict(seq=len(lines) + 1, at=time.strftime('%Y-%m-%d %H:%M:%S'), event=event, detail=detail or {}, prev=prev)
        entry['hash'] = hashlib.sha256((prev + json.dumps({k: entry[k] for k in ('seq', 'at', 'event', 'detail')},
                                                          ensure_ascii=False, sort_keys=True)).encode('utf-8')).hexdigest()
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def audit_check():
    prev, entries = '0' * 64, []
    if AUDIT_FILE.exists():
        for line in AUDIT_FILE.read_text(encoding='utf-8').splitlines():
            e = json.loads(line)
            want = hashlib.sha256((prev + json.dumps({k: e[k] for k in ('seq', 'at', 'event', 'detail')},
                                                     ensure_ascii=False, sort_keys=True)).encode('utf-8')).hexdigest()
            if e['prev'] != prev or e['hash'] != want:
                return dict(valid=False, broken_at=e['seq'], count=len(entries) + 1, entries=entries[-40:])
            prev = e['hash']
            entries.append(e)
    return dict(valid=True, count=len(entries), entries=entries[-40:][::-1], head=prev[:12])


def set_password(password, confirm):
    if configured():
        raise ValueError('Đã có mật khẩu nạp dữ liệu.')
    if len(password) < 8:
        raise ValueError('Mật khẩu cần ít nhất 8 ký tự.')
    if password != confirm:
        raise ValueError('Hai lần nhập mật khẩu không giống nhau.')
    salt = secrets.token_bytes(16)
    write_json(SECURITY_FILE, dict(salt=salt.hex(), hash=_scrypt(password, salt).hex(), created_at=time.strftime('%Y-%m-%d %H:%M:%S')))
    audit('setup', {})
    return new_session()


def unlock(password):
    now = time.time()
    if FAILS['until'] > now:
        raise ValueError(f'Nhập sai nhiều lần. Thử lại sau {int(FAILS["until"] - now) + 1} giây.')
    sec = read_json(SECURITY_FILE, None)
    if sec is None:
        raise ValueError('Chưa đặt mật khẩu nạp dữ liệu.')
    if not hmac.compare_digest(_scrypt(password, bytes.fromhex(sec['salt'])).hex(), sec['hash']):
        FAILS['n'] += 1
        audit('unlock_failed', {'n': FAILS['n']})
        if FAILS['n'] >= 5:
            FAILS.update(n=0, until=now + 60)
        raise ValueError('Mật khẩu không đúng.')
    FAILS.update(n=0, until=0.0)
    audit('unlock', {})
    return new_session()


def new_session():
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = time.time() + SESSION_TTL
    return token


def session_left(token, touch=True):
    until = SESSIONS.get(token)
    if until is None or until < time.time():
        SESSIONS.pop(token, None)
        return 0
    if touch:
        SESSIONS[token] = time.time() + SESSION_TTL
        until = SESSIONS[token]
    return int(until - time.time())


BIOMETRIC_CHALLENGES: dict[str, float] = {}


def b64_decode(data: str) -> bytes:
    s = str(data or '').replace('-', '+').replace('_', '/')
    pad = len(s) % 4
    if pad:
        s += '=' * (4 - pad)
    return base64.b64decode(s)


def b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii').replace('+', '-').replace('/', '_').rstrip('=')


def has_biometric() -> bool:
    if not configured():
        return False
    sec = read_json(SECURITY_FILE, {})
    return bool(sec and (sec.get('ai_face_descriptor') or sec.get('biometric')))


def create_biometric_challenge() -> str:
    now = time.time()
    for k in [k for k, exp in BIOMETRIC_CHALLENGES.items() if exp < now]:
        BIOMETRIC_CHALLENGES.pop(k, None)
    chal = secrets.token_urlsafe(32)
    BIOMETRIC_CHALLENGES[chal] = now + 60.0
    return chal


def extract_der_from_attestation(att_bytes: bytes) -> bytes:
    idx = att_bytes.find(b'authData')
    if idx == -1:
        raise ValueError('Không tìm thấy authData trong attestationObject.')
    post = att_bytes[idx + 8:]
    if not post:
        raise ValueError('authData rỗng.')
    if post[0] == 0x58:
        auth_len = post[1]
        auth_data = post[2:2 + auth_len]
    elif post[0] == 0x59:
        auth_len = int.from_bytes(post[1:3], 'big')
        auth_data = post[3:3 + auth_len]
    else:
        auth_data = post[1:]

    if len(auth_data) < 55:
        raise ValueError('authData quá ngắn.')
    cred_id_len = int.from_bytes(auth_data[53:55], 'big')
    cose_bytes = auth_data[55 + cred_id_len:]
    idx_x = cose_bytes.find(b'\x21\x58\x20')
    idx_y = cose_bytes.find(b'\x22\x58\x20')
    if idx_x != -1 and idx_y != -1:
        x_bytes = cose_bytes[idx_x + 3:idx_x + 35]
        y_bytes = cose_bytes[idx_y + 3:idx_y + 35]
        pub_num = ec.EllipticCurvePublicNumbers(int.from_bytes(x_bytes, 'big'), int.from_bytes(y_bytes, 'big'), ec.SECP256R1())
        return pub_num.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    raise ValueError('Không trích xuất được tọa độ P-256 từ COSE key.')


def register_biometric(credential_id: str, public_key_der_b64: str = '', attestation_b64: str = ''):
    if not HAS_CRYPTOGRAPHY:
        raise ValueError('Máy chủ chưa hỗ trợ thư viện cryptography cho WebAuthn.')
    sec = read_json(SECURITY_FILE, None)
    if sec is None:
        raise ValueError('Chưa đặt mật khẩu nạp dữ liệu.')

    der_bytes = None
    if public_key_der_b64:
        try:
            raw = b64_decode(public_key_der_b64)
            serialization.load_der_public_key(raw)
            der_bytes = raw
        except Exception:
            der_bytes = None

    if not der_bytes and attestation_b64:
        try:
            der_bytes = extract_der_from_attestation(b64_decode(attestation_b64))
        except Exception as exc:
            raise ValueError(f'Không trích xuất được khóa công khai từ attestationObject: {exc}') from exc

    if not der_bytes:
        raise ValueError('Không nhận được khóa công khai sinh trắc học hợp lệ.')

    sec['biometric'] = dict(
        credential_id=credential_id,
        public_key=b64_encode(der_bytes),
        created_at=time.strftime('%Y-%m-%d %H:%M:%S'),
        counter=0
    )
    write_json(SECURITY_FILE, sec)
    audit('biometric_registered', dict(credential_id=credential_id[:16] + '...'))


def save_face_descriptor(descriptor: list[float]):
    if not configured():
        raise ValueError('Chưa đặt mật khẩu nạp dữ liệu.')
    if not isinstance(descriptor, list) or len(descriptor) != 128:
        raise ValueError('Vector đặc trưng khuôn mặt không hợp lệ (cần 128 chiều).')
    sec = read_json(SECURITY_FILE, {})
    sec['ai_face_descriptor'] = [float(x) for x in descriptor]
    sec['ai_face_enrolled_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    write_json(SECURITY_FILE, sec)
    audit('ai_face_enrolled', {})


def verify_face_descriptor(probe_descriptor: list[float], threshold: float = 0.55) -> str:
    now = time.time()
    if FAILS['until'] > now:
        raise ValueError(f'Nhập sai nhiều lần. Thử lại sau {int(FAILS["until"] - now) + 1} giây.')
    sec = read_json(SECURITY_FILE, None)
    if not sec or not sec.get('ai_face_descriptor'):
        raise ValueError('Chưa đăng ký khuôn mặt FaceID.')
    if not isinstance(probe_descriptor, list) or len(probe_descriptor) != 128:
        raise ValueError('Dữ liệu quét khuôn mặt không hợp lệ.')

    enrolled = sec['ai_face_descriptor']
    # Calculate Euclidean distance
    dist = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(enrolled, probe_descriptor)))
    if dist > threshold:
        FAILS['n'] += 1
        audit('ai_face_unlock_failed', {'dist': round(dist, 4), 'n': FAILS['n']})
        if FAILS['n'] >= 5:
            FAILS.update(n=0, until=now + 60)
        raise ValueError(f'Khuôn mặt không khớp (độ sai biệt: {dist:.2f} > {threshold}).')

    FAILS.update(n=0, until=0.0)
    audit('ai_face_unlock', {'dist': round(dist, 4)})
    return new_session()


def remove_biometric():
    sec = read_json(SECURITY_FILE, None)
    if sec:
        sec.pop('biometric', None)
        sec.pop('ai_face_descriptor', None)
        sec.pop('ai_face_enrolled_at', None)
        write_json(SECURITY_FILE, sec)
        audit('biometric_removed', {})


def verify_biometric(credential_id: str, client_data_b64: str, auth_data_b64: str, signature_b64: str) -> str:
    now = time.time()
    if FAILS['until'] > now:
        raise ValueError(f'Nhập sai nhiều lần. Thử lại sau {int(FAILS["until"] - now) + 1} giây.')
    if not HAS_CRYPTOGRAPHY:
        raise ValueError('Máy chủ chưa hỗ trợ thư viện cryptography.')
    sec = read_json(SECURITY_FILE, None)
    bio = sec.get('biometric') if sec else None
    if not bio:
        raise ValueError('Chưa kích hoạt mở khóa bằng FaceID/sinh trắc học.')
    if bio.get('credential_id') != credential_id:
        raise ValueError('Mã định danh thiết bị sinh trắc học không khớp.')

    try:
        client_data_raw = b64_decode(client_data_b64)
        client_data = json.loads(client_data_raw.decode('utf-8'))
    except Exception:
        raise ValueError('Dữ liệu xác thực clientDataJSON không hợp lệ.')

    if client_data.get('type') != 'webauthn.get':
        raise ValueError('Loại thao tác xác thực không hợp lệ.')

    chal = client_data.get('challenge', '')
    exp = BIOMETRIC_CHALLENGES.pop(chal, None)
    if not exp or exp < now:
        raise ValueError('Phiên xác thực sinh trắc học đã hết hạn hoặc bị phát lại. Vui lòng thử lại.')

    origin = client_data.get('origin', '')
    if not any(origin.startswith(o) for o in ORIGINS):
        raise ValueError(f'Nguồn gốc {origin} không hợp lệ.')

    try:
        auth_data = b64_decode(auth_data_b64)
    except Exception:
        raise ValueError('Dữ liệu authenticatorData không hợp lệ.')

    if len(auth_data) < 37:
        raise ValueError('Độ dài authenticatorData không đúng.')

    flags = auth_data[32]
    if not (flags & 0x01):
        raise ValueError('Không phát hiện hiện diện của người dùng (User Present flag is off).')

    try:
        der_bytes = b64_decode(bio['public_key'])
        pub_key = serialization.load_der_public_key(der_bytes)
        sig = b64_decode(signature_b64)
        client_hash = hashlib.sha256(client_data_raw).digest()
        signed_payload = auth_data + client_hash
        pub_key.verify(sig, signed_payload, ec.ECDSA(hashes.SHA256()))
    except Exception:
        FAILS['n'] += 1
        audit('biometric_unlock_failed', {'n': FAILS['n']})
        if FAILS['n'] >= 5:
            FAILS.update(n=0, until=now + 60)
        raise ValueError('Chữ ký sinh trắc học không khớp hoặc bị từ chối.')

    FAILS.update(n=0, until=0.0)
    audit('biometric_unlock', {})
    return new_session()


def batches():
    return read_json(BATCH_FILE, [])


def current_batches():
    code = company()['code']
    return [b for b in batches() if b['company'] == code]


def package_summary():
    mine = current_batches()
    if not mine:
        return None
    last = mine[-1]
    return dict(version=last['version'], sealed_at=last['sealed_at'], files=sum(len(b['files']) for b in mine),
                manifest=last['manifest'][:12], amendments=len(mine) - 1, last_reason=last['reason'], company=last['company'])


SLOTS = [
    ('agent1', 'invoices', 'Hóa đơn bán'), ('agent1', 'payments', 'Tiền khách trả'), ('agent1', 'outflows', 'Lịch cố định T5'),
    ('agent1', 'bank', 'Dòng sao kê'), ('agent1', 'statements', 'Kỳ sao kê'), ('agent1', 'actions', 'Hứa trả và nhắc nợ'),
    ('agent2', 'transactions', 'Sổ giao dịch'),
    ('agent3', 'xml', 'Hóa đơn XML hoặc ZIP'), ('agent3', 'list', 'Sao kê hoặc bảng kê'),
]


def slot_of(kind):
    if kind.startswith('a1:'):
        return 'agent1:' + kind[3:]
    return {'transactions': 'agent2:transactions', 'invoice_xml': 'agent3:xml', 'zip': 'agent3:xml',
            'statement_or_list': 'agent3:list'}.get(kind, '')


def target_slot(record, aid):
    if record.get('kind') == 'shared_bank':
        return 'agent1:bank' if aid == 'agent1' else 'agent3:list'
    return record.get('slot')


def slots_state(pending_records):
    sealed = {target_slot(f, aid) for b in current_batches() for f in b['files']
              for aid, result in f.get('results', {}).items() if result.get('state') == 'done'}
    waiting = {target_slot(r, aid) for r in pending_records
               for aid, check_result in r.get('checks', {}).items() if check_result.get('state') == 'ready'}
    out = []
    for aid, key, label in SLOTS:
        s = f'{aid}:{key}'
        out.append(dict(agent=aid, key=key, label=label, state='pending' if s in waiting else 'sealed' if s in sealed else 'empty'))
    return out


# ----------------------------------------------------------------------------------------------------------- inbox
def intake_context():
    c = company()
    return {key: c[key] for key in ('code', 'agent2_company', 'tax_code', 'date_format', 'number_format')}


def pending():
    context = intake_context()
    out = []
    for meta in sorted(PENDING.glob('*.json')):
        record = read_json(meta, None)
        if not record:
            continue
        bound = record.get('intake_context')
        if bound is not None and bound['code'] != context['code']:
            continue
        if bound != context:
            record['checks'] = {aid: dict(state='stale', message='Cần kiểm tra lại với hồ sơ hiện tại.')
                                for aid in record['targets']}
        out.append(record)
    return sorted(out, key=lambda r: r['added_at'])


def pending_file(fid, context):
    record = read_json(PENDING / f'{fid}.json', None)
    if record is None or record.get('intake_context', context)['code'] != context['code']:
        raise KeyError('Không có tệp này trong hàng chờ của doanh nghiệp hiện tại.')
    return record


def history():
    return read_json(WORK / 'history.json', [])


def _day(text):
    m = re.match(r'\s*(\d{4})-(\d{2})-(\d{2})', text) or None
    if m:
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
    m = re.match(r'\s*(\d{1,2})/(\d{1,2})/(\d{4})', text)
    return f'{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}' if m else None


DATE_COLUMNS = ('issue date', 'ngay lap', 'payment date', 'ngay thanh toan', 'posted at', 'ngay giao dich', 'date', 'ngay chi', 'ngay su kien', 'end date')


def period_of(name, raw, kind):
    """First and last document date in the file, as ISO days, or None when it cannot be read cheaply."""
    ext = Path(name).suffix.lower()
    try:
        days = []
        if ext in ('.csv', '.txt') and kind != 'unknown':
            text = raw.decode('utf-8-sig', 'replace')
            lines = text.splitlines()
            delimiter = max((',', ';', '\t'), key=lines[0].count)
            rows = csv.reader(lines, delimiter=delimiter)
            header = [plain(c) for c in next(rows)]
            col = next((header.index(c) for c in DATE_COLUMNS if c in header), None)
            if col is None:
                return None
            for i, row in enumerate(rows):
                if i > 300000:
                    break
                d = _day(row[col]) if col < len(row) else None
                if d:
                    days.append(d)
        elif ext == '.xml':
            days = re.findall(rb'<NLap>(\d{4}-\d{2}-\d{2})', raw[:200000])
            days = [d.decode() for d in days]
        elif ext == '.zip':
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                for member in z.infolist()[:500]:
                    if member.filename.lower().endswith('.xml'):
                        days += [d.decode() for d in re.findall(rb'<NLap>(\d{4}-\d{2}-\d{2})', z.read(member)[:200000])]
        return [min(days), max(days)] if days else None
    except (zipfile.BadZipFile, ValueError, IndexError, StopIteration, csv.Error):
        return None


def add_file(name, raw):
    context = intake_context()
    if not context['code']:
        raise ValueError('Lưu hồ sơ doanh nghiệp trước khi nạp tệp.')
    clean = re.sub(r'[^\w.\-]', '_', Path(name).name)[:120] or 'tep'
    classification = classify(clean, raw)
    digest = hashlib.sha256(raw).hexdigest()
    if classification['kind'] == 'shared_bank':
        for existing in pending():
            if existing.get('sha256') == digest and existing.get('intake_context') == context:
                return existing
        received = {aid: result for batch in current_batches() for item in batch['files']
                    if item.get('kind') == 'shared_bank' and item.get('sha256') == digest
                    and item.get('intake_context') == context
                    for aid, result in item.get('results', {}).items() if result.get('state') == 'done'}
        if set(received) >= set(classification['targets']):
            raise ValueError('Sao kê này đã được ghi vào cả Agent 1 và Agent 3 cho doanh nghiệp đang chọn.')
    fid = uuid.uuid4().hex[:12]
    (PENDING / f'{fid}.bin').write_bytes(raw)
    record = dict(id=fid, name=clean, size=len(raw), added_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                  intake_context=context, **classification)
    record['slot'] = slot_of(record['kind'])
    record['period'] = period_of(clean, raw, record['kind'])
    record['sha256'] = digest
    if classification['kind'] == 'shared_bank' and received:
        record['applied'] = received
    record['checks'] = preview_file(record, raw)
    write_json(PENDING / f'{fid}.json', record)
    return record


def recheck(fid):
    context = intake_context()
    if not context['code']:
        raise ValueError('Lưu hồ sơ doanh nghiệp trước khi kiểm tra tệp.')
    record = pending_file(fid, context)
    raw = (PENDING / f'{fid}.bin').read_bytes()
    if record.get('applied') and record.get('intake_context') != context:
        raise ValueError('Tệp đã ghi một phần với cấu hình cũ. Giữ nguyên hồ sơ để ghi tiếp.')
    if not record.get('applied'):
        record.update(classify(record['name'], raw))
        record['slot'] = slot_of(record['kind'])
    record['intake_context'] = context
    record['checks'] = preview_file(record, raw)
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


def shared_bank_rows(record, raw):
    rows = (xlsx_rows(raw) if record['name'].lower().endswith('.xlsx') else
            (row for row in bank_intake.csv_rows(raw) if any(cell.strip() for cell in row)))
    header = next(rows, [])
    fields = bank_intake.columns(header, plain)
    if fields is None:
        raise ValueError('Thiếu cột sao kê dùng chung. Xem mẫu trên màn Nạp dữ liệu.')
    return bank_intake.normalize_rows(rows, fields, record['intake_context']['number_format'], plain)


def preview_file(record, raw):
    rows = None
    if record['kind'] == 'shared_bank':
        try:
            rows = shared_bank_rows(record, raw)
        except (ValueError, InvalidOperation, csv.Error, ElementTree.ParseError, zipfile.BadZipFile) as exc:
            return {aid: dict(state='error', message=str(exc)) for aid in record['targets']}
        record['period'] = [min(row[2] for row in rows), max(row[2] for row in rows)]
    applied = record.get('applied', {})
    return {aid: applied[aid] if aid in applied else check(aid, record, raw, bank_rows=rows)
            for aid in record['targets']}


def check(aid, record, raw, *, bank_rows=None):
    """Run the agent's own preview; nothing is written to the agent here."""
    c = company()
    if not health(aid):
        return dict(state='offline', message='Agent chưa bật. Bật ở trang Tổng quan rồi bấm Kiểm tra lại.')
    if aid == 'agent1':
        key = agent1_key()
        shared = bank_rows is not None
        kind = 'bank' if shared else record['kind'].split(':', 1)[1]
        mapping = json.dumps({field: field for field in ('bank_id', 'account', 'date', 'direction', 'amount', 'known_at',
                                                        'component', 'memo', 'counterparty', 'customer_id',
                                                        'cash_flow_class')}) if shared else '{}'
        body, ctype = multipart(dict(kind=kind, mapping=mapping,
                                     date_format='%Y-%m-%d' if c['date_format'] == 'iso' else '%d/%m/%Y',
                                     number_format=c['number_format']), 'file',
                                'sao_ke_chung.csv' if shared else record['name'],
                                bank_intake.project(bank_rows, aid, date_format=c['date_format'], number_format=c['number_format']) if shared else raw)
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
        workspace = ensure_agent3_workspace()
        if workspace['state'] != 'ok':
            return dict(state='error', message=workspace['message'])
        if bank_rows is not None:
            return dict(state='ready', rows=len(bank_rows), message=f'{len(bank_rows)} dòng sao kê đã chuẩn hóa')
        return dict(state='ready', message='Agent 3 tự phân loại khi ghi; tệp trùng nội dung không bị nạp hai lần.')
    return dict(state='error', message='Agent này chưa nhận tệp.')


def agent3_workspace():
    tax = re.sub(r'[^0-9-]', '', company()['tax_code'] or '')
    return tax if tax and mst_ok(tax) else ''


def ensure_agent3_workspace(password=None):
    """Synchronize from the shared file through the backend-only bridge."""
    status, result = call('POST', agent_url('agent3', '/api/platform/sync'), {},
                          {'X-Agent3-Platform-Token': AGENT3_TOKEN})
    if status == 0:
        return dict(state='offline', message='Agent 3 chưa bật. Khởi động Agent 3 từ portal để đồng bộ hồ sơ.')
    if status != 200:
        return dict(state='error', message='Không đồng bộ được Agent 3. Kiểm tra hồ sơ chung và khởi động lại Agent 3 từ portal.')
    return dict(state='ok', id=result['workspace_id'], profile_revision=result['profile_revision'],
                message='Hồ sơ Agent 3 đã đồng bộ từ portal.')


def commit(fids, reason=''):
    """Write the checked files to their agents and record them as one sealed batch (version) of the company's package."""
    context = intake_context()
    records = [pending_file(fid, context) for fid in dict.fromkeys(fids)]
    if not context['code'] or any(r.get('intake_context') != context for r in records):
        raise ValueError('Hồ sơ doanh nghiệp đã đổi. Kiểm tra lại các tệp trước khi ghi.')
    prior = current_batches()
    reason = (reason or '').strip()
    if prior and len(reason) < 10:
        raise ValueError('Gói đã được niêm phong. Bổ sung hoặc thay thế cần lý do, ít nhất 10 ký tự.')
    entries = []
    completed = []
    for record in records:
        fid = record['id']
        raw = (PENDING / f'{fid}.bin').read_bytes()
        shared = record['kind'] == 'shared_bank'
        bank_rows = None
        applied = record.get('applied', {})
        if shared:
            if not all(aid in applied or record['checks'].get(aid, {}).get('state') == 'ready' for aid in record['targets']):
                continue
            bank_rows = shared_bank_rows(record, raw)
            # Keep the original once per company, including when a downstream write needs a retry.
            archive = WORK / 'bank_sources' / hashlib.sha256(context['code'].encode()).hexdigest()
            archive.mkdir(parents=True, exist_ok=True)
            original = archive / hashlib.sha256(raw).hexdigest()
            if not original.exists():
                original.write_bytes(raw)
        outcome = {}
        for aid in record['targets']:
            if aid in applied:
                outcome[aid] = applied[aid]
                continue
            chk = record.get('checks', {}).get(aid, {})
            if chk.get('state') != 'ready':
                outcome[aid] = dict(state='skipped', message='Chưa qua kiểm tra nên không ghi.')
                continue
            if aid == 'agent1':
                chk = check('agent1', record, raw, bank_rows=bank_rows)  # fresh preview after earlier writes
                if chk.get('state') != 'ready':
                    outcome[aid] = dict(state='error', message=chk.get('message', 'Kiểm tra lại không đạt.'))
                    if shared:
                        record['checks'][aid] = outcome[aid]
                        write_json(PENDING / f'{fid}.json', record)
                        break
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
                if ws['state'] == 'ok' and intake_context() != context:
                    ws = dict(state='error', message='Hồ sơ doanh nghiệp đã đổi trong khi ghi. Kiểm tra lại tệp trước khi gửi Agent 3.')
                if ws['state'] != 'ok':
                    outcome[aid] = dict(state='error', message=ws['message'])
                    continue
                content = bank_intake.project(bank_rows, aid) if shared else raw
                name = f'sao_ke_{hashlib.sha256(content).hexdigest()[:16]}.csv' if shared else record['name']
                status, res = call('PUT', agent_url('agent3', f'/api/workspaces/{ws["id"]}/inbox?name={quote(name)}'), content,
                                   {'Content-Type': 'application/octet-stream', 'X-Agent3-Profile-Revision': ws['profile_revision']}, timeout=600)
                if status == 200:
                    used = [f for f in res.get('files', []) if f.get('label') != 'Không dùng']
                    rejection = '; '.join(f.get('reason', '') for f in res.get('files', []))
                    outcome[aid] = dict(state='done' if used else 'error' if shared else 'skipped',
                                        message=(f'Đã nạp {len(used)} tệp: ' + ', '.join(sorted({f["label"] for f in used})))
                                        if used else rejection or 'Agent 3 không dùng tệp này.')
                else:
                    outcome[aid] = dict(state='error', message=res.get('error', f'Lỗi {status}'))
            if shared:
                if outcome[aid]['state'] == 'done':
                    applied[aid] = outcome[aid]
                    record['applied'] = applied
                record['checks'][aid] = outcome[aid]
                write_json(PENDING / f'{fid}.json', record)
                if outcome[aid]['state'] != 'done':
                    break
        if any(v['state'] == 'done' for v in outcome.values()):
            entries.append(dict(name=record['name'], label=record['label'], size=record['size'], sha256=record.get('sha256')
                                or hashlib.sha256(raw).hexdigest(), kind=record['kind'], slot=record.get('slot', ''), period=record.get('period'),
                                results=outcome, **({'intake_context': context} if shared else {})))
            if (len(applied) == len(record['targets']) if shared else
                    all(v['state'] in ('done', 'skipped') for v in outcome.values())):
                completed.append(fid)
    if not entries:
        raise ValueError('Không tệp nào được ghi. Xem kết quả kiểm tra của từng tệp.')
    manifest = hashlib.sha256('\n'.join(sorted(f'{e["name"]}:{e["sha256"]}' for e in entries)).encode('utf-8')).hexdigest()
    batch = dict(id=uuid.uuid4().hex[:10], company=context['code'], version=len(prior) + 1, kind='bổ sung' if prior else 'gốc',
                 sealed_at=time.strftime('%Y-%m-%d %H:%M:%S'), reason=reason, files=entries, manifest=manifest)
    with LOCK:
        write_json(BATCH_FILE, batches() + [batch])
    audit('commit', dict(batch=batch['id'], version=batch['version'], company=batch['company'], files=len(entries), manifest=manifest[:16],
                         reason=reason))
    for fid in completed:
        remove_file(fid)
    # Files that failed only because they point at rows written just now (payments after invoices) pass on a new check.
    for record in pending():
        if record.get('intake_context') == context and any(s.get('state') != 'ready' for s in record.get('checks', {}).values()):
            recheck(record['id'])
    return batch


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
                         "default-src 'self'; style-src 'self'; font-src 'self'; "
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
        ctype = {'.woff2': 'font/woff2', '.webp': 'image/webp'}.get(target.suffix, ctype)
        if ctype.startswith('text/') or ctype in ('application/javascript',):
            ctype += '; charset=utf-8'
        self.send(200, target.read_bytes(), ctype, {'Cache-Control': 'public, max-age=3600'} if target.suffix in ('.woff2', '.svg') else None)

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

    def token(self):
        return self.headers.get('X-Session', '')

    def need_session(self):
        if not session_left(self.token()):
            raise AuthError('Cần mở khóa nạp dữ liệu bằng mật khẩu.')

    def route(self, method):
        url = urlsplit(self.path)
        path, query = url.path, {k: v[-1] for k, v in parse_qs(url.query).items()}
        if method == 'GET':
            if path == '/api/state':
                left = session_left(self.token(), touch=False)
                recs = pending() if left else []
                return self.send(200, dict(company=company(), agents=[agent_state(a) for a in AGENTS], origin=ORIGIN,
                                           intake=dict(configured=configured(), unlocked=bool(left), seconds_left=left, has_biometric=has_biometric()),
                                           package=package_summary(), slots=slots_state(recs), pending=recs,
                                           batches=list(reversed(current_batches()))[:30] if left else []))
            if path == '/api/intake/audit':
                self.need_session()
                return self.send(200, audit_check())
            if path == '/api/agents/agent1/key':
                return self.send(200, dict(key=agent1_key()))
            m = re.fullmatch(r'/api/agents/(agent[1-4])/log', path)
            if m:
                return self.send(200, dict(log=log_tail(m.group(1))))
            if path == '/api/agent4/metrics':
                return self.send(200, agent4_metrics())
            if path.startswith('/agent4/') or path == '/agent4':
                return self.static(CHAT, path[len('/agent4/'):])
            if path.startswith('/design/platform-fonts/'):
                return self.static(DESIGN / 'fonts', path[len('/design/platform-fonts/'):])
            if path.startswith('/design/'):
                return self.static(DESIGN, path[len('/design/'):])
            if path.startswith('/api/'):
                return self.send(404, {'error': 'Không có địa chỉ này.'})
            if path.startswith('/models/'):
                return self.static(STATIC / 'models', path[len('/models/'):])
            return self.static(STATIC, path.lstrip('/') if '.' in path.rsplit('/', 1)[-1] else '')
        self.guard()
        if method == 'POST' and path == '/api/agents/agent1/connect-link':
            body = self.json_body()
            return self.send(200, agent1_connect_link(body.get('company'), self.headers.get('Origin') or ORIGIN))
        if method == 'POST' and path == '/api/intake/setup':
            b = self.json_body()
            return self.send(200, dict(token=set_password(str(b.get('password', '')), str(b.get('confirm', '')))))
        if method == 'POST' and path == '/api/intake/unlock':
            return self.send(200, dict(token=unlock(str(self.json_body().get('password', '')))))
        if method == 'POST' and path == '/api/intake/face/register':
            b = self.json_body()
            pw = str(b.get('password', ''))
            descriptor = b.get('descriptor', [])
            if pw:
                unlock(pw)
            else:
                self.need_session()
            save_face_descriptor(descriptor)
            token = new_session()
            audit('ai_face_unlock', {'action': 'initial_registration'})
            return self.send(200, dict(ok=True, token=token))
        if method == 'POST' and path == '/api/intake/face/verify':
            b = self.json_body()
            descriptor = b.get('descriptor', [])
            token = verify_face_descriptor(descriptor)
            return self.send(200, dict(token=token))
        if method == 'POST' and path == '/api/intake/face/remove':
            self.need_session()
            remove_biometric()
            return self.send(200, dict(ok=True))
        if method == 'POST' and path == '/api/intake/lock':
            SESSIONS.pop(self.token(), None)
            audit('lock', {})
            return self.send(200, dict(ok=True))
        if method == 'PUT' and path == '/api/company':
            if current_batches():
                try:
                    self.need_session()
                except AuthError:
                    raise AuthError('Gói dữ liệu đã niêm phong nên cấu hình bị khóa. Mở khóa ở trang Nạp dữ liệu rồi sửa.') from None
            data, code_changed = save_company(self.json_body())
            audit('company_saved', dict(code=data['code'], tax_code=data['tax_code']))
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
            self.need_session()
            name = query.get('name', '')
            if not name:
                raise ValueError('Thiếu tên tệp.')
            if query.get('company', company()['code']) != company()['code']:
                raise ValueError('Doanh nghiệp đã đổi. Tải lại trang trước khi nạp tệp.')
            record = add_file(name, self.body(300 * 1024 * 1024))
            audit('upload', dict(company=record['intake_context']['code'], name=record['name'], size=record['size'],
                                 sha256=record['sha256'][:16]))
            return self.send(200, record)
        m = re.fullmatch(r'/api/inbox/([0-9a-f]{12})/(check|delete)', path)
        if method == 'POST' and m:
            self.need_session()
            fid, action = m.groups()
            if action == 'delete':
                pending_file(fid, intake_context())
                remove_file(fid)
                audit('discard', dict(id=fid))
                return self.send(200, dict(ok=True))
            return self.send(200, recheck(fid))
        if method == 'POST' and path == '/api/inbox/commit':
            self.need_session()
            b = self.json_body()
            ids = [i for i in b.get('ids', []) if re.fullmatch(r'[0-9a-f]{12}', str(i))]
            return self.send(200, dict(batch=commit(ids, str(b.get('reason', '')))))
        if method == 'POST' and path == '/api/agent4/query':
            question = str(self.json_body().get('question', '')).strip()[:2000]
            if not question:
                raise ValueError('Nhập câu hỏi.')
            return self.send(200, agent4_query(question))
        self.send(404, {'error': 'Không có địa chỉ này.'})

    def handle_one(self, method):
        try:
            path = urlsplit(self.path).path
            if method != 'GET' and (path in ('/api/company', '/api/agent3/workspace', '/api/agents/agent1/connect-link') or path.startswith('/api/inbox')):
                with LOCK:
                    self.route(method)
            else:
                self.route(method)
        except AuthError as e:
            self.send(401, {'error': str(e), 'locked': True})
        except PermissionError as e:
            self.send(403, {'error': str(e)})
        except (ValueError, KeyError) as e:
            self.send(400, {'error': str(e).strip("'")})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # The browser navigated away before the response arrived.
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
    print(f'Portal: {ORIGIN} (Ctrl+C to stop the portal and its agents)', flush=True)
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
