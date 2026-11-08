import re
from datetime import date
from decimal import Decimal
from ..canonicalization.normalize import exact_sum,exact_product,date_values,currency_values,tax_values,money_values
from .contracts import QualityIssue

def issue(code,path,message,field=None,*,severity='WARNING',classification='QUALITY',action='VERIFY_SOURCE',evidence=None,source_block_refs=()):
    return QualityIssue(code=code,field_path=path,severity=severity,classification=classification,action=action,message=message,
        evidence=tuple(evidence if evidence is not None else field.provenance.evidence if field else ()),source_block_refs=tuple(source_block_refs))

def raw_valid(path,raw):
    if path.endswith('tax_id'): return bool(tax_values(raw))
    if path.endswith('issue_date'): return bool(date_values(raw,'AUTO'))
    if path=='currency': return len(currency_values(raw))==1
    if path.startswith('totals.') or path.endswith(('.net','.unit_price','.quantity')): return bool(money_values(raw))
    return bool(raw.strip())

def validate_raw(path,raw,*,source_confirmed=False,evidence=()):
    if raw_valid(path,raw): return 'VALID',()
    classification='INVALID_SOURCE_CONTENT' if source_confirmed else 'INVALID_EXTRACTION'
    status='INVALID_SOURCE_CONTENT' if source_confirmed else 'UNKNOWN'
    return status,(issue(classification,path,'Unparseable observed content; source invalidity requires independent fidelity proof.',
        severity='ERROR',classification=classification,action='VERIFY_SOURCE' if source_confirmed else 'REEXTRACT',evidence=evidence),)

def validate_field(path,field):
    if field is None or field.status in ('MISSING','AMBIGUOUS'): return 'UNKNOWN'
    if field.status=='NOT_APPLICABLE': return 'NOT_APPLICABLE'
    if field.status=='NOT_PROVIDED_BY_SOURCE': return 'NOT_CHECKED'
    value=field.value
    if path.endswith('tax_id'): return 'VALID' if tax_values(value) else 'UNKNOWN'
    if path.endswith('issue_date'): return 'VALID' if isinstance(value,date) else 'UNKNOWN'
    if path=='currency': return 'VALID' if currency_values(value)==(value,) else 'UNKNOWN'
    if isinstance(value,Decimal): return 'VALID' if value.is_finite() else 'UNKNOWN'
    return 'VALID' # Shape/format only, never legal correctness or OCR fidelity.

def consistency(record):
    issues=[]
    get=lambda field:field.value if field else None
    net,vat,gross=(get(getattr(record.totals,n)) for n in ('net','vat','gross'))
    if all(v is not None for v in (net,vat,gross)) and exact_sum((net,vat))!=gross:
        ev=tuple(e for n in ('net','vat','gross') for e in getattr(record.totals,n).provenance.evidence)
        issues.append(issue('HEADER_TOTAL_MISMATCH','totals.gross','Observed net + VAT differs from observed gross; check the source.',
            severity='ERROR',classification='UNKNOWN',evidence=ev))
    for name in ('net','vat','gross'):
        observed=get(getattr(record.totals,name));derived=get(getattr(record.derived.totals,name))
        if observed is not None and derived is not None and observed!=derived:
            issues.append(issue('ITEM_TOTAL_MISMATCH','totals.'+name,'Observed and item-derived totals differ; values remain unchanged.',
                getattr(record.totals,name),severity='ERROR',classification='UNKNOWN'))
    for item in record.items:
        q,p,n=(get(getattr(item,name)) for name in ('quantity','unit_price','net'))
        if all(v is not None for v in (q,p,n)) and exact_product(q,p)!=n:
            issues.append(issue('ROW_AMOUNT_MISMATCH','items.'+item.item_id+'.net','Quantity times unit price differs from net; no rounding policy applied.',
                item.net,classification='UNKNOWN'))
    return issues
