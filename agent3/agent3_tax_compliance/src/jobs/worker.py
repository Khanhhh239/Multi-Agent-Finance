"""python -m src.jobs.worker --taxpayer-id ... --job-id ... (Bearer in CAPTURE_WORKER_TOKEN)."""
import argparse,os,json
from ..config import Settings
from ..ingestion.auth import authenticate
from .service import CaptureJobs
from ..extraction.contracts import ExtractionProfile

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--taxpayer-id',required=True);parser.add_argument('--job-id',required=True)
    parser.add_argument('--number-locale',choices=('AUTO','VI','EN'),default='AUTO',help='Explicit decimal/group separator convention; AUTO preserves ambiguity.')
    args=parser.parse_args();settings=Settings.from_env();ctx=authenticate(settings,'Bearer '+os.environ.get('CAPTURE_WORKER_TOKEN',''))
    result=CaptureJobs(settings).work_one(ctx,args.taxpayer_id,args.job_id,profile=ExtractionProfile(number_locale=args.number_locale))
    print(json.dumps({k:result.get(k) for k in ('job_id','state','attempts','error_code','record_id')}))
    return 0 if result['state']=='REVIEW' else 1
if __name__=='__main__': raise SystemExit(main())
