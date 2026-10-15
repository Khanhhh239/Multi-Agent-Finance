"""Versioned HR, workflow, document and receivable evidence; no truth inputs."""
from collections import defaultdict
import json
from pathlib import Path

from .generate import parse
from .temporal_evidence import approved_evidence
from .noise_policy import verified_document

SOURCES = {
    'leave_periods': 'leave_id', 'system_actions': 'action_id',
    'leave_activity_authorizations': 'authorization_id',
    'employment_events': 'employment_event_id', 'payroll_settlements': 'settlement_id',
    'workflow_policies': 'workflow_policy_id', 'override_events': 'override_id',
    'document_series': 'series_id', 'document_register': 'register_id',
    'document_cancellations': 'cancellation_id',
    'receivable_invoices': 'invoice_id', 'receipt_allocations': 'allocation_id',
    'receipt_coverage': 'coverage_id', 'receivable_explanations': 'explanation_id',
}
REQUIRED = {'C4': ('leave_periods', 'system_actions'),
            'E2': ('employment_events', 'payroll_settlements'),
            'F2': ('workflow_policies', 'override_events'),
            'F3': ('document_series', 'document_register', 'document_cancellations'),
            'F4': ('receivable_invoices', 'receipt_allocations', 'receipt_coverage', 'receivable_explanations')}

SCHEMA = json.loads(Path(__file__).with_name('evidence_sources.schema.json').read_text(encoding='utf-8'))


def required_columns(name):
    table = SCHEMA['tables'][name]
    return [*SCHEMA['common'], *(SCHEMA['approved'] if table.get('approved') else []), *table['fields']]


class EvidenceBook:
    """Latest revision at the action/cutoff, not the later posting timestamp.

    Immutable bindings prevent an entity filter from resurrecting old revisions.
    Empty tables and queries are valid; malformed/conflicting source IDs fail.
    """
    def __init__(self, tables):
        self.rows = {}
        self.index = {}
        for name, identity in SOURCES.items():
            rows = sorted(tables.get(name, []), key=lambda r: (r['observed_at'], r[identity]))
            identities, seen, index = {}, {}, defaultdict(list)
            for row in rows:
                missing = set(required_columns(name))-set(row)
                if missing:
                    raise ValueError(f'Missing evidence columns {name}: {sorted(missing)}')
                key = row['company_id'], row[identity]
                if not row[identity]:
                    raise ValueError(f'Empty {identity}')
                binding = tuple(row.get(k, '') for k in ('employee_id', 'transaction_id', 'series_id', 'customer_id', 'invoice_id', 'fiscal_year', 'document_type', 'branch_id'))
                if key in identities and identities[key] != binding:
                    raise ValueError(f'Source identity changed binding: {key}')
                identities[key] = binding
                version = key, row['observed_at']
                if version in seen and seen[version] != row:
                    raise ValueError(f'Conflicting source revision: {version}')
                seen[version] = row
                index[(row['company_id'], '', '')].append(row)
                for field in ('employee_id', 'transaction_id', 'series_id', 'invoice_id'):
                    if row.get(field):
                        index[(row['company_id'], field, row[field])].append(row)
            self.rows[name], self.index[name] = rows, index

    def at(self, name, company, now, field='', value=''):
        identity = SOURCES[name]
        versions = {}
        for row in self.index[name].get((company, field, value), []):
            if row['observed_at'] > now:
                break
            versions[row[identity]] = row
        return list(versions.values())


