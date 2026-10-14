import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.adapters.ocr.protocol import BlockOrigin
from src.extraction.contracts import ExtractionProfile
from src.extraction.service import extract


def scan(spans):
    doc=fragmented(spans)
    page=doc.pages[0]
    blocks=tuple(b.model_copy(update={'origins':(BlockOrigin(method='OCR',source_block_id=b.block_id),)})
                 for b in page.blocks)
    return doc.model_copy(update={'pages':(page.model_copy(update={'blocks':blocks}),)})


class OCRMissingFieldsV2Tests(unittest.TestCase):
    def test_complete_labelled_date_with_trailing_parenthesis(self):
        doc=scan([('Ngày (Day) 16 tháng (Month) 05 năm (Year) 2023)',.4,.04,.4)])
        record=extract(doc,'PDF',MASTER).record
        self.assertEqual(str(record.invoice.issue_date.value),'2023-05-16')
        self.assertEqual(len(record.invoice.issue_date.provenance.evidence),1)

    def test_date_does_not_discard_extra_words_digits_or_bad_day(self):
        for text in ('Ngày 16 tháng 05 năm 2023 the 19','Ngày 16 tháng 05 năm 20231)',
                     'Ngày 31 tháng 02 năm 2023)'):
            with self.subTest(text=text):
                self.assertEqual(extract(scan([(text,.4,.04,.4)]),'PDF',MASTER).record.invoice.issue_date.status,'MISSING')

    def test_merged_english_translation_does_not_hide_vat_label(self):
        doc=scan([('Tiền thuế GTGT (VATamount):',.57,.54,.2),('2.009',.88,.54,.06)])
        record=extract(doc,'PDF',MASTER,ExtractionProfile(number_locale='VI')).record
        self.assertEqual(str(record.totals.vat.value),'2009')
        self.assertEqual({e.block_id for e in record.totals.vat.provenance.evidence},{'span-0','span-1'})

    def test_no_space_translation_is_removed_from_label_only(self):
        doc=scan([('Tên người mua (Buyer): CÔNG TY (VATamount)',.05,.2,.6)])
        record=extract(doc,'PDF',MASTER).record
        self.assertEqual(record.parties.buyer.name.value,'CÔNG TY (VATamount)')

    def test_bad_tax_read_does_not_erase_unlabelled_issuer(self):
        doc=scan([('HÓA ĐƠN GIÁ TRỊ GIA TĂNG',.3,.04,.5),('CHI NHÁNH CÔNG TY A',.05,.1,.5),
                  ('Mã số thuế (Tax code)',.05,.13,.15),('0312662961.002',.32,.13,.2),
                  ('Tên khách hàng:',.05,.20,.2),('Tên đơn vị: CÔNG TY B',.05,.23,.5)])
        artifact=extract(doc,'PDF',MASTER)
        self.assertEqual(artifact.record.parties.seller.name.value,'CHI NHÁNH CÔNG TY A')
        self.assertEqual(artifact.record.parties.seller.tax_id.status,'MISSING')
        self.assertTrue(any(i.code=='UNPARSEABLE_FIELD' and i.field_path=='seller.tax_id'
                            for i in artifact.issues))

    def test_two_bad_tax_anchors_do_not_choose_an_issuer(self):
        doc=scan([('HÓA ĐƠN GIÁ TRỊ GIA TĂNG',.3,.04,.5),('CÔNG TY A',.05,.1,.3),
                  ('Mã số thuế: 0312662961.002',.05,.13,.4),
                  ('Mã số thuế: 0123456789.001',.05,.16,.4),('Tên người mua: CÔNG TY B',.05,.23,.5)])
        self.assertEqual(extract(doc,'PDF',MASTER).record.parties.seller.name.status,'MISSING')

    def test_trailing_letters_and_dot_tax_are_not_silently_fixed(self):
        doc=scan([('Tên người mua: CÔNG TY B',.05,.2,.4),
                  ('Mã số thuế: 0123456789 m)',.05,.23,.4),('Ký hiệu: 1K23THAM',.6,.1,.25)])
        record=extract(doc,'PDF',MASTER).record
        self.assertEqual(record.parties.buyer.tax_id.status,'MISSING')
        self.assertEqual(record.invoice.series.status,'MISSING')


if __name__=='__main__': unittest.main()
