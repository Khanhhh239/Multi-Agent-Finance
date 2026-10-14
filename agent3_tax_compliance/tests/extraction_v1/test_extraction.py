import json,unittest,tempfile,hashlib,sqlite3
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from fastapi.testclient import TestClient
from src.adapters.ocr.protocol import NormalizedDocumentExtraction,NormalizedPageExtraction,ExtractionBlock,BlockOrigin,OCRConfig
from src.ingestion.models import Geometry,AuthGrant
from src.domain.evidence import Evidence
from src.domain.taxpayer import TaxpayerMaster,BranchRelation,AccessContext
from src.domain.cfr import CanonicalFinancialRecord
from src.extraction.contracts import ExtractionProfile,ExtractionArtifact,IdentityMap,IdentityEntry,ItemLineage,DerivationManifest,DerivationNode
from src.extraction.service import extract,canonicalize
from src.extraction.repository import ExtractionRepository
from src.extraction.evidence import resolve
from src.canonicalization.normalize import money_values,date_values,currency_values,vat_values,exact_sum,exact_product
from src.canonicalization.identity import allocate
from src.canonicalization.derive import rederive,affected_nodes,sha
from src.config import Settings
from src.app import create_app

STAMP=dict(config_version='fixture-v1',creator='fixture',stage='test',created_at=datetime(2026,10,12,tzinfo=timezone.utc))
CTX=AccessContext(actor_id='test',tenant_id='tenant-a',taxpayer_ids=frozenset({'payer-a'}),permissions=frozenset({'ADMIN'}))
MASTER=TaxpayerMaster(**STAMP,tenant_id='tenant-a',taxpayer_id='payer-a',revision=1,tax_code='1234567890',effective_from=date(2026,1,1),provenance_reference='synthetic')

def document(texts=None,second=None,failed=False):
    texts=texts or ['Tên người bán: CÔNG TY A','MST người bán: 1234567890','Tên người mua: CÔNG TY A',
        'MST người mua: 9876543210','Số hóa đơn: A001','Ngày lập: 03/04/2026','Đơn vị tiền tệ: VND',
        'Mặt hàng 1','Tên hàng: sản phẩm','Tiền trước thuế: 100','Thuế suất: 8%','Số dòng: 1',
        'Cộng trước thuế: 100','Tiền thuế: 8','Tổng thanh toán: 108']
    pages=[]
    for p,lines in enumerate((texts,) if second is None else (texts,second)):
        geometry=Geometry(transform_id='transform-'+str(p),original_space='IMAGE_RAW_PIXELS',original_to_render=(1,0,0,1,0,0),render_to_original=(1,0,0,1,0,0))
        blocks=[]
        for n,text in enumerate(lines):
            identifier=f'block-{p}-{n}'
            blocks.append(ExtractionBlock(block_id=identifier,text_raw=text,geometry_status='AVAILABLE',reading_order=n,
                evidence=Evidence(source_id='source-a',document_id='document-a',page_index=p,bbox=(.05,.02+n*.04,.9,.05+n*.04),
                    block_id=identifier,transform_id=geometry.transform_id),origins=(BlockOrigin(method='OCR',source_block_id=identifier,
                        raw_score=.99,score_kind='DETECTION',score_semantics='ENGINE_HEURISTIC_NOT_CALIBRATED'),)))
        pages.append(NormalizedPageExtraction(**STAMP,page_id='page-'+str(p),page_index=p,image_hash='a'*64,geometry=geometry,
            route='OCR',status='COMPLETE',blocks=tuple(blocks)))
    if failed:
        from src.adapters.ocr.protocol import OCRIssue
        pages[-1]=pages[-1].model_copy(update={'status':'FAILED','blocks':(),'issue':OCRIssue(code='OCR_FAILED',message='fixture missing page')})
    return NormalizedDocumentExtraction(**STAMP,tenant_id='tenant-a',taxpayer_id='payer-a',taxpayer_master_revision=1,
        ingestion_id='ingestion-a',source_id='source-a',document_id='document-a',input_sha256='b'*64,
        document_artifact_sha256='c'*64,runtime_sha256='d'*64,ocr_config=OCRConfig(),
        status='COMPLETE' if not failed else 'PARTIAL' if len(pages)>1 else 'FAILED',pages=tuple(pages))

def run(doc=None,profile=None): return extract(doc or document(),'PDF',MASTER,profile)

