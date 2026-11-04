import hashlib
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_xml_invoice as fx  # noqa: E402
from src.config import Settings  # noqa: E402
from src.domain.taxpayer import AccessContext, TaxpayerMaster  # noqa: E402
from src.ingestion.models import AuthGrant, IngestionError  # noqa: E402
from src.ingestion.service import IngestionService  # noqa: E402
from src.ingestion.upload import StagedUpload  # noqa: E402
from src.jobs.service import CaptureJobs  # noqa: E402
from src.quality.repository import replay  # noqa: E402
from src.review.repository import ReviewRepository  # noqa: E402

CTX = AccessContext(actor_id='test', tenant_id='tenant-a', taxpayer_ids=frozenset({'payer-a'}), permissions=frozenset({'ADMIN'}))
STAMP = dict(config_version='fixture-v1', creator='fixture', stage='test', created_at=datetime(2026, 10, 12, tzinfo=timezone.utc))
MASTER = TaxpayerMaster(**STAMP, tenant_id='tenant-a', taxpayer_id='payer-a', revision=1, tax_code=fx.SELLER,
                        effective_from=date(2026, 1, 1), provenance_reference='synthetic')


class XmlPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        grant = AuthGrant(token_sha256=hashlib.sha256(b'xml-test-only').hexdigest(), actor_id=CTX.actor_id, tenant_id=CTX.tenant_id,
                          taxpayer_ids=CTX.taxpayer_ids, permissions=CTX.permissions)
        self.settings = Settings(database_path=root / 'capture.sqlite3', staging_directory=root / 'staging', auth_grants=(grant,))
        self.jobs = CaptureJobs(self.settings)
        self.jobs.base.initialize()
        self.jobs.base.add_taxpayer(CTX, MASTER)
        self.service = IngestionService(self.settings)

    def upload(self, raw, key='xml-key', mime='application/xml', name='inv.xml'):
        with StagedUpload(self.settings) as staged:
            staged.write(raw)
            return self.service.accept_staged(CTX, 'payer-a', 1, key, staged, mime, name)

    def run_job(self, raw, key='xml-key'):
        view = self.upload(raw, key)
        job = self.jobs.enqueue(CTX, 'payer-a', view.ingestion_id)
        return view, self.jobs.work_one(CTX, 'payer-a', job['job_id'])

    def test_signed_invoice_flows_to_review_without_ocr(self):
        view, job = self.run_job(fx.signed_invoice())
        self.assertEqual(job['state'], 'REVIEW', job)
        record = self.jobs.base.record(CTX, 'payer-a', job['record_id'])
        self.assertEqual(record.source_format.value, 'INVOICE_XML')
        self.assertEqual(str(record.totals.gross.value), '2200000')
        self.assertEqual(record.derived.invoice_direction.value, 'OUTPUT')
        self.assertEqual(record.totals.gross.provenance.derived_from, ('HDon/DLHDon/NDHDon/TToan/TgTTTBSo',))
        q = self.jobs.quality.get(CTX, 'payer-a', job['assessment_id'])
        gross = next(f for f in q.fields if f.field_path == 'totals.gross')
        self.assertEqual(gross.reliability, 'DETERMINISTIC_VERIFIED')
        self.assertEqual(gross.validation, 'VALID')
        self.assertFalse([i for i in q.issues if i.severity == 'ERROR'], [(i.code, i.message) for i in q.issues if i.severity == 'ERROR'])
        self.assertEqual(replay(self.jobs.quality.inputs(CTX, 'payer-a', q.assessment_id), q), q)
        self.assertEqual(self.jobs.view(CTX, 'payer-a', record.record_id)['page_count'], 0)
        with self.jobs.ingestion.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ocr_jobs').fetchone()[0], 0)

    def test_tampered_invoice_is_blocked_with_errors_and_no_verified_fidelity(self):
        raw = fx.signed_invoice().replace(b'<TgTTTBSo>2200000<', b'<TgTTTBSo>22000000<')
        _, job = self.run_job(raw, 'tamper')
        self.assertEqual(job['state'], 'REVIEW')
        q = self.jobs.quality.get(CTX, 'payer-a', job['assessment_id'])
        codes = {i.code for i in q.issues if i.severity == 'ERROR'}
        self.assertTrue({'XML_CHECK_WORDS', 'XML_CHECK_SIGNATURE_SELLER'} <= codes, codes)
        gross = next(f for f in q.fields if f.field_path == 'totals.gross')
        self.assertNotEqual(gross.reliability, 'DETERMINISTIC_VERIFIED')
        self.assertFalse(gross.eligible_within_policy)

    def test_unsigned_invoice_never_verified(self):
        _, job = self.run_job(fx.BODY.encode(), 'unsigned')
        q = self.jobs.quality.get(CTX, 'payer-a', job['assessment_id'])
        self.assertTrue(all(f.reliability != 'DETERMINISTIC_VERIFIED' for f in q.fields))
        self.assertIn('FIDELITY_UNVERIFIED', {i.code for i in q.issues})

    def test_malformed_xml_fails_closed(self):
        view = self.upload(b'<HDon><DLHDon><broken></HDon>', 'bad')
        done = self.service.work_one(CTX, 'payer-a', view.ingestion_id)
        self.assertEqual(done.status, 'FAILED')
        self.assertEqual(done.issue.code, 'CORRUPT_DOCUMENT')
        self.assertFalse(done.issue.retryable)

    def test_foreign_xml_and_wrong_mime_rejected_at_upload(self):
        with self.assertRaises(IngestionError):
            self.upload(b'<root><a/></root>', 'foreign')
        with self.assertRaises(IngestionError):
            self.upload(fx.BODY.encode(), 'mime', mime='application/pdf')

    def test_idempotent_extraction(self):
        view, job = self.run_job(fx.signed_invoice(), 'idem')
        a = self.jobs.extraction.work_xml(CTX, 'payer-a', view.ingestion_id)
        b = self.jobs.extraction.work_xml(CTX, 'payer-a', view.ingestion_id)
        self.assertEqual(a, b)
        self.assertEqual(a.record.record_id, job['record_id'])


    def test_rebuild_and_human_correction_on_structured_source(self):
        from src.review.contracts import Change, CorrectionCommand
        from src.review.correction_service import CorrectionService
        _, job = self.run_job(fx.signed_invoice(), 'rebuild')
        repo = CorrectionService(self.settings)
        record_id = job['record_id']
        self.assertTrue(repo.rebuild(CTX, 'payer-a', record_id)['verified'])
        task = repo.page(CTX, 'payer-a', 'tasks', record_id=record_id)['items'][0]
        command = CorrectionCommand(record_id=record_id, expected_revision=1, task_id=task['task_id'], reason='Compared against source',
                                    changes=(Change(field_path='parties.buyer.name', new_value='Công ty B (đã xác nhận)'),))
        result = repo.correct(CTX, 'payer-a', command, 'fix-1')
        self.assertEqual(repo.base.record(CTX, 'payer-a', record_id).revision, 2)
        q = repo.quality.get(CTX, 'payer-a', result['assessment_id'])
        self.assertEqual(replay(repo.quality.inputs(CTX, 'payer-a', q.assessment_id), q), q)
        self.assertTrue(repo.rebuild(CTX, 'payer-a', record_id)['verified'])
        untouched = next(f for f in q.fields if f.field_path == 'totals.gross')
        self.assertEqual(untouched.reliability, 'DETERMINISTIC_VERIFIED')


    def test_same_invoice_submitted_twice_is_flagged_as_duplicate_and_replays(self):
        from src.review.correction_service import CorrectionService
        raw = fx.signed_invoice()
        _, first = self.run_job(raw, 'dup-1')
        _, second = self.run_job(raw, 'dup-2')
        q1 = self.jobs.quality.get(CTX, 'payer-a', first['assessment_id'])
        q2 = self.jobs.quality.get(CTX, 'payer-a', second['assessment_id'])
        self.assertNotIn('XML_CHECK_DUPLICATE', {i.code for i in q1.issues})
        dup = [i for i in q2.issues if i.code == 'XML_CHECK_DUPLICATE']
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].severity, 'ERROR')
        self.assertIn(first['record_id'], dup[0].message)
        self.assertTrue(CorrectionService(self.settings).rebuild(CTX, 'payer-a', second['record_id'])['verified'])


    def test_view_groups_checks_and_never_reports_external_checks_as_ok(self):
        _, ok = self.run_job(fx.signed_invoice(), 'grp-1')
        groups = {g['group']: g for g in self.jobs.view(CTX, 'payer-a', ok['record_id'])['check_groups']}
        self.assertEqual({k: groups[k]['status'] for k in ('amounts', 'invoice', 'tax_ids', 'signature')},
                         {'amounts': 'OK', 'invoice': 'OK', 'tax_ids': 'OK', 'signature': 'OK'})
        self.assertEqual(groups['authority']['status'], 'UNAVAILABLE')
        _, bad = self.run_job(fx.signed_invoice().replace(b'<TgTTTBSo>2200000<', b'<TgTTTBSo>22000000<'), 'grp-2')
        groups = {g['group']: g for g in self.jobs.view(CTX, 'payer-a', bad['record_id'])['check_groups']}
        self.assertEqual(groups['amounts']['status'], 'FAIL')
        self.assertEqual(groups['signature']['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
