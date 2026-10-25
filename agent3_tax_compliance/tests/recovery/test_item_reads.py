import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'extraction_v1'))
from test_extraction import document,MASTER
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile
from src.recovery.field_reads import typed_read
from src.recovery.regions import plan_regions,supported


class ItemReadTests(unittest.TestCase):
    def test_table_recovery_does_not_starve_critical_identifiers(self):
        from src.recovery.policy import diagnose
        paths=('items.a.quantity','items.a.net','parties.seller.tax_id','totals.gross')
        field=SimpleNamespace(confidence_basis='UNAVAILABLE',status='MISSING',value=None,provenance=SimpleNamespace(evidence=[]))
        with patch('src.recovery.policy.flatten',return_value={path:field for path in paths}),patch('src.recovery.policy.plan_regions',return_value=({},[object()])):
            plan=diagnose(object(),object(),SimpleNamespace(pages=[]))
        self.assertEqual({e['field_path'] for e in plan['entries'] if e['state']=='SCHEDULED'},set(paths[2:]))
        self.assertEqual(plan['scheduled_crops'],2)

    def test_exact_numbers_locale_and_competing_cells(self):
        path='items.row-1.unit_price';vi=ExtractionProfile(number_locale='VI')
        self.assertEqual(typed_read(path,['Đơn giá:','9.007.199.254.740.993,01'],vi),'9007199254740993.01')
        self.assertEqual(typed_read('items.row-1.quantity',['Số lượng: 0'],vi),'0')
        self.assertEqual(typed_read('items.row-1.net',['Thành tiền: (1.200,50)'],vi),'-1200.50')
        for texts in (['100','200'],['Số lượng: 100'],['1O0'],['100 abc']):
            self.assertIsNone(typed_read(path,texts,vi))
        self.assertIsNone(typed_read(path,['1.234'],ExtractionProfile()))

    def test_vat_requires_printed_percent_and_preserves_exemptions(self):
        profile=ExtractionProfile()
        for raw,treatment,rate in [('8%','TAXABLE_RATE','0.08'),('0%','TAXABLE_RATE','0'),('KCT','KCT',None),('KKKNT','KKKNT',None)]:
            self.assertEqual(typed_read('items.a.vat_treatment',[raw],profile),treatment)
            self.assertEqual(typed_read('items.a.vat_rate',[raw],profile),rate)
        for raw in ('8','108%','8% 10%','Tổng thuế: 8%'):
            self.assertIsNone(typed_read('items.a.vat_rate',[raw],profile))

    def test_invalid_cells_keep_their_source_and_do_not_borrow_other_columns(self):
        doc=document(['Mặt hàng 1','Tên hàng: Hàng A','Số lượng: 1O0','Tiền trước thuế: 100','Thuế suất: 8x'])
        artifact=extract(doc,'PDF',MASTER);item=artifact.record.items[0];prefix='items.'+item.item_id
        _,regions=plan_regions(artifact.record,artifact,doc,prefix+'.quantity')
        self.assertEqual(len(regions),1);self.assertIn('1O0',regions[0][1].text_raw)
        _,regions=plan_regions(artifact.record,artifact,doc,prefix+'.vat_rate')
        self.assertEqual(len(regions),1);self.assertIn('8x',regions[0][1].text_raw)
        self.assertTrue(supported(prefix+'.net'));self.assertFalse(supported(prefix+'.gross'))


if __name__=='__main__':unittest.main()
