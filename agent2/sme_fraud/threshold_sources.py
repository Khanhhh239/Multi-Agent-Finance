"""Explicit accounting measurements for dynamic thresholds; never truth or ML fields."""
import re

from .dynamic_thresholds import digest, integer, timestamp


def account_code(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{3,12}(?:[.-][A-Za-z0-9]+)*', value):
        raise ValueError('Expense account codes must be explicit strings, retaining subaccounts')
    return value


def expense_account(value):
    return value.startswith(('6', '8', '154'))


def family(purpose):
    if purpose in {'payroll', 'salary_accrual'}:
        return 'payroll'
    if purpose in {'vendor_payment', 'invoice_accrual', 'rent', 'selling_expense'}:
        return 'payables'
    return 'general_expense'


def known_at(row):
    return max(timestamp(row['posted_at']), timestamp(row.get('observed_at') or row['posted_at']))


def extract_observations(tables):
    """One debit measurement per document/account, plus separate cash outflows.

    Ledger debits retain exact expense/cost subaccounts and exclude VAT/assets.
    A 331/334 settlement is a cash measurement, never reclassified as a new
    expense. Without ledger lines, transaction amounts use their own scope.
    """
    records, gaps = [], []
    transactions = {}
    for row in tables.get('transactions', []):
        key = row['company_id'], row['transaction_id']
        if key in transactions and transactions[key] != row:
            raise ValueError('Conflicting transaction in dynamic source')
        transactions[key] = row
    documents = {}
    for row in tables.get('journal_documents', []):
        key = row['company_id'], row['document_id']
        if key in documents and documents[key] != row:
            raise ValueError('Conflicting journal document in dynamic source')
        documents[key] = row
    groups, seen_lines = {}, set()
    for line in tables.get('journal_lines', []):
        company, document = line['company_id'], line['document_id']
        account = account_code(line['account_code'])
        debit, credit = integer(line.get('debit_vnd', 0), 'debit_vnd'), integer(line.get('credit_vnd', 0), 'credit_vnd')
        if debit and credit:
            raise ValueError('A dynamic journal line cannot contain both debit and credit')
        if not debit or not expense_account(account):
            continue
        line_key = (company, document, line.get('line_id') or digest(line))
        if line_key in seen_lines:
            raise ValueError('Ambiguous duplicate expense line; supply stable unique line_id values')
        seen_lines.add(line_key)
        header = documents.get((company, document))
        event_at, observed = timestamp(line['posted_at']), known_at(line)
        if header:
            if timestamp(header['posted_at']) != event_at:
                raise ValueError('Expense line/document posting timestamps differ')
            observed = max(observed, known_at(header))
        tid = line.get('transaction_id') or (header or {}).get('transaction_id', '')
        if line.get('transaction_id') and header and header.get('transaction_id') not in {'', line['transaction_id']}:
            raise ValueError('Expense line/document transaction binding differs')
        transaction = transactions.get((company, tid)) if tid else None
        if tid and transactions and transaction is None:
            raise ValueError('Expense source transaction is missing or cross-company')
        if transaction:
            if not int(transaction['is_financial_entry']) or timestamp(transaction['posted_at']) != event_at:
                raise ValueError('Expense source transaction is nonfinancial or differently dated')
            observed = max(observed, known_at(transaction))
        purpose = (header or {}).get('purpose') or (transaction or {}).get('accounting_purpose') or (transaction or {}).get('txn_type', '')
        key = company, document, account
        if key not in groups:
            groups[key] = dict(observation_id='expense:'+digest(key)[:24], company_id=company,
                account_code=account, measurement='expense_debit', family=family(purpose),
                event_at=event_at, observed_at=observed, amount_vnd=0, currency='VND',
                source_transaction_id=tid, source_ref='journal:'+document+':'+account)
        item = groups[key]
        if item['event_at'] != event_at or item['source_transaction_id'] != tid:
            raise ValueError('Inconsistent expense lines within one document/account')
        item['amount_vnd'] += debit
        item['observed_at'] = max(item['observed_at'], observed)
    records.extend(groups.values())
    has_ledger = bool(tables.get('journal_lines'))
    for key, row in sorted(transactions.items()):
        if not int(row['is_financial_entry']):
            continue
        amount = integer(row['amount_vnd'], 'amount_vnd')
        if not amount:
            continue
        if row.get('currency', 'VND') != 'VND':
            gaps.append(dict(company_id=key[0], transaction_id=key[1], reason='unverified_vnd_amount'))
            continue
        account = account_code(row['debit_account'])
        common = dict(company_id=key[0], account_code=account, family=family(row.get('accounting_purpose') or row['txn_type']),
            event_at=timestamp(row['posted_at']), observed_at=known_at(row), amount_vnd=amount,
            currency='VND', source_transaction_id=key[1], source_ref='transaction:'+key[1])
        if row.get('payment_channel') in {'bank', 'cash'} and str(row.get('credit_account', '')).startswith(('111', '112')):
            records.append(dict(common, observation_id='payment:'+digest(key)[:24], measurement='cash_outflow'))
        if not has_ledger and expense_account(account):
            records.append(dict(common, observation_id='transaction:'+digest(key)[:24], measurement='transaction_amount'))
    records.sort(key=lambda r: (max(r['event_at'], r['observed_at']), r['observation_id']))
    return records, dict(ledger_available=has_ledger, observation_count=len(records), information_gaps=gaps,
                         unit='document_account_debit_or_separate_cash_payment', expense_prefixes=['6', '8', '154'])
