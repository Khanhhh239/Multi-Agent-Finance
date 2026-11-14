"""Enterprise-only streaming authenticated storage for large HE private keys.

The wrapping key is supplied by the enterprise protected-key provider; this
module never generates a replacement wrapping key or writes it to disk.
"""
import io
import os
from pathlib import Path
import struct
import uuid
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from experiments.he_inference.protocol import canonical

MAGIC=b'A2HE4K01'
MAX_PRIVATE=2*1024**3


def seal(path,key,binding,raw):
    path=Path(path)
    if len(key)!=32 or not isinstance(raw,bytes) or not 0<len(raw)<=MAX_PRIVATE:raise ValueError('private key limit')
    if path.exists():raise ValueError('private context is immutable')
    header=canonical(dict(version='he4-private-context/0.1.0',binding=binding,size=len(raw)))
    if len(header)>4096:raise ValueError('binding limit')
    nonce=os.urandom(12);prefix=MAGIC+struct.pack('>I',len(header))+header+nonce
    encryptor=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor();encryptor.authenticate_additional_data(prefix)
    temporary=path.with_name(path.name+'.pending-'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(prefix)
            for start in range(0,len(raw),1024*1024):stream.write(encryptor.update(raw[start:start+1024*1024]))
            stream.write(encryptor.finalize());stream.write(encryptor.tag);stream.flush();os.fsync(stream.fileno())
        # Atomic creation with no replacement; concurrent provisioners cannot
        # silently rotate a company key. Caller owns its private directory.
        path.hardlink_to(temporary);temporary.unlink()
    finally:
        if temporary.exists():temporary.unlink()


def open_private(path,key,binding):
    import json
    path=Path(path)
    if len(key)!=32 or path.stat().st_size>MAX_PRIVATE+8192:raise ValueError('private context limit')
    with path.open('rb') as stream:
        if stream.read(8)!=MAGIC:raise ValueError('context format')
        length=struct.unpack('>I',stream.read(4))[0]
        if not 0<length<=4096:raise ValueError('context header')
        header=stream.read(length);nonce=stream.read(12);meta=json.loads(header)
        if set(meta)!={'version','binding','size'} or meta['version']!='he4-private-context/0.1.0' or meta['binding']!=binding or type(meta['size']) is not int or not 0<meta['size']<=MAX_PRIVATE:raise ValueError('context binding')
        size=meta['size'];prefix=MAGIC+struct.pack('>I',length)+header+nonce
        if path.stat().st_size!=len(prefix)+size+16:raise ValueError('context length')
        stream.seek(-16,2);tag=stream.read(16);stream.seek(len(prefix))
        decryptor=Cipher(algorithms.AES(key),modes.GCM(nonce,tag)).decryptor();decryptor.authenticate_additional_data(prefix)
        plain=bytearray();left=size
        while left:
            chunk=stream.read(min(left,1024*1024))
            if not chunk:raise ValueError('truncated context')
            plain.extend(decryptor.update(chunk));left-=len(chunk)
        # No native key parser receives bytes before tag verification succeeds.
        plain.extend(decryptor.finalize());return bytes(plain)
