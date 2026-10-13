"""No float money, silent locale guessing or implicit rounding."""
from datetime import date
from decimal import Decimal, localcontext
import re
import unicodedata


def key(text):
    text=unicodedata.normalize('NFD',text.casefold().replace('đ','d'))
    text=''.join(c for c in text if not unicodedata.combining(c))
    text=re.sub(r'\s*/\s*',' / ',text)
    return ' '.join(text.split()).strip(' :')


def plain(value): return format(value,'f')


def money_values(raw,locale='AUTO'):
    value=unicodedata.normalize('NFKC',raw).strip().replace('\u2212','-')
    value=re.sub(r'\s*(VND|USD|EUR|đ|₫)\s*$','',value,flags=re.I).strip()
    negative=value.startswith('(') and value.endswith(')')
    if negative: value=value[1:-1].strip()
    if value.startswith(('+','-')):
        if negative: return ()
        negative=value[0]=='-';value=value[1:]
    if len(value)>128 or not re.fullmatch(r'[0-9]+(?:[., ][0-9]+)*',value): return ()
    def parse(decimal,group):
        if value.count(decimal)>1: return None
        whole,sep,fraction=value.partition(decimal)
        if sep and (not fraction.isdigit()): return None
        groups=re.split(re.escape(group)+'| ',whole)
        if len(groups)>1 and (not 1<=len(groups[0])<=3 or any(len(s)!=3 for s in groups[1:])): return None
        if any(not s.isdigit() for s in groups): return None
        joined=''.join(groups)+('.'+fraction if sep else '')
        return Decimal(('-' if negative else '')+joined)
    choices=[]
    for loc in (('VI','EN') if locale=='AUTO' else (locale,)):
        result=parse(',' if loc=='VI' else '.', '.' if loc=='VI' else ',')
        if result is not None and result not in choices: choices.append(result)
    return tuple(plain(v) for v in choices)


def date_values(raw,order='DMY'):
    value=raw.strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): return (date.fromisoformat(value).isoformat(),)
    except ValueError: return ()
    match=re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',value)
    if not match: return ()
    a,b,y=map(int,match.groups());results=[]
    for style in (('DMY','MDY') if order=='AUTO' else (order,)):
        try: parsed=date(y,b,a) if style=='DMY' else date(y,a,b)
        except ValueError: continue
        if parsed.isoformat() not in results: results.append(parsed.isoformat())
    return tuple(results)


def currency_values(raw):
    value=key(raw).upper()
    if value in ('VND','VNĐ','D','₫','DONG','VIET NAM DONG'): return ('VND',)
    if value in ('USD','EUR','GBP','JPY','CNY','AUD','CAD','SGD'): return (value,)
    if value=='$': return ('USD','CAD','AUD','SGD')
    return ()


def tax_values(raw):
    value=re.sub(r'\s+','',raw)
    if not re.fullmatch(r'[0-9]{10}(?:-?[0-9]{3})?',value): return ()
    return (value.replace('-',''),)


def vat_values(raw):
    value=key(raw).replace(' ','')
    if value in ('kct','khongchiuthue'): return (('KCT',None),)
    if value in ('kkknt','khongkekhaitinhnopthue','khongkekhainopthue'): return (('KKKNT',None),)
    match=re.fullmatch(r'(\d+(?:[.,]\d+)?)%',value)
    if match:
        with localcontext() as ctx:
            ctx.prec=160;rate=Decimal(match[1].replace(',','.'))/Decimal('100')
        if 0<=rate<=1: return (('TAXABLE_RATE',plain(rate)),)
    return ()


def exact_sum(values):
    values=tuple(values)
    with localcontext() as ctx:
        ctx.prec=max([len(v.as_tuple().digits)+abs(v.as_tuple().exponent) for v in values]+[1])+len(str(len(values)))+8
        return sum(values,Decimal('0'))


def exact_product(a,b):
    with localcontext() as ctx:
        ctx.prec=len(a.as_tuple().digits)+len(b.as_tuple().digits)+8
        return a*b
