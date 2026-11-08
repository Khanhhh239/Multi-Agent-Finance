"""Simulated review on copies of pinned native + PP-OCRv6/VietOCR artifacts; no OCR rerun or accuracy claim."""
import json,sqlite3,sys,time,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.config import Settings
from src.domain.taxpayer import AccessContext
from src.persistence.repository import digest
from src.review.correction_service import CorrectionService
from src.review.contracts import CorrectionCommand,Change
from src.quality.repository import replay

LOCAL=ROOT/'data invoice/plan06_local';PUBLIC=ROOT/'docs/agent3/plans/evidence/plan06'
def main():
    LOCAL.mkdir(parents=True,exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
    previous=json.loads((ROOT/'docs/agent3/plans/evidence/plan05/baseline_summary.json').read_text(encoding='utf-8'))
    repos={};original_hashes={}
    for cohort in ('native','hybrid'):
        source=ROOT/'data invoice/plan05_local'/(cohort+'.sqlite3');original_hashes[str(source.relative_to(ROOT))]=digest(source.read_bytes())
        target=LOCAL/(cohort+'.sqlite3')
        if not target.exists():
            with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:src.backup(dst)
        repo=CorrectionService(Settings(database_path=target,staging_directory=LOCAL/'staging'));repo.base.initialize();repos[cohort]=repo
    outcomes=[];latencies=[]
    for row in previous['outcomes']:
        repo=repos[row['cohort']];old_q=repo.quality.get(AccessContext(actor_id='plan06-fixture-runner',tenant_id=json.loads((ROOT/row['artifact_path']).read_text(encoding='utf-8'))['tenant_id'],
            taxpayer_ids=frozenset({json.loads((ROOT/row['artifact_path']).read_text(encoding='utf-8'))['taxpayer_id']})),
            json.loads((ROOT/row['artifact_path']).read_text(encoding='utf-8'))['taxpayer_id'],row['assessment_id'])
        ctx=AccessContext(actor_id='plan06-simulated-review-not-independent-label',tenant_id=old_q.tenant_id,taxpayer_ids=frozenset({old_q.taxpayer_id}),permissions=frozenset({'ADMIN'}));payer=old_q.taxpayer_id
        artifact=repo.extraction.get(ctx,payer,row['artifact_id']);record=artifact.record
        assert record is not None
        repo.quality.work(ctx,payer,artifact.artifact_id);repo.ensure_tasks(ctx,payer,record.record_id)
        tasks=repo.page(ctx,payer,'tasks',record_id=record.record_id,revision=1,limit=100)['items'];assert tasks
        changes=[Change(field_path='parties.seller.tax_id',new_value=repo.base.taxpayer(ctx,payer,record.taxpayer_master_revision).tax_code),
                 Change(field_path='parties.buyer.tax_id',new_value='9876543210')]
        if record.items:
            prefix='items.'+record.items[0].item_id+'.';changes.extend([Change(field_path=prefix+'net',new_value='200000.01'),
                Change(field_path=prefix+'vat_treatment',new_value='TAXABLE_RATE'),Change(field_path=prefix+'vat_rate',new_value='0.08')])
        doc=repo.ingestion.document(ctx,payer,artifact.ingestion_id)
        command=CorrectionCommand(record_id=record.record_id,expected_revision=1,task_id=tasks[0]['task_id'],reason='Synthetic functional correction; not an independent human label',changes=tuple(changes),
            confirm_items_complete=bool(record.items),expected_item_count=len(record.items) if record.items else None,
            verified_pages=tuple(p.page_index for p in doc.pages) if record.items else ())
        started=time.perf_counter();result=repo.correct(ctx,payer,command,'plan06-functional-v1');latency=(time.perf_counter()-started)*1000
        if not result['replayed']:latencies.append(latency)
        export=repo.export(ctx,payer,record.record_id);q=repo.quality.get(ctx,payer,result['assessment_id'])
        assert export['record']['revision']==2 and repo.rebuild(ctx,payer,record.record_id)['verified']
        assert replay(repo.quality.inputs(ctx,payer,q.assessment_id),q)==q
        grant=repo.grant(ctx,payer,artifact.artifact_id,doc.pages[0].page_index);assert repo.redeem(ctx,payer,grant['token']).startswith(b'\x89PNG')
        path=LOCAL/(row['cohort']+'-'+record.record_id+'.export.json');path.write_text(json.dumps(export,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        outcomes.append({'cohort':row['cohort'],'artifact_id':artifact.artifact_id,'record_id':record.record_id,'record_revision':2,
            'event_id':result['event_id'],'assessment_id':q.assessment_id,'pages':len(doc.pages),'items':len(record.items),
            'initial_tasks':len(tasks),'remaining_tasks':len(repo.page(ctx,payer,'tasks',record_id=record.record_id,revision=2,status='OPEN',limit=100)['items']),
            'replay_verified':True,'signed_evidence_verified':True,'direction':export['summary']['direction']['value'],
            'human_proof_branch_fields':sum(f.reliability=='HUMAN_CONFIRMED' for f in q.fields),
            'simulated_review_only':True,'export_path':str(path.relative_to(ROOT)),'export_sha256':digest(path.read_bytes())})
    for path,expected in original_hashes.items():assert digest((ROOT/path).read_bytes())==expected
    latencies.sort()
    old_path=PUBLIC/'baseline_summary.json'
    old=json.loads(old_path.read_text()) if old_path.exists() else {}
    timing={'samples':len(latencies),'p95':latencies[math.ceil(.95*len(latencies))-1], 'minimum':min(latencies),'maximum':max(latencies),
        'scope':'Initial synthetic correction transaction on cloned local DB; excludes upload, PDF/OCR, HTTP/UI and human time.'} if latencies else old.get('correction_latency_ms')
    summary={'date':'2026-10-13','gate_scope':'TECHNICAL_MANUAL_REVIEW_ONLY','documents':len(outcomes),'pages':sum(o['pages'] for o in outcomes),
        'original_review_rate':1.0,'reviewed_by_independent_human':0,'human_correction_time_seconds':None,'after_human_review_field_accuracy':None,
        'production_acceptance':'NOT_EVALUATED_DQ_01_TO_05','ocr_model_changed':False,'ocr_rerun':False,
        'correction_latency_ms':timing,'end_to_end_pdf_ocr_p95_ms':None,'source_databases_unchanged':original_hashes,'outcomes':outcomes,
        'limitations':repo.limitations()+['Scripted corrections exercise the human-proof code path but are not actual human review or annotation.',
            '15 artifacts/17 pages contain repeated logical documents and one synthetic template; sample counts are not independent.',
            'UI visual/user acceptance and correction time are not measured; syntax and DOM bindings are checked separately.']}
    old_path.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'documents':len(outcomes),'pages':summary['pages'],'correction_latency_ms':timing,'independent_human_reviews':0}))
if __name__=='__main__':main()
