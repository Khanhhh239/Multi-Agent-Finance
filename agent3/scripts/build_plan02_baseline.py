"""Functional reader baseline only. No OCR/model/real-data accuracy evaluation."""
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(PROJECT))
sys.path.insert(0,str(PROJECT/'tests/ingestion'))
from fixtures import image_bytes,pdf_bytes
from src.config import Settings
from src.domain.taxpayer import AccessContext,TaxpayerMaster
from src.ingestion.service import IngestionService
from src.ingestion.upload import StagedUpload

LOCAL=ROOT/'data invoice/plan02_local'
RUN=LOCAL/'native_unicode_v2'
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan02'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    LOCAL.mkdir(parents=True,exist_ok=True); RUN.mkdir(parents=True,exist_ok=True); PUBLIC.mkdir(parents=True,exist_ok=True)
    extra=LOCAL/'functional_set_v2'; extra.mkdir(exist_ok=True)
    cases={name:pdf_bytes(name) for name in ('mixed','invisible','hybrid','garbage','encrypted','oversized')}
    cases.update({'rotation-90':pdf_bytes(rotation=90,crop=True),'rotation-180':pdf_bytes(rotation=180,crop=True),
                  'rotation-270':pdf_bytes(rotation=270,crop=True),'corrupt':b'%PDF-1.4\ninvalid'})
    fixtures=[]
    for name,raw in cases.items():
        path=extra/(name+'.pdf')
        if not path.exists(): path.write_bytes(raw)
        fixtures.append((path,name))
    image=extra/'exif-6.jpg'
    if not image.exists(): image.write_bytes(image_bytes(exif=6,format='JPEG'))
    fixtures.append((image,'exif-6'))
    originals=PROJECT/'tests/fixtures/ocr/functional_set_v1'
    sources=sorted(p for p in originals.glob('syn-*') if p.suffix in ('.pdf','.png'))
    assert len(sources)==30
    settings=Settings(database_path=RUN/'baseline.sqlite3',staging_directory=RUN/'staging')
    service=IngestionService(settings); repo=service.repository; repo.base.initialize()
    ctx=AccessContext(actor_id='baseline-fixture',tenant_id='synthetic-tenant',taxpayer_ids=frozenset({'synthetic-payer'}),permissions=frozenset({'ADMIN'}))
    try: repo.base.taxpayer(ctx,'synthetic-payer',1)
    except KeyError:
        repo.base.add_taxpayer(ctx,TaxpayerMaster(config_version='fixture-v1',creator='baseline',stage='synthetic',
            tenant_id=ctx.tenant_id,taxpayer_id='synthetic-payer',revision=1,tax_code='0000000000',
            effective_from=date(2026,1,1),provenance_reference='project-generated-non-production'))
    rows=[]; confusion=Counter(); latencies=[]; failures=[]
    for path,kind in [(p,'project-original') for p in sources]+fixtures:
        mime={'.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg'}[path.suffix]
        with StagedUpload(settings) as staged:
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(64*1024),b''): staged.write(chunk)
            view=service.accept_staged(ctx,'synthetic-payer',1,path.stem,staged,mime,path.name)
        started=perf_counter(); outcome=service.work_one(ctx,'synthetic-payer',view.ingestion_id)
        row=dict(source_path=str(path.relative_to(ROOT)),sha256=sha(path),origin='SYNTHETIC_PROJECT',
                 case=kind,ingestion_id=view.ingestion_id,status=outcome.status,
                 issue=outcome.issue.model_dump(mode='json') if outcome.issue else None,
                 submit_to_result_ms=(perf_counter()-started)*1000)
        expected_error={'encrypted':'ENCRYPTED_PDF','oversized':'LIMIT_EXCEEDED','corrupt':'CORRUPT_DOCUMENT'}.get(kind)
        if expected_error:
            assert outcome.issue and outcome.issue.code==expected_error,(kind,outcome)
        else:
            assert outcome.status=='SUCCEEDED',(path,outcome.issue)
            artifact=repo.document(ctx,'synthetic-payer',view.ingestion_id)
            manifest_path=RUN/'manifests'/(path.stem+'.json'); manifest_path.parent.mkdir(exist_ok=True)
            manifest_path.write_text(artifact.model_dump_json(indent=2)+'\n',encoding='utf-8')
            row.update(document_manifest=str(manifest_path.relative_to(ROOT)),document_sha256=sha(manifest_path),
                       routes=[p.route for p in artifact.pages],reader_elapsed_ms=artifact.reader_elapsed_ms)
            if kind=='project-original':
                expected='NATIVE_TEXT' if 'pdf_text' in path.stem else 'OCR'
                for page in artifact.pages: confusion[(expected,page.route)]+=1
                latencies.append(artifact.reader_elapsed_ms)
            for page in artifact.pages:
                assert page.route_reasons and page.geometry.transform_id
                if page.route=='NATIVE_TEXT': assert page.native_blocks
        rows.append(row)
        print(f'{path.stem}: {outcome.status} '+str(row.get('routes',expected_error)),flush=True)
    manifest=RUN/'baseline_manifest.jsonl'
    manifest.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    summary=dict(schema_version='1.0.0',config_version='ingestion-v1',creator='build_plan02_baseline',stage='functional-baseline',
        created_at=datetime.now(timezone.utc).isoformat(),original_source_count=30,extra_source_count=len(fixtures),
        original_page_count=sum(confusion.values()),route_confusion=[dict(expected=a,actual=b,count=n) for (a,b),n in sorted(confusion.items())],
        reader_latency_ms=dict(median=statistics.median(latencies),max=max(latencies),sample_count=len(latencies)),
        expected_negative_documents=3,unexpected_failures=failures,manifest_sha256=sha(manifest),
        original_source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
        scope='synthetic-functional-only; no OCR inference or real invoice accuracy')
    (PUBLIC/'baseline_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    text=['# Native/PDF reader functional baseline — 12/10/2026','',
          'Bộ project-generated của PLAN_00: 30 file/10 logical documents; thêm 11 fixtures PLAN_02. Không có OCR inference hoặc số accuracy thực tế.',
          '', '| Expected route | Actual route | Pages |','|---|---|---:|']
    text += [f'| {a} | {b} | {n} |' for (a,b),n in sorted(confusion.items())]
    text += ['',f'Original pages: {sum(confusion.values())}. Route confusion chỉ là functional diagnostic theo loại fixture đã sinh, không chứng minh generalization.',
        '',f'Latency reader (parse/native/layout/render; không gồm OCR hay process startup): median {statistics.median(latencies):.2f} ms, max {max(latencies):.2f} ms trên 30 documents. Không là SLO production.',
        '', 'Extra cases: mixed, invisible overlay, hybrid, garbage text, encrypted, oversized, rotations 90/180/270 có crop, corrupt, JPEG EXIF 6. Ba negative cases trả đúng typed errors; không có extraction outbox cho chúng.',
        '', 'Reading order: reader giữ source_order và reading_order heuristic; chưa chứng minh thứ tự nhiều cột hoặc độ đúng line items. Invisible text bị bỏ khỏi native blocks; HYBRID có OCR regions và deduplication_required cho PLAN_03.',
        '', 'Manifest, text/bbox và renders nằm trong `data invoice/plan02_local/` (ignored). Raw hashes ở baseline_summary.json. Retry cùng ingestion giữ page_id; không ghi đè raw. NATIVE_TEXT không tạo probability confidence=1.0.',
        '', 'Lệnh root: `.\\agent3_tax_compliance\\.venv\\Scripts\\python.exe scripts/build_plan02_baseline.py`. Chạy lại tái dùng ingestions đã commit; latency của reader lấy từ artifact lần đầu.']
    (PUBLIC/'native_pdf_baseline.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(f'PASS: 30 originals + {len(fixtures)} extra cases; {sum(confusion.values())} original pages; 3 typed negative documents',flush=True)


if __name__=='__main__': main()
