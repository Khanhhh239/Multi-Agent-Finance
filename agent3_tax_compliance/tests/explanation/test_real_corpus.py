"""Primary-PDF transcription and retrieval contracts; not a legal accuracy benchmark."""
import hashlib
import json
import unittest
import unicodedata
from datetime import date
from pathlib import Path
from pydantic import ValidationError
from src.explanation_v2.contracts import Corpus,Chunk,Policy
from src.explanation_v2.service import load_config
from src.explanation_v2.retrieval import retrieve
from src.explanation_v2.cli import inspect
from src.legal_registry.registry import load_registry
from src.orchestration.contracts import LegalCitation

APP=Path(__file__).resolve().parents[2]
ROOT=APP.parent
EVIDENCE=ROOT/'docs/agent3/plans/evidence/plan12/legal_corpus_20261016'


class RealCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus=Corpus.model_validate_json((APP/'configs/explanation/corpus_20261016_v1.json').read_text(encoding='utf-8'))
        cls.registry=load_registry()

    def citation(self,docid,locator,**updates):
        doc=next(d for d in self.registry.documents if d.document_id==docid)
        return LegalCitation(document_id=docid,locator=locator,official_url=doc.official_url,
                             sha256=doc.sha256,locator_reviewed=True).model_copy(update=updates)

    def search(self,docid,locator,on=date(2026,7,1),query='hóa đơn thuế',top_k=1):
        return retrieve(self.corpus,self.registry,(self.citation(docid,locator),),query,on,top_k)

    def test_default_load_uses_new_corpus_and_keeps_old_frozen_file(self):
        policy,corpus=load_config()
        self.assertEqual(corpus,self.corpus);self.assertFalse(policy.enabled)
        self.assertEqual(json.loads((APP/'configs/explanation/corpus_v1.json').read_text(encoding='utf-8'))['chunks'],[])

    def test_real_source_manifest_all_pdfs_pinned(self):
        manifest=json.loads((EVIDENCE/'source_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['documents']),11)
        for source in manifest['documents']:
            self.assertEqual(source['status'],'MATCHED_PINNED_PRIMARY_PDF')
            self.assertEqual(source['sha256'],source['expected_sha256'])
        self.assertFalse(any(p['independent_legal_approval'] for p in manifest['provenance']))

    def test_runtime_registry_coverage_hash_and_unicode(self):
        self.assertEqual(len(self.corpus.chunks),11)
        self.assertTrue(inspect(Policy(),self.corpus,self.registry)['valid'])
        for chunk in self.corpus.chunks:
            self.assertEqual(hashlib.sha256(chunk.text.encode()).hexdigest(),chunk.text_sha256)
            self.assertEqual(unicodedata.normalize('NFC',chunk.text),chunk.text)
            self.assertTrue(chunk.source_pages);self.assertTrue(chunk.required_context)
            self.assertNotIn('PENDING',chunk.locator)

    def test_old_deferred_clause_exclusive_boundary(self):
        before=self.search('ND181_2025','Article26.pdf32-34',date(2026,6,19))
        after=self.search('ND181_2025','Article26.pdf32-34',date(2026,6,20))
        self.assertIn('ND181-A26-2-g-original',{c.chunk_id for c in before})
        self.assertNotIn('ND181-A26-2-g-original',{c.chunk_id for c in after})
        self.assertEqual(len(before),4);self.assertEqual(len(after),3)

    def test_new_deferred_clause_not_before_effective_date(self):
        self.assertFalse(self.search('ND144_2026','Article4.pdf3',date(2026,6,19)))
        found=self.search('ND144_2026','Article4.pdf3',date(2026,6,20))
        self.assertEqual(len(found),1)
        self.assertIn('Trường hợp sau khi điều chỉnh',found[0].text)
        self.assertIn('vào kỳ tính thuế có chứng từ',found[0].text)

    def test_non_cash_threshold_does_not_drop_exceptions_at_top1(self):
        found=self.search('ND181_2025','Article26.pdf32-34',date(2025,8,1),query='05 triệu đồng',top_k=1)
        text=' '.join(c.text for c in found)
        for phrase in ('đã bao gồm thuế giá trị gia tăng','trừ các chứng từ bên mua nộp tiền mặt',
                       'mua nhiều lần trong cùng một ngày','người lao động','ủy quyền qua bên thứ ba'):
            self.assertIn(phrase,text)

    def test_content_quote_includes_exceptions_and_actual_pdf_pages(self):
        found=self.search('ND254_2026','Article10.pdf21',query='mã số thuế người mua')
        self.assertEqual(found[0].source_pages,(21,22,23))
        self.assertIn('không nhất thiết có đầy đủ các nội dung',found[0].text)
        self.assertIn('(nếu người mua yêu cầu)',found[0].text)
        self.assertIn('Phụ lục',found[0].scope_note)

    def test_effective_and_supersession_quote_not_wrong_document(self):
        found=self.search('ND254_2026','Article43.pdf46')
        self.assertIn('Điều 1 Nghị định số 41/2022',found[0].text)
        self.assertIn('Nghị định số 70/2025',found[0].text)
        self.assertFalse(self.search('ND254_2026','Article43.pdf46',date(2026,6,30)))

    def test_unreviewed_and_wrong_sha_locator_never_retrieved(self):
        for updates in ({'sha256':'0'*64},{'locator_reviewed':False},{'locator':'Article99'}):
            cite=self.citation('ND254_2026','Article10.pdf21').model_copy(update=updates)
            self.assertFalse(retrieve(self.corpus,self.registry,(cite,),'',date(2026,7,1)))

    def test_future_date_after_corpus_review_cutoff_abstains(self):
        self.assertTrue(self.search('ND254_2026','Article10.pdf21',date(2026,10,16)))
        self.assertFalse(self.search('ND254_2026','Article10.pdf21',date(2026,10,17)))

    def test_references_cannot_be_loaded_as_active_corpus(self):
        packet=json.loads((APP/'configs/explanation/legal_sources/reference_packet_20261016.json').read_text(encoding='utf-8'))
        with self.assertRaises(ValidationError):Corpus.model_validate(packet)
        self.assertEqual(len(packet['chunks']),6)
        self.assertNotIn('ND174_2025',{c.document_id for c in self.corpus.chunks})
        self.assertFalse(self.search('ND123_2020','Article10.PENDING_REVIEW',date(2024,1,1)))

    def test_scope_and_coverage_report_remains_honest(self):
        report=json.loads((EVIDENCE/'rule_coverage.json').read_text(encoding='utf-8'))
        self.assertEqual(sum(v['all_selected_locators_have_excerpts'] for v in report['versions']),2)
        self.assertTrue(all(v['publication']=='DRAFT' for v in report['versions']))
        self.assertTrue(all(v['current_date_outside_version'] for v in report['versions']))

    def test_invalid_provision_dates_pages_and_text_tampering_rejected(self):
        data=self.corpus.chunks[0].model_dump(mode='json')
        for change in ({'provision_to':'2026-06-01'},{'source_pages':[0]},{'source_pages':[True]},
                       {'source_pages':[21,21]},{'text':data['text']+'changed'}):
            with self.subTest(change=change):
                with self.assertRaises(ValidationError):Chunk.model_validate(dict(data,**change))


if __name__=='__main__':unittest.main()
