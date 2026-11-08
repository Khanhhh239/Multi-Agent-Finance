"""Conservative labelled fields. Party roles require explicit label/context."""
import re
from ..canonicalization.normalize import key, money_values, date_values, currency_values, tax_values
from .candidates import make_candidate, choose
from .contracts import ExtractionIssue

ALIASES = {
 'seller.name': ('ten nguoi ban','don vi ban hang','don vi ban','seller name'),
 'seller.tax_id': ('mst nguoi ban','ma so thue nguoi ban','seller tax id'),
 'seller.address': ('dia chi nguoi ban','seller address'),
 'buyer.name': ('ten nguoi mua','nguoi mua','don vi mua hang','don vi mua','buyer name','ho ten nguoi mua hang','ten khach hang'),
 'buyer.tax_id': ('mst nguoi mua','ma so thue nguoi mua','buyer tax id'),
 'buyer.address': ('dia chi nguoi mua','buyer address'),
 'invoice.number': ('so hoa don','invoice number','invoice no','so'),
 'invoice.series': ('ky hieu','invoice series'),
 'invoice.issue_date': ('ngay lap','ngay hoa don','invoice date'),
 'currency': ('don vi tien te','loai tien','currency','dong tien thanh toan'),
 'totals.net': ('cong truoc thue','tong tien chua thue','subtotal','cong tien hang','cong tien hang hoa, dich vu'),
 'totals.vat': ('tien thue','tong tien thue','vat amount','tien thue gtgt'),
 'totals.gross': ('tong thanh toan','tong cong thanh toan','grand total','tong cong tien thanh toan','tong tien thanh toan'),
 'expected_rows': ('so dong','total items'),
}

TRANSLATIONS = re.compile(r'\s*\(\s*(?:Seller|Buyer|Tax\s*code|Address|Serial(?:\s*No\.)?|Invoice\s*No\.|No\.|Company(?:\x27s\s*name)?|Customer\x27s\s*Name|Payment\s*currency|Total\s*amount(?:\s*excl\.\s*VAT)?|VAT\s*amount|Total\s*payment|Total\s*of\s*payment|Date|Day|Month|Year)\s*\)\s*', re.I)


def clean_label(text):
    # Known OCR variants of the English address gloss only. Never fuzzy-edit
    # the actual address or accept an arbitrary parenthetical label.
    text=re.sub(r'\(\s*(?:Addres|Addrass)\s*\)', ' ', text, flags=re.I)
    text=re.sub(r'\(\s*Co\.\s*name\s*\)', ' ',text,flags=re.I)
    text=re.sub(r'\(\s*Company\s+name\s*\)', ' ',text,flags=re.I)
    return TRANSLATIONS.sub(' ',text).strip()


def bounds(blocks):
    boxes=[b.evidence.bbox for b in blocks if b.evidence]
    if not boxes: return None
    return (min(b[0] for b in boxes),min(b[1] for b in boxes),
            max(b[2] for b in boxes),max(b[3] for b in boxes))


def fragment_text(group):
    """Use glyph gaps, preserving spaces already present in native runs."""
    result=group[0].text_raw
    for previous,current in zip(group,group[1:]):
        gap=current.evidence.bbox[0]-previous.evidence.bbox[2]
        char_width=(previous.evidence.bbox[2]-previous.evidence.bbox[0])/max(1,len(previous.text_raw))
        separator='' if result.endswith((' ','\n')) or current.text_raw.startswith(' ') or gap<=.25*char_width else ' '
        result+=separator+current.text_raw
    return result.strip()


def logical_fragments(page):
    """Join adjacent native font runs, retaining every original evidence ID."""
    # Font ascent changes the top coordinate within a line. Cluster by actual
    # vertical overlap before sorting left to right (not by rounded top alone).
    lines=[];unboxed=[]
    for block in sorted(page.blocks,key=lambda b:b.reading_order):
        box=bounds((block,))
        if not box: unboxed.append(block);continue
        for line in lines:
            other=bounds(line)
            overlap=min(box[3],other[3])-max(box[1],other[1])
            if overlap>.5*min(box[3]-box[1],other[3]-other[1]):
                line.append(block);break
        else: lines.append([block])
    lines.sort(key=lambda line:bounds(line)[1])
    ordered=[b for line in lines for b in sorted(line,key=lambda b:b.evidence.bbox[0])]+unboxed
    groups=[]
    for block in ordered:
        if not block.text_raw.strip(): continue
        native=all(o.method=='NATIVE_TEXT' for o in block.origins)
        box=bounds((block,))
        target=None
        if native and box:
            for group in reversed(groups):
                other=bounds(group)
                if not other or not all(all(o.method=='NATIVE_TEXT' for o in b.origins) for b in group): continue
                overlap=min(box[3],other[3])-max(box[1],other[1])
                if overlap>.5*min(box[3]-box[1],other[3]-other[1]) and -.003<=box[0]-other[2]<=.012:
                    target=group;break
        if target is None: groups.append([block])
        else: target.append(block)
    return [(fragment_text(group),tuple(group)) for group in groups]


