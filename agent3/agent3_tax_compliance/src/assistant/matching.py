"""Step 4: match purchase invoices to outgoing bank transactions. Deterministic; ambiguity goes to a person.

A match needs an exact amount (within 1 dong, or with a bundled interbank transfer fee up to 55,000 VND when a valid
seller signal is present) and a seller signal: the transfer goes to the bank account printed on the invoice, or names
the seller / its tax id (10-digit enterprise, 13-digit branch, or 12-digit CCCD), or quotes the invoice number with
context. Amount alone is AMBIGUOUS.
"""
import re
import unicodedata
from datetime import timedelta
from decimal import Decimal
from itertools import combinations

from ..extraction.xml_context import fold, similarity
from .models import BankTxn, InvoiceFact, Match

ONE = Decimal(1)
MAX_BANK_FEE = Decimal(55_000)  # Interbank CITAD / Napas transfer fee tolerance when seller_signal is present
SIGNAL_RANK = {'ACCOUNT': 0, 'NAME_OR_TAX_ID': 1, 'INVOICE_NUMBER': 2}

# Explicit invoice markers required before short (1..3 digit) or year-like (1990..2099) invoice numbers
_MARKER_HEAD = r'(?:thanh\s+toan\s+hd|tt\s+hd|so\s+hd|hoa\s+don(?:\s+so)?|hdon|hd|inv|invoice|bill)'
_LIST_LINK = r'(?:0*\d{1,8}\s*(?:[,;&+\-]|\bva\b|\bvoi\b|\s)\s*){0,5}'


def _fold_keep_punct(text: str) -> str:
    t = unicodedata.normalize('NFD', (text or '').replace('đ', 'd').replace('Đ', 'D'))
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r'[^a-z0-9#:/.,;&+\-]+', ' ', t.casefold()).split())


def _seller_tax_id_in_text(seller_tax_id: str | None, raw_text: str) -> bool:
    """Match 10-digit enterprise MST, 13-digit branch MST (10-3 or 13), and 12-digit CCCD MST on digit boundaries."""
    if not seller_tax_id:
        return False
    clean = seller_tax_id.replace('-', '').strip()
    if not clean.isdigit() or len(clean) not in (10, 12, 13):
        return False
    if len(clean) == 12:
        return bool(re.search(rf'(?<!\d){re.escape(clean)}(?!\d)', raw_text))
    if len(clean) == 13:
        parent10, branch3 = clean[:10], clean[10:]
        # Match exact branch MST (0100109106-001 or 0100109106001) OR standalone parent 10-digit MST (not another branch)
        if re.search(rf'(?<!\d){parent10}[-\s]?{branch3}(?!\d)', raw_text):
            return True
        return bool(re.search(rf'(?<!\d){parent10}(?![-\s]?\d)', raw_text))
    # len == 10: match standalone 10-digit MST or 13-digit branch of the same enterprise (not inside 12-digit CCCD or 14+ digit account)
    return bool(re.search(rf'(?<!\d){re.escape(clean)}(?:[-\s]?\d{{3}})?(?!\d)', raw_text))


