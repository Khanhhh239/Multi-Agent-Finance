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
from .label_api import handle_labels
from .batch_training_api import BatchTrainingManager,handle_batch_training
from .case_queue_api import handle_case_queue
from .case_queue_store import CaseQueueStore
from .pipeline_benchmark_api import handle_pipeline_benchmark
from .remediation_api import handle_remediation
from .remediation_store import RemediationStore
from .pipeline_release_api import handle_releases
from .bundle_workspace_api import handle_bundle_workspace
from .model_lifecycle import ModelLifecycle
from .model_lifecycle_api import handle_model_lifecycle
from .lr_fhe_training import LRFHETrainingService
from .lr_registry import LRModelRegistry

from pathlib import Path

PAGE=(Path(__file__).with_name('web')/'status.html').read_text('utf-8')


def default_workspace_dir():
    configured = os.environ.get('AGENT2_WORKSPACE_DIR')
    base = Path(configured) if configured else (Path(__file__).resolve().parents[1] / '.runtime' / 'default-workspace')
    base.mkdir(parents=True, exist_ok=True)
    return base


def make_server(port=8766,authorizer=None,snapshot_store=None,analysis_resources=None,he_backend=None,review_store=None,comparison_store=None,label_store=None,batch_training=None,case_queue_store=None,remediation_store=None,release_service=None):
    authorizer=authorizer or FileAuthorizer(None)
    if snapshot_store is None:
        ws_dir = default_workspace_dir()
        snapshot_store = SnapshotStore(ws_dir / 'snapshots-v2.sqlite3')
    if he_backend and he_backend.node.auth is not authorizer:
        raise ValueError('HE must use the same current authorizer as the web server')
    reviews=review_store
    comparisons=comparison_store
    manager=None
    if he_backend and hasattr(he_backend,'settings'):
        from experiments.he4.config_manager import Manager
        manager=Manager(he_backend,snapshot_store)
    if he_backend and he_backend.node.jobs:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from .review_store import ReviewStore
        jobs=he_backend.node.jobs.store
        if release_service is None:
            from .pipeline_release import ReleaseService
            from .pipeline_release_store import ReleaseStore
            release_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-pipeline-release-v1',info=b'enterprise-release-storage').derive(jobs.mac_key)
            release_service=ReleaseService(ReleaseStore(jobs.path.with_name('pipeline-releases.sqlite3'),release_key),snapshot_store,analysis_resources)
        if label_store is None:
            from .label_packets import LabelStore
            label_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-labels-v1',info=b'enterprise-verified-labels').derive(jobs.mac_key)
            label_store=LabelStore(jobs.path.with_name('verified-labels.sqlite3'),label_key)
        if batch_training is None:
            batch_key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-batch-training-v1',info=b'enterprise-batch-training').derive(jobs.mac_key)
            runtime_cfg=os.environ.get('AGENT2_BATCH_TRAINING_CONFIG') or jobs.path.with_name('batch-training-runtime.json')
            batch_training=BatchTrainingManager(jobs.path.with_name('batch-training.sqlite3'),batch_key,snapshot_store=snapshot_store,label_store=label_store,runtime_config_path=runtime_cfg)
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
    if case_queue_store is None:
        cq_db=os.environ.get('AGENT2_CASE_QUEUE_DB')
        if cq_db:case_queue_store=CaseQueueStore(cq_db)
        elif he_backend and he_backend.node.jobs:case_queue_store=CaseQueueStore(he_backend.node.jobs.store.path.with_name('case-queue.sqlite3'))
        elif snapshot_store and hasattr(snapshot_store,'path'):case_queue_store=CaseQueueStore(snapshot_store.path.with_name('case-queue.sqlite3'))
    if remediation_store is None:
        rem_db=os.environ.get('AGENT2_REMEDIATION_DB')
        if rem_db:remediation_store=RemediationStore(rem_db)
        elif he_backend and he_backend.node.jobs:remediation_store=RemediationStore(he_backend.node.jobs.store.path.with_name('remediation.sqlite3'))
        elif snapshot_store and hasattr(snapshot_store,'path'):remediation_store=RemediationStore(snapshot_store.path.with_name('remediation.sqlite3'))
        elif case_queue_store and hasattr(case_queue_store,'path'):remediation_store=RemediationStore(case_queue_store.path.with_name('remediation.sqlite3'))
    if release_service is not None and release_service.case_queue is None:
        release_service.case_queue=case_queue_store
    if release_service is not None:
        release_service.workspace.remediation=remediation_store
        if he_backend is not None and hasattr(he_backend.node.jobs,'submit_bound'):
            from .bundle_he import BundleHE
            release_service.he_executor=BundleHE(he_backend)
    model_lifecycle=None
    if snapshot_store is not None and analysis_resources is not None:
        if release_service is not None:
            lc_db=release_service.store.path.with_name('model-lifecycle.sqlite3')
        elif analysis_resources.model_db is not None:
            lc_db=Path(analysis_resources.model_db).with_name('model-lifecycle.sqlite3')
        elif hasattr(snapshot_store,'path'):
            lc_db=Path(snapshot_store.path).with_name('model-lifecycle.sqlite3')
        else:
            lc_db=default_workspace_dir()/'model-lifecycle.sqlite3'
        model_lifecycle=ModelLifecycle(
            lc_db,
            snapshot_store=snapshot_store,
            analysis_resources=analysis_resources,
            authorizer=authorizer,
            label_store=label_store,
            case_queue_store=case_queue_store,
            release_service=release_service,
        )
        lr_rt_cfg=getattr(batch_training,'runtime_config_path',None) or os.environ.get('AGENT2_BATCH_TRAINING_CONFIG')
        model_lifecycle.lr_fhe=LRFHETrainingService(
            lc_db.with_name('lr-fhe-jobs.sqlite3'),
            snapshot_store=snapshot_store,
            label_store=label_store,
            model_lifecycle=model_lifecycle,
            runtime_config_path=lr_rt_cfg,
            portal_url=getattr(authorizer,'portal_url',None),
            portal_bridge_secret=os.environ.get('AGENT2_PORTAL_BRIDGE_SECRET'),
        )
        model_lifecycle.lr_registry=LRModelRegistry(
            lc_db.with_name('lr-model-registry.sqlite3'),
            lr_fhe_service=model_lifecycle.lr_fhe,
            model_lifecycle=model_lifecycle,
            snapshot_store=snapshot_store,
        )
        model_lifecycle.lr_fhe.lr_registry=model_lifecycle.lr_registry
        from .federated_lr import FederatedLRService
        model_lifecycle.federated=FederatedLRService(lc_db.with_name('federated-lr.sqlite3'),model_lifecycle.lr_fhe,authorizer)
    class Handler(BaseHTTPRequestHandler):
        def respond(self,code,value,mime='application/json; charset=utf-8'):
            body=value if isinstance(value,bytes) else (json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
            if self.close_connection:self.send_header('Connection','close')
            if code==401:self.send_header('WWW-Authenticate','Bearer realm="agent2"')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors "+os.environ.get('SOSOAT_FRAME_ANCESTORS',"'none'"))
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if handle_workbench(self,authorizer,analysis_mode='four_encrypted_branches' if he_backend and hasattr(he_backend,'settings') else None,bundle_mode=release_service is not None):return
            if handle_model_lifecycle(self,authorizer,model_lifecycle,'GET'):return
            if handle_releases(self,authorizer,release_service,'GET'):return
            if handle_bundle_workspace(self,authorizer,release_service,'GET'):return
            if handle_remediation(self,authorizer,remediation_store,'GET',case_queue_store=case_queue_store,snapshot_store=snapshot_store):return
            if handle_case_queue(self,authorizer,case_queue_store,'GET',snapshot_store,analysis_resources,release_service):return
            if handle_batch_training(self,authorizer,batch_training,'GET'):return
            if handle_labels(self,authorizer,snapshot_store,label_store,'GET'):return
            if handle_workspace(self,authorizer,snapshot_store,he_backend,reviews):return
            if handle_comparison(self,authorizer,snapshot_store,he_backend,reviews,comparisons,'GET',analysis_resources):return
            if handle_reviews(self,authorizer,snapshot_store,he_backend,reviews,'GET'):return
            if handle_config(self,authorizer,manager,'GET'):return
            if handle_he_workbench(self,authorizer,he_backend,'GET'):return
            if handle_analysis(self,authorizer,snapshot_store,'GET',analysis_resources):return
            if handle_snapshots(self,authorizer,snapshot_store,'GET'):return
            if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
                return self.respond(403,dict(error='Chỉ truy cập qua localhost.'))
            path=urlsplit(self.path).path
            if path in ('/api/health','/health'):return self.respond(200,dict(status='ok',mode='import_snapshots' if snapshot_store else 'validation_only',milestone='R1',pipeline_ready=False,work_area_ready=snapshot_store is not None and authorizer.configured,analysis_configured=he_backend is not None,release_gate='full_spec_not_approved',active_delivery=False,validation_auth_configured=authorizer.configured,snapshot_storage_configured=snapshot_store is not None))
            if path=='/status':return self.respond(200,PAGE,'text/html; charset=utf-8')
            self.respond(410,dict(error='Luồng Agent2 cũ đã được lưu trữ. API pipeline v2.1 chưa được triển khai.',mode='core_only'))
        def _drain_small_body(self):
            try:
                length=int(self.headers.get('Content-Length') or 0)
                if 0<length<=65536:self.rfile.read(length)
            except (ValueError,OSError):pass
        def do_POST(self):
            if handle_model_lifecycle(self,authorizer,model_lifecycle,'POST'):return
            if handle_releases(self,authorizer,release_service,'POST'):return
            if handle_bundle_workspace(self,authorizer,release_service,'POST'):return
            if handle_pipeline_benchmark(self,authorizer,snapshot_store,batch_training,'POST',analysis_resources):return
            if handle_remediation(self,authorizer,remediation_store,'POST',case_queue_store=case_queue_store,snapshot_store=snapshot_store):return
            if handle_case_queue(self,authorizer,case_queue_store,'POST',snapshot_store,analysis_resources,release_service):return
            if handle_batch_training(self,authorizer,batch_training,'POST'):return
            if handle_labels(self,authorizer,snapshot_store,label_store,'POST'):return
            if handle_config(self,authorizer,manager,'POST'):return
            if handle_reviews(self,authorizer,snapshot_store,he_backend,reviews,'POST'):return
            if handle_comparison(self,authorizer,snapshot_store,he_backend,reviews,comparisons,'POST',analysis_resources):return
            if handle_he_workbench(self,authorizer,he_backend,'POST'):return
            if not handle_analysis(self,authorizer,snapshot_store,'POST',analysis_resources) and not handle_validation(self,authorizer) and not handle_snapshots(self,authorizer,snapshot_store,'POST'):
                self._drain_small_body()
                self.respond(410,dict(error='Chưa mở ghi dữ liệu hoặc chạy job; API cũ đã được lưu trữ.',mode='validation_only'))
        def do_PUT(self):
            if handle_labels(self,authorizer,snapshot_store,label_store,'PUT'):return
            if not handle_analysis(self,authorizer,snapshot_store,'PUT',analysis_resources) and not handle_snapshots(self,authorizer,snapshot_store,'PUT'):
                self._drain_small_body()
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
    parser.add_argument('--batch-training-config',default=os.environ.get('AGENT2_BATCH_TRAINING_CONFIG'),help='Opt-in multi-batch encrypted training config')
    parser.add_argument('--release-config',default=os.environ.get('AGENT2_RELEASE_CONFIG'),help='Protected release metadata DB/key config; otherwise derived from configured enterprise HE job key')
    # Known old launcher options are accepted only for compatibility; their paths are never opened.
    for name in ('data-root','reports-root','database','ml-review-root'):parser.add_argument('--'+name,action='append')
    for name in ('qa','demo-ml-manager'):parser.add_argument('--'+name,action='store_true')
    args=parser.parse_args()
    if not args.snapshot_db:
        ws_dir=default_workspace_dir()
        args.snapshot_db=str(ws_dir/'snapshots-v2.sqlite3')
        args.model_db=args.model_db or str(ws_dir/'models-v2.sqlite3')
        args.analysis_bindings=args.analysis_bindings or str(ws_dir/'analysis-bindings.json')
    store=SnapshotStore(args.snapshot_db)
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
    batch_mgr=BatchTrainingManager.from_config(args.batch_training_config,snapshot_store=store) if args.batch_training_config else None
    resources=AnalysisResources(args.model_db,args.analysis_bindings)
    release_service=None
    if args.release_config:
        from .pipeline_release import ReleaseService
        release_service=ReleaseService.from_config(args.release_config,store,resources)
    server=make_server(args.port,authorizer,store,resources,he_backend,batch_training=batch_mgr,release_service=release_service)
    print(f'Agent2 validation backend: http://127.0.0.1:{server.server_port}; pipeline_ready=false',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
        if he_backend:he_backend.node.jobs.close()


if __name__=='__main__':main()