class ExtractionTests(unittest.TestCase):
    def test_money_locales_signs_and_ambiguity(self):
        for raw,expected in [('1.234,56','1234.56'),('1,234.56','1234.56'),('(1.234,56)','-1234.56'),('-12 345,67','-12345.67')]:
            self.assertEqual(money_values(raw),(expected,))
        self.assertEqual(set(money_values('1.234')),{'1234','1.234'})
        self.assertEqual(money_values('1.234','VI'),('1234',))
        for raw in ('NaN','1e9','1,23,4','--3'): self.assertFalse(money_values(raw))

    def test_exact_arithmetic_beyond_context_precision(self):
        a=Decimal('123456789012345678901234567890.12345678')
        self.assertEqual(str(exact_sum((a,Decimal('.00000001')))),'123456789012345678901234567890.12345679')
        self.assertEqual(exact_product(a,Decimal('1')),a)

    def test_dates_and_currency_no_hidden_defaults(self):
        self.assertEqual(set(date_values('03/04/2026','AUTO')),{'2026-04-03','2026-03-04'})
        self.assertFalse(date_values('03/04'));self.assertFalse(date_values('31/02/2026'))
        self.assertEqual(len(currency_values('$')),4)
        with self.assertRaises(ValidationError): ExtractionProfile(default_currency='VND')
        a=run(document(['Số hóa đơn: A']));self.assertEqual(a.record.currency.status,'MISSING')
        a=run(document(['Số hóa đơn: A']),ExtractionProfile(default_currency='VND',currency_policy_reference='profile-approved-v1'))
        self.assertEqual(a.record.currency.source,'profile');self.assertEqual(a.record.currency.confidence_basis,'DETERMINISTIC')

    def test_parties_not_assigned_by_position_or_similar_name(self):
        a=run();self.assertEqual(a.record.parties.seller.name.value,a.record.parties.buyer.name.value)
        self.assertEqual(a.record.parties.seller.tax_id.value,'1234567890')
        self.assertEqual(a.record.parties.buyer.tax_id.value,'9876543210')
        self.assertEqual(a.record.derived.invoice_direction.value,'OUTPUT')
        self.assertEqual(a.record.derived.counterparty.tax_id.value,'9876543210')
        b=run(document(['MST: 9876543210','MST: 1234567890']))
        self.assertEqual(b.record.parties.seller.tax_id.status,'MISSING')
        self.assertEqual(b.record.derived.invoice_direction.status,'AMBIGUOUS')

    def test_explicit_party_sections(self):
        a=run(document(['Người mua','MST: 9876543210','Người bán','MST: 1234567890','Ngày lập: 01/01/2026']))
        self.assertEqual(a.record.parties.buyer.tax_id.value,'9876543210')
        self.assertEqual(a.record.parties.seller.tax_id.value,'1234567890')

    def test_conflicts_and_ocr_scores_never_become_field_confidence(self):
        a=run(document(['MST người bán: 1234567890','MST người bán: 9876543210','Ngày lập: 03/04/2026']),ExtractionProfile(date_order='AUTO'))
        self.assertEqual(a.record.parties.seller.tax_id.status,'AMBIGUOUS')
        self.assertEqual(len(a.record.parties.seller.tax_id.candidates),2)
        self.assertEqual(a.record.invoice.issue_date.status,'AMBIGUOUS')
        self.assertTrue(all(c.raw_scores[0].kind=='DETECTION' for c in a.candidates))
        self.assertIsNone(a.record.parties.seller.tax_id.confidence)
        self.assertTrue(all(c.selection_reason=='COMPETING_VALUE' for c in a.candidates))

    def test_vat_kct_kkknt_zero_and_group_partition(self):
        lines=['Số dòng: 3']
        for n,vat in enumerate(('KCT','KKKNT','0%'),1): lines.extend([f'Mặt hàng {n}',f'Tên hàng: Item {n}','Tiền trước thuế: 100',f'Thuế suất: {vat}'])
        a=run(document(lines));self.assertEqual(len(a.record.items),3)
        self.assertEqual([i.vat_treatment.value for i in a.record.items],['KCT','KKKNT','TAXABLE_RATE'])
        self.assertEqual([i.vat_rate.status for i in a.record.items],['NOT_APPLICABLE','NOT_APPLICABLE','PRESENT'])
        self.assertEqual(a.record.items[-1].vat_rate.value,Decimal('0'))
        self.assertEqual(len(a.vat_groups),3);self.assertTrue(all(g.category.status=='MISSING' for g in a.vat_groups))
        self.assertEqual(a.record.derived.totals.net.value,Decimal('300'))

    def test_no_rounding_and_total_mismatch_preserves_both(self):
        a=run(document(['Số dòng: 1','Mặt hàng 1','Tên hàng: A','Tiền trước thuế: 0,03','Thuế suất: 8%','Tổng thanh toán: 100']))
        self.assertEqual(a.record.derived.totals.vat.value,Decimal('.0024'))
        self.assertEqual(a.record.totals.gross.value,Decimal('100'))
        self.assertIn('TOTAL_MISMATCH',[i.code for i in a.issues])

    def test_missing_pages_empty_items_and_mismatched_row_count(self):
        for doc,expected in [(document(['Số hóa đơn: A']),'UNKNOWN'),(document(['Số dòng: 1']), 'INCOMPLETE'),
                             (document(second=['Mặt hàng 2'],failed=True),'INCOMPLETE')]:
            a=run(doc);self.assertEqual(a.record.item_discovery_status,expected)
            self.assertEqual(a.record.derived.totals.gross.status,'MISSING')

    def test_two_invoices_never_merged(self):
        a=run(document(['Số hóa đơn: A','Tổng thanh toán: 10'],second=['Số hóa đơn: B','Tổng thanh toán: 20']))
        self.assertEqual(a.segmentation.status,'REVIEW_SPLIT');self.assertIsNone(a.record)

    def test_multipage_rows_preserved(self):
        a=run(document(['Số hóa đơn: A','Số dòng: 2','Mặt hàng 1','Tên hàng: A','Tiền trước thuế: 10','Thuế suất: 8%'],
            second=['Số hóa đơn: A','Mặt hàng 2','Tên hàng: B','Tiền trước thuế: 20','Thuế suất: 8%']))
        self.assertEqual(len(a.record.items),2);self.assertEqual(a.record.item_discovery_status,'COMPLETE')
        self.assertEqual(a.record.derived.totals.gross.value,Decimal('32.4'))

    def test_identity_reorder_correction_explicit_reextraction(self):
        old=allocate(('anchor-a','anchor-b'));mapping={e.anchor_id:e.item_id for e in old.entries}
        new=allocate(('anchor-b','anchor-a'),old,mapping)
        self.assertEqual(new.entries[0].item_id,old.entries[1].item_id)
        with self.assertRaises(ValueError): allocate(('anchor-a',),old)
        with self.assertRaises(ValueError): allocate(('anchor-a',),old,{'anchor-a':'other-id'})
        a=run();record=a.record.model_copy(update={'items':tuple(i.model_copy(update={'line_number':99}) for i in a.record.items)})
        corrected,_,_=rederive(record,MASTER,a.profile)
        self.assertEqual(corrected.items[0].item_id,a.record.items[0].item_id)

    def test_split_and_merge_require_complete_lineage(self):
        old=allocate(('a',));item=old.entries[0].item_id
        change=ItemLineage(operation='SPLIT',previous_ids=(item,),new_ids=('new-a','new-b'),reason='review split')
        new=allocate(('b','c'),old,{'b':'new-a','c':'new-b'},(change,))
        merge=ItemLineage(operation='MERGE',previous_ids=('new-a','new-b'),new_ids=('merged',),reason='review merge')
        end=allocate(('d',),new,{'d':'merged'},(merge,));self.assertEqual(len(end.lineage),2)
        with self.assertRaises(ValueError): allocate(('d',),new,{'d':'merged'},(change,))

    def test_direction_correction_invalidates_and_rederives(self):
        a=run();r=a.record
        changed=r.parties.seller.tax_id.model_copy(update={'value':'1111111111'})
        r=r.model_copy(update={'parties':r.parties.model_copy(update={'seller':r.parties.seller.model_copy(update={'tax_id':changed})})})
        updated,manifest,_=rederive(r,MASTER,a.profile)
        self.assertIsNone(updated.derived.invoice_direction.value);self.assertIsNone(updated.derived.counterparty)
        self.assertIn('derived.counterparty',affected_nodes(a.derivation,('parties.seller.tax_id',)))
        self.assertNotEqual(manifest.observed_sha256,a.derivation.observed_sha256)
        self.assertEqual(updated.totals,r.totals)

    def test_branch_relation_and_effective_dates(self):
        a=run(document(['MST người bán: 1234567890-001','MST người mua: 9876543210','Ngày lập: 03/04/2026']))
        self.assertIsNone(a.record.derived.invoice_direction.value)
        relation=BranchRelation(tenant_id='tenant-a',parent_tax_code='1234567890',branch_tax_code='1234567890001',effective_from=date(2026,1,1),evidence_reference='reviewed')
        r,_,_=rederive(a.record,MASTER,a.profile,(relation,));self.assertEqual(r.derived.invoice_direction.value,'OUTPUT')
        expired=relation.model_copy(update={'effective_to':date(2026,4,1)})
        r,_,_=rederive(a.record,MASTER,a.profile,(expired,));self.assertIsNone(r.derived.invoice_direction.value)
        with self.assertRaises(ValueError): rederive(a.record,MASTER,a.profile,(relation.model_copy(update={'tenant_id':'other'}),))

    def test_pure_replay_schema_and_dag(self):
        doc=document();a=run(doc)
        b=canonicalize(doc,'PDF',MASTER,a.profile,a.identity_map,record_id=a.record.record_id,artifact_id=a.artifact_id,
            created_at=a.created_at,extractor_sha256=a.extractor_sha256)
        self.assertEqual(a.model_dump_json(),b.model_dump_json())
        self.assertEqual(ExtractionArtifact.model_validate_json(a.model_dump_json()),a)
        with self.assertRaises(ValidationError):
            DerivationManifest(observed_sha256='a'*64,master_sha256='b'*64,relations_sha256='c'*64,profile_version='v1',
                nodes=(DerivationNode(path='a',inputs=('b',)),DerivationNode(path='b',inputs=('a',))))

    def test_wrong_master_rejected(self):
        with self.assertRaises(ValueError): extract(document(),'PDF',MASTER.model_copy(update={'revision':2}))

    def test_hyphenated_branch_master_preserves_13_digits(self):
        master=MASTER.model_copy(update={'tax_code':'1234567890-001'})
        a=extract(document(['MST người bán: 1234567890001','MST người mua: 9876543210','Ngày lập: 03/04/2026']),'PDF',master)
        self.assertEqual(a.record.derived.invoice_direction.value,'OUTPUT')
        self.assertEqual(a.record.parties.seller.tax_id.value,'1234567890001')

    def test_invalid_money_never_written_as_present(self):
        a=run(document(['Tổng thanh toán: 1e9','Ngày lập: 31/02/2026']))
        self.assertEqual(a.record.totals.gross.status,'MISSING');self.assertEqual(a.record.invoice.issue_date.status,'MISSING')
        self.assertIn('UNPARSEABLE_FIELD',[i.code for i in a.issues])

    def test_geometry_column_table_and_continuation(self):
        doc=document(['Số dòng: 1']);p=doc.pages[0];blocks=list(p.blocks)
        cells=[('Tên hàng',.05,.15,.3),('Thành tiền',.5,.15,.65),('Thuế suất',.75,.15,.9),
               ('Dịch vụ',.05,.25,.3),('100',.5,.25,.65),('8%',.75,.25,.9),('bảo trì',.05,.30,.3)]
        for n,(text,x,y,right) in enumerate(cells,1):
            b=p.blocks[0];ev=b.evidence.model_copy(update={'bbox':(x,y,right,y+.025),'block_id':'cell-'+str(n)})
            blocks.append(b.model_copy(update={'block_id':ev.block_id,'text_raw':text,'reading_order':n,'evidence':ev}))
        doc=doc.model_copy(update={'pages':(p.model_copy(update={'blocks':tuple(blocks)}),)})
        a=run(doc);self.assertEqual(len(a.record.items),1)
        self.assertEqual(a.record.items[0].description.value,'Dịch vụ bảo trì')
        self.assertEqual(a.record.items[0].net.value,Decimal('100'))

    def test_ocr_merged_labels_and_slash_spacing(self):
        a=run(document(['MST người bán 1234567890','Số hóa đơn ABC123','Số dòng 1',
            'Mặt hàng 1 Sản phẩm A','Tiền trước thuế 100','Thuế suất/ nhóm 8%']))
        self.assertEqual(a.record.invoice.number.value,'ABC123')
        self.assertEqual(a.record.parties.seller.tax_id.value,'1234567890')
        self.assertEqual(a.record.items[0].description.value,'Sản phẩm A')
        self.assertEqual(a.record.items[0].vat_rate.value,Decimal('.08'))

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        from src.ingestion.service import IngestionService
        from src.ingestion.upload import StagedUpload
        from src.adapters.ocr.bridge import OCRBridge,config_key
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
        self.token='extraction-test-only'
        grant=AuthGrant(token_sha256=hashlib.sha256(self.token.encode()).hexdigest(),actor_id=CTX.actor_id,tenant_id=CTX.tenant_id,
            taxpayer_ids=CTX.taxpayer_ids,permissions=CTX.permissions)
        self.settings=Settings(database_path=root/'capture.sqlite3',staging_directory=root/'staging',auth_grants=(grant,))
        self.repo=ExtractionRepository(self.settings);self.repo.base.initialize();self.repo.base.add_taxpayer(CTX,MASTER)
        service=IngestionService(self.settings)
        raw=(Path(__file__).resolve().parents[1]/'fixtures/ocr/functional_set_v1/syn-00-pdf_text.pdf').read_bytes()
        with StagedUpload(self.settings) as staged:
            staged.write(raw);view=service.accept_staged(CTX,'payer-a',1,'fixture-key',staged,'application/pdf','invoice.pdf')
        self.identifier=view.ingestion_id
        self.assertEqual(service.work_one(CTX,'payer-a',self.identifier).status,'SUCCEEDED')
        class NativeOnly:
            def inventory(self): return {'runtime_sha256':'a'*64}
            def run_batch(self,*args): raise AssertionError('native integration must not call an OCR model')
        config=OCRConfig();bridge=OCRBridge(self.settings,config,NativeOnly())
        self.job=bridge.work_one(CTX,'payer-a',self.identifier);self.key=config_key(config,'a'*64)

    def test_atomic_idempotent_roundtrip(self):
        a=self.repo.work(CTX,'payer-a',self.identifier,self.key)
        b=self.repo.work(CTX,'payer-a',self.identifier,self.key)
        self.assertEqual(a,b);self.assertEqual(self.repo.get(CTX,'payer-a',a.artifact_id),a)
        self.assertEqual(self.repo.base.record(CTX,'payer-a',a.record.record_id),a.record)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],7)

    def test_audit_failure_rolls_back_record_and_artifact(self):
        with patch.object(self.repo.ingestion,'_event',side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError): self.repo.work(CTX,'payer-a',self.identifier,self.key)
        with self.repo.ingestion.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM cfr_extractions').fetchone()[0],0)

    def test_scoped_authenticated_api_and_evidence(self):
        a=self.repo.work(CTX,'payer-a',self.identifier,self.key)
        client=TestClient(create_app(self.settings));url='/v1/cfr-extractions/'+a.artifact_id
        self.assertEqual(client.get(url,params={'taxpayer_id':'payer-a'}).status_code,401)
        headers={'Authorization':'Bearer '+self.token}
        self.assertEqual(client.get(url,params={'taxpayer_id':'payer-other'},headers=headers).status_code,403)
        self.assertEqual(client.get(url,params={'taxpayer_id':'payer-a'},headers=headers).status_code,200)
        candidate=next(c for c in a.candidates if c.semantic_field=='totals.gross')
        response=client.get(url+'/evidence/'+candidate.candidate_id,params={'taxpayer_id':'payer-a'},headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        evidence=response.json();self.assertTrue(evidence['geometry_available'])
        self.assertTrue(all(r['span'] and r['original_bbox'][2]>r['original_bbox'][0] for r in evidence['regions']))
        self.assertEqual(client.get(url+'/evidence/not-found',params={'taxpayer_id':'payer-a'},headers=headers).status_code,404)

    def test_evidence_rejects_wrong_document_and_hash(self):
        a=self.repo.work(CTX,'payer-a',self.identifier,self.key);norm=self.job['result']
        doc=self.repo.ingestion.document(CTX,'payer-a',self.identifier)
        cid=a.candidates[0].candidate_id
        with self.assertRaises(ValueError): resolve(a,cid,norm.model_copy(update={'runtime_sha256':'f'*64}),doc)
        with self.assertRaises(ValueError): resolve(a,cid,norm,doc.model_copy(update={'tenant_id':'other'}))
        result=resolve(a,cid,norm,doc)
        e=a.candidates[0].evidence_refs[0];region=result['regions'][0];p=doc.pages[e.page_index]
        self.assertAlmostEqual(region['render_bbox'][0],e.bbox[0]*p.render_width)

    def test_tenant_denied_and_append_only(self):
        a=self.repo.work(CTX,'payer-a',self.identifier,self.key)
        other=CTX.model_copy(update={'tenant_id':'tenant-b'})
        with self.assertRaises(KeyError): self.repo.get(other,'payer-a',a.artifact_id)
        with self.repo.ingestion.db() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE cfr_extractions SET sha256='tamper'")
        with self.assertRaises(ValueError): self.repo.work(CTX,'payer-a',self.identifier,'f'*64)

    def test_concurrent_calls_share_allocated_item_ids(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.repo.work(CTX,'payer-a',self.identifier,self.key),range(2)))
        self.assertEqual(results[0].identity_map,results[1].identity_map)
        self.assertEqual(results[0].artifact_id,results[1].artifact_id)

if __name__=='__main__': unittest.main()
