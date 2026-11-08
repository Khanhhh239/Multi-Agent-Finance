import unittest
from test_fragmented_headers import fragmented
from src.extraction.invoice_fields import values_on_page,party_role

class PartyRegionTests(unittest.TestCase):
    def test_generic_fields_in_two_columns_never_follow_reading_order(self):
        spans=[('Người bán',.05,.1,.25),('Người mua',.55,.1,.25),
            ('MST: 1234567890',.05,.17,.28),('MST: 9876543210',.55,.17,.28),
            ('Địa chỉ: Hà Nội',.05,.22,.28),('Địa chỉ: Đà Nẵng',.55,.22,.28)]
        for data in (spans,list(reversed(spans))):
            rows=list(values_on_page(fragmented(data).pages[0],sections=True))
            result={path:value for path,value,_ in rows}
            self.assertEqual(result['seller.tax_id'],'1234567890');self.assertEqual(result['buyer.tax_id'],'9876543210')
            self.assertEqual(result['seller.address'],'Hà Nội');self.assertEqual(result['buyer.address'],'Đà Nẵng')
    def test_split_labels_are_bound_in_their_column(self):
        spans=[('Người bán',.05,.1,.25),('Người mua',.55,.1,.25),
            ('MST:',.05,.17,.08),('1234567890',.15,.17,.2),('MST:',.55,.17,.08),('9876543210',.65,.17,.2)]
        result={p:v for p,v,_ in values_on_page(fragmented(spans).pages[0],sections=True)}
        self.assertEqual(result['seller.tax_id'],'1234567890');self.assertEqual(result['buyer.tax_id'],'9876543210')
    def test_geometry_conflicts_and_table_are_not_guessed(self):
        anchors=[('seller',(.05,.1,.3,.12)),('buyer',(.55,.1,.8,.12))]
        self.assertIsNone(party_role((.05,.3,.95,.33),anchors,.6))
        self.assertIsNone(party_role((.05,.7,.3,.73),anchors,.6))
        self.assertIsNone(party_role((.05,.05,.3,.07),anchors,.6))
