"""Đợi chuỗi 18 job hoàn tất, sau đó đo các việc 2–5 và kiểm tra; không tự push."""
import json
import hashlib
import argparse
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from fullweek_refresh import ROOT,JOBS,free_ram,check_protected,measure


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    directory=ROOT/'outputs/implementation';state=directory/'fullweek_refresh.json'
    while True:
        try:records=json.loads(state.read_text(encoding='utf-8')) if state.exists() else []
        except (json.JSONDecodeError,OSError):time.sleep(1);continue
        latest={record['job']:record for record in records}
        failed=[name for name in JOBS if latest.get(name,{}).get('status')=='failed']
        if failed:raise ValueError('Chuỗi chính thất bại: '+','.join(failed))
        if all(latest.get(name,{}).get('status')=='passed' for name in JOBS):break
        print('waiting ordered fullweek refresh',flush=True);time.sleep(30)
    path=directory/'fullweek_additional.json'
    records=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    for job,primary in [('P4','t1/P4/metrics.csv'),
        ('G3','t1/G3/metrics.csv'),('T9-source-policy','t9/sprint3/source_precision_coverage.csv')]:
        if any(r['job']==job and r['status']=='passed' for r in records):continue
        check_protected()
        while free_ram()<3*1024**3:
            print(job,'waiting >=3GiB',flush=True);time.sleep(30)
        before=measure(ROOT/'outputs'/primary);started=time.monotonic()
        record=dict(job=job,status='running',free_ram_bytes=free_ram());records.append(record)
        path.write_text(json.dumps(records,indent=2),encoding='utf-8')
        with (directory/f'fullweek_{job}.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,'-u',str(ROOT/'scripts/run_plan.py'),'--jobs',job,'--fail-fast'],
                cwd=ROOT,check=False,stdout=log,stderr=subprocess.STDOUT)
        record.update(status='passed' if result.returncode==0 else 'failed',exit_code=result.returncode,seconds=time.monotonic()-started)
        check_protected();path.write_text(json.dumps(records,indent=2),encoding='utf-8')
        after=measure(ROOT/'outputs'/primary)
        conclusion=''
        if job in ['P4','G3'] and (ROOT/'outputs/t1'/job/'protocol.json').exists():
            protocol=json.loads((ROOT/'outputs/t1'/job/'protocol.json').read_text(encoding='utf-8'))
            conclusion=f"; tiêu chí đạt={protocol.get('eligible')}; P4 mặc định vẫn tắt" if job=='P4' else f"; tiêu chí G3 đạt={protocol.get('eligible')}"
        if job=='T9-source-policy':
            protocol=json.loads((ROOT/'outputs/t9/sprint3/source_policy.json').read_text(encoding='utf-8'))
            conclusion=f"; chọn nguồn tau={protocol.get('selected_tau')}, variant={protocol.get('selected_variant')}; stop={protocol.get('stop_rule_recommendation')}"
        from fullweek_journal import append_row
        append_row(ROOT/'docs/05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md',
            f"| {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')} | {job} | {record['seconds']:.1f}s | {before} → {after} | {record['status']}; `{primary}`; mã khoá giữ nguyên{conclusion} |")
        if result.returncode:return result.returncode
    for script in ['real_v2_b1_reference.py','sync_v2_index.py']:
        subprocess.run([sys.executable,str(ROOT/'scripts/sprint1'/script)],cwd=ROOT,check=True)
    for script in ['compare_collection_policy.py','compare_cash_baselines.py']:
        subprocess.run([sys.executable,str(ROOT/'scripts'/script)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/sprint1/verify_code.py')],cwd=ROOT,check=True)
    backups=json.loads((directory/'legacy_expand_backups.json').read_text(encoding='utf-8'))
    for item in backups:
        if hashlib.sha256((ROOT/item['backup']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Backup legacy bị thay đổi: '+item['backup'])
    subprocess.run([sys.executable,str(ROOT/'scripts/verify_report_repeat.py')],cwd=ROOT,check=True)
    if args.publish:
        subprocess.run([sys.executable,str(ROOT/'scripts/sprint1/publish_sprint1.py')],cwd=ROOT,check=True)
        return 0
    print('Ready for final review, commit and push; no push performed by this worker',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
