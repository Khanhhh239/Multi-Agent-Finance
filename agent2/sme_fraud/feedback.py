"""Append human case decisions to a local audit log; no automatic recalibration."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .generate import write_csv
from .case_identity import load_lineage, resolve, scope_hash, feedback_view
from .review_decision_gate import check_decision

DECISIONS = {'confirmed_suspicion', 'confirmed_fraud', 'non_compliance', 'false_positive', 'information_gap'}


@contextmanager
def feedback_lock(directory, timeout=10):
    """Shared lock for CLI/web readers and writers, including other processes."""
    directory = Path(directory)
    with (directory / '.feedback.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Feedback log is busy; retry shortly')
                time.sleep(.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def event_hash(event):
    return hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_audit(path):
    previous, events = '', []
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                event = json.loads(line)
                digest = event.pop('event_hash')
                if event['previous_hash'] != previous or event_hash(event) != digest:
                    raise ValueError('Feedback audit hash chain is invalid')
                event['event_hash'] = digest
                events.append(event)
                previous = digest
    return events


def record_feedback(directory, case_id, decision, reviewer, reason, reviewed_at=None, *, expected_hash=None, database=None):
    directory = Path(directory)
    with feedback_lock(directory):
        return _record_feedback(directory, case_id, decision, reviewer, reason, reviewed_at,
                                expected_hash=expected_hash,expected_database=database)


def _record_feedback(directory, case_id, decision, reviewer, reason, reviewed_at, *, expected_hash=None,expected_database=None):
    if (decision not in DECISIONS or not isinstance(reviewer,str) or not isinstance(reason,str) or
            not reviewer.strip() or not reason.strip() or len(reviewer)>100 or len(reason)>2000):
        raise ValueError('Valid decision, reviewer (1–100 characters) and reason (1–2000 characters) are required')
    with (directory / 'case_queue.csv').open(encoding='utf-8-sig', newline='') as stream:
        cases = {r['case_id']: r for r in csv.DictReader(stream)}
    lineage = load_lineage(directory)
    case_id = resolve(case_id, lineage['aliases'])
    if case_id not in cases:
        raise ValueError('Unknown case ID')
    audit_path = directory / 'feedback_audit.jsonl'
    events = read_audit(audit_path)
    latest,_=feedback_view(events,lineage['current'] or cases,lineage)
    actual=latest.get(case_id,{}).get('event_hash','')
    if expected_hash is not None and expected_hash!=actual:
        raise RuntimeError('Hồ sơ vừa có kết luận mới. Tải lại hồ sơ trước khi lưu.')
    workflow_reference=check_decision(directory,lineage['current'].get(case_id,cases[case_id]),decision,
                                      expected_database=expected_database,reviewer=reviewer.strip())
    stamp = reviewed_at or datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')
    when = datetime.fromisoformat(stamp)
    if when.tzinfo is None or when < datetime.fromisoformat(cases[case_id]['last_seen_at']):
        raise ValueError('Review time must have timezone and follow the case snapshot')
    if events and when < datetime.fromisoformat(events[-1]['reviewed_at']):
        raise ValueError('Review timestamps must be nondecreasing')
    event = dict(case_id=case_id, decision=decision, reviewer=reviewer.strip(), reason=reason.strip(),
                 reviewed_at=stamp, previous_hash=events[-1]['event_hash'] if events else '',
                 case_scope_hash=scope_hash(lineage['current'].get(case_id, cases[case_id])))
    if workflow_reference:event['workflow_approval_id']=workflow_reference
    event['event_hash'] = event_hash(event)
    with audit_path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    events.append(event)
    write_review_states(directory, cases, events, lineage)
    return event


def write_review_states(directory, cases, events, lineage):
    """Refresh the derived CSV after either feedback or an identity migration."""
    latest, _ = feedback_view(events, lineage['current'] or cases, lineage)
    states = []
    for key, case in cases.items():
        feedback = latest.get(key)
        states.append(dict(case_id=key, status='awaiting_information' if feedback and feedback['decision'] == 'information_gap'
                           else 'closed' if feedback else 'new',
                           decision=feedback['decision'] if feedback else '',
                           reviewer=feedback['reviewer'] if feedback else '',
                           reason=feedback['reason'] if feedback else '', reviewed_at=feedback['reviewed_at'] if feedback else ''))
    with tempfile.NamedTemporaryFile(dir=directory, suffix='.csv', delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        write_csv(temporary_path, states)
        temporary_path.replace(directory / 'case_review_states.csv')
    finally:
        temporary_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--decision', choices=sorted(DECISIONS), required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--reason', required=True)
    parser.add_argument('--reviewed-at')
    parser.add_argument('--expected-hash',help='Phiên bản kết luận đã đọc; dùng chuỗi rỗng cho lần đầu')
    parser.add_argument('--database',type=Path,help='Nếu khai báo, phải trùng SQLite đã gắn với thư mục hồ sơ')
    args = parser.parse_args()
    print(json.dumps(record_feedback(args.report, args.case_id, args.decision, args.reviewer, args.reason, args.reviewed_at,
                                    expected_hash=args.expected_hash,database=args.database), ensure_ascii=True))


if __name__ == '__main__':
    main()
