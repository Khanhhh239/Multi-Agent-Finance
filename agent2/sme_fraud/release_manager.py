"""Offline releases, isolated installs and side-by-side local upgrades."""
from contextlib import contextmanager
from datetime import datetime, timezone
from email.parser import BytesParser
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from urllib.request import Request,urlopen

FORMAT='sme-release-v1'
RECEIPT='installation.json'
ROOT=Path(__file__).resolve().parents[1]
SEMVER=re.compile(r'\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): value.update(block)
    return value.hexdigest()


def path_guard(path):
    path=Path(path).absolute()
    for parent in (path,*path.parents):
        if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():
            raise ValueError('Release paths cannot contain symlinks/junctions')
        if parent.name.casefold() in {'005','sme_fraud_005'}:
            raise ValueError('Holdout 005 is excluded from release operations')
    return path.resolve()


def fresh(path):
    path=path_guard(path)
    if path.exists(): raise FileExistsError('Destination must not exist')
    for parent in path.parents:
        if any((parent/name).is_file() for name in ('manifest.json','case_queue.csv','predictions_frozen.json','backup_manifest.json','suite_manifest.json')):
            raise ValueError('Destination is inside a protected snapshot')
    if path.is_relative_to(ROOT/'data'): raise ValueError('Cannot install into source data')
    return path


def inventory(root):
    root=path_guard(root)
    result={}
    for path in sorted(root.rglob('*')):
        path_guard(path)
        if path.is_file(): result[path.relative_to(root).as_posix()]=dict(sha256=sha(path),bytes=path.stat().st_size)
    return result


def write_record(path,value):
    value=dict(value); value['checksum']=digest(value)
    temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists(): temporary.unlink()


def read_record(path):
    value=json.loads(path_guard(path).read_text(encoding='utf-8'))
    checksum=value.pop('checksum',None)
    if digest(value)!=checksum: raise ValueError('Release/deployment record checksum mismatch')
    return value


def literal(path,name):
    for item in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(item,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in item.targets):
            return ast.literal_eval(item.value)
    raise ValueError('Missing version declaration: '+name)


def contracts(app):
    package=app/'sme_fraud'
    review={name:sha(package/name) for name in literal(package/'review_backup.py','RUNTIME_FILES')}
    return dict(review=review,suite=dict(review=review,suite={name:sha(package/name) for name in ('backup_suite.py','p2_controls_web.py')}))


def canonical(name): return re.sub(r'[-_.]+','-',name).lower()


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        entries=[name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
        if len(entries)!=1: raise ValueError('Invalid wheel metadata')
        metadata=BytesParser().parsebytes(archive.read(entries[0]))
    return canonical(metadata['Name']),metadata['Version']


def build_release(source,wheels,output,version):
    source,wheels=path_guard(source),path_guard(wheels); output=fresh(output)
    if not SEMVER.fullmatch(version): raise ValueError('Use a semantic application version')
    if output.is_relative_to(wheels): raise ValueError('Release output overlaps its wheelhouse')
    if any(output.is_relative_to(source/name) for name in ('sme_fraud','review_ui','data','reports')):
        raise ValueError('Release output overlaps source content')
    selected={}
    for path in (source/'sme_fraud').iterdir():
        if path.is_file() and path.suffix in {'.py','.json'}: selected[path.relative_to(source)]=path
    for path in (source/'review_ui').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts: selected[path.relative_to(source)]=path
    for name in ('README.md','RELEASES.md','requirements.txt','requirements-lock.txt','requirements-review-lock.txt','start_review.py','manage_release.py'):
        path=source/name
        if path.is_file(): selected[Path(name)]=path
    requirements={}
    for line in (source/'requirements-review-lock.txt').read_text(encoding='utf-8').splitlines():
        line=line.split('#',1)[0].strip()
        if line:
            match=re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s]+)',line)
            if not match: raise ValueError('Release dependency pins must be exact')
            requirements[canonical(match[1])]=match[2]
    wheel_map={}
    for path in wheels.glob('*.whl'):
        name,package_version=wheel_metadata(path)
        if name in wheel_map: raise ValueError('Duplicate wheel for '+name)
        wheel_map[name]=(package_version,path)
    if set(wheel_map)!=set(requirements) or any(wheel_map[name][0]!=version for name,version in requirements.items()):
        raise ValueError('Wheelhouse does not exactly match release dependency lock')
    output.parent.mkdir(parents=True,exist_ok=True); output.mkdir()
    try:
        before={str(name):sha(path) for name,path in selected.items()}
        for name,path in selected.items():
            path_guard(path); target=output/'app'/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
        version_file=output/'app/sme_fraud/version.py'
        text=version_file.read_text(encoding='utf-8')
        text,count=re.subn(r"(?m)^APP_VERSION = .*?$",'APP_VERSION = '+repr(version),text)
        if count!=1: raise ValueError('Cannot bind packaged code version')
        version_file.write_text(text,encoding='utf-8')
        (output/'wheels').mkdir()
        lock=[]
        for name,(package_version,path) in sorted(wheel_map.items()):
            shutil.copyfile(path,output/'wheels'/path.name)
            lock.append(f'{name}=={package_version} --hash=sha256:{sha(path)}')
        (output/'requirements.lock').write_text('\n'.join(lock)+'\n',encoding='utf-8')
        app=output/'app'; package=app/'sme_fraud'
        schema=literal(package/'review_store.py','SCHEMA_VERSION')
        if literal(package/'version.py','REVIEW_SCHEMA_VERSION')!=schema: raise ValueError('Declared review schema differs from code')
        if before!={str(name):sha(path) for name,path in selected.items()}: raise ValueError('Source changed during release build')
        payload=inventory(output)
        metadata=dict(format=FORMAT,app_version=version,profile='review-local-win64-py312',
            schemas=dict(review=schema,p2=literal(package/'version.py','P2_JOURNAL_SCHEMA_VERSION')),
            protocols=dict(review=literal(package/'review_backup.py','VERSION'),suite=literal(package/'backup_suite.py','VERSION')),
            runtime_contracts=contracts(app),dependencies=requirements,
            python=dict(major=3,minor=12,platform='win32',machine='AMD64'),files=payload,
            source_files=before,build_transform='Only APP_VERSION in the packaged version.py is set to the requested release version.',
            created_at=datetime.now(timezone.utc).isoformat())
        metadata['release_id']=version+'-'+digest(dict(files=payload,schemas=metadata['schemas']))[:12]
        write_record(output/'release.json',metadata)
        verify_release(output)
        return metadata
    except BaseException:
        # Keep an incomplete artifact for diagnosis; it cannot pass verify/install.
        raise


