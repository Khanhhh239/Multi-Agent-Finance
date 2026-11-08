"""Affine maps use x'=a*x+c*y+e, y'=b*x+d*y+f; never modify raw bytes."""
import math

IDENTITY=(1.,0.,0.,1.,0.,0.)


def apply(matrix, point):
    a,b,c,d,e,f=matrix; x,y=point
    return a*x+c*y+e,b*x+d*y+f


def compose(first, second):
    """Apply first, then second."""
    a,b,c,d,e,f=first; g,h,i,j,k,l=second
    return g*a+i*b,h*a+j*b,g*c+i*d,h*c+j*d,g*e+i*f+k,h*e+j*f+l


def inverse(matrix):
    a,b,c,d,e,f=matrix; determinant=a*d-b*c
    if not math.isfinite(determinant) or abs(determinant)<1e-15:
        raise ValueError('singular/nonfinite affine transform')
    result=(d/determinant,-b/determinant,-c/determinant,a/determinant,
            (c*f-d*e)/determinant,(b*e-a*f)/determinant)
    if not all(math.isfinite(v) for v in result):
        raise ValueError('nonfinite affine transform')
    return result


def bbox(matrix, rect):
    x0,y0,x1,y1=rect
    points=[apply(matrix,p) for p in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]
    return min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)


def exif_transform(orientation,width,height):
    return {1:IDENTITY,2:(-1,0,0,1,width,0),3:(-1,0,0,-1,width,height),
            4:(1,0,0,-1,0,height),5:(0,1,1,0,0,0),6:(0,1,-1,0,height,0),
            7:(0,-1,-1,0,height,width),8:(0,-1,1,0,0,width)}[orientation]


def crop_transform(left,top):
    return 1,0,0,1,-left,-top


def deskew_transform(degrees,center):
    # Available for a future explicit deskew profile; no guessed deskew at ingestion.
    angle=math.radians(degrees); a=math.cos(angle); b=math.sin(angle); x,y=center
    return a,b,-b,a,x-a*x+b*y,y-b*x-a*y
