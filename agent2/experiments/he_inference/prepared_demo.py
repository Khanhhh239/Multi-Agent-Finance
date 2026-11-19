"""Persistent synthetic C001/C002 preparation; never changes live configuration."""
import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time

import numpy as np
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sme_fraud.auth import FileAuthorizer
from sme_fraud.he_workbench import HEWorkbench
from sme_fraud.import_files import ImportFailure, digest
from sme_fraud.method_preprocess import row_values
from sme_fraud.snapshot_features import build_from_snapshot
from .demo import worker_environment
from .enterprise_server import load_node
from .key_manager import PROVIDER, WINDOWS_PROVIDER, create_key, load_key
from .protocol import ABS_TOLERANCE, REL_TOLERANCE, canonical, public_hex, read_json
from .registry_demo import setup_demo, database_dump
from .registry_export import ReadOnlySnapshots, _load_model
from .worker_bundle import build

VERSION = 'he-prepared-demo/1.1.0'
COMPANIES = ('C001', 'C002')


def private_folder(path):
    """Create a new private key directory without modifying an existing tree."""
    path = Path(path).resolve()
    if os.name == 'nt':
        path.mkdir(parents=True, exist_ok=False)
        result = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, check=True)
        # Account display names may use the console code page. Only the ASCII SID
        # is used; decoding a display name must not break key preparation.
        sid = next(csv.reader(io.StringIO(result.stdout.decode('utf-8', errors='replace'))))[1]
        if not re.fullmatch(r'S-1-[0-9-]+', sid):
            raise ValueError('Unable to resolve current Windows SID')
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                        '*'+sid+':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                       capture_output=True, check=True)
    else:
        path.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(path, 0o700)
    return path


def write(path, value):
    # Preparation only publishes into its own newly created private folder.
    with Path(path).open('xb') as stream:
        stream.write(canonical(value))


def snapshot_source(store, scope, snapshot_id):
    """Export exact uploaded bytes; regenerating a fixture can change metadata."""
    with store._transaction(scope) as conn:
        manifest, _ = store._read_snapshot(conn, scope, snapshot_id)
        row = conn.execute('SELECT content FROM source_blobs WHERE tenant_id=? AND company_id=? AND source_hash=?',
            (scope.tenant_id, next(iter(scope.company_ids)), manifest['source_hash'])).fetchone()
        if row is None or digest(row[0]) != manifest['source_hash']:
            raise ValueError('Original source integrity mismatch')
        return row[0].encode('utf-8') if isinstance(row[0], str) else row[0]


