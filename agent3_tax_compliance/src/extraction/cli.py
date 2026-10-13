import argparse,json,os
from pathlib import Path
from ..config import Settings
from ..ingestion.auth import authenticate
from .contracts import ExtractionProfile
from .repository import ExtractionRepository

def main():
    parser=argparse.ArgumentParser(description='Extract CFR from a committed PLAN_03 result; does not run OCR.')
    parser.add_argument('--taxpayer-id',required=True);parser.add_argument('--ingestion-id',required=True)
    parser.add_argument('--ocr-config-key',required=True);parser.add_argument('--profile',type=Path)
    args=parser.parse_args();settings=Settings.from_env()
    ctx=authenticate(settings,'Bearer '+os.environ.get('CAPTURE_WORKER_TOKEN',''))
    profile=ExtractionProfile.model_validate_json(args.profile.read_text(encoding='utf-8')) if args.profile else ExtractionProfile()
    repo=ExtractionRepository(settings);repo.base.initialize()
    artifact=repo.work(ctx,args.taxpayer_id,args.ingestion_id,args.ocr_config_key,profile)
    print(json.dumps({'artifact_id':artifact.artifact_id,'record_id':artifact.record.record_id if artifact.record else None,
        'segmentation':artifact.segmentation.status,'review_required':True,'issues':[i.code for i in artifact.issues]}))

if __name__=='__main__': main()
