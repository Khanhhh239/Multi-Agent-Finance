"""Small static UI and existing-credential discovery; no new identity store."""
from pathlib import Path
from urllib.parse import urlsplit

from .auth import AuthError
from .validation_api import RequestFailure, respond_failure

ROOT = Path(__file__).with_name('web')
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/workspace': ('workspace.html','text/html; charset=utf-8'),
          '/status': ('status.html','text/html; charset=utf-8'),
          '/data-import': ('index.html','text/html; charset=utf-8'),
          '/assets/workspace.js': ('workspace.js','text/javascript; charset=utf-8'),
          '/assets/workspace.css': ('workspace.css','text/css; charset=utf-8'),
          '/analysis-settings': ('analysis-settings.html','text/html; charset=utf-8'),
          '/assets/analysis-settings.js': ('analysis-settings.js','text/javascript; charset=utf-8'),
          '/encrypted-analysis': ('he-analysis.html', 'text/html; charset=utf-8'),
          '/assets/he-analysis.js': ('he-analysis.js', 'text/javascript; charset=utf-8'),
          '/assets/workbench.js': ('workbench.js', 'text/javascript; charset=utf-8'),
          '/assets/workbench.css': ('workbench.css', 'text/css; charset=utf-8'),
          '/samples/import-demo.json': ('import-demo.json', 'application/json; charset=utf-8')}
SAMPLES={'/samples/import-demo.csv':('csv','text/csv; charset=utf-8'),'/samples/import-demo.xlsx':('xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}


def handle_workbench(handler, authorizer,*,analysis_mode=None):
    path = urlsplit(handler.path)
    if path.path not in ASSETS and path.path not in SAMPLES and path.path not in ('/api/v1/ui/context','/api/v1/ui/settings'):
        return False
    try:
        handler.close_connection = True
        port = handler.server.server_port
        if handler.headers.get_all('Host', []) not in ([f'127.0.0.1:{port}'], [f'localhost:{port}']):
            raise RequestFailure(403, 'HOST_DENIED', 'Địa chỉ truy cập không hợp lệ.', 'Mở qua localhost.')
        origins = handler.headers.get_all('Origin', [])
        if origins and origins not in ([f'http://127.0.0.1:{port}'], [f'http://localhost:{port}']):
            raise RequestFailure(403, 'ORIGIN_DENIED', 'Nguồn yêu cầu không được phép.', 'Mở màn hình trên cùng địa chỉ backend.')
        if path.query:
            raise RequestFailure(400, 'QUERY_NOT_SUPPORTED', 'Không nhận tham số trên URL.', 'Mở đúng đường dẫn, không đặt mã truy cập trên URL.')
        if path.path == '/api/v1/ui/settings':
            settings=dict(auth_mode=getattr(authorizer,'mode','local'),portal_url=getattr(authorizer,'portal_url',None))
            if analysis_mode:settings['analysis_mode']=analysis_mode
            handler.respond(200,settings)
        elif path.path == '/api/v1/ui/context':
            values = handler.headers.get_all('Authorization', [])
            value = values[0] if len(values) == 1 else None
            handler.respond(200, authorizer.describe(value))
        elif path.path in SAMPLES:
            import json
            from .tabular_templates import sample
            kind,mime=SAMPLES[path.path];handler.respond(200,sample(json.loads((ROOT/'import-demo.json').read_bytes()),kind),mime)
        else:
            filename, mime = ASSETS[path.path]
            if path.path=='/' and analysis_mode=='four_encrypted_branches':filename='workspace.html'
            handler.respond(200, (ROOT / filename).read_bytes(), mime)
    except AuthError as error:
        respond_failure(handler, error)
    return True
