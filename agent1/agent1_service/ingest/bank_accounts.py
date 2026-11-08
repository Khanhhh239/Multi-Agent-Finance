"""Operator approved bank account scope, separate from statement uploads."""
import hashlib
import os
from pathlib import Path

from .bank_statement import _day
from .money import SCALES
from .strict_files import loads_json


def registry_path(state_dir, key_dir=None):
    state = Path(state_dir).resolve()
    keys = Path(key_dir or os.environ.get('AGENT1_KEY_DIR') or
                state.parent / (state.name + '-keys')).resolve()
    return Path(os.environ.get('AGENT1_BANK_ACCOUNTS_FILE') or
                keys / 'bank-accounts.json').resolve()


def load_account_registry(path, firm_id):
    """Require a reviewed account list backed by a separate local source file."""
    path = Path(path)
    if not path.is_file():
        raise ValueError('Chưa có danh mục tài khoản ngân hàng được duyệt')
    raw = path.read_bytes()
    registry = loads_json(raw)
    if not isinstance(registry, dict) or registry.get('firm_id') != firm_id:
        raise ValueError('Danh mục tài khoản không thuộc doanh nghiệp này')
    if registry.get('source_type') not in {'bank_confirmation', 'bank_portal_export'}:
        raise ValueError('Danh mục phải lấy từ xác nhận hoặc bản xuất của ngân hàng')
    if not isinstance(registry.get('reviewed_by'), str) or not registry['reviewed_by'].strip():
        raise ValueError('Danh mục thiếu người kiểm duyệt')
    _day(registry.get('reviewed_on'), 'reviewed_on')
    evidence_name = registry.get('evidence_file')
    digest = registry.get('evidence_sha256')
    if not isinstance(evidence_name, str) or not evidence_name.strip() or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError('Danh mục thiếu file bằng chứng hoặc SHA-256')
    evidence = (path.parent / evidence_name).resolve()
    if not evidence.is_file() or hashlib.sha256(evidence.read_bytes()).hexdigest() != digest.lower():
        raise ValueError('File bằng chứng danh mục tài khoản thiếu hoặc sai SHA-256')
    accounts = registry.get('accounts')
    if not isinstance(accounts, list) or not accounts:
        raise ValueError('Danh mục tài khoản trống')
    by_id = {}
    for row in accounts:
        if not isinstance(row, dict):
            raise ValueError('Tài khoản trong danh mục không hợp lệ')
        account = row.get('account_id')
        bank = row.get('bank')
        currency = row.get('currency')
        if (not isinstance(account, str) or not account or account != account.strip()
                or bank not in {'vcb', 'bidv', 'tcb', 'mb', 'acb'}
                or currency not in SCALES or account in by_id):
            raise ValueError('Tài khoản trùng, sai ngân hàng hoặc tiền tệ trong danh mục')
        by_id[account] = {'bank': bank, 'currency': currency}
    return {'accounts': by_id, 'registry_sha256': hashlib.sha256(raw).hexdigest(),
            'evidence_sha256': digest.lower(), 'reviewed_by': registry['reviewed_by'],
            'reviewed_on': registry['reviewed_on']}
