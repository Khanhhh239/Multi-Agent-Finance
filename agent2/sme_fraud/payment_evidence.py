"""Bound purchase/payment evidence and cumulative limits; no truth inputs."""
from collections import defaultdict
from datetime import date

from .generate import parse
from .exception_validation import validated_tables
from .temporal_evidence import approved_evidence, bank_token, EmployeeHistory
from .noise_policy import verified_document
from .spec_policy import bank_identity


REQUEST_COLUMNS = ('request_id', 'company_id', 'vendor_id', 'purchase_order_id',
                   'contract_id', 'invoice_number', 'txn_type', 'total_vnd',
                   'status', 'evidence_on_file', 'evidence_id', 'approver_id',
                   'approved_at', 'observed_at')
SOURCE_IDS = {'payment_requests': 'request_id', 'procurement_links': 'link_id',
              'transaction_documents': 'record_id', 'supplier_payment_agreements': 'agreement_id',
              'recurring_payments': 'pattern_id', 'vendor_payment_schedules': 'schedule_id'}
SOURCE_REQUIRED = {
    'payment_requests': REQUEST_COLUMNS,
    'procurement_links': ('link_id', 'company_id', 'vendor_id', 'transaction_id', 'request_id',
                          'purchase_order_id', 'status', 'evidence_id', 'verifier_id',
                          'verified_at', 'observed_at'),
    'transaction_documents': ('record_id', 'company_id', 'vendor_id', 'transaction_id',
                              'document_type', 'status', 'evidence_id', 'verifier_id',
                              'verified_at', 'observed_at'),
    'supplier_payment_agreements': ('agreement_id', 'company_id', 'vendor_id', 'contract_id',
                                    'total_vnd', 'status', 'evidence_on_file', 'evidence_id',
                                    'approver_id', 'approved_at', 'observed_at'),
    'recurring_payments': ('pattern_id', 'company_id', 'vendor_id', 'txn_type',
                           'frequency', 'expected_amount_vnd', 'tolerance_vnd', 'effective_from',
                           'effective_to', 'status', 'evidence_on_file', 'evidence_id',
                           'approver_id', 'approved_at', 'observed_at'),
    'vendor_payment_schedules': ('schedule_id', 'company_id', 'vendor_id', 'txn_type',
                                 'schedule_type', 'window_start_mmdd', 'window_end_mmdd',
                                 'expected_amount_vnd', 'tolerance_vnd', 'allow_partial',
                                 'effective_from', 'effective_to', 'status', 'evidence_on_file',
                                 'evidence_id', 'approver_id', 'approved_at', 'observed_at'),
}


def disbursement(row):
    return bool(int(row['is_financial_entry']) and row['payment_channel'] in {'bank', 'cash'}
                and row['txn_type'] != 'customer_receipt')


