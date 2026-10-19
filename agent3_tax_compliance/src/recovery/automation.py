"""Revision-bound recovery queue with durable attempt limits; no CFR writes."""
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from pydantic import StrictBool,StrictInt,Field
from ..domain.base import Contract
from ..canonicalization.derive import sha
from ..persistence.repository import digest
from ..quality.completeness import flatten
from ..review.contracts import ReviewError
from ..review.repository import ReviewRepository,envelope
from .regions import RegionRecovery,RegionCommand,implementation_sha as region_sha
from .policy import diagnose,select_candidate,VERSION


class AutoCommand(Contract):
    expected_record_revision: StrictInt=Field(ge=1)
    retry_failed: StrictBool=False


def implementation_sha():
    return sha({'regions':region_sha(),**{p.name:digest(p.read_bytes()) for p in (Path(__file__),Path(__file__).with_name('policy.py'))}})


class AutomationReview:
    def __init__(self,settings,region=None):
        self.repo=ReviewRepository(settings);self.region=region or RegionRecovery(settings)
        self.path=settings.database_path.with_suffix('.automation.sqlite3')

    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS recovery_runs (tenant TEXT,payer TEXT,record TEXT,revision INTEGER,plan_key TEXT,binding TEXT,attempt INTEGER,id TEXT,status TEXT,expires REAL,payload TEXT,sha256 TEXT,PRIMARY KEY(tenant,payer,binding,attempt))')
        return db

    def inputs(self,ctx,payer,rid):
        record,artifact,_=self.repo.head_context(ctx,payer,rid)
        with self.repo.ingestion.db() as db:
            key=db.execute('SELECT ocr_config_key FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',(ctx.tenant_id,payer,artifact.artifact_id)).fetchone()[0]
        normalized=self.repo.extraction.ocr.get(ctx,payer,artifact.ingestion_id,key)['result']
        return record,artifact,normalized

    @staticmethod
    def read_payload(row):
        if digest(row['payload'].encode())!=row['sha256']:raise ValueError('automation report integrity failure')
        return json.loads(row['payload'])

    def inspect(self,ctx,payer,rid):
        ctx.require(ctx.tenant_id,payer)
        record,artifact,normalized=self.inputs(ctx,payer,rid)
        plan=diagnose(record,artifact,normalized)
        key=sha([record.model_dump(mode='json'),artifact.artifact_id,implementation_sha()])
        latest=None
        with closing(self.db()) as db:
            row=db.execute('SELECT * FROM recovery_runs WHERE tenant=? AND payer=? AND record=? AND revision=? AND plan_key=? AND payload IS NOT NULL ORDER BY rowid DESC LIMIT 1',(ctx.tenant_id,payer,rid,record.revision,key)).fetchone()
            if row:latest=self.read_payload(row)
        return record,plan,key,latest

    def run(self,ctx,payer,rid,command):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        record,plan,key,_=self.inspect(ctx,payer,rid)
        if record.revision!=command.expected_record_revision:raise ReviewError('REVISION_CONFLICT','Hóa đơn đã đổi; tải lại trước khi tự phục hồi.',409,record.revision)
        runtime='NOT_USED';inventory_error=None;comparison_ready=False
        spare=plan['max_crops']-plan['scheduled_crops']
        if plan['scheduled_fields']:
            try:runtime=self.region.client.inventory()['runtime_sha256']
            except Exception:runtime='UNAVAILABLE';inventory_error='MODEL_UNAVAILABLE'
            if not inventory_error and spare and hasattr(self.region,'comparison_runtime'):
                try:
                    runtime=sha([runtime,self.region.comparison_runtime()]);comparison_ready=True
                except Exception:pass  # Comparison failure must not block primary reads.
        binding=sha([key,runtime]);scope=(ctx.tenant_id,payer,binding)
        with closing(self.db()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute('SELECT * FROM recovery_runs WHERE tenant=? AND payer=? AND binding=? ORDER BY attempt DESC',scope).fetchall()
            if rows and rows[0]['status']=='RUNNING' and rows[0]['expires']>time.time():raise ReviewError('AUTOMATION_BUSY','Đang phục hồi bản này; chờ hoàn tất.',429)
            if rows and rows[0]['payload']:
                cached=self.read_payload(rows[0])
                if not command.retry_failed or not cached['errors']:
                    head=self.repo.base.record(ctx,payer,rid)
                    if head.revision!=record.revision:raise ReviewError('REVISION_CONFLICT','Hóa đơn đã đổi; tải lại để đối chiếu gợi ý.',409,head.revision)
                    return {**cached,'cache_hit':True}
            if len(rows)>=2:raise ReviewError('AUTOMATION_BUDGET','Đã hết 2 lượt phục hồi cho bản dữ liệu/cấu hình này; cần xử lý riêng.',409)
            attempt=len(rows)+1;identifier='auto-review-'+uuid4().hex
            db.execute('INSERT INTO recovery_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ctx.tenant_id,payer,rid,record.revision,key,binding,attempt,identifier,'RUNNING',time.time()+240,None,None))
        fields=flatten(record);entries=[];errors=[]
        for entry in plan['entries']:
            item={**entry}
            if entry['state']=='SCHEDULED':
                try:
                    if inventory_error:raise ReviewError(inventory_error,'Bộ đọc chưa sẵn sàng.',503)
                    result=self.region.read(ctx,payer,rid,RegionCommand(expected_record_revision=record.revision,field_path=entry['field_path']))
                    item.update(state='PROCESSED',recovery=result,selection=select_candidate(fields[entry['field_path']],entry,result))
                    if (comparison_ready and result.get('status')=='NEEDS_REVIEW' and entry['crop_count']<=spare):
                        spare-=entry['crop_count'];comparison_ready=False
                        try:
                            other=self.region.read(ctx,payer,rid,RegionCommand(expected_record_revision=record.revision,
                                field_path=entry['field_path'],reader='comparison'))
                            item['comparison']=other
                            if other.get('status')=='CANDIDATE':
                                item.update(primary_recovery=result,recovery=other,
                                    selection=select_candidate(fields[entry['field_path']],entry,other))
                        except Exception:item['comparison_error']='COMPARISON_UNAVAILABLE'
                except ReviewError as exc:
                    item.update(state='ERROR',reason=exc.code);errors.append({'field_path':entry['field_path'],'code':exc.code})
                except Exception:
                    item.update(state='ERROR',reason='RECOVERY_FAILED');errors.append({'field_path':entry['field_path'],'code':'RECOVERY_FAILED'})
            entries.append(item)
        current=self.repo.base.record(ctx,payer,rid)
        stale=current.revision!=record.revision
        result=envelope(run_id=identifier,record_id=rid,record_revision=record.revision,plan_key=key,policy_version=VERSION,
            runtime_sha256=runtime,attempt=attempt,entries=entries,errors=errors,stale=stale,
            recommended=sum(e.get('selection',{}).get('decision')=='RECOMMENDED' for e in entries),
            review_required=True,cache_hit=False,auto_confirmed=False)
        raw=json.dumps(result,ensure_ascii=False,separators=(',',':'))
        with closing(self.db()) as db,db:
            db.execute('UPDATE recovery_runs SET status=?,payload=?,sha256=? WHERE tenant=? AND payer=? AND binding=? AND attempt=?',('STALE' if stale else 'COMPLETE',raw,digest(raw.encode()),*scope,attempt))
        if stale:raise ReviewError('REVISION_CONFLICT','Hóa đơn đổi trong lúc phục hồi; chưa áp dụng kết quả.',409,current.revision)
        return result
