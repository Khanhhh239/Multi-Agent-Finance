"""Bounded image experiments with explicit inverse geometry; no text guessing."""
import math
from PIL import Image,ImageOps

IDENTITY=(1.,0.,0.,1.,0.,0.)


def point(matrix,p):
    a,b,c,d,e,f=matrix;x,y=p
    return a*x+c*y+e,b*x+d*y+f


def inverse(matrix):
    a,b,c,d,e,f=matrix;det=a*d-b*c
    if not math.isfinite(det) or abs(det)<1e-12:raise ValueError('invalid affine')
    return d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det


def rotation(image,degrees,max_pixels=12_000_000):
    if not math.isfinite(degrees) or abs(degrees)>3:raise ValueError('deskew is bounded to three degrees')
    a=math.cos(math.radians(degrees));b=math.sin(math.radians(degrees))
    corners=[point((a,b,-b,a,0,0),p) for p in ((0,0),(image.width,0),(image.width,image.height),(0,image.height))]
    left=min(p[0] for p in corners);top=min(p[1] for p in corners)
    width=math.ceil(max(p[0] for p in corners)-left);height=math.ceil(max(p[1] for p in corners)-top)
    if width*height>max_pixels:raise ValueError('deskew pixel budget')
    forward=(a,b,-b,a,-left,-top);back=inverse(forward)
    # PIL takes x'=a*x+b*y+c, y'=d*x+e*y+f, unlike our affine tuple.
    a,b,c,d,e,f=back
    result=image.transform((width,height),Image.Transform.AFFINE,(a,c,e,b,d,f),Image.Resampling.BICUBIC,fillcolor='white')
    return result,forward,back


def estimate_skew(image):
    """Projection search at half-degree steps, abstaining on weak improvement."""
    thumb=ImageOps.grayscale(image);thumb.thumbnail((768,768))
    scores={}
    try:
        for step in range(-6,7):
            angle=step*.5
            with thumb.rotate(-angle,expand=False,fillcolor=255) as sample:
                with sample.point(lambda value:1 if value<150 else 0) as binary:
                    pixels=binary.tobytes();width=binary.width
                    ink=[sum(pixels[y*width:(y+1)*width]) for y in range(binary.height)]
                mean=sum(ink)/max(1,len(ink))
                scores[angle]=sum((value-mean)**2 for value in ink)/max(1,len(ink))
        base=scores[0.];best=max(scores,key=lambda a:(scores[a],-abs(a)))
        gain=scores[best]/max(base,1.)
        return (best if abs(best)>=.5 and gain>=1.20 else 0.),gain
    finally:thumb.close()


def prepare(image,enabled=False):
    angle,gain=estimate_skew(image) if enabled else (0.,1.)
    if angle:
        try:processed,forward,back=rotation(image,angle)
        except ValueError:return image.copy(),IDENTITY,{'angle':0.,'gain':gain,'reason':'PIXEL_BUDGET'}
    else:processed=image.copy();forward=back=IDENTITY
    return processed,back,{'angle':angle,'gain':gain,'input_to_processed':forward,'processed_to_input':back}


def tile_boxes(width,height,overlap=.12):
    if not .05<=overlap<=.25:raise ValueError('overlap outside budget')
    if width<64 or height<64:return []
    dx=round(width*overlap/2);dy=round(height*overlap/2);x=width//2;y=height//2
    return [(0,0,x+dx,y+dy),(x-dx,0,width,y+dy),(0,y-dy,x+dx,height),(x-dx,y-dy,width,height)]


def bounds(polygon):
    return min(p[0] for p in polygon),min(p[1] for p in polygon),max(p[0] for p in polygon),max(p[1] for p in polygon)


def overlap(a,b):
    x0,y0,x1,y1=a;u0,v0,u1,v1=b
    inter=max(0,min(x1,u1)-max(x0,u0))*max(0,min(y1,v1)-max(y0,v0))
    return inter/max(1.,min((x1-x0)*(y1-y0),(u1-u0)*(v1-v0)))


def add_tiles(original,tile_results,size,max_extra=200):
    """Retain baseline boxes; add only uncovered, non-truncated tile boxes."""
    width,height=size;output=list(original);added=0;truncated=0
    for tile,detections in tile_results:
        left,top,right,bottom=tile
        for detection in detections:
            polygon=[[x+left,y+top] for x,y in detection['polygon']];box=bounds(polygon)
            if ((left>0 and box[0]<=left+3) or (top>0 and box[1]<=top+3)
                or (right<width and box[2]>=right-3) or (bottom<height and box[3]>=bottom-3)):
                truncated+=1;continue
            if any(overlap(box,bounds(d['polygon']))>=.7 for d in output):continue
            if added>=max_extra:continue
            output.append({**detection,'polygon':polygon,'source_id':'coverage-tile-'+str(added)})
            added+=1
    return output,{'tiles':len(tile_results),'added_boxes':added,'edge_boxes_rejected':truncated,'max_extra_boxes':max_extra}


def map_polygon(polygon,back,size):
    width,height=size
    # Expanded white corners may be detected; clip only after mapping into
    # the source raster. The exact inverse is retained in response metadata.
    return [[max(0.,min(width,x)),max(0.,min(height,y))] for x,y in (point(back,p) for p in polygon)]
