"""Supported: labelled item sections and explicit column headers with spatial rows.

Unrecognized tables remain UNKNOWN. Completeness needs an explicit row count.
"""
import re
from .invoice_fields import values_on_page,normalize_field
from .candidates import make_candidate,choose,provenance
from .contracts import ExtractionIssue
from ..canonicalization.normalize import key,vat_values
from ..domain.field import FieldObject
from ..domain.cfr import Item
from .spatial_tables import discover_spatial

ITEM_ALIASES={
 'description':('ten hang','ten hang hoa','description'),
 'quantity':('so luong','quantity','qty'),
 'unit_price':('don gia','unit price'),
 'net':('tien truoc thue','thanh tien','net amount'),
 'vat':('thue suat / nhom','thue suat','vat','vat rate'),
}

def discover_rows(document,issues):
    rows=[]
    for page in document.pages:
        native=tuple(b.model_copy(update={'origins':tuple(o for o in b.origins if o.method=='NATIVE_TEXT')})
                     for b in page.blocks if any(o.method=='NATIVE_TEXT' for o in b.origins))
        if native and any(any(o.method=='OCR' for o in b.origins) for b in page.blocks):
            native_page=page.model_copy(update={'blocks':native})
            native_rows=discover_rows(document.model_copy(update={'pages':(native_page,)}),[])
            if native_rows:
                rows.extend(native_rows)
                issues.append(ExtractionIssue(code='HYBRID_TABLE_REVIEW',message='Native table structure retained; OCR table observations still require review.'))
                continue
        blocks=sorted(page.blocks,key=lambda b:b.reading_order)
        starts=[n for n,b in enumerate(blocks) if re.fullmatch(r'(mat hang|item)\s+\d+(?:\s+.*|:.*)?',key(b.text_raw))]
        if starts:
            for pos,start in enumerate(starts):
                end=starts[pos+1] if pos+1<len(starts) else len(blocks)
                segment=page.model_copy(update={'blocks':tuple(blocks[start:end])})
                marker=blocks[start];obs=list(values_on_page(segment,ITEM_ALIASES))
                # Marker and its value share a visual line in the synthetic profile.
                prefix=re.match(r'(?:\S+\s+\S+\s+\d+|\S+\s+\d+)(?=$|[\s:])',marker.text_raw)
                inline=marker.text_raw[prefix.end():].strip(' :') if prefix else ''
                if inline: obs=[('description',inline,(marker,))]+obs
                else:
                    marker_alias={'description':(key(marker.text_raw),)}
                    obs=list(values_on_page(segment,marker_alias))+obs
                rows.append((marker.block_id,obs))
            continue
        # Column headers must be explicit, separate blocks on one line.
        headers={}
        for b in blocks:
            for name,labels in ITEM_ALIASES.items():
                if key(b.text_raw) in labels and b.evidence: headers.setdefault(name,[]).append(b)
        if not all(k in headers for k in ('description','net','vat')):
            rows.extend(discover_spatial(page));continue
        first=headers['description'][0]
        center=lambda b:(b.evidence.bbox[1]+b.evidence.bbox[3])/2
        aligned={name:min(vals,key=lambda b:abs(center(b)-center(first))) for name,vals in headers.items()}
        if any(abs(center(b)-center(first))>0.02 for b in aligned.values()):
            rows.extend(discover_spatial(page));continue
        columns=sorted(aligned.items(),key=lambda pair:pair[1].evidence.bbox[0])
        cuts=[(columns[n][1].evidence.bbox[2]+columns[n+1][1].evidence.bbox[0])/2 for n in range(len(columns)-1)]
        body=[b for b in blocks if b.evidence and b.evidence.bbox[1]>max(h.evidence.bbox[3] for h in aligned.values())]
        bands=[]
        for b in sorted(body,key=lambda b:center(b)):
            if any(key(b.text_raw).startswith(k) for k in ('tong thanh toan','cong truoc thue','subtotal','grand total','so dong','total items')): break
            if not bands or abs(center(b)-center(bands[-1][0]))>max(0.008,(b.evidence.bbox[3]-b.evidence.bbox[1])*0.6): bands.append([])
            bands[-1].append(b)
        for band in bands:
            cells={name:[] for name,_ in columns}
            for b in band:
                x=(b.evidence.bbox[0]+b.evidence.bbox[2])/2
                col=sum(x>cut for cut in cuts);cells[columns[col][0]].append(b)
            if not cells['description']: continue
            if not cells['net'] and not cells['vat']:
                # Continuation belongs only to a preceding row on this page.
                if rows and rows[-1][0] in {b.block_id for b in blocks}:
                    previous=rows[-1][1]
                    for n,(name,raw,refs) in enumerate(previous):
                        if name=='description': previous[n]=(name,raw+' '+ ' '.join(b.text_raw for b in cells['description']),refs+tuple(cells['description']))
                continue
            obs=[(name,' '.join(b.text_raw for b in sorted(cell,key=lambda b:b.evidence.bbox[0])),tuple(cell)) for name,cell in cells.items() if cell]
            rows.append((cells['description'][0].block_id,obs))
    if not rows:
        issues.append(ExtractionIssue(code='TABLE_NOT_DISCOVERED',message='No supported item rows; empty items do not prove an empty table.'))
    return rows

def build_items(rows,identity,profile,issues):
    items=[];candidates=[]
    ids={e.anchor_id:e.item_id for e in identity.entries}
    for line,(anchor,observations) in enumerate(rows,1):
        prefix='items.'+ids[anchor];by={name:[] for name in ('description','quantity','unit_price','net','vat_treatment','vat_rate')}
        for name,raw,blocks in observations:
            if name=='vat':
                variants=vat_values(raw)
                if not variants: issues.append(ExtractionIssue(code='UNPARSEABLE_VAT',field_path=prefix,message='VAT label could not be parsed.'))
                for treatment,rate in variants:
                    by['vat_treatment'].append(make_candidate(prefix+'.vat_treatment',raw,treatment,blocks))
                    if rate is not None: by['vat_rate'].append(make_candidate(prefix+'.vat_rate',raw,rate,blocks))
            else:
                normalized=normalize_field(prefix+'.'+name,raw,profile)
                if not normalized: issues.append(ExtractionIssue(code='UNPARSEABLE_ITEM',field_path=prefix+'.'+name,
                    message='Item cell failed the explicit parser.',block_refs=tuple(b.block_id for b in blocks)))
                for value in normalized:
                    by[name].append(make_candidate(prefix+'.'+name,raw,value,blocks))
        fields={}
        for name,values in by.items():
            fields[name],marked=choose(prefix+'.'+name,values,issues);candidates.extend(marked)
        if fields['vat_treatment'].value in ('KCT','KKKNT'):
            fields['vat_rate']=FieldObject(status='NOT_APPLICABLE',source='document',provenance=provenance(by['vat_treatment']))
        # JSON validation converts exact decimal strings without float intermediates.
        payload={name:value.model_dump(mode='json') for name,value in fields.items()}
        items.append(Item.model_validate({'item_id':ids[anchor],'line_number':line,**payload}))
    return tuple(items),candidates
