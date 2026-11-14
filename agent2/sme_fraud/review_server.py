"""Loopback validation backend and status page; old workflow APIs are retired."""
import argparse
import json
import os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from .auth import FileAuthorizer
from .validation_api import handle_validation
from .snapshot_api import handle_snapshots
from .analysis_api import handle_analysis
from .snapshots import SnapshotStore
from .workbench import handle_workbench
from .portal_auth import PortalAuthorizer
from .analysis_resources import AnalysisResources
from .he_workbench import handle_he_workbench
from .review_api import handle_reviews
from .config_api import handle_config
from .workspace_api import handle_workspace
from .comparison_api import handle_comparison

from pathlib import Path

PAGE=(Path(__file__).with_name('web')/'status.html').read_text('utf-8')


def make_server(port=8766,authorizer=None,snapshot_store=None,analysis_resources=None,he_backend=None):
    authorizer=authorizer or FileAuthorizer(None)
    if he_backend and he_backend.node.auth is not authorizer:
        raise ValueError('HE must use the same current authorizer as the web server')
    reviews=None
    comparisons=None
    manager=None
    if he_backend and hasattr(he_backend,'settings'):
        from experiments.he4.config_manager import Manager
        manager=Manager(he_backend,snapshot_store)
    if he_backend and he_backend.node.jobs:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from .review_store import ReviewStore
        jobs=he_backend.node.jobs.store
        key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-review-v1',info=b'enterprise-review-storage').derive(jobs.mac_key)
        reviews=ReviewStore(jobs.path.with_name('reviews.sqlite3'),key)
        from .comparison_store import ComparisonStore
        comparison_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-comparison-v1',info=b'enterprise-selection-plans').derive(jobs.mac_key)
        comparisons=ComparisonStore(jobs.path.with_name('comparisons.sqlite3'),comparison_key)
        if hasattr(he_backend.node.jobs,'legacy'):
            legacy=he_backend.node.jobs.legacy.store
            legacy_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-review-v1',info=b'enterprise-review-storage').derive(legacy.mac_key)
            reviews=dict(current=reviews,legacy=ReviewStore(legacy.path.with_name('reviews.sqlite3'),legacy_key))
            legacy_comparison_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-comparison-v1',info=b'enterprise-selection-plans').derive(legacy.mac_key)
            comparisons=dict(current=comparisons,legacy=ComparisonStore(legacy.path.with_name('comparisons.sqlite3'),legacy_comparison_key))
    class Handler(BaseHTTPRequestHandler):
        def respond(self,code,value,mime='application/json; charset=utf-8'):
            body=value if isinstance(value,bytes) else (json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
            if self.close_connection:self.send_header('Connection','close')
            if code==401:self.send_header('WWW-Authenticate','Bearer realm="agent2"')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors "+os.environ.get('SOSOAT_FRAME_ANCESTORS',"'none'"))
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if handle_workbench(self,authorizer,analysis_mode='four_encrypted_branches' if he_backend and hasattr(he_backend,'settings') else None):return
            if handle_workspace(self,authorizer,snapshot_store,he_backend,reviews):return
            if handle_comparison(self,authorizer,snapshot_store,he_backend,reviews,comparisons,'GET'):return
            if handle_reviews(self,authorizer,snapshot_store,he_backend,reviews,'GET'):return
            if handle_config(self,authorizer,manager,'GET'):return
            if handle_he_workbench(self,authorizer,he_backend,'GET'):return
            if handle_analysis(self,authorizer,snapshot_store,'GET',analysis_resources):return
            if handle_snapshots(self,authorizer,snapshot_store,'GET'):return
            if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
                return self.respond(403,dict(error='Chỉ truy cập qua localhost.'))
            path=urlsplit(self.path).path
            if path=='/api/health':return self.respond(200,dict(status='ok',mode='import_snapshots' if snapshot_store else 'validation_only',milestone='R1',pipeline_ready=False,work_area_ready=snapshot_store is not None and authorizer.configured,analysis_configured=he_backend is not None,release_gate='full_spec_not_approved',active_delivery=False,validation_auth_configured=authorizer.configured,snapshot_storage_configured=snapshot_store is not None))
            if path=='/status':return self.respond(200,PAGE,'text/html; charset=utf-8')
            self.respond(410,dict(error='Luồng Agent2 cũ đã được lưu trữ. API pipeline v2.1 chưa được triển khai.',mode='core_only'))
        def do_POST(self):
            if handle_config(self,authorizer,manager,'POST'):return
            if handle_reviews(self,authorizer,snapshot_store,he_backend,reviews,'POST'):return
            if handle_comparison(self,authorizer,snapshot_store,he_backend,reviews,comparisons,'POST'):return
            if handle_he_workbench(self,authorizer,he_backend,'POST'):return
            if not handle_analysis(self,authorizer,snapshot_store,'POST',analysis_resources) and not handle_validation(self,authorizer) and not handle_snapshots(self,authorizer,snapshot_store,'POST'):
                self.respond(410,dict(error='Chưa mở ghi dữ liệu hoặc chạy job; API cũ đã được lưu trữ.',mode='validation_only'))
        def do_PUT(self):
            if not handle_analysis(self,authorizer,snapshot_store,'PUT',analysis_resources) and not handle_snapshots(self,authorizer,snapshot_store,'PUT'):
                self.respond(410,dict(error='API cũ đã được lưu trữ.'))
        def log_message(self,*args):pass
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--auth-file',default=os.environ.get('AGENT2_AUTH_FILE'),help='Backend-only credential hashes and company memberships; no credentials configured by default')
    parser.add_argument('--portal-url',default=os.environ.get('AGENT2_PORTAL_URL'),help='Trusted loopback Portal origin; uses its session and permissions, with no local credential fallback')
    parser.add_argument('--snapshot-db',default=os.environ.get('AGENT2_SNAPSHOT_DB'),help='New dedicated snapshot SQLite database; never the legacy --database path')
    parser.add_argument('--model-db',default=os.environ.get('AGENT2_MODEL_DB'),help='Existing immutable MethodStore opened read-only for inference')
    parser.add_argument('--analysis-bindings',default=os.environ.get('AGENT2_ANALYSIS_BINDINGS'),help='Backend-only tenant/company artifact pins; no automatic fit or latest selection')
    parser.add_argument('--he-node-config',default=os.environ.get('AGENT2_HE_NODE_CONFIG'),help='Opt-in protected enterprise HE node config; embeds node locally using this server authorizer')
    parser.add_argument('--he-bindings',default=os.environ.get('AGENT2_HE_BINDINGS'),help='Backend-only HE artifact pins per tenant/company')
    parser.add_argument('--he4-config',default=os.environ.get('AGENT2_HE4_CONFIG'),help='Opt-in four-branch enterprise config, with independent Concrete worker and protected contexts')
    # Known old launcher options are accepted only for compatibility; their paths are never opened.
    for name in ('data-root','reports-root','database','ml-review-root'):parser.add_argument('--'+name,action='append')
    for name in ('qa','demo-ml-manager'):parser.add_argument('--'+name,action='store_true')
    args=parser.parse_args();store=SnapshotStore(args.snapshot_db) if args.snapshot_db else None
    authorizer=PortalAuthorizer(args.portal_url,os.environ.get('AGENT2_PORTAL_BRIDGE_SECRET')) if args.portal_url else FileAuthorizer(args.auth_file)
    if args.portal_url and args.snapshot_db:
        from pathlib import Path
        # Compatibility with an already-running Portal launcher: these are only
        # explicit, scoped filenames beside its snapshot DB, never a model scan.
        args.model_db=args.model_db or str(Path(args.snapshot_db).parent/'models-v2.sqlite3')
        args.analysis_bindings=args.analysis_bindings or str(Path(args.snapshot_db).parent/'analysis-bindings.json')
    he_backend=None
    if args.he_node_config or args.he_bindings:
        if not args.he_node_config or not args.he_bindings or not args.snapshot_db:
            parser.error('HE requires --he-node-config, --he-bindings and --snapshot-db')
        from pathlib import Path
        from experiments.he_inference.protocol import read_json
        from experiments.he_inference.enterprise_server import load_node
        from .he_workbench import HEWorkbench
        config=read_json(args.he_node_config)
        if config.get('version')!='he-enterprise-service/1.2.0' or Path(config['snapshot_db']).resolve()!=Path(args.snapshot_db).resolve():
            parser.error('HE web requires strict config 1.2.0 and the same snapshot DB as the import screen')
        he_backend=HEWorkbench(load_node(config,authorizer),args.he_bindings)
        if args.he4_config:
            from experiments.he4.web import FourWorkbench
            he4=read_json(args.he4_config)
            if Path(he4['state_key_file']).resolve()!=Path(config['state_key_file']).resolve():
                parser.error('HE4 must use this enterprise node protected wrapping key')
            he_backend=FourWorkbench(he_backend.node,args.he_bindings,he4)
    elif args.he4_config:parser.error('HE4 requires the existing protected HE node and company bindings')
    server=make_server(args.port,authorizer,store,AnalysisResources(args.model_db,args.analysis_bindings),he_backend)
    print(f'Agent2 validation backend: http://127.0.0.1:{server.server_port}; pipeline_ready=false',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
        if he_backend:he_backend.node.jobs.close()


if __name__=='__main__':main()
