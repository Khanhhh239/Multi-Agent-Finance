"""Local import only: document hashes bind attestations to bytes, not legal truth."""
import hashlib
import os
import tempfile
from pathlib import Path, PureWindowsPath


def verify_files(dossier,root):
    root=Path(root).resolve(strict=True)
    total=0
    for doc in dossier.documents:
        relative=Path(doc.relative_path)
        if relative.is_absolute() or PureWindowsPath(doc.relative_path).anchor or '..' in relative.parts:
            raise ValueError('evidence path must stay inside evidence root')
        try:path=(root/relative).resolve(strict=True)
        except OSError:raise ValueError('evidence file unavailable') from None
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('unsafe evidence path')
        if path.stat().st_size>64*1024*1024:raise ValueError('evidence file too large')
        total+=path.stat().st_size
        if total>128*1024*1024:raise ValueError('evidence dossier too large')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=doc.sha256:raise ValueError('evidence bytes changed')
    return tuple(d.evidence_id for d in dossier.documents)


def store_files(dossier,root,destination):
    """Retain the verified bytes, not merely a mutable external file path."""
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for doc in dossier.documents:
        target=destination/doc.sha256
        if target.exists():
            if file_sha(target)!=doc.sha256:raise ValueError('stored evidence integrity failure')
            continue
        with tempfile.NamedTemporaryFile(dir=destination,delete=False) as stream:
            temporary=Path(stream.name)
            try:
                with (Path(root)/doc.relative_path).open('rb') as source:
                    size=0
                    while block:=source.read(1024*1024):
                        size+=len(block)
                        if size>64*1024*1024:raise ValueError('evidence grew during import')
                        stream.write(block)
            except BaseException:
                stream.close();temporary.unlink(missing_ok=True);raise
        try:
            if file_sha(temporary)!=doc.sha256:raise ValueError('evidence changed during import')
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)


def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def verify_stored(dossier,destination):
    for doc in dossier.documents:
        try:pin=file_sha(Path(destination)/doc.sha256)
        except OSError:raise ValueError('stored evidence unavailable') from None
        if pin!=doc.sha256:raise ValueError('stored evidence integrity failure')
