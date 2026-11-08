"""Scoped operational measurements. Counts are not OCR ground-truth accuracy."""
import json
import math
import sqlite3
import threading
import time
from contextlib import closing
from fastapi import APIRouter,Request
from ..domain.base import Identifier
from ..ingestion.auth import authenticate
from ..quality.completeness import flatten
from .repository import ReviewRepository,envelope

router=APIRouter()
_seen=set();_lock=threading.Lock()

def stage(path,method):
    if method!='POST':return None
    if path=='/v1/corrections':return 'review_save'
    if path.endswith('/reread-region'):return 'region_ocr'
    if path.endswith('/automation-review'):return 'automatic_recovery'
    if path.endswith('/explanations'):return 'explanation'
    if path=='/v1/evaluations':return 'tax_check'
    if path=='/v1/ingestions':return 'upload'
    return None

def db(settings):
    path=settings.database_path.with_suffix('.insights.sqlite3');path.parent.mkdir(parents=True,exist_ok=True)
    result=sqlite3.connect(path,timeout=2)
    result.execute('CREATE TABLE IF NOT EXISTS timings (tenant TEXT,payer TEXT,stage TEXT,seconds REAL,first_request INTEGER,created REAL)')
    return result

def record_timing(settings,tenant,payer,name,seconds,first):
    if not math.isfinite(seconds) or seconds<0:raise ValueError('invalid elapsed time')
    with closing(db(settings)) as conn,conn:
        conn.execute('INSERT INTO timings VALUES(?,?,?,?,?,?)',(tenant,payer,name,seconds,int(first),time.time()))
        conn.execute('DELETE FROM timings WHERE tenant=? AND payer=? AND rowid NOT IN (SELECT rowid FROM timings WHERE tenant=? AND payer=? ORDER BY rowid DESC LIMIT 1000)',(tenant,payer,tenant,payer))

def percentile(values,q):
    ordered=sorted(values)
    return ordered[max(0,math.ceil(q*len(ordered))-1)] if ordered else None

def timings(settings,ctx,payer):
    ctx.require(ctx.tenant_id,payer)
    with closing(db(settings)) as conn:
        rows=conn.execute('SELECT stage,seconds,first_request FROM timings WHERE tenant=? AND payer=? ORDER BY rowid DESC LIMIT 1000',(ctx.tenant_id,payer)).fetchall()
    names=sorted({r[0] for r in rows})
    return [dict(stage=name,count=len(values),p50_seconds=percentile(values,.5),p95_seconds=percentile(values,.95),
                 first_request_count=sum(r[2] for r in rows if r[0]==name),
                 subsequent_count=sum(not r[2] for r in rows if r[0]==name))
            for name in names for values in [[r[1] for r in rows if r[0]==name]]]

def install(app):
    @app.middleware('http')
    async def measured(request,call_next):
        started=time.perf_counter();response=await call_next(request);name=stage(request.url.path,request.method)
        if name and response.status_code<400:
            # Metrics must never make an otherwise successful save fail.
            try:
                ctx=authenticate(request.app.state.settings,request.headers.get('authorization'))
                payer=request.query_params.get('taxpayer_id');ctx.require(ctx.tenant_id,payer)
                binding=(str(request.app.state.settings.database_path),ctx.tenant_id,payer,name)
                with _lock:first=binding not in _seen;_seen.add(binding)
                record_timing(request.app.state.settings,ctx.tenant_id,payer,name,time.perf_counter()-started,first)
            except Exception:pass
        return response

@router.get('/v1/records/{record_id}/capture-insights')
def insights(request:Request,record_id:Identifier,taxpayer_id:Identifier):
    settings=request.app.state.settings;ctx=authenticate(settings,request.headers.get('authorization'))
    repo=ReviewRepository(settings);record,artifact,_=repo.head_context(ctx,taxpayer_id,record_id)
    fields={p:f for p,f in flatten(record).items() if not p.startswith('derived.')}
    with repo.ingestion.db() as conn:
        rows=conn.execute('SELECT payload,sha256 FROM review_events WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',(ctx.tenant_id,taxpayer_id,record_id)).fetchall()
    changes=0
    for row in rows:
        event=repo.checked_event(row)
        changes+=sum(c['field_path'] not in ('item_discovery_status','items') and c['before']!=c['after'] for c in event['changes'])
    return envelope(record_id=record_id,record_revision=record.revision,field_count=len(fields),item_count=len(record.items),
        present=sum(f.status=='PRESENT' for f in fields.values()),missing=sum(f.status=='MISSING' for f in fields.values()),
        ambiguous=sum(f.status=='AMBIGUOUS' for f in fields.values()),
        human_confirmed=sum(f.confidence_basis=='HUMAN_CONFIRMED' for f in fields.values()),review_saves=len(rows),
        reviewed_field_events=changes,timings=timings(settings,ctx,taxpayer_id),accuracy=None,
        measurement_scope='Last 1000 successful HTTP operations for this taxpayer. Time to response headers includes server work, not browser rendering. First/subsequent request is not model cold/warm inference.',
        quality_scope='Current saved record counts; human confirmation is not independent ground-truth accuracy.')
