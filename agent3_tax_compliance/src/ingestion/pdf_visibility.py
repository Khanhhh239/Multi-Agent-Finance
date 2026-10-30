"""Conservative native-text admission for PDFs with visual overlays."""
from dataclasses import dataclass
import math
from .models import IngestionError


def intersects(a,b):
    return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])


@dataclass(frozen=True)
class NativeVisibility:
    safe_indices: frozenset[int]
    requires_ocr: bool
    whole_page_fallback: bool = False


def valid_box(box):
    return len(box)==4 and all(math.isfinite(x) for x in box) and box[0]<box[2] and box[1]<box[3]


def padded(box):
    # PDF points, before crop/rotation transforms. Withhold boundary glyphs too.
    return (box[0]-1,box[1]-1,box[2]+1,box[3]+1)


def native_visibility(page,spans):
    annotations=[];unknown=False;raw_annotations=[]
    for number,annotation in enumerate(page.annots() or (),1):
        if number>1000:
            raise IngestionError('LIMIT_EXCEEDED','PDF annotation budget exceeded.')
        raw_annotations.append(annotation)
    for annotation in raw_annotations:
        box=tuple(annotation.rect)
        # Only bounded standard appearances are admitted for selective reuse.
        # Unknown annotation types and widgets retain the previous OCR-only path.
        if annotation.type[1] not in ('Highlight','Square') or not valid_box(box):
            unknown=True
        else:annotations.append(padded(box))
    widgets=0
    for _ in page.widgets() or ():
        widgets+=1
        if widgets>1000:
            raise IngestionError('LIMIT_EXCEEDED','PDF widget budget exceeded.')
    log=page.get_bboxlog()
    if len(log)>20000:
        raise IngestionError('LIMIT_EXCEEDED','PDF paint-operation budget exceeded.')
    if unknown or widgets:
        return NativeVisibility(frozenset(),True,True)
    # A later filled path or image can conceal earlier visible text without
    # using annotations. Preserve the rendered appearance and use OCR only.
    paints=[(i,box) for i,(kind,box,*_) in enumerate(log) if kind in ('fill-path','fill-image','fill-shade')]
    if any(not valid_box(box) for _,box in paints):
        return NativeVisibility(frozenset(),True,True)
    viewport=tuple(page.rect*page.derotation_matrix)
    safe=set();withheld=False
    for index,span in enumerate(spans):
        if span.get('type')==3 or span.get('opacity',1)<.05:continue
        text=''.join(chr(c[0]) if 0<=c[0]<=0x10ffff else '\ufffd' for c in span.get('chars',()))
        if not text.strip():continue  # Covered whitespace cannot hide a field value.
        box=span['bbox']
        inside=(valid_box(box) and viewport[0]<=box[0]<box[2]<=viewport[2]
                and viewport[1]<=box[1]<box[3]<=viewport[3])
        covered=(not inside or any(intersects(box,mask) for mask in annotations)
                 or any(i>span.get('seqno',-1) and intersects(box,padded(paint)) for i,paint in paints))
        if covered:withheld=True
        else:safe.add(index)
    return NativeVisibility(frozenset(safe),bool(annotations) or withheld)


def requires_visual_ocr(page,spans):
    return native_visibility(page,spans).requires_ocr
