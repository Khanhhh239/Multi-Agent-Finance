"""Bounded, immutable line rereads. Suggestions never modify CFR or raw OCR."""
import io
import json
import math
import sqlite3
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from uuid import uuid4

from PIL import Image
from pydantic import Field, StrictInt
from ..domain.base import Contract, utcnow
from ..canonicalization.derive import sha
from ..persistence.repository import digest
from ..review.contracts import ReviewError
from ..review.repository import ReviewRepository, envelope
from ..review.revision_reprocessor import field_slot
from ..adapters.ocr.protocol import OCRConfig, OCRBridgeRequest, OCRError, correlate
from ..adapters.ocr.worker_client import WorkerClient

POLICY='region-lines-v1'
MODEL='vietocr_region_v1'
_SLOT=threading.BoundedSemaphore(1)


def implementation_sha():
    root=Path(__file__).resolve().parents[1]/'adapters/ocr'
    paths=[Path(__file__),*(root/name for name in ('protocol.py','worker_client.py','registry.py'))]
    return sha({p.name:digest(p.read_bytes()) for p in paths})


class RegionCommand(Contract):
    expected_record_revision: StrictInt = Field(ge=1)
    field_path: str = Field(min_length=1,max_length=256)


def supported(path):
    parts=path.split('.')
    return path in {'parties.'+p+'.'+f for p in ('seller','buyer') for f in ('name','address')} or (len(parts)==3 and parts[0]=='items' and parts[2]=='description')


def plan_regions(record,artifact,normalized,path):
    if not supported(path):
        raise ReviewError('REGION_UNSUPPORTED','Chỉ đọc lại tên, địa chỉ hoặc mô tả dòng hàng trong phiên bản này.')
    node,key=field_slot(record.model_dump(mode='json'),path)
    field=node.get(key) or {}
    refs=field.get('provenance',{}).get('evidence',[])
    if not refs:
        semantic=path.removeprefix('parties.')
        refs=[e.model_dump(mode='json') for c in artifact.candidates if c.semantic_field==semantic for e in c.evidence_refs]
    # Use only server-owned block IDs. Never accept caller-supplied rectangles.
    blocks={(p.page_index,b.block_id):(p,b) for p in normalized.pages for b in p.blocks if b.evidence}
    selected={}
    for ref in refs:
        pair=blocks.get((ref['page_index'],ref.get('block_id')))
        if pair:
            p,b=pair;selected[(p.page_index,b.block_id)]=(p,b)
    if not selected:
        raise ReviewError('REGION_NO_EVIDENCE','Chưa có vùng chữ đáng tin cậy. Cần đối chiếu toàn trang hoặc xử lý riêng.')
    if len(selected)>4:
        raise ReviewError('REGION_BUDGET','Trường có hơn 4 vùng chữ; cần xử lý riêng thay vì đọc thiếu một phần.')
    ordered=sorted(selected.values(),key=lambda v:(v[0].page_index,v[1].reading_order))
    for (pa,a),(pb,b) in zip(ordered,ordered[1:]):
        if pa.page_index!=pb.page_index or b.evidence.bbox[1]-a.evidence.bbox[3]>.04:
            raise ReviewError('REGION_CONFLICT','Các vùng nguồn rời nhau; cần chọn đúng ứng viên trước khi đọc lại để tránh ghép nhầm bên bán/bên mua.')
    for p,b in ordered:
        x0,y0,x1,y1=b.evidence.bbox
        # A line recognizer must not receive a whole table/page or multiline block.
        if y1-y0>.08 or (x1-x0)*(y1-y0)>.08:
            raise ReviewError('REGION_NOT_LINE','Vùng nguồn quá lớn cho bộ đọc từng dòng. Cần tách vùng trước.')
    return field,ordered


def crop_box(bbox,width,height):
    x0,y0,x1,y1=bbox
    return (max(0,math.floor(x0*width)-1),max(0,math.floor(y0*height)-1),
            min(width,math.ceil(x1*width)+1),min(height,math.ceil(y1*height)+1))