def header_key(text):
    """Whitespace/line wrapping tolerance for labels only, never field values."""
    stripped=re.sub(r'\([^)]*\)', ' ',text)
    if not stripped.strip():stripped=text.strip().strip('()')
    return ''.join(c for c in key(stripped) if c.isalnum())


def header_observations(page,aliases):
    """Assemble complete known column labels from bounded vertical fragments."""
    fragments=logical_fragments(page)
    names={header_key(label):name for name,labels in aliases.items() for label in labels}
    names.pop('',None)
    prefixes={label[:i] for label in names for i in range(1,len(label)+1)}
    prepared=[(i,raw,refs,header_key(raw),bounds(refs)) for i,(raw,refs) in enumerate(fragments)]
    observations=[]
    for index,raw,refs,token,box in prepared:
        if not token or not box or token not in prefixes:continue
        matches=[];frontier=[(token,raw,refs,box,frozenset({index}))]
        for _ in range(4):
            following=[]
            for text,printed,blocks,last,used in frontier:
                if text in names:matches.append((len(text),names[text],printed,blocks))
                for other_index,more,more_refs,addition,other in prepared:
                    if other_index in used:continue
                    if not addition or not other:continue
                    combined=text+addition
                    if combined not in prefixes:continue
                    overlap=min(last[2],other[2])-max(last[0],other[0])
                    width=min(last[2]-last[0],other[2]-other[0])
                    gap=other[1]-last[3]
                    height=min(last[3]-last[1],other[3]-other[1])
                    if (overlap>.4*width and abs((last[0]+last[2]-other[0]-other[2])/2)<.05
                            and -.5*height<=gap<=max(.012,1.2*(last[3]-last[1]))
                            and (other[1]+other[3]-last[1]-last[3])/2>.4*height):
                        following.append((combined,printed+' '+more,blocks+more_refs,other,used|{other_index}))
            # Bound branching on noisy/overlapping OCR. Never search a whole
            # page combinatorially merely to force a recognized label.
            frontier=following[:16]
            if not frontier:break
        if matches:
            _,name,printed,blocks=max(matches,key=lambda match:match[0])
            observations.append((name,printed,tuple({b.block_id:b for b in blocks}.values())))
    return observations


def labelled(text, aliases):
    # Translations are removed from the label only, never from the value.
    parts=re.split(r'[:：]',text,maxsplit=1)
    normalized=key(clean_label(parts[0]))
    pairs=sorted(((path,key(label)) for path,labels in aliases.items() for label in labels),key=lambda p:len(p[1]),reverse=True)
    for path,label in pairs:
        if normalized==label: return path,parts[1].strip() if len(parts)==2 else ''
        if label in ('so','nguoi mua','don vi','don vi ban','don vi mua'): continue  # Section labels require exact matches.
        # OCR may merge label + value without a colon. Compare complete label
        # prefixes at whitespace boundaries, retaining offsets in the raw text.
        for boundary in reversed(list(re.finditer(r'\s+',text[:128]))):
            if key(clean_label(text[:boundary.start()]))==label:
                return path,text[boundary.end():].strip()
    return None,None


def right_values(refs,fragments):
    box=bounds(refs)
    if not box: return []
    x0,y0,x1,y1=box;result=[]
    for raw,blocks in fragments:
        other=bounds(blocks)
        if blocks==refs or not other: continue
        ox0,oy0,ox1,oy1=other
        if ox0>=x1-.003 and min(y1,oy1)-max(y0,oy0)>.5*min(y1-y0,oy1-oy0):
            result.append((ox0,raw.lstrip(':：').strip(),blocks))
    return sorted(result,key=lambda row:row[0])


