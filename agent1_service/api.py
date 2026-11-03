"""API local có xác thực, cô lập một DN và cổng NO-GO mặc định."""
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import secrets
import uuid
import io
import math
import re
import zipfile
import pandas as pd
from cryptography.fernet import Fernet
from fastapi import FastAPI,Header,HTTPException,Depends,UploadFile,File,Form,Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
from .store import Store
from .jobs.nightly import run
from .ingest.dates import local_dates
from agent1.api_surface import what_if,scenario_library

ALLOWED={'invoices':'invoice_id','invoice_events':'event_id','bank_txns':'txn_id','customers':'customer_id','promises':None,'outflows':None,'cash_balances':'date'}


class ForecastRequest(BaseModel):
    cutoff:str
    balance:float=Field(allow_inf_nan=False)


class PromiseRequest(BaseModel):
    invoice_id:str
    customer_id:str
    amount:float=Field(gt=0,allow_inf_nan=False)
    made_date:str
    promised_date:str


class IngestRequest(BaseModel):
    table:str
    records:list[dict]=Field(max_length=100000)


class ExpenseShift(BaseModel):
    from_week:int=Field(ge=1,le=13)
    to_week:int=Field(ge=1,le=13)
    amount:float=Field(gt=0,allow_inf_nan=False)


class ScenarioRequest(BaseModel):
    delay_customer:str|None=Field(default=None,min_length=1)
    delay_weeks:int=Field(default=2,ge=0,le=52)
    revenue_drop:float|None=Field(default=None,ge=0,le=1)
    shift_out:ExpenseShift|None=None


def key_directory(state_dir,key_dir=None):
    """Thư mục khoá TÁCH khỏi thư mục dữ liệu (cam kết bảo mật Điều 3.2). Mặc định: thư mục anh em `<data>-keys`;
    triển khai thật nên đặt AGENT1_KEY_DIR sang ổ/thiết bị khác. Từ chối nếu nằm trong thư mục dữ liệu."""
    data=Path(state_dir).resolve()
    keys=Path(key_dir or os.environ.get('AGENT1_KEY_DIR') or data.parent/(data.name+'-keys')).resolve()
    if keys==data or data in keys.parents:raise ValueError('Thư mục khoá không được nằm trong thư mục dữ liệu')
    keys.mkdir(parents=True,exist_ok=True)
    # Di chuyển khoá kiểu cũ (nằm cùng agent1.db) sang thư mục khoá; không tự chọn nếu hai bản khác nhau.
    for name in ('encryption.key','api-token.txt'):
        old,new=data/name,keys/name
        if old.exists():
            if new.exists() and new.read_bytes()!=old.read_bytes():raise ValueError(f'{name} có hai bản khác nhau; cần xử lý tay')
            if not new.exists():new.write_bytes(old.read_bytes())
            old.unlink()
    return keys


