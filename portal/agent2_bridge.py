"""Portal session bridge to Agent2. Permissions come only from an operator file.

The current Portal has one shared workspace login, not named user accounts.
Changing its company profile cannot change these memberships.
"""
from datetime import datetime, timezone
import json
import re
import time
from pathlib import Path
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

VERSION = 'portal-agent2-access/1.0.0'
SESSION_VERSION = 'portal-agent2-session/1.0.0'
ID = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')
PERMISSIONS = {'data.import', 'evidence.verify', 'model.fit'}


class BridgeError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def discard_rejected_body(handler):
    """Bounded transport-only drain so a 401 survives Windows TCP close.

    Authorization has already failed. Never parse/store/forward this body, and
    never wait for an unbounded or malformed upload merely to send a denial.
    """
    if handler.command not in ('POST','PUT') or handler.headers.get_all('Transfer-Encoding',[]):return
    sizes=handler.headers.get_all('Content-Length',[])
    if len(sizes)!=1 or not re.fullmatch(r'[0-9]{1,12}',sizes[0]):return
    remaining=int(sizes[0])
    if not 0<remaining<=10*1024*1024:return
    previous=handler.connection.gettimeout();deadline=time.monotonic()+.25
    try:
        handler.connection.settimeout(.1)
        while remaining and time.monotonic()<deadline:
            chunk=handler.rfile.read1(min(8192,remaining))
            if not chunk:break
            remaining-=len(chunk)
    except OSError:
        pass
    finally:handler.connection.settimeout(previous)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:raise ValueError('duplicate key')
        result[key] = value
    return result


def identity(path, expires_at):
    """Strict server-side policy. No default membership, tenant or role."""
    try:
        with Path(path).open('rb') as stream:raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:raise ValueError('policy size')
        data = json.loads(raw, object_pairs_hook=_unique)
        if not isinstance(data, dict) or set(data) != {'version','actor_id','tenant_id','status','memberships'}:raise ValueError('fields')
        if data['version'] != VERSION or data['status'] not in ('active','revoked'):raise ValueError('version/status')
        if not all(isinstance(data[k],str) and ID.fullmatch(data[k]) for k in ('actor_id','tenant_id')):raise ValueError('identity')
        members = data['memberships']
        if not isinstance(members,list) or len(members)>1024:raise ValueError('members')
        seen = set()
        for m in members:
            if not isinstance(m,dict) or set(m) != {'company_id','role','status','permissions'}:raise ValueError('member fields')
            if not isinstance(m['company_id'],str) or not ID.fullmatch(m['company_id']) or m['company_id'] in seen:raise ValueError('company')
            if m['role'] not in ('accountant','director') or m['status'] not in ('active','suspended','revoked'):raise ValueError('member role/status')
            if not isinstance(m['permissions'],list) or not all(isinstance(p,str) and p in PERMISSIONS for p in m['permissions']):raise ValueError('permissions')
            seen.add(m['company_id'])
    except (OSError,ValueError,TypeError,RecursionError,OverflowError):
        raise BridgeError(503,'Chưa có cấu hình quyền Agent2 hợp lệ. Người quản lý cần cấp quyền phía server.') from None
    if data['status'] != 'active':raise BridgeError(403,'Quyền truy cập Agent2 của workspace đã bị thu hồi.')
    return dict(data,version=SESSION_VERSION,expires_at=datetime.fromtimestamp(expires_at,timezone.utc).isoformat())