def party_role(box,anchors,party_end):
    """Assign a block to an explicit party region; ambiguous geometry abstains.

    Side-by-side panels use their column starts. Stacked sections use the last
    preceding anchor. Reading order never decides between two party columns.
    """
    if not box or box[1]>=party_end:return None
    eligible=[(r,b) for r,b in anchors if b[1]<=box[1]+.003]
    if not eligible:return None
    opposing=[(a,b) for a in eligible for b in eligible if a[0]!=b[0] and abs(a[1][0]-b[1][0])>.28 and abs(a[1][1]-b[1][1])<.08]
    if opposing:
        left,right=sorted(opposing[0],key=lambda a:a[1][0])
        boundary=(left[1][0]+right[1][0])/2
        # A block spanning both columns cannot establish a unique party role.
        if box[0]<boundary<box[2] and box[2]-box[0]>.5:return None
        return right[0] if box[0]>=boundary else left[0]
    eligible.sort(key=lambda a:(-a[1][1],abs(a[1][0]-box[0])))
    if len(eligible)>1 and eligible[0][0]!=eligible[1][0] and abs(eligible[0][1][1]-eligible[1][1][1])<.003:return None
    return eligible[0][0]

def values_on_page(page, aliases=ALIASES, sections=False):
    fragments=logical_fragments(page)
    table_tops=[bounds(refs)[1] for raw,refs in fragments if bounds(refs) and header_key(raw) in ('stt','tenhanghoadichvu','diengiai')]
    party_end=min(table_tops) if table_tops else 1.
    role_anchors=[]
    if sections:
        for raw,refs in fragments:
            path,_=labelled(raw,ALIASES);box=bounds(refs)
            role=path.split('.')[0] if path in ('seller.name','buyer.name') else None
            if key(clean_label(raw)) in ('nguoi ban','seller'):role='seller'
            if key(clean_label(raw)) in ('nguoi mua','buyer'):role='buyer'
            if role and box:role_anchors.append((role,box))
    # An unlabelled issuer block is accepted only with invoice title, an
    # explicit buyer boundary, one valid tax ID and a nearby organisation name.
    issuer={}
    if sections:
        buyer_indices=[i for i,(raw,_) in enumerate(fragments) if labelled(raw,ALIASES)[0]=='buyer.name']
        has_title=any('hoa don' in key(raw) for raw,_ in fragments)
        if buyer_indices and has_title:
            boundary=buyer_indices[0]
            taxes=[]
            for i,(raw,refs) in enumerate(fragments[:boundary]):
                found,value=labelled(raw,{'tax':('ma so thue','mst')})
                if found and not value:
                    choices=right_values(refs,fragments)
                    if choices: value=choices[0][1]
                # A malformed OCR tax value must not hide a clearly observed
                # issuer name. Use only the shape to anchor the issuer region;
                # the strict tax parser below still rejects the value itself.
                if value and (tax_values(value) or re.fullmatch(r'[0-9][0-9\s.-]{8,20}',value)):
                    taxes.append(i)
            if len(taxes)==1:
                i=taxes[0];raw,refs=fragments[i]
                box=bounds(refs)
                for j in range(max(0,i-3),i):
                    name,name_refs=fragments[j];nbox=bounds(name_refs)
                    if (box and nbox and 0<=box[1]-nbox[3]<.05 and abs(nbox[0]-box[0])<.03
                            and re.match(r'^(cong ty|chi nhanh|tap doan|ban quan ly)\b',key(name))
                            and ':' not in name):
                        issuer[i]=(j,name,name_refs)
                        if not any(r=='seller' for r,_ in role_anchors):role_anchors.append(('seller',nbox))
                        break
    context=None
    for index,(raw,blocks) in enumerate(fragments):
        text=key(clean_label(raw))
        if index in issuer:
            _,name,name_refs=issuer[index];context='seller'
            yield 'seller.name',name,name_refs+blocks
        if sections:
            if text in ('nguoi ban','seller'): context='seller'
            elif text in ('nguoi mua','buyer'): context='buyer'
        # A rate and the next VAT label sometimes share a single font run.
        label_raw=re.sub(r'^\d+(?:[.,]\d+)?\s*%\s+(?=Tiền thuế)', '',raw,flags=re.I)
        path,inline=labelled(label_raw,aliases)
        if (path=='buyer.name' and key(clean_label(label_raw.split(':',1)[0]))=='nguoi mua'
                and bounds(blocks) and bounds(blocks)[1]>=party_end):continue
        if (path=='invoice.number' and key(clean_label(label_raw.split(':',1)[0]))=='so'
                and bounds(blocks) and any(top<=bounds(blocks)[1]<=top+.08 for top in table_tops)):
            continue  # A wrapped quantity column is not an invoice identifier.
        if sections and path in ('seller.name','buyer.name'): context=path.split('.')[0]
        if path is None and sections and (context or role_anchors) and (not bounds(blocks) or bounds(blocks)[1]<party_end):
            box=bounds(blocks);role=party_role(box,role_anchors,party_end) if role_anchors and box else context
            if role:
                path,inline=labelled(raw,{
                    role+'.tax_id':('mst','ma so thue','tax id'),
                    role+'.name':('ten don vi','don vi','name'),role+'.address':('dia chi','address')})
        if path is None:
            if sections:
                # OCR can append a single closing parenthesis after a complete
                # labelled date. Accept punctuation, never trailing words or
                # extra digits; date_values still validates the calendar date.
                match=re.fullmatch(r'ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})\s*\)?',text)
                if match: yield 'invoice.issue_date','/'.join(match.groups()),blocks
                elif re.match(r'^ngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4}\b',text):
                    # Keep the invalid observation for targeted recovery. The
                    # strict parser rejects trailing words/digits as before.
                    yield 'invoice.issue_date',raw,blocks
            continue
        if inline:
            yield path,inline,blocks
            continue
        # Pair only blocks immediately to the right on the same visual line.
        box=bounds(blocks)
        if not box: continue
        x0,y0,x1,y1=box
        candidates=[]
        for other_raw,other_blocks in fragments:
            if other_blocks==blocks: continue
            other_box=bounds(other_blocks)
            if not other_box: continue
            if sections and path.startswith(('seller.','buyer.')) and role_anchors:
                assigned=party_role(other_box,role_anchors,party_end)
                if assigned!=path.split('.')[0]:continue
            ox0,oy0,ox1,oy1=other_box
            overlap=min(y1,oy1)-max(y0,oy0)
            if ox0>=x1-0.003 and overlap>0.5*min(y1-y0,oy1-oy0):
                if labelled(other_raw,aliases)[0] is None:
                    candidates.append((ox0,other_raw,other_blocks))
        if candidates:
            # Multiple financial columns require their explicit column band;
            # proximity alone cannot identify which amount is the total.
            if path.startswith('totals.') and path!='totals.net' and sum(bool(money_values(value,'AUTO')) for _,value,_ in candidates)>1:
                continue
            _,value,value_blocks=min(candidates,key=lambda entry:entry[0])
            yield path,value.strip().lstrip(':：').strip(),blocks+value_blocks
        elif path.startswith('totals.'):
            # Some PDF producers offset the right-hand amount by almost one
            # font height. Read only nearby printed numbers to the right; never
            # infer a total or borrow a distant previous table row. Preserve
            # every eligible competing value instead of picking one by amount.
            for value,value_blocks in fragments:
                other=bounds(value_blocks)
                if not other or value_blocks==blocks: continue
                ox0,oy0,ox1,oy1=other
                height=max(y1-y0,oy1-oy0)
                if (x1<=ox0<=x1+.25 and abs((oy0+oy1-y0-y1)/2)<=height
                        and money_values(value,'AUTO')):
                    yield path,value.strip(),blocks+value_blocks
        elif path in ('seller.name','buyer.name','seller.tax_id','buyer.tax_id',
                      'seller.address','buyer.address','invoice.series','invoice.number','invoice.issue_date'):
            # A name may be below its explicit label. Never cross a page,
            # column, another field label or a distant vertical gap.
            below=[]
            for value,value_blocks in fragments:
                other=bounds(value_blocks)
                if not other: continue
                if sections and path.startswith(('seller.','buyer.')) and role_anchors and party_role(other,role_anchors,party_end)!=path.split('.')[0]:continue
                ox0,oy0,ox1,oy1=other
                if abs(ox0-x0)<.015 and 0<=oy0-y1<=1.5*(y1-y0):
                    below.append((oy0,value,value_blocks))
            if below:
                _,value,value_blocks=min(below,key=lambda entry:entry[0])
                generic={'ignore':('mst','ma so thue','dia chi','so tai khoan','ngan hang','ten don vi','don vi','ho ten nguoi mua hang','ten khach hang')}
                if labelled(value,aliases)[0] is None and labelled(value,generic)[0] is None:
                    yield path,value.strip(),blocks+value_blocks


