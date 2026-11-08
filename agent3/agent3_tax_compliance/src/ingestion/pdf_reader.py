"""Called only inside the bounded worker, never by an API handler."""
import hashlib
import math
import unicodedata
import warnings
from time import perf_counter

from .models import DocumentArtifact, Geometry, IngestionError, PageArtifact, TextBlock
from .preprocess import bbox, compose, exif_transform, inverse
from .pdf_visibility import native_visibility
from ..domain.evidence import Evidence

STAMP=dict(config_version='ingestion-v1',creator='pdf-reader',stage='ingestion-read')


def stable_id(prefix,*values):
    return prefix+'-'+hashlib.sha256('|'.join(map(str,values)).encode()).hexdigest()[:32]


def checked_pixels(width,height,settings,total):
    pixels=width*height
    if width<=0 or height<=0 or pixels>settings.max_render_pixels or total+pixels>settings.max_document_pixels:
        raise IngestionError('LIMIT_EXCEEDED','Rendered pixel budget exceeded.')
    return total+pixels


def normalized(rect,matrix,width,height):
    x0,y0,x1,y1=bbox(matrix,rect)
    values=(max(0,x0/width),max(0,y0/height),min(1,x1/width),min(1,y1/height))
    return values if values[0]<values[2] and values[1]<values[3] else None


def area(rectangles):
    """Exact union area by x-sweep; list size is bounded by reader limits."""
    edges=sorted({x for r in rectangles for x in (r[0],r[2])})
    result=0.
    for left,right in zip(edges,edges[1:]):
        intervals=sorted((r[1],r[3]) for r in rectangles if r[0]<right and r[2]>left)
        bottom=top=None; length=0.
        for a,b in intervals:
            if top is None: bottom,top=a,b
            elif a>top: length+=top-bottom; bottom,top=a,b
            else: top=max(top,b)
        if top is not None: length+=top-bottom
        result+=(right-left)*length
    return min(1.,max(0.,result))


def page_route(texts,rectangles,image_rectangles,invisible,policy):
    joined=''.join(texts)
    # Embedded Vietnamese fonts can map spaces to NBSP (category Zs), which
    # Python's isprintable() rejects even though it is a valid PDF text glyph.
    valid=sum((ch.isprintable() or unicodedata.category(ch)=='Zs') and ch!='\ufffd'
              and unicodedata.category(ch) not in ('Co','Cn') for ch in joined)
    ratio=valid/len(joined) if joined else 0.
    alphanumeric=sum(ch.isalnum() for ch in joined)
    text_area=area(rectangles); image_area=area(image_rectangles)
    usable=(alphanumeric>=policy.min_alphanumeric and ratio>=policy.min_valid_glyph_ratio
            and text_area>=policy.min_text_coverage)
    reasons=[]
    if invisible: reasons.append('INVISIBLE_TEXT_IGNORED')
    if not usable:
        route='OCR'; regions=((0.,0.,1.,1.),); reasons.append('NATIVE_TEXT_INSUFFICIENT_OR_UNTRUSTED')
    elif image_area>=policy.hybrid_image_coverage:
        route='HYBRID'; regions=tuple(image_rectangles); reasons.append('USABLE_TEXT_AND_IMAGE_REGIONS')
    else:
        route='NATIVE_TEXT'; regions=(); reasons.append('USABLE_VISIBLE_NATIVE_TEXT')
    return route,regions,tuple(reasons),ratio,text_area,image_area


