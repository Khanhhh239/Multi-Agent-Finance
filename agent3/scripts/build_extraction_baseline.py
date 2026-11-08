"""Reuse committed normalized artifacts. No model execution or held-out tuning."""
import json,sqlite3,sys
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.config import Settings
from src.domain.taxpayer import AccessContext
from src.extraction.repository import ExtractionRepository
from src.extraction.service import canonicalize
from src.extraction.evidence import resolve
from src.canonicalization.derive import sha
from src.persistence.repository import digest
LOCAL=ROOT/'data invoice/plan04_local'
PUBLIC=ROOT/'docs/agent3/plans/evidence/plan04'

def comparable(value):
    if value is None: return None
    if isinstance(value,Decimal): return format(value,'f')
    if hasattr(value,'isoformat'): return value.isoformat()
    return ' '.join(str(value).split())

def field(record,path,row_positions):
    if record is None: return None
    if path.startswith(('seller.','buyer.')):
        party,name=path.split('.');return getattr(getattr(record.parties,party),name)
    if path.startswith('items.'):
        _,ref,name=path.split('.')
        position=row_positions[ref]
        if position>=len(record.items): return None
        return getattr(record.items[position],{'net_amount':'net'}.get(name,name),None)
    target=record
    for part in path.split('.'): target=getattr(target,part,None)
    return target

def raw_in_region(expected,normalized):
    raw=comparable(expected['raw_text'])
    for region in expected.get('evidence',[]):
        selected=[];x0,y0,x1,y1=region['bbox']
        for b in normalized.pages[region['page_index']].blocks:
            if not b.evidence: continue
            a,c,d,e=b.evidence.bbox;cx=(a+d)/2;cy=(c+e)/2
            if x0-.015<=cx<=x1+.015 and y0-.015<=cy<=y1+.015: selected.append(b)
        texts=[comparable(b.text_raw) for b in selected]
        texts.append(comparable(' '.join(b.text_raw for b in sorted(selected,key=lambda b:b.reading_order))))
        if raw in texts: return True
    return False

def evaluate(artifact,normalized,annotation):
    refs=list(dict.fromkeys(f['field_path'].split('.')[1] for f in annotation['fields'] if f['field_path'].startswith('items.')))
    positions={ref:n for n,ref in enumerate(refs)};out=[]
    for expected in annotation['fields']:
        if expected['status']!='OBSERVED': continue
        path=expected['field_path'];actual=field(artifact.record,path,positions)
        observed=comparable(actual.value) if actual else None
        truth=comparable(expected['normalized_value'])
        correct=actual is not None and actual.status=='PRESENT' and observed==truth
        present=actual is not None and actual.status=='PRESENT'
        cause=None
        if not correct:
            cause='PARSER' if all(p.route=='NATIVE_TEXT' for p in normalized.pages) or raw_in_region(expected,normalized) else 'OCR_TEXT_OR_LAYOUT_REQUIRES_INSPECTION'
        out.append({'field':path,'expected':truth,'predicted':observed,'status':actual.status.value if actual else 'NO_ROW',
            'correct':correct,'wrong_present':present and not correct,'diagnostic':cause,'raw_value_in_gt_region':raw_in_region(expected,normalized)})
    truths=[]
    for ref in refs:
        fs={f['field_path'].split('.')[-1]:f for f in annotation['fields'] if f['field_path'].startswith('items.'+ref+'.') and f['status']=='OBSERVED'}
        if 'description' in fs and 'net_amount' in fs:
            truths.append((comparable(fs['description']['normalized_value']),comparable(fs['net_amount']['normalized_value'])))
    predictions=[(comparable(i.description.value) if i.description else None,comparable(i.net.value) if i.net else None) for i in artifact.record.items] if artifact.record else []
    matches=0
    for truth in truths:
        if truth in predictions: matches+=1;predictions.remove(truth)
    return {'fields':out,'rows_expected':len(truths),'rows_matched_description_and_net':matches,
        'not_evaluated_by_status':{s:sum(f['status']==s for f in annotation['fields']) for s in ('NOT_ANNOTATED','ABSENT_CONFIRMED','UNREADABLE')},
        'row_alignment':'Generator row order for per-field diagnostics; unordered exact description+net multiset for row recall.'}

