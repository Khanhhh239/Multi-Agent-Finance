"""Conservative labelled fields. Party roles require explicit label/context."""
import re
from ..canonicalization.normalize import key, money_values, date_values, currency_values, tax_values
from .candidates import make_candidate, choose
from .contracts import ExtractionIssue

ALIASES = {
 'seller.name': ('ten nguoi ban','don vi ban hang','seller name'),
 'seller.tax_id': ('mst nguoi ban','ma so thue nguoi ban','seller tax id'),
 'seller.address': ('dia chi nguoi ban','seller address'),
 'buyer.name': ('ten nguoi mua','don vi mua hang','buyer name'),
 'buyer.tax_id': ('mst nguoi mua','ma so thue nguoi mua','buyer tax id'),
 'buyer.address': ('dia chi nguoi mua','buyer address'),
 'invoice.number': ('so hoa don','invoice number','invoice no'),
 'invoice.series': ('ky hieu','invoice series'),
 'invoice.issue_date': ('ngay lap','ngay hoa don','invoice date'),
 'currency': ('don vi tien te','loai tien','currency'),
 'totals.net': ('cong truoc thue','tong tien chua thue','subtotal'),
 'totals.vat': ('tien thue','tong tien thue','vat amount'),
 'totals.gross': ('tong thanh toan','tong cong thanh toan','grand total'),
 'expected_rows': ('so dong','total items'),
}

def labelled(text, aliases):
    normalized=key(text)
    pairs=sorted(((path,key(label)) for path,labels in aliases.items() for label in labels),key=lambda p:len(p[1]),reverse=True)
    for path,label in pairs:
        if normalized==label: return path,''
        parts=re.split(r'[:：]',text,maxsplit=1)
        if len(parts)==2 and key(parts[0])==label: return path,parts[1].strip()
        # OCR may merge label + value without a colon. Compare complete label
        # prefixes at whitespace boundaries, retaining offsets in the raw text.
        for boundary in re.finditer(r'\s+',text[:128]):
            if key(text[:boundary.start()])==label:
                return path,text[boundary.end():].strip()
    return None,None

def values_on_page(page, aliases=ALIASES, sections=False):
    blocks=sorted(page.blocks,key=lambda b:b.reading_order)
    context=None
    for index,block in enumerate(blocks):
        text=key(block.text_raw)
        if sections:
            if text in ('nguoi ban','seller'): context='seller'
            elif text in ('nguoi mua','buyer'): context='buyer'
        path,inline=labelled(block.text_raw,aliases)
        if path is None and sections and context:
            path,inline=labelled(block.text_raw,{
                context+'.tax_id':('mst','ma so thue','tax id'),
                context+'.name':('ten don vi','name'),context+'.address':('dia chi','address')})
        if path is None: continue
        if inline:
            yield path,inline,(block,)
            continue
        # Pair only blocks immediately to the right on the same visual line.
        if not block.evidence: continue
        x0,y0,x1,y1=block.evidence.bbox
        candidates=[]
        for other in blocks:
            if other.block_id==block.block_id or not other.evidence: continue
            ox0,oy0,ox1,oy1=other.evidence.bbox
            overlap=min(y1,oy1)-max(y0,oy0)
            if ox0>=x1-0.003 and overlap>0.5*min(y1-y0,oy1-oy0):
                if labelled(other.text_raw,aliases)[0] is None:
                    candidates.append(other)
        if candidates:
            nearest=min(candidates,key=lambda b:b.evidence.bbox[0])
            yield path,nearest.text_raw.strip(),(block,nearest)

def normalize_field(path,raw,profile):
    if path.endswith('tax_id'): return tax_values(raw)
    if path=='invoice.issue_date': return date_values(raw,profile.date_order)
    if path.startswith('totals.') or path.endswith(('.net','.quantity','.unit_price')):
        return money_values(raw,profile.number_locale)
    if path=='currency': return currency_values(raw)
    if path=='expected_rows': return (raw,) if re.fullmatch(r'[0-9]{1,5}',raw) else ()
    return (raw.strip(),) if raw.strip() else ()

def extract_headers(document,profile,issues):
    observations={p:[] for p in ALIASES}
    for page in document.pages:
        for path,raw,blocks in values_on_page(page,sections=True):
            normalized=normalize_field(path,raw,profile)
            if not normalized:
                issues.append(ExtractionIssue(code='UNPARSEABLE_FIELD',field_path=path,
                    message='Label found but value failed the explicit parser.',block_refs=tuple(b.block_id for b in blocks)))
            observations[path].extend(make_candidate(path,raw,value,blocks) for value in normalized)
    fields={};candidates=[]
    for path,values in observations.items():
        fields[path],marked=choose(path,values,issues);candidates.extend(marked)
    return fields,candidates
