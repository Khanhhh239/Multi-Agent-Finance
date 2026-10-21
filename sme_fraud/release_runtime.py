"""Operations executed inside the installed, matching application runtime."""
from contextlib import redirect_stdout
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import threading
from urllib.request import urlopen

from .version import APP_VERSION, REVIEW_SCHEMA_VERSION, P2_JOURNAL_SCHEMA_VERSION


def inspect_data(root):
    from .backup_suite import RECEIPT, runtime, p2_state
    from .case_identity import digest
    from .p2_controls_web import P2Controls
    from .review_backup import restored_store, read_database, database_state, snapshot_state, guarded
    root=guarded(root)
    suite=(root/RECEIPT).is_file()
    p2_specs=[]; p2_states={}
    if suite:
        receipt=json.loads((root/RECEIPT).read_text(encoding='utf-8'))
        checksum=receipt.pop('receipt_sha256',None)
        if digest(receipt)!=checksum or receipt['runtime_contract']!=runtime():
            raise ValueError('Suite receipt or runtime mismatch')
        review=root/'review'
        for item in receipt['p2_stores']:
            paths={key:guarded(root/item[key]) for key in ('source','report','database')}
            if any(not path.is_relative_to(root) for path in paths.values()):
                raise ValueError('P2 reference escapes restored data')
            p2=P2Controls(paths['source'],paths['report'],paths['database'],readonly=True)
            if p2.snapshot_id!=item['snapshot_id']: raise ValueError('P2 snapshot mismatch')
            with read_database(p2.database) as db: p2_states[item['id']]=p2_state(db,p2)
            p2_specs.append(dict(id=item['id'],**paths))
    else: review=root
    store=restored_store(review)
    with read_database(store.database) as db:
        tables=database_state(db); history=snapshot_state(db,store.reports_root,store.scenarios)
    logical=dict(review_tables=tables,review_history=history,p2=p2_states)
    return dict(kind='suite' if suite else 'review',app_version=APP_VERSION,
        schemas=dict(review=REVIEW_SCHEMA_VERSION,p2=P2_JOURNAL_SCHEMA_VERSION),
        logical_sha256=digest(logical),logical=logical,
        cases=sum(row['cases'] for row in history['snapshots'].values())),store,p2_specs


def operate(command,root,output=None):
    from .backup_suite import create_suite, restore_suite
    from .review_backup import create_backup, restore_backup
    if command=='restore':
        root=Path(root)
        result=(restore_suite(root,output) if (root/'suite_manifest.json').is_file() else restore_backup(root,output))
        return inspect_data(output)[0]
    info,store,p2_specs=inspect_data(root)
    if command=='snapshot':
        if info['kind']=='suite':
            create_suite(store.database,store.data_root,store.reports_root,p2_specs,output,
                         owner=dict(kind='deployment-checkpoint',created_at=datetime.now(timezone.utc).isoformat()),
                         calendar=store.review_calendar)
        else: create_backup(store.database,store.data_root,store.reports_root,output,calendar=store.review_calendar)
        return dict(status='snapshotted',logical_sha256=info['logical_sha256'],kind=info['kind'])
    if command=='probe':
        from .notifications import Notifications
        from .p2_controls_web import P2Controls
        from .review_server import make_server
        p2=None
        if p2_specs:
            item=p2_specs[0]; p2=P2Controls(item['source'],item['report'],item['database'],readonly=True)
        server=make_server(store,port=0,p2_controls=p2,notifications=Notifications(store,dict(dry_run=True,replay_existing=False)))
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            for path in ('/','/app.js','/styles.css','/case_graph.js','/vendor/cytoscape.min.js','/api/meta'):
                with urlopen(base+path,timeout=30) as response:
                    if response.status!=200 or not response.read(): raise RuntimeError('HTTP health probe failed')
            with urlopen(base+'/api/meta',timeout=30) as response:
                if json.load(response)['notification_mode']!='dry_run': raise RuntimeError('Probe must stay dry-run')
        finally: server.shutdown(); thread.join(); server.server_close()
        after=inspect_data(root)[0]
        if after['logical_sha256']!=info['logical_sha256']:
            raise RuntimeError('Health probe changed operational data')
        return dict(info,http_probe=True,notifications='dry_run')
    return info


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['inspect','probe','snapshot','restore','serve'])
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path)
    parser.add_argument('--port',type=int,default=8773); parser.add_argument('--instance-id',default='')
    args=parser.parse_args()
    try:
        if args.command=='serve':
            from .notifications import Notifications
            from .p2_controls_web import P2Controls
            from .review_server import make_server
            _,store,specs=inspect_data(args.root)
            selected=next((row for row in specs if row['id']=='step2_uat'),specs[0] if specs else None)
            p2=P2Controls(selected['source'],selected['report'],selected['database']) if selected else None
            server=make_server(store,args.port,instance_id=args.instance_id,p2_controls=p2,
                               notifications=Notifications(store,dict(dry_run=True,replay_existing=False)))
            print(f'Managed review UI: http://127.0.0.1:{server.server_port}/ ; dry-run',flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: server.server_close()
            return 0
        with redirect_stdout(io.StringIO()): result=operate(args.command,args.root,args.output)
        print(json.dumps(result,ensure_ascii=True),flush=True)
        return 0
    except Exception as error:
        print(json.dumps(dict(error=type(error).__name__,message=str(error)),ensure_ascii=True),flush=True)
        return 1


if __name__=='__main__': sys.exit(main())
