"""Install the data files that ship next to the source code instead of in git.

The submission zip (built by scripts/make_submission.py) carries them under assets/:
  assets/agent3/legal_corpus.sqlite3.gz         Agent 3 legal corpus (40 Vietnamese VAT documents)
  assets/agent3/legal_corpus.sqlite3.gz.sha256  its checksum

Safe to run on every start: files that are already installed are left alone.
Exit code is 0 even when an asset is missing, so the platform still starts; the message says what is affected.
"""
from __future__ import annotations

import gzip
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAW_DB = ROOT / 'agent3' / 'agent3_tax_compliance' / 'data' / 'lawbase' / 'legal_corpus.sqlite3'
LAW_GZ = ROOT / 'assets' / 'agent3' / 'legal_corpus.sqlite3.gz'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def install_law_db() -> bool:
    if LAW_DB.is_file() and LAW_DB.stat().st_size > 0:
        print('[assets] Kho luật Agent 3 đã có sẵn.', flush=True)
        return True
    if not LAW_GZ.is_file():
        print('[assets] CẢNH BÁO: thiếu assets/agent3/legal_corpus.sqlite3.gz. Agent 3 vẫn chạy nhưng '
              'không trả lời được câu hỏi điều khoản luật. Có thể tự tải lại từ vbpl.vn bằng: '
              'cd agent3/agent3_tax_compliance; ..\\.venv\\Scripts\\python.exe -m src.lawbase.cli sync', flush=True)
        return False
    expected_file = LAW_GZ.with_name(LAW_GZ.name + '.sha256')
    if expected_file.is_file():
        expected = expected_file.read_text(encoding='utf-8').split()[0].strip().lower()
        if sha256(LAW_GZ) != expected:
            print('[assets] LỖI: legal_corpus.sqlite3.gz bị hỏng (sai SHA-256). Hãy giải nén lại file zip nộp.', flush=True)
            return False
    LAW_DB.parent.mkdir(parents=True, exist_ok=True)
    tmp = LAW_DB.with_suffix('.sqlite3.tmp')
    with gzip.open(LAW_GZ, 'rb') as src, tmp.open('wb') as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    tmp.replace(LAW_DB)
    print(f'[assets] Đã cài kho luật Agent 3 ({LAW_DB.stat().st_size // (1 << 20)} MB).', flush=True)
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    install_law_db()
    return 0


if __name__ == '__main__':
    sys.exit(main())
