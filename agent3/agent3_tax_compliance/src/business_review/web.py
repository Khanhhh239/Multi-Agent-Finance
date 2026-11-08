"""Authenticated human review commands; never caller-supplied PaymentProof/legal approval."""
import asyncio
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from types import SimpleNamespace
from pydantic import Field,StrictBool
from ..domain.base import Contract,Identifier
from ..domain.money import ExactDecimal
from ..planning.contracts import DailyPurchases,PurchaseEvidence
from ..persistence.repository import digest
from ..review.contracts import ReviewError
from ..canonicalization.derive import sha
from .contracts import ReviewDossier,InvoiceReview,ProductReview,PaymentReview,DailyReview,DocumentProof
from .repository import BusinessReviewRepository
from .evidence import file_sha,verify_stored
from .service import observed


class PaymentCommand(Contract):
    case: Literal['STANDARD','SPECIAL','UNKNOWN']
    settlement: Literal['VERIFIED_NON_CASH','VERIFIED_CASH','UNSETTLED','UNKNOWN'] = 'UNKNOWN'
    method: Literal['BANK_TRANSFER','CARD','CASH','CASH_DEPOSIT_TO_SELLER','UNKNOWN'] = 'UNKNOWN'
    amount: ExactDecimal = Field(ge=0)
    execution_confirmed: StrictBool = False
    full_settlement: StrictBool = False
    evidence_ids: tuple[Identifier,...] = Field(min_length=1,max_length=99)


class LedgerCommand(Contract):
    record_ids: tuple[Identifier,...] = Field(min_length=1,max_length=100)
    complete: StrictBool = False
    evidence_ids: tuple[Identifier,...] = Field(min_length=1,max_length=99)


class SaveCommand(Contract):
    expected_record_revision: int = Field(strict=True,ge=1)
    expected_review_id: Identifier | None
    review_reference: str = Field(min_length=3,max_length=512)
    confirmed: StrictBool
    invoice: InvoiceReview | None = None
    products: tuple[ProductReview,...] = Field(default=(),max_length=1000)
    payment: PaymentCommand | None = None
    daily: LedgerCommand | None = None


def fail(code,message,status=422):raise ReviewError(code,message,status)


