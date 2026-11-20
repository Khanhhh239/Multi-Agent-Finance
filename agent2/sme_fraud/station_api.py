"""Loopback API for the training station web (port 8890). Authenticated by a per-installation secret file, not a user session.

The station sees which companies contributed, label counts, encrypted-training progress and validation results.
It never receives company secret keys or plaintext transaction features.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from finance_input import AccessScope

from .import_files import ImportFailure, fail
from .validation_api import read_json, respond_failure

# Deployments where the code directory is read-only (e.g. the Azure VM image) point this at writable state.
SECRET_FILE = Path(os.environ.get('AGENT2_STATION_SECRET_FILE')
                   or Path(__file__).resolve().parents[1] / '.runtime' / 'station-secret.txt')
ROUTE = re.compile(r'/api/v1/station/(status|run|job)\Z')
PERMS = frozenset({'data.import', 'model.fit', 'evidence.verify'})


def station_secret() -> str:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SECRET_FILE.is_file():
        try:  # owner-only, and never replace a secret another process has just written
            fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w', encoding='ascii') as stream:
                stream.write(secrets.token_hex(32))
    return SECRET_FILE.read_text(encoding='ascii').strip()


def handle_station(handler, lifecycle, method: str) -> bool:
    match = ROUTE.fullmatch(urlsplit(handler.path).path)
    if match is None:
        return False
    try:
        tokens = handler.headers.get_all('X-Station-Token', [])
        if len(tokens) != 1 or not hmac.compare_digest(tokens[0], station_secret()):
            fail(401, 'STATION_AUTH', 'Trạm huấn luyện chưa được xác thực.', 'Mở trạm bằng lệnh khởi động trên cùng máy chủ.')
        fed = getattr(lifecycle, 'federated', None) if lifecycle is not None else None
        if fed is None:
            fail(503, 'FEDERATED_NOT_CONFIGURED', 'Chưa cấu hình huấn luyện chung.', 'Chạy thiết lập HE huấn luyện.')
        action = match[1]
        if method == 'GET' and action == 'status':
            value = fed.station_status()
        elif method == 'POST' and action == 'run':
            body = read_json(handler)
            body = body if isinstance(body, dict) else {}
            value = fed.start(lambda cid: AccessScope('demo', frozenset({cid}), 'station-' + cid, PERMS), body)
        elif method == 'POST' and action == 'job':
            body = read_json(handler)
            value = fed.job(str((body or {}).get('run_id') or ''))
        else:
            fail(405, 'METHOD_NOT_ALLOWED', 'Thao tác trạm không hợp lệ.', 'Dùng đúng phương thức.')
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        handler.respond(200, raw, 'application/json; charset=utf-8')
    except ImportFailure as error:
        respond_failure(handler, error)
    except Exception as exc:
        respond_failure(handler, ImportFailure(503, 'STATION_UNAVAILABLE', f'Trạm chưa xử lý được yêu cầu ({type(exc).__name__}: {exc}).', 'Thử lại.'))
    return True
