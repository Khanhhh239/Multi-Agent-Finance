"""One disputed header is a field review, not two invoices."""
import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER,document
from src.adapters.ocr.protocol import BlockOrigin
from src.extraction.service import extract
from src.extraction.segmentation import same_slot


class HeaderSegmentationTests(unittest.TestCase):
    def disputed(self):
        doc=fragmented([('Số hóa đơn: 00000016',.64,.063,.18),
                        ('Số hóa đơn: 0000000016',.644,.060,.18)])
        page=doc.pages[0]
        second=page.blocks[1].model_copy(update={'origins':(BlockOrigin(method='OCR',source_block_id='ocr-header'),)})
        return doc.model_copy(update={'pages':(page.model_copy(update={'blocks':(page.blocks[0],second)}),)})

    def test_same_header_disagreement_preserves_both_candidates(self):
        artifact=extract(self.disputed(),'PDF',MASTER)
        self.assertEqual(artifact.segmentation.status,'SINGLE_CANDIDATE')
        number=artifact.record.invoice.number
        self.assertEqual(number.status,'AMBIGUOUS')
        self.assertIsNone(number.value)
        self.assertEqual({c.value for c in number.candidates},{'00000016','0000000016'})
        self.assertTrue(all(c.provenance.evidence for c in number.candidates))

    def test_repeated_disputed_header_across_continuation_pages(self):
        doc=self.disputed();first=doc.pages[0]
        blocks=[]
        for b in first.blocks:
            identifier=b.block_id+'-p2'
            blocks.append(b.model_copy(update={'block_id':identifier,'evidence':b.evidence.model_copy(
                update={'page_index':1,'block_id':identifier,'transform_id':'transform-1'})}))
        second=first.model_copy(update={'page_id':'page-1','page_index':1,'blocks':tuple(blocks),
                                       'geometry':first.geometry.model_copy(update={'transform_id':'transform-1'})})
        artifact=extract(doc.model_copy(update={'pages':(first,second)}),'PDF',MASTER)
        self.assertEqual(artifact.segmentation.status,'SINGLE_CANDIDATE')
        self.assertEqual(artifact.record.invoice.number.status,'AMBIGUOUS')

    def test_separate_header_locations_keep_leading_zero_conflict(self):
        doc=fragmented([('Số hóa đơn: 00016',.6,.1,.3),('Số hóa đơn: 000016',.6,.6,.3)])
        artifact=extract(doc,'PDF',MASTER)
        self.assertEqual(artifact.segmentation.status,'REVIEW_SPLIT')
        self.assertIsNone(artifact.record)

    def test_different_pages_with_different_numbers_still_require_split(self):
        artifact=extract(document(['Số hóa đơn: 001'],second=['Số hóa đơn: 002']),'PDF',MASTER)
        self.assertEqual(artifact.segmentation.status,'REVIEW_SPLIT')

    def test_unlocated_conflicting_readings_do_not_bypass_split(self):
        doc=self.disputed();page=doc.pages[0]
        blocks=tuple(b.model_copy(update={'geometry_status':'UNAVAILABLE','evidence':None}) for b in page.blocks)
        artifact=extract(doc.model_copy(update={'pages':(page.model_copy(update={'blocks':blocks}),)}),'PDF',MASTER)
        self.assertEqual(artifact.segmentation.status,'REVIEW_SPLIT')

    def test_large_bridge_box_does_not_merge_independent_headers(self):
        self.assertFalse(same_slot((0,(.1,.1,.4,.12)),(0,(.1,.1,.4,.5))))


if __name__=='__main__':unittest.main()
