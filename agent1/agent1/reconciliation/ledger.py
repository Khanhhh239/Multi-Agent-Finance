"""Encrypted, immutable service adapter for Thắng's local decision ledger.

The upstream SQLite EventStore is deliberately not used: all commands live in
the existing encrypted tenant store. Accepting a match changes this local
subledger only; it never posts to an ERP or moves bank money.
"""
from __future__ import annotations

import json

from ._thang.data import canonical, fingerprint, iso_date
from ._thang.ledger import replay

LOCAL_ACTIONS = {'writeoff', 'reverse_writeoff'}


class DecisionLedger:
    def __init__(self, store, firm):
        self.store, self.firm = store, firm

    def events(self):
        return [row['command'] for row in self.store.get(self.firm, 't9_events')]

    def gold(self, cutoff):
        iso_date(cutoff)
        events = self.events()
        gold = replay([e for e in events if e['action'] not in LOCAL_ACTIONS], cutoff)
        written = {}
        for e in events:
            if e['available_on'] > cutoff or e['effective_on'] > cutoff:
                continue
            if e['action'] == 'writeoff':
                written[e['decision_id']] = e
            elif e['action'] == 'reverse_writeoff':
                written.pop(e['decision_id'], None)
        gold['writeoffs'] = list(written.values())
        gold['snapshot_hash'] = fingerprint(gold)
        return gold

    def cached(self, key, request_hash):
        prior = next((r for r in self.store.get(self.firm, 't9_requests')
                      if r['id'] == fingerprint(key)), None)
        if prior:
            if prior['payload_hash'] != request_hash:
                raise ValueError('Idempotency key đã dùng với nội dung khác')
            return dict(prior['result'], replayed=True)
        return None

    def transact(self, key, commands, *, request_hash=None):
        if not isinstance(key, str) or not key.strip() or not commands:
            raise ValueError('Cần idempotency_key và lệnh đối soát')
        canonical(commands)
        request_hash = request_hash or fingerprint(commands)
        request_id = fingerprint(key)
        with self.store.lock, self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            prior = next((r for r in self.store.get(self.firm, 't9_requests')
                          if r['id'] == request_id), None)
            if prior:
                if prior['payload_hash'] != request_hash:
                    raise ValueError('Idempotency key đã dùng với nội dung khác')
                return dict(prior['result'], replayed=True)
            events = self.events()
            last_day = events[-1]['available_on'] if events else '0001-01-01'
            for command in commands:
                if command['tenant_id'] != self.firm:
                    raise ValueError('Lệnh thuộc doanh nghiệp khác')
                iso_date(command['available_on']); iso_date(command['effective_on'])
                if command['available_on'] < last_day or command['effective_on'] > command['available_on']:
                    raise ValueError('Thời điểm nhận lệnh không được lùi hoặc trước ngày nghiệp vụ')
                last_day = command['available_on']
                if command['action'] == 'writeoff':
                    if not command.get('source_ref') or not command.get('reviewed_by'):
                        raise ValueError('Write-off cần nguồn và người xác nhận')
                    if type(command['amount_minor']) is not int or command['amount_minor'] <= 0:
                        raise ValueError('Write-off cần tiền nguyên dương')
                    context = command.get('invoice_context')
                    if (not isinstance(context, dict) or context.get('invoice_id') != command['invoice_id']
                            or not context.get('customer_id') or context.get('currency') != 'VND'
                            or not context.get('issue_date')):
                        raise ValueError('Write-off cần ràng buộc khách hàng và chứng từ nguồn')
                    iso_date(context['issue_date'])
            prospective = events + commands
            replay([e for e in prospective if e['action'] not in LOCAL_ACTIONS], '9999-12-31')
            result = dict(sequence=len(prospective), command_hash=fingerprint(commands), replayed=False)
            if commands[-1].get('decision_id'):
                result['decision_id'] = commands[-1]['decision_id']
            rows = [('t9_events', dict(id=f'{len(events)+i:020d}', command=c))
                    for i, c in enumerate(commands, 1)]
            rows.append(('t9_requests', dict(id=request_id, payload_hash=request_hash, result=result)))
            for kind, row in rows:
                encrypted = self.store.cipher.encrypt(json.dumps(row, ensure_ascii=False, allow_nan=False).encode())
                self.store.connection.execute('INSERT INTO records VALUES (?,?,?,?)',
                                              (self.firm, kind, row['id'], encrypted))
            self.store.connection.execute('INSERT INTO audit(firm,action,count) VALUES (?,?,?)',
                                          (self.firm, 't9:append', len(commands)))
        return result
