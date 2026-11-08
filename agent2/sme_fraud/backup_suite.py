"""Verified backup/restore of ReviewStore plus named, independent P2 journals."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import time

from .case_identity import digest
from .p2_controls_web import P2Controls
from .review_backup import (create_backup, verify_backup, restore_backup, restored_store,
    guarded, new_destination, stage_directory, read_database, copy_checked, sha, identifier, runtime_contract)

VERSION = 'review-p2-backup-suite-v1'
MANIFEST = 'suite_manifest.json'
RECEIPT = 'suite_restore_receipt.json'
NAME = re.compile(r'[a-z][a-z0-9_]{0,40}\Z')


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def runtime():
    root = Path(__file__).parent
    return dict(review=runtime_contract(), suite={name:sha(root/name)
                for name in ('backup_suite.py', 'p2_controls_web.py')})


def no_link(path):
    path = Path(path)
    if path.is_symlink() or getattr(path, 'is_junction', lambda:False)():
        raise ValueError('Backup paths cannot be symlinks or junctions')


def inventory(root):
    root = Path(root)
    no_link(root)
    result = {}
    for path in sorted(root.rglob('*')):
        no_link(path)
        if path.is_file() and path != root/MANIFEST:
            result[path.relative_to(root).as_posix()] = dict(sha256=sha(path), bytes=path.stat().st_size)
    return result


def copy_tree(source, target):
    source, target = guarded(source), Path(target)
    before = inventory(source)
    for name in before:
        copy_checked(source/name, target/name)
    if inventory(source) != before or inventory(target) != before:
        raise ValueError('P2 snapshot changed during backup')


def p2_state(db, controls):
    if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok'] or list(db.execute('PRAGMA foreign_key_check')):
        raise ValueError('P2 SQLite integrity check failed')
    schemas = list(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"))
    if 'reviews' not in {r['name'] for r in schemas}:
        raise ValueError('Not a P2 UAT database')
    tables = {}
    for schema in schemas:
        columns = [r[1] for r in db.execute('PRAGMA table_info('+identifier(schema['name'])+')')]
        projection = ','.join(map(identifier, columns))
        query = 'SELECT '+projection+' FROM '+identifier(schema['name'])+' ORDER BY '+projection
        value, count = hashlib.sha256(), 0
        for row in db.execute(query):
            encoded = [dict(blob_hex=v.hex()) if isinstance(v,bytes) else v for v in row]
            value.update((json.dumps(encoded,ensure_ascii=False,separators=(',',':'))+'\n').encode())
            count += 1
        tables[schema['name']] = dict(rows=count, sha256=value.hexdigest(), schema_sha256=digest(schema['sql']))
    history = controls._history(db)
    return dict(tables=tables, history_events=len(history), history_head=history[-1]['event_hash'] if history else '',
                current_review_count=len({r['control_id'] for r in history if r['snapshot_id']==controls.snapshot_id}))


def create_suite(database, data_root, reports_root, p2_stores, output, *, owner, calendar=None, timeout=120):
    paths = [guarded(p) for p in (database,data_root,reports_root)]
    database, data_root, reports_root = paths
    names, controls, seen = set(), [], set()
    for spec in p2_stores:
        name = spec['id']
        if not isinstance(name,str) or not NAME.fullmatch(name) or name in names:
            raise ValueError('P2 store IDs must be unique safe names')
        names.add(name)
        source, report, db = (guarded(spec[key]) for key in ('source','report','database'))
        if db in seen: raise ValueError('P2 databases cannot be listed twice')
        seen.add(db)
        for path in (source,report,db): no_link(path)
        controls.append((name,P2Controls(source,report,db,readonly=True)))
        paths.extend((source,report,db))
    if not controls: raise ValueError('At least one P2 journal is required')
    output = new_destination(output,paths)
    started = now_iso()
    with stage_directory(output) as staged:
        main = create_backup(database,data_root,reports_root,staged/'review',calendar=calendar,timeout=timeout)
        copied, stores = set(), []
        for name,control in controls:
            snap = control.snapshot_id
            asset = Path('p2/snapshots')/snap
            if snap not in copied:
                copy_tree(control.source,staged/asset/'data')
                copy_tree(control.report,staged/asset/'reports')
                copied.add(snap)
            relative_db = Path('p2/stores')/(name+'.sqlite3')
            target = staged/relative_db
            target.parent.mkdir(parents=True,exist_ok=True)
            with read_database(control.database) as source:
                state = p2_state(source,control)
                captured = now_iso()
                deadline = time.monotonic()+timeout
                def progress(status,remaining,total):
                    if time.monotonic()>deadline: raise TimeoutError('P2 SQLite backup timeout')
                with closing(sqlite3.connect(target)) as destination:
                    source.backup(destination,pages=256,progress=progress,sleep=.05)
                    destination.execute('PRAGMA journal_mode=DELETE')
            restored = P2Controls(staged/asset/'data',staged/asset/'reports',target,readonly=True)
            with read_database(target) as destination:
                if restored.snapshot_id!=snap or p2_state(destination,restored)!=state:
                    raise ValueError('P2 backup differs from its pinned source snapshot')
            stores.append(dict(id=name,snapshot_id=snap,database=relative_db.as_posix(),
                source=(asset/'data').as_posix(),report=(asset/'reports').as_posix(),
                captured_at=captured,original_database=str(control.database),state=state))
        manifest = dict(version=VERSION,status='complete',owner=owner,started_at=started,created_at=now_iso(),
            runtime_contract=runtime(),review_manifest_sha256=main['manifest_sha256'],
            p2_stores=stores,files=inventory(staged),
            consistency='Each SQLite has its own pinned read snapshot; P2 UAT journals are independent of ReviewStore.',
            notifications_on_restore='dry_run_no_dispatch',secrets_exported=False)
        manifest['manifest_sha256'] = digest(manifest)
        (staged/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        verify_suite(staged)
    return manifest


def verify_suite(bundle, *, require_runtime=True):
    no_link(bundle)
    bundle = guarded(bundle)
    no_link(bundle/MANIFEST)
    manifest = json.loads((bundle/MANIFEST).read_text(encoding='utf-8'))
    checksum = manifest.pop('manifest_sha256',None)
    if checksum!=digest(manifest): raise ValueError('Suite manifest checksum mismatch')
    manifest['manifest_sha256'] = checksum
    if manifest.get('version')!=VERSION or manifest.get('status')!='complete':
        raise ValueError('Unsupported or incomplete backup suite')
    for name in manifest['files']:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
            raise ValueError('Invalid suite file path')
        guarded(bundle/name)
    if inventory(bundle)!=manifest['files']: raise ValueError('Suite file inventory/checksum mismatch')
    if require_runtime:
        if manifest['runtime_contract']!=runtime(): raise ValueError('Use the matching backup-suite runtime')
        main = verify_backup(bundle/'review')
        if main['manifest_sha256']!=manifest['review_manifest_sha256']: raise ValueError('Review backup binding mismatch')
        ids = set()
        for item in manifest['p2_stores']:
            if not NAME.fullmatch(item['id']) or item['id'] in ids: raise ValueError('Invalid P2 store ID')
            ids.add(item['id'])
            for key in ('source','report','database'):
                if not any(name==item[key] or name.startswith(item[key]+'/') for name in manifest['files']):
                    raise ValueError('P2 reference is not bound to backed-up files')
            p2 = P2Controls(bundle/item['source'],bundle/item['report'],bundle/item['database'],readonly=True)
            with read_database(p2.database) as db:
                if p2.snapshot_id!=item['snapshot_id'] or p2_state(db,p2)!=item['state']:
                    raise ValueError('P2 semantic state differs from suite manifest')
    return manifest


def restore_suite(bundle, output):
    bundle = guarded(bundle)
    output = new_destination(output,(bundle,))
    manifest = verify_suite(bundle)
    # ReviewStore rebases absolute bindings to its final path. The outer folder
    # becomes usable only once the suite receipt is published last. A process
    # crash can leave an incomplete folder; it is never silently overwritten.
    output.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir()
    try:
        main = restore_backup(bundle/'review',output/'review')
        for name in manifest['files']:
            if not name.startswith('review/'): copy_checked(bundle/name,output/name)
        for item in manifest['p2_stores']:
            p2 = P2Controls(output/item['source'],output/item['report'],output/item['database'],readonly=True)
            with read_database(p2.database) as db:
                if p2_state(db,p2)!=item['state']: raise ValueError('Restored P2 state mismatch')
        if inventory(bundle)!=manifest['files']: raise ValueError('Suite changed during restore')
        receipt = dict(version=VERSION,backup_manifest_sha256=manifest['manifest_sha256'],restored_at=now_iso(),
            runtime_contract=manifest['runtime_contract'],review_receipt=main,p2_stores=manifest['p2_stores'],
            notifications_mode='dry_run',dispatch_performed=False)
        receipt['receipt_sha256'] = digest(receipt)
        (output/RECEIPT).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except BaseException:
        checked = output.resolve()
        if checked!=output or not checked.is_dir() or checked==bundle or bundle.is_relative_to(checked):
            raise ValueError('Refusing unexpected restore cleanup path')
        shutil.rmtree(checked)
        raise
    return receipt


def restored_suite(root, p2_id=None):
    root = guarded(root)
    receipt = json.loads((root/RECEIPT).read_text(encoding='utf-8'))
    checksum = receipt.pop('receipt_sha256',None)
    if digest(receipt)!=checksum: raise ValueError('Restore suite receipt checksum mismatch')
    if receipt.get('version')!=VERSION or receipt.get('runtime_contract')!=runtime():
        raise ValueError('Restored suite needs its matching runtime')
    store = restored_store(root/'review')
    items = receipt['p2_stores']
    item = next((v for v in items if v['id']==p2_id),None) if p2_id else items[0]
    if item is None: raise ValueError('Unknown restored P2 journal')
    for key in ('source','report','database'):
        path = PurePosixPath(item[key])
        if path.is_absolute() or '..' in path.parts or '\\' in item[key] or ':' in item[key]:
            raise ValueError('Invalid restored P2 reference')
        if not guarded(root/item[key]).is_relative_to(root): raise ValueError('P2 reference escapes restored suite')
    verified = P2Controls(root/item['source'],root/item['report'],root/item['database'],readonly=True)
    if verified.snapshot_id!=item['snapshot_id']: raise ValueError('Restored P2 snapshot binding mismatch')
    # Writable only in the restored copy, after the receipt/state were verified.
    p2 = P2Controls(root/item['source'],root/item['report'],root/item['database'])
    return store,p2
