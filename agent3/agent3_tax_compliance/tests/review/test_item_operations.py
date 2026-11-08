import sys,unittest
from pathlib import Path
from pydantic import ValidationError
sys.path.insert(0,str(Path(__file__).parent))
import test_review as fixtures
from src.review.contracts import CorrectionCommand,ItemOperation,ReviewError,Change
from src.quality.repository import verified_events

class ItemOperationsTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReviewTests('test_idempotent_double_submit_and_key_conflict');self.f.setUp();self.addCleanup(self.f.doCleanups)
    def op(self,**kw):
        data=dict(operation='ADD',item_id='manual-new',page_index=0,bbox=(.1,.4,.9,.45),
                  values={'description':'Printed service','net':'9007199254740993.12','vat_treatment':'KCT'})
        data.update(kw);return ItemOperation(**data)
    def save(self,ops,**kw):
        f=self.f;r=f.repo.base.record(f.ctx,f.payer,f.record.record_id)
        task=f.repo.page(f.ctx,f.payer,'tasks',record_id=r.record_id,revision=r.revision)['items'][0]
        command=CorrectionCommand(record_id=r.record_id,expected_revision=r.revision,task_id=task['task_id'],reason='Compared printed row',item_operations=tuple(ops),**kw)
        return f.repo.correct(f.ctx,f.payer,command,'row-save-'+str(r.revision))
    def test_add_exact_decimal_proof_and_full_replay(self):
        f=self.f;result=self.save([self.op()]);r=f.repo.base.record(f.ctx,f.payer,f.record.record_id)
        self.assertEqual(str(r.items[-1].net.value),'9007199254740993.12');self.assertEqual(r.item_discovery_status,'INCOMPLETE')
        self.assertEqual(r.items[-1].description.provenance.evidence[0].page_index,0)
        self.assertIsNone(r.derived.totals.net.value)
        with f.repo.ingestion.db() as db:self.assertIn(result['event_id'],verified_events(db,r))
        self.assertTrue(f.repo.rebuild(f.ctx,f.payer,r.record_id)['verified'])
        self.assertEqual(f.repo.base.record(f.ctx,f.payer,r.record_id,1),f.record)
    def test_delete_keeps_other_ids_and_replay_and_cannot_recycle_id(self):
        f=self.f;self.save([self.op()]);self.save([ItemOperation(operation='DELETE',item_id='manual-new')])
        r=f.repo.base.record(f.ctx,f.payer,f.record.record_id)
        self.assertEqual([i.item_id for i in r.items],[i.item_id for i in f.record.items])
        self.assertTrue(f.repo.rebuild(f.ctx,f.payer,r.record_id)['verified'])
        with self.assertRaises(ReviewError):self.save([self.op()])
        self.assertEqual(f.repo.base.record(f.ctx,f.payer,r.record_id).revision,3)
    def test_completeness_uses_new_count_not_old_count(self):
        self.save([self.op()],confirm_items_complete=True,expected_item_count=len(self.f.record.items)+1,verified_pages=(0,))
        self.assertEqual(self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id).item_discovery_status,'COMPLETE')
        self.assertTrue(self.f.repo.rebuild(self.f.ctx,self.f.payer,self.f.record.record_id)['verified'])
    def test_invalid_page_duplicate_and_contradiction_roll_back(self):
        for op in [self.op(page_index=99),self.op(item_id=self.f.record.items[0].item_id),self.op(values={'description':'service','vat_treatment':'KCT','vat_rate':'.08'})]:
            with self.assertRaises((ReviewError,ValidationError)):self.save([op])
        self.assertEqual(self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id).revision,1)
    def test_delete_all_cannot_claim_complete(self):
        ops=[ItemOperation(operation='DELETE',item_id=i.item_id) for i in self.f.record.items]
        with self.assertRaises(ReviewError):self.save(ops,confirm_items_complete=True,expected_item_count=1,verified_pages=(0,))
        self.save(ops);self.assertFalse(self.f.repo.base.record(self.f.ctx,self.f.payer,self.f.record.record_id).items)
    def test_contract_rejects_geometry_and_mixed_edits(self):
        for kw in [dict(bbox=(.9,.2,.1,.3)),dict(bbox=None),dict(values={'description':'service','hacked':'a'}),dict(values={'description':' '})]:
            with self.assertRaises(ValidationError):self.op(**kw)
        with self.assertRaises(ValidationError):self.f.command([Change(field_path='currency',new_value='USD')],item_operations=(self.op(),))
    def test_http_idempotency_scope_and_stale(self):
        f=self.f;command=f.command([],item_operations=(self.op(),)).model_dump(mode='json');url='/v1/corrections?taxpayer_id='+f.payer
        headers={**f.headers,'Idempotency-Key':'manual-row-http'}
        a=f.client.post(url,json=command,headers=headers);self.assertEqual(a.status_code,200,a.text)
        b=f.client.post(url,json=command,headers=headers);self.assertTrue(b.json()['replayed'])
        c=f.client.post(url,json=command,headers={**f.headers,'Idempotency-Key':'manual-row-stale'});self.assertEqual(c.status_code,409)
        denied=f.client.post('/v1/corrections?taxpayer_id=other',json=command,headers=headers);self.assertEqual(denied.status_code,403)
