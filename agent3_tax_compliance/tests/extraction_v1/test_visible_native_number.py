"""A visible native identifier prevents an OCR zero error becoming PRESENT."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import pymupdf as fitz
from test_extraction import document,MASTER
from src.config import Settings
from src.ingestion.pdf_reader import read_pdf
from src.adapters.ocr.layout_merge import merge
from src.adapters.ocr.protocol import ExtractionBlock,BlockOrigin
from src.extraction.service import extract
from src.extraction.invoice_fields import labelled,ALIASES
from test_fragmented_headers import fragmented


class VisibleNativeNumberTests(unittest.TestCase):
    def test_short_party_labels_bind_names_and_tax_ids_without_company_prefix_guessing(self):
        doc=fragmented([('Đơn vị bán (Seller): CÔNG TY A',.05,.1,.75),
                        ('Mã số thuế (Tax code): 1234567890',.05,.14,.75),
                        ('Địa chỉ: 10 Đường A',.05,.18,.75),
                        ('Đơn vị mua (Buyer): CÔNG TY B',.05,.25,.75),
                        ('Mã số thuế (Tax code): 9876543210',.05,.29,.75)])
        record=extract(doc,'PDF',MASTER).record
        self.assertEqual(record.parties.seller.name.value,'CÔNG TY A')
        self.assertEqual(record.parties.seller.tax_id.value,'1234567890')
        self.assertEqual(record.parties.buyer.name.value,'CÔNG TY B')
        self.assertEqual(record.parties.buyer.tax_id.value,'9876543210')
        self.assertIsNone(labelled('ĐƠN VỊ BÁN LẺ ABC',ALIASES)[0])

    def test_masked_body_does_not_remove_uncovered_invoice_number(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source=folder/'synthetic.pdf'
            with fitz.open() as pdf:
                page=pdf.new_page(width=300,height=240)
                page.insert_text((30,35),'Invoice number: 00000166')
                page.insert_text((30,95),'Hidden price 987654321')
                annotation=page.add_rect_annot(fitz.Rect(25,75,250,105))
                annotation.set_colors(fill=(0,0,0));annotation.update();pdf.save(source)
            digest=hashlib.sha256(source.read_bytes()).hexdigest();base=document()
            page=read_pdf(source,folder,dict(source_id=base.source_id,document_id=base.document_id,input_sha256=digest),Settings(render_dpi=150))[0]
            header=next(b for b in page.native_blocks if 'Invoice number' in b.text)
            evidence=header.evidence.model_copy(update={'block_id':'ocr-number'})
            ocr=ExtractionBlock(block_id='ocr-number',text_raw='Invoice number: 000000166',reading_order=0,
                geometry_status='AVAILABLE',evidence=evidence,origins=(BlockOrigin(method='OCR',source_block_id='number'),))
            normalized=base.pages[0].model_copy(update={'page_id':page.page_id,'route':page.route,
                'geometry':page.geometry,'image_hash':page.render_sha256,'blocks':merge(page,[ocr])})
            result=extract(base.model_copy(update={'input_sha256':digest,'pages':(normalized,)}),'PDF',MASTER)
            self.assertEqual(result.segmentation.status,'SINGLE_CANDIDATE')
            self.assertEqual(result.record.invoice.number.status,'AMBIGUOUS')
            self.assertIsNone(result.record.invoice.number.value)
            self.assertEqual({c.value for c in result.record.invoice.number.candidates},{'00000166','000000166'})
            self.assertNotIn('987654321',' '.join(b.text for b in page.native_blocks))