def read_pdf(path,output,identity,settings):
    import pymupdf as fitz
    try:
        document=fitz.open(path)
    except Exception:
        raise IngestionError('CORRUPT_DOCUMENT','PDF parser rejected the document.') from None
    pages=[]; total=0; bytes_written=0
    with document:
        if not document.is_pdf:
            raise IngestionError('CORRUPT_DOCUMENT','Parser result is not PDF.')
        if document.needs_pass:
            raise IngestionError('ENCRYPTED_PDF','Password-protected PDFs are outside the current reader scope.',
                                 next_action='Provide an authorized unencrypted export.')
        if not 0<len(document)<=settings.max_pages:
            raise IngestionError('LIMIT_EXCEEDED','PDF page count exceeds configured bounds.')
        if document.is_repaired:
            raise IngestionError('CORRUPT_DOCUMENT','PDF required structural repair; strict profile rejects it.')
        for index,page in enumerate(document):
            scale=settings.render_dpi/72
            if not math.isfinite(page.rect.width+page.rect.height):
                raise IngestionError('CORRUPT_DOCUMENT','Nonfinite PDF page geometry.')
            width=math.ceil(page.rect.width*scale); height=math.ceil(page.rect.height*scale)
            total=checked_pixels(width,height,settings,total)
            matrix=compose(tuple(page.rotation_matrix),(scale,0,0,scale,0,0))
            unrotated=page.rect*page.derotation_matrix
            spans=page.get_texttrace()
            if len(spans)>2000 or sum(len(s.get('chars',())) for s in spans)>settings.max_page_characters:
                raise IngestionError('LIMIT_EXCEEDED','PDF text budget exceeded.')
            visibility=native_visibility(page,spans)
            visible=[]; invisible=0
            for number,span in enumerate(spans):
                if span.get('type')==3 or span.get('opacity',1)<0.05:
                    invisible+=1; continue
                if number not in visibility.safe_indices:continue
                text=''.join(chr(ch[0]) if 0<=ch[0]<=0x10ffff else '\ufffd' for ch in span['chars'])
                region=normalized(span['bbox'],matrix,width,height)
                if text.strip() and region:
                    visible.append((number,text,tuple(span['bbox']),region))
            image_info=page.get_image_info()
            if len(image_info)>500:
                raise IngestionError('LIMIT_EXCEEDED','PDF image object budget exceeded.')
            image_rectangles=[]
            for info in image_info:
                if info['width']*info['height']>settings.max_source_pixels:
                    raise IngestionError('LIMIT_EXCEEDED','Embedded image pixel budget exceeded.')
                rect=normalized(info['bbox'],matrix,width,height)
                if rect: image_rectangles.append(rect)
            route,regions,reasons,ratio,text_area,image_area=page_route(
                [v[1] for v in visible],[v[3] for v in visible],image_rectangles,invisible,settings.route_policy)
            if route=='OCR':
                # Selective visibility does not override native glyph/coverage
                # trust policy. Unusable native text must not enter fusion.
                visible=[]
                text_area=0.
            if visibility.requires_ocr:
                route,regions=('HYBRID' if visible else 'OCR'),((0.,0.,1.,1.),)
                reasons=('PDF_VISUAL_OVERLAY_REQUIRES_OCR','PDF_OCCLUDED_NATIVE_WITHHELD',
                         'PDF_UNOCCLUDED_NATIVE_RETAINED' if visible else 'NATIVE_TEXT_WITHHELD_FOR_VISUAL_REVIEW')
                if visibility.whole_page_fallback:reasons+=('PDF_VISIBILITY_WHOLE_PAGE_FALLBACK',)
            order=sorted(range(len(visible)),key=lambda i:(round(visible[i][2][1],1),visible[i][2][0],visible[i][0]))
            ranks={item:rank for rank,item in enumerate(order)}
            blocks=[]
            page_id=stable_id('page',identity['source_id'],index)
            for i,(number,text,original,region) in enumerate(visible):
                block_id=stable_id('block',page_id,number)
                blocks.append(TextBlock(block_id=block_id,text=text,source_order=number,reading_order=ranks[i],
                    original_bbox=original,evidence=Evidence(source_id=identity['source_id'],document_id=identity['document_id'],
                    page_index=index,bbox=region,block_id=block_id,transform_id=page_id+'-transform')))
            drawings=page.get_drawings()
            if len(drawings)>10000:
                raise IngestionError('LIMIT_EXCEEDED','PDF drawing object budget exceeded.')
            horizontal=vertical=0
            for drawing in drawings:
                for item in drawing['items']:
                    if item[0]=='l':
                        p,q=item[1:3]
                        horizontal+=abs(p.y-q.y)<0.5
                        vertical+=abs(p.x-q.x)<0.5
            table=horizontal>=2 and vertical>=2
            if table: reasons+=('TABLE_STRUCTURE_PRESENT',)
            if blocks: reasons+=('READING_ORDER_HEURISTIC_RETAIN_SOURCE_ORDER',)
            pixmap=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False,annots=True)
            # PyMuPDF rounds bounds; validate actual dimensions before materializing PNG bytes.
            checked_pixels(pixmap.width,pixmap.height,settings,total-width*height)
            png=pixmap.tobytes('png'); bytes_written+=len(png)
            if bytes_written>settings.max_artifact_bytes:
                raise IngestionError('LIMIT_EXCEEDED','Rendered artifact byte budget exceeded.')
            (output/f'page-{index}.png').write_bytes(png)
            pages.append(PageArtifact(**STAMP,source_id=identity['source_id'],input_sha256=identity['input_sha256'],
                document_id=identity['document_id'],page_id=page_id,page_index=index,
                original_width=unrotated.width,original_height=unrotated.height,
                render_width=pixmap.width,render_height=pixmap.height,rotation=page.rotation,
                geometry=Geometry(transform_id=page_id+'-transform',original_space='PDF_UNROTATED_CROP_TOP_LEFT',
                    crop_origin=(page.cropbox.x0,page.cropbox.y0),original_to_render=matrix,render_to_original=inverse(matrix)),
                render_sha256=hashlib.sha256(png).hexdigest(),route=route,route_policy_version=settings.route_policy.version,
                route_reasons=reasons,valid_glyph_ratio=ratio,text_coverage=text_area,image_coverage=image_area,
                invisible_text_spans=invisible,table_structure_present=table,ocr_regions=regions,
                native_blocks=tuple(blocks),deduplication_required=route=='HYBRID'))
    return pages


