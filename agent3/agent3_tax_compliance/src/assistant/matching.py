"""Step 4: match purchase invoices to outgoing bank transactions. Deterministic; ambiguity goes to a person.

A match needs an exact amount (within 1 dong) and a seller signal: the transfer goes to the bank account printed
on the invoice, or names the seller / its tax id, or quotes the invoice number. Amount alone is AMBIGUOUS.
"""
from datetime import timedelta
from decimal import Decimal
from itertools import combinations

from ..extraction.xml_context import fold, similarity
from .models import BankTxn, InvoiceFact, Match

ONE = Decimal(1)
SIGNAL_RANK = {'ACCOUNT': 0, 'NAME_OR_TAX_ID': 1, 'INVOICE_NUMBER': 2}


def seller_signal(inv: InvoiceFact, txn: BankTxn) -> str | None:
    if inv.seller_account and txn.counterparty_account and inv.seller_account == txn.counterparty_account:
        return 'ACCOUNT'
    text = fold(f'{txn.counterparty_name or ""} {txn.description}')
    if inv.seller_tax_id and inv.seller_tax_id.replace('-', '') in text.replace(' ', ''):
        return 'NAME_OR_TAX_ID'
    if inv.seller_name and txn.counterparty_name and similarity(inv.seller_name, txn.counterparty_name) >= 0.8:
        return 'NAME_OR_TAX_ID'
    number = str(int(inv.number)) if inv.number and inv.number.isdigit() else None
    if number and len(number) >= 2 and number in text.split():
        return 'INVOICE_NUMBER'
    return None


def _in_window(inv, txn, before, after):
    return inv.issue_date - timedelta(days=before) <= txn.booked <= inv.issue_date + timedelta(days=after)


def match_payments(invoices: list[InvoiceFact], txns: list[BankTxn], thresholds: dict, decisions: dict) -> list[Match]:
    before, after = thresholds['match_days_before_invoice'], thresholds['match_days_after_invoice']
    max_parts = thresholds['split_payment_max_parts']
    out, used = [], set()
    pending = sorted((i for i in invoices if i.role == 'PURCHASE' and not i.duplicate_of and i.gross and i.gross > 0 and i.issue_date),
                     key=lambda i: (i.issue_date, i.key))
    debits = sorted((t for t in txns if t.direction == 'OUT'), key=lambda t: (t.booked, t.txn_id))

    remaining = []
    for inv in pending:                                   # human decisions first
        d = decisions.get(inv.key)
        if d and '_scopes' in d:
            d = d['_scopes'].get('payment')
        if d and d['action'] == 'PAYMENT_EVIDENCE_ATTACHED':
            tids = tuple(d.get('txn_ids', ()))
            valid = all(t in {x.txn_id for x in debits} for t in tids)
            if not valid or used.intersection(tids):
                remaining.append(inv)
                continue
            used.update(tids)
            out.append(Match((inv.key,), tids, 'MATCHED', 'DECISION', f'{d["evidence"]} (xác nhận bởi {d["by"]})'))
        else:
            remaining.append(inv)

    # 1. one transfer, one invoice. Assigned globally: the closest pair wins, so two invoices of the same seller and
    #    the same amount do not steal each other's payment.
    pairs = []
    for inv in remaining:
        for t in debits:
            if t.txn_id in used:
                continue
            if not _in_window(inv, t, before, after) or abs(t.amount - inv.gross) > ONE:
                continue
            sig = seller_signal(inv, t)
            if sig:
                gap = (t.booked - inv.issue_date).days
                pairs.append((SIGNAL_RANK[sig], abs(gap), gap < 0, inv.issue_date, inv.key, t.txn_id, sig))
    done = set()
    for _, _, _, _, ikey, tid, sig in sorted(pairs):
        if ikey in done or tid in used:
            continue
        done.add(ikey)
        used.add(tid)
        out.append(Match((ikey,), (tid,), 'MATCHED', sig))
    unmatched = [inv for inv in remaining if inv.key not in done]

    left = []
    for inv in unmatched:                                 # 2. several transfers to the seller for one invoice
        cands = [t for t in debits if t.txn_id not in used and _in_window(inv, t, before, after) and seller_signal(inv, t)
                 and t.amount < inv.gross][:12]
        found = None
        for k in range(2, max_parts + 1):
            for combo in combinations(cands, k):
                if abs(sum(t.amount for t in combo) - inv.gross) <= ONE:
                    found = combo
                    break
            if found:
                break
        if found:
            used.update(t.txn_id for t in found)
            out.append(Match((inv.key,), tuple(t.txn_id for t in found), 'MATCHED', 'SPLIT_PAYMENTS', f'{len(found)} lần chuyển'))
        else:
            left.append(inv)

    still = set(i.key for i in left)                      # 3. one transfer settling several invoices of one seller
    for t in debits:
        if t.txn_id in used:
            continue
        group = [i for i in left if i.key in still and _in_window(i, t, before, after) and seller_signal(i, t)][:10]
        for k in range(2, min(len(group), 6) + 1):
            combo = next((c for c in combinations(group, k) if abs(sum(i.gross for i in c) - t.amount) <= ONE), None)
            if combo:
                used.add(t.txn_id)
                still.difference_update(i.key for i in combo)
                out.append(Match(tuple(i.key for i in combo), (t.txn_id,), 'MATCHED', 'COMBINED_PAYMENT', f'{k} hóa đơn'))
                break

    for inv in (i for i in left if i.key in still):       # 4. amount only: a person must confirm
        cands = [t for t in debits if t.txn_id not in used and _in_window(inv, t, before, after) and abs(t.amount - inv.gross) <= ONE]
        if cands:
            out.append(Match((inv.key,), tuple(t.txn_id for t in cands), 'AMBIGUOUS', 'AMOUNT_ONLY',
                             'cùng số tiền nhưng không có tài khoản, tên, mã số thuế hay số hóa đơn của người bán'))
    return out
