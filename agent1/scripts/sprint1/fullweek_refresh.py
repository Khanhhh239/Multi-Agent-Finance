"""Chuỗi chạy lại tuần đầy đủ: RAM >=3 GiB, sao lưu, hash mã khoá và nhật ký mỗi job."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))

JOBS=['A','B','DA-paired','T1-variants','onboarding','EF','noisy-EF','T9-T1','T3-T1',
    'crisis-ablation','DR-eval','E2E-full','T6','regime-cash','collection-policy','copula-hierarchy','IW-oof','scaling']
PRIMARY=dict(zip(JOBS,['t1/A_rolling_origin_src.csv','t1/B_domain_adaptation_tgt.csv',
    't1/DA_paired_metrics.csv','t1/T1_variants.csv','t1/onboarding_source_validation.csv',
    't1/EF_t8_t9.csv','t1/EF_t8_t9_src_noisy_promises.csv','t1/T9_T1_error_propagation.csv',
    't1/T3_T1_ablation.csv','t1/crisis_ablation.csv','t1/DR/metrics.csv','e2e/e2e_metrics.csv',
    't6/t6_interval_metrics.csv','t7/regime_cash/metrics.csv','t6/collection_policy/metrics.csv',
    't6/copula_hierarchy/metrics.csv','t1/IW_oof/metrics.csv','t1/scaling_results.csv']))


def free_ram():
    if os.name=='nt':
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
                *[(name,ctypes.c_ulonglong) for name in ['total','available','page_total','page_free','virtual_total','virtual_free','extended']]]
        state=Memory();state.length=ctypes.sizeof(state)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):raise OSError('Không đọc được RAM')
        return state.available
    return os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')


def check_protected():
    expected=json.loads((ROOT/'outputs/implementation/fullweek_protected.json').read_text(encoding='utf-8'))
    for name,digest in expected.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Mã khoá thay đổi: '+name)
    if os.environ.get('AGENT1_EXPAND_LEGACY')=='1':raise ValueError('Không chạy chuỗi mới với expand legacy')


def measure(path):
    import pandas as pd
    if not path.exists():return 'chưa có CSV'
    frame=pd.read_csv(path)
    values=[]
    for column in ['pinball_avg','pinball','WAPE','cov80','IS80','DSO','WAPE_collect_w1_4','mean','reduction_vs_P0','precision','coverage']:
        if column in frame:
            values.append(f'{column}={pd.to_numeric(frame[column],errors="coerce").mean():.6g}')
            if len(values)==2:break
    return '; '.join(values) or f'{len(frame)} hàng'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--jobs',default=','.join(JOBS))
    parser.add_argument('--poll-seconds',type=int,default=30);args=parser.parse_args()
    directory=ROOT/'outputs/implementation';state_path=directory/'fullweek_refresh.json'
    records=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else []
    journal=ROOT/'docs/05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md'
    for job in args.jobs.split(','):
        check_protected();primary=ROOT/'outputs'/PRIMARY[job]
        if any(r['job']==job and r['status']=='passed' for r in records):
            print(job,'already passed in refresh journal',flush=True);continue
        before=measure(primary)
        while (available:=free_ram())<3*1024**3:
            state_path.with_name('fullweek_wait.json').write_text(json.dumps(dict(job=job,status='waiting_for_3GiB',
                free_bytes=available,checked_at=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()),indent=2),encoding='utf-8')
            print(job,'waiting RAM',round(available/1024**3,2),'GiB',flush=True);time.sleep(args.poll_seconds)
        started=time.monotonic()
        record=dict(job=job,status='running',started_at=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
            free_ram_bytes=available,primary=str(primary.relative_to(ROOT)),before=before)
        records.append(record);state_path.write_text(json.dumps(records,indent=2),encoding='utf-8')
        with (directory/f'fullweek_{job}.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,'-u',str(ROOT/'scripts/run_plan.py'),'--jobs',job,'--fail-fast'],
                cwd=ROOT,env=dict(os.environ,AGENT1_THREADS='4',OMP_NUM_THREADS='4',PYTHONUTF8='1'),stdout=log,stderr=subprocess.STDOUT)
        elapsed=time.monotonic()-started;check_protected()
        record.update(status='passed' if result.returncode==0 else 'failed',exit_code=result.returncode,seconds=elapsed)
        if result.returncode==0:
            import pandas as pd
            frame=pd.read_csv(primary)
            if 'measurement_version' not in frame or not frame.measurement_version.fillna('').str.endswith('-fullweek').all():
                record.update(status='failed',reason='CSV thiếu hậu tố -fullweek')
        after=measure(primary);record['after']=after
        state_path.write_text(json.dumps(records,indent=2),encoding='utf-8')
        from fullweek_journal import append_row
        append_row(journal,f"| {datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%d/%m/%Y %H:%M')} | {job} | {elapsed:.1f}s | {before} → {after} | {record['status']}; trung bình cột CSV `{record['primary']}`; không đổi tiêu chí |")
        print(job,record['status'],round(elapsed,1),'seconds',flush=True)
        if record['status']!='passed':return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
