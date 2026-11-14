"""Reading verified evidence is separate from asserting verification on import."""
import copy
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from sme_fraud.auth import AuthError, FileAuthorizer
from sme_fraud.feature_pipeline import run_job, read_artifact
from sme_fraud.import_files import canonical, ImportFailure
from sme_fraud.imports import validate_input
from sme_fraud.snapshot_features import build_feature_rows, build_from_snapshot
from sme_fraud.snapshots import SnapshotStore
from test_snapshot_features import bundle, feature, AS_OF
from test_snapshots import commit_fields
from test_validation_backend import policy_for


class SnapshotVerificationAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.store = SnapshotStore(self.base/'snapshots.sqlite3')
        self.data = bundle('C001')
        doc = next(d for d in self.data['supporting_documents'] if d['record_id'] == 'DOC_KNOWN')
        doc.update(source_kind='original', verification_status='verified',
                   verification=dict(verified_by='synthetic-writer', verified_at=doc['observed_at'],
                                     basis='Synthetic authorization fixture; not a real original document'))
        doc['source']['is_simulated'] = False
        self.writer = AccessScope('demo', frozenset({'C001'}), 'synthetic-writer', frozenset({'data.import', 'evidence.verify'}))
        self.token = secrets.token_urlsafe(32)
        self.policy = policy_for(self.token)
        self.policy_file = self.base/'policy.json'; self.policy_file.write_bytes(canonical(self.policy))
        self.auth = FileAuthorizer(self.policy_file)
        self.header = 'Bearer '+self.token
        self.reader = self.auth.authorize(self.header, 'C001')
        draft = self.store.upload(self.writer, canonical(self.data), 'verified.json', 'verified-upload')
        report = self.store.preview(self.writer, draft['import_id'], 1)
        self.assertNotEqual(report['status'], 'rejected')
        self.snapshot_id = self.store.commit(self.writer, draft['import_id'], commit_fields(report), 'verified-commit')['snapshot']['snapshot_id']

    def test_reader_job_uses_committed_verification_without_mutating_data_or_permissions(self):
        before = self.store.get_snapshot(self.reader, self.snapshot_id, data=True)
        saved = run_job(self.store, self.auth, self.header, 'C001', self.snapshot_id, AS_OF, self.base/'features')
        artifact = read_artifact(saved['directory'])
        self.assertEqual(feature(artifact, 'C001', 'T001')['verified_original_document_count'], 1)
        self.assertEqual(before, self.store.get_snapshot(self.reader, self.snapshot_id, data=True))
        self.assertEqual(self.auth.authorize(self.header, 'C001'), self.reader)
        self.assertNotIn('evidence.verify', self.reader.permissions)

    def test_raw_builder_still_requires_permission_to_assert_verification(self):
        self.assertIn('VERIFICATION_PERMISSION', {e['code'] for e in validate_input(self.data, self.reader)['errors']})
        with self.assertRaises(ImportFailure) as error:
            build_feature_rows(self.data, self.reader, AS_OF)
        self.assertEqual(error.exception.code, 'FEATURE_INPUT_INVALID')

    def test_reader_cannot_commit_a_new_verified_import(self):
        draft = self.store.upload(self.reader, canonical(self.data), 'new-verified.json', 'reader-upload')
        report = self.store.preview(self.reader, draft['import_id'], 1)
        self.assertEqual(report['status'], 'rejected')
        self.assertIn('VERIFICATION_PERMISSION', {e['code'] for e in report['errors']})
        with self.assertRaises(ImportFailure) as error:
            self.store.commit(self.reader, draft['import_id'], commit_fields(report), 'reader-commit')
        self.assertEqual(error.exception.code, 'VALIDATION_REJECTED')

    def test_committed_read_does_not_suppress_other_validation_errors(self):
        # Force additional diagnostics at the validation boundary. The permission
        # exception must not turn any other error into an accepted snapshot.
        original = validate_input
        for code in ('VERIFICATION_MISSING', 'VERIFICATION_TIME', 'REFERENCE_MISSING', 'ACCESS_DENIED'):
            def invalid(data, scope, extra=code):
                report = copy.deepcopy(original(data, scope))
                report['errors'].append(dict(code=extra))
                report['status'] = 'rejected'
                return report
            with self.subTest(code=code), patch('sme_fraud.snapshot_features.validate_input', side_effect=invalid):
                with self.assertRaises(ImportFailure) as error:
                    build_from_snapshot(self.store, self.reader, self.snapshot_id, AS_OF)
                self.assertEqual(error.exception.code, 'FEATURE_INPUT_INVALID')

    def test_verified_snapshot_still_rejects_wrong_company_or_missing_read_permission(self):
        for authority in (
            AccessScope('demo', frozenset({'C002'}), 'foreign-reader', frozenset({'data.import'})),
            AccessScope('demo', frozenset({'C001'}), 'no-read-permission', frozenset()),
        ):
            with self.subTest(scope=authority), self.assertRaises(ImportFailure) as error:
                build_from_snapshot(self.store, authority, self.snapshot_id, AS_OF)
            self.assertIn(error.exception.status, (403, 404))

    def test_reader_revocation_after_build_still_prevents_export(self):
        original = build_from_snapshot
        def revoke(*args, **kwargs):
            result = original(*args, **kwargs)
            self.policy['principals'][0]['status'] = 'revoked'
            self.policy_file.write_bytes(canonical(self.policy))
            return result
        with patch('sme_fraud.feature_pipeline.build_from_snapshot', side_effect=revoke), self.assertRaises(AuthError):
            run_job(self.store, self.auth, self.header, 'C001', self.snapshot_id, AS_OF, self.base/'out')
        self.assertFalse((self.base/'out').exists())


if __name__ == '__main__':
    unittest.main()