def prepare(destination):
    root = private_folder(destination)
    (root/'PREPARING').write_text('Incomplete until prepared.json is published. Do not reuse or overwrite keys.\n', encoding='utf-8')
    enterprise = root/'enterprise'; enterprise.mkdir(mode=0o700)
    worker = root/'worker'; worker.mkdir(mode=0o700)
    data = root/'data'; data.mkdir(mode=0o700)
    env = setup_demo(enterprise)  # Explicit offline fit, before any scoring.
    # Tokens were only used in RAM for this offline preparation. Do not leave a
    # one-hour demo credential that would make the persisted packet unusable.
    # The embedded web node will use the current Portal authorizer instead.
    signing = create_key(enterprise/'node-signing.dpapi.json', purpose='node-signing')
    wrapping = create_key(enterprise/'state-wrapping.dpapi.json')
    node_public = signing.public_info()['verify_key']
    worker_key = Ed25519PrivateKey.generate()
    (worker/'response-signing.hex').write_text(worker_key.private_bytes_raw().hex(), encoding='ascii')
    bundle = build(worker/'bundle')
    write(worker/'grants.json', dict(version='he-worker-grants/1.0.0', grants=[dict(
        tenant_id='demo', company_id=c, node_verify_key=node_public, active=True) for c in COMPANIES]))
    write(worker/'service.json', dict(version='he-worker-service/1.0.0', state_dir=str(worker/'state'),
        grants_file=str(worker/'grants.json'), response_signing_key_file=str(worker/'response-signing.hex')))
    write(enterprise/'node.json', dict(version='he-enterprise-service/1.2.0', key_protection=PROVIDER,
        auth_file=str(enterprise/'auth.json'), model_db=str(env['model_db']), snapshot_db=str(env['snapshot_db']),
        worker_url='http://127.0.0.1:8868', worker_verify_key=public_hex(worker_key),
        provisioning_key_file=str(enterprise/'node-signing.dpapi.json'),
        state_dir=str(enterprise/'state'), state_key_file=str(enterprise/'state-wrapping.dpapi.json')))
    write(enterprise/'he-ui-bindings.json', dict(version='he-ui-bindings/1.0.0', bindings=[dict(
        tenant_id='demo', company_id=c, artifact_id=env['artifacts'][c]) for c in COMPANIES]))
    write(enterprise/'portal-access.demo.json', dict(version='portal-agent2-access/1.0.0',
        tenant_id='demo', actor_id='he-demo-reviewer', status='active', memberships=[dict(
            company_id=c, role='accountant', status='active', permissions=['data.import']) for c in COMPANIES]))
    rows = []
    for company in COMPANIES:
        scope = env['auth'].authorize(env['header'], company)
        snapshots = ReadOnlySnapshots(env['snapshot_db'])
        with (data/(company+'_5_giao_dich.json')).open('xb') as stream:
            stream.write(snapshot_source(snapshots, scope, env['queries'][company]))
        with (data/(company+'_lich_su_fit.json')).open('xb') as stream:
            stream.write(snapshot_source(snapshots, scope, env['training'][company]))
        evaluation = snapshots.get_snapshot(scope, env['queries'][company])
        history = snapshots.get_snapshot(scope, env['training'][company])
        rows.append(dict(company_id=company, artifact_id=env['artifacts'][company],
            evaluation_snapshot_id=env['queries'][company], training_snapshot_id=env['training'][company],
            evaluation_checksum=evaluation['checksum'], history_checksum=history['checksum'],
            history_rows=32, reference_rows=8, evaluation_rows=5,
            evaluation_file='data/'+company+'_5_giao_dich.json', history_file='data/'+company+'_lich_su_fit.json'))
    (enterprise/'auth.json').write_bytes(canonical(dict(policy_version='1.0.0', principals=[])))
    # SQLite containers can change their header/WAL state on a normal open.
    # Lock immutable records inside them, rather than the whole mutable file.
    tracked = [p for folder in (data, enterprise) for p in folder.iterdir()
               if p.is_file() and p.name not in ('models.sqlite3','snapshots.sqlite3')]
    tracked += [worker/'service.json', worker/'grants.json', worker/'response-signing.hex', bundle/'worker-manifest.json']
    protection = ('Windows DPAPI current-user' if PROVIDER == WINDOWS_PROVIDER else
                  'Linux owner-only key file; not protected from host root')
    worker_protection = ('private directory current-user/SYSTEM ACL; not an HE decryption key'
                         if PROVIDER == WINDOWS_PROVIDER else
                         'private owner-only directory; not an HE decryption key')
    manifest = dict(version=VERSION, status='prepared', data='synthetic_only', tenant_id='demo',
        prepared_at=datetime.now(timezone.utc).isoformat(), companies=rows,
        model='he_mahalanobis_2d', feature_contract_columns=33, selected_columns=2,
        key_scope='enterprise node wrapping/signing; HE secret keys are generated separately for each job/company',
        enterprise_keys=[signing.public_info(), wrapping.public_info()],
        source_sha256={p.relative_to(root).as_posix():digest(p.read_bytes()) for p in tracked},
        key_protection=protection,
        worker_signing_protection=worker_protection,
        live_configuration_changed=False, live_services_restarted=False)
    (root/'README.md').write_text(
        '# Bộ thử HE C001/C002\n\n'
        'Dữ liệu mô phỏng, không dùng đánh giá độ chính xác nghiệp vụ.\n\n'
        'Mỗi doanh nghiệp có 32 dòng fit, 8 dòng tham chiếu và 5 dòng đánh giá riêng. '
        'Chọn snapshot có 5 bản ghi khi chạy giao diện. Không dùng lịch sử fit làm tập đánh giá.\n\n'
        'Tệp để nhập thử: data/C001_5_giao_dich.json và data/C002_5_giao_dich.json. '
        'Các tệp này đã được lưu thành snapshot trong enterprise/snapshots.sqlite3.\n\n'
        f'Khóa node dùng {protection}; toàn bộ thư mục khóa bị giới hạn quyền truy cập tương ứng với hệ điều hành. '
        'Không đổi tên/xóa khóa hoặc chạy prepare đè lên thư mục này. Không đẩy thư mục lên Git/cloud.\n\n'
        'Hướng dẫn đầy đủ: agent2/docs/HE_COMPANY_DEMO.md trong repo. '
        'Chưa bật HE trên Portal live; auth.json không cấp credential standalone.\n', encoding='utf-8')
    write(root/'prepared.json', manifest)
    (root/'PREPARING').unlink()
    return manifest


