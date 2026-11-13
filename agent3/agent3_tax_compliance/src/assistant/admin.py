"""Administrator password for the settings page.

The settings (enterprise profile and policies, risk lists, shared catalogs, legal corpus sync, new enterprises) change
what every user sees, so they need the administrator password. Day-to-day work (loading files, reviewing, deciding,
asking) does not.

The password is stored only as a scrypt hash with a random salt in data/admin.json. A login gives an HttpOnly cookie
valid 30 minutes from the last request. Five wrong passwords lock logins for one minute. This guards against
accidental or casual changes on a shared office computer; it is not a replacement for securing the machine itself.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

PROJECT = Path(__file__).resolve().parents[2]
STORE = Path(os.environ.get('AGENT3_ADMIN_STORE') or PROJECT / 'data/admin.json')   # override only for interface tests
COOKIE = 'agent3_admin'
TTL = 30 * 60
MIN_LEN = 8
_sessions: dict[str, float] = {}
_fails = dict(n=0, until=0.0)

# (method, path pattern) that need an administrator session
PROTECTED = [
    ('POST', r'/api/workspaces'),
    ('POST', r'/api/demo'),
    ('PUT', r'/api/workspaces/[^/]+/pack'),
    ('POST', r'/api/workspaces/[^/]+/bank/formats'),
    ('PUT', r'/api/workspaces/[^/]+/risk-list'),
    ('POST', r'/api/law/sync'),
    ('PUT', r'/api/admin/catalog/[a-z_]+'),
    ('POST', r'/api/admin/password'),
]


def _hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2 ** 14, r=8, p=1, dklen=32).hex()


def configured(store: Path | None = None) -> bool:
    return (store or STORE).exists()


def set_password(password: str, store: Path | None = None):
    store = store or STORE
    if not isinstance(password, str) or len(password) < MIN_LEN:
        raise HTTPException(422, f'mật khẩu cần ít nhất {MIN_LEN} ký tự')
    salt = secrets.token_bytes(16)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(dict(salt=salt.hex(), hash=_hash(password, salt), set_at=datetime.now().isoformat(timespec='seconds'))),
                     encoding='utf-8')
    _sessions.clear()


def check(password: str, store: Path | None = None) -> bool:
    store = store or STORE
    now = time.time()
    if now < _fails['until']:
        raise HTTPException(429, f'nhập sai nhiều lần; thử lại sau {int(_fails["until"] - now) + 1} giây')
    d = json.loads(store.read_text(encoding='utf-8'))
    ok = hmac.compare_digest(_hash(password or '', bytes.fromhex(d['salt'])), d['hash'])
    if ok:
        _fails.update(n=0, until=0.0)
    else:
        _fails['n'] += 1
        if _fails['n'] >= 5:
            _fails.update(n=0, until=now + 60)
    return ok


def new_session() -> str:
    tok = secrets.token_urlsafe(32)
    _sessions[tok] = time.time() + TTL
    return tok


def is_admin(request: Request) -> bool:
    tok = request.cookies.get(COOKIE)
    exp = _sessions.get(tok or '')
    if not exp or exp < time.time():
        _sessions.pop(tok or '', None)
        return False
    _sessions[tok] = time.time() + TTL                    # sliding expiry
    return True


def needs_admin(method: str, path: str) -> bool:
    return any(method == m and re.fullmatch(p, path) for m, p in PROTECTED)


async def middleware(request: Request, call_next):
    if needs_admin(request.method, request.url.path) and not is_admin(request):
        msg = ('chưa đặt mật khẩu quản trị; vào trang Quản trị để đặt' if not configured()
               else 'cần đăng nhập quản trị để thay đổi cấu hình')
        return JSONResponse({'detail': msg, 'admin_required': True}, status_code=401)
    return await call_next(request)


def install(app):
    from fastapi import Body
    from fastapi.responses import Response

    app.middleware('http')(middleware)

    @app.get('/api/admin/status')
    def admin_status(request: Request):
        return dict(configured=configured(), logged_in=is_admin(request), ttl_minutes=TTL // 60)

    @app.post('/api/admin/setup')
    def admin_setup(response: Response, password: str = Body(..., embed=True)):
        if configured():
            raise HTTPException(409, 'mật khẩu quản trị đã được đặt; dùng Đổi mật khẩu')
        set_password(password)
        response.set_cookie(COOKIE, new_session(), httponly=True, samesite='strict', max_age=TTL)
        return dict(ok=True)

    @app.post('/api/admin/login')
    def admin_login(response: Response, password: str = Body(..., embed=True)):
        if not configured():
            raise HTTPException(409, 'chưa đặt mật khẩu quản trị')
        if not check(password):
            raise HTTPException(401, 'sai mật khẩu')
        response.set_cookie(COOKIE, new_session(), httponly=True, samesite='strict', max_age=TTL)
        return dict(ok=True)

    @app.post('/api/admin/logout')
    def admin_logout(request: Request, response: Response):
        _sessions.pop(request.cookies.get(COOKIE) or '', None)
        response.delete_cookie(COOKIE)
        return dict(ok=True)

    @app.post('/api/admin/password')
    def admin_password(old: str = Body(...), new: str = Body(...)):
        if not check(old):
            raise HTTPException(401, 'mật khẩu hiện tại không đúng')
        set_password(new)
        return dict(ok=True, note='đã đổi mật khẩu; mọi phiên đăng nhập cũ bị hủy, hãy đăng nhập lại')

    from . import catalog

    @app.get('/api/admin/catalog')
    def catalog_list():
        return [dict(name=n, version=catalog.load(n).get('version'), note=catalog.load(n).get('note', '')) for n in catalog.NAMES]

    @app.get('/api/admin/catalog/{name}')
    def catalog_get(name: str):
        try:
            return dict(data=catalog.load(name), history=catalog.history(name)[:20])
        except catalog.CatalogError as e:
            raise HTTPException(404, str(e))

    @app.put('/api/admin/catalog/{name}')
    def catalog_put(name: str, data: dict = Body(...), by: str = ''):
        try:
            return catalog.save(name, data, by)
        except catalog.CatalogError as e:
            raise HTTPException(422, str(e))
