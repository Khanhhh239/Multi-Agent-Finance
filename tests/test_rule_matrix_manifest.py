"""Keep the published business matrix linked to real, resolvable tests."""
import json
import unittest
from pathlib import Path

from sme_fraud.rules import RULE_NAMES


class RuleMatrixManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads((Path(__file__).parent/'fixtures/rule_test_matrix.json').read_text(encoding='utf-8'))

    def test_every_registered_rule_has_all_seven_dimensions_and_routing(self):
        rows = self.matrix['rules']
        self.assertEqual(len(rows), len(RULE_NAMES))
        self.assertEqual({row['rule_id'] for row in rows}, set(RULE_NAMES))
        for row in rows:
            self.assertEqual(set(row['checks']), set(self.matrix['dimensions']))
            self.assertEqual(row['downstream']['status'], 'covered')

    def test_covered_cells_need_evidence_and_nonapplicable_cells_need_a_reason(self):
        for row in self.matrix['rules']:
            for cell in [*row['checks'].values(), row['downstream']]:
                self.assertIn(cell['status'], ('covered', 'not_applicable'))
                self.assertTrue(cell['note'].strip())
                self.assertTrue(cell['tests'] if cell['status'] == 'covered' else not cell['tests'])

    def test_every_cited_test_resolves_to_one_actual_test(self):
        refs = {ref for row in self.matrix['rules'] for cell in [*row['checks'].values(), row['downstream']]
                for ref in cell['tests']}
        for ref in sorted(refs):
            with self.subTest(reference=ref):
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromName(ref)
                self.assertEqual(loader.errors, [])
                self.assertEqual(suite.countTestCases(), 1)


if __name__ == '__main__':
    unittest.main()
