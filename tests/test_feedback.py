import csv
import json
import tempfile
import unittest
from pathlib import Path

from sme_fraud.feedback import read_audit, record_feedback
from sme_fraud.generate import write_csv


class FeedbackTest(unittest.TestCase):
    def test_human_feedback_is_append_only_and_information_gap_stays_open(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_csv(root / 'case_queue.csv', [dict(case_id='RC_test', last_seen_at='2025-08-01T12:00:00+07:00')])
            initial = (root / 'case_queue.csv').read_bytes()
            record_feedback(root, 'RC_test', 'information_gap', 'Ke toan', 'Can bien ban', '2026-10-13T09:00:00+07:00')
            with (root / 'case_review_states.csv').open(encoding='utf-8-sig', newline='') as stream:
                self.assertEqual(next(csv.DictReader(stream))['status'], 'awaiting_information')
            audit_before = (root / 'feedback_audit.jsonl').read_bytes()
            record_feedback(root, 'RC_test', 'false_positive', 'Ke toan', 'Da doi chieu ho so', '2026-10-13T10:00:00+07:00')
            self.assertTrue((root / 'feedback_audit.jsonl').read_bytes().startswith(audit_before))
            self.assertEqual((root / 'case_queue.csv').read_bytes(), initial)
            self.assertEqual(len(read_audit(root / 'feedback_audit.jsonl')), 2)
            with self.assertRaises(ValueError):
                record_feedback(root, 'RC_test', 'false_positive', 'Ke toan', '', '2026-10-13T11:00:00+07:00')
            with self.assertRaises(ValueError):
                record_feedback(root, 'unknown', 'false_positive', 'Ke toan', 'note')
            # Tampering with an earlier event is detectable without rewriting history.
            text = (root / 'feedback_audit.jsonl').read_text(encoding='utf-8')
            (root / 'feedback_audit.jsonl').write_text(text.replace('Can bien ban', 'changed'), encoding='utf-8')
            with self.assertRaises(ValueError):
                read_audit(root / 'feedback_audit.jsonl')


if __name__ == '__main__':
    unittest.main()
