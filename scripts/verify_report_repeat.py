"""Chạy lại bộ sinh báo cáo hai lần, đối chiếu hash; không thay kiểm tái lập huấn luyện."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]


def fingerprints(paths):
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}


def main():
    paths=[ROOT/p for p in ['docs/RESULTS_TABLES.md','docs/03_Evaluation/04_ket_qua_hien_co.md',
        'docs/03_Evaluation/GATES_CURRENT.md','docs/03_Evaluation/KET_QUA_CHUA_DAT.md',
        'docs/05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md','outputs/implementation/work_packages.csv',
        'outputs/implementation/gates.csv','outputs/t1/DA_hypotheses.csv']]
    command=[sys.executable,str(ROOT/'scripts/make_report.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    inputs=list((ROOT/'outputs').rglob('*.csv'))
    before_inputs=fingerprints(inputs);first=fingerprints(paths)
    subprocess.run(command,cwd=ROOT,check=True)
    second=fingerprints(paths);after_inputs=fingerprints(list((ROOT/'outputs').rglob('*.csv')))
    result=dict(passed=first==second and before_inputs==after_inputs,report_sha256=second,
        stable_inputs=before_inputs==after_inputs,checked_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='report generation only; does not establish experimental retraining reproducibility')
    (ROOT/'outputs/implementation/report_reproducibility.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('report_repeat',result['passed'])
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
