from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile
import time
import shutil

from .models import IngestionError


class StagedUpload:
    def __init__(self,settings):
        self.settings=settings; self.size=0; self.hash=hashlib.sha256(); self.header=b''
        settings.staging_directory.mkdir(parents=True,exist_ok=True)
        descriptor,name=tempfile.mkstemp(prefix='capture-',suffix='.part',dir=settings.staging_directory)
        self.path=Path(name); self.stream=os.fdopen(descriptor,'wb')

    def write(self,chunk):
        if self.size+len(chunk)>self.settings.max_upload_bytes:
            raise IngestionError('LIMIT_EXCEEDED','Upload exceeds byte limit.',status=413)
        self.stream.write(chunk); self.hash.update(chunk); self.size+=len(chunk)
        if len(self.header)<4096:
            self.header=(self.header+chunk[:4096])[:4096]

    def finish(self):
        self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()
        if not self.size:
            raise IngestionError('EMPTY_FILE','Empty uploads are not accepted.',status=400)
        return self.hash.hexdigest()

    def close(self):
        self.stream.close()
        self.path.unlink(missing_ok=True)

    def __enter__(self): return self
    def __exit__(self,*args): self.close()


def cleanup_staging(settings, now=None):
    """Remove only old system-created .part files; never recurse or follow directories."""
    directory=settings.staging_directory.resolve()
    if not directory.exists(): return 0
    cutoff=(time.time() if now is None else now)-settings.staging_ttl_seconds
    removed=0
    for path in directory.glob('capture-*.part'):
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory):
            continue
        if path.stat().st_mtime<cutoff:
            try:
                path.unlink(); removed+=1
            except PermissionError:
                pass  # Active upload on Windows: leave for the next cleanup pass.
    for path in directory.glob('capture-worker-*'):
        if path.is_symlink() or not path.is_dir() or not path.resolve().is_relative_to(directory):
            continue
        if path.stat().st_mtime<cutoff:
            # This namespace contains only worker-owned scratch copies/renders;
            # raw and committed artifacts live in SQLite. TTL exceeds worker deadline.
            shutil.rmtree(path); removed+=1
    return removed
