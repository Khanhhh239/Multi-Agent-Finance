"""One runtime T9 path: T0 observations -> constrained flow -> accepted ledger.

Proposals are never training truth. Historical snapshots use both business and
knowledge dates. Receipt identity, noncash closures and invoice balances remain
separate; no fitted T1 prior or synthetic outcome participates in matching.
"""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from . import CONTRACT_VERSION
from ._thang.allocation import Config
from ._thang.constrained import allocate
from ._thang.data import fingerprint, iso_date
from ._thang.matching import normalize
from .ledger import DecisionLedger


LINK_COLUMNS = ['txn_id', 'invoice_id', 'est_pay_date', 'amount', 'amount_minor',
                'known_at', 'decision_id', 'method', 'evidence_type']
NON_AR = {'financing', 'internal', 'internal_transfer', 'cash_deposit', 'cash_to_bank', 'other_external', 'non_ar'}


class ObservationGap(ValueError):
    """A historical origin lacks complete observed bank coverage, not a data repair."""


def day(value):
    if isinstance(value, str):
        iso_date(value)
        return value
    return pd.Timestamp(value).date().isoformat()


def today():
    return pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').date().isoformat()


def knowledge_day(row, fallback):
    dates = [day(row[field]) for field in ('available_on', 'known_at') if row.get(field)]
    return max(dates) if dates else day(fallback)


def money(row, column='amount'):
    """Exact VND boundary; legacy decimal values must also be integral, never rounded."""
    if str(row.get('currency', 'VND')).upper() != 'VND':
        raise ValueError('Luồng hiện tại tính bằng VND; chưa có quy đổi tỷ giá cho mô hình')
    value = row.get(column + '_minor', row.get(column))
    if isinstance(value, (bool, np.bool_)) or value is None:
        raise ValueError('Thiếu số tiền nguyên theo đơn vị nhỏ nhất')
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        raise ValueError('Số tiền VND phải hữu hạn, nguyên và không âm')
    return int(number)


def invoice_context(invoice):
    """Stable document/customer scope of a reviewed noncash decision."""
    fields = ('invoice_id', 'customer_id', 'seller_mst', 'buyer_mst', 'symbol', 'invoice_no')
    context = {field: str(invoice[field]) if pd.notna(invoice.get(field)) else None for field in fields}
    context.update(currency=str(invoice.get('currency', 'VND')).upper(), issue_date=day(invoice['issue_date']))
    return context


def visible(rows, cutoff, business):
    from agent1_service.ingest.dates import normalize_date_fields
    result = []
    for raw in rows:
        row = normalize_date_fields(raw, required=(business,))
        effective = day(row[business])
        # Legacy local records have only a business date. New API records
        # always carry availability; this fallback is explicitly research-only.
        known = knowledge_day(row, effective)
        if known < effective:
            raise ValueError('Ngày biết chứng từ không được trước ngày nghiệp vụ')
        if effective <= cutoff and known <= cutoff:
            result.append(row)
    return result


