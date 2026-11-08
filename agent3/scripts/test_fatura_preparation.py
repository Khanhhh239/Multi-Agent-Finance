"""Semantic regressions for the offline FATURA importer (standard unittest)."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('fatura_prep',Path(__file__).with_name('prepare_fatura_dataset.py'))
prep=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


class FaturaMappingTests(unittest.TestCase):
    def test_ambiguous_numeric_date_is_not_guessed(self):
        self.assertIsNone(prep.normalize_date('Date: 03/04/2026'))
        self.assertEqual(prep.normalize_date('Date: 14/04/2026'),'2026-04-14')
        self.assertEqual(prep.normalize_date('Date: 20-Mar-2008'),'2008-03-20')

    def test_money_does_not_select_rate_or_largest_candidate(self):
        self.assertEqual(prep.normalize_money('TAX:VAT (3.88%): 28.18 EUR'),'28.18')
        self.assertIsNone(prep.normalize_money('TOTAL: 100.00 USD or 200.00 EUR'))
        self.assertIsNone(prep.normalize_money('TOTAL: 1.234 EUR'))

    def test_money_exact_large_value_and_explicit_grouping(self):
        self.assertEqual(prep.normalize_money('TOTAL: 9007199254740993.01 USD'),'9007199254740993.01')
        self.assertEqual(prep.normalize_money('TOTAL: 1,234.56 EUR'),'1234.56')
        self.assertEqual(prep.normalize_money('TOTAL: 1.234,56 EUR'),'1234.56')

    def test_non_vat_tax_is_not_vat(self):
        self.assertIsNone(prep.normalize_value('totals.vat','TAX','GST (5%): 10.00 INR'))
        self.assertEqual(prep.normalize_value('totals.vat','TAX','VAT (5%): 10.00 EUR'),'10.00')

    def test_buyer_name_excludes_address_and_preserves_invoice_zeros(self):
        self.assertEqual(prep.normalize_value('buyer.name','BILL_TO','BILL_TO:\nExample Buyer\n123 Street'),'Example Buyer')
        self.assertEqual(prep.normalize_value('invoice.number','NUMBER','INVOICE # 000123'),'000123')
        self.assertEqual(prep.normalize_value('invoice.number','NUMBER','INVOICE ID INV/27-92/824'),'INV/27-92/824')

    def test_geometry_changes_origin_and_requires_cross_format_support(self):
        box={'bbox':[[10,80],[30,60]]}
        mapped,status=prep.transform_bbox(box,100,100,[[10,20,30,40]])
        self.assertEqual(mapped,[0.1,0.2,0.3,0.4])
        self.assertEqual(status,'HF_GEOMETRY_CONFIRMED')
        self.assertIsNone(prep.transform_bbox(box,100,100,[[50,50,70,70]])[0])
        self.assertIsNone(prep.transform_bbox({'bbox':[[-1,80],[30,60]]},100,100,[])[0])

    def test_no_tax_id_or_items_invented_from_source(self):
        ann,_,_=prep.map_annotation({'GSTIN_SELLER':{'text':'1234567890'},'TABLE':[]},{'bboxes':[]},595,841,'test')
        fields={f['field_path']:f for f in ann['fields']}
        for path in ['seller.tax_id','buyer.tax_id','vat_category','items']:
            self.assertEqual(fields[path]['status'],'NOT_ANNOTATED')
            self.assertIsNone(fields[path]['normalized_value'])

    def test_splits_are_disjoint_and_inspected_templates_stay_in_dev(self):
        groups=prep.split_groups()
        self.assertEqual({k:len(v) for k,v in groups.items()},{'dev':30,'calibration':10,'test':10})
        self.assertEqual(set.union(*(set(v) for v in groups.values())),set(range(1,51)))
        for a,b in [('dev','calibration'),('dev','test'),('calibration','test')]:
            self.assertFalse(set(groups[a])&set(groups[b]))
        self.assertTrue(set(prep.CFG['previously_inspected_templates'])<=set(groups['dev']))


if __name__=='__main__':unittest.main()
