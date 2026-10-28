import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile


def run(spans):return extract(fragmented(spans),'PDF',MASTER,ExtractionProfile(number_locale='VI'))


class Round3PartyTests(unittest.TestCase):
    def test_unlabelled_issuer_address_is_not_appended_to_company_name(self):
        record=run([('HÓA ĐƠN GIÁ TRỊ GIA TĂNG',.2,.04,.5),('CÔNG TY A',.1,.10,.3),
            ('Lô D26, Phường B, Quận C, Thành phố D',.1,.118,.6),
            ('Mã số thuế: 1234567890',.1,.137,.4),('Tên người mua: CÔNG TY B',.1,.2,.5)]).record
        self.assertEqual(record.parties.seller.name.value,'CÔNG TY A')

    def test_buyer_section_company_name_gloss_and_numeric_noise(self):
        record=run([('Người mua (Buyer):',.1,.2,.2),('Tên đơn vị (Company name):',.1,.23,.23),
                    ('CÔNG TY B',.4,.23,.3),('Địa chỉ:',.1,.26,.1),('Đường B',.4,.26,.3)]).record
        self.assertEqual(record.parties.buyer.name.value,'CÔNG TY B')
        self.assertEqual(record.parties.buyer.address.value,'Đường B')
        noisy=run([('Tên người mua: 300',.1,.2,.4)])
        self.assertEqual(noisy.record.parties.buyer.name.status,'MISSING')
        self.assertTrue(any(i.code=='UNPARSEABLE_FIELD' for i in noisy.issues))

    def test_company_name_starting_with_don_vi_is_not_a_new_label(self):
        record=run([('Tên người mua: ĐƠN VỊ MUA GIẢ LẬP',.1,.2,.6)]).record
        self.assertEqual(record.parties.buyer.name.value,'ĐƠN VỊ MUA GIẢ LẬP')

    def test_address_one_word_per_block_keeps_aligned_next_line(self):
        record=run([('Tên người mua: CÔNG TY B',.1,.1,.6),('Địa chỉ:',.1,.2,.1),
            ('Số',.3,.2,.02),('12',.33,.2,.02),('Đường',.36,.2,.05),('B,',.42,.2,.02),
            ('Thành phố C',.3,.215,.3),('Số tài khoản: 1234',.3,.23,.4)]).record
        self.assertEqual(record.parties.buyer.address.value,'Số 12 Đường B, Thành phố C')

    def test_name_continuation_stops_before_fused_tax_label(self):
        record=run([('Tên người mua: CÔNG TY A',.1,.2,.5),
            ('CHI NHÁNH B Mã số thuế: 1234567890',.1,.215,.6)]).record
        self.assertEqual(record.parties.buyer.name.value,'CÔNG TY A CHI NHÁNH B')

    def test_fused_native_tax_headers_keep_each_mixed_rate(self):
        record=run([('STT',.02,.3,.03),('Tên hàng hóa dịch vụ',.1,.3,.2),('SL',.4,.3,.03),
            ('Đơn giá',.5,.3,.08),('Thành tiền',.65,.3,.1),
            ('Thuế suất',.78,.3,.08),('Tiền thuế',.87,.3,.1),
            ('1',.03,.36,.02),('Hàng A',.1,.36,.2),('1',.41,.36,.02),('100',.53,.36,.04),('100',.7,.36,.04),('8%',.81,.36,.03),('8',.92,.36,.02),
            ('2',.03,.4,.02),('Hàng B',.1,.4,.2),('1',.41,.4,.02),('100',.53,.4,.04),('100',.7,.4,.04),('10%',.81,.4,.03),('10',.92,.4,.02)]).record
        self.assertEqual([str(i.vat_rate.value) for i in record.items],['0.08','0.1'])
