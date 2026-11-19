"""Re-uploading bytes that Agent 2 already saved as an immutable snapshot must read as "already recorded", not as an error."""
import csv
import io

import pytest

import agent2_intake


def _csv(rows=2):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['transaction_id', 'txn_type', 'payment_channel', 'amount_vnd', 'posted_at', 'created_at', 'approved_at',
                'business_purpose', 'accounting_purpose', 'vendor_id', 'employee_id', 'creator_id'])
    for i in range(rows):
        w.writerow([f'TX{i}', 'vendor_payment', 'bank', 1000000 + i, '2026-10-01 09:00:00', '2026-10-01 09:00:00',
                    '2026-10-01 09:00:00', 'chi phi', 'chi phi', 'V1', 'E1', 'E2'])
    return out.getvalue().encode('utf-8')


COMMITTED = {'error': '{"status": "rejected", "errors": [{"code": "IMPORT_COMMITTED", "message": "Lần nhập đã tạo snapshot bất biến."}]}'}


def _preview(call):
    return agent2_intake.preview(call, lambda p: 'http://x' + p, 'tok', 'demo', 'MPX10', 'Minh Phát', 'giao_dich.csv', _csv())


def test_committed_upload_is_reported_as_already_committed():
    with pytest.raises(agent2_intake.AlreadyCommitted):
        _preview(lambda *a, **k: (409, COMMITTED))


def test_committed_preview_is_reported_as_already_committed():
    answers = iter([(200, {'import_id': 'imp', 'revision': 1}), (409, COMMITTED)])
    with pytest.raises(agent2_intake.AlreadyCommitted):
        _preview(lambda *a, **k: next(answers))


def test_other_failures_stay_errors():
    with pytest.raises(agent2_intake.IntakeError) as caught:
        _preview(lambda *a, **k: (500, {'error': 'boom'}))
    assert not isinstance(caught.value, agent2_intake.AlreadyCommitted)
