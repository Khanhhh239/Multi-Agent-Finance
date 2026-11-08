from ..canonicalization.derive import sha
from ..ingestion.preprocess import bbox

def resolve(artifact,candidate_id,normalized,document):
    """Return checked raw spans and coordinates in render/original spaces."""
    if sha(normalized.model_dump(mode='json'))!=artifact.normalized_input_sha256: raise ValueError('normalized input hash mismatch')
    if (document.tenant_id,document.taxpayer_id,document.source_id,document.document_id,document.input_sha256)!=(
            artifact.tenant_id,artifact.taxpayer_id,artifact.source_id,artifact.document_id,artifact.input_sha256):
        raise ValueError('document ownership mismatch')
    # PLAN_03 binds the serialized PLAN_02 artifact hash; verify exact serializer.
    from ..persistence.repository import digest
    if digest(document.model_dump_json().encode())!=normalized.document_artifact_sha256: raise ValueError('document artifact hash mismatch')
    candidate=next((c for c in artifact.candidates if c.candidate_id==candidate_id),None)
    if candidate is None: raise KeyError('candidate not found')
    regions=[]
    for ev in candidate.evidence_refs:
        page=document.pages[ev.page_index];norm_page=normalized.pages[ev.page_index]
        block=next((b for b in norm_page.blocks if b.block_id==ev.block_id),None)
        if block is None or not block.evidence or block.evidence.model_dump(exclude={'span'})!=ev.model_dump(exclude={'span'}): raise ValueError('evidence block mismatch')
        if ev.span and ev.span[1]>len(block.text_raw): raise ValueError('evidence span outside block')
        x0,y0,x1,y1=ev.bbox
        pixels=(x0*page.render_width,y0*page.render_height,x1*page.render_width,y1*page.render_height)
        regions.append({'page_index':ev.page_index,'block_id':ev.block_id,'raw_text':block.text_raw,
            'span':ev.span,'render_bbox':pixels,'original_bbox':bbox(page.geometry.render_to_original,pixels),
            'original_space':page.geometry.original_space,'crop_origin':page.geometry.crop_origin,
            'transform_id':ev.transform_id,'ocr_config':normalized.ocr_config.model_dump(mode='json'),
            'extractor_sha256':artifact.extractor_sha256})
    return {'candidate_id':candidate_id,'geometry_available':bool(regions),'regions':regions}