@contextmanager
def worker_service(root, state_dir=None):
    worker = root/'worker'; bundle = worker/'bundle'
    manifest = read_json(bundle/'worker-manifest.json')
    for name, expected in manifest['sha256'].items():
        path = (bundle/name).resolve()
        if not path.is_relative_to(bundle.resolve()) or digest(path.read_bytes()) != expected:
            raise ValueError('Prepared worker bundle mismatch')
    with tempfile.TemporaryDirectory(prefix='he-prepared-worker-') as temp:
        ready = Path(temp)/'ready.json'
        service_config = worker/'service.json'
        if state_dir is not None:
            service = read_json(service_config)
            service['state_dir'] = str(state_dir)
            service_config = Path(temp)/'service.json'
            write(service_config, service)
        env = worker_environment(); env['PYTHONPATH'] = str(bundle)
        command = [sys.executable,'-X','utf8','-B','-m','experiments.he_inference.worker_server',
                   '--config',str(service_config),'--port','0','--ready-file',str(ready)]
        with (Path(temp)/'worker.log').open('wb') as log:
            process = subprocess.Popen(command, cwd=bundle, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline=time.monotonic()+25
                while not ready.exists():
                    if process.poll() is not None or time.monotonic()>deadline:
                        raise RuntimeError('Prepared ciphertext worker could not start')
                    time.sleep(.05)
                yield 'http://127.0.0.1:'+str(read_json(ready)['port'])
            finally:
                if os.name == 'nt' and process.poll() is None:
                    # A Windows venv launcher can keep a child interpreter.
                    # Stop only this Popen's tree, never the Portal's worker.
                    stopped = subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW)
                    if stopped.returncode and process.poll() is None:process.terminate()
                elif process.poll() is None:process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


