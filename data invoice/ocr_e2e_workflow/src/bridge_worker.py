"""OCR bridge JSONL worker. Only benchmark src is on sys.path; no app imports.

The parent installs process limits before supplying stdin. One adapter per batch.
The response file is bounded while writing and lives in a private parent temp dir.
"""
import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone


def main():
    wire=sys.stdin.buffer.read(1024*1024+1)
    if len(wire)>1024*1024: return 2
    payload=json.loads(wire)
    config=payload['config']
    requests=[json.loads(line) for line in payload['requests_jsonl'].splitlines() if line]
    if not 1<=len(requests)<=64: return 2
    from src.adapters import create_adapter
    import importlib.metadata as metadata
    from PIL import Image
    versions={name:metadata.version(name) for name in payload['distributions']}
    versions['python']=sys.version.split()[0]
    adapter=None
    initialization_failed=False
    try:
        adapter=create_adapter(config,requests[0]['request_id'])
    except Exception as exc:
        initialization_failed=True
        initialization_kind=type(exc).__name__
    written=0
    with Path(payload['output']).open('wb') as output:
        for req in requests:
            response={name:req[name] for name in ('request_id','source_id','document_id','page_id',
                      'page_index','image_hash','model_config_version','runtime_sha256')}
            response.update(schema_version='1.0.0',config_version=req['config_version'],
                            creator='benchmark-bridge-worker',stage='ocr',
                            created_at=datetime.now(timezone.utc).isoformat(),
                            protocol_version='ocr-bridge-1',engine_versions=versions,result=None,issue=None)
            issue=None
            if req.get('protocol_version')!='ocr-bridge-1' or req.get('accepted_result_version')!='1.1':
                issue=('PROTOCOL_ERROR','Unsupported protocol or result version',False)
            elif initialization_failed:
                issue=('MODEL_UNAVAILABLE','Adapter initialization failed: '+initialization_kind,False)
            else:
                try:
                    path=Path(req['image_path'])
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=req['image_hash']:
                        raise ValueError('hash')
                    with Image.open(path) as image:
                        if image.size!=(req['image_width'],req['image_height']): raise ValueError('size')
                    adapter.run_id=req['request_id']
                    result=adapter.predict(path).to_dict()
                    if config['adapter']=='ppocrv6_vietocr':
                        result['metadata']['confidence_semantics']=('UNAVAILABLE' if config.get('recognition_only') else 'DETECTION_SCORE_NOT_TEXT_CONFIDENCE')
                    if result['error']:
                        issue=('OCR_FAILED','Adapter inference failed',False)
                    elif result['metadata'].get('recognition_errors',0):
                        issue=('OCR_FAILED','One or more text crops failed recognition',False)
                    else: response['result']=result
                except OSError:
                    issue=('TRANSIENT_IO','Unable to read staged page',True)
                except Exception:
                    issue=('BAD_INPUT','Invalid page identity or image',False)
            if issue:
                response['issue']=dict(code=issue[0],message=issue[1],retryable=issue[2])
            line=(json.dumps(response,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
            written+=len(line)
            if written>payload['max_output_bytes']: return 3
            output.write(line); output.flush()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
