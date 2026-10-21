"""Kiểm thử hai môi trường một lần cho đúng hash mã; dùng lại nếu mã không đổi."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]


def source_hash():
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for name in ['agent1','agent1_service','scripts','tests','pilot'] for p in (ROOT/name).rglob('*')
        if p.suffix in {'.py','.json','.html','.ps1'}}
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()


def main():
    directory=ROOT/'outputs/implementation';marker=directory/'fullweek_code_verification.json'
    expected=source_hash()
    if marker.exists():
        previous=json.loads(marker.read_text(encoding='utf-8'))
        intact=all((ROOT/name).exists() and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
            for name,digest in previous.get('evidence_sha256',{}).items())
        if previous.get('passed') and previous.get('source_sha256')==expected and intact:
            print('same code hash; verified tests reused');return
    evidence=[]
    for name,python,xml in [('workspace',Path(sys.executable),'tests.xml'),('clean',ROOT/'.venv-check/Scripts/python.exe','tests_clean.xml')]:
        if not python.exists():raise ValueError('Thiếu môi trường kiểm tra '+name)
        with (directory/f'tests_{name}_fullweek.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(python),'-m','pytest','tests','-q',f'--junitxml=outputs/implementation/{xml}'],
                cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        evidence.append(directory/xml);print(name,'tests passed',flush=True)
    with (directory/'ruff_fatal.log').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,'-m','ruff','check','agent1','agent1_service','scripts','tests','pilot',
            '--select','E9,F63,F7,F82'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    if source_hash()!=expected:raise ValueError('Mã đổi trong khi kiểm thử; chưa đóng dấu kiểm chứng')
    marker.write_text(json.dumps(dict(passed=True,source_sha256=expected,evidence_sha256={
        p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}),indent=2),encoding='utf-8')


if __name__=='__main__':main()