def extend_address(raw,refs,page):
    """Continue only adjacent, aligned address text; stop at the next label."""
    values=value_blocks(raw,refs)
    box=bounds(values or refs)
    if not box:return raw,refs
    label_left=bounds(refs)[0]
    used={b.block_id for b in refs}
    for _ in range(5):
        nearby=[]
        for text,blocks in logical_fragments(page):
            other=bounds(blocks)
            if not other or any(b.block_id in used for b in blocks):continue
            if min(abs(other[0]-box[0]),abs(other[0]-label_left))<.02 and -.002<=other[1]-box[3]<=1.2*(box[3]-box[1]):
                nearby.append((other[1],text,blocks,other))
        if not nearby:break
        _,text,blocks,other=min(nearby,key=lambda entry:entry[0])
        if ':' in text or labelled(text,ALIASES)[0] or key(text).startswith(('stt','hinh thuc','so tai khoan','ngan hang')):break
        raw+=' '+text.strip();refs+=blocks;used.update(b.block_id for b in blocks);box=other
    return raw,refs


def value_blocks(raw,refs):
    """Find value spans even when the native PDF emits one block per word."""
    values=[b for b in refs if any(c.isalnum() for c in b.text_raw)
            and key(b.text_raw.strip()) in key(raw)]
    # Isolated words shared with a label/anchor cannot locate a whole value.
    # Inline label+value spans retain their full original box as before.
    return values if values and key(fragment_text(values))==key(raw) else []


