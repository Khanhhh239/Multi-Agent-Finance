"""Revalidate the existing Portal session and trusted memberships on every guard."""
from datetime import datetime, timezone
import json
import hashlib
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError

from finance_input.json_io import loads
from .auth import FileAuthorizer, AuthError, _denied, parse_policy


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):return None


class PortalAuthorizer(FileAuthorizer):
    mode = 'portal'

    def __init__(self, portal_url, bridge_secret, clock=None):
        parsed = urlsplit(portal_url)
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1','localhost'} or
            parsed.username or parsed.password or not parsed.port or parsed.path not in ('','/') or parsed.query or parsed.fragment):
            raise ValueError('Portal URL must be a configured HTTP loopback origin')
        if not isinstance(bridge_secret,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',bridge_secret):
            raise ValueError('Missing valid backend-only Portal bridge secret')
        self.portal_url = portal_url.rstrip('/')
        self.secret = bridge_secret
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.opener = build_opener(ProxyHandler({}),NoRedirect())

    @property
    def configured(self):return True

    def describe(self, authorization):
        principal = self._authorized_principal(authorization)
        grants = [dict(company_id=m.company_id,role=m.role,status=m.status,permissions=sorted(m.permissions)) for m in principal.memberships]
        context = json.dumps([principal.tenant_id,principal.actor_id,grants],sort_keys=True,separators=(',',':')).encode()
        return dict(actor_id=principal.actor_id,companies=[m.company_id for m in principal.memberships if m.status=='active' and 'data.import' in m.permissions],
                    context_id=hashlib.sha256(context).hexdigest())

    def _authorized_principal(self, authorization):
        if not isinstance(authorization,str) or len(authorization)>4096:raise _denied()
        parts = authorization.split()
        if len(parts)!=2 or parts[0].lower()!='bearer' or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',parts[1]):raise _denied()
        request = Request(self.portal_url+'/api/internal/agent2/identity',
            data=json.dumps(dict(session=parts[1])).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.secret})
        try:
            with self.opener.open(request,timeout=3) as response:
                raw = response.read(1024*1024+1)
                if response.status!=200 or len(raw)>1024*1024:raise ValueError('identity response')
            data = loads(raw)
            if not isinstance(data,dict) or set(data)!={'version','actor_id','tenant_id','status','memberships','expires_at'} or data['version']!='portal-agent2-session/1.0.0':raise ValueError('identity contract')
            principal = parse_policy(dict(policy_version='1.0.0',principals=[{k:v for k,v in dict(data,token_sha256='0'*64).items() if k!='version'}]))[0]
            if principal.status!='active' or principal.expires_at<=self.clock():raise _denied()
            return principal
        except HTTPError as error:
            if error.code==401:raise _denied() from None
            if error.code==403:raise _denied(403) from None
            raise AuthError(503,'PORTAL_UNAVAILABLE','Chưa xác minh được phiên và quyền từ Portal.','Kiểm tra Portal rồi thử lại; dữ liệu chưa được cấp quyền.') from None
        except (URLError,OSError,ValueError,TypeError,KeyError,RecursionError,OverflowError):
            raise AuthError(503,'PORTAL_UNAVAILABLE','Chưa xác minh được phiên và quyền từ Portal.','Kiểm tra Portal rồi thử lại; không dùng quyền lưu tạm.') from None
