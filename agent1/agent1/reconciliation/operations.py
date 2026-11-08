"""Reviewable local commands; no ERP writes and no client-supplied knowledge date."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from ._thang.data import fingerprint
from .pipeline import NON_AR, day, invoice_context, money, today


def propose(source, cutoff):
    cutoff = day(cutoff)
    if cutoff > today():
        raise ValueError('Không đối soát snapshot tương lai')
    with source.store.lock:
        result = source.propose(cutoff)
        result.update(created_on=today(), ledger_sequence=len(source.ledger.events()))
        result['id'] = fingerprint(result)[:32]
        source.store.put(source.firm, 't9_proposals', [result])
    return result


def accept(source, key, actor, *, proposal_id=None, allocations=None, note=''):
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError('Cần tên người xác nhận')
    if bool(proposal_id) == bool(allocations):
        raise ValueError('Chọn một đề xuất hoặc cung cấp phân bổ thủ công')
    request_hash = fingerprint(dict(action='accept', actor=actor, proposal_id=proposal_id,
                                    allocations=allocations, note=note))
    with source.store.lock:
        cached = source.ledger.cached(key, request_hash)
        if cached:
            return cached
        now = today()
        view = source.view(now)
        if proposal_id:
            proposal = next((r for r in source.store.get(source.firm, 't9_proposals') if r['id'] == proposal_id), None)
            if proposal is None:
                raise ValueError('Không tìm thấy đề xuất của doanh nghiệp')
            if proposal['cutoff'] != now:
                raise ValueError('Cần chạy lại đề xuất tại ngày hiện tại trước khi xác nhận')
            if proposal['ledger_sequence'] != len(source.ledger.events()) or (
                source.view(proposal['cutoff'])['snapshot_hash'] != proposal['snapshot_hash']):
                raise ValueError('Đề xuất đã cũ; cần chạy đối soát lại')
            allocations = [dict(txn_id=a['payment_id'], invoice_id=a['invoice_id'], amount_minor=a['amount_minor'])
                           for a in proposal['allocations']]
            if not allocations:
                raise ValueError('Đề xuất không có phân bổ xác định được')
        elif not isinstance(note, str) or not note.strip():
            raise ValueError('Phân bổ thủ công cần ghi nguồn bằng chứng trong ghi chú')
        invoices = view['invoices'].set_index('invoice_id').to_dict('index') if len(view['invoices']) else {}
        banks = {r['txn_id']: r for r in view['bank']}
        by_i, by_p, parties, seen = Counter(), Counter(), {}, set()
        for a in allocations:
            iid, tid, amount = a['invoice_id'], a['txn_id'], a['amount_minor']
            if (tid, iid) in seen or type(amount) is not int or amount <= 0:
                raise ValueError('Cạnh phân bổ trùng hoặc số tiền không phải nguyên dương')
            seen.add((tid, iid))
            if iid not in invoices or tid not in banks:
                raise ValueError('Thiếu chứng từ nguồn đã quan sát được')
            invoice, bank = invoices[iid], banks[tid]
            if invoice['closure_type'] != 'open' or day(bank['value_date']) < day(invoice['issue_date']):
                raise ValueError('Hóa đơn đã đóng hoặc tiền về trước ngày lập hóa đơn')
            if bank.get('direction', 'in') != 'in' or bank.get('cash_flow_class') in NON_AR:
                raise ValueError('Giao dịch không phải khoản thu phải thu hợp lệ')
            party = invoice['customer_id']
            if bank.get('customer_id') not in (None, '', party):
                raise ValueError('Khách hàng trên giao dịch không khớp hóa đơn; cần kiểm tra nguồn')
            if tid in parties and parties[tid] != party:
                raise ValueError('Một khoản thu không được gán chéo khách hàng')
            parties[tid] = party
            by_i[iid] += amount; by_p[tid] += amount
        used = view['links'].groupby('txn_id').amount_minor.sum().to_dict() if len(view['links']) else {}
        if any(amount > invoices[iid]['amount_open_minor'] for iid, amount in by_i.items()) or any(
            amount + used.get(tid, 0) > money(banks[tid]) for tid, amount in by_p.items()):
            raise ValueError('Phân bổ vượt dư nợ hoặc tiền ngân hàng chưa phân bổ')
        gold = view['gold']
        ledger_inv = {r['id']: r for r in gold['invoices']}
        ledger_pay = {r['id']: r for r in gold['payments']}
        commands = []

        def record(kind, identifier, data, effective):
            commands.append(dict(tenant_id=source.firm, action='record', kind=kind,
                                 effective_on=effective, available_on=now,
                                 data=dict(tenant_id=source.firm, id=identifier, currency='VND', **data)))

        for iid in sorted(by_i):
            invoice = invoices[iid]
            data = dict(tenant_id=source.firm, id=iid, side='AR', party_id=invoice['customer_id'], currency='VND',
                        amount_minor=money(invoice, 'amount_gross')-int(invoice['credit_note']),
                        invoice_number=str(invoice['invoice_no']), source_ref=invoice.get('source_sha256') or iid)
            old = ledger_inv.get(iid)
            if old is None:
                record('invoice', iid, {k:v for k,v in data.items() if k not in {'tenant_id','id','currency'}}, day(invoice['issue_date']))
            elif any(old.get(k) != data[k] for k in ('amount_minor','invoice_number','party_id')):
                commands.append(dict(tenant_id=source.firm, action='revise', kind='invoice', expected_version=old['version'],
                                     effective_on=day(invoice['issue_date']), available_on=now, data=data))
        for tid in sorted(by_p):
            bank = banks[tid]
            if tid in ledger_pay:
                if ledger_pay[tid]['party_id'] != parties[tid] or ledger_pay[tid]['amount_minor'] != money(bank):
                    raise ValueError('Khoản thu đã ghi nhận đổi khách hoặc số tiền; cần xử lý nguồn')
                continue
            record('payment', tid, dict(side='AR', party_id=parties[tid], amount_minor=money(bank),
                                       source_ref=bank.get('source_sha256') or tid), day(bank['value_date']))
            record('bank', tid, dict(direction='credit', amount_minor=money(bank), account_id=bank.get('account_id', 'legacy'),
                                    source_ref=bank.get('source_sha256') or tid), day(bank['value_date']))
            record('bank_link', tid, dict(payment_id=tid, bank_id=tid, fee_minor=0), day(bank['value_date']))
        decision = 'D-' + fingerprint(dict(key=key, request=request_hash))[:24]
        base = dict(tenant_id=source.firm, decision_id=decision, effective_on=now, available_on=now)
        commands.extend([
            dict(base, action='suggest', allocations=[dict(invoice_id=a['invoice_id'], payment_id=a['txn_id'],
                                                          amount_minor=a['amount_minor']) for a in allocations],
                 reviewed_by=actor, source_ref=proposal_id or note, note=note),
            dict(base, action='approve', reviewed_by=actor),
            dict(base, action='commit', external_result='verified', reviewed_by=actor),
        ])
        result = source.ledger.transact(key, commands, request_hash=request_hash)
        return dict(result, decision_id=decision)


def reverse(source, key, decision_id, actor, note):
    request_hash = fingerprint(dict(action='reverse', decision_id=decision_id, actor=actor, note=note))
    if not actor.strip() or not note.strip():
        raise ValueError('Đảo phân bổ cần người xác nhận và lý do')
    with source.store.lock:
        cached = source.ledger.cached(key, request_hash)
        if cached:
            return cached
        now = today()
        gold = source.ledger.gold(now)
        written = next((e for e in gold['writeoffs'] if e['decision_id'] == decision_id), None)
        if not written and any(a['invoice_id'] == e['invoice_id'] for d in gold['decisions']
                               if d['decision_id'] == decision_id for a in d['allocations'] for e in gold['writeoffs']):
            raise ValueError('Cần đảo write-off trước khi thay đổi phân bổ liên quan')
        command = dict(tenant_id=source.firm, action='reverse_writeoff' if written else 'reverse',
                       decision_id=decision_id, effective_on=now, available_on=now, reviewed_by=actor, note=note)
        return source.ledger.transact(key, [command], request_hash=request_hash)


def writeoff(source, key, invoice_id, effective_on, actor, source_ref):
    effective_on = day(effective_on)
    request_hash = fingerprint(dict(action='writeoff', invoice_id=invoice_id, effective_on=effective_on,
                                    actor=actor, source_ref=source_ref))
    with source.store.lock:
        cached = source.ledger.cached(key, request_hash)
        if cached:
            return cached
        now = today()
        view = source.view(now)
        invoices = view['invoices'].set_index('invoice_id') if len(view['invoices']) else pd.DataFrame()
        if invoice_id not in invoices.index:
            raise ValueError('Không có hóa đơn đã quan sát')
        invoice = invoices.loc[invoice_id]
        if invoice.closure_type != 'open' or not day(invoice.issue_date) <= effective_on <= now:
            raise ValueError('Write-off cần hóa đơn đang mở và ngày nghiệp vụ hợp lệ')
        receipts = view['links'][view['links'].invoice_id.eq(invoice_id)]
        if len(receipts) and receipts.est_pay_date.max() > pd.Timestamp(effective_on):
            raise ValueError('Write-off không được trước khoản thu đã quan sát của hóa đơn')
        command = dict(tenant_id=source.firm, action='writeoff', decision_id='W-'+fingerprint(key)[:24],
                       invoice_id=invoice_id, amount_minor=int(invoice.amount_open_minor), effective_on=effective_on,
                       available_on=now, reviewed_by=actor, source_ref=source_ref,
                       invoice_context=invoice_context(dict(invoice, invoice_id=invoice_id)))
        return source.ledger.transact(key, [command], request_hash=request_hash)
