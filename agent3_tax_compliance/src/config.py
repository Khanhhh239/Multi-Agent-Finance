import os
from pathlib import Path

from pydantic import Field, model_validator

from .domain.base import Contract
from .ingestion.models import AuthGrant, RoutePolicy

PROJECT = Path(__file__).resolve().parents[1]


class Settings(Contract):
    database_path: Path = PROJECT / 'data/foundation/capture.sqlite3'
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_upload_seconds: float = Field(default=60,gt=0,le=600)
    staging_directory: Path = PROJECT / 'data/foundation/staging'
    max_pages: int = Field(default=40,gt=0,le=1000)
    max_source_pixels: int = Field(default=32_000_000,gt=0)
    max_render_pixels: int = Field(default=8_000_000,gt=0)
    max_document_pixels: int = Field(default=40_000_000,gt=0)
    max_artifact_bytes: int = Field(default=64*1024*1024,gt=0)
    max_page_characters: int = Field(default=200_000,gt=0)
    render_dpi: int = Field(default=150,ge=72,le=300)
    worker_timeout_seconds: float = Field(default=45,gt=0,le=300)
    worker_memory_mb: int = Field(default=512,ge=64,le=4096)
    max_attempts: int = Field(default=3,ge=1,le=10)
    max_pending_ingestions: int = Field(default=50,ge=1)
    staging_ttl_seconds: int = Field(default=3600,ge=60)
    route_policy: RoutePolicy = RoutePolicy()
    auth_grants: tuple[AuthGrant,...] = ()

    @model_validator(mode='after')
    def separate_storage(self):
        path = self.database_path.resolve()
        legacy = (PROJECT / 'data/database').resolve()
        if path.is_relative_to(legacy) or path.suffix not in ('.sqlite3', '.sqlite'):
            raise ValueError('foundation database must be a separate .sqlite/.sqlite3 outside legacy database directory')
        if self.staging_directory.resolve().is_relative_to(legacy):
            raise ValueError('staging must be separate from legacy database directory')
        if len({g.token_sha256 for g in self.auth_grants})!=len(self.auth_grants):
            raise ValueError('token grants must be unique')
        if self.staging_ttl_seconds<=max(self.worker_timeout_seconds,self.max_upload_seconds)+30:
            raise ValueError('staging TTL must exceed active upload/worker deadlines plus cleanup margin')
        return self

    @classmethod
    def from_env(cls):
        raw = os.environ.get('CAPTURE_DATABASE_PATH', 'data/foundation/capture.sqlite3')
        path = Path(raw)
        if not path.is_absolute():
            path = PROJECT / path
        import json
        staging=Path(os.environ.get('CAPTURE_STAGING_DIRECTORY','data/foundation/staging'))
        if not staging.is_absolute():
            staging=PROJECT/staging
        return cls(database_path=path,staging_directory=staging,
                   max_upload_bytes=int(os.environ.get('CAPTURE_MAX_UPLOAD_BYTES',20*1024*1024)),
                   max_pages=int(os.environ.get('CAPTURE_MAX_PAGES',40)),
                   worker_timeout_seconds=float(os.environ.get('CAPTURE_WORKER_TIMEOUT_SECONDS',45)),
                   worker_memory_mb=int(os.environ.get('CAPTURE_WORKER_MEMORY_MB',512)),
                   auth_grants=json.loads(os.environ.get('CAPTURE_AUTH_GRANTS_JSON','[]')))
