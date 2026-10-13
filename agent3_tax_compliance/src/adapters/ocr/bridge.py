import json
import tempfile
from pathlib import Path
from uuid import uuid4
from ...persistence.repository import digest
from .protocol import (OCRConfig, OCRBridgeRequest, NormalizedPageExtraction,
                       NormalizedDocumentExtraction, OCRError)
from .worker_client import WorkerClient
from .normalizer import normalize
from .layout_merge import merge
from .repository import OCRRepository
from .registry import load_default_config

STAMP=dict(config_version='ocr-layout-v1',creator='ocr-bridge',stage='ocr-layout')


def config_key(config,runtime_sha):
    implementations=''.join(digest(Path(__file__).with_name(name).read_bytes()) for name in
                            ('protocol.py','normalizer.py','layout_merge.py','bridge.py','worker_client.py','registry.py'))
    return digest((config.model_dump_json()+runtime_sha+'ocr-layout-v1'+implementations).encode())


def request_for(page,path,config,runtime_sha):
    return OCRBridgeRequest(**STAMP,request_id='ocr-'+uuid4().hex,
        source_id=page.source_id,document_id=page.document_id,page_id=page.page_id,page_index=page.page_index,
        image_hash=page.render_sha256,image_path=str(Path(path).resolve()),image_width=page.render_width,
        image_height=page.render_height,model_config_version=config.version,runtime_sha256=runtime_sha,
        timeout_seconds=config.timeout_seconds,model_id=config.model_id)


class OCRBridge:
    def __init__(self,settings,config=None,client=None):
        self.settings=settings; self.config=config or load_default_config()
        self.client=client or WorkerClient(model_id=self.config.model_id); self.repository=OCRRepository(settings)

    def work_one(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer)
        ctx.require(ctx.tenant_id,payer,'WRITE')
        doc=self.repository.ingestion.document(ctx,payer,identifier)
        runtime=self.client.inventory()['runtime_sha256']
        key=config_key(self.config,runtime)
        # Each page's process retry budget is included, plus startup/commit margin.
        lease=len(doc.pages)*self.config.timeout_seconds*self.config.max_attempts+30
        token=self.repository.claim(ctx,payer,identifier,key,lease,self.config.max_attempts)
        if token is None: return self.repository.get(ctx,payer,identifier,key)
        try:
            pages=[]
            for page in doc.pages:
                cache_key=digest((key+page.model_dump_json()).encode())
                cached=self.repository.cached(ctx,payer,cache_key)
                if cached:
                    pages.append(cached); continue
                raw_responses=()
                try:
                    if page.route=='UNSUPPORTED': raise OCRError('BAD_INPUT','Unsupported page route')
                    ocr_blocks=[]
                    if page.route in ('OCR','HYBRID'):
                        raw=self.repository.ingestion.render(ctx,payer,identifier,page.page_index)
                        if digest(raw)!=page.render_sha256: raise OCRError('BAD_INPUT','Render hash mismatch')
                        with tempfile.TemporaryDirectory(prefix='capture-ocr-page-') as directory:
                            path=Path(directory)/'page.png'; path.write_bytes(raw)
                            responses=self.client.run_batch([request_for(page,path,self.config,runtime)],self.config)
                        raw_responses=tuple(responses)
                        ocr_blocks=normalize(page,responses[0])
                    blocks=merge(page,ocr_blocks)
                    normalized=NormalizedPageExtraction(**STAMP,page_id=page.page_id,page_index=page.page_index,
                        image_hash=page.render_sha256,geometry=page.geometry,route=page.route,status='COMPLETE',
                        blocks=blocks,raw_responses=raw_responses,
                        table_candidates=tuple(b.block_id for b in blocks if b.evidence) if page.table_structure_present else ())
                    self.repository.cache(ctx,payer,cache_key,normalized)
                except OCRError as error:
                    normalized=NormalizedPageExtraction(**STAMP,page_id=page.page_id,page_index=page.page_index,
                        image_hash=page.render_sha256,geometry=page.geometry,route=page.route,status='FAILED',
                        raw_responses=raw_responses,issue=error.issue)
                pages.append(normalized)
            good=sum(p.status=='COMPLETE' for p in pages)
            result=NormalizedDocumentExtraction(**STAMP,tenant_id=doc.tenant_id,taxpayer_id=doc.taxpayer_id,
                taxpayer_master_revision=doc.taxpayer_master_revision,ingestion_id=identifier,
                source_id=doc.source_id,document_id=doc.document_id,input_sha256=doc.input_sha256,
                document_artifact_sha256=digest(doc.model_dump_json().encode()),runtime_sha256=runtime,
                ocr_config=self.config,status='COMPLETE' if good==len(pages) else 'PARTIAL' if good else 'FAILED',pages=tuple(pages))
            self.repository.finish(ctx,payer,identifier,key,token,result=result)
        except OCRError as error:
            self.repository.finish(ctx,payer,identifier,key,token,issue=error.issue)
        except Exception:
            self.repository.finish(ctx,payer,identifier,key,token,
                                   issue=OCRError('OCR_FAILED','Extraction could not complete').issue)
            raise
        return self.repository.get(ctx,payer,identifier,key)
