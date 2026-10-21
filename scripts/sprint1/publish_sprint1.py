"""Commit/push đúng nhánh sau đủ phép đo và QA; chặn dữ liệu thô và remote thay đổi."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import subprocess
import sys
from fullweek_refresh import ROOT,JOBS,check_protected
from verify_code import source_hash

REMOTE='https://github.com/Khanhhh239/Multi-Agent-Finance.git'
BRANCH='agent1-Khanh'


def validate_paths(paths):
    for name in paths:
        path=PurePosixPath(name);parts=path.parts
        blocked=any(part in {'raw','interim','processed','.git','.venv','.venv-check','.publish-repo'} or part.startswith('.state') for part in parts)
        if path.is_absolute() or '..' in parts or blocked or path.suffix.lower() in {'.parquet','.dat','.db','.sqlite','.sqlite3','.key','.pem','.pfx','.log'}:
            raise ValueError('File không được phép đưa vào commit: '+name)
        if path.name.startswith('.env') or path.name in {'api-token.txt','token.txt'}:
            raise ValueError('File chứa cấu hình riêng: '+name)
        if parts and parts[0]=='data' and (len(parts)<3 or parts[1]!='synthetic' or path.suffix!='.json'):
            raise ValueError('Chỉ cho phép cấu hình tổng hợp trong data/: '+name)


def git(*arguments,check=True):
    result=subprocess.run(['git','-C',str(ROOT/'.publish-repo'),*arguments],capture_output=True,text=True,encoding='utf-8',
        env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never'))
    if check and result.returncode:raise RuntimeError('git '+arguments[0]+' failed: '+result.stderr[-1500:])
    return result


def csv_hashes():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'outputs').rglob('*.csv')}


def main():
    status=ROOT/'outputs/implementation/publish_status.json'
    try:
        check_protected()
        records=json.loads((ROOT/'outputs/implementation/fullweek_refresh.json').read_text(encoding='utf-8'))
        latest={record['job']:record for record in records}
        if not all(latest.get(name,{}).get('status')=='passed' for name in JOBS):raise ValueError('Chưa đủ 18 job; chưa commit/push')
        additions=json.loads((ROOT/'outputs/implementation/fullweek_additional.json').read_text(encoding='utf-8'))
        if not all(any(r['job']==name and r['status']=='passed' for r in additions) for name in ['P4','G3','T9-source-policy']):
            raise ValueError('Chưa đủ P4/G3/T9 source policy')
        for name in ['t1/P4/protocol.json','t1/G3/protocol.json','t9/sprint3/source_policy.json']:
            protocol=json.loads((ROOT/'outputs'/name).read_text(encoding='utf-8'))
            if not protocol.get('complete'):raise ValueError('Giao thức chưa hoàn tất: '+name)
            if name.startswith('t9/') and protocol.get('selected_tau') is not None and not protocol.get('target_complete'):
                raise ValueError('Chưa chấm chính sách T9 nguồn trên target')
        verification=json.loads((ROOT/'outputs/implementation/fullweek_code_verification.json').read_text(encoding='utf-8'))
        if not verification.get('passed') or verification['source_sha256']!=source_hash():raise ValueError('Mã hiện tại chưa được kiểm thử')
        repeat=json.loads((ROOT/'outputs/implementation/report_reproducibility.json').read_text(encoding='utf-8'))
        if not repeat.get('passed') or not repeat.get('stable_inputs'):raise ValueError('Báo cáo chưa tái lập ổn định')
        for name,digest in repeat['report_sha256'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Báo cáo thay đổi sau QA: '+name)
        if git('remote','get-url','origin').stdout.strip()!=REMOTE or git('branch','--show-current').stdout.strip()!=BRANCH:
            raise ValueError('Sai remote/nhánh publish')
        git('fetch','origin',BRANCH)
        if git('merge-base','--is-ancestor','origin/'+BRANCH,'HEAD',check=False).returncode:
            raise ValueError('Remote có thay đổi chưa tích hợp; dừng để tránh ghi đè công việc khác')
        journal=ROOT/'docs/05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md'
        from fullweek_journal import normalize
        from fullweek_refresh import measure
        text=normalize(journal.read_text(encoding='utf-8'))
        # Older in-memory controllers may have recorded row counts only.
        # Recover actual metrics from immutable legacy CSVs and finished outputs.
        for record in latest.values():
            primary=ROOT/record['primary']
            legacy=primary.with_name(primary.stem+'.legacy_expand.csv')
            if legacy.exists():
                old=f"{record['before']} → {record.get('after', '')}"
                new=f'{measure(legacy)} → {measure(primary)}'
                text='\n'.join(line.replace(old,new) if f"| {record['job']} |" in line else line for line in text.split('\n'))
        journal.write_text(text,encoding='utf-8')
        before=csv_hashes()
        subprocess.run([sys.executable,str(ROOT/'scripts/sprint1/prepare_publish.py'),'--copy'],cwd=ROOT,check=True)
        if before!=csv_hashes() or verification['source_sha256']!=source_hash():raise ValueError('Nguồn thay đổi trong khi đồng bộ')
        git('add','-A')
        changed=[name for name in git('diff','--cached','--name-only','-z').stdout.split('\0') if name]
        validate_paths(changed)
        suspicious=re.compile(rb'(?:sk-proj-[A-Za-z0-9_-]{25,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')
        for name in changed:
            path=ROOT/'.publish-repo'/name
            if path.is_file() and path.suffix.lower() not in {'.png','.jpg'} and suspicious.search(path.read_bytes()):
                raise ValueError('Cần kiểm tra dữ liệu xác thực trước publish: '+name)
        if changed:
            message=('Rerun Agent 1 hazard chain with full-week censoring\n\n'
                'Archive legacy expand CSVs and refresh the ordered benchmark chain. Integrate real-data v2 G5/G6 with legacy audit gates; record controlled P4, Mondrian CQR and source-selected T9 results.\n\n'
                'Reports are generated from CSVs, tests pass in both environments, and unmet scientific criteria remain explicit. No raw data, parquet, private state or tokens are included.\n\n'
                'Co-Authored-By: Codex <codex@openai.com>\n')
            body=ROOT/'.publish-repo/.git/fullweek_commit_message.txt';body.write_text(message,encoding='utf-8')
            git('commit','--file',str(body))
        commit=git('rev-parse','HEAD').stdout.strip()
        git('push','origin','HEAD:'+BRANCH)
        remote=git('ls-remote','--heads','origin',BRANCH).stdout.split()[0]
        if commit!=remote:raise ValueError('Chưa xác nhận HEAD trên remote')
        status.write_text(json.dumps(dict(passed=True,commit=commit,branch=BRANCH,remote=REMOTE,
            commit_url='https://github.com/Khanhhh239/Multi-Agent-Finance/commit/'+commit),indent=2),encoding='utf-8')
        print('committed and pushed',commit,flush=True)
    except Exception as error:
        status.write_text(json.dumps(dict(passed=False,error=str(error),branch=BRANCH,remote=REMOTE),indent=2),encoding='utf-8')
        raise


if __name__=='__main__':main()
