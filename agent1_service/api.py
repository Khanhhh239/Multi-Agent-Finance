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
import zipfile
import pandas as pd
from cryptography.fernet import Fernet
from fastapi import FastAPI,Header,HTTPException,Depends,UploadFile,File,Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel,Field
from .store import Store
from .jobs.nightly import run
from .ingest.dates import local_dates
from agent1.api_surface import what_if,scenario_library

ALLOWED={'invoices':'invoice_id','bank_txns':'txn_id','customers':'customer_id','promises':None,'outflows':None,'cash_balances':'date'}


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


def create_app(state_dir=None,token=None,firm_id=None,engine=run,key_dir=None):
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

    @app.post('/ingest')
    def ingest(body:IngestRequest,firm=Depends(authorize)):
        if body.table not in ALLOWED:raise HTTPException(422,'Bảng không được phép')
        records=[]
        for row in body.records:
            if row.get('firm_id',firm)!=firm:raise HTTPException(403,'Dữ liệu thuộc DN khác')
            row=dict(row,firm_id=firm)
            required={
                'invoices': {'invoice_id','customer_id','invoice_no','issue_date','due_date','amount_gross'},
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

    @app.post('/ingest/file')
    async def ingest_file(file:UploadFile=File(...),kind:str=Form(...),bank:str=Form(default='vcb'),mapping:str=Form(default='{}'),firm=Depends(authorize)):
        content=await file.read(10_000_001)
        if len(content)>10_000_000:raise HTTPException(413,'File vượt giới hạn 10 MB')
        try:
            columns=json.loads(mapping)
            if not isinstance(columns,dict):raise ValueError('Ánh xạ cột phải là JSON object')
            if kind=='xml':
                from .ingest.einvoice_xml import read_invoice_xml
                frame=pd.DataFrame([read_invoice_xml(content,firm)]);table='invoices'
            else:
                if kind in {'bank_excel','ledger_excel'}:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        if sum(info.file_size for info in z.infolist())>100_000_000:raise ValueError('Workbook giải nén vượt giới hạn')
                    raw=pd.read_excel(io.BytesIO(content))
                elif kind=='bank_csv':raw=pd.read_csv(io.BytesIO(content))
                else:raise ValueError('Loại file không hỗ trợ')
                if kind.startswith('bank_'):
                    from .ingest.bank_statement import normalize_statement
                    frame=normalize_statement(raw,firm,bank,mapping=columns or None);table='bank_txns'
                else:
                    from .ingest.erp_ledger import normalize_ledger
                    frame=normalize_ledger(raw,firm,columns);table='invoices'
            records=json.loads(frame.to_json(orient='records',date_format='iso'))
            return ingest(IngestRequest(table=table,records=records),firm=firm)
        except (ValueError,KeyError,zipfile.BadZipFile,TypeError):
            raise HTTPException(422,'File không khớp lược đồ; kiểm tra phiên bản XML hoặc ánh xạ cột')

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
        promises=pd.DataFrame(store.get(firm,'promises'))
        if len(promises):
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

    @app.delete('/data')
    def delete(firm=Depends(authorize)):
        store.delete_firm(firm);last.pop(firm,None);return dict(deleted=True)

    @app.get('/',response_class=HTMLResponse)
    def home():
        return (Path(__file__).parent/'ui/index.html').read_text(encoding='utf-8')
    app.state.store=store
    return app
