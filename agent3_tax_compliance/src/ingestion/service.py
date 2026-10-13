import hashlib
import json
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

from ..config import PROJECT
from ..domain.envelope import SourceEnvelope
from .detector import detect
from .models import DocumentArtifact, IngestionError, IngestionIssue
from .repository import IngestionRepository
from .sandbox import run_bounded

STAMP=dict(config_version='ingestion-v1',creator='ingestion-service',stage='upload')
WORKER_KEYS=('max_upload_bytes','max_pages','max_source_pixels','max_render_pixels','max_document_pixels',
             'max_artifact_bytes','max_page_characters','render_dpi','route_policy')


class IngestionService:
    def __init__(self,settings):
        self.settings=settings; self.repository=IngestionRepository(settings)

    def authorize_upload(self,ctx,payer,master_revision):
        ctx.require(ctx.tenant_id,payer,'WRITE'); ctx.require(ctx.tenant_id,payer,'READ')
        self.repository.base.initialize()
        try:
            return self.repository.base.taxpayer(ctx,payer,master_revision)
        except KeyError:
            raise IngestionError('NOT_FOUND','Selected taxpayer master revision is not provisioned.',status=404,
                                 next_action='Have an administrator provision the taxpayer master first.') from None

    def accept_staged(self,ctx,payer,master_revision,key,staged,mime,filename=None,*,enqueue=True):
        self.authorize_upload(ctx,payer,master_revision)
        sha=staged.finish()
        source_format,_=detect(staged.header,mime,filename)
        options=self.settings.model_dump(mode='json',include=set(WORKER_KEYS))
        fingerprint=hashlib.sha256(json.dumps(dict(sha256=sha,master_revision=master_revision,
            source_format=source_format.value,reader_version='reader-v1',geometry_version='geometry-v1',
            configuration=options),sort_keys=True).encode()).hexdigest()
        identifier='ingestion-'+uuid4().hex
        envelope=SourceEnvelope(**STAMP,tenant_id=ctx.tenant_id,taxpayer_id=payer,taxpayer_master_revision=master_revision,
            request_id='request-'+uuid4().hex,source_id='source-'+uuid4().hex,sha256=sha,size_bytes=staged.size,
            declared_mime=mime.split(';',1)[0].strip().lower(),detected_format=source_format,adapter_version='reader-v1',profile_version='ingestion-v1')
        # File is read into bounded memory only AFTER streaming, size limit and SHA validation.
        raw=staged.path.read_bytes()
        view=self.repository.accept(ctx,payer,key,fingerprint,envelope,raw,identifier,'document-'+uuid4().hex)
        return self.repository.enqueue(ctx,payer,view.ingestion_id) if enqueue else view

    def work_one(self,ctx,payer,identifier):
        ctx.require(ctx.tenant_id,payer,'READ')
        ctx.require(ctx.tenant_id,payer,'WRITE')
        token=self.repository.claim(ctx,payer,identifier)
        if token is None: return self.repository.get(ctx,payer,identifier)
        view=self.repository.get(ctx,payer,identifier)
        try:
            envelope,raw=self.repository.base.source(ctx,payer,view.source_id)
            settings=self.settings.model_dump(mode='json',include=set(WORKER_KEYS))
            identity=dict(tenant_id=ctx.tenant_id,taxpayer_id=payer,taxpayer_master_revision=envelope.taxpayer_master_revision,
                ingestion_id=identifier,source_id=view.source_id,document_id=view.document_id,
                input_sha256=view.input_sha256,source_format=envelope.detected_format.value)
            self.settings.staging_directory.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='capture-worker-',dir=self.settings.staging_directory) as temp:
                directory=Path(temp); input_path=directory/'raw.bin'; input_path.write_bytes(raw)
                request=dict(input=str(input_path),output=str(directory),identity=identity,settings=settings)
                payload=(json.dumps(request)+'\n').encode()
                run_bounded([sys.executable,'-m','src.ingestion.reader_worker'],payload,
                            self.settings.worker_timeout_seconds,self.settings.worker_memory_mb,PROJECT)
                result_path=directory/'result.json'
                if not result_path.is_file() or result_path.stat().st_size>self.settings.max_artifact_bytes:
                    raise IngestionError('WORKER_RESOURCE_ERROR','Worker result is missing or exceeds its bound.')
                result=json.loads(result_path.read_text(encoding='utf-8'))
                if not result['ok']:
                    issue=IngestionIssue.model_validate(result['issue'])
                    self.repository.fail(ctx,payer,identifier,token,issue)
                else:
                    document=DocumentArtifact.model_validate(result['document'])
                    paths=[directory/f'page-{page.page_index}.png' for page in document.pages]
                    if len(paths)>self.settings.max_pages or sum(p.stat().st_size for p in paths)>self.settings.max_artifact_bytes:
                        raise IngestionError('LIMIT_EXCEEDED','Worker output exceeded configured artifact bounds.')
                    self.repository.complete(ctx,payer,identifier,token,document,[p.read_bytes() for p in paths])
        except IngestionError as error:
            self.repository.fail(ctx,payer,identifier,token,error.issue)
        except Exception:
            self.repository.fail(ctx,payer,identifier,token,IngestionIssue(code='PROCESSING_ERROR',retryable=True,
                message='Ingestion processing failed.',next_action='Inspect configuration/storage and retry within the attempt limit.'))
        return self.repository.get(ctx,payer,identifier)
