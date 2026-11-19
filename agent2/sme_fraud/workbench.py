"""Small static UI and existing-credential discovery; no new identity store."""
from pathlib import Path
from urllib.parse import urlsplit

from .auth import AuthError
from .validation_api import RequestFailure, respond_failure

ROOT = Path(__file__).with_name('web')
ASSETS = {'/': ('investigation.html', 'text/html; charset=utf-8'),
          '/workspace': ('investigation.html','text/html; charset=utf-8'),
          '/status': ('status.html','text/html; charset=utf-8'),
          '/data-import': ('investigation.html','text/html; charset=utf-8'),
          '/assets/workspace.css': ('workspace.css','text/css; charset=utf-8'),
          '/analysis-settings': ('analysis-settings.html','text/html; charset=utf-8'),
          '/pipeline-releases': ('pipeline-releases.html','text/html; charset=utf-8'),
          '/pipeline-workspace': ('investigation.html','text/html; charset=utf-8'),
          '/pipeline-operations': ('bundle-workspace.html','text/html; charset=utf-8'),
          '/model-management': ('model-management.html','text/html; charset=utf-8'),
          '/assets/agent2-shell.js': ('agent2-shell.js','text/javascript; charset=utf-8'),
          '/assets/agent2-shell.css': ('agent2-shell.css','text/css; charset=utf-8'),
          '/federated-training': ('federated-training.html','text/html; charset=utf-8'),
          '/assets/federated-training.js': ('federated-training.js','text/javascript; charset=utf-8'),
          '/assets/federated-training.css': ('federated-training.css','text/css; charset=utf-8'),
          '/assets/investigation.js': ('investigation.js','text/javascript; charset=utf-8'),
          '/assets/investigation.css': ('investigation.css','text/css; charset=utf-8'),
          '/assets/model-management.js': ('model-management.js','text/javascript; charset=utf-8'),
          '/assets/model-management.css': ('model-management.css','text/css; charset=utf-8'),
          '/assets/bundle-workspace.js': ('bundle-workspace.js','text/javascript; charset=utf-8'),
          '/assets/bundle-remediation.js': ('bundle-remediation.js','text/javascript; charset=utf-8'),
          '/assets/bundle-remediation.css': ('bundle-remediation.css','text/css; charset=utf-8'),
          '/assets/pipeline-releases.js': ('pipeline-releases.js','text/javascript; charset=utf-8'),
          '/assets/pipeline-releases.css': ('pipeline-releases.css','text/css; charset=utf-8'),
          '/label-verification': ('label-verification.html','text/html; charset=utf-8'),
          '/assets/label-verification.js': ('label-verification.js','text/javascript; charset=utf-8'),
          '/batch-training': ('batch-training.html','text/html; charset=utf-8'),
          '/assets/batch-training.js': ('batch-training.js','text/javascript; charset=utf-8'),
          '/assets/analysis-settings.js': ('analysis-settings.js','text/javascript; charset=utf-8'),
          '/encrypted-analysis': ('he-analysis.html', 'text/html; charset=utf-8'),
          '/assets/he-analysis.js': ('he-analysis.js', 'text/javascript; charset=utf-8'),
          '/assets/workbench.js': ('workbench.js', 'text/javascript; charset=utf-8'),
          '/assets/rule-source-intake.js': ('rule-source-intake.js','text/javascript; charset=utf-8'),
          '/samples/rule-sources.xlsx': ('rule-sources.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
          '/assets/workbench.css': ('workbench.css', 'text/css; charset=utf-8'),
          '/assets/platform-theme.css': ('platform-theme.css', 'text/css; charset=utf-8'),
          '/assets/platform-theme.js': ('platform-theme.js', 'text/javascript; charset=utf-8'),
          '/samples/import-demo.json': ('import-demo.json', 'application/json; charset=utf-8')}
for _font in sorted((ROOT / 'platform-fonts').glob('*.woff2')) if (ROOT / 'platform-fonts').is_dir() else ():
    ASSETS['/assets/platform-fonts/' + _font.name] = ('platform-fonts/' + _font.name, 'font/woff2')
SAMPLES={'/samples/import-demo.csv':('csv','text/csv; charset=utf-8'),'/samples/import-demo.xlsx':('xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}


def handle_workbench(handler, authorizer,*,analysis_mode=None,bundle_mode=False):
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
            if bundle_mode:settings['workspace_mode']='bundle_shadow';settings['workspace_path']='pipeline-workspace'
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
            handler.respond(200, (ROOT / filename).read_bytes(), mime)
    except AuthError as error:
        respond_failure(handler, error)
    return True
