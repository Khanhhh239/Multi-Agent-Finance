"""Atomic batch publication, provenance and history of entity graph snapshots."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.generate import write_csv
from sme_fraud.sync_entity_graph import sync, load_snapshot
from sme_fraud.feature_contract import sha
from test_entity_graph import sources, CUTOFF


def dataset(root, tables=None):
    data = root/'data'
    data.mkdir(exist_ok=True)
    tables = tables or sources()
    tables = dict(tables, companies=[dict(company_id='C001', name='SME fixture')])
    for name, rows in tables.items():
        write_csv(data/f'{name}.csv', rows, list(rows[0]) if rows else ['company_id'])
    manifest = dict(files={p.name: dict(sha256=sha(p)) for p in data.glob('*.csv')})
    (data/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return data


class EntityGraphSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = dataset(self.root)
        self.output = self.root/'graphs'

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_json_snapshot_is_idempotent_and_sources_remain_unchanged(self):
        before = {p.name: sha(p) for p in self.data.iterdir()}
        first = sync(self.data, self.output, CUTOFF)
        second = sync(self.data, self.output, CUTOFF)
        self.assertTrue(first['changed'])
        self.assertFalse(second['changed'])
        self.assertEqual(first['fingerprint'], second['fingerprint'])
        saved = load_snapshot(self.output)
        self.assertEqual(saved['summary']['findings'], 4)
        self.assertEqual(saved['source_sha256']['vendors.csv'], before['vendors.csv'])
        self.assertEqual({p.name: sha(p) for p in self.data.iterdir()}, before)

    def test_later_master_batch_retires_old_relation_and_keeps_prior_snapshot(self):
        sync(self.data, self.output, CUTOFF)
        first_pointer = json.loads((self.output/'latest.json').read_text())
        tables = sources()
        tables['vendors'].append(dict(tables['vendors'][0], phone='', recorded_at='2025-09-01T00:00:00+07:00'))
        dataset(self.root, tables)
        sync(self.data, self.output, '2025-09-02T00:00:00+07:00')
        graph = load_snapshot(self.output)['companies']['C001']
        hit = next(f for f in graph['findings'] if f['type'] == 'vendor_employee_shared_phone')
        self.assertEqual(hit['vendor_ids'], ['V2'])
        self.assertTrue((self.output/'snapshots'/first_pointer['snapshot']).is_file())

    def test_checksum_failure_and_failed_publication_preserve_current_pointer(self):
        sync(self.data, self.output, CUTOFF)
        previous = (self.output/'latest.json').read_bytes()
        with (self.data/'vendors.csv').open('a') as stream:
            stream.write('tampering')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            sync(self.data, self.output, CUTOFF)
        self.assertEqual((self.output/'latest.json').read_bytes(), previous)
        self.assertFalse((self.output/'.graph-sync.lock').exists())
        dataset(self.root)
        import sme_fraud.sync_entity_graph as module
        original = module.atomic_json

        def fail_pointer(path, payload):
            if path.name == 'latest.json':
                raise OSError('simulated crash before commit')
            return original(path, payload)

        with patch.object(module, 'atomic_json', fail_pointer), self.assertRaises(OSError):
            sync(self.data, self.output, '2025-08-13T12:00:00+07:00')
        self.assertEqual((self.output/'latest.json').read_bytes(), previous)
        self.assertEqual(load_snapshot(self.output)['as_of'], CUTOFF)

    def test_corrupt_snapshot_unknown_company_backward_clock_and_in_place_output_are_rejected(self):
        sync(self.data, self.output, CUTOFF)
        with self.assertRaises(ValueError):
            sync(self.data, self.output, '2025-01-01T00:00:00+07:00')
        with self.assertRaises(ValueError):
            sync(self.data, self.output, CUTOFF, ['C_OTHER'])
        with self.assertRaises(ValueError):
            sync(self.data, self.data/'graphs', CUTOFF)
        pointer = json.loads((self.output/'latest.json').read_text())
        (self.output/'snapshots'/pointer['snapshot']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            load_snapshot(self.output)

    def test_two_writers_cannot_publish_to_same_output(self):
        self.output.mkdir()
        (self.output/'.graph-sync.lock').write_text('another writer')
        with self.assertRaises(FileExistsError):
            sync(self.data, self.output, CUTOFF)
