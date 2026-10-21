"""Scheduled local backup job, owned retention, health status and restore CLI."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from xml.etree import ElementTree as ET

from .backup_suite import (VERSION as SUITE_VERSION, MANIFEST, NAME, create_suite, verify_suite,
                          restore_suite, restored_suite, no_link)
from .case_identity import digest
from .feedback import feedback_lock
from .review_backup import guarded, ROOT
from .review_capacity import ReviewCalendar

VERSION = 'review-backup-job-v1'
OWNER_FILE = 'backup_repository.json'
VN = timezone(timedelta(hours=7))
RUN_NAME = re.compile(r'run-\d{8}T\d{6}Z-[0-9a-f]{8}\Z')


def timestamp(value):
    at = datetime.fromisoformat(value)
    if at.utcoffset() is None: raise ValueError('Backup timestamps require a timezone')
    return at.astimezone(timezone.utc)


def atomic_json(path, value):
    temporary = path.with_name('.'+path.name+'-'+uuid.uuid4().hex)
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists(): temporary.unlink()


def load_config(path):
    path = Path(path).resolve()
    raw = json.loads(path.read_text(encoding='utf-8-sig'))
    required = {'version','job_id','backup_root','database','data_root','reports_root',
                'p2_stores','schedule','retention','calendar','timeout_seconds'}
    if not isinstance(raw,dict) or set(raw)!=required or raw['version']!=VERSION:
        raise ValueError('Invalid backup job configuration')
    if not isinstance(raw['job_id'],str) or not NAME.fullmatch(raw['job_id']):
        raise ValueError('Invalid backup job ID')
    if not isinstance(raw['schedule'],dict) or raw['schedule'].keys()!={'timezone','daily_at'} or raw['schedule']['timezone']!='Asia/Saigon':
        raise ValueError('Backup schedule must use Asia/Saigon')
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',raw['schedule']['daily_at']):
        raise ValueError('Invalid daily backup time')
    retention = raw['retention']
    if not isinstance(retention,dict) or set(retention)!={'days','minimum_successful'}:
        raise ValueError('Invalid retention policy')
    for key,maximum in (('days',3650),('minimum_successful',100)):
        if type(retention[key]) is not int or not 1<=retention[key]<=maximum:
            raise ValueError('Invalid retention '+key)
    if type(raw['timeout_seconds']) is not int or not 1<=raw['timeout_seconds']<=3600:
        raise ValueError('Invalid backup timeout')
    def resolve(value):
        if not isinstance(value,str) or not value: raise ValueError('Empty backup path')
        candidate = Path(value)
        if not candidate.is_absolute(): candidate = path.parent/candidate
        for parent in (candidate,*candidate.parents): no_link(parent)
        return guarded(candidate)
    config = dict(raw, config_path=path)
    for key in ('backup_root','database','data_root','reports_root'): config[key]=resolve(raw[key])
    if not isinstance(raw['p2_stores'],list) or not raw['p2_stores']:
        raise ValueError('At least one P2 store is required')
    names,databases,stores = set(),set(),[]
    for item in raw['p2_stores']:
        if not isinstance(item,dict) or set(item)!={'id','database','source','report'}:
            raise ValueError('Invalid P2 store configuration')
        name = item['id']
        if not isinstance(name,str) or not NAME.fullmatch(name) or name in names:
            raise ValueError('Invalid or duplicate P2 store ID')
        names.add(name)
        store = dict(id=name,**{key:resolve(item[key]) for key in ('database','source','report')})
        if store['database'] in databases: raise ValueError('Duplicate P2 database')
        databases.add(store['database']); stores.append(store)
    config['p2_stores']=stores
    calendar = raw['calendar']
    if not isinstance(calendar,dict) or set(calendar)!={'working_weekdays','non_working_dates'}:
        raise ValueError('Invalid review calendar')
    config['calendar'] = ReviewCalendar(tuple(calendar['working_weekdays']),tuple(calendar['non_working_dates']))
    root = config['backup_root']
    if root==root.parent or root.is_relative_to(ROOT/'data'):
        raise ValueError('Unsafe backup repository')
    inputs = [config[k] for k in ('database','data_root','reports_root')]
    inputs += [store[k] for store in stores for k in ('database','source','report')]
    for source in [*inputs,path]:
        if root==source or root.is_relative_to(source) or source.is_relative_to(root):
            raise ValueError('Backup repository overlaps an input/configuration')
    for parent in (root,*root.parents):
        if any((parent/name).is_file() for name in ('manifest.json','case_queue.csv','predictions_frozen.json',MANIFEST)):
            raise ValueError('Backup repository overlaps a frozen snapshot')
    config['source_binding'] = digest([str(p) for p in inputs])
    return config


def repository_owner(config, *, create=False):
    root = config['backup_root']; no_link(root)
    path = root/OWNER_FILE
    if not path.exists():
        if not create: raise FileNotFoundError('Backup repository is not initialized')
        owner = dict(version=VERSION,job_id=config['job_id'],repository_id=uuid.uuid4().hex,
                     source_binding=config['source_binding'])
        with path.open('x',encoding='utf-8') as stream: json.dump(owner,stream,indent=2)
    no_link(path)
    owner = json.loads(path.read_text(encoding='utf-8'))
    if (owner.get('version')!=VERSION or owner.get('job_id')!=config['job_id']
            or owner.get('source_binding')!=config['source_binding']
            or not re.fullmatch('[0-9a-f]{32}',owner.get('repository_id',''))):
        raise ValueError('Backup repository ownership/source binding mismatch')
    return owner


def retention_plan(config, owner, now):
    root = config['backup_root']; no_link(root)
    checked, warnings = [], []
    for candidate in root.iterdir():
        if not RUN_NAME.fullmatch(candidate.name): continue
        try:
            no_link(candidate)
            if not candidate.is_dir() or candidate.resolve().parent!=root:
                raise ValueError('Retention candidate is outside its repository')
            manifest = verify_suite(candidate,require_runtime=False)
            if manifest['owner']!=owner:
                continue
            created = timestamp(manifest['created_at'])
            if created>now: raise ValueError('Backup creation time is in the future')
            checked.append((created,candidate,manifest['manifest_sha256']))
        except Exception as error:
            warnings.append(dict(path=str(candidate),error=type(error).__name__,message=str(error)))
    checked.sort(key=lambda item:(item[0],item[1].name),reverse=True)
    protected = {path for _,path,_ in checked[:config['retention']['minimum_successful']]}
    cutoff = now-timedelta(days=config['retention']['days'])
    expired = [dict(path=str(path),manifest_sha256=checksum)
               for created,path,checksum in checked if created<cutoff and path not in protected]
    return dict(delete=expired,verified_successful=len(checked),warnings=warnings)


def prune(config, owner, now):
    plan = retention_plan(config,owner,now)
    removed = []
    root = config['backup_root'].resolve()
    for item in plan['delete']:
        path = Path(item['path'])
        try:
            no_link(path)
            resolved = path.resolve()
            if resolved!=path or resolved.parent!=root or not RUN_NAME.fullmatch(resolved.name):
                raise ValueError('Refusing unexpected recursive retention target')
            manifest = verify_suite(resolved,require_runtime=False)
            if manifest['owner']!=owner or manifest['manifest_sha256']!=item['manifest_sha256']:
                raise ValueError('Retention candidate changed after planning')
            shutil.rmtree(resolved)
            removed.append(str(resolved))
        except Exception as error:
            plan['warnings'].append(dict(path=str(path),error=type(error).__name__,message=str(error)))
    return dict(deleted=removed,warnings=plan['warnings'],verified_successful_before=plan['verified_successful'])


def record(config, event):
    root = config['backup_root']
    previous = json.loads((root/'latest.json').read_text(encoding='utf-8')) if (root/'latest.json').exists() else {}
    if event['status'] in {'success','retention_warning'}:
        event['last_success_at']=event['completed_at']
        event['last_success_bundle']=event['bundle']
        event['consecutive_failures']=0
    else:
        event['last_success_at']=previous.get('last_success_at')
        event['last_success_bundle']=previous.get('last_success_bundle')
        event['consecutive_failures']=previous.get('consecutive_failures',0)+1
    with (root/'events.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(event,ensure_ascii=False)+'\n'); stream.flush(); os.fsync(stream.fileno())
    atomic_json(root/'latest.json',event)


def run_job(config_path, *, clock=None):
    config = load_config(config_path)
    now = (clock or (lambda:datetime.now(timezone.utc)))()
    if now.utcoffset() is None: raise ValueError('Job clock must have a timezone')
    now = now.astimezone(timezone.utc)
    root = config['backup_root']; root.mkdir(parents=True,exist_ok=True)
    try:
        with feedback_lock(root,timeout=.1):
            owner = repository_owner(config,create=True)
            run_id = 'run-'+now.strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
            event = dict(version=VERSION,job_id=config['job_id'],run_id=run_id,started_at=now.isoformat(),
                         status='running',schedule=config['schedule'])
            try:
                manifest = create_suite(config['database'],config['data_root'],config['reports_root'],
                    config['p2_stores'],root/run_id,owner=owner,calendar=config['calendar'],timeout=config['timeout_seconds'])
                # An injected clock controls retention tests without modifying immutable manifests.
                finished = (clock or (lambda:datetime.now(timezone.utc)))().astimezone(timezone.utc)
                cleaned = prune(config,owner,max(finished,timestamp(manifest['created_at'])))
                event.update(status='retention_warning' if cleaned['warnings'] else 'success',
                    completed_at=finished.isoformat(),bundle=str(root/run_id),manifest_sha256=manifest['manifest_sha256'],
                    p2_stores=[dict(id=row['id'],history_events=row['state']['history_events']) for row in manifest['p2_stores']],
                    retention=cleaned,exit_code=2 if cleaned['warnings'] else 0)
            except Exception as error:
                event.update(status='failed',completed_at=datetime.now(timezone.utc).isoformat(),
                    error=type(error).__name__,message=str(error),exit_code=1,
                    retention=dict(deleted=[],reason='No pruning after a failed backup'))
            record(config,event)
            return event
    except TimeoutError:
        return dict(status='skipped_busy',exit_code=0,job_id=config['job_id'])


def status(config_path, *, now=None):
    config = load_config(config_path); root=config['backup_root']
    if not (root/'latest.json').exists(): return dict(status='never_run',healthy=False,schedule=config['schedule'])
    repository_owner(config)
    event = json.loads((root/'latest.json').read_text(encoding='utf-8'))
    at = (now or datetime.now(timezone.utc)).astimezone(VN)
    hour,minute = map(int,config['schedule']['daily_at'].split(':'))
    scheduled = at.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if scheduled>at: scheduled-=timedelta(days=1)
    if at<scheduled+timedelta(hours=2): scheduled-=timedelta(days=1)
    last = timestamp(event['last_success_at']) if event.get('last_success_at') else None
    overdue = last is None or last<scheduled
    return dict(event,healthy=event['status']=='success' and not overdue,overdue=overdue,
                expected_schedule=config['schedule'],last_expected_run=scheduled.isoformat())


def task_xml(config_path, executable, user_sid, *, now=None):
    config=load_config(config_path)
    executable=Path(executable).resolve()
    if not executable.is_file() or executable.name.casefold() not in {'python.exe','pythonw.exe'}:
        raise ValueError('Task executable must be an installed Python executable')
    if not re.fullmatch(r'S-1-\d+(?:-\d+)+',user_sid): raise ValueError('Invalid Windows user SID')
    at=(now or datetime.now(timezone.utc)).astimezone(VN)
    hour,minute=map(int,config['schedule']['daily_at'].split(':'))
    boundary=at.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if boundary<=at: boundary+=timedelta(days=1)
    namespace='http://schemas.microsoft.com/windows/2004/02/mit/task'
    ET.register_namespace('',namespace)
    def element(parent,name,text=None,**attributes):
        node=ET.SubElement(parent,'{'+namespace+'}'+name,attributes)
        if text is not None: node.text=text
        return node
    task=ET.Element('{'+namespace+'}Task',version='1.3')
    registration=element(task,'RegistrationInfo')
    element(registration,'Description','Agent22 managed review/P2 backup: '+config['job_id'])
    trigger=element(element(task,'Triggers'),'CalendarTrigger')
    element(trigger,'StartBoundary',boundary.isoformat(timespec='seconds'))
    element(trigger,'Enabled','true')
    element(element(trigger,'ScheduleByDay'),'DaysInterval','1')
    principal=element(element(task,'Principals'),'Principal',id='Author')
    element(principal,'UserId',user_sid); element(principal,'LogonType','InteractiveToken')
    element(principal,'RunLevel','LeastPrivilege')
    settings=element(task,'Settings')
    for name,value in dict(MultipleInstancesPolicy='IgnoreNew',DisallowStartIfOnBatteries='false',
        StopIfGoingOnBatteries='false',AllowHardTerminate='false',StartWhenAvailable='true',
        RunOnlyIfNetworkAvailable='false',AllowStartOnDemand='true',Enabled='true',Hidden='false',
        RunOnlyIfIdle='false',WakeToRun='false',ExecutionTimeLimit='PT1H',Priority='7').items():
        element(settings,name,value)
    action=element(element(task,'Actions',Context='Author'),'Exec')
    element(action,'Command',str(executable))
    element(action,'Arguments',subprocess.list2cmdline(['-B','-m','sme_fraud.backup_job','run','--config',str(config['config_path'])]))
    element(action,'WorkingDirectory',str(ROOT))
    return ET.tostring(task,encoding='unicode',xml_declaration=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('run','status','prune-plan','check-config'):
        command=commands.add_parser(name); command.add_argument('--config',type=Path,required=True)
    task=commands.add_parser('task-xml'); task.add_argument('--config',type=Path,required=True)
    task.add_argument('--python-executable',type=Path,required=True); task.add_argument('--user-sid',required=True)
    task.add_argument('--output',type=Path,required=True)
    for name in ('verify','restore'):
        command=commands.add_parser(name); command.add_argument('--backup',type=Path,required=True)
        if name=='restore': command.add_argument('--output',type=Path,required=True)
    serve=commands.add_parser('serve'); serve.add_argument('--restored',type=Path,required=True)
    serve.add_argument('--p2-store'); serve.add_argument('--port',type=int,default=8772)
    args=parser.parse_args()
    try:
        if args.command=='run': result=run_job(args.config)
        elif args.command=='check-config':
            config=load_config(args.config)
            result=dict(status='valid',job_id=config['job_id'],schedule=config['schedule'],retention=config['retention'],
                        p2_stores=[row['id'] for row in config['p2_stores']])
        elif args.command=='task-xml':
            xml=task_xml(args.config,args.python_executable,args.user_sid)
            with args.output.open('x',encoding='utf-16') as stream: stream.write(xml)
            result=dict(status='definition_written',output=str(args.output.resolve()))
        elif args.command=='status':
            result=status(args.config); result['exit_code']=0 if result.get('healthy') else 2
        elif args.command=='prune-plan':
            config=load_config(args.config)
            with feedback_lock(config['backup_root']): result=retention_plan(config,repository_owner(config),datetime.now(timezone.utc))
        elif args.command=='verify':
            manifest=verify_suite(args.backup); result=dict(status='verified',p2_stores=len(manifest['p2_stores']))
        elif args.command=='restore':
            receipt=restore_suite(args.backup,args.output); result=dict(status='restored',p2_stores=len(receipt['p2_stores']))
        else:
            from .notifications import Notifications
            from .review_server import make_server
            store,p2=restored_suite(args.restored,args.p2_store)
            server=make_server(store,args.port,instance_id='restored-review-p2-suite',p2_controls=p2,
                               notifications=Notifications(store,dict(dry_run=True,replay_existing=False)))
            print(f'Restored review + P2 UI: http://127.0.0.1:{server.server_port}/ ; dry-run only',flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: server.server_close()
            return 0
    except Exception as error:
        result=dict(status='failed',error=type(error).__name__,message=str(error),exit_code=1)
    try: print(json.dumps(result,ensure_ascii=True),flush=True)
    except (OSError,AttributeError): pass  # pythonw has no stdout; durable job files remain available.
    return result.get('exit_code',0)


if __name__=='__main__': sys.exit(main())
