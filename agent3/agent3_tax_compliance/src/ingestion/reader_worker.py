"""Entry point intentionally imports only stdlib before the parent installs limits."""
import json
from pathlib import Path
import sys


def main():
    request=json.loads(sys.stdin.buffer.readline())
    # This point is reached only after the parent's memory/job limit is installed.
    from src.config import Settings
    from src.ingestion.models import IngestionError
    from src.ingestion.pdf_reader import read_document
    output=Path(request['output'])
    try:
        settings=Settings(**request['settings'])
        result=read_document(Path(request['input']),output,request['identity'],settings)
        payload={'ok':True,'document':result.model_dump(mode='json')}
    except IngestionError as error:
        payload={'ok':False,'issue':error.issue.model_dump(mode='json')}
    except (MemoryError, OSError):
        payload={'ok':False,'issue':dict(code='WORKER_RESOURCE_ERROR',retryable=False,
                 message='Reader exhausted resources.',next_action='Reduce document size before submitting again.')}
    except Exception:
        payload={'ok':False,'issue':dict(code='CORRUPT_DOCUMENT',retryable=False,
                 message='Document could not be decoded.',next_action='Export a valid PDF/PNG/JPEG and submit again.')}
    encoded=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    if len(encoded)>request['settings']['max_artifact_bytes']:
        raise RuntimeError('manifest bound exceeded')
    (output/'result.json').write_bytes(encoded)


if __name__=='__main__': main()
