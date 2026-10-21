"""Consistent Case Management backup, verification and restore into a new directory."""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import time
import uuid

from .case_identity import digest, load_lineage, scope_hash
from .feedback import feedback_lock, read_audit
from .information_requests import InformationRequests
from .review_capacity import ReviewCalendar
from .review_store import SCHEMA_VERSION, source_fingerprint, source_paths
from .review_decision_gate import BINDING_FILE,assert_binding,read_binding,write_binding

ROOT=Path(__file__).resolve().parents[1]
VERSION='case-management-backup-v1'
RUNTIME_FILES=('review_backup.py','review_store.py','review_support.py','case_identity.py','information_requests.py',
               'feedback.py','review_capacity.py','entity_graph.py','review_decision_gate.py')
SIDE_FILES=('case_identity.json','feedback_audit.jsonl','case_review_states.csv',BINDING_FILE)
MANIFEST='backup_manifest.json'


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def guarded(path):
    path=Path(path).resolve()
    if any(p.casefold() in {'005','sme_fraud_005'} for p in path.parts):
        raise ValueError('Holdout 005 is excluded from Case Management backup/restore')
    return path


def runtime_contract():
    return {name:sha(Path(__file__).parent/name) for name in RUNTIME_FILES}


def new_destination(target,protected=()):
    target=guarded(target)
    if target.exists():raise FileExistsError('Destination must be a new directory')
    if target.is_relative_to(ROOT/'data'):
        raise ValueError('Destination cannot be inside workspace source data')
    for root in protected:
        if target.is_relative_to(root):raise ValueError('Destination overlaps an input directory')
    for parent in target.parents:
        if any((parent/n).is_file() for n in ('manifest.json','case_queue.csv','predictions_frozen.json',MANIFEST)):
            raise ValueError('Destination cannot be nested in a snapshot or backup')
    return target


@contextmanager
def stage_directory(target):
    target.parent.mkdir(parents=True,exist_ok=True)
    # Normal mkdir inherits the destination ACL on Windows; tempfile's private
    # directory ACL would survive publication and block workspace readers.
    staged=target.parent/('.review-backup-'+uuid.uuid4().hex)
    staged.mkdir()
    try:
        yield staged
        if target.exists():raise FileExistsError('Destination appeared during the operation')
        staged.rename(target)
    finally:
        if staged.exists():
            checked=staged.resolve()
            if checked.parent!=target.parent or not checked.name.startswith('.review-backup-'):
                raise ValueError('Unexpected staging cleanup path')
            shutil.rmtree(checked)


@contextmanager
def read_database(path):
    path=guarded(path)
    if not path.is_file():raise FileNotFoundError(path)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=15)) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('BEGIN')
        yield db


def identifier(name):return '"'+name.replace('"','""')+'"'


