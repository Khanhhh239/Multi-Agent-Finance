import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'extraction_v1'))
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile
from src.recovery.field_reads import typed_read,text_read
from src.recovery.regions import plan_regions
from src.review.contracts import ReviewError


class FieldReadTests(unittest.TestCase):
    def test_name_strips_labels_and_role_anchor_without_guessing_words(self):
        self.assertEqual(text_read('parties.seller.name',['Tên người bán (Seller):','CÔNG TY A','Mã số thuế: 1234567890']),'CÔNG TY A')
        self.assertEqual(text_read('parties.buyer.name',['Tên đơn vị (Company)','CÔNG TY SIM FOODS']),'CÔNG TY SIM FOODS')
        self.assertIsNone(text_read('parties.seller.name',['Tên người mua: CÔNG TY B']))
        self.assertEqual(text_read('items.item-1.description',['Hàng A','tháng) tháng)']),'Hàng A tháng) tháng)')

    def test_tax_identifier_exact_digits_branch_and_split_label(self):
        for raw,want in [('Mã số thuế (Tax code): 0312662961-002','0312662961002'),
                         ('0312662961002','0312662961002')]:
            self.assertEqual(typed_read('parties.seller.tax_id',[raw],ExtractionProfile()),want)
        self.assertEqual(typed_read('parties.buyer.tax_id',['Mã số thuế (Tax code)','0109646560'],ExtractionProfile()),'0109646560')

    def test_tax_never_salvages_digits_from_bad_observation(self):
        for raw in ('0312662961.002','0109646560 m)','O109646560','MST người mua: 0109646560'):
            self.assertIsNone(typed_read('parties.seller.tax_id',[raw],ExtractionProfile()))

    def test_dates_strict_calendar_and_bilingual_label(self):
        p=ExtractionProfile()
        self.assertEqual(typed_read('invoice.issue_date',['Ngày (Day) 16 tháng (Month) 05 năm (Year) 2023)'],p),'2023-05-16')
        self.assertEqual(typed_read('invoice.issue_date',['Ngày lập: 16/05/2023'],p),'2023-05-16')
        for raw in ('Ngày 31 tháng 02 năm 2023','Ngày 16 tháng 05 năm 2023 the 19','KÝ NGÀY: 16/05/2023'):
            self.assertIsNone(typed_read('invoice.issue_date',[raw],p))

    def test_money_exact_decimal_and_ambiguous_locale_abstains(self):
        p=ExtractionProfile(number_locale='VI')
        self.assertEqual(typed_read('totals.gross',['Tổng thanh toán: 9.007.199.254.740.993,01'],p),'9007199254740993.01')
        self.assertIsNone(typed_read('totals.gross',['1.234'],ExtractionProfile()))
        self.assertIsNone(typed_read('totals.gross',['Tiền thuế: 1.234'],p))
        self.assertIsNone(typed_read('totals.gross',['100','200'],p))

    def test_series_and_number_do_not_trim_extra_letters(self):
        p=ExtractionProfile()
        self.assertEqual(typed_read('invoice.series',['Ký hiệu: 1K23THA'],p),'1K23THA')
        self.assertIsNone(typed_read('invoice.series',['Ký hiệu: 1K23THAM'],p))
        self.assertEqual(typed_read('invoice.number',['Số hóa đơn: 00002134'],p),'00002134')
        self.assertIsNone(typed_read('invoice.number',['Số tài khoản: 00002134'],p))

    def test_failed_tax_has_source_despite_no_candidate_and_keeps_role(self):
        doc=fragmented([('Tên người bán: CÔNG TY A',.05,.1,.4),
            ('Mã số thuế: 0312662961.002',.05,.13,.4),
            ('Tên người mua: CÔNG TY B',.05,.2,.4),('Mã số thuế: 0109646560 m)',.05,.23,.4)])
        a=extract(doc,'PDF',MASTER)
        self.assertEqual(a.record.parties.seller.tax_id.status,'MISSING')
        _,regions=plan_regions(a.record,a,doc,'parties.seller.tax_id')
        self.assertEqual([b.block_id for _,b in regions],['span-1'])
        _,regions=plan_regions(a.record,a,doc,'parties.buyer.tax_id')
        self.assertEqual([b.block_id for _,b in regions],['span-3'])

    def test_bad_date_retains_recoverable_observation_without_accepting_it(self):
        doc=fragmented([('Ngày 16 tháng 05 năm 2023 the 19',.4,.1,.4)])
        a=extract(doc,'PDF',MASTER)
        self.assertEqual(a.record.invoice.issue_date.status,'MISSING')
        self.assertEqual([b.block_id for _,b in plan_regions(a.record,a,doc,'invoice.issue_date')[1]],['span-0'])

    def test_below_label_tax_and_address_with_original_evidence(self):
        doc=fragmented([('Tên người mua: CÔNG TY B',.05,.1,.4),
            ('Mã số thuế:',.05,.13,.12),('0109646560',.05,.146,.13),
            ('Địa chỉ (Address):',.05,.18,.2),('Đường A, Phường B',.05,.196,.4),
            ('Thành phố C',.05,.212,.3),('Số tài khoản: 123',.05,.23,.4)])
        a=extract(doc,'PDF',MASTER)
        self.assertEqual(a.record.parties.buyer.tax_id.value,'0109646560')
        self.assertEqual(a.record.parties.buyer.address.value,'Đường A, Phường B Thành phố C')
        self.assertEqual({e.block_id for e in a.record.parties.buyer.address.provenance.evidence},{'span-3','span-4','span-5'})

    def test_address_translation_typo_only_changes_label(self):
        doc=fragmented([('Tên người mua: CÔNG TY B',.05,.1,.4),
            ('Địa chỉ (Addrass): Đường A (Addres)',.05,.13,.5)])
        a=extract(doc,'PDF',MASTER)
        self.assertEqual(a.record.parties.buyer.address.value,'Đường A (Addres)')

    def test_absent_or_competing_source_does_not_invent_region(self):
        doc=fragmented([('Tên người mua: CÔNG TY B',.05,.1,.4)])
        a=extract(doc,'PDF',MASTER)
        with self.assertRaises(ReviewError) as e:plan_regions(a.record,a,doc,'parties.buyer.tax_id')
        self.assertEqual(e.exception.code,'REGION_NO_EVIDENCE')

    def test_same_line_geometry_overrides_detector_reverse_order(self):
        doc=fragmented([('0109646560 m)',.3,.129,.2),('Tên người mua: CÔNG TY B',.05,.1,.4),
                        ('Mã số thuế:',.05,.13,.12)])
        a=extract(doc,'PDF',MASTER)
        _,regions=plan_regions(a.record,a,doc,'parties.buyer.tax_id')
        self.assertEqual([b.block_id for _,b in regions],['span-2','span-0'])


if __name__=='__main__':unittest.main()