def verify_release(root):
    root=path_guard(root); manifest=read_record(root/'release.json')
    actual=inventory(root); actual.pop('release.json',None)
    if manifest.get('format')!=FORMAT or actual!=manifest['files']: raise ValueError('Release content checksum mismatch')
    if contracts(root/'app')!=manifest['runtime_contracts']: raise ValueError('Release runtime declaration mismatch')
    if literal(root/'app/sme_fraud/version.py','APP_VERSION')!=manifest['app_version']: raise ValueError('Packaged app version mismatch')
    return manifest


def export_archive(release,output):
    release=path_guard(release); verify_release(release); output=fresh(output)
    if output.is_relative_to(release): raise ValueError('Archive cannot be inside its own release')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_STORED) as archive:
        for name in inventory(release): archive.write(release/name,name)
    return dict(archive=str(output),sha256=sha(output))


def unpack_archive(archive,output):
    archive=path_guard(archive); output=fresh(output)
    with zipfile.ZipFile(archive) as package:
        entries=package.infolist(); names=[entry.filename for entry in entries]
        if len(names)!=len(set(names)) or len(names)>10000 or sum(e.file_size for e in entries)>2_000_000_000:
            raise ValueError('Invalid release archive size or duplicate entries')
        for entry in entries:
            name=entry.filename
            if not name or name.startswith('/') or '\\' in name or ':' in name or '..' in Path(name).parts or ((entry.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Unsafe release archive entry')
        output.parent.mkdir(parents=True,exist_ok=True); output.mkdir()
        for entry in entries:
            target=output/entry.filename
            if entry.is_dir(): target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with package.open(entry) as incoming,target.open('xb') as outgoing: shutil.copyfileobj(incoming,outgoing)
    return verify_release(output)


def clean_environment():
    environment=dict(os.environ)
    for name in list(environment):
        if name.upper().startswith(('PYTHON','PIP_')): environment.pop(name)
    environment.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PIP_CONFIG_FILE=os.devnull)
    return environment


def execute(command,*,cwd,timeout=600):
    result=subprocess.run([str(value) for value in command],cwd=cwd,env=clean_environment(),
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if result.returncode: raise RuntimeError(result.stdout[-5000:])
    return result.stdout


def environment_report(python,cwd):
    code="import json,sys,site,importlib.metadata as m; print(json.dumps(dict(prefix=sys.prefix,base_prefix=sys.base_prefix,user_site=site.ENABLE_USER_SITE,packages={x.metadata['Name'].lower().replace('_','-'):x.version for x in m.distributions()})))"
    return json.loads(execute([python,'-I','-B','-c',code],cwd=cwd))


def install_release(release,output,python=None):
    release=path_guard(release); manifest=verify_release(release); output=fresh(output)
    if output.is_relative_to(release): raise ValueError('Installation must be separate from its release artifact')
    python=path_guard(python or sys.executable)
    probe=json.loads(execute([python,'-I','-c','import json,sys,platform;print(json.dumps([*sys.version_info[:2],sys.platform,platform.machine()]))'],cwd=release))
    expected=manifest['python']
    if probe!=[expected['major'],expected['minor'],expected['platform'],expected['machine']]:
        raise ValueError('Release requires its recorded Python/platform; no cross-platform wheel substitution')
    output.parent.mkdir(parents=True,exist_ok=True); output.mkdir()
    (output/'app').mkdir()
    for name in manifest['files']:
        if name.startswith('app/'):
            target=output/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(release/name,target)
    # venv scripts contain absolute paths; create at the final location, never rename.
    execute([python,'-I','-m','venv',output/'env'],cwd=output)
    installed_python=output/'env/Scripts/python.exe'
    log=execute([installed_python,'-I','-m','pip','--isolated','--disable-pip-version-check','install',
        '--no-index','--only-binary=:all:','--require-hashes','--find-links',release/'wheels','-r',release/'requirements.lock'],cwd=output)
    (output/'install.log').write_text(log,encoding='utf-8')
    check=execute([installed_python,'-I','-m','pip','check'],cwd=output)
    environment=environment_report(installed_python,output)
    if environment['prefix']==environment['base_prefix'] or environment['user_site'] is not False:
        raise RuntimeError('Installation is not isolated')
    if any(environment['packages'].get(name)!=value for name,value in manifest['dependencies'].items()):
        raise RuntimeError('Installed dependency versions differ from release')
    receipt=dict(format=FORMAT,release_id=manifest['release_id'],app_version=manifest['app_version'],
        installed_at=datetime.now(timezone.utc).isoformat(),root=str(output),manifest=manifest,
        python=str(installed_python),environment=environment,pip_check=check.strip())
    write_record(output/RECEIPT,receipt)
    verify_install(output)
    return receipt


def verify_install(root):
    root=path_guard(root); receipt=read_record(root/RECEIPT)
    if receipt.get('format')!=FORMAT or receipt['root']!=str(root): raise ValueError('Installation moved or is invalid; recreate its venv')
    expected={name[4:]:value for name,value in receipt['manifest']['files'].items() if name.startswith('app/')}
    if inventory(root/'app')!=expected: raise ValueError('Installed code/assets changed')
    python=path_guard(receipt['python'])
    if not python.is_relative_to(root/'env') or not python.is_file(): raise ValueError('Invalid installed interpreter')
    return receipt


def runtime_call(installation,command,root,output=None):
    installation=path_guard(installation); receipt=verify_install(installation)
    result=environment_report(receipt['python'],installation)
    if any(result['packages'].get(name)!=version for name,version in receipt['manifest']['dependencies'].items()):
        raise ValueError('Installed environment drifted from its release')
    arguments=[receipt['python'],'-B','-m','sme_fraud.release_runtime',command,'--root',path_guard(root)]
    if output is not None: arguments+=['--output',path_guard(output)]
    return json.loads(execute(arguments,cwd=installation/'app'))


def backup_requirement(backup):
    backup=path_guard(backup)
    kind='suite' if (backup/'suite_manifest.json').is_file() else 'review'
    name='suite_manifest.json' if kind=='suite' else 'backup_manifest.json'
    value=json.loads((backup/name).read_text(encoding='utf-8')); checksum=value.pop('manifest_sha256',None)
    if digest(value)!=checksum: raise ValueError('Backup manifest checksum mismatch')
    expected='review-p2-backup-suite-v1' if kind=='suite' else 'case-management-backup-v1'
    if value.get('version')!=expected: raise ValueError('Unsupported backup format; no implicit migration')
    return kind,value['runtime_contract']


def matching_install(installations,backup):
    kind,required=backup_requirement(backup)
    matches=[]
    for candidate in path_guard(installations).iterdir():
        if not (candidate/RECEIPT).is_file(): continue
        receipt=verify_install(candidate)
        if receipt['manifest']['runtime_contracts'][kind]==required:
            matches.append((receipt['installed_at'],candidate))
    if not matches: raise ValueError('No archived matching runtime is installed; restore its release first. Backup metadata is not rewritten.')
    return max(matches,key=lambda item:item[0])[1]


def restore_with(installation,backup,output):
    receipt=verify_install(installation); kind,required=backup_requirement(backup)
    if receipt['manifest']['runtime_contracts'][kind]!=required:
        raise ValueError('Target runtime is incompatible; use an archived matching release or an approved explicit migration adapter')
    output=fresh(output)
    if output.is_relative_to(path_guard(installation)):
        raise ValueError('Mutable restored data must be separate from installed code')
    return runtime_call(installation,'restore',backup,output)


@contextmanager
def deployment_lock(root):
    root=path_guard(root)
    with (root/'.deployment.lock').open('a+b') as stream:
        if stream.tell()==0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt; msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl; fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error: raise RuntimeError('Deployment is busy or its managed web service is running; stop it before upgrade/rollback') from error
        try: yield
        finally:
            stream.seek(0)
            if os.name=='nt': msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(stream,fcntl.LOCK_UN)


def deployment_state(root):
    state=read_record(path_guard(root)/'deployment.json')
    if state.get('format')!='sme-deployment-v1': raise ValueError('Unsupported deployment version')
    previous=''
    for index,event in enumerate(state['history']):
        value=dict(event); checksum=value.pop('event_hash')
        if value['previous_hash']!=previous or digest(value)!=checksum or value['generation']!=index+1:
            raise ValueError('Deployment history chain is invalid')
        previous=checksum
    if state['generation']!=len(state['history']): raise ValueError('Deployment generation mismatch')
    return state


def commit_state(root,state,event):
    state=dict(state); state['history']=list(state['history']); state['generation']+=1
    event=dict(event,at=datetime.now(timezone.utc).isoformat(),generation=state['generation'],
               previous_hash=state['history'][-1]['event_hash'] if state['history'] else '')
    event['event_hash']=digest(event); state['history'].append(event)
    write_record(root/'deployment.json',state)
    return state


def revision(root,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier): raise ValueError('Invalid revision ID')
    value=read_record(root/'revisions'/identifier/'revision.json')
    if value['id']!=identifier or path_guard(value['data'])!=root/'revisions'/identifier/'data':
        raise ValueError('Revision binding mismatch')
    return value


def make_revision(root,installation,backup):
    identifier=uuid.uuid4().hex; folder=root/'revisions'/identifier; folder.mkdir(parents=True)
    info=restore_with(installation,backup,folder/'data')
    probe=runtime_call(installation,'probe',folder/'data')
    if info['logical_sha256']!=probe['logical_sha256']: raise RuntimeError('Health probe changed migrated data')
    value=dict(id=identifier,installation=str(path_guard(installation)),data=str(folder/'data'),
               app_version=verify_install(installation)['app_version'],initial_sha256=info['logical_sha256'],kind=info['kind'])
    write_record(folder/'revision.json',value)
    return value


def init_deployment(installation,backup,output):
    output=fresh(output); output.parent.mkdir(parents=True,exist_ok=True); output.mkdir()
    with deployment_lock(output):
        item=make_revision(output,installation,backup)
        return commit_state(output,dict(format='sme-deployment-v1',generation=0,history=[],active=item['id'],
            active_sha256=item['initial_sha256'],previous=None,previous_sha256=None),dict(action='initialize',release=item['app_version']))


def upgrade(root,installation):
    root=path_guard(root)
    with deployment_lock(root):
        state=deployment_state(root); active=revision(root,state['active'])
        try:
            before=runtime_call(active['installation'],'inspect',active['data'])
            checkpoint=root/'checkpoints'/uuid.uuid4().hex; checkpoint.parent.mkdir(exist_ok=True)
            runtime_call(active['installation'],'snapshot',active['data'],checkpoint)
            item=make_revision(root,installation,checkpoint)
            after=runtime_call(active['installation'],'inspect',active['data'])
            if before['logical_sha256']!=after['logical_sha256'] or item['initial_sha256']!=before['logical_sha256']:
                raise RuntimeError('Source changed or upgrade did not preserve operational data')
            updated=dict(state,previous=state['active'],previous_sha256=before['logical_sha256'],
                         active=item['id'],active_sha256=item['initial_sha256'])
            return commit_state(root,updated,dict(action='upgrade',release=item['app_version'],checkpoint=str(checkpoint)))
        except Exception as error:
            commit_state(root,state,dict(action='upgrade_failed_active_unchanged',error=type(error).__name__,message=str(error)))
            raise


def rollback(root):
    root=path_guard(root)
    with deployment_lock(root):
        state=deployment_state(root)
        if not state['previous']: raise ValueError('No previous revision')
        active=revision(root,state['active']); previous=revision(root,state['previous'])
        current=runtime_call(active['installation'],'inspect',active['data'])
        old=runtime_call(previous['installation'],'probe',previous['data'])
        if current['logical_sha256']!=state['active_sha256']:
            raise RuntimeError('Post-upgrade writes exist. Rollback is blocked to preserve them; checkpoint and an explicit reverse migration are required.')
        if old['logical_sha256']!=state['previous_sha256']: raise RuntimeError('Previous revision data changed; refusing rollback')
        return commit_state(root,dict(state,active=state['previous'],active_sha256=old['logical_sha256'],
            previous=state['active'],previous_sha256=current['logical_sha256']),dict(action='rollback',release=previous['app_version']))


def run_managed(root,port):
    root=path_guard(root)
    if not 1<=port<=65535: raise ValueError('Invalid loopback port')
    with deployment_lock(root):
        state=deployment_state(root); active=revision(root,state['active'])
        installation=verify_install(active['installation']); runtime_call(active['installation'],'inspect',active['data'])
        instance='managed-'+uuid.uuid4().hex
        with (root/'service.log').open('ab') as log:
            child=subprocess.Popen([installation['python'],'-B','-m','sme_fraud.release_runtime','serve',
                '--root',active['data'],'--port',str(port),'--instance-id',instance],cwd=Path(active['installation'])/'app',
                env=clean_environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            write_record(root/'service.json',dict(instance_id=instance,port=port,pid=child.pid))
            try:
                code=child.wait()
                if code: raise RuntimeError('Managed web failed; see service.log')
            finally:
                if child.poll() is None: child.terminate(); child.wait(timeout=20)
                if (root/'service.json').exists() and read_record(root/'service.json')['instance_id']==instance:
                    (root/'service.json').unlink()


def stop_managed(root):
    root=path_guard(root); service=read_record(root/'service.json'); port=service['port']
    if type(port) is not int or not 1<=port<=65535: raise ValueError('Invalid service record')
    base=f'http://127.0.0.1:{port}'
    with urlopen(base+'/api/health',timeout=5) as response: health=json.load(response)
    if health.get('instance_id')!=service['instance_id']: raise ValueError('Service identity changed; refusing shutdown')
    with urlopen(base+'/api/meta',timeout=5) as response: meta=json.load(response)
    request=Request(base+'/api/shutdown',data=b'{}',headers={'Content-Type':'application/json','X-CSRF-Token':meta['csrf_token']})
    with urlopen(request,timeout=5) as response: return json.load(response)


def main():
    parser=argparse.ArgumentParser(description=__doc__); commands=parser.add_subparsers(dest='command',required=True)
    build=commands.add_parser('build'); build.add_argument('--source',type=Path,default=ROOT)
    build.add_argument('--wheels',type=Path,required=True); build.add_argument('--output',type=Path,required=True); build.add_argument('--version',required=True)
    verify=commands.add_parser('verify'); verify.add_argument('--release',type=Path,required=True)
    archive=commands.add_parser('archive'); archive.add_argument('--release',type=Path,required=True); archive.add_argument('--output',type=Path,required=True)
    unpack=commands.add_parser('unpack'); unpack.add_argument('--archive',type=Path,required=True); unpack.add_argument('--output',type=Path,required=True)
    install=commands.add_parser('install'); install.add_argument('--release',type=Path,required=True); install.add_argument('--output',type=Path,required=True)
    resolve=commands.add_parser('resolve'); resolve.add_argument('--installations',type=Path,required=True); resolve.add_argument('--backup',type=Path,required=True)
    for name in ('restore','initialize'):
        command=commands.add_parser(name); command.add_argument('--installation',type=Path,required=True)
        command.add_argument('--backup',type=Path,required=True); command.add_argument('--output',type=Path,required=True)
    for name in ('upgrade','rollback','status','run','stop'):
        command=commands.add_parser(name); command.add_argument('--deployment',type=Path,required=True)
        if name=='upgrade': command.add_argument('--installation',type=Path,required=True)
        if name=='run': command.add_argument('--port',type=int,default=8773)
    args=parser.parse_args()
    try:
        if args.command=='build': value=build_release(args.source,args.wheels,args.output,args.version); result=dict(status='built',release_id=value['release_id'])
        elif args.command=='verify': result=dict(status='verified',release_id=verify_release(args.release)['release_id'])
        elif args.command=='archive': result=export_archive(args.release,args.output)
        elif args.command=='unpack': result=dict(status='unpacked',release_id=unpack_archive(args.archive,args.output)['release_id'])
        elif args.command=='install': result=dict(status='installed',release_id=install_release(args.release,args.output)['release_id'])
        elif args.command=='resolve': result=dict(installation=str(matching_install(args.installations,args.backup)))
        elif args.command=='restore': result=restore_with(args.installation,args.backup,args.output)
        elif args.command=='initialize': result=init_deployment(args.installation,args.backup,args.output)
        elif args.command=='upgrade': result=upgrade(args.deployment,args.installation)
        elif args.command=='rollback': result=rollback(args.deployment)
        elif args.command=='run': run_managed(args.deployment,args.port); result=dict(status='stopped')
        elif args.command=='stop': result=stop_managed(args.deployment)
        else: result=deployment_state(args.deployment)
        print(json.dumps(result,ensure_ascii=True),flush=True); return 0
    except Exception as error:
        print(json.dumps(dict(status='failed',error=type(error).__name__,message=str(error)),ensure_ascii=True),flush=True); return 1


if __name__=='__main__': sys.exit(main())
