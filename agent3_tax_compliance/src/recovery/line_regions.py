"""Crop adjacent observed word spans as a line without changing evidence."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ObservedLine:
    block_id: str
    text_raw: str
    evidence: object
    region_bbox: tuple
    source_blocks: tuple


def region_box(block):
    return getattr(block,'region_bbox',block.evidence.bbox)


def line_regions(selected):
    lines=[]
    for page,block in sorted(selected,key=lambda entry:(entry[0].page_index,entry[1].evidence.bbox[1],entry[1].evidence.bbox[0])):
        box=block.evidence.bbox;target=None
        for line in reversed(lines):
            if line[0][0].page_index!=page.page_index:continue
            other=tuple((min if i<2 else max)(b.evidence.bbox[i] for _,b in line) for i in range(4))
            overlap=min(box[3],other[3])-max(box[1],other[1])
            gap=max(box[0]-other[2],other[0]-box[2],0)
            if overlap>.5*min(box[3]-box[1],other[3]-other[1]) and gap<.06:
                target=line;break
        if target is None:lines.append([(page,block)])
        else:target.append((page,block))
    output=[]
    for line in lines:
        line.sort(key=lambda entry:entry[1].evidence.bbox[0]);page=line[0][0];blocks=tuple(b for _,b in line)
        box=tuple((min if i<2 else max)(b.evidence.bbox[i] for b in blocks) for i in range(4))
        output.append((page,ObservedLine(blocks[0].block_id,' '.join(b.text_raw for b in blocks),blocks[0].evidence,box,blocks)))
    return output
