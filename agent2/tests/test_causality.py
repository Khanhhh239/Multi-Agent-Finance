"""Meaningful regression checks for temporal leakage, labels and scenario diversity."""
import copy
import unittest

from sme_fraud.features import build_features
from sme_fraud.generate import Generator, FAMILIES, HARD_NEGATIVES


class CausalFeaturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = Generator(10_000,.005,20261012,2).finalize()
        cls.features = build_features(cls.tables)

    def test_future_transactions_do_not_change_past_features(self):
        cutoff = self.tables["transactions"][600]["posted_at"]
        truncated = dict(self.tables)
        truncated["transactions"] = [r for r in self.tables["transactions"] if r["posted_at"]<=cutoff]
        expected = [r for r in self.features if r["transaction_id"] in {t["transaction_id"] for t in truncated["transactions"]}]
        self.assertEqual(build_features(truncated),expected)

    def test_future_master_and_event_records_do_not_change_past_features(self):
        cutoff = self.tables["transactions"][1200]["posted_at"]
        short = copy.deepcopy(self.tables)
        short["transactions"] = [r for r in short["transactions"] if r["posted_at"]<=cutoff]
        with_future = build_features(short)
        for name,column in (("employees","recorded_at"),("vendors","recorded_at"),("advances","recorded_at"),
                             ("entity_links","observed_at"),("attendance","observed_at"),
                             ("vendor_status_history","observed_at"),("bank_account_changes","observed_at"),
                             ("advance_events","observed_at")):
            short[name] = [r for r in short[name] if r[column]<=cutoff]
        self.assertEqual(build_features(short),with_future)

    def test_truth_and_split_are_not_feature_inputs(self):
        changed = dict(self.tables)
        changed["labels"],changed["splits"] = [],[]
        self.assertEqual(build_features(changed),self.features)

    def test_simultaneous_payments_cannot_see_each_other(self):
        original = next(r for r in self.tables["transactions"] if r["txn_type"]=="vendor_payment")
        duplicate = dict(original,transaction_id="T999999999")
        changed = dict(self.tables)
        changed["transactions"] = [r for r in self.tables["transactions"] if r["posted_at"]<=original["posted_at"]] + [duplicate]
        changed['journal_lines'] = self.tables['journal_lines'] + [
            dict(line,transaction_id=duplicate['transaction_id']) for line in self.tables['journal_lines']
            if line['transaction_id']==original['transaction_id']]
        result = {r["transaction_id"]:r for r in build_features(changed)}
        expected = next(r for r in self.features if r["transaction_id"]==original["transaction_id"])
        self.assertEqual(result[original["transaction_id"]],expected)
        copied = dict(result[duplicate["transaction_id"]],transaction_id=original["transaction_id"])
        self.assertEqual(copied,expected)

    def test_same_seed_is_reproducible(self):
        other = Generator(10_000,.005,20261012,2).finalize()
        self.assertEqual(other["transactions"],self.tables["transactions"])
        self.assertEqual(other["labels"],self.tables["labels"])

    def test_fraud_and_hard_negative_coverage(self):
        truth = self.tables["labels"]
        self.assertEqual(sum(r["is_fraud"] for r in truth),50)
        self.assertEqual({r["fraud_type"] for r in truth if r["is_fraud"]},set(FAMILIES))
        self.assertEqual({r["hard_negative_type"] for r in truth if r["hard_negative_type"]},set(HARD_NEGATIVES))
        self.assertTrue(all(not r["is_fraud"] for r in truth if r["hard_negative_type"]))
        self.assertIn("ghost_employee_payroll",{r["variant"] for r in truth})
        self.assertIn("multiple_recipients",{r["variant"] for r in truth})


if __name__=="__main__":
    unittest.main()
