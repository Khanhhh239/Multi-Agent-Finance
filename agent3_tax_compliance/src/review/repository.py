import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4
from ..canonicalization.derive import sha
from ..persistence.repository import digest
from ..quality.repository import QualityRepository
from .contracts import ReviewError

def envelope(**values): return {'schema_version':'1.0.0',**values}
def raw_json(value): return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))

class ReviewRepository:
    def __init__(self,settings):
        self.quality=QualityRepository(settings);self.extraction=self.quality.extraction
        self.ingestion=self.quality.ingestion;self.base=self.quality.base;self.settings=settings

    def secret(self):
        with self.ingestion.db() as db: return db.execute('SELECT secret FROM review_secrets WHERE id=1').fetchone()[0]

    def sign(self,value):
        body=base64.urlsafe_b64encode(raw_json(value).encode()).decode().rstrip('=')
        return body+'.'+hmac.new(self.secret(),body.encode(),hashlib.sha256).hexdigest()

    def unsign(self,token):
        try:
            body,mac=token.split('.')
            if not hmac.compare_digest(mac,hmac.new(self.secret(),body.encode(),hashlib.sha256).hexdigest()): raise ValueError()
            return json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        except (ValueError,TypeError,UnicodeError): raise ReviewError('INVALID_TOKEN','Invalid signed token.',400) from None

    def head_context(self,ctx,payer,record_id):
        record=self.base.record(ctx,payer,record_id)
        with self.ingestion.db() as db:
            rows=db.execute("SELECT artifact_id FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND json_extract(payload,'$.record.record_id')=? ORDER BY rowid",
                (ctx.tenant_id,payer,record_id)).fetchall()
        artifact=next((a for a in (self.extraction.get(ctx,payer,r['artifact_id']) for r in rows)
                       if a.record and a.record.record_id==record_id),None)
        if artifact is None: raise KeyError('capture extraction not found')
        with self.ingestion.db() as db:
            rows=db.execute('SELECT assessment_id FROM quality_assessments WHERE tenant_id=? AND taxpayer_id=? AND extraction_artifact_id=? ORDER BY rowid DESC',
                (ctx.tenant_id,payer,artifact.artifact_id)).fetchall()
        assessment=next((q for q in (self.quality.get(ctx,payer,r['assessment_id']) for r in rows) if q.record_revision==record.revision),None)
        if assessment is None: raise ReviewError('ASSESSMENT_MISSING','Run quality on the current record revision.',409,record.revision)
        return record,artifact,assessment

    def view(self,ctx,payer,record_id):
        r,a,q=self.head_context(ctx,payer,record_id)
        doc=self.ingestion.document(ctx,payer,a.ingestion_id)
        with self.ingestion.db() as db:
            job=db.execute('SELECT job_id,state,payload FROM capture_jobs WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                (ctx.tenant_id,payer,a.ingestion_id)).fetchone()
        if job and json.loads(job['payload']).get('record_id',r.record_id)!=r.record_id:
            job=None
        return envelope(record=r.model_dump(mode='json'),extraction_artifact_id=a.artifact_id,ingestion_id=a.ingestion_id,
            candidates=[c.model_dump(mode='json') for c in a.candidates],assessment=q.model_dump(mode='json'),
            page_count=len(doc.pages),limitations=self.limitations(),capture_job={k:job[k] for k in ('job_id','state')} if job else None)

    @staticmethod
    def limitations():
        return ['Technical manual-review MVP; Vietnamese production accuracy is not established.',
            'Independent labels, real pilot data and release calibration remain pending.',
            'Existing rows can be edited; adding/splitting/merging rows and multi-invoice documents require re-extraction/operator.',
            'No tax compliance verdict or automatic acceptance.']

    def build_tasks(self,db,ctx,payer,assessment,old_tasks=()):
        if not assessment.record_id: return []
        ids=[]
        for rec in assessment.recommendations:
            if rec.reason=='AUTO_ACCEPT_DISABLED': continue
            path=rec.field_path or ''
            task_id='task-'+sha([ctx.tenant_id,payer,assessment.record_id,assessment.record_revision,rec.reason,path,rec.action])[:32]
            lineage=[t['task_id'] for t in old_tasks if t['reason']==rec.reason and t['field_path']==path]
            db.execute('INSERT OR IGNORE INTO review_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (ctx.tenant_id,payer,task_id,assessment.record_id,assessment.record_revision,assessment.assessment_id,
                 rec.reason,path,rec.action,'OPEN',raw_json(lineage)))
            ids.append(task_id)
        return ids

    def ensure_tasks(self,ctx,payer,record_id):
        ctx.require(ctx.tenant_id,payer,'WRITE');record,artifact,q=self.head_context(ctx,payer,record_id)
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            head=db.execute('SELECT head FROM records WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',
                (ctx.tenant_id,payer,record_id)).fetchone()[0]
            if head!=record.revision: raise ReviewError('REVISION_CONFLICT','Reload the current revision.',409,head)
            ids=self.build_tasks(db,ctx,payer,q)
            self.ingestion._event(db,ctx,payer,artifact.ingestion_id,'REVIEW_TASKS_BUILT',q.input_sha256,{'record_revision':head,'task_count':len(ids)})
        return envelope(task_ids=ids,record_revision=head)

    def page(self,ctx,payer,kind,*,record_id=None,status=None,revision=None,cursor=None,limit=25):
        ctx.require(ctx.tenant_id,payer)
        if not 1<=limit<=100: raise ReviewError('PAGE_LIMIT','Page size must be between 1 and 100.')
        tables={'tasks':'review_tasks','revisions':'revisions','audit':'review_events','records':'records'}
        table=tables[kind];where='tenant_id=? AND taxpayer_id=?';args=[ctx.tenant_id,payer]
        scope=[ctx.tenant_id,payer,kind,record_id,status,revision]
        if record_id: where+=' AND record_id=?';args.append(record_id)
        if revision is not None:
            if kind not in ('tasks','revisions') or revision<1: raise ReviewError('INVALID_FILTER','Invalid revision filter.')
            where+=' AND revision=?';args.append(revision)
        if status:
            if kind!='tasks' or status not in ('OPEN','RESOLVED','SUPERSEDED','WAITING_DATA','OPERATOR'): raise ReviewError('INVALID_FILTER','Invalid task status.')
            where+=' AND status=?';args.append(status)
        with self.ingestion.db() as db:
            snapshot=db.execute(f'SELECT COALESCE(MAX(rowid),0) FROM {table} WHERE {where}',args).fetchone()[0]
            after=0
            if cursor:
                saved=self.unsign(cursor)
                if saved.get('scope')!=scope or saved.get('exp',0)<time.time(): raise ReviewError('CURSOR_SCOPE','Cursor expired or belongs to another query.',400)
                snapshot=saved['snapshot'];after=saved['after']
            rows=db.execute(f'SELECT rowid AS _rowid,* FROM {table} WHERE {where} AND rowid>? AND rowid<=? ORDER BY rowid LIMIT ?',
                            args+[after,snapshot,limit+1]).fetchall()
        items=[]
        for row in rows[:limit]:
            data=dict(row);data.pop('_rowid',None)
            if kind=='revisions':
                if digest(data['payload'].encode())!=data['sha256']: raise ValueError('revision integrity failure')
                data={'revision':data['revision'],'sha256':data['sha256']}
            elif kind=='audit':
                event=self.checked_event(data);data={k:event[k] for k in ('event_id','actor_id','created_at','before_revision','after_revision','before_sha256','after_sha256','reason')}
                data['field_paths']=[c['field_path'] for c in event['changes']]
            elif kind=='tasks':
                data['previous_ids']=json.loads(data['previous_ids'])
                data.update(schema_version='1.0.0',config_version='review-task-v1',creator='review-task-builder',stage='review',
                    created_at=self.quality.get(ctx,payer,data['assessment_id']).created_at.isoformat())
            elif kind=='records':
                record=self.base.record(ctx,payer,data['record_id'])
                data['summary']={'invoice_number':record.invoice.number.value,
                    'issue_date':record.invoice.issue_date.value.isoformat() if record.invoice.issue_date.value else None,
                    'seller_name':record.parties.seller.name.value,
                    'gross':str(record.totals.gross.value) if record.totals.gross.value is not None else None}
            items.append(data)
        next_cursor=self.sign({'scope':scope,'snapshot':snapshot,'after':rows[limit-1]['_rowid'],'exp':int(time.time())+3600}) if len(rows)>limit else None
        return envelope(items=items,next_cursor=next_cursor)

    @staticmethod
    def checked_event(row):
        from .contracts import CorrectionEvent
        if digest(row['payload'].encode())!=row['sha256']: raise ValueError('review event integrity failure')
        return CorrectionEvent.model_validate_json(row['payload']).model_dump(mode='json')

    def task_action(self,ctx,payer,task_id,command):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        with self.ingestion.db() as db:
            db.execute('BEGIN IMMEDIATE')
            task=db.execute('SELECT * FROM review_tasks WHERE tenant_id=? AND taxpayer_id=? AND task_id=?',(ctx.tenant_id,payer,task_id)).fetchone()
            if not task: raise KeyError('task not found')
            head=db.execute('SELECT head FROM records WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',(ctx.tenant_id,payer,task['record_id'])).fetchone()[0]
            if task['revision']!=head or task['status'] in ('RESOLVED','SUPERSEDED'): raise ReviewError('STALE_TASK','Reload the current task.',409,head)
            state={'REQUEST_DATA':'WAITING_DATA','OPERATOR':'OPERATOR','REOPEN':'OPEN'}[command.action]
            db.execute('UPDATE review_tasks SET status=? WHERE tenant_id=? AND taxpayer_id=? AND task_id=?',(state,ctx.tenant_id,payer,task_id))
            artifact=self.extraction.get(ctx,payer,self.quality.get(ctx,payer,task['assessment_id']).extraction_artifact_id)
            self.ingestion._event(db,ctx,payer,artifact.ingestion_id,'REVIEW_TASK_ACTION',sha([task_id,state]),{'task_id':task_id,'action':command.action,'reason':command.reason})
        return envelope(task_id=task_id,status=state)

    def grant(self,ctx,payer,artifact_id,page_index,ttl=120):
        ctx.require(ctx.tenant_id,payer)
        if not 1<=ttl<=300: raise ReviewError('TTL','Evidence expiry must be 1–300 seconds.')
        artifact=self.extraction.get(ctx,payer,artifact_id);doc=self.ingestion.document(ctx,payer,artifact.ingestion_id)
        if page_index not in {p.page_index for p in doc.pages}: raise KeyError('page not found')
        token=self.sign({'scope':[ctx.tenant_id,payer,ctx.actor_id,artifact_id,page_index],'exp':time.time()+ttl})
        return envelope(token=token,expires_in=ttl,page_index=page_index)

    def redeem(self,ctx,payer,token):
        ctx.require(ctx.tenant_id,payer);claims=self.unsign(token);scope=claims.get('scope',[])
        if len(scope)!=5 or scope[:3]!=[ctx.tenant_id,payer,ctx.actor_id] or claims.get('exp',0)<time.time():
            raise ReviewError('EVIDENCE_EXPIRED','Evidence access expired or is outside this actor scope.',403)
        artifact=self.extraction.get(ctx,payer,scope[3])
        return self.ingestion.render(ctx,payer,artifact.ingestion_id,scope[4])

    def export(self,ctx,payer,record_id):
        view=self.view(ctx,payer,record_id);q=view['assessment']
        return envelope(record=view['record'],summary={'direction':view['record']['derived']['invoice_direction'],
            'observed_totals':view['record']['totals'],'derived_totals':view['record']['derived']['totals']},
            unresolved_issues=q['issues'],review_required=True,limitations=self.limitations())

    def rebuild(self,ctx,payer,record_id):
        from ..domain.cfr import CanonicalFinancialRecord
        from ..canonicalization.derive import rederive
        from .revision_reprocessor import field_slot
        current,artifact,_=self.head_context(ctx,payer,record_id)
        source,_=self.base.source(ctx,payer,current.source_id)
        if source.sha256!=artifact.input_sha256: raise ValueError('source binding mismatch')
        from ..extraction.service import canonicalize,implementation_sha
        if artifact.extractor_sha256!=implementation_sha(): raise ValueError('rebuild requires the pinned extractor implementation')
        with self.ingestion.db() as db:
            row=db.execute('SELECT ocr_config_key FROM cfr_extractions WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',
                (ctx.tenant_id,payer,artifact.artifact_id)).fetchone()
        normalized=self.extraction.ocr.get(ctx,payer,artifact.ingestion_id,row['ocr_config_key'])['result']
        document=self.ingestion.document(ctx,payer,artifact.ingestion_id)
        if sha(normalized.model_dump(mode='json'))!=artifact.normalized_input_sha256 or normalized.document_artifact_sha256!=digest(document.model_dump_json().encode()):
            raise ValueError('normalized/document binding mismatch')
        initial=canonicalize(normalized,source.detected_format,self.base.taxpayer(ctx,payer,current.taxpayer_master_revision),
            artifact.profile,artifact.identity_map,record_id=artifact.record.record_id,artifact_id=artifact.artifact_id,
            created_at=artifact.created_at,extractor_sha256=artifact.extractor_sha256)
        if initial!=artifact: raise ValueError('initial extraction replay mismatch')
        # Revision 1 is pinned to the immutable extraction. Later observed changes come only from events.
        data=artifact.record.model_dump(mode='json')
        master=self.base.taxpayer(ctx,payer,current.taxpayer_master_revision)
        with self.ingestion.db() as db:
            rows=db.execute('SELECT * FROM review_events WHERE tenant_id=? AND taxpayer_id=? AND record_id=? ORDER BY rowid',
                (ctx.tenant_id,payer,record_id)).fetchall()
        for row in rows:
            event=self.checked_event(row)
            if sha(data)!=event['before_sha256'] or data['revision']!=event['before_revision']: raise ValueError('event chain mismatch')
            for change in event['changes']:
                if change['field_path']=='items':
                    if {'rows':data['items']}!=change['before']:raise ValueError('before items mismatch')
                    data['items']=change['after']['rows']
                elif change['field_path']=='item_discovery_status':
                    if data['item_discovery_status']!=change['before']: raise ValueError('before mismatch')
                    data['item_discovery_status']=change['after']
                else:
                    node,key=field_slot(data,change['field_path'])
                    if node.get(key)!=change['before']: raise ValueError('before mismatch')
                    node[key]=change['after']
            data.update(event['record_stamp']);record=CanonicalFinancialRecord.model_validate(data)
            record,_,_=rederive(record,master,artifact.profile);data=record.model_dump(mode='json')
            if sha(data)!=event['after_sha256']: raise ValueError('after mismatch')
        if data!=current.model_dump(mode='json'): raise ValueError('rebuild differs from persisted head')
        return envelope(record_revision=current.revision,sha256=sha(data),verified=True,source_sha256=source.sha256)
