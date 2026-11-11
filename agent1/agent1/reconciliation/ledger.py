"""Encrypted, immutable service adapter for Thắng's local decision ledger.

The upstream SQLite EventStore is deliberately not used: all commands live in
the existing encrypted tenant store. Accepting a match changes this local
subledger only; it never posts to an ERP or moves bank money.
"""
from __future__ import annotations

import json
from copy import deepcopy

from ._thang.data import canonical, fingerprint, iso_date
from ._thang.ledger import replay

LOCAL_ACTIONS = {'writeoff', 'reverse_writeoff', 'correct_source'}


class DecisionLedger:
    def __init__(self, store, firm, prefix=''):
        self.store, self.firm, self.prefix = store, firm, prefix

    def events(self):
        return [row['command'] for row in self.store.get(self.firm, self.prefix + 't9_events')]

    def gold(self, cutoff, *, until_sequence=None):
        iso_date(cutoff)
        events = self.events()
        if until_sequence is not None:
            events = events[:until_sequence]
        return self._gold(events, cutoff)

    def _gold(self, events, cutoff):
        """Replay source revisions without mutating the immutable event history.

        A correction may release endpoints only after all touching decisions
        have been reversed. A checkpoint rebuilds the remaining active state
        through the upstream validator; corrected bank cash replaces its old
        version once. Earlier cutoffs still replay the original commands.
        """
        projected, archived, corrections = [], {}, []
        for command in events:
            if command['available_on'] > cutoff or command['effective_on'] > cutoff:
                continue
            if command['action'] != 'correct_source':
                if command['action'] not in LOCAL_ACTIONS:
                    projected.append(command)
                continue
            if self.prefix != 'company_' or command['tenant_id'] != self.firm:
                raise ValueError('Sửa nguồn chỉ áp dụng cho ledger Workspace của doanh nghiệp hiện tại')
            if not command.get('reviewed_by', '').strip() or not command.get('note', '').strip():
                raise ValueError('Sửa nguồn cần người xác nhận và lý do')
            reset_i, reset_p = set(command['reset_invoices']), set(command['reset_payments'])
            state = replay(projected, cutoff)
            active = [d for d in state['decisions'] if d['status'] == 'committed']
            if any(a['invoice_id'] in reset_i or a['payment_id'] in reset_p for d in active for a in d['allocations']):
                raise ValueError('Cần đảo tất cả phân bổ bị ảnh hưởng trước khi sửa nguồn')
            if any(d['status'] not in ('committed', 'reversed', 'cancelled') for d in state['decisions']):
                raise ValueError('Cần giải quyết quyết định đang chờ trước khi sửa nguồn')
            corrections.append(command)
            if not reset_i and not reset_p and not command['banks']:
                continue
            for d in state['decisions']:
                if d['status'] != 'committed':
                    archived[d['decision_id']] = d
            docs = {}
            for event in projected:
                if event['action'] in ('record', 'revise'):
                    docs[event['kind'], event['data']['id']] = deepcopy(event)
            if any(kind not in {'invoice', 'payment', 'bank', 'bank_link'} for kind, _ in docs):
                raise ValueError('Ledger này có chứng từ chưa hỗ trợ sửa nguồn')
            docs = {key: e for key, e in docs.items()
                    if not (key[0] == 'invoice' and key[1] in reset_i
                            or key[0] == 'payment' and key[1] in reset_p
                            or key[0] == 'bank_link' and e['data']['payment_id'] in reset_p)}
            for bank in command['banks']:
                if bank['id'] not in reset_p or bank['tenant_id'] != self.firm:
                    raise ValueError('Phạm vi sửa sao kê không hợp lệ')
                if ('bank', bank['id']) in docs:
                    docs['bank', bank['id']] = dict(tenant_id=self.firm, action='record', kind='bank',
                        data={k:v for k,v in bank.items() if k != 'effective_on'}, effective_on=bank['effective_on'])
            projected = []
            for kind in ('invoice', 'payment', 'bank', 'bank_link'):
                for (record_kind, _), event in sorted(docs.items()):
                    if record_kind == kind:
                        projected.append(dict(event, action='record', available_on=command['available_on']))
            for d in active:
                base = dict(tenant_id=self.firm, decision_id=d['decision_id'],
                            effective_on=command['effective_on'], available_on=command['available_on'])
                projected.extend([dict(base, action='suggest', allocations=d['allocations']),
                                  dict(base, action='approve'), dict(base, action='commit', external_result='verified')])
        if corrections:
            gold = replay(projected, cutoff)
            current = {d['decision_id']: d for d in gold['decisions']}
            gold['decisions'] = [d for _, d in sorted({**archived, **current}.items())]
            gold['lineage'] = [dict(sequence=n, command_hash=fingerprint(e)) for n, e in enumerate(events, 1)
                               if e['available_on'] <= cutoff and e['effective_on'] <= cutoff]
            gold['source_corrections'] = [dict(id=e['correction_id'], available_on=e['available_on'],
                                              reviewed_by=e['reviewed_by'], note=e['note']) for e in corrections]
        else:
            gold = replay([e for e in events if e['action'] not in LOCAL_ACTIONS], cutoff)
        if self.prefix == 'company_':
            banks = {e['data']['id']: dict(e['data'], effective_on=e['effective_on'], available_on=e['available_on'])
                     for e in projected if e['action'] == 'record' and e.get('kind') == 'bank'}
            gold['banks'] = list(banks.values())
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
        prior = next((r for r in self.store.get(self.firm, self.prefix + 't9_requests')
                      if r['id'] == fingerprint(key)), None)
        if prior:
            if prior['payload_hash'] != request_hash:
                raise ValueError('Idempotency key đã dùng với nội dung khác')
            return dict(prior['result'], replayed=True)
        return None

    def transact(self, key, commands, *, request_hash=None, batches=None, result_fields=None):
        if not isinstance(key, str) or not key.strip() or not (commands or batches):
            raise ValueError('Cần idempotency_key và lệnh đối soát')
        canonical(commands)
        request_hash = request_hash or fingerprint(commands)
        request_id = fingerprint(key)
        with self.store.lock, self.store.connection:
            self.store.connection.execute('BEGIN IMMEDIATE')
            prior = next((r for r in self.store.get(self.firm, self.prefix + 't9_requests')
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
            self._gold(prospective, '9999-12-31')
            result = dict(result_fields or {}, sequence=len(prospective), command_hash=fingerprint(commands), replayed=False)
            if commands and commands[-1].get('decision_id'):
                result['decision_id'] = commands[-1]['decision_id']
            rows = [(self.prefix + 't9_events', dict(id=f'{len(events)+i:020d}', command=c))
                    for i, c in enumerate(commands, 1)]
            rows.append((self.prefix + 't9_requests', dict(id=request_id, payload_hash=request_hash, result=result)))
            for kind, row in rows:
                encrypted = self.store.cipher.encrypt(json.dumps(row, ensure_ascii=False, allow_nan=False).encode())
                self.store.connection.execute('INSERT INTO records VALUES (?,?,?,?)',
                                              (self.firm, kind, row['id'], encrypted))
            # Dataset, review state and accepted events become visible together.
            for kind, records in (batches or {}).items():
                for row in records:
                    encrypted = self.store.cipher.encrypt(json.dumps(row, ensure_ascii=False, allow_nan=False).encode())
                    self.store.connection.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?)',
                                                  (self.firm, kind, str(row['id']), encrypted))
            self.store.connection.execute('INSERT INTO audit(firm,action,count) VALUES (?,?,?)',
                                          (self.firm, 't9:append', len(commands)))
        return result
