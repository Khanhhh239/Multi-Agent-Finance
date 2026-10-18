import hashlib
import json
import platform
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from ...ingestion.sandbox import run_bounded
from ...ingestion.models import IngestionError
from .protocol import OCRBridgeResponse, OCRError, correlate
from .registry import EngineRegistry, confined, adapter_config

_WORKER_SLOT=threading.BoundedSemaphore(1)


@contextmanager
def worker_slot(timeout=None):
    acquired=_WORKER_SLOT.acquire() if timeout is None else _WORKER_SLOT.acquire(timeout=timeout)
    if not acquired:raise OCRError('WORKER_TIMEOUT','OCR worker is busy; retry later',True)
    try:yield
    finally:_WORKER_SLOT.release()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class WorkerClient:
    def __init__(self, benchmark_root=None, model_id='tesseract', registry=None):
        self.root=Path(benchmark_root or Path(__file__).resolve().parents[4]/'data invoice/ocr_e2e_workflow').resolve()
        self.profile=(registry or EngineRegistry()).get(model_id)
        self.python=confined(self.root,self.profile.interpreter)
        self.executable=self.root/'tools/tesseract/tesseract.exe'
        self.languages=self.root/'tools/tesseract/tessdata'
        self._runtime=None
        self.metrics_history=[]

    def inventory(self):
        if self._runtime is not None: return self._runtime
        files=[self.python,self.python.parents[1]/'pyvenv.cfg']
        files.extend(confined(self.root,p) for p in (*self.profile.assets,*self.profile.source_files,
            'src/bridge_worker.py','src/adapters/__init__.py','src/adapters/base.py','src/contracts.py','src/utils.py'))
        if self.profile.adapter=='tesseract': files.extend(sorted((self.root/'tools/tesseract').glob('*.dll')))
        if any(not p.is_file() for p in files):
            raise OCRError('MODEL_UNAVAILABLE','Pinned interpreter, worker, executable or language data missing')
        try:
            probe=subprocess.run([str(self.python),'-c',
                "import sys,json,importlib.metadata as m; print(json.dumps({'python':sys.version.split()[0], **{k:m.version(k) for k in "+repr(list(self.profile.distributions))+"}}))"],
                capture_output=True,timeout=15,check=True)
            versions=json.loads(probe.stdout)
            if self.profile.adapter=='tesseract':
                engine=subprocess.run([str(self.executable),'--version'],capture_output=True,timeout=10,check=True)
                versions['tesseract']=engine.stdout.decode(errors='replace').splitlines()[0]
        except Exception:
            raise OCRError('MODEL_UNAVAILABLE','Runtime probe failed') from None
        # Pin installed Python package implementation, not just version labels.
        site=self.python.parents[1]/'Lib/site-packages'
        if self.profile.adapter=='tesseract':
            for package in ('PIL','pytesseract'):
                files.extend(sorted((site/package).rglob('*.py')))
                files.extend(sorted((site/package).rglob('*.pyd')))
        # Distribution metadata/RECORD pin the installed package inventory.
        # Large framework libraries are not rehashed on every page; local model
        # weights, model definitions and adapter implementations are hashed.
        for path in sorted(site.glob('*.dist-info')):
            for name in ('METADATA','RECORD'):
                if (path/name).is_file(): files.append(path/name)
        checksums={str(p.relative_to(self.root)).replace('\\','/'):sha(p.read_bytes()) for p in files}
        payload=dict(engine_versions=versions,files=checksums,profile=self.profile.model_dump(mode='json'))
        fingerprint=sha(json.dumps(payload,sort_keys=True).encode())
        self._runtime={**payload,'runtime_sha256':fingerprint,'platform':platform.platform(),
                       'processor':platform.processor(),'available':True}
        return self._runtime

    def verify_runtime(self):
        runtime=self.inventory()
        for name,expected in runtime['files'].items():
            path=self.root/name
            if not path.is_file() or sha(path.read_bytes())!=expected:
                raise OCRError('MODEL_UNAVAILABLE','Runtime files changed since inventory; restart worker client')

    def run_batch(self, requests, config, *, slot_timeout=None):
        runtime=self.inventory()
        if config.model_id!=self.profile.model_id:
            raise OCRError('PROTOCOL_ERROR','Client engine does not match OCR configuration')
        if not requests or len(requests)>64: raise OCRError('BAD_INPUT','Batch must contain 1..64 pages')
        for req in requests:
            if req.runtime_sha256!=runtime['runtime_sha256'] or req.model_config_version!=config.version or req.model_id!=config.model_id:
                raise OCRError('PROTOCOL_ERROR','Request runtime/config mismatch')
        self.verify_runtime()
        with worker_slot(slot_timeout), tempfile.TemporaryDirectory(prefix='capture-ocr-') as directory:
            output=Path(directory)/'responses.jsonl'
            engine_config=adapter_config(self.profile,self.root,config)
            payload=dict(config=engine_config,distributions=list(self.profile.distributions),requests_jsonl='\n'.join(r.model_dump_json() for r in requests),
                         output=str(output),max_output_bytes=config.max_output_bytes)
            last=None
            for attempt in range(config.max_attempts):
                try:
                    if output.exists(): output.unlink()
                    self.last_metrics=run_bounded([str(self.python),'-m','src.bridge_worker'],json.dumps(payload).encode(),
                                config.timeout_seconds*len(requests),config.memory_mb,self.root,
                                max_processes=self.profile.max_processes,environment=self.profile.environment)
                    if not output.is_file(): raise OCRError('WORKER_CRASH','Worker did not produce output')
                    if output.stat().st_size>config.max_output_bytes:
                        raise OCRError('OUTPUT_LIMIT','Response exceeds configured byte bound')
                    lines=output.read_bytes().splitlines()
                    if len(lines)!=len(requests): raise OCRError('PROTOCOL_ERROR','Missing or extra response lines')
                    responses=[OCRBridgeResponse.model_validate_json(line) for line in lines]
                    for req,response in zip(requests,responses):
                        correlate(req,response)
                        if response.issue: raise OCRError(response.issue.code,response.issue.message,response.issue.retryable)
                    self.metrics_history.append(self.last_metrics)
                    return [r.model_copy(update={'engine_versions':runtime['engine_versions']}) for r in responses]
                except IngestionError as exc:
                    code=('OUTPUT_LIMIT' if getattr(exc,'worker_exit_code',None)==3 else
                          'WORKER_TIMEOUT' if exc.issue.code=='WORKER_TIMEOUT' else 'WORKER_CRASH')
                    last=OCRError(code,
                                  'Bounded OCR worker did not complete',exc.issue.code=='WORKER_TIMEOUT')
                except OCRError as exc: last=exc
                except (ValueError,TypeError): last=OCRError('PROTOCOL_ERROR','Invalid worker response')
                except OSError: last=OCRError('TRANSIENT_IO','Unable to stage worker output',True)
                if not last.issue.retryable: break
            raise last
