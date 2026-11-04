"""Context guards for signed XML invoices: buyer versus taxpayer profile (V5-buyer), vendor history (V3, V5) and
replacement / adjustment references (V10).

Two kinds of output, both ExtractionIssue values so that replay stays deterministic:
  XML_REVIEW_*   a deviation a human must look at (assessor severity WARNING, never silently accepted)
  XML_CONTEXT_*  an explicit record of what could NOT be judged (UNAVAILABLE) or was judged and passed
Observations that depend on stored state (history, references) are stored on the artifact and replayed
through `extra_issues`; buyer checks depend only on the pinned taxpayer master and are recomputed.

Thresholds are engineering proposals pending calibration on real vendor history and tax-expert review.
"""
import re
import unicodedata
from datetime import datetime
from decimal import Decimal

from ..domain.taxpayer import identity_match
from .contracts import ExtractionIssue
from .xml_invoice import extract

MIN_HISTORY = 5               # prior distinct invoices of a seller before the amount outlier test is applied
OUTLIER_MAD_K = Decimal(5)    # robust z-score limit: (x - median) / (1.4826 * MAD)
OUTLIER_RATIO = Decimal(3)    # fallback when MAD is zero: x greater than ratio times the median
MAD_SCALE = Decimal('1.4826')
NAME_SIMILARITY = 0.8
ADDRESS_SIMILARITY = 0.6

STORED_PREFIXES = ('XML_CHECK_DUPLICATE', 'XML_CHECK_RELATED_MISMATCH', 'XML_REVIEW_VENDOR_', 'XML_REVIEW_RELATED_',
                   'XML_CONTEXT_VENDOR_', 'XML_CONTEXT_AMOUNT_')


def stored_observations(issues):
    """Issues that came from stored state and must be replayed as explicit inputs (buyer checks are recomputed)."""
    return tuple(i for i in issues if i.code.startswith(STORED_PREFIXES))


def fold(text):
    """Diacritic-insensitive, case-insensitive, punctuation-free form of a Vietnamese text."""
    t = unicodedata.normalize('NFD', (text or '').replace('đ', 'd').replace('Đ', 'D'))
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', t.casefold()).split())


def similarity(a, b):
    x, y = set(fold(a).split()), set(fold(b).split())
    return len(x & y) / len(x | y) if x and y else 0.0


def _issue(code, path, message):
    return ExtractionIssue(code=code, field_path=path, message=message)


def _date(text):
    try:
        return datetime.strptime(text or '', '%Y-%m-%d').date()
    except ValueError:
        return None


# ----------------------------------------------------------------------------- buyer versus taxpayer profile
def buyer_profile_issues(fields, master, relations=(), on_date=None):
    f = lambda k: fields[k].value  # noqa: E731
    buyer_tax = (f('buyer_tax_id') or '').replace('-', '')
    canonical = master.model_copy(update={'tax_code': master.tax_code.replace('-', '')})
    canonical_relations = tuple(r.model_copy(update={'parent_tax_code': r.parent_tax_code.replace('-', ''),
                                                     'branch_tax_code': r.branch_tax_code.replace('-', '')}) for r in relations)
    match = identity_match(buyer_tax, canonical, on_date, canonical_relations) if buyer_tax else 'UNKNOWN'
    name_hit = bool(master.legal_name and f('buyer_name') and similarity(f('buyer_name'), master.legal_name) >= NAME_SIMILARITY)
    out = []
    if match == 'MATCH':
        if master.legal_name:
            if not f('buyer_name'):
                out.append(_issue('XML_REVIEW_BUYER_NAME', 'parties.buyer.name', 'Buyer name is missing although the buyer tax code is the taxpayer.'))
            elif not name_hit:
                out.append(_issue('XML_REVIEW_BUYER_NAME', 'parties.buyer.name',
                                  'Buyer name differs from the registered legal name of the taxpayer.'))
        else:
            out.append(_issue('XML_CONTEXT_BUYER_NAME_UNAVAILABLE', None, 'Taxpayer profile has no legal name; buyer name not checked.'))
        if master.registered_address:
            if not f('buyer_address'):
                out.append(_issue('XML_REVIEW_BUYER_ADDRESS', 'parties.buyer.address', 'Buyer address is missing.'))
            elif similarity(f('buyer_address'), master.registered_address) < ADDRESS_SIMILARITY:
                out.append(_issue('XML_REVIEW_BUYER_ADDRESS', 'parties.buyer.address',
                                  'Buyer address differs from the registered address of the taxpayer.'))
        else:
            out.append(_issue('XML_CONTEXT_BUYER_ADDRESS_UNAVAILABLE', None, 'Taxpayer profile has no registered address; buyer address not checked.'))
        if not out:
            out.append(_issue('XML_CONTEXT_BUYER_CHECKED', None, 'Buyer name and address agree with the taxpayer profile.'))
        return out
    if buyer_tax and on_date and buyer_tax[:10] == canonical.tax_code[:10]:
        return [_issue('XML_REVIEW_BUYER_BRANCH_UNRESOLVED', 'parties.buyer.tax_id',
                       'Buyer tax code shares the taxpayer prefix but no registered branch relation covers it.')]
    if name_hit and buyer_tax:
        return [_issue('XML_REVIEW_BUYER_TAX_ID_MISMATCH', 'parties.buyer.tax_id',
                       'Buyer name equals the taxpayer legal name but the buyer tax code differs.')]
    if name_hit:
        return [_issue('XML_REVIEW_BUYER_TAX_ID_MISSING', 'parties.buyer.tax_id',
                       'Buyer name equals the taxpayer legal name but the invoice carries no buyer tax code.')]
    return [_issue('XML_CONTEXT_BUYER_NOT_TAXPAYER', None, 'Buyer is not the taxpayer; profile check not applicable.')]


