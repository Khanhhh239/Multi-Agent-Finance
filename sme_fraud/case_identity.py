"""Canonical case scopes and conservative, auditable snapshot lineage.

The feedback hash chain is never rewritten. Aliases only connect equivalent
one-to-one scopes; split/merge/changed scopes retain history without inheriting
a conclusion. The sidecar is guarded by the current queue file checksum.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime

IDENTITY_VERSION = 'component-members-v1'
LINEAGE_FILE = 'case_identity.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def values(value, *, pipe=False):
    if isinstance(value, str):
        value = value.split('|') if pipe else json.loads(value or '[]')
    return sorted(set(value or []))


def component_key(company, members):
    return 'cluster:' + digest([IDENTITY_VERSION, company, sorted(set(members))])[:24]


def scope(case, *, cluster=True):
    result = {key: case.get(key, '') for key in ('company_id', 'opened_at', 'last_seen_at',
              'source_scope', 'source_status', 'priority', 'evidence_digest')}
    result.update(case_type=case.get('case_type') or 'transaction',
                  transaction_ids=values(case.get('transaction_ids')),
                  rule_ids=values(case.get('rule_ids'), pipe=True),
                  batch_event_ids=values(case.get('batch_event_ids')),
                  max_score=int(case.get('max_score', 0)))
    if cluster:
        result['cluster_members'] = values(case.get('cluster_members'))
    return result


def scope_hash(case):
    return digest(scope(case))


def equivalent(old, new):
    if scope(old, cluster=False) != scope(new, cluster=False):
        return False
    # Legacy root-based cases have no member list. Exact transaction/evidence
    # scope must still match; new versions also require exact graph membership.
    return (not old.get('identity_version') or
            values(old.get('cluster_members')) == values(new.get('cluster_members')))


def queue_hash(directory):
    return hashlib.sha256((Path(directory) / 'case_queue.csv').read_bytes()).hexdigest()


def load_lineage(directory, *, allow_stale=False):
    path = Path(directory) / LINEAGE_FILE
    if not path.exists():
        return dict(version=1, current={}, aliases={}, scope_aliases={}, legacy_bindings={}, archives={}, relations=[])
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('version') != 1:
        raise ValueError('Unsupported case identity mapping version')
    if not allow_stale and state.get('queue_sha256') != queue_hash(directory):
        raise ValueError('Case snapshot changed; prepare the review store before saving feedback')
    return state


def write_lineage(directory, state):
    directory = Path(directory)
    with tempfile.NamedTemporaryFile(dir=directory, suffix='.json', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write((json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(directory / LINEAGE_FILE)
    finally:
        temporary.unlink(missing_ok=True)


def resolve(identity, aliases):
    seen = set()
    while identity in aliases:
        if identity in seen:
            raise ValueError('Cyclic case identity mapping')
        seen.add(identity)
        identity = aliases[identity]
    return identity


def feedback_view(events, cases, lineage):
    latest, view = {}, []
    for event in events:
        target = resolve(event['case_id'], lineage['aliases'])
        binding = event.get('case_scope_hash') or lineage['legacy_bindings'].get(event['event_hash'], '')
        binding = resolve(binding, lineage['scope_aliases'])
        applies = target in cases and bool(binding) and binding == scope_hash(cases[target])
        if applies:
            latest[target] = event
        view.append(dict(event, resolved_case_id=target, applies_to_current_scope=applies))
    return latest, view


def plan_lineage(previous, current, state, events, fingerprint):
    """Called under the feedback lock after validating the entire new snapshot."""
    state = json.loads(json.dumps(state))
    old = {c['case_id']: c for c in previous}
    new = {c['case_id']: c for c in current}
    if len(new) != len(current):
        raise ValueError('Duplicate case ID in review snapshot')
    candidates, reverse, by_scope = {}, {}, {}
    for new_id, after in new.items():
        by_scope.setdefault(digest(scope(after, cluster=False)), []).append(new_id)
    for old_id, before in old.items():
        for new_id in by_scope.get(digest(scope(before, cluster=False)), []):
            after = new[new_id]
            if equivalent(before, after):
                candidates.setdefault(old_id, []).append(new_id)
                reverse.setdefault(new_id, []).append(old_id)
    pairs = [(a, targets[0]) for a, targets in candidates.items()
             if len(targets) == 1 and len(reverse[targets[0]]) == 1]
    for new_id in new:
        state['aliases'].pop(new_id, None)
    for after in new.values():
        state['scope_aliases'].pop(scope_hash(after), None)
    for identity, case in old.items():
        state['archives'][identity + '|' + scope_hash(case)] = case
    # Bind legacy events only to an actual cached, reviewed snapshot, never to
    # a guessed vendor/root or an arbitrary successor after a split.
    for event in events:
        if not event.get('case_scope_hash') and event['event_hash'] not in state['legacy_bindings']:
            before = old.get(event['case_id'])
            if before and datetime.fromisoformat(event['reviewed_at']) >= datetime.fromisoformat(before['last_seen_at']):
                state['legacy_bindings'][event['event_hash']] = scope_hash(before)
    for old_id, new_id in pairs:
        before, after = old[old_id], new[new_id]
        if old_id != new_id:
            state['aliases'][old_id] = new_id
        left, right = scope_hash(before), scope_hash(after)
        if left != right:
            state['scope_aliases'][left] = right
        after['owner_id'] = before.get('owner_id', after.get('owner_id', ''))
    # Relations describe actual membership overlap, but do not convey rights or
    # conclusions. Keep old summaries available even when a case disappears.
    overlaps, member_index, source_index = {}, {}, {}
    for new_id, after in new.items():
        for tid in values(after.get('transaction_ids')):
            member_index.setdefault((after['company_id'], tid), set()).add(new_id)
        if after.get('case_type') == 'source':
            key = after['company_id'], after.get('source_scope'), tuple(values(after.get('rule_ids'), pipe=True))
            source_index.setdefault(key, set()).add(new_id)
    for old_id, before in old.items():
        targets = set()
        for tid in values(before.get('transaction_ids')):
            targets.update(member_index.get((before['company_id'], tid), ()))
        if before.get('case_type') == 'source':
            key = before['company_id'], before.get('source_scope'), tuple(values(before.get('rule_ids'), pipe=True))
            targets.update(source_index.get(key, ()))
        overlaps[old_id] = sorted(targets)
    incoming = {}
    for targets in overlaps.values():
        for target in targets:
            incoming[target] = incoming.get(target, 0) + 1
    relations = {digest(r): r for r in state['relations']}
    for old_id, before in old.items():
        targets = overlaps.get(old_id, [])
        for new_id in targets or ['']:
            kind = ('equivalent' if (old_id, new_id) in pairs else
                    'split_merge' if len(targets) > 1 and incoming[new_id] > 1 else
                    'split' if len(targets) > 1 else 'merged' if incoming.get(new_id, 0) > 1 else
                    'changed' if new_id else 'retired')
            if old_id == new_id and kind == 'equivalent' and scope_hash(before) == scope_hash(new[new_id]):
                continue
            item = dict(old_case_id=old_id, new_case_id=new_id, relation=kind,
                        old_scope_hash=scope_hash(before), new_scope_hash=scope_hash(new[new_id]) if new_id else '')
            relations[digest(item)] = item
    state.update(queue_sha256=fingerprint, current=new,
                 relations=sorted(relations.values(), key=lambda r: (r['old_case_id'], r['new_case_id'], r['old_scope_hash'])))
    for identity in state['aliases']:
        resolve(identity, state['aliases'])
    return state, pairs