class ObservedSource:
    def __init__(self, store, firm, bank_accounts_file=None):
        self.store, self.firm = store, firm
        self.ledger = DecisionLedger(store, firm)
        self.bank_accounts_file = bank_accounts_file

    def task_records(self, cutoff):
        """Knowledge-filtered observations for T3/T8, T4 and T5 at one cutoff."""
        from agent1_service.ingest.dates import normalize_date_fields
        cutoff=day(cutoff)
        result={}
        for kind in ('customers','promises','outflows'):
            records=[]
            for row in self.store.as_of(self.firm,kind,cutoff):
                # Old /promises records used Timestamp.isoformat(). Normalize
                # only the read view; encrypted source/history stay untouched.
                row=normalize_date_fields(row)
                if row.get('firm_id',self.firm)!=self.firm:
                    raise ValueError('Dữ liệu thuộc doanh nghiệp khác')
                business=row.get('made_date') if kind=='promises' else row.get('date') if kind=='outflows' else None
                known=knowledge_day(row,business or '0001-01-01')
                if known>cutoff or kind=='promises' and day(row['made_date'])>cutoff:
                    continue
                copied=dict(row)
                if kind=='outflows':copied['known_at']=known
                records.append(copied)
            result[kind]=records
        return result

    def invoice_records(self, cutoff):
        from agent1_service.ingest.invoices import effective_invoices
        cutoff = day(cutoff)
        invoices = self.store.get(self.firm, 'invoice_versions') or self.store.get(self.firm, 'invoices')
        invoices = visible(invoices, cutoff, 'issue_date')
        frame = effective_invoices(invoices, self.store.get(self.firm, 'invoice_events'), cutoff)
        return frame.to_dict('records') if len(frame) else []

    def inputs(self, cutoff):
        cutoff = day(cutoff)
        rows = self.invoice_records(cutoff)
        bank = visible(self.store.get(self.firm, 'bank_txns'), cutoff, 'value_date')
        statements = self.store.get(self.firm, 'bank_statements')
        if statements:
            from agent1_service.ingest.bank_accounts import load_account_registry, registry_path
            from agent1_service.ingest.bank_statement import statement_scope
            registry = load_account_registry(self.bank_accounts_file or registry_path(self.store.path.parent), self.firm)
            known = [s for s in statements if s['available_on'] <= cutoff]
            coverage = statement_scope(known, min(s['period_start'] for s in statements), cutoff, registry)
            if not coverage['verified']:
                raise ObservationGap('Phạm vi sao kê chưa đầy đủ tại ngày cắt')
            ids = {s['statement_id'] for s in known}
            bank = [r for r in bank if r.get('statement_id') in ids]
        for row in rows + bank:
            if row.get('firm_id', self.firm) != self.firm:
                raise ValueError('Dữ liệu thuộc doanh nghiệp khác')
        return rows, bank

    def legacy_writeoff_context(self, event):
        """Infer old scope only when retained daily source history is unambiguous."""
        versions = self.store.get(self.firm, 'invoice_versions')
        approved = event['available_on']
        records = [r for r in visible(versions, approved, 'issue_date') if r['invoice_id'] == event['invoice_id']]
        earlier = [r for r in records if knowledge_day(r, r['issue_date']) < approved]
        candidates = [r for r in records if knowledge_day(r, r['issue_date']) == approved]
        if earlier:
            candidates.append(max(earlier, key=lambda r: r.get('revision', 1)))
        if not candidates:
            raise ValueError('Write-off cũ thiếu lịch sử để xác minh khách/chứng từ; cần đảo write-off và duyệt lại')
        if len({fingerprint(invoice_context(r)) for r in candidates}) > 1:
            raise ValueError('Write-off cũ không xác định được thứ tự đổi khách/chứng từ cùng ngày; cần đảo write-off và duyệt lại')
        original = next((r for r in self.invoice_records(approved) if r['invoice_id'] == event['invoice_id']), None)
        if original is None:
            raise ValueError('Write-off cũ mất chứng từ tại ngày duyệt; cần đảo write-off và kiểm tra nguồn')
        return invoice_context(original)

    def noncash_changes(self, cutoff):
        """Observed changes to the cash target, including historical corrections.

        Revisions have no separate economic revision date in T0, so amount
        corrections conservatively take effect on their availability day.
        Signed adjustment documents and credit notes retain their own dates.
        """
        versions = self.store.get(self.firm, 'invoice_versions') or self.store.get(self.firm, 'invoices')
        records = visible(versions, day(cutoff), 'issue_date')
        changes, previous = {}, {}
        for row in sorted(records, key=lambda r: (r['invoice_id'], r.get('revision', 1))):
            iid = row['invoice_id']
            known = knowledge_day(row, row['issue_date'])
            kind = row.get('adjustment_type')
            if kind == 'replacement':
                continue
            if kind == 'adjustment':
                target = row.get('adjusts_invoice_id')
                if target:
                    changes.setdefault(target, []).append(dict(effective_on=day(row['issue_date']),
                                                              available_on=known, kind='adjustment'))
                continue
            prior = previous.get(iid)
            if prior is not None and money(row, 'amount_gross') != money(prior, 'amount_gross'):
                changes.setdefault(iid, []).append(dict(effective_on=known, available_on=known, kind='revision'))
            if row.get('credit_note_date') and pd.notna(row['credit_note_date']):
                credit_date = day(row['credit_note_date'])
                credit = money({'amount': row.get('credit_note', 0)})
                if credit and (prior is None or (prior.get('credit_note'), prior.get('credit_note_date')) !=
                              (row.get('credit_note'), row.get('credit_note_date'))):
                    changes.setdefault(iid, []).append(dict(effective_on=credit_date,
                                                              available_on=max(known, credit_date), kind='credit_note'))
            previous[iid] = row
        return {iid: sorted(events, key=lambda e: (e['effective_on'], e['available_on'], e['kind']))
                for iid, events in changes.items()}

    def view(self, cutoff):
        cutoff = day(cutoff)
        invoices, bank = self.inputs(cutoff)
        changes = self.noncash_changes(cutoff)
        by_invoice = {r['invoice_id']: r for r in invoices}
        by_bank = {r['txn_id']: r for r in bank}
        gold = self.ledger.gold(cutoff)
        ledger_invoices = {r['id']: r for r in gold['invoices']}
        ledger_payments = {r['id']: r for r in gold['payments']}
        events = [e for e in self.ledger.events() if e['available_on'] <= cutoff]
        accepted_at = {}
        for e in events:
            if e['action'] in {'commit', 'verify'}:
                accepted_at[e['decision_id']] = e['available_on']
        links = []
        for decision in gold['decisions']:
            if decision['status'] != 'committed':
                continue
            for allocation in decision['allocations']:
                iid, tid = allocation['invoice_id'], allocation['payment_id']
                if iid not in by_invoice or tid not in by_bank:
                    raise ValueError('Phân bổ đã ghi nhận mất chứng từ nguồn; cần đảo phân bổ để xử lý')
                party = by_invoice[iid]['customer_id']
                if (ledger_invoices[iid]['party_id'] != party or ledger_payments[tid]['party_id'] != party
                        or by_bank[tid].get('customer_id') not in (None, '', party)):
                    raise ValueError('Khách hàng của chứng từ đã đổi so với phân bổ đã duyệt; cần đảo phân bổ và kiểm tra nguồn')
                if day(by_bank[tid]['value_date']) < day(by_invoice[iid]['issue_date']):
                    raise ValueError('Ngày thu trước ngày lập hóa đơn sau revision; cần đảo phân bổ và kiểm tra nguồn')
                if (by_bank[tid].get('direction', 'in') != 'in' or by_bank[tid].get('cash_flow_class') in NON_AR):
                    raise ValueError('Khoản thu đã duyệt không còn là thu phải thu; cần đảo phân bổ và kiểm tra nguồn')
                money(by_invoice[iid], 'amount_gross')
                if money(by_bank[tid]) != ledger_payments[tid]['amount_minor']:
                    raise ValueError('Số tiền nguồn của khoản thu đã đổi; cần đảo phân bổ và kiểm tra nguồn')
                links.append(dict(txn_id=tid, invoice_id=iid, est_pay_date=day(by_bank[tid]['value_date']),
                                  amount=allocation['amount_minor'], amount_minor=allocation['amount_minor'],
                                  known_at=accepted_at[decision['decision_id']], decision_id=decision['decision_id'],
                                  method='accepted_constrained_flow', evidence_type='reviewed_bank_allocation'))
        written = {}
        for event in gold['writeoffs']:
            iid = event['invoice_id']
            if iid not in by_invoice:
                raise ValueError('Write-off mất chứng từ nguồn; cần đảo write-off và kiểm tra nguồn')
            context = event.get('invoice_context')
            if context is None:
                # Legacy commands are immutable. Recover their scope only from
                # retained T0 history at approval, never from the latest buyer.
                context = self.legacy_writeoff_context(event)
            if context != invoice_context(by_invoice[iid]):
                raise ValueError('Khách hàng hoặc chứng từ của write-off đã đổi; cần đảo write-off và kiểm tra nguồn')
            if iid in written:
                raise ValueError('Trùng write-off có hiệu lực cho một hóa đơn; cần đảo write-off để xử lý')
            written[iid] = event
        for invoice in invoices:
            iid = invoice['invoice_id']
            gross = money(invoice, 'amount_gross')
            credit = 0
            if invoice.get('credit_note_date') is not None and pd.notna(invoice.get('credit_note_date')):
                if day(invoice['credit_note_date']) <= cutoff:
                    credit = money({'amount': invoice.get('credit_note', 0)})
            own = sorted((r for r in links if r['invoice_id'] == iid), key=lambda r: (r['est_pay_date'], r['txn_id']))
            paid = sum(r['amount_minor'] for r in own)
            if paid + credit > gross:
                raise ValueError('Phân bổ vượt công nợ có hiệu lực; cần đảo phân bổ trước khi xử lý sửa chứng từ')
            for field in ('paid_date_true','closed_date_true','cash_received_amount','remaining_amount',
                          'paid_amount','writeoff_amount','observation_end','outcome_status_at_end','default_date'):
                invoice.pop(field,None)
            invoice.update(firm_id=self.firm, amount_gross=gross, amount_gross_minor=gross,
                           credit_note=credit, paid_date_est=pd.NaT, writeoff_date=pd.NaT,
                           closure_type='open', amount_open_minor=gross-credit-paid,
                           last_cash_date=pd.Timestamp(own[-1]['est_pay_date']) if own else pd.NaT,
                           closed_date=pd.NaT, outcome_known_at=None)
            if invoice.get('due_date') is not None and pd.notna(invoice.get('due_date')):
                invoice['term_days'] = (pd.Timestamp(invoice['due_date'])-pd.Timestamp(invoice['issue_date'])).days
            if iid in written:
                event = written[iid]
                if event['effective_on'] < day(invoice['issue_date']) or any(
                    r['est_pay_date'] > event['effective_on'] for r in own
                ):
                    raise ValueError('Ngày write-off không còn hợp lệ với chứng từ; cần đảo write-off và kiểm tra nguồn')
                if event['amount_minor'] != gross-credit-paid:
                    raise ValueError('Write-off không còn khớp dư nợ; cần xử lý chứng từ nguồn')
                invoice.update(writeoff_date=pd.Timestamp(event['effective_on']), closure_type='writeoff',
                               closed_date=pd.Timestamp(event['effective_on']),
                               amount_open_minor=0, outcome_known_at=event['available_on'])
            elif credit >= gross:
                invoice.update(closure_type='credit_note', amount_open_minor=0,
                               closed_date=pd.Timestamp(invoice['credit_note_date']),
                               outcome_known_at=max(day(invoice['credit_note_date']),
                                                    knowledge_day(invoice, invoice['issue_date'])))
            elif paid == gross-credit and own:
                last_cash = day(own[-1]['est_pay_date'])
                credit_date = day(invoice['credit_note_date']) if credit else day(invoice['issue_date'])
                amount_changes = [e['effective_on'] for e in changes.get(iid, []) if e['kind'] != 'credit_note']
                balance_date = max(amount_changes, default=day(invoice['issue_date']))
                # A same-day reduction is conservatively a noncash closure:
                # this day-granular contract cannot prove the ordering.
                noncash_close = bool(credit and credit_date >= last_cash or amount_changes and balance_date >= last_cash)
                invoice.update(paid_date_est=pd.NaT if noncash_close else pd.Timestamp(last_cash),
                               closure_type=('credit_note' if credit and credit_date >= balance_date else 'adjustment')
                                            if noncash_close else 'paid',
                               closed_date=pd.Timestamp(max(last_cash, credit_date, balance_date)),
                               outcome_known_at=max([r['known_at'] for r in own] +
                                                    [knowledge_day(invoice, invoice['issue_date']), credit_date] +
                                                    [e['available_on'] for e in changes.get(iid, [])]))
        frame = pd.DataFrame(invoices)
        for column in ('issue_date', 'due_date', 'paid_date_est', 'writeoff_date', 'credit_note_date',
                       'last_cash_date', 'closed_date'):
            if column in frame:
                frame[column] = pd.to_datetime(frame[column])
        links = pd.DataFrame(links, columns=LINK_COLUMNS)
        for column in ('est_pay_date', 'known_at'):
            links[column] = pd.to_datetime(links[column])
        digest = fingerprint(dict(contract=CONTRACT_VERSION, cutoff=cutoff, ledger=gold['snapshot_hash'],
                                  noncash_changes=changes,
                                  invoices=invoices if not invoices else [
                                      {k: str(v) for k, v in r.items()} for r in invoices], bank=bank,
                                  tasks=self.task_records(cutoff)))
        return dict(invoices=frame, links=links, bank=bank, gold=gold, snapshot_hash=digest,
                    noncash_changes=changes, contract_version=CONTRACT_VERSION, cutoff=cutoff)

    def task_tables(self, cutoff):
        view=self.view(cutoff)
        for kind,rows in self.task_records(cutoff).items():
            frame=pd.DataFrame(rows)
            for column in ('date','made_date','promised_date','known_at'):
                if column in frame:frame[column]=pd.to_datetime(frame[column])
            if kind=='promises' and len(frame):frame['kept']=np.nan
            view[kind]=frame
        return view

    def propose(self, cutoff, *, max_age_days=3650):
        view = self.view(cutoff)
        invoices = view['invoices'].to_dict('records')
        customers = self.task_records(cutoff)['customers']
        name_ids = {}
        for customer in customers:
            if customer.get('available_on', '0001-01-01') > day(cutoff):
                continue
            name_ids.setdefault(normalize(customer.get('short', '')), set()).add(customer['customer_id'])
        used = view['links'].groupby('txn_id').amount_minor.sum().to_dict() if len(view['links']) else {}
        inv = [dict(tenant_id=self.firm, id=r['invoice_id'], invoice_number=str(r['invoice_no']),
                    party_id=r['customer_id'], side='AR', currency='VND', amount_minor=r['amount_open_minor'],
                    issued_on=day(r['issue_date'])) for r in invoices if r['amount_open_minor'] > 0]
        payments, ignored = [], []
        for row in view['bank']:
            tid = row['txn_id']
            if row.get('direction', 'in') != 'in' or row.get('cash_flow_class') in NON_AR:
                ignored.append(dict(payment_id=tid, status='unmatched', reason='non_ar_bank_movement'))
                continue
            amount = money(row) - int(used.get(tid, 0))
            if amount < 0:
                raise ValueError('Phân bổ vượt tiền nhận trên sao kê')
            if amount == 0:
                continue
            party = row.get('customer_id', '')
            exact_names = name_ids.get(normalize(row.get('counterparty', '')), set())
            if not party and len(exact_names) == 1:
                party = next(iter(exact_names))
            payments.append(dict(tenant_id=self.firm, id=tid, side='AR', party_id=party,
                                 currency='VND', amount_minor=amount, payment_on=day(row['value_date']),
                                 reference=str(row.get('memo', '')), **({'remittance': row['remittance']} if 'remittance' in row else {})))
        result = allocate(inv, payments, Config(max_age_days=max_age_days))
        result['decisions'].extend(ignored)
        result.update(snapshot_hash=view['snapshot_hash'], cutoff=day(cutoff), contract_version=CONTRACT_VERSION)
        return result


