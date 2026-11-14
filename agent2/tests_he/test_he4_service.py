from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from experiments.he4.service import Worker,VERSION
from experiments.he4 import FRESH_ADMISSION
from experiments.he_inference.protocol import sign,public_hex,sha,canonical,HEUnavailable
from experiments.he_inference.http_common import ServiceError
from unittest.mock import patch


class WorkerSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.node=Ed25519PrivateKey.generate();self.other=Ed25519PrivateKey.generate();self.cloud=Ed25519PrivateKey.generate()
        self.grants=self.root/'grants.json';self.rows=[dict(tenant_id='t',company_id='C001',node_verify_key=public_hex(self.node),active=True)]
        self.write();self.worker=Worker(self.root/'worker',self.grants,self.cloud,{})
        self.addCleanup(self.worker.close)

    def write(self):self.grants.write_text(json.dumps(dict(version='he-worker-grants/1.0.0',grants=self.rows)))
    def packet(self,fields,**overrides):
        p=dict(version=VERSION,tenant_id='t',company_id='C001',node_verify_key=public_hex(self.node),expires_at=int(time.time())+60,**fields);p.update(overrides);return sign(p,self.node)

    def test_signed_upload_scope_replay_and_revocation(self):
        raw=b'ciphertext';fields=dict(sha256=sha(raw),size=len(raw),purpose='ciphertext');packet=self.packet(fields)
        first=self.worker.upload(packet,len(raw),io.BytesIO(raw));self.assertEqual(first,self.worker.upload(packet,len(raw),io.BytesIO(raw)))
        with self.assertRaises(ServiceError):self.worker.upload(self.packet(fields,company_id='C002'),len(raw),io.BytesIO(raw))
        self.rows[0]['active']=False;self.write()
        with self.assertRaises(ServiceError):self.worker.upload(packet,len(raw),io.BytesIO(raw))

    def test_plaintext_extra_fields_signature_and_expiry_rejected(self):
        fields=dict(sha256=sha(b'x'),size=1,purpose='ciphertext')
        for packet in (self.packet(dict(fields,plaintext=[1,2])),self.packet(fields,expires_at=0),sign(self.packet(fields)['payload'],self.other)):
            with self.subTest(packet=packet),self.assertRaises((ServiceError,HEUnavailable)):self.worker.upload(packet,1,io.BytesIO(b'x'))
        self.assertFalse(list(self.worker.blobs.root.glob('*/*')))

    def test_unknown_circuit_is_rejected_before_native_loading(self):
        fields=dict(profile='rules',circuit_sha256='0'*64,evaluation_keys_sha256='1'*64,arguments_sha256=['2'*64]*6,session_id='s',nonce='n')
        with self.assertRaises(ServiceError) as error:self.worker.score(self.packet(fields))
        self.assertEqual(error.exception.code,'HE4_CIRCUIT_INCOMPATIBLE')

    def test_blob_download_does_not_cross_node_scope(self):
        raw=b'ciphertext';fields=dict(sha256=sha(raw),size=len(raw),purpose='ciphertext');self.worker.upload(self.packet(fields),len(raw),io.BytesIO(raw))
        self.rows.append(dict(tenant_id='t',company_id='C001',node_verify_key=public_hex(self.other),active=True));self.write()
        packet=sign(dict(self.packet(dict(sha256=sha(raw)))['payload'],node_verify_key=public_hex(self.other)),self.other)
        with self.assertRaises(ServiceError):self.worker.download(packet)

    def admitted(self):
        self.worker.builds['statistics']=(self.root/'program','c'*64)
        blobs=[]
        for raw,purpose in ((b'public keys','public_evaluation_keys'),(b'ciphertext','ciphertext')):
            self.worker.upload(self.packet(dict(sha256=sha(raw),size=len(raw),purpose=purpose)),len(raw),io.BytesIO(raw));blobs.append(sha(raw))
        packet=self.packet(dict(profile='statistics',circuit_sha256='c'*64,evaluation_keys_sha256=blobs[0],arguments_sha256=[blobs[1]],session_id='admitted',nonce='one'))
        self.worker.slots.acquire();self.addCleanup(self.worker.slots.release)
        with self.assertRaises(ServiceError) as error:self.worker.score(packet)
        self.assertEqual(error.exception.code,'WORKER_BUSY')
        return packet

    def test_fresh_resume_can_only_continue_exact_previously_admitted_request(self):
        original=self.admitted();future=time.time()+301
        with patch('experiments.he4.service.time.time',return_value=future):
            with self.assertRaises(ServiceError) as error:self.worker.score(original)
            self.assertEqual(error.exception.code,'HE4_EXPIRED')
            outer=self.packet(dict(request=original))
            with self.assertRaises(ServiceError) as error:self.worker.resume(outer)
            self.assertEqual(error.exception.code,'WORKER_BUSY')
            changed=sign(dict(original['payload'],nonce='never-admitted'),self.node)
            with self.assertRaises(ServiceError) as error:self.worker.resume(self.packet(dict(request=changed)))
            self.assertEqual(error.exception.code,'HE4_REQUEST_NOT_ADMITTED')

    def test_resume_does_not_bypass_current_grant_or_owner(self):
        original=self.admitted();self.rows[0]['active']=False;self.write()
        with self.assertRaises(ServiceError):self.worker.resume(self.packet(dict(request=original)))

    def test_attempt_setup_io_failure_does_not_leave_permanent_running_claim(self):
        original=self.admitted();self.worker.slots.release()
        with patch.object(Path,'hardlink_to',side_effect=OSError('fixture disk unavailable')):
            with self.assertRaises(ServiceError) as error:self.worker.resume(self.packet(dict(request=original)))
        self.assertEqual(error.exception.code,'HE4_STORAGE_UNAVAILABLE');self.assertEqual(self.worker.active,0)
        with self.worker.store.transaction() as conn:row=conn.execute('SELECT state FROM jobs').fetchone()
        self.assertEqual(row['state'],'retryable');self.assertFalse(list(self.worker.state.glob('attempt_*')))
        self.worker.slots.acquire()  # balance admitted() cleanup

    def unadmitted_expired(self):
        self.worker.builds['statistics']=(self.root/'program','c'*64)
        blobs=[]
        for raw,purpose in ((b'public keys','public_evaluation_keys'),(b'ciphertext','ciphertext')):
            self.worker.upload(self.packet(dict(sha256=sha(raw),size=len(raw),purpose=purpose)),len(raw),io.BytesIO(raw));blobs.append(sha(raw))
        return self.packet(dict(profile='statistics',circuit_sha256='c'*64,evaluation_keys_sha256=blobs[0],arguments_sha256=[blobs[1]],session_id='unreceived',nonce='one'),expires_at=int(time.time())-7*3600)

    def fresh_admission(self,original,**overrides):
        return self.packet(dict(request=original,purpose=FRESH_ADMISSION),**overrides)

    @staticmethod
    def fake_native(command,**kwargs):
        # Protocol fixture only; actual HE parity runs in a separate HTTP test.
        root=Path(command[command.index('--request')+1]);(root/'result.cipher').write_bytes(b'fake native output')

    def test_fresh_admission_keeps_exact_expired_packet_and_cached_result(self):
        original=self.unadmitted_expired()
        with self.assertRaises(ServiceError) as error:self.worker.score(original)
        self.assertEqual(error.exception.code,'HE4_EXPIRED')
        with self.assertRaises(ServiceError) as error:self.worker.resume(self.packet(dict(request=original)))
        self.assertEqual(error.exception.code,'SESSION_NOT_REGISTERED')
        with patch('experiments.he4.service.subprocess.run',side_effect=self.fake_native) as native:
            first=self.worker.admit(self.fresh_admission(original))
            self.assertEqual(first,self.worker.admit(self.fresh_admission(original,expires_at=int(time.time())+120)))
            self.assertEqual(first,self.worker.resume(self.packet(dict(request=original))))
            self.assertEqual(native.call_count,1)
        self.assertEqual(first['payload']['request_sha256'],sha(canonical(original)))
        with self.worker.store.transaction() as conn:rows=conn.execute('SELECT session,nonce,state,generation FROM jobs').fetchall()
        self.assertEqual([tuple(r) for r in rows],[('unreceived','one','done',1)])

    def test_admission_requires_fresh_distinct_signed_capability(self):
        original=self.unadmitted_expired()
        for packet in (self.packet(dict(request=original)),self.packet(dict(request=original,purpose='wrong')),self.fresh_admission(original,expires_at=int(time.time())-1),sign(self.fresh_admission(original)['payload'],self.other)):
            with self.subTest(packet=packet),self.assertRaises((ServiceError,HEUnavailable)):self.worker.admit(packet)
        with self.assertRaises(ServiceError):self.worker.resume(self.fresh_admission(original))
        with self.worker.store.transaction() as conn:self.assertEqual(conn.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_admission_cannot_cross_owner_or_revoked_grant(self):
        original=self.unadmitted_expired()
        self.rows.append(dict(tenant_id='t',company_id='C002',node_verify_key=public_hex(self.node),active=True));self.write()
        with self.assertRaises(ServiceError) as error:self.worker.admit(self.fresh_admission(original,company_id='C002'))
        self.assertEqual(error.exception.code,'HE4_ADMISSION_OWNER')
        self.rows[0]['active']=False;self.write()
        with self.assertRaises(ServiceError):self.worker.admit(self.fresh_admission(original))
        with self.worker.store.transaction() as conn:self.assertEqual(conn.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_fresh_admission_does_not_replace_admitted_nonce_hash(self):
        original=self.unadmitted_expired()
        with patch('experiments.he4.service.subprocess.run',side_effect=self.fake_native) as native:
            receipt=self.worker.admit(self.fresh_admission(original));raw=b'other ciphertext'
            self.worker.upload(self.packet(dict(sha256=sha(raw),size=len(raw),purpose='ciphertext')),len(raw),io.BytesIO(raw))
            changed=sign(dict(original['payload'],arguments_sha256=[sha(raw)]),self.node)
            with self.assertRaises(ServiceError) as error:self.worker.admit(self.fresh_admission(changed))
            self.assertEqual(error.exception.code,'REQUEST_NONCE_CONFLICT')
            self.assertEqual(receipt,self.worker.resume(self.packet(dict(request=original))));self.assertEqual(native.call_count,1)

    def test_fresh_admission_rejects_tampered_inner_and_wrong_build(self):
        original=self.unadmitted_expired();bad=deepcopy(original);bad['payload']['nonce']='tampered'
        with self.assertRaises(HEUnavailable):self.worker.admit(self.fresh_admission(bad))
        changed=sign(dict(original['payload'],circuit_sha256='0'*64),self.node)
        with self.assertRaises(ServiceError) as error:self.worker.admit(self.fresh_admission(changed))
        self.assertEqual(error.exception.code,'HE4_CIRCUIT_INCOMPATIBLE')

    def test_http_fresh_admission_after_seven_hour_pause(self):
        import threading
        from experiments.he4.service import make_server
        from experiments.he_inference.http_common import post
        original=self.unadmitted_expired();server=make_server(0,self.worker)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(server.server_port)
        try:
            with self.assertRaises(ServiceError) as error:post(url,'/v1/evaluate',original)
            self.assertEqual(error.exception.code,'HE4_EXPIRED')
            with self.assertRaises(ServiceError) as error:post(url,'/v1/resume',self.packet(dict(request=original)))
            self.assertEqual(error.exception.code,'SESSION_NOT_REGISTERED')
            with patch('experiments.he4.service.subprocess.run',side_effect=self.fake_native) as native:
                first=post(url,'/v1/admit',self.fresh_admission(original))
                self.assertEqual(first,post(url,'/v1/results',self.packet(dict(session_id='unreceived',nonce='one',request_sha256=sha(canonical(original))))))
                self.assertEqual(first,post(url,'/v1/admit',self.fresh_admission(original)));self.assertEqual(native.call_count,1)
        finally:server.shutdown();server.server_close();thread.join(5)


if __name__=='__main__':unittest.main()
