"""Conservative overlap dedup. Conflicts survive; row order is not item identity."""
import re
import unicodedata
from .protocol import ExtractionBlock, BlockOrigin


def text_key(text):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFC',text)).strip().casefold()


def overlap(a,b):
    x0,y0,x1,y1=a; u0,v0,u1,v1=b
    intersection=max(0,min(x1,u1)-max(x0,u0))*max(0,min(y1,v1)-max(y0,v0))
    return intersection/min((x1-x0)*(y1-y0),(u1-u0)*(v1-v0))


def merge(page, ocr_blocks):
    blocks=[ExtractionBlock(block_id=b.block_id,text_raw=b.text,geometry_status='AVAILABLE',
                evidence=b.evidence,reading_order=b.reading_order,
                origins=(BlockOrigin(method='NATIVE_TEXT',source_block_id=b.block_id),)) for b in page.native_blocks]
    for candidate in ocr_blocks:
        # PDF text traces may split a label and its amount into separate spans,
        # while OCR returns the entire row. Collapse only an exact text match
        # across overlapping native spans; never numeric fuzzy matching.
        group=[b for b in blocks if candidate.evidence and b.evidence
               and all(o.method=='NATIVE_TEXT' for o in b.origins)
               and overlap(candidate.evidence.bbox,b.evidence.bbox)>=.70]
        group.sort(key=lambda b:(round(b.evidence.bbox[1],2),b.evidence.bbox[0]))
        if len(group)>1 and text_key(' '.join(b.text_raw for b in group))==text_key(candidate.text_raw):
            identifiers={b.block_id for b in group}
            blocks=[b for b in blocks if b.block_id not in identifiers]
            origins=tuple(o for b in group for o in b.origins)+candidate.origins
            blocks.append(candidate.model_copy(update={'origins':origins}))
            continue
        duplicate=False
        conflicts=[]
        for index,existing in enumerate(blocks):
            if not candidate.evidence or not existing.evidence: continue
            if overlap(candidate.evidence.bbox,existing.evidence.bbox)<0.70: continue
            if text_key(existing.text_raw)==text_key(candidate.text_raw):
                blocks[index]=existing.model_copy(update={'origins':existing.origins+candidate.origins})
                duplicate=True; break
            # Differing text at the same location is evidence of a conflict,
            # not permission to choose the higher uncalibrated score.
            conflicts.append(existing.block_id)
            blocks[index]=existing.model_copy(update={'conflict_with':tuple(sorted(set(existing.conflict_with+(candidate.block_id,))))})
        if not duplicate:
            blocks.append(candidate.model_copy(update={'conflict_with':tuple(conflicts)}))
    # Detect a clear vertical gutter for two-column, non-table pages. Tables
    # use row-major ordering; this is a layout hint, never inferred line items.
    boxed=[b for b in blocks if b.evidence]
    columnar=(not page.table_structure_present and len(boxed)>=4
              and all(b.evidence.bbox[2]<=.48 or b.evidence.bbox[0]>=.52 for b in boxed)
              and any(b.evidence.bbox[2]<=.48 for b in boxed)
              and any(b.evidence.bbox[0]>=.52 for b in boxed))
    def key(block):
        if not block.evidence: return (2,0,0,block.block_id)
        x,y,_,_=block.evidence.bbox
        return (int(x>=.52) if columnar else 0,round(y,3),x,block.block_id)
    ordered=sorted(blocks,key=key)
    return tuple(b.model_copy(update={'reading_order':i}) for i,b in enumerate(ordered))
