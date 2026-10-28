"""Synthetic evidence-preserving regressions for dense/wrapped table rows."""
import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile
from src.extraction.spatial_tables import spatial_headers,column_bounds


def run(spans):
    return extract(fragmented(spans),'PDF',MASTER,ExtractionProfile(number_locale='VI'))


HEADERS=[('STT',.02,.30,.04),('Tên hàng hóa dịch vụ',.1,.30,.25),
         ('SL',.48,.30,.04),('Đơn giá',.6,.30,.09),('Thành tiền',.8,.30,.12)]


class AmountRowAlignmentTests(unittest.TestCase):
    def test_unreadable_first_amount_cannot_shift_later_rows(self):
        items=run(HEADERS+[
            ('1',.03,.36,.02),('A sản phẩm',.1,.36,.2),('10',.49,.36,.02),('495.000',.6,.36,.08),('A.950.000',.83,.36,.09),
            ('2',.03,.40,.02),('B sản phẩm',.1,.40,.2),('11',.49,.40,.02),('5.000',.6,.40,.06),('55.000',.83,.40,.06),
            ('3',.03,.44,.02),('C sản phẩm',.1,.44,.2),('9',.49,.44,.02),('35.000',.6,.44,.06),('315.000',.83,.44,.08)]).record.items
        self.assertEqual(len(items),3)
        self.assertEqual(items[0].net.status,'MISSING')
        self.assertEqual([str(item.quantity.value) for item in items],['10','11','9'])
        self.assertEqual([item.description.value for item in items],['A sản phẩm','B sản phẩm','C sản phẩm'])

    def test_translated_column_heading_is_not_part_of_first_description(self):
        items=run(HEADERS+[
            ('(Name of goods and services)',.1,.32,.25),
            ('1',.03,.36,.02),('A sản phẩm',.1,.36,.2),('1',.49,.36,.02),('100',.6,.36,.06),('100',.83,.36,.06),
            ('2',.03,.40,.02),('B sản phẩm',.1,.40,.2),('1',.49,.40,.02),('200',.6,.40,.06),('200',.83,.40,.06)]).record.items
        self.assertEqual(items[0].description.value,'A sản phẩm')
        self.assertEqual(items[1].description.value,'B sản phẩm')

    def test_wrapped_decimal_and_serial_do_not_shift_the_next_row(self):
        spans=HEADERS+[
            ('Máy thử nghiệm',.1,.35,.25),('Mã A',.1,.363,.15),
            ('1.000,',.6,.375,.08),('7',.6,.388,.02),
            ('1',.03,.38,.02),('1',.49,.38,.02),('1.001',.83,.38,.06),
            ('SN: ABC-123',.1,.389,.2),
            ('2',.03,.391,.02),('1',.49,.391,.02),('200',.83,.391,.06),
            ('Bộ nhớ thử nghiệm',.1,.402,.25),('200',.6,.402,.05),
            ('3',.03,.414,.02),('1',.49,.414,.02),('300',.83,.414,.06),
            ('(CODE-02)',.1,.415,.18),('300',.6,.415,.05),
            ('Ổ đĩa thử nghiệm',.1,.428,.25)]
        artifact=run(spans);items=artifact.record.items
        self.assertEqual(len(items),3)
        self.assertEqual([str(item.unit_price.value) for item in items],['1000.7','200','300'])
        self.assertIn('SN: ABC-123',items[0].description.value)
        self.assertEqual(items[1].description.value,'Bộ nhớ thử nghiệm (CODE-02)')
        self.assertEqual(items[2].description.value,'Ổ đĩa thử nghiệm')
        observed={e.block_id for e in items[0].unit_price.provenance.evidence}
        self.assertEqual(observed,{'span-7','span-8'})
        self.assertNotEqual(artifact.record.item_discovery_status,'COMPLETE')

    def test_missing_price_is_not_filled_from_next_row_or_net(self):
        items=run(HEADERS+[
            ('1',.03,.36,.02),('A sản phẩm',.1,.36,.2),('2',.49,.36,.02),('200',.83,.36,.06),
            ('2',.03,.40,.02),('B sản phẩm',.1,.40,.2),('1',.49,.40,.02),('300',.6,.40,.06),('300',.83,.40,.06)]).record.items
        self.assertEqual(len(items),2)
        self.assertEqual(items[0].unit_price.status,'MISSING')
        self.assertEqual(str(items[1].unit_price.value),'300')

    def test_fused_tax_labels_use_layout_subboxes_but_original_value_evidence(self):
        spans=[('STT',.02,.3,.03),('Tên hàng hóa dịch vụ',.08,.3,.2),
               ('SL',.33,.3,.03),('Đơn giá',.4,.3,.08),
               ('Thành tiền',.51,.3,.09),('trước thuế',.51,.31,.09),
               ('Thuê suất Tiên thuế GTGT',.62,.3,.18),
               ('Thành tiền sau',.82,.3,.14),('thuế GTGT',.83,.31,.12),
               ('1',.03,.36,.02),('A sản phẩm',.08,.36,.2),('1',.34,.36,.02),
               ('100',.43,.36,.04),('100',.55,.36,.04),('8%',.64,.36,.03),
               ('8',.75,.36,.02),('108',.91,.36,.04)]
        doc=fragmented(spans);headers=spatial_headers(doc.pages[0])
        self.assertLess(column_bounds(headers['vat'])[2],column_bounds(headers['_vat_amount'])[2])
        self.assertEqual(headers['vat'][1][0].evidence,doc.pages[0].blocks[6].evidence)
        self.assertEqual(headers['_vat_amount'][1][0].evidence,doc.pages[0].blocks[6].evidence)
        item=run(spans).record.items[0]
        self.assertEqual(str(item.net.value),'100')
        self.assertEqual(str(item.vat_rate.value),'0.08')
        self.assertEqual({e.block_id for e in item.vat_rate.provenance.evidence},{'span-14'})

    def test_column_number_band_does_not_create_an_item_or_price(self):
        items=run(HEADERS+[
            ('1',.03,.33,.02),('2',.1,.33,.02),('4',.49,.33,.02),('5',.6,.33,.02),('6',.83,.33,.02),
            ('1',.03,.35,.02),('A sản phẩm',.1,.35,.2),('1',.49,.35,.02),('100',.6,.35,.06),('100',.83,.35,.06),
            ('2',.03,.39,.02),('B sản phẩm',.1,.39,.2),('1',.49,.39,.02),('200',.6,.39,.06),('200',.83,.39,.06)]).record.items
        self.assertEqual(len(items),2)
        self.assertEqual([str(item.unit_price.value) for item in items],['100','200'])

    def test_separate_serial_named_product_is_not_attached_to_distant_row(self):
        items=run(HEADERS+[
            ('1',.03,.36,.02),('A sản phẩm',.1,.36,.2),('1',.49,.36,.02),('100',.6,.36,.06),('100',.83,.36,.06),
            ('2',.03,.42,.02),('SN: sản phẩm khác',.1,.42,.25),('1',.49,.42,.02),('200',.6,.42,.06),('200',.83,.42,.06)]).record.items
        self.assertEqual(items[0].description.value,'A sản phẩm')
        self.assertEqual(items[1].description.value,'SN: sản phẩm khác')


if __name__=='__main__':unittest.main()
