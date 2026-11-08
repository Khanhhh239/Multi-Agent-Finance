"""Verified batch publication, automatic expiry and independent company tables."""
import csv
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.generate import write_csv
from sme_fraud.sync_dynamic_thresholds import sync, load_snapshot, sha
from sme_fraud.dynamic_thresholds import ThresholdPolicy
from test_dynamic_threshold_sources import transaction
from test_dynamic_thresholds import NOW


def dataset(root, second=False):
    directory = root/'data'
    directory.mkdir(exist_ok=True)
    tables = dict(companies=[dict(company_id=c) for c in ('C001', 'C002')],
        transactions=[transaction(str(i), posted_at=(NOW-timedelta(days=i+1)).isoformat(),
            amount_vnd=1_000_000 if not second else 2_000_000) for i in range(4)]+
            [transaction('OTHER', company_id='C002', posted_at=(NOW-timedelta(days=1)).isoformat(), amount_vnd=100_000_000)])
    for name, rows in tables.items():
        write_csv(directory/f'{name}.csv', rows)
    (directory/'manifest.json').write_text(json.dumps(dict(files={p.name:dict(sha256=sha(p)) for p in directory.glob('*.csv')})))
    return directory


class ThresholdSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = dataset(self.root)
        self.output = self.root/'parameters'
        self.policy = ThresholdPolicy(minimum_samples=2, cycle_enabled=False)

    def tearDown(self):
        self.temp.cleanup()

    def run_sync(self, cutoff=None, **values):
        return sync(self.data, self.output, cutoff or NOW.isoformat(), policy=self.policy, **values)

    def test_idempotent_separate_company_csvs_and_unchanged_full_sources(self):
        before = {p.name:sha(p) for p in self.data.iterdir()}
        self.assertTrue(self.run_sync()['changed'])
        self.assertFalse(self.run_sync()['changed'])
        saved = load_snapshot(self.output)
        self.assertEqual(saved['summary']['companies'], 2)
        for company, name in saved['company_files'].items():
            with (self.output/'snapshots'/saved['fingerprint']/name).open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(rows)
            self.assertEqual({r['company_id'] for r in rows}, {company})
        self.assertEqual({p.name:sha(p) for p in self.data.iterdir()}, before)

    def test_new_source_batch_updates_threshold_and_clock_expiry_removes_old_samples(self):
        self.run_sync()
        first = load_snapshot(self.output)
        dataset(self.root, second=True)
        self.run_sync()
        second = load_snapshot(self.output)
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])
        row = next(r for r in second['parameters'] if r['company_id'] == 'C001' and r['window_days'] == 90)
        self.assertEqual(row['threshold_vnd'], 2_000_000)
        self.assertTrue((self.output/'snapshots'/first['fingerprint']/'commit.json').exists())
        self.run_sync((NOW+timedelta(days=100)).isoformat())
        self.assertTrue(all(r['threshold_vnd'] is None for r in load_snapshot(self.output)['parameters']))

    def test_tampered_source_or_failed_publication_preserve_current_tables(self):
        self.run_sync()
        pointer = (self.output/'latest.json').read_bytes()
        with (self.data/'transactions.csv').open('a') as stream:
            stream.write('tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.run_sync()
        self.assertEqual((self.output/'latest.json').read_bytes(), pointer)
        dataset(self.root)
        import sme_fraud.sync_dynamic_thresholds as module
        original = module.atomic_json

        def fail_pointer(path, payload):
            if path.name == 'latest.json':
                raise OSError('simulated failure')
            return original(path, payload)

        with patch.object(module, 'atomic_json', fail_pointer), self.assertRaises(OSError):
            self.run_sync((NOW+timedelta(days=1)).isoformat())
        self.assertEqual((self.output/'latest.json').read_bytes(), pointer)
        self.assertFalse((self.output/'.threshold-sync.lock').exists())
        # A committed but unpublished snapshot is reusable after a retry.
        self.assertTrue(self.run_sync((NOW+timedelta(days=1)).isoformat())['changed'])
        load_snapshot(self.output)

    def test_corrupt_artifacts_unknown_company_backward_cutoff_and_in_place_output_are_rejected(self):
        self.run_sync()
        for cutoff, values in (((NOW-timedelta(days=1)).isoformat(), {}), (None, {'companies':['OTHER']})):
            with self.assertRaises(ValueError):
                self.run_sync(cutoff, **values)
        with self.assertRaises(ValueError):
            sync(self.data, self.data/'parameters', NOW.isoformat())
        saved = load_snapshot(self.output)
        (self.output/'snapshots'/saved['fingerprint']/saved['company_files']['C001']).write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            load_snapshot(self.output)

    def test_concurrent_writers_and_company_selection(self):
        self.output.mkdir()
        (self.output/'.threshold-sync.lock').write_text('other writer')
        with self.assertRaises(FileExistsError):
            self.run_sync()
        (self.output/'.threshold-sync.lock').unlink()
        self.run_sync(companies=['C002'])
        self.assertEqual(set(load_snapshot(self.output)['company_files']), {'C002'})


if __name__ == '__main__':
    unittest.main()