PUBLIC = {'/','/workspace','/status','/data-import','/encrypted-analysis','/analysis-settings','/assets/workspace.js','/assets/workspace.css','/assets/analysis-settings.js','/assets/he-analysis.js','/assets/workbench.js','/assets/workbench.css','/samples/import-demo.json','/samples/import-demo.csv','/samples/import-demo.xlsx','/api/v1/ui/settings'}
PUBLIC.update({'/label-verification','/assets/label-verification.js','/batch-training','/assets/batch-training.js'})
PUBLIC.update({'/pipeline-releases','/assets/pipeline-releases.js','/assets/pipeline-releases.css'})
PUBLIC.update({'/pipeline-workspace','/assets/bundle-workspace.js'})
PUBLIC.update({'/assets/bundle-remediation.js','/assets/bundle-remediation.css'})
PUBLIC.update({'/assets/rule-source-intake.js','/samples/rule-sources.xlsx'})
PUBLIC.update({'/assets/platform-theme.css','/assets/platform-theme.js'})
FONT_ASSET = re.compile(r'/assets/platform-fonts/[a-z0-9-]{3,64}\.woff2\Z')
HE_API = re.compile(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/he/(?:datasets|runs|jobs(?:/herun_[a-f0-9]{32}(?:/(?:result|resume|reviews(?:/rvw_[a-f0-9]{64}/(?:start|heartbeat|save|attachments(?:/att_[a-f0-9]{64})?))?))?)?)\Z')
API = re.compile(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/(?:imports/(?:upload|validate|imp_[a-f0-9]{32}(?:/(?:source|mapping|inspect|preview|commit|report))?)|snapshots/snp_[a-f0-9]{32}(?:/(?:data|analyze))?)\Z')


def allowed_path(path):
    if '..' in path or '//' in path:return False
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/pipeline-workspace/backlog(?:/(?:reevaluate|active|shadow))?',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/pipeline-workspace/runs/[A-Za-z0-9_.:-]{8,128}/reviews/rvw_[a-f0-9]{64}/remediation(?:/documents/doc_[a-f0-9]{24}/versions/[1-9][0-9]{0,3})?',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/pipeline-workspace(?:/runs(?:/[A-Za-z0-9_.:-]{8,128}(?:/(?:report(?:\.csv)?|reviews/rvw_[a-f0-9]{64}/(?:start|heartbeat|save|attachments|tasks)(?:/att_[a-f0-9]{64})?))?)?)?',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/pipeline-releases(?:/(?:prepare|qualify|approve|switch|revoke|diff|runs|objects/(?:rbun|rgat|rapr|ract|rpin|robs)_[a-f0-9]{64}))?',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/pipeline-benchmarks',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/remediation/(?:summary|report|tasks(?:/(?:filter/(?:all|mine_or_dept|due_soon|overdue|awaiting_confirmation|completed)|query|tsk_[a-f0-9]{24}/(?:assign|submit|decision)))?|cases/[A-Za-z0-9_.:-]{1,128}(?:/(?:checklist|documents))?|documents/doc_[a-f0-9]{24}(?:/(?:versions/[0-9]{1,4}(?:/content)?|content|verify))?)',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/case-queue/(?:evaluate|recover|reevaluate-backlog|(?:active|shadow)(?:/periods/[A-Za-z0-9_.-]{1,64})?(?:/technical)?|backlog(?:/shadow)?(?:/technical)?|cases/case_[a-f0-9]{32}(?:/workflow|(?:/shadow)?(?:/technical)?))',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/batch-training(?:/(?:preview|create-labels|confirm|resume|receive|evaluate|approve|shadow|shadow-runs(?:/(?:check|shrun_[0-9]+_[a-f0-9]{16}))?))?',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/(?:label-sources(?:/snp_[a-f0-9]{32})?|label-packets(?:/lbl_[a-f0-9]{64}(?:/(?:save|lock|reopen|export))?)?)',path):return True
    if re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/rules/catalogue',path):return True
    if FONT_ASSET.fullmatch(path):return True
    return path in PUBLIC or path == '/api/v1/ui/context' or API.fullmatch(path) is not None or HE_API.fullmatch(path) is not None or re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/workspace(?:/runs/herun_[a-f0-9]{32}(?:/(?:report|report\.csv|comparison))?)?',path) is not None or re.fullmatch(r'/api/v1/companies/[A-Za-z0-9_.:-]{1,128}/analysis-config(?:/(?:draft|fit|activate))?',path) is not None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):return None


def open_backend(request):
    return build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=600)