class WebReviews(BusinessReviewRepository):
    def __init__(self,settings):super().__init__(settings);self.settings=settings

    def setup_web(self,db):
        db.execute('''CREATE TABLE IF NOT EXISTS business_documents(
            tenant_id TEXT,taxpayer_id TEXT,record_id TEXT,revision INTEGER,document_id TEXT,
            record_sha256 TEXT,payload TEXT,sha256 TEXT,PRIMARY KEY(tenant_id,taxpayer_id,document_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS business_requests(
            tenant_id TEXT,taxpayer_id TEXT,request_id TEXT,command_sha256 TEXT,review_id TEXT,
            PRIMARY KEY(tenant_id,taxpayer_id,request_id))''')

    def current(self,ctx,payer,record_id,revision):
        record=self.base.record(ctx,payer,record_id)
        if record.revision!=revision:fail('BUSINESS_REVISION_CONFLICT','Hóa đơn đã đổi. Mở bản mới rồi đối chiếu lại hồ sơ.',409)
        return record

    def document_rows(self,ctx,payer,record):
        if not self.path.exists():return []
        with self.db() as db:
            self.setup_web(db)
            rows=db.execute('SELECT payload,sha256,record_sha256 FROM business_documents WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=? ORDER BY rowid',
                (ctx.tenant_id,payer,record.record_id,record.revision)).fetchall()
        result=[]
        for row in rows:
            if digest(row['payload'].encode())!=row['sha256'] or row['record_sha256']!=sha(record.model_dump(mode='json')):raise ValueError('document metadata integrity failure')
            result.append(json.loads(row['payload']))
        return result

    async def upload(self,ctx,payer,record_id,revision,kind,file):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        record=self.current(ctx,payer,record_id,revision)
        if len(self.document_rows(ctx,payer,record))>=99:fail('BUSINESS_DOCUMENT_LIMIT','Tối đa 99 tài liệu bổ sung cho một bản hóa đơn.')
        destination=self.evidence_directory(ctx,payer);destination.mkdir(parents=True,exist_ok=True)
        stamp=time.monotonic();size=0;pin=hashlib.sha256();first=b''
        with tempfile.NamedTemporaryFile(dir=destination,delete=False) as stream:
            temporary=Path(stream.name)
            try:
                while True:
                    remaining=self.settings.max_upload_seconds-(time.monotonic()-stamp)
                    if remaining<=0:fail('BUSINESS_UPLOAD_TIMEOUT','Tải tài liệu quá lâu. Thử lại với tệp nhỏ hơn.',408)
                    try:block=await asyncio.wait_for(file.read(1024*1024),remaining)
                    except asyncio.TimeoutError:fail('BUSINESS_UPLOAD_TIMEOUT','Tải tài liệu quá lâu.',408)
                    if not block:break
                    if not first:first=block[:16]
                    size+=len(block)
                    if size>self.settings.max_upload_bytes:fail('BUSINESS_DOCUMENT_TOO_LARGE','Tài liệu vượt giới hạn dung lượng.',413)
                    pin.update(block);stream.write(block)
            except BaseException:
                stream.close();temporary.unlink(missing_ok=True);raise
        try:
            if not (first.startswith(b'%PDF-') or first.startswith(b'\x89PNG\r\n\x1a\n') or first.startswith(b'\xff\xd8\xff')):
                fail('BUSINESS_DOCUMENT_FORMAT','Chọn PDF, PNG hoặc JPEG. Tệp này chưa được hỗ trợ.')
            self.current(ctx,payer,record_id,revision)
            identifier='bd-'+uuid4().hex
            filename=''.join(c for c in (file.filename or 'tai-lieu').replace('\\','/').rsplit('/',1)[-1] if c.isprintable())[:180]
            doc=dict(evidence_id=identifier,filename=filename,kind=kind,sha256=pin.hexdigest(),size_bytes=size)
            target=destination/pin.hexdigest()
            if target.exists():
                if file_sha(target)!=pin.hexdigest():raise ValueError('stored evidence corrupt')
            else:os.replace(temporary,target)
            raw=json.dumps(doc,ensure_ascii=False,sort_keys=True)
            with self.db() as db:
                self.setup_web(db);db.execute('BEGIN IMMEDIATE')
                count=db.execute('SELECT count(*) FROM business_documents WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=?',
                    (ctx.tenant_id,payer,record_id,revision)).fetchone()[0]
                if count>=99:fail('BUSINESS_DOCUMENT_LIMIT','Tối đa 99 tài liệu bổ sung.')
                db.execute('INSERT INTO business_documents VALUES(?,?,?,?,?,?,?,?)',(ctx.tenant_id,payer,record_id,revision,identifier,
                    sha(record.model_dump(mode='json')),raw,digest(raw.encode())))
            return doc
        finally:temporary.unlink(missing_ok=True)

    def editor(self,ctx,payer,record_id):
        record=self.base.record(ctx,payer,record_id);dossier=self.latest(ctx,payer,record)
        documents=[dict(evidence_id='source-invoice',kind='INVOICE',filename='Hóa đơn gốc',source=True)]
        documents+=self.document_rows(ctx,payer,record)
        known={d['evidence_id'] for d in documents}
        if dossier:
            for doc in dossier.documents:
                if doc.evidence_id not in known:documents.append(dict(evidence_id=doc.evidence_id,kind=doc.kind,filename='Tài liệu đã lưu',sha256=doc.sha256))
        return dict(record_revision=record.revision,record_sha256=sha(record.model_dump(mode='json')),
            review_id=dossier.review_id if dossier else None,reviewer_id=dossier.reviewer_id if dossier else None,
            reviewed_at=dossier.reviewed_at.isoformat() if dossier else None,review_reference=dossier.review_reference if dossier else '',
            invoice=dossier.invoice.model_dump(mode='json') if dossier and dossier.invoice else None,
            products=[p.model_dump(mode='json') for p in dossier.products] if dossier else [],
            payment=dossier.payment.model_dump(mode='json') if dossier and dossier.payment else None,
            daily=dossier.daily.model_dump(mode='json') if dossier and dossier.daily else None,documents=documents,
            can_write='WRITE' in ctx.permissions or 'ADMIN' in ctx.permissions)

    def save(self,ctx,payer,record_id,command,request_id):
        ctx.require(ctx.tenant_id,payer,'WRITE')
        command=SaveCommand.model_validate_json(command.model_dump_json())
        if not command.confirmed:fail('BUSINESS_CONFIRMATION_REQUIRED','Xác nhận bạn đã đối chiếu các thông tin sẽ lưu.')
        request_sha=sha([record_id,command.model_dump(mode='json'),ctx.actor_id])
        with self.db() as db:
            self.setup_web(db)
            old=db.execute('SELECT * FROM business_requests WHERE tenant_id=? AND taxpayer_id=? AND request_id=?',(ctx.tenant_id,payer,request_id)).fetchone()
        if old:
            if old['command_sha256']!=request_sha:fail('BUSINESS_IDEMPOTENCY_CONFLICT','Mã lần lưu thuộc nội dung khác.',409)
            return dict(saved=True,review_id=old['review_id'],record_revision=command.expected_record_revision,legal_approval=False)
        record=self.current(ctx,payer,record_id,command.expected_record_revision)
        if record.record_type!='INVOICE' or record.invoice is None:fail('BUSINESS_UNSUPPORTED_RECORD','Hồ sơ này chỉ hỗ trợ bản ghi hóa đơn.')
        source,raw_source=self.base.source(ctx,payer,record.source_id)
        target=self.evidence_directory(ctx,payer)/source.sha256;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if file_sha(target)!=source.sha256:raise ValueError('stored source corrupt')
        else:
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as stream:
                temporary=Path(stream.name);stream.write(raw_source)
            try:os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
        available={d['evidence_id']:DocumentProof(evidence_id=d['evidence_id'],relative_path=d['sha256'],sha256=d['sha256'],kind=d['kind'])
            for d in self.document_rows(ctx,payer,record)}
        previous=self.latest(ctx,payer,record)
        if previous:
            for d in previous.documents:available.setdefault(d.evidence_id,d.model_copy(update={'relative_path':d.sha256}))
        available['source-invoice']=DocumentProof(evidence_id='source-invoice',relative_path=source.sha256,sha256=source.sha256,kind='INVOICE')
        referenced={'source-invoice'}
        for part in (command.invoice,command.payment,command.daily,*command.products):
            if part:referenced.update(part.evidence_ids)
        if not referenced<=available.keys():fail('BUSINESS_EVIDENCE_SCOPE','Tài liệu không thuộc bản hóa đơn này. Tải lại danh sách.')
        docs=tuple(available[k] for k in sorted(referenced));verify_stored(SimpleNamespace(documents=docs),self.evidence_directory(ctx,payer))
        if sum((self.evidence_directory(ctx,payer)/d.sha256).stat().st_size for d in docs)>128*1024*1024:
            fail('BUSINESS_DOCUMENT_LIMIT','Tổng chứng cứ hồ sơ vượt 128 MB.')
        payment=None
        if command.payment:
            seller=observed(record.parties.seller.tax_id) if record.parties.seller else None
            buyer=observed(record.parties.buyer.tax_id) if record.parties.buyer else None
            if not seller or not buyer:fail('BUSINESS_PARTIES_REQUIRED','Lưu MST người bán và người mua trên hóa đơn trước khi xác nhận thanh toán.')
            payment=PaymentReview(**command.payment.model_dump(),seller_tax_id=seller,buyer_tax_id=buyer)
        daily=None
        if command.daily:
            if len(set(command.daily.record_ids))!=len(command.daily.record_ids) or record_id not in command.daily.record_ids:
                fail('BUSINESS_LEDGER_RECORDS','Danh sách mua cùng ngày phải có hóa đơn hiện tại, không được trùng.')
            rows=[]
            for identifier in command.daily.record_ids:
                other=self.base.record(ctx,payer,identifier)
                on=observed(other.invoice.issue_date) if other.invoice else None
                seller=observed(other.parties.seller.tax_id) if other.parties.seller else None
                gross=observed(other.totals.gross)
                if (not on or not seller or gross is None or gross<0 or observed(other.currency)!='VND' or
                    on!=observed(record.invoice.issue_date) or seller.replace('-','')!=str(observed(record.parties.seller.tax_id)).replace('-','')):
                    fail('BUSINESS_LEDGER_RECORDS','Chỉ chọn hóa đơn VND cùng người bán/ngày và đủ số tiền đã lưu.')
                rows.append(PurchaseEvidence(tenant_id=ctx.tenant_id,taxpayer_id=payer,record_id=identifier,revision=other.revision,
                    input_sha256=sha(other.model_dump(mode='json')),issue_date=on,seller_tax_id=seller.replace('-',''),gross=gross))
            daily=DailyReview(ledger=DailyPurchases(version='web-ledger-v1',complete=command.daily.complete,
                verification_reference=command.review_reference,purchases=tuple(rows)),evidence_ids=command.daily.evidence_ids)
        dossier=ReviewDossier(review_id='br-'+uuid4().hex,tenant_id=ctx.tenant_id,taxpayer_id=payer,record_id=record_id,
            record_revision=record.revision,record_sha256=sha(record.model_dump(mode='json')),reviewer_id=ctx.actor_id,
            reviewed_at=datetime.now(timezone.utc),review_reference=command.review_reference,documents=docs,
            invoice=command.invoice,products=command.products,payment=payment,daily=daily)
        from .service import bind_scope
        bind_scope(record,dossier);self.verify_daily(ctx,payer,dossier)
        with self.db() as db:
            self.setup_web(db);db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM business_requests WHERE tenant_id=? AND taxpayer_id=? AND request_id=?',(ctx.tenant_id,payer,request_id)).fetchone()
            if old:
                if old['command_sha256']!=request_sha:fail('BUSINESS_IDEMPOTENCY_CONFLICT','Mã lần lưu thuộc nội dung khác.',409)
                return dict(saved=True,review_id=old['review_id'],record_revision=record.revision,legal_approval=False)
            self.current(ctx,payer,record_id,record.revision)
            latest=db.execute('SELECT review_id FROM business_reviews WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=? ORDER BY rowid DESC LIMIT 1',
                (ctx.tenant_id,payer,record_id,record.revision)).fetchone()
            if (latest['review_id'] if latest else None)!=command.expected_review_id:
                fail('BUSINESS_REVIEW_CONFLICT','Hồ sơ đã được lưu ở nơi khác. Tải bản mới để đối chiếu.',409)
            raw=dossier.model_dump_json()
            db.execute('INSERT INTO business_reviews VALUES(?,?,?,?,?,?,?,?)',(ctx.tenant_id,payer,record_id,record.revision,dossier.review_id,ctx.actor_id,raw,digest(raw.encode())))
            db.execute('INSERT INTO business_requests VALUES(?,?,?,?,?)',(ctx.tenant_id,payer,request_id,request_sha,dossier.review_id))
        return dict(saved=True,review_id=dossier.review_id,record_revision=record.revision,legal_approval=False)

    def download(self,ctx,payer,record_id,document_id):
        record=self.base.record(ctx,payer,record_id)
        if document_id=='source-invoice':return self.base.source(ctx,payer,record.source_id)[1]
        available={d['evidence_id']:d['sha256'] for d in self.document_rows(ctx,payer,record)}
        dossier=self.latest(ctx,payer,record)
        if dossier:available.update({d.evidence_id:d.sha256 for d in dossier.documents})
        if document_id not in available:raise KeyError('document not found')
        path=self.evidence_directory(ctx,payer)/available[document_id]
        if file_sha(path)!=available[document_id]:raise ValueError('stored evidence corrupt')
        return path.read_bytes()

    def candidates(self,ctx,payer,record_id):
        record=self.base.record(ctx,payer,record_id)
        if record.record_type!='INVOICE' or record.invoice is None:fail('BUSINESS_UNSUPPORTED_RECORD','Danh sách mua cùng ngày chỉ hỗ trợ hóa đơn.')
        with self.base.connection() as db:
            ids=db.execute('SELECT record_id FROM records WHERE tenant_id=? AND taxpayer_id=? ORDER BY record_id LIMIT 501',(ctx.tenant_id,payer)).fetchall()
        items=[]
        for (identifier,) in ids[:500]:
            other=self.base.record(ctx,payer,identifier)
            if (other.invoice and observed(other.invoice.issue_date)==observed(record.invoice.issue_date) and
                other.parties.seller and record.parties.seller and observed(other.parties.seller.tax_id) is not None and
                str(observed(other.parties.seller.tax_id)).replace('-','')==str(observed(record.parties.seller.tax_id)).replace('-','') and
                observed(other.currency)=='VND' and observed(other.totals.gross) is not None and observed(other.totals.gross)>=0):
                items.append(dict(record_id=identifier,revision=other.revision,number=observed(other.invoice.number),gross=str(observed(other.totals.gross))))
        return dict(items=items,truncated=len(ids)>500,completeness_verified=False)
