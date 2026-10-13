"""Explicit local administration/worker entrypoints; never runs on module import."""
import argparse
import json
import os
from pathlib import Path

from ..config import Settings
from ..domain.taxpayer import TaxpayerMaster
from .auth import authenticate
from .models import IngestionError
from .service import IngestionService
from .upload import cleanup_staging


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('provision','work','recover','cleanup'))
    parser.add_argument('--taxpayer-id')
    parser.add_argument('--master-file',type=Path)
    parser.add_argument('--limit',type=int,default=1)
    args=parser.parse_args()
    settings=Settings.from_env()
    token=os.environ.get('CAPTURE_WORKER_TOKEN','')
    try:
        ctx=authenticate(settings,'Bearer '+token if token else None)
        service=IngestionService(settings)
        if args.command=='cleanup':
            if 'ADMIN' not in ctx.permissions: raise PermissionError('admin required')
            print(json.dumps({'removed_staging_files':cleanup_staging(settings)})); return
        if args.command=='provision':
            if args.master_file is None: parser.error('--master-file is required')
            master=TaxpayerMaster.model_validate_json(args.master_file.read_text(encoding='utf-8'))
            ctx.require(master.tenant_id,master.taxpayer_id,'ADMIN')
            service.repository.base.initialize()
            service.repository.base.add_taxpayer(ctx,master)
            print(json.dumps({'status':'provisioned','revision':master.revision})); return
        if not args.taxpayer_id: parser.error('--taxpayer-id is required')
        ctx.require(ctx.tenant_id,args.taxpayer_id,'WRITE')
        service.repository.base.initialize()
        recovered=service.repository.recover_stored(ctx,args.taxpayer_id)
        if args.command=='recover':
            print(json.dumps({'requeued_stored':recovered,'pending':len(service.repository.pending(ctx,args.taxpayer_id))})); return
        if not 1<=args.limit<=100: parser.error('--limit must be between 1 and 100')
        results=[]
        for identifier in service.repository.pending(ctx,args.taxpayer_id)[:args.limit]:
            view=service.work_one(ctx,args.taxpayer_id,identifier)
            results.append({'ingestion_id':view.ingestion_id,'status':view.status,'issue':view.issue.code if view.issue else None})
        print(json.dumps({'requeued_stored':recovered,'results':results}))
    except IngestionError as error:
        print(json.dumps({'error':error.issue.model_dump(mode='json')})); raise SystemExit(1)
    except PermissionError:
        print(json.dumps({'error':'ACCESS_DENIED'})); raise SystemExit(1)


if __name__=='__main__': main()