class RegionRecovery:
    def __init__(self,settings,client=None):
        self.settings=settings
        self.repo=ReviewRepository(settings)
        self.client=client or WorkerClient(model_id=MODEL)
        self.path=settings.database_path.with_suffix('.region-ocr.sqlite3')

    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.execute('CREATE TABLE IF NOT EXISTS region_reads (tenant TEXT,payer TEXT,cache_key TEXT,payload TEXT,sha256 TEXT,PRIMARY KEY(tenant,payer,cache_key))')
        return db

    def cached(self,ctx,payer,key):
        from contextlib import closing
        with closing(self.db()) as db:
            row=db.execute('SELECT payload,sha256 FROM region_reads WHERE tenant=? AND payer=? AND cache_key=?',(ctx.tenant_id,payer,key)).fetchone()
        if not row:return None
        if digest(row[0].encode())!=row[1]:raise ValueError('region result integrity failure')
        return {**json.loads(row[0]),'cache_hit':True}

    def read(self,ctx,payer,record_id,command):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        record,artifact,_=self.repo.head_context(ctx,payer,record_id)
        if record.revision!=command.expected_record_revision:
            raise ReviewError('REVISION_CONFLICT','Hóa đơn đã đổi; tải lại trước khi đọc vùng.',409,record.revision)
        with self.repo.ingestion.db() as db:
            key=db.execute('SELECT ocr_config_key FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',
                (ctx.tenant_id,payer,artifact.artifact_id)).fetchone()[0]
        normalized=self.repo.extraction.ocr.get(ctx,payer,artifact.ingestion_id,key)['result']
        field,regions=plan_regions(record,artifact,normalized,command.field_path)
        config=OCRConfig(version=POLICY,model_id=MODEL,timeout_seconds=30,memory_mb=3072,max_attempts=1,max_output_bytes=256*1024)
        try:runtime=self.client.inventory()['runtime_sha256']
        except OCRError as exc:raise ReviewError(exc.issue.code,'Bộ đọc vùng chưa sẵn sàng; dữ liệu hiện tại được giữ nguyên.',503) from None
        cache_key=sha({'record':sha(record.model_dump(mode='json')),'artifact':artifact.artifact_id,
            'ocr':sha(normalized.model_dump(mode='json')),'field':command.field_path,'runtime':runtime,
            'config':config.model_dump(mode='json'),'implementation':implementation_sha()})
        cached=self.cached(ctx,payer,cache_key)
        if cached:
            head=self.repo.base.record(ctx,payer,record_id)
            if head.revision!=record.revision:
                raise ReviewError('REVISION_CONFLICT','Hóa đơn đã đổi; tải lại trước khi dùng kết quả.',409,head.revision)
            return cached
        if not _SLOT.acquire(blocking=False):
            raise ReviewError('REGION_BUSY','Đang đọc một vùng khác; thử lại khi hoàn tất.',429)
        try:
            started=time.perf_counter();observations=[];requests=[];total_pixels=0
            with tempfile.TemporaryDirectory(prefix='agent3-region-') as directory:
                for index,(page,block) in enumerate(regions):
                    raw=self.repo.ingestion.render(ctx,payer,artifact.ingestion_id,page.page_index)
                    if digest(raw)!=page.image_hash:raise ValueError('region page hash mismatch')
                    with Image.open(io.BytesIO(raw)) as image:
                        box=crop_box(block.evidence.bbox,*image.size)
                        pixels=(box[2]-box[0])*(box[3]-box[1]);total_pixels+=pixels
                        if pixels>1_000_000 or total_pixels>2_000_000:
                            raise ReviewError('REGION_BUDGET','Vùng vượt ngân sách ảnh; cần xử lý riêng.')
                        with image.crop(box) as crop:
                            path=Path(directory)/f'line-{index}.png'
                            with crop.convert('RGB') as rgb:rgb.save(path)
                            width,height=crop.size
                    image_hash=digest(path.read_bytes())
                    requests.append(OCRBridgeRequest(config_version=POLICY,creator='region-recovery',stage='ocr',request_id='region-'+uuid4().hex,
                        source_id=record.source_id,document_id=record.document_id,page_id=page.page_id,page_index=page.page_index,
                        image_hash=image_hash,image_path=str(path.resolve()),image_width=width,image_height=height,
                        model_config_version=config.version,runtime_sha256=runtime,model_id=MODEL,timeout_seconds=config.timeout_seconds))
                    observations.append({'block_id':block.block_id,'original_text':block.text_raw,'evidence':block.evidence.model_dump(mode='json'),
                        'crop_pixel_box':box,'page_size':image.size,'crop_sha256':image_hash})
                try:responses=self.client.run_batch(requests,config,slot_timeout=0)
                except OCRError as exc:raise ReviewError(exc.issue.code,'Đọc vùng chưa thành công; giữ nguyên kết quả cũ và có thể thử lại.',503) from None
            if len(responses)!=len(requests):raise ValueError('region response count mismatch')
            for request,observation,response in zip(requests,observations,responses):
                correlate(request,response)
                if response.result is None:raise ValueError('region response missing result')
                observation.update(text=response.result.document_text_raw,raw_response=response.model_dump(mode='json'))
            head=self.repo.base.record(ctx,payer,record_id)
            if head.revision!=record.revision:
                raise ReviewError('REVISION_CONFLICT','Hóa đơn đã đổi trong khi đọc vùng; kết quả chưa được áp dụng.',409,head.revision)
            suggestion=unicodedata.normalize('NFC',' '.join(o['text'].strip() for o in observations)).strip()
            # Preserve duplicates and disagreements for review, not a guessed correction.
            result=envelope(recovery_id='region-read-'+uuid4().hex,record_id=record_id,record_revision=record.revision,
                extraction_artifact_id=artifact.artifact_id,field_path=command.field_path,actor_id=ctx.actor_id,
                created_at=utcnow().isoformat(),policy=POLICY,model_id=MODEL,runtime_sha256=runtime,
                status='CANDIDATE' if suggestion and all(o['text'].strip() for o in observations) else 'NEEDS_REVIEW',
                original_value=field.get('value'),suggested_value=suggestion or None,review_required=True,
                observations=observations,elapsed_seconds=time.perf_counter()-started,cache_hit=False)
            payload=json.dumps(result,ensure_ascii=False,separators=(',',':'))
            from contextlib import closing
            with closing(self.db()) as db,db:
                db.execute('INSERT OR IGNORE INTO region_reads VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,cache_key,payload,digest(payload.encode())))
                # Another app process may have committed the same key first.
                # Always return the persisted winner, so a later review reason
                # cannot refer to an observation ID that was never stored.
                stored=db.execute('SELECT payload,sha256 FROM region_reads WHERE tenant=? AND payer=? AND cache_key=?',
                    (ctx.tenant_id,payer,cache_key)).fetchone()
                if digest(stored[0].encode())!=stored[1]:raise ValueError('region result integrity failure')
                winner=json.loads(stored[0])
            return {**winner,'cache_hit':winner['recovery_id']!=result['recovery_id']}
        finally:_SLOT.release()