def extend_name(raw,refs,page):
    box=bounds(value_blocks(raw,refs) or refs)
    if not box:return raw,refs
    used={b.block_id for b in refs}
    for _ in range(4):
        nearby=[]
        for text,blocks in logical_fragments(page):
            other=bounds(blocks)
            if (other and not any(b.block_id in used for b in blocks)
                    and abs(other[0]-box[0])<.02
                    and -.002<=other[1]-box[3]<=1.2*(box[3]-box[1])):
                nearby.append((other[1],text,blocks,other))
        if not nearby:break
        _,text,blocks,other=min(nearby,key=lambda row:row[0])
        # A native font span can fuse the name tail with the next tax label.
        boundary=re.search(r'(?:Mã\s+số\s+thuế|MST|Tax\s+code)\s*[:：]',text,re.I)
        tail=text[:boundary.start()].strip() if boundary else text.strip()
        # Unlabelled issuer addresses often immediately follow the legal name.
        # Keep administrative address prose out of that name continuation.
        normalized_tail=key(tail)
        address_parts=sum(token in normalized_tail for token in ('phuong ','quan ','thanh pho ','duong ','khu do thi '))
        if re.search(r'\d',tail) and address_parts>=2:break
        generic={'stop':('dia chi','address','ten don vi','don vi','mst','ma so thue','so tai khoan','dien thoai','hinh thuc thanh toan')}
        if not tail or ':' in tail or labelled(tail,ALIASES)[0] or labelled(tail,generic)[0] or header_key(tail) in ('stt','tenhanghoadichvu'):break
        if not any(c.isalpha() for c in tail):break
        raw+=' '+tail;refs+=blocks;used.update(b.block_id for b in blocks);box=other
        if boundary:break
    return raw,refs

def normalize_field(path,raw,profile):
    if path.endswith('.name') and not any(c.isalpha() for c in raw):return ()
    if path.endswith('.name') and header_key(raw) in ('thuesuatgtgt','thuesuat','tenhanghoadichvu','donvitinh','soluong','dongia','thanhtien'):return ()
    if path.endswith('tax_id'): return tax_values(raw)
    if path=='invoice.issue_date': return date_values(raw,profile.date_order)
    if path.startswith('totals.') or path.endswith(('.net','.quantity','.unit_price')):
        return money_values(raw,profile.number_locale)
    if path=='currency': return currency_values(raw)
    if path=='expected_rows': return (raw,) if re.fullmatch(r'[0-9]{1,5}',raw) else ()
    if path=='invoice.number':
        value=raw.strip()
        return (value,) if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._-]{0,31}',value) else ()
    if path=='invoice.series':
        value=re.sub(r'\s+','',raw)
        if re.match(r'^[1-9][CK]\d{2}',value,re.I) and not re.fullmatch(r'[1-9][CK]\d{2}[A-Z]{3}',value,re.I): return ()
        return (value,) if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/._-]{0,31}',value) else ()
    return (raw.strip(),) if raw.strip() else ()


