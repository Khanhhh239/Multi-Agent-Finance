import hashlib
from .protocol import ExtractionBlock, BlockOrigin, OCRError
from ...domain.evidence import Evidence


def block_id(*parts):
    return 'block-'+hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:32]


def normalize(page, response):
    result=response.result
    if result is None: raise OCRError('OCR_FAILED','Cannot normalize failed response')
    if result.metadata.get('orientation_rotation',0)!=0:
        raise OCRError('PROTOCOL_ERROR','Worker changed raster orientation without a negotiated transform')
    if (response.page_id,response.source_id,response.document_id,response.page_index,response.image_hash)!=(
            page.page_id,page.source_id,page.document_id,page.page_index,page.render_sha256):
        raise OCRError('PROTOCOL_ERROR','Normalization ownership mismatch')
    width,height=page.render_width,page.render_height
    if (result.image_width,result.image_height)!=(width,height):
        raise OCRError('PROTOCOL_ERROR','Geometry dimensions mismatch')
    raw_sha=hashlib.sha256(response.model_dump_json().encode()).hexdigest()
    blocks=[]
    for index,det in enumerate(result.detections):
        if any(x<0 or x>width or y<0 or y>height for x,y in det.polygon):
            raise OCRError('PROTOCOL_ERROR','Detection polygon lies outside page')
        polygon=tuple((x/width,y/height) for x,y in det.polygon)
        twice_area=sum(x*y_next-x_next*y for (x,y),(x_next,y_next) in zip(polygon,polygon[1:]+polygon[:1]))
        if abs(twice_area)<1e-12:
            raise OCRError('PROTOCOL_ERROR','Detection polygon has zero area')
        xs,ys=zip(*polygon); bbox=(min(xs),min(ys),max(xs),max(ys))
        if bbox[0]>=bbox[2] or bbox[1]>=bbox[3]:
            raise OCRError('PROTOCOL_ERROR','Detection has zero area')
        # Page/config/image identity and detection index are stable across retries;
        # timestamps and request IDs deliberately do not enter the block ID.
        identifier=block_id(page.page_id,page.render_sha256,response.runtime_sha256,
                            response.model_config_version,index,det.text_raw,det.polygon)
        origin=BlockOrigin(method='OCR',source_block_id=det.source_id or str(index),raw_score=det.confidence,
                           score_semantics='ENGINE_HEURISTIC_NOT_CALIBRATED' if det.confidence is not None else 'UNAVAILABLE',
                           score_kind=('UNAVAILABLE' if det.confidence is None else 'DETECTION'
                               if result.metadata.get('confidence_semantics')=='DETECTION_SCORE_NOT_TEXT_CONFIDENCE' else 'ENGINE_AGGREGATE'),
                           response_sha256=raw_sha)
        blocks.append(ExtractionBlock(block_id=identifier,text_raw=det.text_raw,geometry_status='AVAILABLE',
            evidence=Evidence(source_id=page.source_id,document_id=page.document_id,page_index=page.page_index,
                              bbox=bbox,block_id=identifier,transform_id=page.geometry.transform_id),
            polygon=polygon,block_type=det.block_type,reading_order=index,origins=(origin,)))
    if not blocks and result.document_text_raw:
        blocks.append(ExtractionBlock(block_id=block_id(page.page_id,response.model_config_version,result.document_text_raw),
            text_raw=result.document_text_raw,geometry_status='UNAVAILABLE',reading_order=0,
            origins=(BlockOrigin(method='OCR',source_block_id='full-page',response_sha256=raw_sha),)))
    return blocks
