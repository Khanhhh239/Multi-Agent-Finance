from pathlib import PurePosixPath, PureWindowsPath
from ..domain.envelope import SourceFormat
from .models import IngestionError

SUPPORTED={SourceFormat.PDF:('application/pdf',{'.pdf'}),
           SourceFormat.IMAGE:('image/png',{'.png'})}


def detect(header: bytes, mime: str, filename: str | None = None):
    """No archive extraction or XML entity processing during signature detection."""
    if not header:
        raise IngestionError('EMPTY_FILE','Empty uploads are not accepted.',status=400)
    if filename and (len(filename)>128 or PurePosixPath(filename).name!=filename
                     or PureWindowsPath(filename).name!=filename or ':' in filename or '\x00' in filename
                     or filename in ('.','..')):
        raise IngestionError('FORMAT_MISMATCH','Filename must be a simple basename.',status=400)
    if header.startswith(b'%PDF-'):
        detected,actual,suffixes=SourceFormat.PDF,'application/pdf',{'.pdf'}
    elif header.startswith(b'\x89PNG\r\n\x1a\n'):
        detected,actual,suffixes=SourceFormat.IMAGE,'image/png',{'.png'}
    elif header.startswith(b'\xff\xd8\xff'):
        detected,actual,suffixes=SourceFormat.IMAGE,'image/jpeg',{'.jpg','.jpeg'}
    else:
        if header.startswith((b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08')):
            label='ZIP/XLSX container'
        elif header.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
            label='OLE2/XLS container'
        elif header.lstrip(b'\xef\xbb\xbf \t\r\n').startswith(b'<'):
            label=SourceFormat.UNKNOWN_XML.value
        else:
            label=SourceFormat.UNKNOWN.value
        raise IngestionError('UNSUPPORTED_FORMAT',f'Unsupported signature: {label}.',status=415,
                             next_action='Submit PDF, PNG or JPEG; other adapters belong to later plans.')
    declared=mime.split(';',1)[0].strip().lower()
    if declared not in (actual,'application/octet-stream'):
        raise IngestionError('FORMAT_MISMATCH','Declared MIME does not match signature.',status=415)
    if filename and PurePosixPath(filename).suffix.lower() not in suffixes:
        raise IngestionError('FORMAT_MISMATCH','Filename extension does not match signature.',status=415)
    return detected,actual