def summary_values(page):
    """Read multi-column totals only under explicit financial column headers."""
    labels={
        'totals.net':('tri gia chua thue gtgt','tong chua thue gtgt','cong tien hang','thanh tien truoc thue gtgt','thanh tien truoc thue','thanh tien','tien dich vu','amount excluding vat','total before vat'),
        'totals.vat':('tien thue gtgt','tien thue','vat amount'),
        'totals.gross':('tien thanh toan','tong tien thanh toan','gia tri thanh toan','cong tien thanh toan','thanh tien sau thue','thanh tien sau thue gtgt','payment amount','total amount','cong'),
    }
    fragments=logical_fragments(page)
    headings=header_observations(page,labels)
    for raw,refs in fragments:
        text=key(raw);box=bounds(refs)
        if not box or not (text.startswith(('tong cong','tong tien thanh toan')) or text=='cong'):continue
        numbers=[entry for entry in right_values(refs,fragments) if money_values(entry[1],'AUTO')]
        if len(numbers)<2:continue
        eligible={name:[] for name in labels}
        for name,_,blocks in headings:
            header=bounds(blocks)
            if header and 0<box[1]-header[3]<.35:eligible[name].append((header,blocks))
        bands=[]
        for net in eligible['totals.net']:
            for vat in eligible['totals.vat']:
                for gross in eligible['totals.gross']:
                    group=(net,vat,gross)
                    centers=[((b[0]+b[2])/2,(b[1]+b[3])/2) for b,_ in group]
                    if (centers[0][0]<centers[1][0]<centers[2][0]
                            and max(y for _,y in centers)-min(y for _,y in centers)<.035):
                        bands.append(group)
        if not bands:continue
        # Use a coherent, most recent summary band. A right-aligned amount can
        # lie beyond its short heading; column boundaries, not nearest text or
        # a distant item-table heading, determine which printed total it is.
        band=max(bands,key=lambda group:max(b[3] for b,_ in group))
        # Item totals may also print a discount column before the financial
        # trio. A number left of the net heading is not a second net amount.
        numbers=[entry for entry in numbers
                 if sum(bounds(entry[2])[::2])/2>=band[0][0][0]-.005]
        if len(numbers)>3:continue
        centers=[(b[0]+b[2])/2 for b,_ in band]
        cuts=[(a+b)/2 for a,b in zip(centers,centers[1:])]
        numbers.sort(key=lambda entry:bounds(entry[2])[0])
        for index,(_,value,blocks) in enumerate(numbers):
            value_box=bounds(blocks)
            # Three explicitly labelled columns and three observed amounts
            # establish printed order even when headings are short/centred
            # and values are aligned against each column's right border.
            column=index if len(numbers)==3 else sum((value_box[0]+value_box[2])/2>cut for cut in cuts)
            path=tuple(labels)[column]
            yield path,value,refs+band[column][1]+blocks

def extract_headers(document,profile,issues):
    observations={p:[] for p in ALIASES}
    for page in document.pages:
        # Preserve competing modality observations. An OCR box slightly closer
        # to a label must not hide a valid native value behind it.
        views=[]
        for method in ('NATIVE_TEXT','OCR'):
            selected=tuple(b.model_copy(update={'origins':tuple(o for o in b.origins if o.method==method)})
                           for b in page.blocks if any(o.method==method for o in b.origins))
            if selected:views.append(page.model_copy(update={'blocks':selected}))
        for view in views or (page,):
            for path,raw,blocks in (*values_on_page(view,sections=True),*summary_values(view)):
                if path.endswith('.address'):raw,blocks=extend_address(raw,blocks,view)
                if path.endswith('.name'):raw,blocks=extend_name(raw,blocks,view)
                normalized=normalize_field(path,raw,profile)
                if not normalized:
                    issues.append(ExtractionIssue(code='UNPARSEABLE_FIELD',field_path=path,
                        message='Label found but value failed the explicit parser.',block_refs=tuple(b.block_id for b in blocks)))
                observations[path].extend(make_candidate(path,raw,value,blocks) for value in normalized)
    fields={};candidates=[]
    for path,values in observations.items():
        fields[path],marked=choose(path,values,issues);candidates.extend(marked)
    return fields,candidates
