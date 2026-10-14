"""Financial values with a font baseline offset must retain source evidence."""
import unittest
from test_fragmented_headers import fragmented
from test_extraction import MASTER
from src.extraction.service import extract
from src.extraction.contracts import ExtractionProfile


def run(spans):
    return extract(fragmented(spans), 'PDF', MASTER, ExtractionProfile(number_locale='VI')).record


class OffsetFinancialValueTests(unittest.TestCase):
    def test_printed_zero_above_total_label_baseline(self):
        record = run([('Cộng tiền hàng:', .34, .565, .22), ('0', .67, .565, .01),
                      ('0', .955, .576, .01), ('Tổng cộng tiền thanh toán:', .647, .586, .204)])
        self.assertEqual(str(record.totals.gross.value), '0')
        self.assertEqual({e.block_id for e in record.totals.gross.provenance.evidence}, {'span-2', 'span-3'})

    def test_distant_previous_row_not_borrowed(self):
        record = run([('Cộng tiền hàng:', .34, .56, .22), ('100.000', .9, .56, .07),
                      ('Tổng cộng tiền thanh toán:', .647, .60, .204)])
        self.assertEqual(record.totals.gross.status, 'MISSING')

    def test_two_offset_values_remain_ambiguous(self):
        record = run([('Tổng cộng tiền thanh toán:', .6, .60, .2),
                      ('100.000', .82, .590, .07), ('108.000', .92, .590, .07)])
        self.assertEqual(record.totals.gross.status, 'AMBIGUOUS')


if __name__ == '__main__':
    unittest.main()
