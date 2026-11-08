"""Bounded worker for rendering original PDF regions, without enlarging a raster."""
import hashlib
import json
import math
import sys
from pathlib import Path


def render_regions(source,output,regions,expected_sha256):
    import pymupdf as fitz
    source=Path(source);output=Path(output)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected_sha256:raise ValueError('Source hash mismatch')
    if not 1<=len(regions)<=4:raise ValueError('Region count exceeded')
    total=0;results=[]
    with fitz.open(source) as document:
        if not document.is_pdf or document.needs_pass or document.is_repaired:raise ValueError('Unsupported PDF')
        for index,region in enumerate(regions):
            page_index=region['page_index'];box=region['bbox'];dpi=300
            if type(page_index) is not int or not 0<=page_index<len(document):raise ValueError('Invalid page')
            if len(box)!=4 or not all(math.isfinite(v) for v in box) or not 0<=box[0]<box[2]<=1 or not 0<=box[1]<box[3]<=1:
                raise ValueError('Invalid region')
            page=document[page_index];rect=page.rect
            clip=fitz.Rect(rect.x0+box[0]*rect.width,rect.y0+box[1]*rect.height,
                           rect.x0+box[2]*rect.width,rect.y0+box[3]*rect.height)
            scale=dpi/72
            # Account for both floor/ceil edges before allocating the pixmap.
            width=math.ceil(clip.x1*scale)-math.floor(clip.x0*scale)
            height=math.ceil(clip.y1*scale)-math.floor(clip.y0*scale)
            pixels=width*height;total+=pixels
            if pixels<=0 or pixels>1_000_000 or total>2_000_000:raise ValueError('Region pixel budget exceeded')
            pixmap=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=clip,colorspace=fitz.csRGB,alpha=False,annots=True)
            if pixmap.width*pixmap.height>pixels:raise ValueError('Unexpected render geometry')
            path=output/f'line-{index}.png';pixmap.save(path)
            results.append({'width':pixmap.width,'height':pixmap.height,'render_dpi':dpi,
                            'pdf_clip':list(clip),'page_rotation':page.rotation,
                            'render_pixel_origin':[pixmap.x,pixmap.y]})
    return results


def main():
    payload=json.loads(sys.stdin.buffer.read(128*1024))
    result=render_regions(payload['source'],payload['output'],payload['regions'],payload['sha256'])
    (Path(payload['output'])/'regions.json').write_text(json.dumps(result),encoding='utf-8')


if __name__=='__main__':main()
