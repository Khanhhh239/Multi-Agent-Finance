"""Trusted portal profile bridge. No browser-selected or standalone enterprises."""
import contextvars
from contextlib import contextmanager
import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from ..extraction.xml_invoice import mst_checksum_ok

LOCK = threading.Lock()
REVISION = contextvars.ContextVar('agent3_profile_revision', default=None)
LOCK_HELD = contextvars.ContextVar('agent3_disk_lock_held', default=False)


@contextmanager
def writing():
    if LOCK_HELD.get():
        yield
    else:
        with LOCK:
            yield


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def etag(ws):
    return '"' + hashlib.sha256((ws / 'pack.json').read_bytes()).hexdigest() + '"'


class Bridge:
    def __init__(self, source, token, portal_url, root, save):
        self.source = Path(source) if source else None
        self.token = token
        u = urlsplit(portal_url)
        self.portal_url = portal_url.rstrip('/') if u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1', '::1') and not u.username and not u.password and u.path in ('', '/') and not u.query and not u.fragment else None
        self.root = root
        self.save = save
        self.bound = None

    def context(self):
        base = dict(state='unconnected', workspace_id=None, profile=None, profile_revision=None, portal_url=self.portal_url)
        if not self.source or not self.token or not self.portal_url:
            return base
        try:
            c = json.loads(self.source.read_text(encoding='utf-8-sig'))
            if not isinstance(c, dict):
                return dict(base, state='invalid_profile')
            tax = str(c.get('tax_code') or '').strip()
            wid = tax.replace('-', '')
            industry = c.get('industry') or []
            if isinstance(industry, str):
                industry = [x.strip() for x in re.split(r'[;\n]', industry) if x.strip()]
            profile = dict(tax_code=tax, legal_name=str(c.get('legal_name') or '').strip(),
                           registered_address=c.get('registered_address') or None, industry=industry,
                           vat_method=c.get('vat_method'), filing_period=c.get('filing_period'),
                           fiscal_year_end_month=c.get('fiscal_year_end_month', 12))
            if not tax or not profile['legal_name']:
                return dict(base, state='missing_profile')
            if (not re.fullmatch(r'\d{10}(?:\d{3})?', wid) or not mst_checksum_ok(wid)
                    or profile['vat_method'] not in ('DIRECT', 'DEDUCTION')
                    or profile['filing_period'] not in ('MONTH', 'QUARTER')
                    or type(profile['fiscal_year_end_month']) is not int
                    or not 1 <= profile['fiscal_year_end_month'] <= 12
                    or not isinstance(industry, list) or any(not isinstance(x, str) for x in industry)):
                return dict(base, state='invalid_profile')
            revision = digest(dict(code=c.get('code'), profile=profile))
            result = dict(base, profile=profile, profile_revision=revision, state='sync_required')
            matches = []
            for p in self.root.glob('*/pack.json'):
                old = json.loads(p.read_text(encoding='utf-8'))
                if not isinstance(old, dict) or not isinstance(old.get('profile'), dict):
                    return dict(result, state='conflict')
                if str(old.get('profile', {}).get('tax_code', '')).replace('-', '') == wid:
                    if old.get('simulated'):
                        return dict(result, state='conflict')
                    matches.append(p.parent.name)
            if len(matches) > 1:
                return dict(result, state='conflict')
            chosen = matches[0] if matches else wid
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,40}', chosen):
                return dict(result, state='conflict')
            if (self.root / chosen).is_symlink():
                return dict(result, state='conflict')
            target = self.root / chosen
            if target.resolve().parent != self.root.resolve():
                return dict(result, state='conflict')
            if not matches and target.exists() and any(target.iterdir()):
                return dict(result, state='conflict')
            result['workspace_id'] = chosen
            if self.bound == (chosen, revision):
                result['state'] = 'ready'
            return result
        except FileNotFoundError:
            return dict(base, state='missing_profile')
        except (ValueError, TypeError, OSError):
            return dict(base, state='invalid_profile')

    def sync(self):
        c = self.context()
        if c['state'] not in ('ready', 'sync_required'):
            raise HTTPException(409, 'Hồ sơ portal chưa hợp lệ hoặc trùng doanh nghiệp. Kiểm tra tại portal.')
        ws = self.root / c['workspace_id']
        old = json.loads((ws / 'pack.json').read_text(encoding='utf-8')) if (ws / 'pack.json').exists() else dict(pack_version=1, policies=[], thresholds={}, bank_formats=[], reference_lists=[], ai_categories=[], days_off=[])
        next_pack = dict(old, profile=c['profile'])
        ws.mkdir(parents=True, exist_ok=True)
        if old != next_pack:
            self.save(ws, next_pack, 'portal')
        # The master file may change during disk writes. Never bind an obsolete revision.
        if self.context()['profile_revision'] != c['profile_revision']:
            self.bound = None
            raise HTTPException(409, 'Hồ sơ portal vừa thay đổi; đồng bộ lại.')
        self.bound = (ws.name, c['profile_revision'])
        return self.context()

    def require(self, wid=None, revision=None):
        c = self.context()
        expected = revision if revision is not None else REVISION.get()
        if c['state'] != 'ready' or not expected or expected != c['profile_revision']:
            raise HTTPException(409, dict(context_stale=True, message='Doanh nghiệp hoặc hồ sơ đã thay đổi. Tải lại trang.'))
        if wid is not None and wid != c['workspace_id']:
            raise HTTPException(403, 'Chỉ được truy cập doanh nghiệp hiện tại của portal.')
        return c
