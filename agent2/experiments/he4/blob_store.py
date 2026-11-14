"""Bounded streaming store for public evaluation keys and ciphertext only."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import threading
import uuid
from experiments.he_inference.http_common import ServiceError

HASH=re.compile('[a-f0-9]{64}\\Z')


class BlobStore:
    def __init__(self,root,limit=2*1024**3,quota=8*1024**3):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.limit=limit;self.quota=quota;self.lock=threading.Lock()

    def scope(self,tenant,company,node):return hashlib.sha256(f'{tenant}\x00{company}\x00{node}'.encode()).hexdigest()

    def path(self,scope,digest):
        if not HASH.fullmatch(scope) or not HASH.fullmatch(digest):raise ServiceError(400,'BLOB_ID')
        return self.root/scope/digest

    def put(self,scope,digest,size,stream,check=lambda:None):
        path=self.path(scope,digest)
        if type(size) is not int or not 0<size<=self.limit:raise ServiceError(413,'BLOB_LIMIT')
        # Serial uploads bound aggregate disk use, including incomplete files.
        if not self.lock.acquire(blocking=False):raise ServiceError(503,'UPLOAD_BUSY')
        temporary=None
        try:
            check();used=sum(p.stat().st_size for p in self.root.glob('*/*') if p.is_file())
            if used+size>self.quota and not path.exists():raise ServiceError(413,'BLOB_QUOTA')
            path.parent.mkdir(exist_ok=True);temporary=path.parent/('pending_'+uuid.uuid4().hex)
            h=hashlib.sha256();left=size
            with temporary.open('xb') as out:
                while left:
                    data=stream.read(min(left,1024*1024))
                    if not data:raise ServiceError(400,'BLOB_INCOMPLETE')
                    if len(data)>left:raise ServiceError(400,'BLOB_LENGTH')
                    out.write(data);h.update(data);left-=len(data)
                out.flush();os.fsync(out.fileno())
            if h.hexdigest()!=digest:raise ServiceError(422,'BLOB_CHECKSUM')
            check()
            if path.exists():
                if path.stat().st_size!=size or self.digest(path)!=digest:raise ServiceError(503,'BLOB_STORAGE_INTEGRITY')
                temporary.unlink();temporary=None
            else:os.replace(temporary,path);temporary=None
            return path
        finally:
            if temporary is not None and temporary.exists():temporary.unlink()
            self.lock.release()

    @staticmethod
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()

    def get(self,scope,digest):
        path=self.path(scope,digest)
        if not path.is_file():raise ServiceError(404,'BLOB_NOT_FOUND')
        if path.stat().st_size>self.limit or self.digest(path)!=digest:raise ServiceError(503,'BLOB_STORAGE_INTEGRITY')
        return path