def create_app(state_dir=None,token=None,firm_id=None,engine=run,key_dir=None,bank_accounts_file=None):
    directory=Path(state_dir or os.environ.get('AGENT1_STATE_DIR','.state'));directory.mkdir(parents=True,exist_ok=True)
    keys=key_directory(directory,key_dir)
    token=token or os.environ.get('AGENT1_API_TOKEN')
    if not token:
        token_file=keys/'api-token.txt'
        if not token_file.exists(): token_file.write_text(secrets.token_urlsafe(32),encoding='utf-8')
        token=token_file.read_text(encoding='utf-8').strip()
    key_file=keys/'encryption.key'
    if not key_file.exists():key_file.write_bytes(Fernet.generate_key())
    store=Store(directory/'agent1.db',key_file.read_bytes())
    # Ẩn danh HMAC ở bước nạp (Điều 3.4). Tắt chỉ cho nghiên cứu cục bộ: AGENT1_PSEUDONYMIZE=0.
    pseudonymize=os.environ.get('AGENT1_PSEUDONYMIZE','1')!='0'
    pseudo_file=keys/'pseudonym.key'
    if not pseudo_file.exists():pseudo_file.write_bytes(secrets.token_bytes(32))
    pseudo_key=pseudo_file.read_bytes()
    firm_id=firm_id or os.environ.get('AGENT1_FIRM_ID','F000')
    from .ingest.bank_accounts import load_account_registry,registry_path
    account_registry_path=bank_accounts_file or registry_path(directory,keys)
    def bank_registry():
        return load_account_registry(account_registry_path,firm_id)
    last={}
    @asynccontextmanager
    async def lifespan(_):
        yield
        store.connection.close()
    app=FastAPI(title='Agent 1 — Trợ lý dòng tiền',lifespan=lifespan)

    def authorize(authorization:str|None=Header(default=None)):
        if not authorization or not hmac.compare_digest(authorization.encode('utf-8'),('Bearer '+token).encode('utf-8')):
            raise HTTPException(401,'Cần bearer token hợp lệ')
        return firm_id

    def frame(kind,firm):
        records=store.get(firm,kind)
        data=pd.DataFrame(records)
        if not len(data):
            raise HTTPException(422,f'Chưa nhập bảng {kind}')
        for column in data.columns:
            if 'date' in column or column=='known_at':
                data[column]=local_dates(data[column],dayfirst=False)
        return data

    @app.get('/health')
    def health():
        return dict(status='ok',pilot_ready=False,forecast_gate='NO_GO',alert_delivery='local_file')

    def ingest_records(body,firm,*,source='json'):
        if body.table not in ALLOWED:raise HTTPException(422,'Bảng không được phép')
        if body.table in {'invoices','invoice_events'}:
            from .ingest.invoices import (validate_invoices, reconcile_invoices,
                resolve_references, validate_cancellations, effective_invoices)
            for row in body.records:
                if row.get('firm_id',firm)!=firm:raise HTTPException(403,'Dữ liệu thuộc DN khác')
            try:
                with store.lock:
                    existing=store.get(firm,'invoices')
                    events=store.get(firm,'invoice_events')
                    if body.table=='invoices':
                        received=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').date().isoformat()
                        rows=[dict(row,available_on=row.get('available_on') or received,
                                   ingested_on=received) for row in body.records]
                        prepared=validate_invoices(rows,source=source,
                            today=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None).normalize())
                        if pseudonymize:
                            from .ingest.privacy import pseudonymize_row
                            prepared=[pseudonymize_row(row,pseudo_key) for row in prepared]
                        all_rows,updates=reconcile_invoices(existing,prepared)
                        resolve_references(all_rows)
                        effective_invoices(all_rows,events)
                        by_id={r['invoice_id']:r for r in all_rows}
                        updates=[by_id[r['invoice_id']] for r in updates]
                        snapshots=[dict(row,id=f"{row['invoice_id']}:{row['revision']}") for row in updates]
                        store.put_many(firm,{'invoices':updates,'invoice_versions':snapshots})
                    else:
                        received=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').date().isoformat()
                        event_rows=[dict(row,available_on=row.get('available_on') or received,
                                         ingested_on=received) for row in body.records]
                        all_events=validate_cancellations(events,event_rows,existing)
                        effective_invoices(existing,all_events)
                        known={e['event_id'] for e in events}
                        updates=[e for e in all_events if e['event_id'] not in known]
                        store.put_many(firm,{'invoice_events':updates})
            except (ValueError,TypeError,KeyError) as error:
                raise HTTPException(422,str(error)) from error
            return dict(accepted=len(body.records))
        records=[]
        for row in body.records:
            if row.get('firm_id',firm)!=firm:raise HTTPException(403,'Dữ liệu thuộc DN khác')
            row=dict(row,firm_id=firm)
            required={
                'bank_txns': {'txn_id','value_date','amount','memo'},
                'customers': {'customer_id','short'},
                'promises': {'invoice_id','customer_id','made_date','promised_date'},
                'outflows': {'date','amount','category'},
                'cash_balances': {'date','balance'},
            }[body.table]
            if not required <= set(row):raise HTTPException(422,'Thiếu cột bắt buộc của '+body.table)
            for col in ('amount','amount_gross','balance'):
                if col in row and (not isinstance(row[col],(int,float)) or isinstance(row[col],bool)
                                   or not math.isfinite(row[col]) or (col!='balance' and row[col]<0)):
                    raise HTTPException(422,'Số tiền không hợp lệ')
            if 'amount_gross' in row and row['amount_gross']==0:raise HTTPException(422,'Giá trị hoá đơn phải dương')
            for col in required:
                if 'date' in col:
                    try:
                        if pd.isna(pd.Timestamp(row[col])):raise ValueError()
                    except (ValueError,TypeError):raise HTTPException(422,'Ngày không hợp lệ')
            if pseudonymize:
                from .ingest.privacy import pseudonymize_row
                row=pseudonymize_row(row,pseudo_key)
            identifier=row.get(ALLOWED[body.table]) if ALLOWED[body.table] else row.get('id',uuid.uuid4().hex)
            if not identifier:raise HTTPException(422,'Thiếu khoá bản ghi')
            row['id']=str(identifier);records.append(row)
        try:store.put(firm,body.table,records)
        except (ValueError,TypeError):raise HTTPException(422,'Bản ghi chứa giá trị không hợp lệ')
        return dict(accepted=len(records))

    @app.post('/ingest')
    async def ingest(request:Request,firm=Depends(authorize)):
        from .ingest.strict_files import loads_json
        try:
            body=IngestRequest.model_validate(loads_json(await request.body()))
        except (ValueError,TypeError) as error:
            raise HTTPException(422,str(error)) from error
        return ingest_records(body,firm)

    @app.post('/ingest/file')
    async def ingest_file(file:UploadFile=File(...),kind:str=Form(...),bank:str=Form(default='vcb'),mapping:str=Form(default='{}'),
                          statement:str=Form(default='{}'),
                          available_on:str|None=Form(default=None),record_version:int=Form(default=1),firm=Depends(authorize)):
        content=await file.read(10_000_001)
        if len(content)>10_000_000:raise HTTPException(413,'File vượt giới hạn 10 MB')
        from .ingest.strict_files import loads_json,read_csv,read_excel,source_hash
        filename=Path(file.filename or 'upload').name
        digest=source_hash(content)
        raw=None
        try:
            columns=loads_json(mapping)
            if not isinstance(columns,dict):raise ValueError('Ánh xạ cột phải là JSON object')
            received=available_on or pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').date().isoformat()
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',received) or pd.isna(pd.to_datetime(received,format='%Y-%m-%d',errors='coerce')):
                raise ValueError('available_on phải là ngày YYYY-MM-DD')
            if record_version<1:raise ValueError('record_version phải là số nguyên dương')
            if kind=='xml':
                from .ingest.einvoice_xml import read_invoice_xml
                frame=pd.DataFrame([read_invoice_xml(content,firm,validate=False)]);table='invoices'
            else:
                if kind in {'bank_excel','ledger_excel'}:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        if sum(info.file_size for info in z.infolist())>100_000_000:raise ValueError('Workbook giải nén vượt giới hạn')
                    raw=read_excel(content,filename)
                elif kind=='bank_csv':raw=read_csv(content,filename)
                else:raise ValueError('Loại file không hỗ trợ')
                if kind.startswith('bank_'):
                    from .ingest.bank_statement import normalize_verified_statement,statement_scope
                    with store.lock:
                        registry=bank_registry()
                        existing=store.get(firm,'bank_statements')
                        credits,entries,period=normalize_verified_statement(
                            raw,firm,bank,loads_json(statement),existing,mapping=columns or None,
                            source={'file':filename,'sha256':digest,'available_on':received,
                                    'ingested_on':pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').date().isoformat()},
                            registry=registry)
                        known={r['txn_id']:r for r in store.get(firm,'bank_txns')}
                        for row in credits:
                            prior=known.get(row['txn_id'])
                            if prior and prior.get('statement_id')!=period['statement_id']:
                                raise ValueError(f'Dòng {row["source_row"]}: txn_id đã thuộc nguồn khác')
                        known_entries={r['txn_id']:r for r in store.get(firm,'bank_entries')}
                        for row in entries:
                            prior=known_entries.get(row['txn_id'])
                            if prior and prior.get('statement_id')!=period['statement_id']:
                                raise ValueError(f'Dòng {row["source_row"]}: giao dịch đã thuộc sao kê khác')
                        if pseudonymize:
                            from .ingest.privacy import pseudonymize_row
                            credits=[pseudonymize_row(row,pseudo_key) for row in credits]
                            entries=[pseudonymize_row(row,pseudo_key) for row in entries]
                        for row in credits:row['id']=row['txn_id']
                        store.put_many(firm,{'bank_txns':credits,'bank_entries':entries,
                                             'bank_statements':[period]})
                        coverage=statement_scope(existing+[period],period['period_start'],period['period_end'],registry)
                    return dict(accepted=len(credits),statement_id=period['statement_id'],coverage=coverage)
                else:
                    from .ingest.erp_ledger import normalize_ledger
                    frame=normalize_ledger(raw,firm,columns);table='invoices'
            records=json.loads(frame.to_json(orient='records',date_format='iso'))
            rows=raw.attrs['source_rows'] if kind!='xml' else [1]
            for row,number in zip(records,rows):
                row.update(source_file=filename,source_row=number,source_sha256=digest)
                if table=='invoices':
                    row['available_on']=row.get('available_on') or received
                    version=row.get('record_version',record_version)
                    if isinstance(version,str) and version.isdecimal():version=int(version)
                    row['record_version']=version
            return ingest_records(IngestRequest(table=table,records=records),firm,
                                  source='xml' if kind=='xml' else 'erp' if kind=='ledger_excel' else 'bank')
        except (ValueError,KeyError,zipfile.BadZipFile,TypeError,HTTPException) as error:
            reason=error.detail if isinstance(error,HTTPException) else str(error)
            detail={'file':filename,'sha256':digest,'reason':reason}
            match=re.search(r'dòng (\d+)',str(reason),flags=re.IGNORECASE)
            if match:
                detail['row']=int(match.group(1))
            rejected=dict(id=uuid.uuid4().hex,**detail)
            if raw is not None and match and 2 <= detail['row'] <= len(raw)+1:
                rejected['raw']=raw.iloc[detail['row']-2].astype(str).to_dict()
            store.put(firm,'ingest_quarantine',[rejected])
            raise HTTPException(422,detail) from error

    @app.post('/promises')
    def promises(body:PromiseRequest,firm=Depends(authorize)):
        try:
            made,promised=local_dates(pd.Series([body.made_date,body.promised_date]),dayfirst=False)
            if pd.isna(made) or pd.isna(promised) or promised<made:raise ValueError()
        except (ValueError,TypeError):raise HTTPException(422,'Ngày hứa trả không hợp lệ')
        row=body.model_dump();row.update(id=uuid.uuid4().hex,firm_id=firm,kept=None)
        row.update(made_date=made.isoformat(),promised_date=promised.isoformat())
        if pseudonymize:
            from .ingest.privacy import pseudonymize_row
            row=pseudonymize_row(row,pseudo_key)
        store.put(firm,'promises',[row]);return dict(id=row['id'],status='recorded_pending_outcome')

    @app.post('/forecast')
    def forecast(body:ForecastRequest,firm=Depends(authorize)):
        if os.environ.get('AGENT1_RESEARCH_MODE')!='1':
            raise HTTPException(409,'NO_GO: chưa đủ bằng chứng G12/G13; chỉ cho phép nghiên cứu local khi cấu hình rõ ràng')
        try:
            date=local_dates(pd.Series([body.cutoff]),dayfirst=False).iloc[0]
            if pd.isna(date):raise ValueError()
            body=body.model_copy(update={'cutoff':str(date.date())})
        except (ValueError,TypeError):raise HTTPException(422,'Ngày dự báo không hợp lệ')
        tables={k:frame(k,firm) for k in ('invoices','bank_txns','customers','outflows')}
        from .ingest.invoices import effective_invoices
        try:
            versions=store.get(firm,'invoice_versions')
            tables['invoices']=effective_invoices(versions or tables['invoices'].to_dict('records'),store.get(firm,'invoice_events'),body.cutoff)
        except ValueError as error:
            raise HTTPException(422,str(error)) from error
        if tables['invoices'].empty:
            raise HTTPException(422,'Không có hóa đơn còn hiệu lực tại ngày dự báo')
        if 'currency' in tables['invoices'] and not tables['invoices'].currency.eq('VND').all():
            raise HTTPException(422,'Dự báo hiện tính bằng VND; cần quy đổi tỷ giá có nguồn trước khi dùng hóa đơn ngoại tệ')
        promises=pd.DataFrame(store.get(firm,'promises'))
        statements=store.get(firm,'bank_statements')
        if statements:
            from .ingest.bank_statement import statement_scope
            try:registry=bank_registry()
            except ValueError as error:raise HTTPException(422,str(error)) from error
            start=min(s['period_start'] for s in statements)
            visible=[s for s in statements if s.get('available_on',s['period_end'])<=body.cutoff]
            coverage=statement_scope(visible,start,body.cutoff,registry)
            if not coverage['verified']:
                raise HTTPException(422,dict(reason='Phạm vi sao kê chưa đầy đủ tại ngày cắt',coverage=coverage))
            tables['bank_txns']=tables['bank_txns'][tables['bank_txns'].statement_id.isin(
                {s['statement_id'] for s in visible}) &
                (tables['bank_txns'].available_on<=body.cutoff)].copy()
            if any(s['currency']!='VND' for s in visible):
                raise HTTPException(422,'Dự báo hiện tính bằng VND; cần quy đổi tỷ giá có nguồn trước khi dùng sao kê ngoại tệ')
        if len(promises):
            promises=promises[promises.invoice_id.isin(tables['invoices'].invoice_id)].copy()
            for c in ('made_date','promised_date'):promises[c]=pd.to_datetime(promises[c])
        else:promises=None
        try:
            cache=None;version=None
            if engine is run:
                from .model_registry import load
                model,version=load(store,firm,body.cutoff)
                if model is not None:cache={'t1':model}
            kwargs={'model_cache':cache} if engine is run else {}
            if engine is run:
                # Dải công bố = copula-t + ACI; trạng thái ACI giữ theo doanh nghiệp qua các lần dự báo.
                previous=store.get(firm,'aci_state');kwargs['aci_state']=previous[-1] if previous else {}
            result,args=engine(tables['invoices'],tables['bank_txns'],tables['customers'],promises,tables['outflows'],body.cutoff,body.balance,**kwargs)
            state=result.pop('aci_state',None)
            if state is not None:store.put(firm,'aci_state',[dict(state,id='current')])
            result['model_version']=version['id'] if version else None
            result['opening_balance']=body.balance
        except (ValueError,KeyError) as e:raise HTTPException(422,str(e))
        last[firm]=args
        store.put(firm,'forecasts',[dict(id=body.cutoff,**result)])
        from .jobs.alerts import emit_alert
        emit_alert(store,directory,firm,result)
        return result

    @app.get('/models')
    def models(firm=Depends(authorize)):
        from .model_registry import summaries
        return summaries(store,firm)

    @app.get('/monitoring')
    def monitoring(firm=Depends(authorize)):
        reports=store.get(firm,'monitoring')
        return dict(reports=reports[-12:],status='observed' if reports else 'not_measured',pilot_ready=False)

    @app.post('/whatif')
    def whatif(body:ScenarioRequest,firm=Depends(authorize)):
        if firm not in last:raise HTTPException(409,'Cần chạy dự báo nghiên cứu trước')
        shift=body.shift_out
        customer=body.delay_customer
        if customer is not None and pseudonymize and not last[firm]['open_df'].customer_id.eq(customer).any():
            # Người dùng có thể nhập mã khách gốc; dữ liệu lưu mã đã ẩn danh.
            from .ingest.privacy import pseudo_id
            customer=pseudo_id(customer,pseudo_key)
        if customer is not None and not last[firm]['open_df'].customer_id.eq(customer).any():
            raise HTTPException(422,'Khách không có hoá đơn mở trong dự báo này')
        if body.delay_customer is None and shift is None and body.revenue_drop is None:
            raise HTTPException(422,'Cần chọn thay đổi trong kịch bản')
        try:
            result=what_if(last[firm],delay_customer=customer,delay_weeks=body.delay_weeks,revenue_drop=body.revenue_drop,
                shift_out=(shift.from_week-1,shift.to_week-1,shift.amount) if shift else None)
        except ValueError as e:raise HTTPException(422,str(e))
        result['quantiles']=result['quantiles'].tolist();return result

    @app.get('/alerts')
    def alerts(firm=Depends(authorize)):
        return store.get(firm,'alerts')

    @app.get('/data')
    def data(firm=Depends(authorize)):
        return {kind:len(store.get(firm,kind)) for kind in ALLOWED}

    @app.get('/bank/coverage')
    def bank_coverage(firm=Depends(authorize)):
        from .ingest.bank_statement import statement_scope
        try:registry=bank_registry()
        except ValueError as error:return {'verified':False,'reason':str(error)}
        statements=store.get(firm,'bank_statements')
        if not statements:return statement_scope([],None,None,registry)
        return statement_scope(statements,min(s['period_start'] for s in statements),
                               max(s['period_end'] for s in statements),registry)

    @app.delete('/data')
    def delete(firm=Depends(authorize)):
        store.delete_firm(firm);last.pop(firm,None);return dict(deleted=True)

    @app.get('/',response_class=HTMLResponse)
    def home():
        return (Path(__file__).parent/'ui/index.html').read_text(encoding='utf-8')
    app.state.store=store
    return app
