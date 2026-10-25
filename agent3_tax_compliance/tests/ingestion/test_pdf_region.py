import hashlib
import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageChops
from src.ingestion.pdf_region import render_regions


class PDFRegionTests(unittest.TestCase):
    def test_clip_matches_original_pdf_at_300_dpi_for_every_rotation(self):
        import pymupdf as fitz
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for rotation in (0,90,180,270):
                source=root/f'rot-{rotation}.pdf'
                with fitz.open() as doc:
                    page=doc.new_page(width=200,height=300)
                    page.insert_text((20,80),'ABC 001 123.45',fontsize=10)
                    page.draw_rect((10,40,120,100),color=(1,0,0))
                    page.set_cropbox(fitz.Rect(10,20,190,280));page.set_rotation(rotation);doc.save(source)
                digest=hashlib.sha256(source.read_bytes()).hexdigest()
                boxes=[{'page_index':0,'bbox':[.1,.1,.4,.4]}]
                result=render_regions(source,root,boxes,digest)[0]
                with fitz.open(source) as doc:
                    full=doc[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72),alpha=False)
                    reference=Image.frombytes('RGB',(full.width,full.height),full.samples)
                with reference,Image.open(root/'line-0.png') as crop:
                    x,y=result['render_pixel_origin']
                    with reference.crop((x,y,x+crop.width,y+crop.height)) as expected:
                        self.assertIsNone(ImageChops.difference(expected,crop).getbbox())
                self.assertEqual(result['page_rotation'],rotation)

    def test_hash_bounds_and_pixel_budget_are_enforced_before_render(self):
        import pymupdf as fitz
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'a.pdf'
            with fitz.open() as doc:doc.new_page();doc.save(source)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            for box in ((0,0,1,1),(-.1,0,.2,.2),(0,0,float('nan'),.2)):
                with self.assertRaises(ValueError):render_regions(source,root,[{'page_index':0,'bbox':box}],digest)
            with self.assertRaises(ValueError):render_regions(source,root,[{'page_index':0,'bbox':[0,0,.1,.1]}],'0'*64)
            self.assertFalse((root/'line-0.png').exists())


if __name__=='__main__':unittest.main()
