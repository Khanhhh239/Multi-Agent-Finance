import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from experiments.he4.blob_store import BlobStore
from experiments.he_inference.http_common import ServiceError


class Blobs(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=BlobStore(self.tmp.name,limit=32,quota=40)
        self.scope=self.store.scope('t','C001','node');self.raw=b'ciphertext';self.sha=hashlib.sha256(self.raw).hexdigest()

    def test_scoped_idempotent_integrity(self):
        a=self.store.put(self.scope,self.sha,len(self.raw),io.BytesIO(self.raw))
        self.assertEqual(self.store.put(self.scope,self.sha,len(self.raw),io.BytesIO(self.raw)),a)
        self.assertEqual(self.store.get(self.scope,self.sha).read_bytes(),self.raw)
        with self.assertRaises(ServiceError):self.store.get(self.store.scope('t','C002','node'),self.sha)
        a.write_bytes(b'changed')
        with self.assertRaises(ServiceError):self.store.get(self.scope,self.sha)

    def test_limits_incomplete_checksum_and_path(self):
        for digest,size,raw in ((self.sha,33,b''),(self.sha,10,b'bad'),('0'*64,10,b'0123456789'),('../evil',1,b'x')):
            with self.assertRaises(ServiceError):self.store.put(self.scope,digest,size,io.BytesIO(raw))
        self.assertFalse(list(Path(self.tmp.name).glob('*/*')))

    def test_revocation_during_upload_does_not_commit(self):
        calls=[]
        def check():
            calls.append(1)
            if len(calls)>1:raise ServiceError(403,'REVOKED')
        with self.assertRaises(ServiceError):self.store.put(self.scope,self.sha,len(self.raw),io.BytesIO(self.raw),check)
        with self.assertRaises(ServiceError):self.store.get(self.scope,self.sha)
