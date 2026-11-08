"""Evidence produced after a timestamp batch closes, separate from row scores."""
from collections import defaultdict, deque
import hashlib
import json

from .generate import parse
from .noise_policy import independent_requests
from .spec_policy import bank_identity


class BatchControls:
    def __init__(self, config, *, normalize, invoice_key, installment_exception, names, weights):
        self.cfg, self.normalize, self.invoice_key = config, normalize, invoice_key
        self.installment_exception, self.names, self.weights = installment_exception, names, weights
        self.payments, self.outflows, self.invoices = defaultdict(deque), defaultdict(deque), defaultdict(list)

    @staticmethod
    def outflow(row):
        return (int(row['is_financial_entry']) == 1 and row['payment_channel'] in {'cash', 'bank'}
                and row['txn_type'] != 'customer_receipt')

    @staticmethod
    def recipient(row):
        if row['payment_channel'] == 'cash':
            return ('cash_vendor', row['vendor_id']) if row['vendor_id'] else None
        identity = bank_identity(row['recipient_account'], row.get('recipient_bank_code', ''))
        return ('bank', identity) if identity else None

    def event(self, rule, scope, now, pool, evidence, *, suppressed='', gap=False, path=()):
        current = sorted(r['transaction_id'] for r in pool if r['posted_at'] == now)
        prior = sorted(r['transaction_id'] for r in pool if r['posted_at'] < now)
        company = pool[0]['company_id']
        scope = json.dumps(scope, ensure_ascii=False, separators=(',', ':'))
        payload = json.dumps([company, now, rule, scope, current], separators=(',', ':'))
        points = 0 if suppressed or gap else self.weights[rule]
        return dict(event_id='BE_'+hashlib.sha256(payload.encode()).hexdigest()[:20],
            company_id=company, detected_at=now, phase='batch_closed', rule_id=rule,
            rule_name=self.names[rule], scope=scope, status='information_gap' if gap else 'evaluated',
            signal=None if gap else not bool(suppressed), points=points,
            hard_trigger=int(rule == 'P1' and points > 0), suppressed_reason=suppressed,
            transaction_ids=current, related_transaction_ids=prior, evidence=evidence, graph_path=list(path))

    def split(self, rule, scope, now, pool, evidence, staff, procurement, agreements):
        count = 2 if rule == 'A1' else 3
        ratio = self.cfg['short_total_ratio'] if rule == 'A1' else 1
        total = sum(int(r['amount_vnd']) for r in pool)
        current = [r for r in pool if r['posted_at'] == now]
        if len(current) < 2 or len(pool) < count:
            return None
        evaluations, participants = [], set()
        phase2 = self.cfg['noise_policy'] == 'phase2'
        for row in current:
            limit = int(row['approval_limit_vnd'])
            if total < ratio * limit:
                continue
            group = [r for r in pool if r['transaction_id'] != row['transaction_id']]
            retained, excluded, reason, check = group, [], '', {}
            if phase2 and evidence.strong_purchase_for(row):
                retained, excluded, proof = evidence.scope(row, group, now)
                reason = 'Nghĩa vụ chi đã duyệt, đúng giao dịch và tổng trong trần' if proof else ''
                check = proof or dict(basis='no_valid_bound_payment_evidence')
            else:
                if phase2:
                    retained, excluded, _ = independent_requests(row, group, procurement, staff, now)
                payments = [r for r in evidence.payments(row) if r['txn_type'] == 'vendor_payment'
                            and r['transaction_id'] != row['transaction_id']]
                key = self.invoice_key(row)
                invoice_history = [r for r in payments if key and self.invoice_key(r) == key]
                contract_history = [r for r in payments if row.get('contract_id')
                                    and r.get('contract_id') == row['contract_id']]
                if phase2 or rule == 'A2':
                    reason, check = self.installment_exception(row, group, invoice_history, contract_history,
                        agreements.records(row['company_id'], row['vendor_id']), staff, now, rule)
                elif (key and all(self.invoice_key(r) == key for r in group)
                      and int(row['invoice_gross_vnd']) > 0
                      and sum(int(r['amount_vnd']) for r in invoice_history)+int(row['amount_vnd']) <= int(row['invoice_gross_vnd'])
                      and int(row['support_doc_count']) > 0):
                    reason = 'Các đợt cùng hóa đơn có hồ sơ và tổng chưa vượt hóa đơn'
            scoped_total = sum(int(r['amount_vnd']) for r in retained)+int(row['amount_vnd'])
            if not reason and excluded and (len(retained)+1 < count or scoped_total < ratio*limit):
                reason = 'Các nghĩa vụ độc lập đã có bằng chứng xác minh'
            evaluation = dict(transaction_id=row['transaction_id'], approval_limit_vnd=limit,
                evaluated_transaction_ids=sorted([r['transaction_id'] for r in retained]+[row['transaction_id']]),
                evaluated_total_vnd=scoped_total, excluded_obligations=excluded,
                installment_check=check, suppressed_reason=reason)
            evaluations.append(evaluation)
            if not reason:
                participants.update(evaluation['evaluated_transaction_ids'])
        if not evaluations:
            return None
        selected = [r for r in pool if r['transaction_id'] in participants] if participants else pool
        if sum(r['posted_at'] == now for r in selected) < 2:
            return None
        reasons = sorted({r['suppressed_reason'] for r in evaluations if r['suppressed_reason']})
        return self.event(rule, scope, now, selected,
            dict(count=len(selected), total_vnd=sum(int(r['amount_vnd']) for r in selected),
                 raw_count=len(pool), raw_total_vnd=total,
                 approval_limit_vnd=min(r['approval_limit_vnd'] for r in evaluations),
                 window_days=self.cfg['short_days' if rule == 'A1' else 'long_days'],
                 evaluations=evaluations), suppressed='; '.join(reasons) if not participants else '')

    def close(self, now, batch, row_scores, *, graph, evidence, staff, procurement, agreements):
        at, events = parse(now), []
        current_payments = [r for r in batch if self.outflow(r) and r['txn_type'] == 'vendor_payment']
        exceptions = {r['transaction_id']: r['_a4_exception'] for r in row_scores}
        current_outflows = [{**r, '_a4_exception': exceptions[r['transaction_id']]}
                            for r in batch if self.outflow(r)]
        companies = sorted({r['company_id'] for r in batch})
        for cid in companies:
            history = self.payments[cid]
            while history and (at-parse(history[0]['posted_at'])).total_seconds() > self.cfg['long_days']*86400:
                history.popleft()
            outflows = self.outflows[cid]
            while outflows and (at-parse(outflows[0]['posted_at'])).total_seconds() > 31*86400:
                outflows.popleft()
            if sum(r['company_id'] == cid for r in batch) < 2:
                continue
            current = [r for r in current_payments if r['company_id'] == cid]
            invoices = defaultdict(list)
            for row in current:
                key = self.invoice_key(row)
                if key:
                    invoices[key].append(row)
            for key, rows in sorted(invoices.items()):
                if len(rows) < 2:
                    continue
                pool = [*self.invoices[key], *rows]
                gross_values = sorted({int(r['invoice_gross_vnd']) for r in pool})
                total = sum(int(r['amount_vnd']) for r in pool)
                if len(gross_values) != 1 or gross_values[0] <= 0:
                    events.append(self.event('P1', ('invoice', *key), now, pool,
                        dict(invoice_number=key[2], observed_gross_values_vnd=gross_values,
                             cumulative_paid_vnd=total, evidence_status='information_gap'), gap=True))
                elif total > gross_values[0]+1:
                    events.append(self.event('P1', ('invoice', *key), now, pool,
                        dict(invoice_number=key[2], invoice_gross_vnd=gross_values[0],
                             cumulative_paid_vnd=total, excess_vnd=total-gross_values[0])))
            eligible = [r for r in [*history, *current]
                        if int(r['amount_vnd']) < int(r['approval_limit_vnd'])]
            unknown_recipients = defaultdict(list)
            for row in current:
                number = self.normalize(row['recipient_account'])
                if row['payment_channel'] == 'bank' and number and self.recipient(row) is None:
                    unknown_recipients[number].append(row)
            for number, rows in sorted(unknown_recipients.items()):
                if len(rows) >= 2:
                    events.append(self.event('A1', ('unconfirmed_recipient', number), now, rows,
                        dict(evidence_status='information_gap', missing_fields=['recipient_bank_code'],
                             count=len(rows), total_vnd=sum(int(r['amount_vnd']) for r in rows)), gap=True))
            recipient_keys = sorted({self.recipient(r) for r in current
                                     if self.recipient(r) is not None})
            for recipient in recipient_keys:
                pool = [r for r in eligible if self.recipient(r) == recipient]
                short = [r for r in pool if (at-parse(r['posted_at'])).total_seconds() <= self.cfg['short_days']*86400]
                event = self.split('A1', ('recipient', *recipient), now, short, evidence, staff, procurement, agreements)
                if event:
                    events.append(event)
                for maker in sorted({r['creator_id'] for r in current if self.recipient(r) == recipient}):
                    event = self.split('A2', ('maker_recipient', maker, *recipient), now,
                        [r for r in pool if r['creator_id'] == maker], evidence, staff, procurement, agreements)
                    if event:
                        events.append(event)
            if self.cfg['enable_graph']:
                components = defaultdict(list)
                for row in eligible:
                    root = graph.group(cid).root(graph.node(row['vendor_id'], 'entity'))
                    components[root].append(row)
                for pool in components.values():
                    if sum(r['posted_at'] == now for r in pool) < 2:
                        continue
                    short = [r for r in pool if (at-parse(r['posted_at'])).total_seconds() <= self.cfg['short_days']*86400]
                    chosen, branch = None, ''
                    for scope, minimum, ratio, label in (
                        (short, 2, self.cfg['short_total_ratio'], 'short_2_85pct'),
                        (pool, 3, 1, 'long_3_100pct')):
                        if label.startswith('short') and self.cfg['spec_policy'] != 'phase3':
                            continue
                        vendors = {r['vendor_id'] for r in scope}
                        total = sum(int(r['amount_vnd']) for r in scope)
                        if len(vendors) > 1 and len(scope) >= minimum and any(
                                total >= ratio*int(r['approval_limit_vnd']) for r in scope if r['posted_at'] == now):
                            chosen, branch = scope, label
                            break
                    if chosen:
                        vendor_ids = sorted({r['vendor_id'] for r in chosen})
                        path = graph.path(cid, graph.node(vendor_ids[0], 'entity'),
                                          {graph.node(v, 'entity') for v in vendor_ids[1:]})
                        events.append(self.event('A3', ('linked_vendors', *vendor_ids), now, chosen,
                            dict(vendor_ids=vendor_ids, count=len(chosen), total_vnd=sum(int(r['amount_vnd']) for r in chosen),
                                 approval_limit_vnd=min(int(r['approval_limit_vnd']) for r in chosen if r['posted_at'] == now),
                                 branch=branch, window_days=self.cfg['short_days'] if branch.startswith('short') else self.cfg['long_days']), path=path))
            all_outflows = [*outflows, *(r for r in current_outflows if r['company_id'] == cid)]
            for maker in sorted({r['creator_id'] for r in current_outflows if r['company_id'] == cid}):
                pool = [r for r in all_outflows if r['creator_id'] == maker and not r['_a4_exception']
                        and self.cfg['near_low'] <= int(r['amount_vnd'])/int(r['approval_limit_vnd']) <= self.cfg['near_high']
                        and (r['posted_at'][:7] == now[:7] if self.cfg['spec_policy'] == 'phase3'
                             and self.cfg['near_period'] == 'calendar_month' else
                             (at-parse(r['posted_at'])).total_seconds() <= 30*86400)]
                if sum(r['posted_at'] == now for r in pool) >= 2 and len(pool) >= self.cfg['near_count']:
                    events.append(self.event('A4', ('near_limit_maker', maker), now, pool,
                        dict(count=len(pool), total_vnd=sum(int(r['amount_vnd']) for r in pool),
                             period=now[:7] if self.cfg['near_period'] == 'calendar_month' else 'rolling_30d')))
        # Separate state: a closed batch never changes the per-row histories.
        for row in current_payments:
            self.payments[row['company_id']].append(row)
            key = self.invoice_key(row)
            if key:
                self.invoices[key].append(row)
        for row in current_outflows:
            self.outflows[row['company_id']].append(row)
        return sorted(events, key=lambda event: (event['company_id'], event['rule_id'], event['event_id']))