def positive(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


class PaymentEvidence:
    """Versions are selected before filtering their bindings, so revocations win.

    All prior cash/bank disbursements consume caps, across makers and recipients.
    Batch totals reserve authority once without ordering equal-time transactions.
    """
    def __init__(self, tables):
        tables = validated_tables(tables, SOURCE_IDS)
        for name, required in SOURCE_REQUIRED.items():
            for record in tables.get(name, []):
                missing = set(required) - set(record)
                if missing:
                    raise ValueError(f'Incomplete payment evidence schema {name}: {sorted(missing)}')
        self.streams, self.positions, self.known = {}, {}, {}
        self.by_entity, self.by_transaction = {}, {}
        for name, identity in SOURCE_IDS.items():
            rows = sorted(tables.get(name, []), key=lambda r: (r['observed_at'], r[identity]))
            bindings, revisions = {}, {}
            for record in rows:
                key = record['company_id'], record[identity]
                if not record[identity]:
                    raise ValueError(f'Empty payment evidence ID: {name}/{identity}')
                binding = tuple(record.get(k, '') for k in ('vendor_id', 'employee_id', 'transaction_id',
                    'request_id', 'purchase_order_id', 'contract_id', 'invoice_number', 'document_type',
                    'txn_type', 'frequency', 'schedule_type', 'window_start_mmdd', 'window_end_mmdd'))
                if key in bindings and bindings[key] != binding:
                    raise ValueError(f'Payment evidence binding changed: {name}/{key}')
                bindings[key] = binding
                version = key, record['observed_at']
                if version in revisions and revisions[version] != record:
                    raise ValueError(f'Conflicting payment evidence revision: {name}/{version}')
                revisions[version] = record
            self.streams[name], self.positions[name], self.known[name] = rows, 0, defaultdict(dict)
            self.by_entity[name], self.by_transaction[name] = defaultdict(set), defaultdict(set)
        self.employee_history = EmployeeHistory(tables['employees'])
        self.transactions = {r['transaction_id']: r for r in tables['transactions']}
        self.history = defaultdict(list)
        self.batch = []

    def staff_at(self, at):
        return self.employee_history.at(at)

    def advance(self, now, batch):
        for name, rows in self.streams.items():
            index, identity = self.positions[name], SOURCE_IDS[name]
            while index < len(rows) and rows[index]['observed_at'] <= now:
                record = rows[index]
                cid, source_id = record['company_id'], record[identity]
                self.known[name][cid][source_id] = record
                entity = record.get('vendor_id') or record.get('employee_id') or ''
                self.by_entity[name][(cid, entity)].add(source_id)
                if record.get('transaction_id'):
                    self.by_transaction[name][(cid, record['transaction_id'])].add(source_id)
                index += 1
            self.positions[name] = index
        self.batch = [r for r in batch if disbursement(r)]

    def records(self, name, row):
        cid, entity = row['company_id'], row['vendor_id'] or row['employee_id'] or ''
        records = self.known[name].get(cid, {})
        return [records[source_id] for source_id in self.by_entity[name].get((cid, entity), ())]

    def transaction_records(self, name, row):
        cid = row['company_id']
        records = self.known[name].get(cid, {})
        return [records[source_id] for source_id in self.by_transaction[name].get((cid, row['transaction_id']), ())]

    def strong_purchase_for(self, row):
        cid = row['company_id']
        return bool(self.known['payment_requests'].get(cid)) or any(
            record.get('document_type') == 'invoice' and
            bank_token(record.get('invoice_number')) and
            positive(record.get('invoice_gross_vnd'))
            for record in self.known['transaction_documents'].get(cid, {}).values())

    def approved(self, record, row, now):
        return bool(approved_evidence(record, self.staff_at(record.get('approved_at', '')), row['company_id'], now)
                    and record['approver_id'] != row['creator_id']
                    and record['approved_at'] <= row['created_at'])

    def verified(self, record, transaction, now):
        return bool(verified_document(record, self.staff_at(record.get('verified_at', '')),
                                      transaction['company_id'], now)
                    and record['verifier_id'] != transaction['creator_id'])

    @staticmethod
    def recipient_ok(record, row):
        if not record.get('recipient_account'):
            return True
        expected = bank_identity(record['recipient_account'], record.get('recipient_bank_code', ''))
        actual = bank_identity(row['recipient_account'], row.get('recipient_bank_code', ''))
        return bool(expected and expected == actual)

    def payments(self, row):
        return [*self.history.get((row['company_id'], row['vendor_id'] or row['employee_id']), []),
                *(r for r in self.batch if r['company_id'] == row['company_id'] and
                  (r['vendor_id'] or r['employee_id']) == (row['vendor_id'] or row['employee_id']))]

    def invoice(self, row, now):
        number = bank_token(row['invoice_number'])
        if not number:
            return None
        linked = [r for r in self.payments(row) if bank_token(r['invoice_number']) == number]
        gross = positive(row['invoice_gross_vnd'])
        if not gross or any(positive(r['invoice_gross_vnd']) != gross for r in linked):
            return None
        paid = sum(int(r['amount_vnd']) for r in linked)
        if paid > gross:
            return None
        proofs = []
        for record in self.records('transaction_documents', row):
            tx = self.transactions.get(record.get('transaction_id'))
            if (record.get('document_type') == 'invoice' and tx and tx['posted_at'] <= now and
                    tx['company_id'] == row['company_id'] and tx['vendor_id'] == row['vendor_id'] and
                    bank_token(tx['invoice_number']) == number and bank_token(record.get('invoice_number')) == number and
                    positive(record.get('invoice_gross_vnd')) == gross and self.verified(record, tx, now)):
                proofs.append(record)
        if not proofs:
            return None
        return dict(invoice_number=row['invoice_number'], invoice_gross_vnd=gross,
                    cumulative_paid_vnd=paid, evidence_ids=sorted({r['evidence_id'] for r in proofs}))

    def procurement(self, row, now):
        records = [r for r in self.transaction_records('procurement_links', row) if r.get('request_id') and
                   r.get('purchase_order_id') and self.verified(r, row, now)]
        if len(records) != 1:
            return None
        record = records[0]
        for field in ('contract_id', 'invoice_number'):
            if record.get(field) and bank_token(record[field]) != bank_token(row.get(field)):
                return None
        return record

    def request(self, row, now, invoice):
        link = self.procurement(row, now)
        if not link or not invoice:
            return None
        request = self.known['payment_requests'].get(row['company_id'], {}).get(link['request_id'])
        if not request or request.get('vendor_id') != row['vendor_id'] or not self.approved(request, row, now):
            return None
        if request.get('txn_type') != row['txn_type'] or request.get('purchase_order_id') != link['purchase_order_id']:
            return None
        for field in ('contract_id', 'invoice_number'):
            if request.get(field) and bank_token(request[field]) != bank_token(row.get(field)):
                return None
        if not self.recipient_ok(request, row):
            return None
        payments = []
        # Unverified/revoked links still consume the named request's budget.
        for tx in self.payments(row):
            links = self.transaction_records('procurement_links', tx)
            if any(r.get('request_id') == request['request_id'] for r in links):
                payments.append(tx)
        total = sum(int(r['amount_vnd']) for r in payments)
        ceiling = positive(request.get('total_vnd'))
        if not ceiling or total > ceiling:
            return None
        # Changing request IDs cannot bypass a shared purchase order's ceiling.
        related = [r for r in self.records('payment_requests', row) if
                   r.get('purchase_order_id') == request['purchase_order_id'] and r.get('status') == 'approved']
        if len({r['request_id'] for r in related}) > 1:
            return None
        return dict(basis='approved_request', request_id=request['request_id'], purchase_order_id=request['purchase_order_id'],
                    contract_id=request.get('contract_id', ''), authorized_total_vnd=ceiling, cumulative_paid_vnd=total,
                    evidence_ids=[request['evidence_id'], link['evidence_id'], *invoice['evidence_ids']])

    def agreement(self, row, now, invoice):
        contract = row.get('contract_id', '')
        if not contract or not invoice:
            return None
        records = [r for r in self.records('supplier_payment_agreements', row) if r.get('contract_id') == contract]
        # Multiple agreement IDs for one contract cannot be selected opportunistically.
        if len(records) != 1 or not self.approved(records[0], row, now) or not self.recipient_ok(records[0], row):
            return None
        record = records[0]
        if record.get('invoice_number') and bank_token(record['invoice_number']) != bank_token(row['invoice_number']):
            return None
        payments = [r for r in self.payments(row) if r.get('contract_id') == contract]
        total = sum(int(r['amount_vnd']) for r in payments)
        ceiling = positive(record.get('total_vnd'))
        if not ceiling or total > ceiling:
            return None
        for tx in payments:
            if not self.invoice(tx, now):
                return None
        return dict(basis='approved_contract', contract_id=contract, agreement_id=record['agreement_id'],
                    authorized_total_vnd=ceiling, cumulative_paid_vnd=total,
                    evidence_ids=[record['evidence_id'], *invoice['evidence_ids']])

    @staticmethod
    def period(timestamp, frequency):
        date = parse(timestamp).date()
        if frequency == 'monthly':
            return timestamp[:7]
        if frequency == 'quarterly':
            return f'{date.year}-Q{(date.month-1)//3+1}'
        if frequency == 'yearly':
            return str(date.year)
        if frequency == 'weekly':
            iso = date.isocalendar()
            return f'{iso.year}-W{iso.week:02}'
        return ''

    def recurring(self, row, now):
        patterns = []
        for record in self.records('recurring_payments', row):
            if record.get('txn_type') != row['txn_type'] or not self.approved(record, row, now):
                continue
            if not record.get('effective_from', '')[:10] <= now[:10] <= record.get('effective_to', '9999')[:10]:
                continue
            if record.get('contract_id') and record['contract_id'] != row.get('contract_id'):
                continue
            if row.get('recurring_pattern_id') and row['recurring_pattern_id'] != record['pattern_id']:
                continue
            if record.get('invoice_number') and bank_token(record['invoice_number']) != bank_token(row['invoice_number']):
                continue
            if not self.recipient_ok(record, row):
                continue
            patterns.append(record)
        if len(patterns) != 1:
            return None
        record = patterns[0]
        period = self.period(now, record.get('frequency'))
        if not period:
            return None
        expected, tolerance = positive(record.get('expected_amount_vnd')), positive(record.get('tolerance_vnd', 0))
        amount = int(row['amount_vnd'])
        partial = str(record.get('allow_partial', '0')) == '1'
        if not expected or (not partial and abs(amount-expected) > tolerance):
            return None
        payments = [r for r in self.payments(row) if self.period(r['posted_at'], record['frequency']) == period and
            (r.get('contract_id') == record['contract_id'] if record.get('contract_id') else r['txn_type'] == row['txn_type'])]
        total = sum(int(r['amount_vnd']) for r in payments)
        if total > expected+tolerance:
            return None
        # An invoice's paid cap still constrains periodic authority when present.
        if row['invoice_number']:
            same_invoice = [r for r in self.payments(row) if bank_token(r['invoice_number']) == bank_token(row['invoice_number'])]
            gross = positive(row['invoice_gross_vnd'])
            if not gross or any(positive(r['invoice_gross_vnd']) != gross for r in same_invoice) or sum(int(r['amount_vnd']) for r in same_invoice) > gross:
                return None
        return dict(basis='approved_recurring', pattern_id=record['pattern_id'], contract_id=record.get('contract_id', ''),
                    billing_period=period, frequency=record['frequency'], allow_partial=partial,
                    authorized_total_vnd=expected+tolerance, cumulative_paid_vnd=total, evidence_ids=[record['evidence_id']])

    @staticmethod
    def schedule_window(timestamp, start, end):
        """Return the annual occurrence containing timestamp, including year-wrap seasons."""
        try:
            start_month, start_day = map(int, start.split('-'))
            end_month, end_day = map(int, end.split('-'))
            current = parse(timestamp).date()
            start_key, end_key = (start_month, start_day), (end_month, end_day)
            current_key = (current.month, current.day)
            if start_key <= end_key:
                lower, upper = date(current.year, start_month, start_day), date(current.year, end_month, end_day)
            elif current_key >= start_key:
                lower, upper = date(current.year, start_month, start_day), date(current.year + 1, end_month, end_day)
            else:
                lower, upper = date(current.year - 1, start_month, start_day), date(current.year, end_month, end_day)
        except (AttributeError, TypeError, ValueError):
            return None
        return (lower, upper) if lower <= current <= upper else None

    def dormancy_schedule(self, row, now):
        """Approved annual/seasonal occurrence for B6 with a cumulative period cap."""
        patterns = []
        for record in self.records('vendor_payment_schedules', row):
            if record.get('schedule_type') not in {'annual', 'seasonal'}:
                continue
            if record.get('txn_type') != row['txn_type'] or not self.approved(record, row, now):
                continue
            if not record.get('effective_from', '')[:10] <= now[:10] <= record.get('effective_to', '')[:10]:
                continue
            if record.get('contract_id') and record['contract_id'] != row.get('contract_id'):
                continue
            if record.get('invoice_number') and bank_token(record['invoice_number']) != bank_token(row['invoice_number']):
                continue
            if not self.recipient_ok(record, row):
                continue
            occurrence = self.schedule_window(now, record.get('window_start_mmdd'), record.get('window_end_mmdd'))
            if occurrence:
                patterns.append((record, occurrence))
        if len(patterns) != 1:
            return None
        record, (lower, upper) = patterns[0]
        expected = positive(record.get('expected_amount_vnd'))
        tolerance = positive(record.get('tolerance_vnd', 0))
        partial = str(record.get('allow_partial', '0')) == '1'
        amount = int(row['amount_vnd'])
        if not expected or (not partial and abs(amount - expected) > tolerance):
            return None
        payments = [tx for tx in self.payments(row)
                    if tx['txn_type'] == row['txn_type']
                    and lower <= parse(tx['posted_at']).date() <= upper
                    and (tx.get('contract_id') == record['contract_id']
                         if record.get('contract_id') else True)]
        total = sum(int(tx['amount_vnd']) for tx in payments)
        if total > expected + tolerance:
            return None
        invoice = None
        if record.get('invoice_number'):
            invoice = self.invoice(row, now)
            if not invoice:
                return None
        return dict(basis='approved_vendor_payment_schedule', schedule_id=record['schedule_id'],
                    schedule_type=record['schedule_type'], occurrence_from=lower.isoformat(),
                    occurrence_through=upper.isoformat(), allow_partial=partial,
                    authorized_total_vnd=expected + tolerance, cumulative_paid_vnd=total,
                    invoice_check=invoice, evidence_ids=[record['evidence_id']])

    def dormancy_exception(self, row, now):
        recurring = self.recurring(row, now)
        if recurring and recurring.get('frequency') == 'yearly':
            return dict(**recurring, transaction_id=row['transaction_id'])
        scheduled = self.dormancy_schedule(row, now)
        return dict(**scheduled, transaction_id=row['transaction_id']) if scheduled else None

    def exemption(self, row, now):
        if not disbursement(row) or not row['vendor_id']:
            return None
        invoice = self.invoice(row, now)
        proof = self.request(row, now, invoice) or self.agreement(row, now, invoice) or self.recurring(row, now)
        if proof:
            return dict(**proof, invoice_check=invoice, transaction_id=row['transaction_id'])
        return None

    def scope(self, row, group, now):
        retained, excluded = [], []
        for tx in group:
            proof = self.exemption(tx, now)
            if proof:
                excluded.append(proof)
            else:
                retained.append(tx)
        return retained, excluded, self.exemption(row, now)

    def shared_obligation(self, row, group, now):
        current = self.procurement(row, now)
        if not current:
            return False
        return any((link := self.procurement(tx, now)) and
                   (link['request_id'] == current['request_id'] or link['purchase_order_id'] == current['purchase_order_id'])
                   for tx in group)

    def commit(self, row):
        if disbursement(row):
            self.history[(row['company_id'], row['vendor_id'] or row['employee_id'])].append(row)
