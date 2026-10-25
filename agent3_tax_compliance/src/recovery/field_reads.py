"""Parse a regional observation, preserving abstention and exact identifiers."""
import re
from ..canonicalization.normalize import key,money_values,vat_values
from ..extraction.invoice_fields import ALIASES,clean_label,labelled,normalize_field,values_on_page

TYPED_PATHS=frozenset(('invoice.number','invoice.series','invoice.issue_date','currency',
    'totals.net','totals.vat','totals.gross','parties.seller.tax_id','parties.buyer.tax_id'))

ITEM_TYPED_FIELDS=frozenset(('quantity','unit_price','net','vat_treatment','vat_rate'))


def item_field(path):
    parts=path.split('.')
    return parts[2] if len(parts)==3 and parts[0]=='items' and parts[1] and parts[2] in ITEM_TYPED_FIELDS else None


def is_typed(path):
    return path in TYPED_PATHS or item_field(path) is not None


def item_read(path,texts,profile):
    """One observed cell only; no arithmetic, digit repair or rate guessing."""
    from ..extraction.tables import ITEM_ALIASES
    name=item_field(path)
    target='vat' if name in ('vat_treatment','vat_rate') else name
    values=[]
    for text in texts:
        found,raw=labelled(text.strip(),ITEM_ALIASES)
        if found and found!=target:return None
        raw=raw if found else text.strip()
        if raw:values.append(raw)
    # Multiple nonempty value boxes may be competing columns; never join digits.
    if len(values)!=1:return None
    if target=='vat':
        choices=vat_values(values[0])
        if len(choices)!=1:return None
        treatment,rate=choices[0]
        return treatment if name=='vat_treatment' else rate
    choices=money_values(values[0],profile.number_locale)
    return choices[0] if len(choices)==1 else None


def semantic(path):
    return path.removeprefix('parties.')


def recovery_refs(path,artifact,normalized):
    """Find the failed observation, never invent a rectangle from field names.

    Source roles are resolved by the same extractor on each modality separately.
    No template coordinates, whole-page fallback or cross-party nearest number.
    """
    target=semantic(path);refs=[]
    for issue in artifact.issues:
        if ((issue.code in ('UNPARSEABLE_FIELD','UNPARSEABLE_ITEM') and issue.field_path==target)
                or (issue.code=='UNPARSEABLE_VAT' and item_field(path) in ('vat_treatment','vat_rate')
                    and issue.field_path==path.rsplit('.',1)[0])):
            refs.extend((None,b) for b in issue.block_refs)
    # Other fields on this row are not evidence for an absent numeric cell.
    if item_field(path):return set(refs)
    for page in normalized.pages:
        for method in ('NATIVE_TEXT','OCR'):
            selected=tuple(b for b in page.blocks if any(o.method==method for o in b.origins))
            if not selected:continue
            for found,_,blocks in values_on_page(page.model_copy(update={'blocks':selected}),sections=True):
                if found==target:
                    refs.extend((page.page_index,b.block_id) for b in blocks)
    return set(refs)


def typed_read(path,texts,profile):
    """Return one fully parsed value or abstain; no substring digit salvage."""
    if item_field(path):return item_read(path,texts,profile)
    target=semantic(path)
    if (path.startswith('totals.') or path.endswith('.tax_id') or path=='invoice.issue_date') and len(texts)>1 and sum(bool(normalize_field(target,t.strip(),profile)) for t in texts)>1:
        return None  # Two complete values are competitors, not digit groups.
    aliases=dict(ALIASES)
    if target.endswith('.tax_id'):
        aliases[target]=(*aliases[target],'mst','ma so thue','tax id')
    raw=' '.join(t.strip() for t in texts).strip()
    found,value=labelled(raw,aliases)
    if found is not None:
        if found!=target:return None
        raw=value
    elif path=='invoice.issue_date':
        match=re.fullmatch(r'ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})\s*\)?',key(clean_label(raw)))
        if match:raw='/'.join(match.groups())
    # Invoice identifiers permit letters, but never swallow a whole label,
    # prose or an account number into an apparently valid invoice number.
    if path=='invoice.number' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._-]{0,31}',raw):return None
    values=normalize_field(target,raw,profile)
    return values[0] if len(values)==1 else None


def text_read(path,texts):
    """Remove only observed field labels, not words from a company name.

    Issuer provenance may include the tax anchor as well as the company name;
    that anchor is evidence of the role, not part of the company's name.
    """
    target=semantic(path);aliases=dict(ALIASES)
    if path.startswith('items.') and path.endswith('.description'):
        aliases[target]=('ten hang','ten hang hoa, dich vu','dien giai')
    if target.startswith(('seller.','buyer.')):
        role=target.split('.')[0]
        for name,labels in {'name':('ten don vi','name'),'address':('dia chi','address'),
                            'tax_id':('mst','ma so thue','tax id')}.items():
            aliases[role+'.'+name]=(*aliases[role+'.'+name],*labels)
    values=[]
    for raw in texts:
        found,value=labelled(raw.strip(),aliases)
        if found==target:
            if value:values.append(value)
        elif found:
            # Keep a same-party tax anchor out of a name; crossing roles is
            # never a legitimate name/address continuation.
            if not (target.startswith(('seller.','buyer.')) and found==target.split('.')[0]+'.tax_id'):
                return None
        else:
            values.append(raw.strip())
    return ' '.join(value for value in values if value) or None
