"""Synthetic visual masks must survive full-page and regional OCR rendering."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import pymupdf as fitz
from src.config import Settings
from src.ingestion.pdf_reader import read_pdf
from src.ingestion.pdf_region import render_regions
from src.ingestion.pdf_visibility import requires_visual_ocr
from src.ingestion.models import IngestionError
from src.ingestion.sandbox import run_bounded
import sys


class PDFVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'synthetic.pdf'
        self.settings=Settings(render_dpi=72)

    def tearDown(self):self.temp.cleanup()

    def fixture(self,kind,rotation=0):
        with fitz.open() as doc:
            page=doc.new_page(width=300,height=240)
            mask=fitz.Rect(30,70,230,105)
            if kind=='background':page.draw_rect(mask,color=None,fill=(0,0,0))
            page.insert_text((35,90),'SECRET 987654321',fontsize=14)
            page.insert_text((35,150),'Visible invoice heading 2026',fontsize=12)
            if kind=='highlight':
                annotation=page.add_highlight_annot(mask)
                annotation.set_colors(stroke=(0,0,0));annotation.set_opacity(1)
                annotation.set_blendmode('Normal');annotation.update()
            elif kind=='rectangle':
                annotation=page.add_rect_annot(mask)
                annotation.set_colors(stroke=(0,0,0),fill=(0,0,0));annotation.update()
            elif kind=='vector':page.draw_rect(mask,color=None,fill=(0,0,0),overlay=True)
            elif kind=='image':
                pixel=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,10,10),False);pixel.clear_with(0)
                page.insert_image(mask,pixmap=pixel,overlay=True)
            page.set_rotation(rotation);doc.save(self.source)
        return hashlib.sha256(self.source.read_bytes()).hexdigest()

    def read(self,digest):
        return read_pdf(self.source,self.root,dict(source_id='source-test',document_id='document-test',input_sha256=digest),self.settings)[0]

    def test_highlight_rectangle_vector_image_and_rotation_use_visible_ocr_only(self):
        for kind in ('highlight','rectangle','vector','image'):
            for rotation in (0,90):
                with self.subTest(kind=kind,rotation=rotation):
                    digest=self.fixture(kind,rotation);page=self.read(digest)
                    self.assertEqual(page.route,'OCR');self.assertFalse(page.native_blocks)
                    self.assertFalse(page.deduplication_required)
                    self.assertIn('PDF_VISUAL_OVERLAY_REQUIRES_OCR',page.route_reasons)
                    self.assertEqual(page.route_policy_version,'route-v1.2')
                    self.assertEqual(page.ocr_regions,((0.,0.,1.,1.),))
                    with fitz.open(self.source) as doc:
                        expected=doc[0].get_pixmap(colorspace=fitz.csRGB,alpha=False,annots=True).tobytes('png')
                    self.assertEqual(page.render_sha256,hashlib.sha256(expected).hexdigest())
                    self.assertEqual((self.root/'page-0.png').read_bytes(),expected)

    def test_plain_text_and_background_painted_before_text_keep_native_route(self):
        for kind in ('plain','background'):
            with self.subTest(kind=kind):
                page=self.read(self.fixture(kind))
                self.assertEqual(page.route,'NATIVE_TEXT')
                self.assertIn('SECRET', ''.join(b.text for b in page.native_blocks))

    def test_regional_render_keeps_annotation_appearance(self):
        digest=self.fixture('highlight')
        box=(.09,.28,.78,.45)
        regions=render_regions(self.source,self.root,[{'page_index':0,'bbox':box}],digest)
        with fitz.open(self.source) as doc:
            clip=fitz.Rect(box[0]*300,box[1]*240,box[2]*300,box[3]*240)
            expected=doc[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72),clip=clip,
                                      colorspace=fitz.csRGB,alpha=False,annots=True)
            actual=fitz.Pixmap(self.root/'line-0.png')
            self.assertEqual(actual.samples,expected.samples)
            without=doc[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72),clip=clip,
                                     colorspace=fitz.csRGB,alpha=False,annots=False)
            self.assertNotEqual(actual.samples,without.samples)
        self.assertEqual(regions[0]['render_dpi'],300)

    def test_annotation_budget_fails_closed(self):
        class TooMany:
            def annots(self):return iter(range(1001))
        with self.assertRaises(IngestionError) as caught:requires_visual_ocr(TooMany(),[])
        self.assertEqual(caught.exception.issue.code,'LIMIT_EXCEEDED')

    def test_real_worker_deadline_is_enforced(self):
        with self.assertRaises(IngestionError) as caught:
            run_bounded([sys.executable,'-c','import time;time.sleep(30)'],b'',.05,256,self.root)
        self.assertEqual(caught.exception.issue.code,'WORKER_TIMEOUT')
        self.assertTrue(caught.exception.issue.retryable)


if __name__=='__main__':unittest.main()