def check(destination):
    root=Path(destination).resolve(); manifest=read_json(root/'prepared.json')
    if manifest['version']!=VERSION or manifest['status']!='prepared' or (root/'PREPARING').exists():
        raise ValueError('Prepared packet incomplete or incompatible')
    checks=[]
    def verify(name, condition):
        if not condition: raise AssertionError(name)
        checks.append(dict(check=name, passed=True))
    for name, expected in manifest['source_sha256'].items():
        path=(root/name).resolve()
        verify('Integrity: '+name, path.is_relative_to(root) and digest(path.read_bytes())==expected)
    for purpose, name in [('node-signing','node-signing.dpapi.json'),('state-wrapping','state-wrapping.dpapi.json')]:
        key=load_key(root/'enterprise'/name, purpose=purpose, required_provider=PROVIDER)
        verify('Protected key usable: '+purpose, key.provider==PROVIDER and key.material.hex().encode() not in (root/'enterprise'/name).read_bytes())
    paths={name:root/'enterprise'/name for name in ('models.sqlite3','snapshots.sqlite3')}
    before={name:database_dump(path) for name,path in paths.items()}
    token=secrets.token_urlsafe(32); header='Bearer '+token
    with tempfile.TemporaryDirectory(prefix='he-prepared-auth-') as temp, worker_service(root, root/'worker/check-state') as url:
        policy=Path(temp)/'auth.json'
        write(policy,dict(policy_version='1.0.0',principals=[dict(actor_id='prepared-demo-checker',tenant_id='demo',
            token_sha256=digest(token.encode()),status='active',expires_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat(),
            memberships=[dict(company_id=c,role='accountant',status='active',permissions=['data.import']) for c in COMPANIES])]))
        auth=FileAuthorizer(policy); config=read_json(root/'enterprise/node.json'); config['worker_url']=url
        config['state_dir']=str(root/'enterprise/check-state')
        node=load_node(config,auth); web=HEWorkbench(node,root/'enterprise/he-ui-bindings.json')
        output=[]
        try:
            for info in manifest['companies']:
                company=info['company_id']; scope=auth.authorize(header,company); again=lambda:auth.authorize(header,company)
                snapshots=ReadOnlySnapshots(paths['snapshots.sqlite3'])
                for identity, checksum in [('evaluation_snapshot_id','evaluation_checksum'),('training_snapshot_id','history_checksum')]:
                    locked=snapshots.get_snapshot(scope,info[identity],again)
                    verify(company+': immutable checksum '+identity,locked['checksum']==info[checksum])
                _,model_manifest,model=_load_model(paths['models.sqlite3'],scope,info['artifact_id'],again)
                verify(company+': independent 32 fit / 8 reference rows',model_manifest['history_rows']==32 and model_manifest['reference_rows']==8 and model_manifest['company_id']==company)
                source=read_json(root/info['evaluation_file'])
                verify(company+': five synthetic evaluation rows',len(source['transactions'])==5 and all(r['company_id']==company and r['source']['is_simulated'] for r in source['transactions']))
                catalog=web.datasets(scope,again); snapshot=next(d for d in catalog['datasets'] if d['snapshot_id']==info['evaluation_snapshot_id'])
                verify(company+': pinned model available and evaluation snapshot has 5 rows',catalog['available'] and snapshot['record_count']==5)
                store=ReadOnlySnapshots(paths['snapshots.sqlite3'])
                metadata=store.get_snapshot(scope,info['evaluation_snapshot_id'],again)
                verify(company+': evaluation file exactly matches original upload',metadata['source_hash']==digest((root/info['evaluation_file']).read_bytes()))
                frame=build_from_snapshot(store,scope,info['evaluation_snapshot_id'],snapshot['as_of'],again)
                values=[row_values(frame,row,model_manifest['preprocess'])[0] for row in frame['features']]
                expected=model.score(np.asarray(values,dtype=float))
                state=web.submit(scope,again,company,header,'prepared-five-'+company,dict(snapshot_id=info['evaluation_snapshot_id']))
                result=node.jobs.wait(company,header,state['job_id'],seconds=45)
                verify(company+': HE returns all five decrypted scores',result['row_count']==5 and all(r['available'] for r in result['rows']))
                actual=np.asarray([r['score'] for r in result['rows']])
                verify(company+': encrypted/plaintext parity',np.allclose(actual,expected,atol=ABS_TOLERANCE,rtol=REL_TOLERANCE))
                repeated=web.submit(scope,again,company,header,'prepared-five-'+company,dict(snapshot_id=info['evaluation_snapshot_id']))
                verify(company+': repeated check preserves job ID',repeated['job_id']==state['job_id'])
                other=next(i for i in manifest['companies'] if i['company_id']!=company)
                try: store.get_snapshot(scope,other['evaluation_snapshot_id'],again)
                except ImportFailure as error: verify(company+': foreign snapshot denied',error.status==404)
                else: raise AssertionError('Foreign snapshot accepted')
                try: _load_model(paths['models.sqlite3'],scope,other['artifact_id'],again)
                except Exception as error:
                    from .protocol import HEUnavailable
                    verify(company+': foreign model denied',isinstance(error,HEUnavailable) and error.code=='artifact_missing')
                else: raise AssertionError('Foreign model accepted')
                output.append(dict(company_id=company,artifact_id=info['artifact_id'],snapshot_id=info['evaluation_snapshot_id'],
                    row_count=5,run_id=result['run_id'],maximum_absolute_error=float(np.max(np.abs(actual-expected)))))
        finally: node.jobs.close()
    verify('Models and snapshots unchanged during inference',before=={name:database_dump(path) for name,path in paths.items()})
    verify('Different companies have different model artifacts',len({r['artifact_id'] for r in output})==2)
    return dict(status='passed',data='synthetic_only',checks=checks,count=len(checks),companies=output,
        secret_keys_or_credentials_in_report=False,live_configuration_changed=False,live_services_restarted=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check'));parser.add_argument('--output-dir',required=True);parser.add_argument('--report')
    args=parser.parse_args()
    try:
        result=prepare(args.output_dir) if args.mode=='prepare' else check(args.output_dir)
        if args.report:
            write(args.report,result)
        print(json.dumps(dict(status=result['status'],companies=COMPANIES,output=str(Path(args.output_dir).resolve())),ensure_ascii=False))
        return 0
    except (OSError,ValueError,AssertionError,RuntimeError,subprocess.SubprocessError) as error:
        # No private key/credential or exception payload in the command output.
        print('HE_DEMO_PREPARATION_OR_CHECK_FAILED: '+type(error).__name__)
        return 2


if __name__=='__main__':raise SystemExit(main())
