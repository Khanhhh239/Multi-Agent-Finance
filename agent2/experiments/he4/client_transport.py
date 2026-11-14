"""Enterprise-side streaming transport. Only public keys/ciphertexts uploaded."""
import base64
import http.client
from pathlib import Path
import time
from experiments.he_inference.http_common import ServiceError,decode,worker_address,post
from experiments.he_inference.protocol import canonical,sign,verify,public_hex,sha
from .blob_store import BlobStore
from . import VERSION


def envelope(scope,key,fields):
    if len(scope.company_ids)!=1:raise ValueError('single-company scope required')
    return sign(dict(version=VERSION,tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids)),node_verify_key=public_hex(key),expires_at=int(time.time())+300,**fields),key)


def upload(url,scope,key,worker_key,path,purpose):
    path=Path(path);digest=BlobStore.digest(path);size=path.stat().st_size
    try:
        existing=verify(post(url,'/v1/blobs/check',envelope(scope,key,dict(sha256=digest))),worker_key)
        if existing!=dict(status='stored',sha256=digest,size=size,tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids))):raise ValueError('existing blob receipt mismatch')
        return digest
    except ServiceError as error:
        if error.code!='BLOB_NOT_FOUND':raise
    packet=envelope(scope,key,dict(sha256=digest,size=size,purpose=purpose))
    host,port=worker_address(url);conn=http.client.HTTPConnection(host,port,timeout=300)
    try:
        conn.putrequest('POST','/v1/blobs');conn.putheader('Content-Type','application/octet-stream');conn.putheader('Content-Length',str(size));conn.putheader('X-HE-Envelope',base64.b64encode(canonical(packet)).decode());conn.endheaders()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):conn.send(chunk)
        response=conn.getresponse();value=decode(response.read(16385))
        if response.status!=200:raise ServiceError(response.status,'HE4_UPLOAD_REJECTED')
        p=verify(value,worker_key)
        if p!=dict(status='stored',sha256=digest,tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids))):raise ValueError('blob receipt mismatch')
        return digest
    except (OSError,http.client.HTTPException):raise ServiceError(503,'WORKER_CONNECTION_UNAVAILABLE') from None
    finally:conn.close()


def download(url,scope,key,digest,output):
    host,port=worker_address(url);conn=http.client.HTTPConnection(host,port,timeout=120)
    try:
        conn.request('POST','/v1/blobs/read',canonical(envelope(scope,key,dict(sha256=digest))),{'Content-Type':'application/json'})
        response=conn.getresponse()
        if response.status!=200:raise ServiceError(response.status,'HE4_DOWNLOAD_REJECTED')
        length=response.getheader('Content-Length','')
        if not length.isascii() or not length.isdigit() or not 0<int(length)<=64*1024**2:raise ValueError('result length')
        raw=response.read(int(length)+1)
        if len(raw)!=int(length) or sha(raw)!=digest:raise ValueError('result integrity')
        Path(output).write_bytes(raw)
    except (OSError,http.client.HTTPException):raise ServiceError(503,'WORKER_CONNECTION_UNAVAILABLE') from None
    finally:conn.close()
