import io
import pymupdf as fitz
from PIL import Image, ImageDraw


def image_bytes(exif=1,format='PNG',size=(120,80)):
    image=Image.new('RGB',size,'white'); ImageDraw.Draw(image).text((5,10),'SYNTHETIC',fill='black')
    output=io.BytesIO()
    if format=='JPEG':
        info=Image.Exif(); info[274]=exif
        image.save(output,format=format,exif=info)
    else: image.save(output,format=format)
    return output.getvalue()


def pdf_bytes(kind='native',rotation=0,crop=False):
    with fitz.open() as doc:
        if kind=='oversized':
            doc.new_page(width=10000,height=10000)
        else:
            page=doc.new_page(width=300,height=400)
            if kind in ('scan','invisible'):
                page.insert_image(page.rect,stream=image_bytes(size=(300,400)))
            if kind in ('native','mixed','hybrid','encrypted'):
                page.insert_text((25,40),'Invoice seller buyer amount 12345',fontsize=11)
                page.insert_text((25,70),'Date 2026-10-12 total amount 100.10',fontsize=11)
            if kind=='hybrid': page.insert_image(fitz.Rect(0,200,300,400),stream=image_bytes(size=(300,200)))
            if kind=='garbage': page.insert_text((25,40),'???????????????????????',fontsize=11)
            if kind=='invisible': page.insert_text((25,40),'Invoice seller buyer hidden text 12345',render_mode=3)
            if crop: page.set_cropbox(fitz.Rect(10,20,290,380))
            page.set_rotation(rotation)
            if kind=='mixed':
                page=doc.new_page(width=300,height=400)
                page.insert_image(page.rect,stream=image_bytes(size=(300,400)))
        if kind=='encrypted':
            return doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='owner-fixture',user_pw='user-fixture')
        return doc.tobytes()
