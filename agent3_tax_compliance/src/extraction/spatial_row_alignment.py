"""Align explicit amount columns without inventing cells or row counts."""
import re
from ..canonicalization.normalize import money_values,key


def center(box):
    return (box[1]+box[3])/2


def join_decimal_fragments(entries):
    """Join an observed decimal separator and its adjacent printed digits."""
    ordered=sorted(entries,key=lambda entry:(entry[2][1],entry[2][0]))
    result=[];index=0
    while index<len(ordered):
        raw,refs,box=ordered[index]
        if index+1<len(ordered) and re.search(r'\d[.,]$',raw.strip()):
            following,more,other=ordered[index+1]
            if (re.fullmatch(r'\d{1,2}',following.strip()) and abs(other[0]-box[0])<.004
                    and -.002<=other[1]-box[3]<=.75*(box[3]-box[1])
                    and money_values(raw.strip()+following.strip(),'AUTO')):
                result.append((raw.strip()+following.strip(),refs+more,
                               (min(box[0],other[0]),box[1],max(box[2],other[2]),other[3])))
                index+=2;continue
        result.append((raw,refs,box));index+=1
    return result


def align_amount_rows(headers,body,columns,cuts,is_header):
    """Use observed net cells as anchors when numbered columns are explicit.

    Incomplete/mixed layouts fall back to the existing parser. A one-to-one
    ordered price column can resolve vertical font offsets; it is never used
    to calculate a net cell or infer a quantity/tax rate.
    """
    if not all(name in headers for name in ('_sequence','quantity','unit_price','net')):
        return None
    cells={name:[] for name in columns}
    sequence_right=max(b.evidence.bbox[2] for b in headers['_sequence'][1] if b.evidence)
    for raw,refs,box in body:
        name=columns[sum((box[0]+box[2])/2>cut for cut in cuts)]
        if name=='_sequence' and not re.fullmatch(r'\d+',raw.strip()) and box[0]>=sequence_right-.003:
            name='description'
        cells[name].append((raw,refs,box))
    # Column-number/formula rows must not become financial observations.
    formula_centers=[center(box) for raw,_,box in cells['description']
                     if re.fullmatch(r'\(?\d+\)?',raw.strip())
                     and any(abs(center(other)-center(box))<.004 and re.fullmatch(r'\(?\d+\)?',value.strip())
                             for value,_,other in cells['_sequence'])]
    if formula_centers:
        cells={name:[entry for entry in entries
                     if not any(abs(center(entry[2])-y)<.55*(entry[2][3]-entry[2][1]) for y in formula_centers)]
               for name,entries in cells.items()}
    descriptions=[entry for entry in cells['description']
                  if len(entry[0].strip())>1 and not is_header(entry[0])
                  and not re.fullmatch(r'[()0-9= x+*/.,-]+',entry[0].strip())]
    sequences=[entry for entry in cells['_sequence'] if re.fullmatch(r'\d+',entry[0].strip())]
    if len(sequences)<2 or not descriptions:return None
    prices=join_decimal_fragments(cells['unit_price'])
    amounts=join_decimal_fragments(cells['net'])
    anchors=[]
    for raw,refs,box in amounts:
        if not re.fullmatch(r'[A-Za-z0-9.,+-]+',raw.strip()):continue
        nearby_description=any(abs(center(other)-center(box))<.05 for _,_,other in descriptions)
        valid=bool(money_values(raw,'AUTO'))
        unreadable=(bool(re.fullmatch(r'[A-Za-z][.,]?\d[0-9.,]*',raw.strip()))
                    and any(abs(center(other)-center(box))<.01 for _,_,other in prices)
                    and any(abs(center(other)-center(box))<.01 for _,_,other in cells['quantity']))
        if nearby_description and (valid or unreadable):anchors.append((raw,refs,box))
    anchors.sort(key=lambda entry:center(entry[2]))
    if len(anchors)<2:return None
    if any(center(b[2])-center(a[2])<.5*min(a[2][3]-a[2][1],b[2][3]-b[2][1])
           for a,b in zip(anchors,anchors[1:])):return None
    # Anchor count must agree with distinct printed row markers, allowing a
    # small number of unreadable/missing markers, not an arbitrary new grid.
    markers={raw.strip() for raw,_,_ in sequences}
    if len(anchors)>len(markers)+1:return None
    assigned=[{'net':[(raw,refs)]} for raw,refs,_ in anchors]
    locations=[center(box) for _,_,box in anchors]
    valid_prices=[entry for entry in prices if money_values(entry[0],'AUTO')]
    ordered_prices=(len(valid_prices)==len(anchors)
                    and all(abs(center(price[2])-locations[i])<.025 for i,price in enumerate(valid_prices)))
    description_locations=locations[:]
    if ordered_prices:
        for i,(raw,refs,box) in enumerate(valid_prices):
            assigned[i]['unit_price']=[(raw,refs)]
            description_locations[i]=center(box)
    for name,entries in cells.items():
        if name.startswith('_') or name in ('description','net') or (name=='unit_price' and ordered_prices):continue
        for raw,refs,box in (prices if name=='unit_price' else entries):
            if not re.fullmatch(r'[A-Za-z0-9.,%+-]+',raw.strip()):continue
            i=min(range(len(anchors)),key=lambda n:abs(locations[n]-center(box)))
            gaps=[abs(locations[i]-locations[n]) for n in range(len(anchors)) if n!=i]
            tolerance=min(.025,max(.008,min(gaps)*.55))
            if abs(locations[i]-center(box))<=tolerance:
                assigned[i].setdefault(name,[]).append((raw,refs))
    previous=None;previous_box=None
    for raw,refs,box in sorted(cells['description'],key=lambda entry:(entry[2][1],entry[2][0])):
        if is_header(raw) or re.fullmatch(r'[()0-9= x+*.,-]+',raw.strip()) or len(raw.strip())<=1:continue
        i=min(range(len(anchors)),key=lambda n:abs(description_locations[n]-center(box)))
        if abs(description_locations[i]-center(box))>=.06:continue
        ancillary=key(raw).startswith(('sn:','s/n:','serial:')) or bool(re.fullmatch(r'\([A-Za-z0-9._/-]+\)',raw.strip()))
        if (ancillary and previous is not None and abs(box[0]-previous_box[0])<.015
                and 0<center(box)-center(previous_box)<1.6*max(box[3]-box[1],previous_box[3]-previous_box[1])):
            i=previous
        assigned[i].setdefault('description',[]).append((raw,refs));previous=i;previous_box=box
    if any(not row.get('description') for row in assigned):return None
    result=[]
    for anchor,row in zip(anchors,assigned):
        observations=[]
        for name,entries in row.items():
            observations.append((name,' '.join(raw for raw,_ in entries),tuple(b for _,refs in entries for b in refs)))
        result.append((anchor[1][0].block_id,observations))
    return result
