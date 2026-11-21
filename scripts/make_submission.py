"""Build the source-code zip to submit to the organisers.

  python scripts/make_submission.py                 # code from HEAD + Agent 3 legal corpus
  python scripts/make_submission.py --include-env   # also the root .env (API keys)
  python scripts/make_submission.py --ref origin/deploy --out dist/SoSon.zip

The zip holds only files tracked by git at --ref (no .venv, node_modules, runtime state or local
secrets), minus the 1.1 GB Agent 4 warehouse kept in Git LFS: on the organisers' machine
data_pipeline/setup_runtime.py regenerates that warehouse from code. Data that cannot be regenerated
offline (the Agent 3 legal corpus) is added under assets/ and installed by scripts/install_assets.py.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAW_DB = ROOT / 'agent3' / 'agent3_tax_compliance' / 'data' / 'lawbase' / 'legal_corpus.sqlite3'
LFS_WAREHOUSE = 'portal/workspace/datasets/enterprise-x10-v3-candidate02/warehouse.duckdb.zlib'
ENV_FILES = ('.env',)


def git(*args: str, **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE='1')
    return subprocess.run(['git', '-c', 'filter.lfs.smudge=', '-c', 'filter.lfs.process=',
                           '-c', 'filter.lfs.required=false', *args],
                          cwd=ROOT, env=env, check=True, **kw)


def law_db_gz(tmp: Path) -> Path:
    """Consistent copy of the legal corpus (SQLite backup API), gzip-compressed."""
    snap = tmp / 'legal_corpus.sqlite3'
    src = sqlite3.connect(f'file:{LAW_DB.as_posix()}?mode=ro', uri=True)
    dst = sqlite3.connect(snap)
    src.backup(dst)
    dst.execute('VACUUM')
    if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('legal_corpus.sqlite3 không qua được integrity_check.')
    dst.close()
    src.close()
    gz = tmp / 'legal_corpus.sqlite3.gz'
    with snap.open('rb') as f, gzip.open(gz, 'wb', compresslevel=9) as g:
        shutil.copyfileobj(f, g, 1 << 20)
    return gz


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ref', default='HEAD', help='git ref to package (default HEAD)')
    ap.add_argument('--out', default='dist/SoSon_source.zip')
    ap.add_argument('--prefix', default='SoSon', help='top-level folder inside the zip')
    ap.add_argument('--include-env', action='store_true', help='add the root .env (API keys)')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if a.ref == 'HEAD':
        dirty = git('status', '--porcelain', '--untracked-files=no', capture_output=True, text=True).stdout.strip()
        if dirty:
            print('[warn] Có thay đổi chưa commit; zip chỉ chứa nội dung đã commit ở HEAD:\n' + dirty, flush=True)
    if not LAW_DB.is_file():
        raise SystemExit(f'Không thấy {LAW_DB.relative_to(ROOT)}; cần kho luật Agent 3 trên máy này để đóng gói.')
    if a.include_env:
        missing = [p for p in ENV_FILES if not (ROOT / p).is_file()]
        if missing:
            raise SystemExit('Thiếu ' + ', '.join(missing) + ' (cần cho --include-env).')

    out = (ROOT / a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    prefix = a.prefix.strip('/') + '/'
    git('archive', '--format=zip', f'--prefix={prefix}', '-o', str(out), a.ref, '--', '.', f':(exclude){LFS_WAREHOUSE}')

    with tempfile.TemporaryDirectory() as t:
        gz = law_db_gz(Path(t))
        digest = hashlib.sha256(gz.read_bytes()).hexdigest()
        with zipfile.ZipFile(out, 'a', compression=zipfile.ZIP_STORED) as z:
            z.write(gz, prefix + 'assets/agent3/legal_corpus.sqlite3.gz')
            z.writestr(prefix + 'assets/agent3/legal_corpus.sqlite3.gz.sha256', f'{digest}  legal_corpus.sqlite3.gz\n')
            if a.include_env:
                for p in ENV_FILES:
                    z.write(ROOT / p, prefix + p, compress_type=zipfile.ZIP_DEFLATED)

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    commit = git('rev-parse', '--short', a.ref, capture_output=True, text=True).stdout.strip()
    print(f'[ok] {out}  ({out.stat().st_size / (1 << 20):.1f} MB, {len(names)} mục, commit {commit})')
    print('     Có API key (.env): ' + ('CÓ' if a.include_env else 'KHÔNG — Agent 3/4 sẽ offline nếu BTC không tự thêm .env'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
