"""Conservative native-text admission for PDFs with visual overlays."""
from .models import IngestionError


def intersects(a,b):
    return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])


def requires_visual_ocr(page,spans):
    # Annotation appearances are rendered, but PDF texttrace does not account
    # for them. Do not let hidden text survive through native/OCR fusion.
    annotations=0
    for _ in page.annots() or ():
        annotations+=1
        if annotations>1000:
            raise IngestionError('LIMIT_EXCEEDED','PDF annotation budget exceeded.')
    widgets=0
    for _ in page.widgets() or ():
        widgets+=1
        if widgets>1000:
            raise IngestionError('LIMIT_EXCEEDED','PDF widget budget exceeded.')
    log=page.get_bboxlog()
    if len(log)>20000:
        raise IngestionError('LIMIT_EXCEEDED','PDF paint-operation budget exceeded.')
    if annotations or widgets:
        return True
    # A later filled path or image can conceal earlier visible text without
    # using annotations. Preserve the rendered appearance and use OCR only.
    paints=[(i,box) for i,(kind,box,*_) in enumerate(log) if kind in ('fill-path','fill-image','fill-shade')]
    return any(i>span.get('seqno',len(log)) and intersects(box,span['bbox'])
               for span in spans if span.get('type')!=3 and span.get('opacity',1)>=.05
               for i,box in paints)