def read_image(path,output,identity,settings):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS=settings.max_source_pixels
    warnings.simplefilter('error',Image.DecompressionBombWarning)
    try:
        with Image.open(path) as image:
            width,height=image.size
            if width*height>settings.max_source_pixels:
                raise IngestionError('LIMIT_EXCEEDED','Image source pixel budget exceeded.')
            if getattr(image,'n_frames',1)!=1:
                raise IngestionError('UNSUPPORTED_FORMAT','Multi-frame images require a separate adapter.')
            orientation=image.getexif().get(274,1)
            if orientation not in range(1,9):
                raise IngestionError('CORRUPT_DOCUMENT','Invalid EXIF orientation.')
            expected=(height,width) if orientation in (5,6,7,8) else (width,height)
            checked_pixels(*expected,settings,0)
            processed=ImageOps.exif_transpose(image).convert('RGB')
            target=output/'page-0.png'; processed.save(target,format='PNG')
    except (Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise IngestionError('LIMIT_EXCEEDED','Image decompression budget exceeded.') from None
    if target.stat().st_size>settings.max_artifact_bytes:
        raise IngestionError('LIMIT_EXCEEDED','Image artifact byte budget exceeded.')
    matrix=exif_transform(orientation,width,height)
    return [PageArtifact(**STAMP,source_id=identity['source_id'],input_sha256=identity['input_sha256'],
        document_id=identity['document_id'],page_id=stable_id('page',identity['source_id'],0),page_index=0,
        original_width=width,original_height=height,render_width=processed.width,render_height=processed.height,
        exif_orientation=orientation,geometry=Geometry(transform_id=stable_id('page',identity['source_id'],0)+'-transform',original_space='IMAGE_RAW_PIXELS',
            original_to_render=matrix,render_to_original=inverse(matrix)),render_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        route='OCR',route_policy_version=settings.route_policy.version,route_reasons=('IMAGE_REQUIRES_OCR',),
        valid_glyph_ratio=0,text_coverage=0,image_coverage=1,invisible_text_spans=0,ocr_regions=((0,0,1,1),))]


def read_document(path,output,identity,settings):
    started=perf_counter()
    pages=read_pdf(path,output,identity,settings) if identity['source_format']=='PDF' else read_image(path,output,identity,settings)
    return DocumentArtifact(**STAMP,**identity,reader_elapsed_ms=(perf_counter()-started)*1000,pages=tuple(pages))