class ObservedSnapshotBuilder:
    """Task views share an as-of source; future outcomes are attached only as labels."""
    def __init__(self, source):
        self.source = source
        self.missing_windows = []

    def snapshot(self, cutoff):
        from agent1.models.features import SnapshotBuilder
        view = self.source.task_tables(cutoff)
        invoices = view['invoices']
        if invoices.empty:
            return invoices
        promises = view['promises']
        open_ids = set(invoices.loc[invoices.closure_type.eq('open'), 'invoice_id'])
        return SnapshotBuilder(invoices, view['links'], promises if len(promises) else None,
                               label_col='paid_date_est').snapshot(cutoff, observed_open_ids=open_ids)

    def build(self, cutoffs, label_end):
        from agent1.models.features import add_labels
        end = day(label_end)
        cutoffs=list(cutoffs)
        self.missing_windows=[]
        if not cutoffs:return pd.DataFrame()
        try:outcome_view = self.source.view(end)
        except ObservationGap:
            self.missing_windows.append(end)
            return pd.DataFrame()
        outcomes = outcome_view['invoices']
        changes = outcome_view['noncash_changes']
        if outcomes.empty:
            return outcomes
        outcomes = outcomes.set_index('invoice_id')
        receipts = outcome_view['links']
        frames = []
        for cutoff in cutoffs:
            if day(cutoff) > end:
                raise ValueError('label_end trước cutoff')
            try:frame = self.snapshot(cutoff)
            except ObservationGap:
                self.missing_windows.append(day(cutoff))
                continue
            if frame.empty:
                continue
            frame['label_date'] = pd.to_datetime(frame.invoice_id.map(outcomes.paid_date_est))
            frame['writeoff_date'] = pd.to_datetime(frame.invoice_id.map(outcomes.writeoff_date))
            # A late-discovered receipt before origin is not future cash.
            eligible = frame.invoice_id.isin(outcomes.index) & (frame.label_date.isna() | (frame.label_date > frame.cutoff)) & (
                frame.writeoff_date.isna() | (frame.writeoff_date > frame.cutoff))
            # Identity correction is not a transferable payment history.
            eligible &= frame.customer_id.eq(frame.invoice_id.map(outcomes.customer_id))
            # A changed face amount is a different target. Until an explicit
            # amount-history label adapter exists, exclude that origin rather
            # than call a previously settled invoice unpaid after an increase.
            eligible &= frame.amount_gross.eq(frame.invoice_id.map(outcomes.amount_gross))
            origin = day(cutoff)
            # Cash received before origin but allocated only afterwards cannot
            # be counted as future cash, or used to rewrite origin features.
            late_cash_ids = set(receipts.loc[
                receipts.est_pay_date.le(pd.Timestamp(origin)) & receipts.known_at.gt(pd.Timestamp(origin)), 'invoice_id'])
            eligible &= ~frame.invoice_id.isin(late_cash_ids)
            late_change = frame.invoice_id.map(lambda iid: any(
                e['effective_on'] <= origin < e['available_on'] for e in changes.get(iid, [])))
            eligible &= ~late_change
            frame = frame[eligible].copy()
            if len(frame):
                labeled=add_labels(frame, end)
                # The first intervening noncash change ends follow-up of the
                # original amount. An origin after a known change can instead
                # learn the remaining cash target from that revised balance.
                for index, row in labeled.iterrows():
                    dates = [e['effective_on'] for e in changes.get(row.invoice_id, [])
                             if origin < e['effective_on'] <= end]
                    if dates:
                        days = (pd.Timestamp(min(dates))-row.cutoff).days
                        if days <= min(row.obs_window, row.remaining):
                            labeled.loc[index, ['obs_window','time_obs','event','remaining','label_date']] = [
                                float(days), float(days), 0, np.inf, pd.NaT]
                if len(labeled):frames.append(labeled)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