# ----------------------------------------------------------------------------- vendor history (V3, V5) and references (V10)
def _median(values):
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def amount_outlier(history, amount):
    """True when `amount` is unusually large against the seller's prior invoice totals (robust, no distribution assumed)."""
    med = _median(history)
    mad = _median([abs(x - med) for x in history])
    scaled = MAD_SCALE * mad
    if scaled > 0:
        return amount > med + OUTLIER_MAD_K * scaled
    return med > 0 and amount > OUTLIER_RATIO * med


def _norm_number(n):
    return str(int(n)) if n and n.isdigit() else n


def history_rows(db, ctx, payer, ingestion_id, seller_tax_id):
    """Prior distinct invoices of this seller, one row per (symbol, number), oldest first."""
    rows = db.execute("SELECT ingestion_id,"
                      "json_extract(payload,'$.record.record_id') AS record_id,"
                      "json_extract(payload,'$.record.parties.seller.name.value') AS name,"
                      "json_extract(payload,'$.record.invoice.series.value') AS series,"
                      "json_extract(payload,'$.record.invoice.number.value') AS number,"
                      "json_extract(payload,'$.record.invoice.issue_date.value') AS issued,"
                      "json_extract(payload,'$.record.totals.gross.value') AS gross "
                      "FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id!=? "
                      "AND json_extract(payload,'$.record.parties.seller.tax_id.value')=? ORDER BY rowid",
                      (ctx.tenant_id, payer, ingestion_id, seller_tax_id)).fetchall()
    seen, out = set(), []
    for r in rows:
        key = (r['series'], _norm_number(r['number']))
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(r))
    return out


def vendor_and_reference_issues(fields, history, other_names):
    """Pure rule evaluation. `history`: prior rows of the same seller; `other_names`: folded names seen under other tax codes."""
    f = lambda k: fields[k].value  # noqa: E731
    out = []
    # V5 vendor identity
    if not history:
        out.append(_issue('XML_CONTEXT_VENDOR_FIRST_SEEN', 'parties.seller.tax_id', 'No earlier invoice from this seller; vendor identity not comparable.'))
    else:
        known = {r['name'] for r in history if r['name']}
        if f('seller_name') and known and not any(similarity(f('seller_name'), k) >= NAME_SIMILARITY for k in known):
            out.append(_issue('XML_REVIEW_VENDOR_NAME_CHANGED', 'parties.seller.name',
                              'Seller name differs from every earlier invoice with this tax code: ' + '; '.join(sorted(known))[:300]))
    if f('seller_name') and any(similarity(f('seller_name'), n) >= NAME_SIMILARITY for n in other_names):
        out.append(_issue('XML_REVIEW_VENDOR_NAME_OTHER_TAX_ID', 'parties.seller.name',
                          'The same seller name appears on earlier invoices under a different tax code.'))
    # V3 amount against vendor history
    try:
        gross = Decimal(f('gross_total')) if f('gross_total') else None
    except ArithmeticError:
        gross = None
    amounts = []
    for r in history:
        try:
            amounts.append(Decimal(r['gross']))
        except (TypeError, ArithmeticError):
            pass
    if gross is None or len(amounts) < MIN_HISTORY:
        out.append(_issue('XML_CONTEXT_AMOUNT_HISTORY_INSUFFICIENT', 'totals.gross',
                          f'{len(amounts)} earlier invoices from this seller; at least {MIN_HISTORY} are needed to judge the amount.'))
    elif amount_outlier(amounts, gross):
        out.append(_issue('XML_REVIEW_VENDOR_AMOUNT_OUTLIER', 'totals.gross',
                          f'Payable total {gross} is far above the usual range of this seller ({len(amounts)} earlier invoices, median {_median(amounts)}).'))
    else:
        out.append(_issue('XML_CONTEXT_AMOUNT_HISTORY_SUFFICIENT', 'totals.gross', f'Payable total is within the range of {len(amounts)} earlier invoices.'))
    # V10 replacement / adjustment reference
    if f('related_nature'):
        kind = 'Replaces' if f('related_nature') == '1' else 'Adjusts'
        series = (f('related_template') or '') + (f('related_symbol') or '')
        target = next((r for r in history if r['series'] == series and _norm_number(r['number']) == _norm_number(f('related_number'))), None)
        if target is None:
            out.append(_issue('XML_REVIEW_RELATED_NOT_CAPTURED', 'invoice.number',
                              f'{kind} invoice {series}/{f("related_number")} dated {f("related_date")}, which has not been captured; its effect cannot be checked.'))
        elif target['issued'] != f('related_date'):
            out.append(_issue('XML_CHECK_RELATED_MISMATCH', 'invoice.number',
                              f'Referenced invoice {series}/{f("related_number")} was captured with issue date {target["issued"]}, not {f("related_date")}.'))
        else:
            out.append(_issue('XML_REVIEW_RELATED_FOUND', 'invoice.number',
                              f'{kind} captured record {target["record_id"]}; the original must not be counted again.'))
    return out


def stored_state_issues(db, ctx, payer, ingestion_id, raw):
    fields = extract(raw).fields
    seller = fields['seller_tax_id'].value
    if not seller:
        return ()
    history = history_rows(db, ctx, payer, ingestion_id, seller)
    names = db.execute("SELECT DISTINCT json_extract(payload,'$.record.parties.seller.name.value') AS name FROM cfr_extractions "
                       "WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id!=? "
                       "AND json_extract(payload,'$.record.parties.seller.tax_id.value')!=? LIMIT 5000",
                       (ctx.tenant_id, payer, ingestion_id, seller)).fetchall()
    return tuple(vendor_and_reference_issues(fields, history, [n['name'] for n in names if n['name']]))
