"""Nạp mã nguồn cục bộ và giới hạn CPU cho toàn bộ bộ kiểm thử."""
import os
import sys
from pathlib import Path
os.environ.setdefault('AGENT1_THREADS', '4')
os.environ.setdefault('OMP_NUM_THREADS', '4')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hashlib
import json

import pytest


@pytest.fixture
def bank_registry(tmp_path):
    """Create a reviewed account list outside the statement upload payload."""
    def create(accounts=('A',), evidence=b'bank account confirmation'):
        keys = tmp_path / 'bank-keys'
        keys.mkdir(exist_ok=True)
        (keys / 'confirmation.txt').write_bytes(evidence)
        registry = {'firm_id': 'F000', 'source_type': 'bank_confirmation',
                    'evidence_file': 'confirmation.txt',
                    'evidence_sha256': hashlib.sha256(evidence).hexdigest(),
                    'reviewed_by': 'test reviewer', 'reviewed_on': '2024-03-31',
                    'accounts': [{'bank': 'vcb', 'account_id': account, 'currency': 'VND'}
                                 for account in accounts]}
        path = keys / 'bank-accounts.json'
        path.write_text(json.dumps(registry), encoding='utf-8')
        return path
    return create
