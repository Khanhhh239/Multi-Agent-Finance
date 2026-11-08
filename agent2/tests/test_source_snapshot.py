import unittest
from sme_fraud.evidence_cases import prepare
from sme_fraud.source_snapshot import inspect_sources


class SourceSnapshotTest(unittest.TestCase):
    def test_document_gaps_can_be_inspected_without_any_transaction(self):
        c,row,_,scope = prepare('F3','positive',901)
        c.tables['transactions'] = []
        result = inspect_sources(c.tables,row['posted_at'])
        self.assertTrue(next(f for f in result if f['scope']==scope)['signal'])

    def test_invoice_aging_without_fake_heartbeat_entry(self):
        c,row,_,scope = prepare('F4','positive',902)
        c.tables['transactions'] = []
        result = inspect_sources(c.tables,row['posted_at'])
        finding = next(f for f in result if f['scope']==scope)
        self.assertTrue(finding['signal'])
        self.assertEqual(finding['points'],0)

    def test_future_cutoff_needs_a_new_complete_receipt_snapshot(self):
        c,row,_,scope = prepare('F4','positive',903)
        c.tables['transactions'] = []
        finding = next(f for f in inspect_sources(c.tables,'2025-09-13T11:00:00+07:00') if f['scope']==scope)
        self.assertIsNone(finding['signal'])

    def test_utc_and_vietnam_cutoffs_represent_the_same_snapshot(self):
        c,row,_,scope = prepare('F4','positive',904)
        c.tables['transactions'] = []
        self.assertEqual(inspect_sources(c.tables,row['posted_at']),inspect_sources(c.tables,'2025-09-12T04:00:00+00:00'))


if __name__=='__main__':
    unittest.main()
