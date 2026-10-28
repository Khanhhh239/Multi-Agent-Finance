"""Bounded table fallback. Missing tax columns never imply a tax treatment."""
import re
from .invoice_fields import logical_fragments,bounds,fragment_text,header_key,header_observations
from ..canonicalization.normalize import key,money_values

LABELS={
    'description':('ten hang hoa, dich vu','ten hang hoa dich vu','ten hang hoa','dien giai','description','name of goods and services','name of goods services'),
    'quantity':('so luong','so luong tb','quantity','qty','sl'),
    'unit_price':('don gia','unit price'),
    'net':('thanh tien','thanh tien truoc thue','thanh tien chua co thue gtgt','thanh tien truoc thue gtgt','tien dich vu','net amount','amount before vat'),
    'vat':('thue suat','thue suat gtgt','thue suat(%)','vat rate','tax rate'),
    '_unit':('don vi tinh','donvitinh','dvt','unit'),
    '_sequence':('stt','no.'),
    '_vat_amount':('tien thue','tien thue gtgt','vat amount'),
    '_gross':('thanh tien sau thue','thanh tien sau thue gtgt','thanh tien co thue gtgt'),
    '_discount':('tong so tien chiet khau','tong tien chiet khau','total discount'),
}
STOP=('cong tien','tong cong','tong tien','tong thanh toan','cong truoc thue','subtotal','grand total',
      'so tien viet','so tien bang','nguoi mua','nguoi ban','thue suat gtgt:', 'tong hop',
      'loai khong chiu thue','loai thue suat')


def header_name(raw):
    normalized=header_key(raw)
    for name,labels in LABELS.items():
        if normalized and normalized in (header_key(label) for label in labels):return name
    return None


def column_bounds(entry):
    """Estimate layout only for two explicit labels fused by OCR.

    The original blocks/evidence remain unchanged; these sub-boxes are used
    exclusively to locate column boundaries, never as observed value evidence.
    """
    raw,refs=entry
    box=bounds(refs)
    if box and refs:
        original=fragment_text(refs)
        if key(original) in ('thue suat tien thue gtgt','thue suat tien thue') and raw in original:
            start=original.index(raw);width=box[2]-box[0]
            return (box[0]+width*start/len(original),box[1],
                    box[0]+width*(start+len(raw))/len(original),box[3])
    return box


def spatial_headers(page):
    observations=header_observations(page,LABELS)
    for raw,refs in logical_fragments(page):
        if key(raw) in ('thue suat tien thue gtgt','thue suat tien thue'):
            words=list(re.finditer(r'\S+',raw))
            if len(words) in (4,5):
                split=words[2].start()
                observations.extend((('vat',raw[:split].strip(),refs),
                                     ('_vat_amount',raw[split:].strip(),refs)))
    descriptions=[(raw,refs) for name,raw,refs in observations if name=='description' and bounds(refs)]
    if not descriptions:return {}
    first=descriptions[0];first_box=bounds(first[1]);y=(first_box[1]+first_box[3])/2
    headers={}
    for name,raw,refs in observations:
        box=bounds(refs)
        if box and name and abs((box[1]+box[3])/2-y)<.04:
            # Prefer Vietnamese first occurrence over the translated subheader.
            headers.setdefault(name,(raw,refs))
    if not all(name in headers for name in ('description','net')):return {}
    if not any(name in headers for name in ('quantity','unit_price','vat')):return {}
    return headers


