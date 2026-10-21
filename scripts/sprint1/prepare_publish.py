"""Đồng bộ file được phép vào clone riêng; không stage/commit/push, mặc định chỉ kiểm kê."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[2]
ALLOWED={'.py','.ps1','.md','.json','.csv','.yaml','.yml','.html','.js','.css','.toml','.png','.jpg','.svg','.xml'}
EXCLUDED={'__pycache__','.pytest_cache','.ruff_cache','.state','.state-ui-check','raw','interim','processed',
    '.git','.venv','.venv-check','.publish-repo','node_modules','dr_comparison_v1'}


def candidates():
    for root in ['agent1','agent1_service','scripts','tests','pilot','docs','outputs','data/synthetic']:
        directory=ROOT/root
        if not directory.exists():continue
        for current,folders,files in os.walk(directory):
            folders[:]=[folder for folder in folders if folder not in EXCLUDED]
            for name in files:
                path=Path(current)/name;relative=path.relative_to(ROOT)
                if relative.as_posix()=='outputs/implementation/publish_manifest.json':continue
                if name in {'publish_status.json','fullweek_wait.json','fullweek_workers.json'}:continue
                if '.in_progress' in name or '.ready.' in name:continue
                if path.suffix not in ALLOWED:continue
                if root=='data/synthetic' and path.suffix!='.json':continue
                if path.suffix=='.xml' and not (root=='tests' or (relative.parent.as_posix()=='outputs/implementation' and name in ['tests.xml','tests_clean.xml'])):continue
                if relative.parts[:2]==('outputs','service') and path.suffix in {'.png','.jpg'}:continue
                if path.stat().st_size>20*1024**2:raise ValueError('Cần kiểm tra file lớn trước publish: '+str(relative))
                yield path
    for name in ['.gitignore','.dockerignore','Dockerfile','compose.yaml','README.md',
        'requirements.txt','requirements-lock.txt','requirements-forecast.txt','requirements-service.txt']:
        if (ROOT/name).exists():yield ROOT/name


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--copy',action='store_true');args=parser.parse_args()
    destination=ROOT/'.publish-repo'
    if not (destination/'.git').is_dir():raise ValueError('Thiếu clone riêng đúng remote')
    records=[]
    for path in candidates():
        relative=path.relative_to(ROOT)
        if path.suffix in {'.db','.key','.parquet','.dat'} or any(part.startswith('.state') for part in relative.parts):
            raise ValueError('File không được phép publish')
        if args.copy:
            output=destination/relative;output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,output)
        records.append(dict(path=relative.as_posix(),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest=dict(copied=args.copy,n_files=len(records),total_bytes=sum(r['bytes'] for r in records),files=records)
    manifest_path=ROOT/'outputs/implementation/publish_manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if args.copy:shutil.copyfile(manifest_path,destination/'outputs/implementation/publish_manifest.json')
    print('publish inventory',len(records),'files;',manifest['total_bytes'],'bytes; copied=',args.copy)


if __name__=='__main__':main()
