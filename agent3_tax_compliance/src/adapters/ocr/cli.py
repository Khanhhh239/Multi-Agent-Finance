import argparse
import json
import os
from pathlib import Path
from ...config import Settings
from ...ingestion.auth import authenticate
from ...ingestion.models import IngestionError
from .bridge import OCRBridge, config_key
from .protocol import OCRConfig, OCRError
from .registry import load_default_config


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--taxpayer-id',required=True)
    parser.add_argument('--ingestion-id',required=True)
    parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    settings=Settings.from_env()
    try:
        ctx=authenticate(settings,'Bearer '+os.environ.get('CAPTURE_WORKER_TOKEN',''))
        ctx.require(ctx.tenant_id,args.taxpayer_id,'WRITE')
        config=OCRConfig.model_validate_json(args.config.read_text(encoding='utf-8')) if args.config else load_default_config()
        bridge=OCRBridge(settings,config)
        bridge.repository.ingestion.base.initialize()
        result=bridge.work_one(ctx,args.taxpayer_id,args.ingestion_id)
        print(json.dumps({'ingestion_id':args.ingestion_id,'status':result['status'],'attempts':result['attempts'],
                          'config_key':config_key(bridge.config,bridge.client.inventory()['runtime_sha256']),
                          'result_available':result['result'] is not None}))
    except OCRError as error:
        print(json.dumps({'error':error.issue.model_dump(mode='json')})); raise SystemExit(1)
    except IngestionError as error:
        print(json.dumps({'error':error.issue.model_dump(mode='json')})); raise SystemExit(1)
    except PermissionError:
        print(json.dumps({'error':'ACCESS_DENIED'})); raise SystemExit(1)


if __name__=='__main__': main()
