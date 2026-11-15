"""Cloud-side durable consent gate. Accepts ciphertext, never X/y/weights in clear."""
import json
from pathlib import Path
import sqlite3
import threading
from contextlib import contextmanager
from . import VERSION, TARGET, PROFILE
from .protocol import require,fields,common,blob,sha,canonical,verify,sign,atomic,TrainingError,decode,encode

BASE={'version','profile','target','tenant_id','company_id','key_epoch','dataset_id','build_sha256'}
UPLOAD=BASE|{'x_cipher','x_cipher_sha256','rows','features'}
CONSENT=BASE|{'consent_id','receipt_sha256','label_revision','label_review_commitment','y_cipher','y_cipher_sha256','weights_cipher','weights_cipher_sha256','steps','verification_mode'}
ACCESS=BASE|{'action','job_id'}


class CloudStore:
    def __init__(self,root,grants,worker_key,build_sha256,evaluate):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'jobs.sqlite3';self.grants=grants;self.key=worker_key;self.build=build_sha256;self.evaluate=evaluate;self.lock=threading.Lock()
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS datasets(owner TEXT,id TEXT,request_hash TEXT,packet TEXT,receipt TEXT,PRIMARY KEY(owner,id))')
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT,consent_id TEXT,request_hash TEXT,packet TEXT,cursor INTEGER,weights_path TEXT,status TEXT,UNIQUE(owner,consent_id))')

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=30);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()

    def authorize(self,packet,expected):
        require(isinstance(packet,dict) and isinstance(packet.get('payload'),dict),'ENVELOPE_FIELDS')
        body=packet['payload'];fields(body,expected);common(body)
        grant=self.grants.get((body['tenant_id'],body['company_id']))
        require(grant is not None and grant.get('active') is True,'COMPANY_DENIED')
        verify(packet,grant['node_verify_key'])
        require(body['key_epoch']==grant['key_epoch'] and body['build_sha256']==self.build,'KEY_BUILD_MISMATCH')
        require(grant.get('target')==TARGET,'TARGET_NOT_GRANTED')
        return body,canonical([body['tenant_id'],body['company_id']]).decode()

    def upload(self,packet):
        body,owner=self.authorize(packet,UPLOAD);blob(body,'x_cipher')
        require(type(body['rows']) is int and body['rows']==4 and type(body['features']) is int and body['features']==2,'DATA_DOMAIN')
        digest=sha(canonical(packet))
        receipt=sign(dict(version=VERSION,kind='dataset_received',tenant_id=body['tenant_id'],company_id=body['company_id'],dataset_id=body['dataset_id'],key_epoch=body['key_epoch'],build_sha256=self.build,profile=PROFILE,target=TARGET,x_cipher_sha256=body['x_cipher_sha256'],upload_sha256=digest),self.key)
        with self.connect() as c:
            old=c.execute('SELECT * FROM datasets WHERE owner=? AND id=?',(owner,body['dataset_id'])).fetchone()
            if old:
                require(old['request_hash']==digest,'DATASET_CONFLICT');return json.loads(old['receipt'])
            c.execute('INSERT INTO datasets VALUES (?,?,?,?,?)',(owner,body['dataset_id'],digest,canonical(packet).decode(),canonical(receipt).decode()))
        return receipt

    def confirm(self,packet):
        body,owner=self.authorize(packet,CONSENT)
        require(type(body['steps']) is int and 1<=body['steps']<=4,'STEPS_INVALID')
        require(type(body['label_revision']) is int and body['label_revision']>=1,'LABEL_REVISION_INVALID')
        require(isinstance(body['consent_id'],str) and 8<=len(body['consent_id'])<=100,'CONSENT_INVALID')
        require(isinstance(body['label_review_commitment'],str) and len(body['label_review_commitment'])==64,'LABEL_BINDING_INVALID')
        require(body['verification_mode'] in ('human_verified','synthetic_expected'),'VERIFICATION_MODE')
        require(body['verification_mode']==self.grants[(body['tenant_id'],body['company_id'])].get('verification_mode'),'VERIFICATION_NOT_GRANTED')
        blob(body,'y_cipher');weights=blob(body,'weights_cipher');digest=sha(canonical(packet));job='trn_'+digest[:32]
        with self.connect() as c:
            dataset=c.execute('SELECT * FROM datasets WHERE owner=? AND id=?',(owner,body['dataset_id'])).fetchone()
            require(dataset is not None,'DATASET_NOT_RECEIVED')
            require(sha(dataset['receipt'].encode())==body['receipt_sha256'],'RECEIPT_MISMATCH')
            source=json.loads(dataset['packet'])['payload']
            require(all(source[k]==body[k] for k in BASE),'DATASET_BINDING_MISMATCH')
            old=c.execute('SELECT * FROM jobs WHERE owner=? AND consent_id=?',(owner,body['consent_id'])).fetchone()
            if old:
                require(old['request_hash']==digest,'CONSENT_CONFLICT');return self.status_value(old,body)
            path=self.root/(job+'-0.cipher');atomic(path,weights)
            c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',(job,owner,body['consent_id'],digest,canonical(packet).decode(),0,path.name,'confirmed'))
            # Dataset upload alone never creates a training job.
            row=c.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
        return self.status_value(row,body)

    def status_value(self,row,body,*,result=False):
        value=dict(version=VERSION,kind='training_status',tenant_id=body['tenant_id'],company_id=body['company_id'],dataset_id=body['dataset_id'],key_epoch=body['key_epoch'],build_sha256=self.build,profile=PROFILE,target=TARGET,job_id=row['id'],status=row['status'],completed_steps=row['cursor'],consent_sha256=row['request_hash'])
        if result and row['status']=='completed':
            raw=(self.root/row['weights_path']).read_bytes();value.update(model_cipher=encode(raw),model_cipher_sha256=sha(raw))
        return sign(value,self.key)

    def access(self,packet):
        body,owner=self.authorize(packet,ACCESS);require(body['action'] in ('status','run','result'),'ACTION_INVALID')
        require(isinstance(body['job_id'],str) and len(body['job_id'])==36 and body['job_id'].startswith('trn_'),'JOB_INVALID')
        with self.lock:
            with self.connect() as c:
                row=c.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(body['job_id'],owner)).fetchone()
                require(row is not None,'JOB_NOT_FOUND');consent=json.loads(row['packet'])['payload']
                require(all(body[k]==consent[k] for k in BASE),'JOB_BINDING_MISMATCH')
                dataset=c.execute('SELECT * FROM datasets WHERE owner=? AND id=?',(owner,body['dataset_id'])).fetchone()
            if body['action']=='run' and row['status']!='completed':
                data=json.loads(dataset['packet'])['payload'];x=blob(data,'x_cipher');y=blob(consent,'y_cipher')
                for step in range(row['cursor'],consent['steps']):
                    weights=(self.root/row['weights_path']).read_bytes()
                    output=self.evaluate(x,y,weights,body)
                    path=self.root/(row['id']+'-'+str(step+1)+'.cipher');atomic(path,output)
                    status='completed' if step+1==consent['steps'] else 'training'
                    with self.connect() as c:
                        c.execute('UPDATE jobs SET cursor=?,weights_path=?,status=? WHERE id=?',(step+1,path.name,status,row['id']))
                        row=c.execute('SELECT * FROM jobs WHERE id=?',(row['id'],)).fetchone()
            return self.status_value(row,body,result=body['action']=='result')
