"""Synthetic regressions for wrapped labels and summary column alignment."""
import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.extraction.contracts import ExtractionProfile
from src.extraction.service import extract


def result(spans):
    return extract(fragmented(spans), 'PDF', MASTER, ExtractionProfile(number_locale='VI'))


class WrappedColumnsTests(unittest.TestCase):
    def test_quantity_fragments_do_not_create_invoice_number(self):
        artifact = result([
            ('Số hóa đơn: 0002781', .6, .1, .3),
            ('Tên hàng hóa dịch vụ', .12, .3, .25),
            ('Số', .5, .3, .05), ('lượng', .5, .315, .05),
            ('Đơn giá', .65, .3, .09), ('Thành tiền', .83, .3, .12),
            ('Hàng A', .12, .36, .15), ('2', .52, .36, .02),
            ('100', .7, .36, .04), ('200', .88, .36, .04)])
        self.assertEqual(artifact.segmentation.status, 'SINGLE_CANDIDATE')
        self.assertEqual(artifact.record.invoice.number.value, '0002781')
        self.assertEqual(len(artifact.record.items), 1)
        self.assertEqual(str(artifact.record.items[0].quantity.value), '2')

    def test_real_competing_numbers_still_require_split(self):
        artifact = result([('Số hóa đơn: 001', .1, .1, .3),
                           ('Số hóa đơn: 002', .1, .2, .3)])
        self.assertEqual(artifact.segmentation.status, 'REVIEW_SPLIT')
        self.assertIsNone(artifact.record)

    def test_second_invoice_number_below_first_table_still_requires_split(self):
        artifact = result([
            ('Số:', .6, .1, .04), ('001', .68, .1, .06),
            ('STT', .02, .3, .04), ('Tên hàng hóa dịch vụ', .1, .3, .27),
            ('Số:', .6, .6, .04), ('002', .68, .6, .06),
            ('STT', .02, .8, .04), ('Tên hàng hóa dịch vụ', .1, .8, .27)])
        self.assertEqual(artifact.segmentation.status, 'REVIEW_SPLIT')
        self.assertIsNone(artifact.record)

    def test_wrapped_compact_headers_preserve_tax_and_evidence(self):
        record = result([
            ('Tênhàng hóa, dịch vụ', .1, .3, .27), ('SL', .48, .3, .04),
            ('Đơngiá', .59, .3, .08), ('Thành', .72, .3, .08),
            ('tiền', .73, .315, .05), ('Thuế', .88, .3, .06), ('suất', .88, .315, .06),
            ('Hàng A', .1, .37, .15), ('2', .49, .37, .02),
            ('100', .62, .37, .04), ('200', .76, .37, .04), ('8%', .89, .37, .04),
            ('Hàng B', .1, .4, .15), ('1', .49, .4, .02),
            ('300', .62, .4, .04), ('300', .76, .4, .04), ('10%', .89, .4, .04),
            ('Tổng cộng', .1, .45, .2)]).record
        self.assertEqual(len(record.items), 2)
        self.assertEqual([str(item.vat_rate.value) for item in record.items], ['0.08', '0.1'])
        self.assertGreaterEqual(len(record.items[0].net.provenance.evidence), 1)
        self.assertNotEqual(record.item_discovery_status, 'COMPLETE')

    def test_summary_uses_coherent_nearest_header_band(self):
        record = result([
            ('Tiền thuế GTGT', .86, .2, .09),
            ('Cộng tiền hàng', .35, .5, .15), ('Tiền thuế GTGT', .6, .5, .12),
            ('Tổng tiền thanh toán', .8, .5, .18),
            ('Tổng cộng', .05, .56, .18), ('1.000', .53, .56, .05),
            ('80', .75, .56, .03), ('1.080', .93, .56, .05)]).record
        self.assertEqual(str(record.totals.net.value), '1000')
        self.assertEqual(str(record.totals.vat.value), '80')
        self.assertEqual(str(record.totals.gross.value), '1080')

    def test_missing_tax_not_inferred_from_totals(self):
        record = result([
            ('Tên hàng hóa dịch vụ', .1, .3, .27), ('SL', .48, .3, .04),
            ('Thành tiền', .75, .3, .15), ('Hàng A', .1, .36, .2),
            ('1', .49, .36, .02), ('1.000', .85, .36, .06),
            ('Tổng tiền thuế: 80', .1, .5, .3)]).record
        self.assertEqual(record.items[0].vat_rate.status, 'MISSING')
        self.assertEqual(record.items[0].vat_treatment.status, 'MISSING')

    def test_unreadable_amount_keeps_explicit_row_and_missing_cell(self):
        record = result([
            ('STT', .02, .3, .04), ('Tên hàng hóa dịch vụ', .1, .3, .27),
            ('Số lượng', .45, .3, .08), ('Đơn giá', .6, .3, .08), ('Thành tiền', .8, .3, .13),
            ('1', .03, .36, .02), ('Hàng A', .1, .36, .2),
            ('10', .49, .36, .03), ('495.000', .62, .36, .08), ('A.950.000', .83, .36, .1),
            ('2', .03, .4, .02), ('Hàng B', .1, .4, .2),
            ('1', .49, .4, .03), ('100', .62, .4, .05), ('100', .83, .4, .05)]).record
        self.assertEqual(len(record.items), 2)
        self.assertEqual(record.items[0].net.status, 'MISSING')
        self.assertEqual(str(record.items[1].net.value), '100')

    def test_conflicting_subtotal_and_summary_remain_ambiguous(self):
        record = result([
            ('Cộng tiền hàng', .35, .4, .15), ('1.000', .53, .4, .05),
            ('80', .75, .4, .03), ('1.080', .93, .4, .05),
            ('Cộng tiền hàng', .35, .5, .15), ('Tiền thuế GTGT', .6, .5, .12),
            ('Tổng tiền thanh toán', .8, .5, .18),
            ('Tổng cộng', .05, .56, .18), ('900', .53, .56, .05),
            ('80', .75, .56, .03), ('1.080', .93, .56, .05)]).record
        self.assertEqual(record.totals.net.status, 'AMBIGUOUS')

    def test_date_continuation_cannot_be_borrowed_as_row_description(self):
        record = result([
            ('STT', .02, .3, .04), ('Tên hàng hóa dịch vụ', .1, .3, .27),
            ('SL', .48, .3, .04), ('Đơn giá', .6, .3, .08), ('Thành tiền', .8, .3, .13),
            ('Dịch vụ đến', .1, .35, .2), ('1', .03, .36, .02),
            ('1', .49, .36, .03), ('100', .62, .36, .05), ('100', .83, .36, .05),
            ('25/04/2025', .1, .375, .15)]).record
        self.assertEqual(len(record.items), 1)
        self.assertEqual(record.items[0].description.value, 'Dịch vụ đến 25/04/2025')

    def test_tax_summary_does_not_create_item(self):
        record = result([
            ('Tên hàng hóa dịch vụ', .1, .3, .27), ('SL', .48, .3, .04),
            ('Đơn giá', .6, .3, .08), ('Thành tiền', .8, .3, .13),
            ('Hàng A', .1, .36, .2), ('1', .49, .36, .03),
            ('100', .62, .36, .05), ('100', .83, .36, .05),
            ('Loại không chịu thuế (Non taxable)', .1, .5, .3),
            ('Loại thuế suất 10%', .1, .55, .3), ('10', .62, .55, .04),
            ('110', .83, .55, .05)]).record
        self.assertEqual(len(record.items), 1)

    def test_leading_discount_column_is_not_net_total(self):
        record = result([
            ('Thành tiền', .6, .4, .08), ('Tiền thuế GTGT', .76, .4, .08),
            ('Tiền thanh toán', .89, .4, .09),
            ('Tổng cộng hóa đơn', .1, .46, .25),
            ('0', .58, .46, .02), ('1.000', .63, .46, .06),
            ('80', .8, .46, .03), ('1.080', .92, .46, .06)]).record
        self.assertEqual(str(record.totals.net.value), '1000')
        self.assertEqual(str(record.totals.vat.value), '80')
        self.assertEqual(str(record.totals.gross.value), '1080')


if __name__ == '__main__':
    unittest.main()