def main():
    LOCAL.mkdir(parents=True,exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
    manifest=[json.loads(line) for line in (ROOT/'data invoice/plan02_local/native_unicode_v2/baseline_manifest.jsonl').read_text(encoding='utf-8').splitlines()]
    hybrid=json.loads((ROOT/'docs/agent3/plans/evidence/plan03/model_switch/baseline_summary.json').read_text(encoding='utf-8'))
    inputs=[('native',r) for r in manifest if r['status']=='SUCCEEDED' and Path(r['source_path']).name.endswith('-pdf_text.pdf')]
    inputs += [('hybrid',r) for r in hybrid['outcomes']]
    assert len(inputs)==15
    repos={}
    for name,source in (('native',ROOT/'data invoice/plan03_local/baseline.sqlite3'),('hybrid',ROOT/'data invoice/plan03_local/model_switch/baseline.sqlite3')):
        database=LOCAL/(name+'.sqlite3')
        if not database.exists():
            with sqlite3.connect(source) as src,sqlite3.connect(database) as dst: src.backup(dst)
        repo=ExtractionRepository(Settings(database_path=database,staging_directory=LOCAL/'staging'))
        repo.base.initialize();repos[name]=repo
    outcomes=[];failures=[]
    for name,row in inputs:
        repo=repos[name];identifier=row['ingestion_id']
        ctx=AccessContext(actor_id='plan04-functional-evaluation',tenant_id='synthetic-tenant',taxpayer_ids=frozenset({'synthetic-payer'}),permissions=frozenset({'ADMIN'}))
        input_path=ROOT/row['artifact_path'] if name=='hybrid' else ROOT/'data invoice/plan03_local'/(identifier+'.extraction.json')
        target=json.loads(input_path.read_text(encoding='utf-8'))
        with repo.ingestion.db() as db:
            keys=db.execute('SELECT config_key,payload FROM ocr_jobs WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=? AND payload IS NOT NULL',
                (ctx.tenant_id,'synthetic-payer',identifier)).fetchall()
        keys=[k for k in keys if sha(json.loads(k['payload']))==sha(target)]
        assert len(keys)==1
        key=keys[0]['config_key'];normalized=repo.ocr.get(ctx,'synthetic-payer',identifier,key)['result']
        artifact=repo.work(ctx,'synthetic-payer',identifier,key)
        again=repo.work(ctx,'synthetic-payer',identifier,key);assert artifact==again
        master=repo.base.taxpayer(ctx,'synthetic-payer',normalized.taxpayer_master_revision)
        replay=canonicalize(normalized,artifact.record.source_format,master,artifact.profile,artifact.identity_map,
            record_id=artifact.record.record_id,artifact_id=artifact.artifact_id,created_at=artifact.created_at,extractor_sha256=artifact.extractor_sha256)
        assert replay==artifact
        document=repo.ingestion.document(ctx,'synthetic-payer',identifier)
        resolved=sum(len(resolve(artifact,c.candidate_id,normalized,document)['regions']) for c in artifact.candidates)
        path=LOCAL/(name+'-'+identifier+'.cfr.json');path.write_text(artifact.model_dump_json(indent=2)+'\n',encoding='utf-8')
        annotation_path=ROOT/Path(row['source_path']).with_suffix('.annotation.json')
        evaluation=evaluate(artifact,normalized,json.loads(annotation_path.read_text(encoding='utf-8'))) if annotation_path.exists() else None
        outcome={'cohort':name,'source_path':row['source_path'],'input_sha256':normalized.input_sha256,'ocr_model_id':normalized.ocr_config.model_id,
            'routes':[p.route for p in normalized.pages],'pages':len(normalized.pages),'artifact_path':str(path.relative_to(ROOT)),
            'artifact_sha256':digest(path.read_bytes()),'normalized_input_sha256':artifact.normalized_input_sha256,
            'extractor_sha256':artifact.extractor_sha256,'artifact_id':artifact.artifact_id,'ocr_config_key':key,
            'record_id':artifact.record.record_id,'items':len(artifact.record.items),'discovery':artifact.record.item_discovery_status,
            'review_required':artifact.review_required,'issues':[i.code for i in artifact.issues],
            'evidence_regions_resolved':resolved,'idempotence_and_pure_replay':True,'evaluation':evaluation}
        outcomes.append(outcome)
        if evaluation:
            failures.extend({'cohort':name,'source_path':row['source_path'],**f} for f in evaluation['fields'] if not f['correct'])
    aggregates={}
    for name in ('native','hybrid','ocr_backed_labelled_subset'):
        selected=[r for r in outcomes if r['cohort']==name] if name!='ocr_backed_labelled_subset' else [
            r for r in outcomes if r['cohort']=='hybrid' and r['evaluation'] and any(route!='NATIVE_TEXT' for route in r['routes'])]
        evaluated=[r for r in selected if r['evaluation']]
        fields=[f for r in evaluated for f in r['evaluation']['fields']]
        per_field={}
        for f in fields:
            label='items.'+f['field'].split('.')[-1] if f['field'].startswith('items.') else f['field']
            counts=per_field.setdefault(label,{'labelled':0,'correct':0,'wrong_present':0})
            counts['labelled']+=1;counts['correct']+=int(f['correct']);counts['wrong_present']+=int(f['wrong_present'])
        aggregates[name]={'documents':len(selected),'pages':sum(r['pages'] for r in selected),'labelled_documents':len(evaluated),
            'unlabelled_documents':len(selected)-len(evaluated),'labelled_fields':len(fields),'correct_fields':sum(f['correct'] for f in fields),
            'wrong_present_fields':sum(f['wrong_present'] for f in fields),'rows_expected':sum(r['evaluation']['rows_expected'] for r in evaluated),
            'rows_matched':sum(r['evaluation']['rows_matched_description_and_net'] for r in evaluated),'per_field':per_field}
    report={'date':'2026-10-12','scope':'technical-functional-synthetic-development-only','independently_reviewed_labels':False,
        'held_out_test':False,'model_execution':False,'production_accuracy_claim':False,'all_require_review':True,
        'cohorts':aggregates,'outcomes':outcomes,'failures_count':len(failures),
        'limitations':['Generated labels, not independent Vietnamese tax invoice labels.',
            'Native and hybrid cohorts overlap logical documents; do not pool as independent accuracy samples.',
            'No explicit row count in original fixtures: discovery remains UNKNOWN even when rows match.',
            'Unknown VAT legal category is retained; taxonomy is outside PLAN_04.',
            'OCR/parser attribution is a region-text diagnostic; label/role/layout failures require manual inspection.',
            'Every CFR requires review; wrong PRESENT values are not accepted financial decisions.']}
    (PUBLIC/'baseline_summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (PUBLIC/'field_failures.json').write_text(json.dumps(failures,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'documents':len(outcomes),'cohorts':aggregates,'failures':len(failures)}))

if __name__=='__main__': main()