def _strip_non_invoice_numbers(raw_desc: str) -> str:
    """Remove dates, formatted money amounts, percentages, and long account/reference numbers before matching SHDon."""
    s = _fold_keep_punct(raw_desc)
    # Strip ISO dates (2026-10-12, 2026/08/12) and DD/MM/YYYY or DD-MM-YY dates
    s = re.sub(r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b', ' ', s)
    s = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', ' ', s)
    s = re.sub(r'\b(?:ngay|ng|date)\s*\d{1,2}[/-]\d{1,2}\b', ' ', s)
    s = re.sub(r'\b(?:thang|quy|nam)\s*\d{1,2}[/-]20\d{2}\b', ' ', s)
    s = re.sub(r'\b(?:nam)\s*20\d{2}\b', ' ', s)
    # Strip formatted currency amounts (e.g. 12.000.000, 105,000, 5.500.000,00) and currency-suffixed numbers
    s = re.sub(r'\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?\b', ' ', s)
    s = re.sub(r'\b\d+\s*(?:vnd|dong|trieu|tr|ty|nghin|ngan)\b', ' ', s)
    # Strip percentages (e.g. 10%, 8%)
    s = re.sub(r'\b\d+(?:[.,]\d+)?\s*%', ' ', s)
    # Strip bank account / FT / reference codes and 9+ digit sequences (SHDon in QD 1450 has at most 8 digits)
    s = re.sub(r'\b(?:tk|stk|tai\s+khoan|ft|ibft|ref|ma\s+gd)\s*[:#\-]?\s*[a-z0-9\-]{6,}\b', ' ', s)
    s = re.sub(r'(?<!\d)\d{9,}(?!\d)', ' ', s)
    return s


def _invoice_number_in_description(inv: InvoiceFact, txn: BankTxn) -> bool:
    if not inv.number or not inv.number.strip().isdigit():
        return False
    raw_num = inv.number.strip()
    number = str(int(raw_num))
    cleaned = _strip_non_invoice_numbers(txn.description or '')

    # Explicit invoice marker pattern (e.g. "HD 12", "TT HD 523 524", "INV#0012", "SO HD: 105", "BILL-12")
    marker_pat = rf'\b{_MARKER_HEAD}(?:\s+so)?(?:\s*[#:\-.]\s*|\s+|(?=\d)){_LIST_LINK}0*{re.escape(number)}\b'
    if re.search(marker_pat, cleaned):
        return True

    # Full zero-padded SHDon of >= 5 characters (e.g. "00000012") on clean boundaries
    if len(raw_num) >= 5 and raw_num.startswith('0') and re.search(rf'(?<![\d/.,\-]){re.escape(raw_num)}(?![\d/.,\-])', cleaned):
        return True

    # Short invoice numbers (1..3 digits) or 4-digit calendar years (1990..2099) NEVER match bare tokens without a marker
    if len(number) <= 3 or (len(number) == 4 and 1990 <= int(number) <= 2099):
        return False

    # Longer invoice numbers (4..8 digits, non-year): must stand on clean word/digit boundaries and not equal the transfer amount
    if str(int(txn.amount)) == number:
        return False
    return bool(re.search(rf'(?<![\d/.,\-])0*{re.escape(number)}(?![\d/.,\-])', cleaned))


def seller_signal(inv: InvoiceFact, txn: BankTxn) -> str | None:
    if inv.seller_account and txn.counterparty_account and inv.seller_account == txn.counterparty_account:
        return 'ACCOUNT'
    raw_combined = f'{txn.counterparty_name or ""} {txn.description or ""}'
    if _seller_tax_id_in_text(inv.seller_tax_id, raw_combined):
        return 'NAME_OR_TAX_ID'
    if inv.seller_name and txn.counterparty_name and similarity(inv.seller_name, txn.counterparty_name) >= 0.8:
        return 'NAME_OR_TAX_ID'
    if _invoice_number_in_description(inv, txn):
        return 'INVOICE_NUMBER'
    return None


def _in_window(inv, txn, before, after):
    return inv.issue_date - timedelta(days=before) <= txn.booked <= inv.issue_date + timedelta(days=after)


def _amount_match_with_fee(debit_total: Decimal, gross_total: Decimal) -> tuple[bool, Decimal]:
    """Return (matched, fee). Exact within 1 VND has fee=0; bundled bank fee allows 0 < debit - gross <= 55,000 VND."""
    diff = debit_total - gross_total
    if abs(diff) <= ONE:
        return True, Decimal(0)
    if ONE < diff <= MAX_BANK_FEE:
        return True, diff
    return False, Decimal(0)


def _fee_note(fee: Decimal, base_note: str = '') -> str:
    if fee <= 0:
        return base_note
    fee_txt = f'gồm phí chuyển khoản ngân hàng {int(fee):,} đồng'.replace(',', '.')
    return f'{base_note} ({fee_txt})' if base_note else fee_txt


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

    # 1. one transfer, one invoice. Exact amount matches win before fee-inclusive matches, then signal rank & date gap.
    pairs = []
    for inv in remaining:
        for t in debits:
            if t.txn_id in used or not _in_window(inv, t, before, after):
                continue
            amt_ok, fee = _amount_match_with_fee(t.amount, inv.gross)
            if not amt_ok:
                continue
            sig = seller_signal(inv, t)
            if sig:
                gap = (t.booked - inv.issue_date).days
                pairs.append((fee > 0, SIGNAL_RANK[sig], abs(gap), gap < 0, fee, inv.issue_date, inv.key, t.txn_id, sig))
    done = set()
    for _, _, _, _, fee, _, ikey, tid, sig in sorted(pairs):
        if ikey in done or tid in used:
            continue
        done.add(ikey)
        used.add(tid)
        out.append(Match((ikey,), (tid,), 'MATCHED', sig, _fee_note(fee)))
    unmatched = [inv for inv in remaining if inv.key not in done]

    left = []
    for inv in unmatched:                                 # 2. several transfers to the seller for one invoice
        cands = [t for t in debits if t.txn_id not in used and _in_window(inv, t, before, after) and seller_signal(inv, t)
                 and t.amount < inv.gross + MAX_BANK_FEE][:12]
        found, found_fee = None, Decimal(0)
        for allow_fee in (False, True):
            for k in range(2, max_parts + 1):
                for combo in combinations(cands, k):
                    total_debit = sum(t.amount for t in combo)
                    if not allow_fee and abs(total_debit - inv.gross) <= ONE:
                        found, found_fee = combo, Decimal(0)
                        break
                    if allow_fee and ONE < total_debit - inv.gross <= MAX_BANK_FEE:
                        found, found_fee = combo, total_debit - inv.gross
                        break
                if found:
                    break
            if found:
                break
        if found:
            used.update(t.txn_id for t in found)
            out.append(Match((inv.key,), tuple(t.txn_id for t in found), 'MATCHED', 'SPLIT_PAYMENTS',
                             _fee_note(found_fee, f'{len(found)} lần chuyển')))
        else:
            left.append(inv)

    still = set(i.key for i in left)                      # 3. one transfer settling several invoices of one seller
    for t in debits:
        if t.txn_id in used:
            continue
        group = [i for i in left if i.key in still and _in_window(i, t, before, after) and seller_signal(i, t)][:10]
        matched_combo, combo_fee = None, Decimal(0)
        for allow_fee in (False, True):
            for k in range(2, min(len(group), 6) + 1):
                for c in combinations(group, k):
                    total_gross = sum(i.gross for i in c)
                    if not allow_fee and abs(t.amount - total_gross) <= ONE:
                        matched_combo, combo_fee = c, Decimal(0)
                        break
                    if allow_fee and ONE < t.amount - total_gross <= MAX_BANK_FEE:
                        matched_combo, combo_fee = c, t.amount - total_gross
                        break
                if matched_combo:
                    break
            if matched_combo:
                break
        if matched_combo:
            used.add(t.txn_id)
            still.difference_update(i.key for i in matched_combo)
            out.append(Match(tuple(i.key for i in matched_combo), (t.txn_id,), 'MATCHED', 'COMBINED_PAYMENT',
                             _fee_note(combo_fee, f'{len(matched_combo)} hóa đơn')))

    for inv in (i for i in left if i.key in still):       # 4. amount only: a person must confirm
        cands = [t for t in debits if t.txn_id not in used and _in_window(inv, t, before, after) and abs(t.amount - inv.gross) <= ONE]
        if cands:
            out.append(Match((inv.key,), tuple(t.txn_id for t in cands), 'AMBIGUOUS', 'AMOUNT_ONLY',
                             'cùng số tiền nhưng không có tài khoản, tên, mã số thuế hay số hóa đơn của người bán'))
    return out
