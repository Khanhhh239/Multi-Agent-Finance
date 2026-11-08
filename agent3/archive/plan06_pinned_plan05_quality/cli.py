import argparse,json,os
from pathlib import Path
from ..config import Settings
from ..ingestion.auth import authenticate
from .policy import load_policy
from .repository import QualityRepository

def main():
    parser=argparse.ArgumentParser(description='Assess a persisted CFR revision; no OCR or tax verdict.')
    parser.add_argument('--taxpayer-id',required=True);parser.add_argument('--artifact-id',required=True)
    parser.add_argument('--revision',type=int);parser.add_argument('--policy',type=Path)
    args=parser.parse_args();settings=Settings.from_env()
    ctx=authenticate(settings,'Bearer '+os.environ.get('CAPTURE_WORKER_TOKEN',''))
    repo=QualityRepository(settings);repo.base.initialize()
    result=repo.work(ctx,args.taxpayer_id,args.artifact_id,load_policy(args.policy),args.revision)
    print(json.dumps({'assessment_id':result.assessment_id,'record_revision':result.record_revision,
        'disposition':result.disposition,'review_required':result.review_required,'auto_accept_enabled':False,
        'critical_completeness':result.critical_completeness.model_dump(mode='json'),'issue_codes':sorted({i.code for i in result.issues})}))

if __name__=='__main__': main()
