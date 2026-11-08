"""Synthetic geometry regressions for failures observed in public invoices."""
import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.adapters.ocr.protocol import BlockOrigin
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile


def run(spans):return extract(fragmented(spans),'PDF',MASTER,ExtractionProfile(number_locale='VI')).record


class PublicLayoutRegressions(unittest.TestCase):
    def test_header_touching_wrapped_description_is_not_lost_as_sequence(self):
        r=run([('STT',.03,.47,.05),('Tên hàng hóa, dịch vụ',.16,.47,.18),
            ('Đơn vị tính',.44,.47,.10),('Số lượng',.59,.47,.08),
            ('Đơn giá',.73,.47,.07),('Thành tiền',.86,.47,.10),
            ('Phần mềm thử nghiệm (Gói 12',.081,.485,.32),
            ('1',.045,.53,.02),('tháng)',.081,.53,.06),('Gói',.47,.53,.04),
            ('1',.67,.53,.02),('4.080.000',.76,.53,.08),('4.080.000',.90,.53,.08),
            ('Cộng tiền hàng:',.42,.63,.15),('4.080.000',.90,.63,.08)])
        self.assertEqual(len(r.items),1)
        self.assertIn('tháng)',r.items[0].description.value)
        self.assertIn('Phần mềm',r.items[0].description.value)
        self.assertEqual(str(r.items[0].net.value),'4080000')
        self.assertEqual(str(r.items[0].quantity.value),'1')
        self.assertEqual(r.items[0].vat_treatment.status,'MISSING')
        self.assertNotEqual(r.item_discovery_status,'COMPLETE')
        self.assertGreaterEqual(len(r.items[0].description.provenance.evidence),2)

    def test_empty_buyer_name_is_section_not_literal_company_label(self):
        r=run([('Họ tên người mua hàng:',.05,.1,.4),('Tên đơn vị: CÔNG TY B',.05,.116,.45),
               ('Mã số thuế: 9876543210',.05,.14,.45)])
        self.assertEqual(r.parties.buyer.name.value,'CÔNG TY B')

    def test_footer_address_is_not_buyer_address(self):
        r=run([('Tên người mua: CÔNG TY B',.05,.1,.4),('Địa chỉ: Địa chỉ B',.05,.13,.4),
               ('STT',.05,.3,.04),('Địa chỉ: Công ty đóng tập hồ sơ',.05,.9,.6)])
        self.assertEqual(r.parties.buyer.address.value,'Địa chỉ B')

    def test_address_continuation_retains_evidence_and_stops_at_next_label(self):
        r=run([('Tên người mua: CÔNG TY B',.05,.1,.4),('Địa chỉ:',.05,.13,.1),
               ('Đường A, Phường B,',.2,.13,.4),('Thành phố C, Việt Nam',.2,.145,.4),
               ('Số tài khoản: 12345',.2,.16,.4)])
        self.assertEqual(r.parties.buyer.address.value,'Đường A, Phường B, Thành phố C, Việt Nam')
        self.assertEqual(len(r.parties.buyer.address.provenance.evidence),3)

    def test_two_party_columns_use_spatial_role(self):
        r=run([('Tên người bán: CÔNG TY A',.05,.1,.35),('Tên người mua: CÔNG TY B',.55,.1,.35),
               ('Mã số thuế: 1234567890',.05,.15,.35),('Mã số thuế: 9876543210',.55,.15,.35)])
        self.assertEqual(r.parties.seller.tax_id.value,'1234567890')
        self.assertEqual(r.parties.buyer.tax_id.value,'9876543210')

    def test_issuer_block_requires_buyer_boundary_and_unique_tax(self):
        spans=[('HÓA ĐƠN GIÁ TRỊ GIA TĂNG',.2,.05,.5),('CÔNG TY A',.05,.1,.3),
               ('Mã số thuế: 1234567890',.05,.12,.35),('Họ tên người mua hàng:',.05,.2,.3),
               ('Tên đơn vị: CÔNG TY B',.05,.23,.4),('Mã số thuế: 9876543210',.05,.26,.4)]
        self.assertEqual(run(spans).parties.seller.tax_id.value,'1234567890')
        self.assertEqual(run(spans[:3]).parties.seller.tax_id.status,'MISSING')
        spans.insert(3,('Mã số thuế: 1111111111',.05,.15,.4))
        self.assertEqual(run(spans).parties.seller.tax_id.status,'MISSING')

    def test_series_below_label_and_reject_ocr_extra_character(self):
        self.assertEqual(run([('Ký hiệu (Serial):',.7,.1,.2),('1C25TAA',.7,.116,.12)]).invoice.series.value,'1C25TAA')
        self.assertEqual(run([('Ký hiệu: 1C25TAAM',.7,.1,.25)]).invoice.series.status,'MISSING')

    def test_native_and_ocr_conflicting_values_survive(self):
        doc=fragmented([('MST người bán: 1234567890',.05,.1,.4),('MST người bán: 9876543210',.05,.101,.4)])
        blocks=list(doc.pages[0].blocks)
        blocks[1]=blocks[1].model_copy(update={'origins':(BlockOrigin(method='OCR',source_block_id='ocr'),)})
        doc=doc.model_copy(update={'pages':(doc.pages[0].model_copy(update={'blocks':tuple(blocks)}),)})
        r=extract(doc,'PDF',MASTER).record
        self.assertEqual(r.parties.seller.tax_id.status,'AMBIGUOUS')
        self.assertEqual({c.value for c in r.parties.seller.tax_id.candidates},{'1234567890','9876543210'})

    def test_table_without_tax_column_preserves_missing_tax(self):
        r=run([('STT',.05,.3,.03),('Tên hàng hóa, dịch vụ',.12,.3,.3),('Số lượng',.5,.3,.1),('Thành tiền',.75,.3,.15),
               ('1',.05,.35,.03),('Dịch vụ A',.12,.35,.3),('2',.5,.35,.1),('20.000',.8,.35,.1),
               ('Cộng tiền hàng:',.12,.4,.3),('20.000',.8,.4,.1)])
        self.assertEqual(len(r.items),1)
        self.assertEqual(str(r.items[0].net.value),'20000')
        self.assertEqual(r.items[0].vat_treatment.status,'MISSING')
        self.assertEqual(r.item_discovery_status,'UNKNOWN')

    def test_wrapped_description_above_centred_amount_does_not_merge_rows(self):
        r=run([('STT',.05,.3,.03),('Tên hàng hóa, dịch vụ',.12,.3,.3),('Số lượng',.5,.3,.1),('Thành tiền',.75,.3,.15),
               ('1',.05,.35,.03),('Dịch vụ A',.12,.35,.3),('1',.5,.35,.1),('10.000',.8,.35,.1),
               ('Dịch vụ B dòng đầu',.12,.39,.3),('2',.05,.40,.03),('dòng cuối',.12,.405,.3),
               ('1',.5,.405,.1),('20.000',.8,.405,.1),('Cộng tiền hàng:',.12,.45,.3)])
        self.assertEqual(len(r.items),2)
        self.assertNotIn('Dịch vụ B',r.items[0].description.value)
        self.assertIn('Dịch vụ B',r.items[1].description.value)

    def test_summary_columns_do_not_treat_first_amount_as_gross(self):
        r=run([('Thành tiền trước thuế GTGT',.42,.5,.16),('Tiền thuế GTGT',.62,.5,.14),('Cộng tiền thanh toán',.8,.5,.17),
               ('Tổng cộng (Total):',.05,.6,.25),('100.000',.48,.6,.09),('8.000',.68,.6,.07),('108.000',.86,.6,.1)])
        self.assertEqual(str(r.totals.net.value),'100000')
        self.assertEqual(str(r.totals.vat.value),'8000')
        self.assertEqual(str(r.totals.gross.value),'108000')


if __name__=='__main__':unittest.main()
