"""Durable ciphertext SGD chain. Checkpoint weights and cursor in one transaction.

The output ciphertext of update N is input to N+1, including epoch boundaries.
At most one process owns this state; status polling does not wait for FHE work.
Crash before commit may recompute the same update, never reset to clear weights.
"""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
from . import PROFILE, TARGET
from . import batch_protocol as p
from .protocol import require, fields, canonical, sha, verify, sign, strict_json, blob, encode


class BatchCloudStore:
    def __init__(self, root, grants, worker_key, build_sha256, evaluate, *, max_updates=4):
        require(type(max_updates) is int and 1 <= max_updates <= 4, 'BATCH_BUILD_LIMIT')
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.grants=grants;self.key=worker_key;self.build=build_sha256;self.evaluate=evaluate;self.max_updates=max_updates
        self.compute_lock=threading.Lock();self.lease=(self.root/'worker.lock').open('a+b')
        try:
            if __import__('os').name=='nt':
                import msvcrt
                self.lease.seek(0);self.lease.write(b'0');self.lease.flush();self.lease.seek(0)
                msvcrt.locking(self.lease.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lease.close();raise ValueError('batch worker state already owned')
        try:
            with self.connect() as c:
                c.execute('PRAGMA journal_mode=WAL')
                app=c.execute('PRAGMA application_id').fetchone()[0]
                tables=c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                require(app in (0,1112818737) and (app!=0 or not tables), 'BATCH_STORAGE_VERSION')
                c.execute('PRAGMA application_id=1112818737')
                c.execute('CREATE TABLE IF NOT EXISTS datasets(owner TEXT,id TEXT,hash TEXT,packet BLOB,receipt BLOB,PRIMARY KEY(owner,id))')
                c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT,consent_id TEXT,hash TEXT,packet BLOB,cursor INTEGER,weights BLOB,weights_hash TEXT,inflight INTEGER,UNIQUE(owner,consent_id))')
                c.execute('CREATE TABLE IF NOT EXISTS checkpoints(job TEXT,cursor INTEGER,weights_hash TEXT,PRIMARY KEY(job,cursor))')
        except Exception:
            self.close();raise

    def close(self):
        if not self.lease.closed:
            if __import__('os').name=='nt':
                import msvcrt
                self.lease.seek(0);msvcrt.locking(self.lease.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lease.fileno(),fcntl.LOCK_UN)
            self.lease.close()

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.root/'batch-jobs.sqlite3',timeout=30,isolation_level=None);c.row_factory=sqlite3.Row
        try:
            c.execute('PRAGMA synchronous=FULL');yield c
        finally:c.close()

    def authorize(self, packet, expected):
        require(isinstance(packet,dict) and isinstance(packet.get('payload'),dict),'ENVELOPE_FIELDS')
        body=packet['payload'];fields(body,expected);p.common(body)
        grant=self.grants.get((body['tenant_id'],body['company_id']))
        require(grant is not None and grant.get('active') is True and grant.get('batch_training') is True,'BATCH_COMPANY_DENIED')
        verify(packet,grant['node_verify_key'])
        require(body['key_epoch']==grant['key_epoch'] and body['build_sha256']==self.build and grant.get('target')==TARGET,'KEY_BUILD_MISMATCH')
        return body,canonical([body['tenant_id'],body['company_id']]).decode()

    def upload(self, packet):
        body,owner=self.authorize(packet,p.UPLOAD)
        batches=body['batches'];require(isinstance(batches,list) and 2<=len(batches)<=min(p.MAX_BATCHES,self.max_updates),'BATCH_COUNT')
        for i,b in enumerate(batches):
            fields(b,{'index','rows','features','x_cipher','x_cipher_sha256'})
            require(type(b['index']) is int and b['index']==i and type(b['rows']) is int and b['rows']==4 and type(b['features']) is int and b['features']==2,'BATCH_ORDER_SHAPE')
            blob(b,'x_cipher')
        require(body['batch_manifest_sha256']==p.manifest(batches),'BATCH_MANIFEST_MISMATCH')
        for name in ('training_commitment','evaluation_commitment'):p.hash_field(body[name])
        digest=sha(canonical(packet))
        receipt=sign(dict(**{k:body[k] for k in p.BASE},kind='batch_dataset_received',upload_sha256=digest,
            batch_manifest_sha256=body['batch_manifest_sha256'],training_commitment=body['training_commitment'],evaluation_commitment=body['evaluation_commitment'],batch_count=len(batches)),self.key)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM datasets WHERE owner=? AND id=?',(owner,body['dataset_id'])).fetchone()
            if old:
                require(old['hash']==digest,'BATCH_DATASET_CONFLICT');return strict_json(old['receipt'])
            c.execute('INSERT INTO datasets VALUES (?,?,?,?,?)',(owner,body['dataset_id'],digest,canonical(packet),canonical(receipt)));c.commit()
        return receipt

    def confirm(self, packet):
        body,owner=self.authorize(packet,p.CONSENT)
        require(type(body['epochs']) is int and body['epochs']>=1,'BATCH_EPOCHS')
        require(isinstance(body['consent_id'],str) and p.ID.fullmatch(body['consent_id']),'CONSENT_INVALID')
        require(body['verification_mode']==self.grants[(body['tenant_id'],body['company_id'])].get('verification_mode') and body['verification_mode'] in ('synthetic_expected','human_verified'),'VERIFICATION_NOT_GRANTED')
        weights=blob(body,'weights_cipher');digest=sha(canonical(packet));job='btr_'+digest[:32]
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            dataset=c.execute('SELECT * FROM datasets WHERE owner=? AND id=?',(owner,body['dataset_id'])).fetchone()
            require(dataset is not None,'BATCH_DATASET_NOT_RECEIVED')
            source=strict_json(dataset['packet'])['payload']
            require(sha(dataset['receipt'])==body['receipt_sha256'],'RECEIPT_MISMATCH')
            require(all(source[k]==body[k] for k in p.BASE|{'batch_manifest_sha256','training_commitment','evaluation_commitment'}),'BATCH_DATASET_BINDING')
            count=len(source['batches']);require(count*body['epochs']<=self.max_updates,'BATCH_UPDATE_LIMIT')
            require(isinstance(body['label_batches'],list) and len(body['label_batches'])==count,'BATCH_LABEL_COUNT')
            for i,b in enumerate(body['label_batches']):
                fields(b,{'index','label_revision','review_commitment','y_cipher','y_cipher_sha256'})
                require(type(b['index']) is int and b['index']==i and type(b['label_revision']) is int and b['label_revision']>=1,'BATCH_LABEL_ORDER')
                p.hash_field(b['review_commitment']);blob(b,'y_cipher')
            old=c.execute('SELECT * FROM jobs WHERE owner=? AND consent_id=?',(owner,body['consent_id'])).fetchone()
            if old:
                require(old['hash']==digest,'BATCH_CONSENT_CONFLICT');return self.status_value(old,body,source)
            c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)',(job,owner,body['consent_id'],digest,canonical(packet),0,weights,sha(weights),None))
            c.execute('INSERT INTO checkpoints VALUES (?,?,?)',(job,0,sha(weights)));c.commit()
            row=c.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
        return self.status_value(row,body,source)

    def status_value(self,row,consent,source,*,result=False):
        count=len(source['batches']);total=count*consent['epochs'];done=row['cursor']==total
        require(sha(row['weights'])==row['weights_hash'],'BATCH_CHECKPOINT_TAMPERED')
        value=dict(**{k:consent[k] for k in p.BASE},kind='batch_training_status',job_id=row['id'],
            consent_sha256=row['hash'],status='completed' if done else 'confirmed' if row['cursor']==0 and row['inflight'] is None else 'training',
            completed_updates=row['cursor'],total_updates=total,batch_count=count,completed_epochs=row['cursor']//count,
            next_batch_index=None if done else row['cursor']%count,inflight_update=row['inflight'],
            batch_manifest_sha256=source['batch_manifest_sha256'],training_commitment=source['training_commitment'],evaluation_commitment=source['evaluation_commitment'])
        if result and done:value.update(model_cipher=encode(row['weights']),model_cipher_sha256=row['weights_hash'])
        return sign(value,self.key)

    def access(self, packet):
        body,owner=self.authorize(packet,p.ACCESS)
        require(body['action'] in ('status','run','result'),'ACTION_INVALID')
        def read():
            with self.connect() as c:
                row=c.execute('SELECT * FROM jobs WHERE owner=? AND id=?',(owner,body['job_id'])).fetchone()
                require(row is not None,'BATCH_JOB_NOT_FOUND');consent=strict_json(row['packet'])['payload']
                self.authorize(strict_json(row['packet']),p.CONSENT)
                require(all(body[k]==consent[k] for k in p.BASE),'BATCH_JOB_BINDING')
                ds=c.execute('SELECT * FROM datasets WHERE owner=? AND id=?',(owner,body['dataset_id'])).fetchone()
                require(ds is not None,'BATCH_DATASET_NOT_RECEIVED');source=strict_json(ds['packet'])['payload']
                self.authorize(strict_json(ds['packet']),p.UPLOAD)
                require(sha(ds['receipt'])==consent['receipt_sha256'] and p.manifest(source['batches'])==consent['batch_manifest_sha256'],'BATCH_SAVED_DATASET_TAMPERED')
                require(sha(row['packet'])==row['hash'],'BATCH_SAVED_CONSENT_TAMPERED')
                require(type(row['cursor']) is int and 0<=row['cursor']<=len(source['batches'])*consent['epochs'],'BATCH_CURSOR_INVALID')
                checkpoint=c.execute('SELECT weights_hash FROM checkpoints WHERE job=? AND cursor=?',(row['id'],row['cursor'])).fetchone()
                require(checkpoint is not None and checkpoint['weights_hash']==row['weights_hash'],'BATCH_CHECKPOINT_TAMPERED')
            return row,consent,source
        row,consent,source=read()
        if body['action']=='run' and self.compute_lock.acquire(blocking=False):
            try:
                row,consent,source=read();count=len(source['batches']);total=count*consent['epochs']
                while row['cursor']<total:
                    self.authorize(packet,p.ACCESS)
                    cursor=row['cursor'];index=cursor%count
                    require(sha(row['weights'])==row['weights_hash'],'BATCH_CHECKPOINT_TAMPERED')
                    with self.connect() as c:c.execute('UPDATE jobs SET inflight=? WHERE id=?',(cursor,row['id']))
                    output=self.evaluate(blob(source['batches'][index],'x_cipher'),blob(consent['label_batches'][index],'y_cipher'),row['weights'],body)
                    self.authorize(packet,p.ACCESS)
                    require(isinstance(output,bytes) and output,'BATCH_OUTPUT_INVALID')
                    with self.connect() as c:
                        c.execute('BEGIN IMMEDIATE')
                        c.execute('INSERT INTO checkpoints VALUES (?,?,?)',(row['id'],cursor+1,sha(output)))
                        c.execute('UPDATE jobs SET cursor=?,weights=?,weights_hash=?,inflight=NULL WHERE id=? AND cursor=?',(cursor+1,output,sha(output),row['id'],cursor));c.commit()
                    row,consent,source=read()
            finally:self.compute_lock.release()
        self.authorize(packet,p.ACCESS)
        row,consent,source=read()
        return self.status_value(row,consent,source,result=body['action']=='result')
