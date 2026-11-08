"""Separate competing readings of one header from distinct invoice headers."""


def location(candidate):
    refs=candidate.evidence_refs
    if not refs or len({e.page_index for e in refs})!=1:
        return None
    return (refs[0].page_index, (min(e.bbox[0] for e in refs),min(e.bbox[1] for e in refs),
                                max(e.bbox[2] for e in refs),max(e.bbox[3] for e in refs)))


def same_slot(first,second):
    if first is None or second is None or first[0]!=second[0]:
        return False
    a,b=first[1],second[1]
    widths=(a[2]-a[0],b[2]-b[0]);heights=(a[3]-a[1],b[3]-b[1])
    if min(*widths,*heights)<=0:
        return False
    # Require mutual spatial agreement; an oversized OCR box cannot bridge
    # independent headers. Never compare digit suffixes or strip leading zeros.
    return (max(widths)<=3*min(widths) and max(heights)<=3*min(heights)
            and min(a[2],b[2])-max(a[0],b[0])>=.6*min(widths)
            and min(a[3],b[3])-max(a[1],b[1])>=.6*min(heights))


def competing_invoice_headers(candidates):
    slots=[]
    for candidate in candidates:
        if candidate.semantic_field!='invoice.number':
            continue
        where=location(candidate)
        # Complete-link grouping prevents transitive overlap from combining
        # two real invoices through one noisy OCR observation.
        for slot in slots:
            if all(same_slot(where,other) for _,other in slot):
                slot.append((candidate,where))
                break
        else:
            slots.append([(candidate,where)])
    values=[{c.normalized_value for c,_ in slot} for slot in slots]
    return any(a!=b for i,a in enumerate(values) for b in values[i+1:])