class EvidencePolicy:
    def __init__(self, tables, config):
        self.book = EvidenceBook(tables)
        self.config = config
        self.transactions = {r['transaction_id']: r for r in tables['transactions']}
        self.staff_history = sorted(tables['employees'],key=lambda r:r['recorded_at'])
        self.staff_cache = {}
        self.customers = defaultdict(list)
        for customer in sorted(tables.get('customers', []), key=lambda c: c['recorded_at']):
            self.customers[(customer['company_id'], customer['customer_id'])].append(customer)
        self.has_diagnostics = bool(tables.get('document_series') or tables.get('receivable_invoices'))
        self.last_snapshot = {}
        self.findings = []

    def staff_at(self, at):
        if at not in self.staff_cache:
            known = {}
            for employee in self.staff_history:
                if employee['recorded_at']>at:
                    break
                known[employee['employee_id']] = employee
            if len(self.staff_cache)>=512:
                self.staff_cache.pop(next(iter(self.staff_cache)))
            self.staff_cache[at] = known
        return self.staff_cache[at]

    def approved(self, record, company, now):
        return approved_evidence(record,self.staff_at(record.get('approved_at','')),company,now)

    def checks(self, row, staff, now):
        cid, tid, checks = row['company_id'], row['transaction_id'], []
        book = self.book
        # C4: actual action trace, approved leave and permission known at action.
        actions = book.at('system_actions', cid, now, 'transaction_id', tid)
        violations, exceptions = [], []
        for event in actions:
            action_at = event.get('action_at', '')
            actor = self.staff_at(action_at).get(event['employee_id'])
            expected_actor = row['creator_id'] if event.get('action') == 'maker' else row['approver_id'] if event.get('action') == 'checker' else ''
            expected_time = row['created_at'] if event.get('action') == 'maker' else row['approved_at']
            if not actor or actor['company_id'] != cid or not event.get('evidence_id') or not action_at or event['employee_id'] != expected_actor or action_at != expected_time or not actor['recorded_at'] <= action_at <= event['observed_at'] <= now:
                continue
            for leave in book.at('leave_periods', cid, action_at, 'employee_id', event['employee_id']):
                if not (self.approved(leave, cid, action_at) and leave['starts_at'] <= action_at < leave['ends_at']):
                    continue
                permissions = [p for p in book.at('leave_activity_authorizations', cid, action_at, 'employee_id', event['employee_id'])
                    if self.approved(p, cid, action_at) and p.get('approver_id') != event['employee_id'] and
                    p.get('leave_id') == leave['leave_id'] and p.get('action') in {'all', event['action']} and p['starts_at'] <= action_at < p['ends_at']]
                proof = dict(action=dict(event), leave=dict(leave), authorizations=permissions)
                (exceptions if permissions else violations).append(proof)
        if violations or exceptions:
            checks.append(dict(rule_id='C4', evidence=dict(violations=violations, authorized_actions=exceptions),
                suppressed='' if violations else 'Thao tác trong nghỉ phép có quyền làm việc đã duyệt trước thao tác', role='transaction', confirmed=bool(violations)))
        # E2: current known employment event plus explicit period/type of payment.
        if row['txn_type'] == 'payroll':
            events = [e for e in book.at('employment_events', cid, now, 'employee_id', row['employee_id'])
                if self.approved(e, cid, now) and e['effective_date'] <= now[:10] and e.get('event_type') in {'termination', 'rehire'}]
            event = max(events, key=lambda e: (e['effective_date'], e['observed_at'], e['employment_event_id']), default=None)
            if event and event['event_type'] == 'termination' and now[:10] > event['effective_date']:
                settlements = book.at('payroll_settlements', cid, now, 'transaction_id', tid)
                settlement = max(settlements, key=lambda e: (e['observed_at'], e['settlement_id']), default=None)
                kind = settlement.get('payment_kind', '') if settlement else ''
                valid = bool(settlement and settlement.get('employee_id') == row['employee_id'] and
                    self.approved(settlement, cid, now) and settlement.get('approver_id') != row['employee_id'] and
                    settlement.get('payroll_period') == row['payroll_period'] and int(row['amount_vnd']) > 0 and
                    settlement.get('service_period_start', '') <= settlement.get('service_period_end', '') and settlement.get('service_period_end'))
                exempt = valid and kind in {'backpay', 'final_settlement', 'severance', 'bonus'} and settlement['service_period_end'] <= event['effective_date'] and int(settlement.get('authorized_amount_vnd', 0)) >= int(row['amount_vnd'])
                confirmed = valid and kind == 'regular_salary' and settlement['service_period_start'] > event['effective_date']
                checks.append(dict(rule_id='E2', evidence=dict(employment_event=dict(event), settlement=settlement,
                    evidence_status='confirmed_post_termination_salary' if confirmed else 'approved_final_payment' if exempt else 'information_gap'),
                    suppressed='Quyết toán/truy lĩnh đúng kỳ và số tiền đã duyệt' if exempt else '',
                    role='transaction' if confirmed else 'context', confirmed=confirmed))
        # F2: recorded bypass of a required control under known workflow policy.
        for event in book.at('override_events', cid, now, 'transaction_id', tid):
            at = event.get('operation_at', '')
            actor = self.staff_at(at).get(event.get('actor_id'))
            if not at or not actor or actor['company_id'] != cid or not event.get('evidence_id') or event.get('status') != 'executed' or not actor['recorded_at'] <= at <= event['observed_at'] <= now:
                continue
            policies = [p for p in book.at('workflow_policies', cid, at) if p.get('control_id') == event.get('control_id') and
                p.get('txn_type') in {'all', row['txn_type']} and p['effective_from'] <= at <= p['effective_to'] and self.approved(p, cid, at)]
            policy = max(policies, key=lambda p: (p['effective_from'], p['observed_at'], p['workflow_policy_id']), default=None)
            bypass = event.get('normal_workflow_completed') in {0, '0'}
            allowed = bool(policy and (policy.get('required') in {0, '0'} or (policy.get('allow_override') in {1, '1'} and
                actor['role'] in policy.get('authorized_override_roles', '').split('|') and int(row['amount_vnd']) <= int(policy.get('override_max_vnd', 0)))))
            confirmed = bool(policy and bypass and not allowed)
            checks.append(dict(rule_id='F2', evidence=dict(override_event=dict(event), workflow_policy=policy,
                evidence_status='confirmed_unauthorized_bypass' if confirmed else 'authorized_or_completed' if policy else 'information_gap'),
                suppressed='Override đúng chính sách hoặc quy trình đã hoàn thành' if policy and (allowed or not bypass) else '',
                role='transaction' if confirmed else 'context', confirmed=confirmed))
        # F3 duplicate numbers: actual distinct documents, not duplicate log rows.
        current = book.at('document_register', cid, now, 'transaction_id', tid)
        for doc in current:
            issued = self.issued_documents(cid, doc['series_id'], staff, now)
            peers = [d for d in issued if int(d['document_number']) == int(doc['document_number']) and d['document_id'] != doc['document_id']]
            if doc in issued and peers:
                checks.append(dict(rule_id='F3', evidence=dict(kind='duplicate_number', document=dict(doc), conflicting_documents=peers),
                    suppressed='', role='context', confirmed=True))
                break
        # One row/rule; F2 may contain several independent bypass events.
        combined = {}
        for check in checks:
            code = check['rule_id']
            if code not in combined:
                combined[code] = check
            else:
                old = combined[code]
                evidence = old['evidence'].get('events', [old['evidence']])
                old['evidence'] = dict(events=[*evidence, check['evidence']])
                old['confirmed'] = old['confirmed'] or check['confirmed']
                if old['confirmed']:
                    old.update(suppressed='', role='transaction')
                    old['evidence']['evidence_status'] = 'confirmed_condition'
                elif not old['suppressed'] or not check['suppressed']:
                    old.update(suppressed='', role='context')
                    old['evidence']['evidence_status'] = 'information_gap'
        return list(combined.values())

    def issued_documents(self, cid, series, staff, now):
        cancelled = {r['document_id'] for r in self.book.at('document_cancellations', cid, now, 'series_id', series)
            if self.approved(r, cid, now)}
        return [d for d in self.book.at('document_register', cid, now, 'series_id', series)
            if d.get('state') == 'issued' and d.get('evidence_id') and d['issued_at'] <= d['observed_at'] <= now and d['document_id'] not in cancelled]

    def snapshot(self, cid, staff, now):
        """As-of source findings; missing documents/debts have no arbitrary row owner."""
        if not self.has_diagnostics or self.last_snapshot.get(cid) == now:
            return
        self.last_snapshot[cid] = now
        book = self.book
        for series in book.at('document_series', cid, now):
            if not self.approved(series, cid, now) or series.get('closed_at', '9999') > now:
                continue
            start, end = int(series['start_number']), int(series['closed_through_number'])
            if not 0 < start <= end or end-start > 100000:
                raise ValueError('Invalid declared document series range')
            issued = self.issued_documents(cid, series['series_id'], staff, now)
            cancelled = [r for r in book.at('document_cancellations', cid, now, 'series_id', series['series_id']) if self.approved(r, cid, now)]
            accounted = {int(d['document_number']) for d in issued} | {int(d['document_number']) for d in cancelled}
            gaps = sorted(set(range(start, end+1)) - accounted)
            known = series.get('cancellation_log_complete') in {1, '1'}
            self.findings.append(dict(rule_id='F3', company_id=cid, cutoff_at=now, scope=f"series:{series['series_id']}",
                status='evaluated' if known else 'information_gap', signal=bool(gaps) if known else None, points=0, action='source_review_only', evidence=dict(series=dict(series), missing_numbers=gaps, cancellations=cancelled)))
        invoices = book.at('receivable_invoices', cid, now)
        allocations = book.at('receipt_allocations', cid, now)
        receipt_totals = defaultdict(int)
        for allocation in allocations:
            if allocation.get('status') == 'verified':
                receipt_totals[allocation['receipt_transaction_id']] += int(allocation['amount_vnd'])
        for invoice in invoices:
            if invoice.get('status') != 'issued' or not invoice.get('evidence_id') or invoice['issued_at'] > invoice['observed_at'] or invoice['issued_at'] > now:
                continue
            overdue = (parse(now).date()-parse(invoice['due_at']).date()).days
            customer_known = any(c['recorded_at'] <= now for c in self.customers[(cid, invoice['customer_id'])])
            coverage = [c for c in book.at('receipt_coverage', cid, now) if self.approved(c, cid, now) and c['covered_through'] <= c['observed_at'] and
                        c['covered_from'] <= invoice['issued_at'] and c['covered_through'] >= now]
            paid, invalid = 0, []
            used = []
            for allocation in allocations:
                if allocation.get('invoice_id') != invoice['invoice_id'] or allocation.get('status') != 'verified':
                    continue
                receipt = self.transactions.get(allocation.get('receipt_transaction_id'))
                valid = bool(receipt and receipt['company_id'] == cid and receipt['customer_id'] == invoice['customer_id'] and
                    receipt['txn_type'] == 'customer_receipt' and int(receipt['is_financial_entry']) and receipt['payment_channel'] in {'bank', 'cash'} and
                    receipt['posted_at'] <= allocation.get('verified_at', '') <= allocation['observed_at'] <= now and verified_document(allocation, self.staff_at(allocation.get('verified_at','')), cid, now) and
                    int(allocation['amount_vnd']) > 0 and receipt_totals[receipt['transaction_id']] <= int(receipt['amount_vnd']))
                if valid:
                    paid += int(allocation['amount_vnd'])
                    used.append(allocation)
                else:
                    invalid.append(allocation['allocation_id'])
            outstanding = max(0, int(invoice['gross_vnd'])-paid)
            explanations = [e for e in book.at('receivable_explanations', cid, now, 'invoice_id', invoice['invoice_id'])
                if self.approved(e, cid, now) and e.get('reason') in {'payment_plan', 'dispute', 'credit_note_pending'} and
                e['effective_from'] <= now <= e['expires_at']]
            known = bool(coverage and not invalid and customer_known and int(invoice['gross_vnd']) > 0 and invoice['due_at'] >= invoice['issued_at'])
            signal = bool(known and overdue > self.config['receivable_overdue_days'] and outstanding > 0 and not explanations)
            self.findings.append(dict(rule_id='F4', company_id=cid, cutoff_at=now, scope=f"invoice:{invoice['invoice_id']}",
                status='evaluated' if known else 'information_gap', signal=signal if known else None, points=0, action='collection_review_only',
                evidence=dict(invoice=dict(invoice), known_paid_vnd=paid, outstanding_vnd=outstanding, overdue_days=overdue,
                    receipt_allocations=used, invalid_allocation_ids=invalid, receipt_coverage=coverage, approved_explanations=explanations)))