def _discover_once(page,inherited_headers=None):
    fragments=logical_fragments(page)
    current=spatial_headers(page);headers=current or inherited_headers
    if not headers:return []
    columns=sorted(headers,key=lambda name:column_bounds(headers[name])[0])
    centers={name:(column_bounds(headers[name])[0]+column_bounds(headers[name])[2])/2 for name in columns}
    cuts=[(centers[a]+centers[b])/2 for a,b in zip(columns,columns[1:])]
    top=max(bounds(refs)[3] for _,refs in headers.values()) if current else 0.
    body=[]
    for raw,refs in fragments:
        box=bounds(refs)
        # OCR boxes can touch the header bottom while the text centre is in
        # the first data row. Testing only the top silently drops that line.
        if not box or (box[1]+box[3])/2<=top:continue
        normalized=key(raw)
        if normalized.startswith(STOP) or normalized in ('cong','tong'):break
        body.append((raw,refs,box))
    from .spatial_row_alignment import align_amount_rows
    aligned=align_amount_rows(headers,body,columns,cuts,header_name)
    if aligned is not None:return aligned
    bands=[]
    for entry in sorted(body,key=lambda row:((row[2][1]+row[2][3])/2,row[2][0])):
        raw,refs,box=entry;center=(box[1]+box[3])/2
        if not bands or abs(center-bands[-1][0])>max(.004,(box[3]-box[1])*.65):
            bands.append((center,[]))
        bands[-1][1].append(entry)
    rows=[];description_lines=[]
    for band_y,band in bands:
        cells={name:[] for name in columns}
        for raw,refs,box in band:
            x=(box[0]+box[2])/2;name=columns[sum(x>cut for cut in cuts)]
            # The sequence header is narrow, while a centred description
            # header can put the midpoint inside the actual description cell.
            # A nonnumeric continuation to its right cannot be an STT value.
            if (name=='_sequence' and not re.fullmatch(r'\d+',raw.strip())
                    and box[0]>=bounds(headers['_sequence'][1])[2]-.003):
                name='description'
            cells[name].append((raw,refs))
        def text(name):return ' '.join(raw for raw,_ in cells.get(name,()))
        desc=text('description')
        borrowed=False
        if not desc and money_values(text('net'),'AUTO'):
            # Detached formula/header fragments or split amount tails must
            # not borrow a nearby description and manufacture another row.
            has_sequence=bool(re.fullmatch(r'\d+',text('_sequence').strip()))
            has_measure=bool(money_values(text('quantity'),'AUTO') or money_values(text('unit_price'),'AUTO'))
            if not has_sequence and not has_measure:continue
            nearby=[]
            for raw,refs,box in body:
                col=columns[sum((box[0]+box[2])/2>cut for cut in cuts)]
                distance=abs((box[1]+box[3])/2-band_y)
                if (col=='description' and distance<.025 and len(raw.strip())>1 and not header_name(raw)
                        and not re.fullmatch(r'[()0-9= x+*/.,-]+',raw.strip())):
                    nearby.append((distance,raw,refs))
            if nearby:
                _,desc,refs=min(nearby,key=lambda row:row[0]);cells['description']=[(desc,refs)];borrowed=True
        if not desc or header_name(desc):continue
        if re.fullmatch(r'[()0-9= x+*/.-]+',desc):
            # A date can be the final line of a service-period description.
            # Keep its observed text for the nearest established row only.
            if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',desc.strip()):
                description_lines.append((band_y,desc,tuple(b for _,bs in cells['description'] for b in bs)))
            continue
        sequence=text('_sequence').strip()
        if sequence and not re.fullmatch(r'\d+',sequence):continue
        if len(desc.strip())<=1:continue
        if not borrowed:description_lines.append((band_y,desc,tuple(b for _,bs in cells['description'] for b in bs)))
        net=text('net')
        numeric=bool(money_values(net,'AUTO'))
        # A printed sequence plus observed quantity/price can establish a row
        # even when its amount is unreadable. Preserve that missing cell;
        # never invent its value by multiplying quantity and price.
        numeric|=bool(sequence and re.fullmatch(r'\d+',sequence) and re.fullmatch(r'[A-Za-z0-9.,+-]+',net.strip())
                      and money_values(text('quantity'),'AUTO') and money_values(text('unit_price'),'AUTO'))
        # Wrapped descriptions may precede or follow the line carrying money.
        if numeric:
            obs=[]
            for name,entries in cells.items():
                if name.startswith('_') or not entries:continue
                raw=' '.join(t for t,_ in entries)
                refs=tuple(b for _,bs in entries for b in bs)
                obs.append((name,raw,refs))
            anchor=next(refs[0].block_id for name,_,refs in obs if name=='description')
            rows.append((anchor,obs,band_y))
    # Amounts are usually vertically centred in a wrapped row. Assign text to
    # the nearest observed row centre rather than always appending to the last
    # row: the first line of row two can precede its centred numeric cells.
    assigned=[[] for row in rows]
    for y,desc,refs in description_lines:
        if not rows:break
        index=min(range(len(rows)),key=lambda i:abs(rows[i][2]-y))
        if abs(rows[index][2]-y)<.05:assigned[index].append((y,desc,refs))
    result=[]
    for (anchor,obs,_),lines in zip(rows,assigned):
        if lines:
            lines.sort(key=lambda line:line[0])
            description=' '.join(raw for _,raw,_ in lines)
            if '_sequence' in headers:description=re.sub(r'^\d+\s+(?=\D)','',description)
            refs=tuple(b for _,_,blocks in lines for b in blocks)
            obs=[(name,raw,bs) for name,raw,bs in obs if name!='description']+[('description',description,refs)]
        result.append((anchor,obs))
    return result


def discover_spatial(page,inherited_headers=None):
    """Partition repeated headers; never merge two table bodies by proximity."""
    anchors=[]
    for raw,refs in logical_fragments(page):
        box=bounds(refs)
        if box and header_name(raw)=='description':
            if not anchors or box[1]-anchors[-1]>.06:anchors.append(box[1])
    if len(anchors)<2:return _discover_once(page,inherited_headers)
    boundaries=[0.]
    for y in anchors[1:]:
        starts=[bounds(refs)[1] for raw,refs in logical_fragments(page)
                if bounds(refs) and header_name(raw) and abs(bounds(refs)[1]-y)<.04]
        boundaries.append(min(starts) if starts else y)
    boundaries.append(1.01);rows=[]
    for low,high in zip(boundaries,boundaries[1:]):
        selected=tuple(b for b in page.blocks if b.evidence and low<=b.evidence.bbox[1]<high)
        rows.extend(_discover_once(page.model_copy(update={'blocks':selected})))
    return rows