def database_state(db):
    if [r[0] for r in db.execute('PRAGMA integrity_check')]!=['ok']:
        raise ValueError('SQLite integrity_check failed')
    if list(db.execute('PRAGMA foreign_key_check')):
        raise ValueError('SQLite foreign_key_check failed')
    schemas=list(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"))
    required={'metadata','cases','settings','information_request_events','admissions'}
    if not required<={r['name'] for r in schemas}:raise ValueError('Not a prepared current ReviewStore database')
    tables={}
    for schema in schemas:
        name=schema['name']
        columns=[r[1] for r in db.execute('PRAGMA table_info('+identifier(name)+')')]
        # Relocation changes only the path-bound cache fingerprint, never data.
        selected=[c for c in columns if not (name=='metadata' and c=='fingerprint')]
        query='SELECT '+','.join(map(identifier,selected))+' FROM '+identifier(name)+' ORDER BY '+','.join(map(identifier,selected))
        value=hashlib.sha256();count=0
        for row in db.execute(query):
            encoded=[{'blob_hex':v.hex()} if isinstance(v,bytes) else v for v in row]
            value.update((json.dumps(encoded,ensure_ascii=False,separators=(',',':'))+'\n').encode())
            count+=1
        tables[name]=dict(rows=count,sha256=value.hexdigest(),schema_sha256=digest(schema['sql']))
    return tables


def metadata_rows(db):
    rows={r['scenario']:dict(r) for r in db.execute('SELECT * FROM metadata ORDER BY scenario')}
    if not rows or set(rows)-{'001','003'}:
        raise ValueError('Backup requires all prepared 001/003 scenarios; 005 is not supported')
    for table in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        name=table[0]
        if 'scenario' in {r[1] for r in db.execute('PRAGMA table_info('+identifier(name)+')')}:
            scopes={r[0] for r in db.execute('SELECT DISTINCT scenario FROM '+identifier(name))}
            if scopes-set(rows):raise ValueError('Database contains a scenario without a backed-up snapshot')
    return rows


def snapshot_state(db,reports,scenarios):
    events=InformationRequests.history(db)
    bindings=set();snapshots={}
    for tag in scenarios:
        report=guarded(reports/('sme_fraud_'+tag))
        if not (report/'case_identity.json').is_file():raise ValueError('Missing case identity mapping')
        lineage=load_lineage(report)
        binding=read_binding(report)
        proof=db.execute('SELECT value FROM settings WHERE key=?',('review_binding:'+tag,)).fetchone()
        if binding['scenario']!=tag or not proof or proof[0]!=binding['binding_id']:
            raise ValueError('Review-store binding differs from SQLite proof')
        cases={r['case_id']:json.loads(r['data']) for r in db.execute('SELECT case_id,data FROM cases WHERE scenario=?',(tag,))}
        if set(cases)!=set(lineage['current']):raise ValueError('Cached case IDs differ from snapshot identity')
        for key,case in cases.items():
            if scope_hash(case)!=scope_hash(lineage['current'][key]):
                raise ValueError('Cached case scope differs from snapshot identity')
        for case in [*lineage['current'].values(),*lineage['archives'].values()]:
            bindings.add((tag,case['company_id'],scope_hash(case)))
        audit=read_audit(report/'feedback_audit.jsonl')
        snapshots[tag]=dict(cases=len(cases),queue_sha256=lineage['queue_sha256'],
            case_scopes_sha256=digest({k:scope_hash(c) for k,c in cases.items()}),
            feedback_events=len(audit),feedback_head=audit[-1]['event_hash'] if audit else '',
            identity_sha256=sha(report/'case_identity.json'),binding_id=binding['binding_id'])
    if any((e['scenario'],e['company_id'],e['case_scope_hash']) not in bindings for e in events):
        raise ValueError('Document request history is not bound to a backed-up snapshot scope')
    return dict(snapshots=snapshots,request_events=len(events),request_head=events[-1]['event_hash'] if events else '')


def copy_checked(source,target):
    if source.is_symlink():raise ValueError('Snapshot symlinks are not supported')
    source=guarded(source)
    target.parent.mkdir(parents=True,exist_ok=True)
    before=sha(source)
    # Do not copy file ACLs/mode from private temporary source files.
    with source.open('rb') as incoming,target.open('xb') as outgoing:
        shutil.copyfileobj(incoming,outgoing)
    if sha(target)!=before or sha(source)!=before:raise ValueError('Snapshot file changed while copying')
    return before


def file_inventory(root):
    result={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Symlinks are not supported in backup bundles')
        if path.is_file():
            name=path.relative_to(root).as_posix()
            if name!=MANIFEST:result[name]=dict(sha256=sha(path),bytes=path.stat().st_size)
    return result


def create_backup(database,data_root,reports_root,output,*,calendar=None,timeout=120):
    database,data_root,reports_root=(guarded(p) for p in (database,data_root,reports_root))
    output=new_destination(output,(data_root,reports_root))
    calendar=calendar or ReviewCalendar()
    if not isinstance(calendar,ReviewCalendar):raise ValueError('Calendar must be a ReviewCalendar')
    with read_database(database) as initial:
        tags=sorted(metadata_rows(initial))
    with ExitStack() as stack:
        for tag in tags:
            guarded(data_root/('sme_fraud_'+tag))
            stack.enter_context(feedback_lock(guarded(reports_root/('sme_fraud_'+tag))))
        source=stack.enter_context(read_database(database))
        metadata=metadata_rows(source)
        if sorted(metadata)!=tags:raise ValueError('Prepared scenario set changed; retry backup')
        state=database_state(source)
        review=snapshot_state(source,reports_root,tags)
        selected={}
        for tag in tags:
            data,report=data_root/('sme_fraud_'+tag),reports_root/('sme_fraud_'+tag)
            assert_binding(source,report,database,tag)
            if source_fingerprint(data,report)!=metadata[tag]['fingerprint']:
                raise ValueError('Prepared cache is stale; verify/prepare the source snapshot before backup')
            selected[tag]=source_paths(data,report)+[report/n for n in SIDE_FILES if (report/n).is_file()]
        with stage_directory(output) as staged:
            copied={}
            for tag,paths in selected.items():
                for path in dict.fromkeys(paths):
                    if path.parent==data_root/('sme_fraud_'+tag):
                        relative=Path('data')/('sme_fraud_'+tag)/path.name
                    else:relative=Path('reports')/('sme_fraud_'+tag)/path.name
                    copied[path]=copy_checked(path,staged/relative)
            deadline=time.monotonic()+timeout
            def progress(status,remaining,total):
                if time.monotonic()>deadline:raise TimeoutError('SQLite backup timeout')
            with closing(sqlite3.connect(staged/'review.sqlite3')) as target:
                source.backup(target,pages=256,progress=progress,sleep=.05)
                target.execute('PRAGMA journal_mode=DELETE')
            if any(sha(path)!=checksum for path,checksum in copied.items()):
                raise ValueError('Snapshot files changed while creating backup')
            for tag in tags:
                if source_fingerprint(data_root/('sme_fraud_'+tag),reports_root/('sme_fraud_'+tag))!=metadata[tag]['fingerprint']:
                    raise ValueError('Snapshot source changed during backup')
            with read_database(staged/'review.sqlite3') as target:
                if database_state(target)!=state or snapshot_state(target,staged/'reports',tags)!=review:
                    raise ValueError('Backup state does not match the source snapshot')
            manifest=dict(version=VERSION,schema_version=SCHEMA_VERSION,created_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                runtime_contract=runtime_contract(),scenarios=tags,original_metadata=metadata,
                calendar=calendar.as_dict(),calendar_provenance='caller_supplied_runtime_configuration',
                source_locations=dict(database=str(database),data_root=str(data_root),reports_root=str(reports_root)),
                files=file_inventory(staged),database_state=state,review_state=review,
                notifications_on_restore='dry_run_no_dispatch',external_secret_configuration_exported=False,
                scope='main_review_store_and_required_sources_reports_only')
            manifest['manifest_sha256']=digest(manifest)
            (staged/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def verify_backup(bundle):
    bundle=guarded(bundle)
    manifest_path=bundle/MANIFEST
    if manifest_path.is_symlink():raise ValueError('Backup manifest cannot be a symlink')
    manifest=json.loads(guarded(manifest_path).read_text(encoding='utf-8'))
    checksum=manifest.pop('manifest_sha256',None)
    if digest(manifest)!=checksum:raise ValueError('Backup manifest checksum mismatch')
    manifest['manifest_sha256']=checksum
    if manifest.get('version')!=VERSION or manifest.get('schema_version')!=SCHEMA_VERSION:
        raise ValueError('Unsupported backup/schema version')
    if manifest['runtime_contract']!=runtime_contract():
        raise ValueError('Use the matching Case Management runtime before restore')
    for name in manifest['files']:
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid backup file path')
        guarded(bundle/name)
    if file_inventory(bundle)!=manifest['files']:raise ValueError('Backup file checksum/inventory mismatch')
    with read_database(bundle/'review.sqlite3') as db:
        metadata=metadata_rows(db)
        if metadata!=manifest['original_metadata'] or sorted(metadata)!=manifest['scenarios']:
            raise ValueError('Backup metadata differs from manifest')
        if database_state(db)!=manifest['database_state'] or snapshot_state(db,bundle/'reports',sorted(metadata))!=manifest['review_state']:
            raise ValueError('Backup semantic state differs from manifest')
    return manifest


def restore_backup(bundle,output):
    bundle=guarded(bundle)
    output=new_destination(output,(bundle,))
    manifest=verify_backup(bundle)
    with stage_directory(output) as staged:
        for name in manifest['files']:copy_checked(bundle/name,staged/name)
        # The staged directory will be renamed. Fingerprints must bind the final
        # absolute paths, while file bytes and every operational table stay intact.
        relocation={}
        with closing(sqlite3.connect(staged/'review.sqlite3')) as db:
            db.row_factory=sqlite3.Row
            for tag in manifest['scenarios']:
                # Calculate using the final path names and verified staged bytes.
                value=hashlib.sha256(SCHEMA_VERSION.encode())
                for path in source_paths(staged/'data'/('sme_fraud_'+tag),staged/'reports'/('sme_fraud_'+tag)):
                    final_path=output/path.relative_to(staged)
                    value.update(str(final_path.resolve()).encode())
                    with path.open('rb') as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
                fingerprint=value.hexdigest()
                db.execute('UPDATE metadata SET fingerprint=? WHERE scenario=?',(fingerprint,tag))
                report=staged/'reports'/('sme_fraud_'+tag)
                binding=read_binding(report)
                binding.update(database=str(output/'review.sqlite3'),report_path=str(output/'reports'/('sme_fraud_'+tag)))
                write_binding(report,binding)
                relocation[tag]=dict(original=manifest['original_metadata'][tag]['fingerprint'],restored=fingerprint)
            db.commit()
            if database_state(db)!=manifest['database_state'] or snapshot_state(db,staged/'reports',manifest['scenarios'])!=manifest['review_state']:
                raise ValueError('Restored operational state differs from backup')
        if file_inventory(bundle)!=manifest['files']:raise ValueError('Backup changed during restore')
        receipt=dict(version=VERSION,backup_manifest_sha256=manifest['manifest_sha256'],
            restored_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),scenarios=manifest['scenarios'],
            calendar=manifest['calendar'],runtime_contract=manifest['runtime_contract'],relocation=relocation,database_state=manifest['database_state'],
            review_state=manifest['review_state'],notifications_mode='dry_run',dispatch_performed=False,
            fingerprint_rebase_only=True,binding_paths_relocated=True,detector_rescored=False)
        (staged/'restore_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt


def restored_store(root):
    from .review_store import ReviewStore
    root=guarded(root)
    receipt=json.loads((root/'restore_receipt.json').read_text(encoding='utf-8'))
    if receipt.get('version')!=VERSION or receipt.get('runtime_contract')!=runtime_contract():
        raise ValueError('Restored copy needs its matching runtime')
    if not receipt['scenarios'] or set(receipt['scenarios'])-{'001','003'}:
        raise ValueError('Restored scenarios must be 001/003')
    with read_database(root/'review.sqlite3') as db:
        metadata=metadata_rows(db)
        if sorted(metadata)!=receipt['scenarios']:raise ValueError('Restored scenario set changed')
        for tag in receipt['scenarios']:
            data,report=guarded(root/'data'/('sme_fraud_'+tag)),guarded(root/'reports'/('sme_fraud_'+tag))
            assert_binding(db,report,root/'review.sqlite3',tag)
            if source_fingerprint(data,report)!=metadata[tag]['fingerprint']:
                raise ValueError('Restored source changed; refusing an automatic cache rebuild')
        snapshot_state(db,root/'reports',receipt['scenarios'])
    calendar=ReviewCalendar(tuple(receipt['calendar']['working_weekdays']),tuple(receipt['calendar']['non_working_dates']))
    store=ReviewStore(root/'data',root/'reports',root/'review.sqlite3',scenarios=receipt['scenarios'],calendar=calendar)
    store.prepare()
    return store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    backup=commands.add_parser('backup')
    for flag in ('database','data-root','reports-root','output'):backup.add_argument('--'+flag,type=Path,required=True)
    backup.add_argument('--working-weekdays',default='0,1,2,3,4,5,6')
    backup.add_argument('--non-working-date',action='append',default=[])
    verify=commands.add_parser('verify');verify.add_argument('--backup',type=Path,required=True)
    restore=commands.add_parser('restore')
    restore.add_argument('--backup',type=Path,required=True);restore.add_argument('--output',type=Path,required=True)
    serve=commands.add_parser('serve');serve.add_argument('--restored',type=Path,required=True);serve.add_argument('--port',type=int,default=8770)
    args=parser.parse_args()
    if args.command=='backup':
        calendar=ReviewCalendar(tuple(int(v) for v in args.working_weekdays.split(',')),tuple(args.non_working_date))
        result=create_backup(args.database,args.data_root,args.reports_root,args.output,calendar=calendar)
    elif args.command=='verify':result=verify_backup(args.backup)
    elif args.command=='restore':result=restore_backup(args.backup,args.output)
    else:
        from .notifications import Notifications
        from .review_server import make_server
        store=restored_store(args.restored)
        notifications=Notifications(store,dict(dry_run=True,replay_existing=False,case_url=f'http://127.0.0.1:{args.port}/'))
        server=make_server(store,port=args.port,notifications=notifications,instance_id='restored-review-copy')
        print(f'Restored UI ready: http://127.0.0.1:{server.server_port} ; dry-run, no automatic dispatch',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
        return
    print(json.dumps(dict(command=args.command,scenarios=result['scenarios'],status='verified'),ensure_ascii=False))


if __name__=='__main__':main()
