"""Chạy tuần tự, có nhật ký/exit code/hash; không đánh dấu thành công khi chỉ mới khởi chạy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
JOBS={
    'A':['scripts/run_t1.py','--exp','A'],
    'point-baselines':['scripts/rescore_point_baselines.py'],
    'B':['scripts/run_t1.py','--exp','B'],
    'EF':['scripts/run_t1.py','--exp','E,F'],
    'SBA':['scripts/run_t2_t3.py','--tasks','sba,t3'],
    'T6':['scripts/run_t6.py'],
    'T9':['scripts/run_t9.py'],
    'T7':['scripts/run_t7.py'],
    'audit':['scripts/audit_synthetic.py'],
    'report':['scripts/make_report.py'],
    'T6-v5':['scripts/run_t6.py'],
    'C':['scripts/run_t1.py','--exp','C'],
    'C-v2':['scripts/sprint1/run_real_v2.py','--data','ci,bpi'],
    'P4':['scripts/sprint1/run_stationary.py'],
    'G3':['scripts/sprint1/run_g3.py'],
    'T9-source-diagnostics':['scripts/sprint1/t9_source_diagnostics.py'],
    'T9-source-policy':['scripts/sprint1/t9_source_diagnostics.py','--with-policy'],
    'seeds':['scripts/run_seed_stability.py'],
    'T4':['scripts/run_t4.py'],
    'Berka':['scripts/run_berka.py'],
    'noisy-build':['scripts/build_noisy_promises.py'],
    'noisy-EF':['scripts/run_t1.py','--exp','E','--world','src_noisy_promises'],
    'tune':['scripts/tune_t1.py','--max-train','40000','--max-valid','10000'],
    'tuned-eval':['scripts/evaluate_tuned_t1.py'],
    'onboarding':['scripts/run_onboarding_source.py'],
    'big':['scripts/build_big.py'],
    'T3':['scripts/run_t2_t3.py','--tasks','t3'],
    'T9-v4':['scripts/run_t9.py'],
    'T9-v5':['scripts/run_t9.py'],
    'E2E-full':['scripts/run_e2e.py','--protocol','source-finetune'],
    'E2E-smoke':['scripts/run_e2e.py','--protocol','source-finetune','--firms','F000','--weeks','2','--source-budget','5000'],
    'scaling':['scripts/run_scaling.py'],
    'domain-distance':['scripts/run_domain_distance.py'],
    'crisis-ablation':['scripts/eval_by_regime.py'],
    'hardcase-fidelity':['scripts/audit_hard_case_fidelity.py'],
    'T1-variants':['scripts/run_t1_variants.py'],
    'T9-T1':['scripts/run_t9_t1_propagation.py'],
    'BPI-no-due':['scripts/run_nodue_bpi.py'],
    'T8-reliability':['scripts/run_t8_reliability.py'],
    'T3-T1':['scripts/run_t3_t1.py'],
    'DA-paired':['scripts/run_da_paired.py'],
    'T9-hardcases':['scripts/run_t9_hardcases.py'],
    'T9-supply-shock':['scripts/run_t9_supply_shock.py'],
    'cash-baselines':['scripts/run_cash_baselines.py'],
    'Chronos':['scripts/run_chronos_baseline.py'],
    'cash-comparisons':['scripts/compare_cash_baselines.py'],
    'DR-build':['scripts/build_dr_comparison.py'],
    'DR-eval':['scripts/run_dr_comparison.py'],
    'regime-cash':['scripts/run_regime_cash.py'],
    'SBA-macro':['scripts/run_sba_macro.py'],
    'obligation-cases':['scripts/run_obligation_cases.py'],
    'rules-business-cases':['scripts/run_rules_business_cases.py'],
    'policy-comparisons':['scripts/compare_collection_policy.py'],
    'VN-listed':['scripts/run_vn_listed_check.py'],
    'copula-hierarchy':['scripts/run_copula_hierarchy.py'],
    'IW-oof':['scripts/run_iw_oof.py'],
    'collection-policy':['scripts/run_collection_policy.py'],
    'tests':['-m','pytest','tests','-q','--junitxml=outputs/implementation/tests.xml'],
}
DEFAULT_JOBS=['noisy-build','big','A','point-baselines','B','EF','SBA','T6','T9','T7','audit','C-v2','seeds','T4',
              'Berka','noisy-EF','T8-reliability','T3-T1','tune','tuned-eval','onboarding','domain-distance','DA-paired','DR-build','DR-eval','crisis-ablation','hardcase-fidelity','T1-variants','BPI-no-due','E2E-smoke','E2E-full','T9-T1','T9-hardcases','cash-baselines','scaling','tests','report']


def main():
    p=argparse.ArgumentParser();p.add_argument('--jobs',default=','.join(DEFAULT_JOBS));p.add_argument('--fail-fast',action='store_true');args=p.parse_args()
    if os.environ.get('AGENT1_EXPAND_LEGACY')=='1':
        raise ValueError('run_plan sinh kết quả fullweek; dùng script chẩn đoán riêng để tái lập expand legacy')
    directory=ROOT/'outputs/implementation';directory.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,AGENT1_THREADS='4',OMP_NUM_THREADS='4',PYTHONUTF8='1')
    state=directory/'run_status.json'
    records=json.loads(state.read_text(encoding='utf-8')) if state.exists() else []
    current=[]
    for name in args.jobs.split(','):
        job=JOBS[name];started=time.time()
        record=dict(job=name,command=[sys.executable,*job],started_at=started,status='running')
        hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                for base in ('agent1','agent1_service','scripts','tests','pilot')
                for path in (ROOT/base).rglob('*') if path.suffix in {'.py','.json','.html'}}
        record['source_hash']=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
        records.append(record)
        current.append(record)
        state.write_text(json.dumps(records,indent=2),encoding='utf-8')
        with (directory/f'{name}.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([sys.executable,'-u',*job],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        record.update(exit_code=result.returncode,seconds=time.time()-started,status='passed' if result.returncode==0 else 'failed')
        state.write_text(json.dumps(records,indent=2),encoding='utf-8')
        print(name,record['status'],flush=True)
        if result.returncode and args.fail_fast:break
    return 1 if any(r['status']=='failed' for r in current) else 0


if __name__=='__main__':raise SystemExit(main())
