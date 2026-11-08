"""Development quality evaluation and score inventory; never fit on PLAN_04 labels."""
import json,sqlite3,sys,time
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.config import Settings
from src.domain.taxpayer import AccessContext
from src.extraction.contracts import ExtractionArtifact
from src.quality.repository import QualityRepository,replay
from src.quality.assessor import family
from src.quality.policy import load_policy
from src.canonicalization.derive import sha
from src.persistence.repository import digest
LOCAL=ROOT/'data invoice/plan05_local';PUBLIC=ROOT/'docs/agent3/plans/evidence/plan05'

def model_path(path,record):
    if path.startswith(('seller.','buyer.')): return 'parties.'+path
    if path.startswith('items.'):
        _,ref,name=path.split('.')
        # Only generator diagnostic row order, not production identity matching.
        position=int(ref.rsplit('-',1)[-1])
        if position>=len(record.items): return None
        return 'items.'+record.items[position].item_id+'.'+{'net_amount':'net'}.get(name,name)
    return path

def main():
    LOCAL.mkdir(parents=True,exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
    baseline=json.loads((ROOT/'docs/agent3/plans/evidence/plan04/baseline_summary.json').read_text(encoding='utf-8'))
    policy=load_policy();repos={}
    for name in ('native','hybrid'):
        source=ROOT/'data invoice/plan04_local'/(name+'.sqlite3');database=LOCAL/(name+'.sqlite3')
        if not database.exists():
            with sqlite3.connect(source) as src,sqlite3.connect(database) as dst: src.backup(dst)
        repo=QualityRepository(Settings(database_path=database,staging_directory=LOCAL/'staging'))
        repo.base.initialize();repos[name]=repo
    outcomes=[];score_inventory=[];recommendations=[];wrong_present=0;false_acceptances=0;latencies=[]
    for row in baseline['outcomes']:
        repo=repos[row['cohort']];raw=(ROOT/row['artifact_path']).read_bytes();assert digest(raw)==row['artifact_sha256']
        artifact=ExtractionArtifact.model_validate_json(raw)
        ctx=AccessContext(actor_id='plan05-development-evaluation',tenant_id=artifact.tenant_id,
            taxpayer_ids=frozenset({artifact.taxpayer_id}),permissions=frozenset({'ADMIN'}))
        started=time.perf_counter();assessment=repo.work(ctx,artifact.taxpayer_id,artifact.artifact_id);latencies.append((time.perf_counter()-started)*1000)
        assert assessment==repo.work(ctx,artifact.taxpayer_id,artifact.artifact_id)
        assert replay(repo.inputs(ctx,artifact.taxpayer_id,assessment.assessment_id),assessment)==assessment
        path=LOCAL/(row['cohort']+'-'+assessment.assessment_id+'.quality.json')
        path.write_text(assessment.model_dump_json(indent=2)+'\n',encoding='utf-8')
        by={f.field_path:f for f in assessment.fields}
        scope=repo.inputs(ctx,artifact.taxpayer_id,assessment.assessment_id)['scope']
        if row['evaluation']:
            for field in row['evaluation']['fields']:
                path_in_record=model_path(field['field'],artifact.record)
                candidates=[c for c in artifact.candidates if c.semantic_field in (path_in_record,field['field'])]
                scores=[s.model_dump(mode='json') for c in candidates for s in c.raw_scores]
                quality=by.get(path_in_record)
                is_accepted=bool(quality and quality.auto_accepted)
                wrong_present+=int(field['wrong_present']);false_acceptances+=int(is_accepted and not field['correct'])
                score_inventory.append({'sample_id':'score-'+sha([row['cohort'],artifact.artifact_id,field['field']])[:32],
                    'source_sha256':artifact.input_sha256,'logical_document_id':Path(row['source_path']).stem.split('-')[0]+'-'+Path(row['source_path']).stem.split('-')[1],
                    'template_group_id':'project-synthetic-template-v1','split':'DEVELOPMENT','cohort':row['cohort'],
                    'field_family':family(path_in_record) if path_in_record else field['field'],'engine_id':row['ocr_model_id'],
                    'engine_config_version':scope['engine_config_version'],'engine_runtime_sha256':scope['engine_runtime_sha256'],
                    'extractor_sha256':artifact.extractor_sha256,'preprocess_version':scope['preprocess_version'],
                    'raw_scores':scores,'correct':field['correct'],'wrong_present':field['wrong_present'],
                    'annotation_status':'GENERATOR_VERIFIED_NOT_INDEPENDENTLY_REVIEWED','calibration_eligible':False,
                    'exclusion_reasons':['NOT_INDEPENDENTLY_REVIEWED','DEVELOPMENT_EXPOSED','SHARED_TEMPLATE_GROUP']+
                        (['DETECTION_NOT_RECOGNITION'] if any(s['kind']=='DETECTION' for s in scores) else ['NO_SUPPORTED_FIELD_SCORE'])})
        recommendations.append({'assessment_id':assessment.assessment_id,'recommendations':[r.model_dump(mode='json') for r in assessment.recommendations]})
        outcomes.append({'cohort':row['cohort'],'source_path':row['source_path'],'assessment_id':assessment.assessment_id,
            'artifact_id':artifact.artifact_id,'record_revision':assessment.record_revision,'artifact_path':str(path.relative_to(ROOT)),
            'artifact_sha256':digest(path.read_bytes()),'disposition':assessment.disposition,'review_required':True,
            'auto_accepted_fields':sum(f.auto_accepted for f in assessment.fields),'critical_completeness':assessment.critical_completeness.model_dump(mode='json'),
            'confidence':assessment.confidence.model_dump(mode='json'),'issue_counts':dict(Counter(i.code for i in assessment.issues)),
            'latency_ms':latencies[-1],'replay_and_idempotence':True})
    card={'version':'calibration-unavailable-dq-v1','date':'2026-10-13','status':'UNAVAILABLE','production_enabled':False,
        'fit_samples':0,'holdout_samples':0,'eligible_independent_samples':0,'insufficient_sample_groups':'ALL',
        'brier':None,'ece':None,'thresholds':policy.thresholds,'threshold_owner':policy.threshold_owner,
        'blocked_by':['DQ-01','DQ-02','DQ-03','DQ-05'],'reason':'Only generated development labels and detection scores; no independent frozen calibration/holdout.',
        'functional_implementation':'equal-width-smoothed-bins-v1; only validated within exact field/family/engine/preprocess/extractor scope.',
        'reference':'https://scikit-learn.org/stable/modules/calibration',
        'next_action':'Acquire permitted Vietnamese invoices, independent adjudication, grouped frozen FIT/HOLDOUT/TEST and an approved risk owner/target.'}
    summary={'date':'2026-10-13','gate_scope':'technical-functional-manual-review','production_accuracy_gate':'NOT_EVALUATED',
        'frozen_release_test_executed':False,'calibration_fit_on_development':False,'documents':len(outcomes),'pages':17,
        'review_rate':sum(r['review_required'] for r in outcomes)/len(outcomes),'accepted_fields':0,'accepted_field_precision':None,
        'false_acceptances_in_development':false_acceptances,'known_wrong_present_fields':wrong_present,
        'known_wrong_present_auto_accepted':false_acceptances,'eligible_calibration_samples':0,
        'latency_ms':{'minimum':min(latencies),'mean':sum(latencies)/len(latencies),'maximum':max(latencies),'scope':'quality repository only; excludes OCR; development fixture timing'},
        'score_rows':len(score_inventory),'score_kind_counts':dict(Counter(s['kind'] for row in score_inventory for s in row['raw_scores'])),
        'policy':policy.model_dump(mode='json'),'policy_sha256':sha(policy.model_dump(mode='json')),'outcomes':outcomes,
        'limitations':['Zero acceptance is a manual-only safety choice, not proof of production precision.',
            'Native/hybrid cohorts share logical documents and one synthetic template; counts are not independent samples.',
            'Validity checks establish shape/arithmetic only, not legal identity or OCR correctness.',
            'No live source fidelity or human-review proof is provisioned; XML branch is functionally tested only.',
            'Calibration/threshold/frozen production release remain unavailable until DQ conditions are met.']}
    for name,value in (('baseline_summary',summary),('calibration_card',card),('calibration_dataset_manifest',score_inventory),('review_recommendations',recommendations)):
        (PUBLIC/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ('documents','review_rate','accepted_fields','known_wrong_present_fields','eligible_calibration_samples','score_rows')}))

if __name__=='__main__': main()
