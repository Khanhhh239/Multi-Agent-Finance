"""Company-scoped, lossless multi-source tabular intake for the 35-rule profile."""
import base64
from copy import deepcopy
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import math
from pathlib import Path
import re
import zipfile

from finance_input.json_io import loads
from .exception_validation import PROFILES,validated_record
from .import_files import canonical, digest, fail, MAX_BYTES
from .native_rule_node import TABLES, CORE_FIELDS, FORBIDDEN, VERSION as NATIVE_VERSION
from .tabular_import import TabularError, bad, headers

VERSION='rule-source-intake/1.0.0'
PACKAGE='agent2-source-files/1.0.0'
PROFILE='agent2-rule-snapshot/1.0.0'
SPECIAL=('metadata','coverage','candidates')
# Required by the retained engine's accounting transport, never invented from
# a payment amount or filled with 0. Optional proof tables remain optional.
ENGINE_FIELDS=('journal_signature','accounting_purpose','recognised_input_vat_vnd',
               'recognised_output_vat_vnd','writeoff_provision_vnd','production_cost_vnd','evidence_on_file')
FIELD=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')
FLAGS={'saturday_operations','contract_on_file','is_holiday','evidence_on_file','is_financial_entry',
       'goods_receipt_verified','callback_verified','self_approval_allowed','cancellation_log_complete',
       'required','allow_override','normal_workflow_completed','alternative_work_evidence',
       'allow_partial','holiday_work_allowed','leave_request_required'}


def required_fields():
    from .authority_policy import AUTHORITY_REQUIRED,COVERAGE_REQUIRED
    result={name:set(CORE_FIELDS.get(name,()))|set(PROFILES.get(name,{}).get('required',()))|{'company_id','observed_at'} for name in TABLES}
    result['approval_authorities'].update(AUTHORITY_REQUIRED);result['approval_authority_coverage'].update(COVERAGE_REQUIRED)
    result['transactions'].update(ENGINE_FIELDS)
    result['journal_documents'].update(('document_id','transaction_id','posted_at','purpose'))
    result['journal_lines'].update(('document_id','transaction_id','posted_at','account_code','debit_vnd','credit_vnd'))
    result['entity_links'].update(('source_id','target_id','link_type'))
    result['vendor_status_history'].update(('vendor_id','status','effective_at'))
    from .tax_risk import FIELDS as TAX_FIELDS
    result['tax_risk_history'].update(TAX_FIELDS)
    return result


def catalogue():
    result={name:set(CORE_FIELDS.get(name,()))|{'company_id','observed_at'} for name in TABLES}
    for name,spec in PROFILES.items():
        if name in result:result[name].update(spec['required']);result[name].update(spec['fields'])
    root=Path(__file__).parent
    for filename in ('authority_policy.schema.json','payment_evidence.schema.json','evidence_sources.schema.json'):
        for name,spec in loads((root/filename).read_bytes()).get('tables',{}).items():
            if name in result:
                result[name].update(spec.get('required',()));result[name].update(spec.get('fields',()))
    result['transactions'].update(ENGINE_FIELDS)
    result['journal_documents'].update(('document_id','transaction_id','posted_at','purpose'))
    result['journal_lines'].update(('document_id','line_id','transaction_id','posted_at','account_code','debit_vnd','credit_vnd'))
    result['metadata']={'contract_version','tenant_id','company_id','as_of','source_id','is_simulated'}
    result['coverage']={'table_name','status','observed_at','covered_from','covered_through','history_basis'}
    result['candidates']={'transaction_id'}
    for name,required in required_fields().items():result[name].update(required)
    result['entity_links'].update(('status','bank_code'));result['journal_lines'].add('line_id')
    return {name:sorted(fields-FORBIDDEN) for name,fields in result.items()}


def mapping(value):
    allowed={'profile','tables','sources','metadata','coverage','candidate_transaction_ids','candidate_selection','date_format'}
    if not isinstance(value,dict) or set(value)-allowed or value.get('profile')!='rule_sources':
        fail(422,'MAPPING_INVALID','Thiết lập nhập nhiều nguồn không hợp lệ.','Chọn lại loại dữ liệu và kiểm tra lại.')
    result={'profile':'rule_sources'}
    for group in ('tables','sources','metadata','coverage'):
        if not isinstance(value.get(group,{}),dict):fail(422,'MAPPING_INVALID','Thiết lập phải là đối tượng.','Kiểm tra '+group+'.')
        result[group]=value.get(group,{})
    for table,columns in result['tables'].items():
        if table not in (*TABLES,*SPECIAL) or not isinstance(columns,dict):fail(422,'MAPPING_TABLE','Bảng ánh xạ không hợp lệ.','Chọn bảng nguồn trong danh sách.')
        for source,target in columns.items():
            if not isinstance(source,str) or not 1<=len(source)<=128 or not isinstance(target,str) or not FIELD.fullmatch(target) or target in FORBIDDEN:
                fail(422,'MAPPING_FIELD','Cột đích không hợp lệ.','Chỉ đổi tên cột, không dùng biểu thức, nhãn hay giá trị mặc định.')
        if len(set(columns.values()))!=len(columns):fail(422,'MAPPING_COLLISION','Hai cột trỏ cùng một trường.','Mỗi trường chỉ nhận một cột nguồn.')
    for key,table in result['sources'].items():
        if not isinstance(key,str) or len(key)>200 or table not in (*TABLES,*SPECIAL):fail(422,'MAPPING_TABLE','Nguồn hoặc bảng đích không hợp lệ.','Chọn lại bảng cho từng tệp/sheet.')
    if set(result['metadata'])-{'as_of','source_id','is_simulated'}:fail(422,'MAPPING_METADATA','Thông tin gói có trường không được phép.','Quyền và phạm vi doanh nghiệp do server kiểm tra.')
    for key,item in result['metadata'].items():
        if key=='is_simulated' and type(item) is not bool or key!='is_simulated' and (not isinstance(item,str) or len(item)>128):
            fail(422,'MAPPING_METADATA','Sai kiểu dữ liệu của thông tin gói.','Mốc/tên nguồn dùng chuỗi; loại mô phỏng dùng Boolean.')
    for table,claim in result['coverage'].items():
        if table in TABLES and claim is None:continue  # Explicitly withdraw an imported claim.
        if table not in TABLES or not isinstance(claim,dict) or set(claim)-{'status','observed_at','covered_from','covered_through','history_basis'}:
            fail(422,'MAPPING_COVERAGE','Khai báo lịch sử không hợp lệ.','Khai báo phạm vi từng bảng; không gửi checksum hoặc số dòng tự tạo.')
        if any(not isinstance(v,str) or len(v)>128 for v in claim.values()):fail(422,'MAPPING_COVERAGE','Trường phạm vi phải là chuỗi.','Chọn mức đầy đủ, loại lịch sử và các mốc thời gian.')
    ids=value.get('candidate_transaction_ids')
    if ids is not None:
        if not isinstance(ids,list) or not 1<=len(ids)<=200 or any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
            fail(422,'RULE_CANDIDATES_INVALID','Chọn 1–200 mã ứng viên duy nhất.','Giữ lịch sử đầy đủ, chỉ giới hạn danh sách cần phân tích.')
        result['candidate_transaction_ids']=ids
    if value.get('candidate_selection') is not None:
        if value['candidate_selection']!='all' or ids is not None:fail(422,'RULE_CANDIDATES_INVALID','Cách chọn ứng viên không hợp lệ.','Chọn danh sách cụ thể hoặc toàn bộ giao dịch.')
        result['candidate_selection']='all'
    fmt=value.get('date_format','iso')
    if fmt not in ('iso','dmy','mdy'):fail(422,'DATE_MAPPING','Định dạng ngày không hợp lệ.','Chọn ISO, ngày/tháng hoặc tháng/ngày.')
    result['date_format']=fmt
    return result


def files(raw,filename):
    if filename.lower().endswith('.json'):
        try:package=loads(raw)
        except (ValueError,UnicodeError):bad('SOURCE_PACKAGE','Gói tệp không hợp lệ.','Chọn lại các CSV nguồn.')
        if not isinstance(package,dict) or set(package)!={'format','files'} or package['format']!=PACKAGE or not isinstance(package['files'],list) or not 1<=len(package['files'])<=len(TABLES)+3:
            bad('SOURCE_PACKAGE','Gói cần danh sách các tệp CSV.','Chọn CSV hoặc một Excel nhiều sheet.')
        result=[];seen=set();total=0
        for item in package['files']:
            if not isinstance(item,dict) or set(item)!={'name','content_b64'}:bad('SOURCE_PACKAGE','Thông tin tệp không hợp lệ.','Chọn lại các tệp.')
            name=item['name']
            if not isinstance(name,str) or not 1<=len(name)<=180 or any(c in name for c in '/\\:\x00') or not name.lower().endswith('.csv') or name in seen:
                bad('SOURCE_FILE_NAME','Tên CSV không hợp lệ hoặc trùng nhau.','Đổi tên để mỗi CSV nguồn có một tên duy nhất.')
            try:content=base64.b64decode(item['content_b64'],validate=True)
            except (ValueError,TypeError):bad('SOURCE_PACKAGE','Không đọc được nội dung CSV.','Chọn lại tệp nguồn.')
            total+=len(content)
            if total>MAX_BYTES:bad('FILE_SIZE','Tổng tệp nguồn vượt 10 MB.','Giảm kích thước xuất nhưng không cắt lịch sử cần phân tích.')
            seen.add(name);result.append((name,content))
        return result
    return [(filename,raw)]


def read_sources(raw,filename):
    result=[];total=0
    for name,content in files(raw,filename):
        if name.lower().endswith('.csv'):
            try:
                text=content.decode('utf-8-sig')
                try:dialect=csv.Sniffer().sniff(text.splitlines()[0],delimiters=',;\t')
                except csv.Error:
                    if any(c in text.splitlines()[0] for c in ',;\t'):raise
                    dialect=csv.excel
                dialect.doublequote=True;rows=csv.reader(io.StringIO(text,newline=''),dialect)
                cols=headers(next(rows),{'file':name,'csv_row':1});records=[]
                for row in rows:
                    if not any(row):continue
                    if len(row)!=len(cols):bad('CSV_WIDTH','Số ô không khớp tên cột.','Sửa dấu phân cách hoặc dấu nháy.',file=name,csv_row=rows.line_num)
                    total+=1;records.append((row,{'file':name,'csv_row':rows.line_num}))
                    if total>30000:bad('ROW_LIMIT','Gói vượt 30.000 dòng nguồn.','Giữ phạm vi nguồn đúng và chọn tối đa 200 ứng viên.')
                # Single multi-table CSV uses the same names as the Excel sheets.
                if cols and cols[0]=='table':
                    groups={}
                    for row,where in records:groups.setdefault(row[0],[]).append((row[1:],where))
                    result.extend(dict(key=table,table=table,headers=cols[1:],rows=r,file=name) for table,r in groups.items())
                else:result.append(dict(key=name,table=name.rsplit('.',1)[0],headers=cols,rows=records,file=name))
            except (UnicodeError,csv.Error,StopIteration,IndexError):bad('CSV_FORMAT','Không đọc được CSV UTF-8.','Dùng dòng tiêu đề và dấu phân cách nhất quán.',file=name)
        elif name.lower().endswith('.xlsx'):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    items=archive.infolist()
                    if len(items)>500 or sum(x.file_size for x in items)>40*1024*1024 or any('vbaproject' in x.filename.lower() for x in items):
                        bad('EXCEL_LIMIT','Excel vượt giới hạn hoặc chứa macro.','Dùng .xlsx không macro, tối đa 40 MB sau giải nén.')
                    for item in items:
                        if item.filename.endswith('.xml') and re.search(b'<!DOCTYPE|<!ENTITY',archive.read(item).upper()):bad('EXCEL_XML','Cấu trúc Excel không được hỗ trợ.','Xuất lại .xlsx từ nguồn.')
                from openpyxl import load_workbook
                book=load_workbook(io.BytesIO(content),read_only=True,data_only=False,keep_links=False)
                try:
                    if len(book.worksheets)>len(TABLES)+3:bad('EXCEL_SHEETS','Quá nhiều bảng nguồn.','Dùng các sheet trong tệp mẫu.')
                    for sheet in book:
                        if sheet.max_row and sheet.max_row>30001 or sheet.max_column and sheet.max_column>256:bad('EXCEL_DIMENSIONS','Sheet vượt giới hạn.','Xóa định dạng thừa ngoài vùng dữ liệu.',sheet=sheet.title)
                        iterator=sheet.iter_rows();first=next(iterator,None)
                        if first is None:continue
                        cols=headers([c.value for c in first],{'sheet':sheet.title,'row':1});records=[]
                        if any(c.data_type=='f' for c in first):bad('EXCEL_FORMULA','Tên cột không được là công thức.','Dùng tên cột dạng Text.',sheet=sheet.title,row=1)
                        for index,cells in enumerate(iterator,2):
                            if not any(c.value is not None for c in cells):continue
                            if any(c.data_type=='f' for c in cells):bad('EXCEL_FORMULA','Ô dữ liệu còn công thức.','Xuất bản chỉ chứa giá trị.',sheet=sheet.title,row=index)
                            total+=1
                            if total>30000:bad('ROW_LIMIT','Gói vượt 30.000 dòng nguồn.','Không cắt bỏ lịch sử để vượt giới hạn.')
                            records.append(([c.value for c in cells],{'sheet':sheet.title,'row':index}))
                        result.append(dict(key=sheet.title,table=sheet.title,headers=cols,rows=records,file=name))
                finally:book.close()
            except TabularError:raise
            except (zipfile.BadZipFile,KeyError,ValueError,OSError):bad('EXCEL_FORMAT','Không đọc được Excel.','Dùng .xlsx không mật khẩu hoặc macro.')
        else:bad('FILE_FORMAT','Nhập nhiều nguồn nhận CSV hoặc Excel .xlsx.','Dùng chế độ nhập chuẩn cho JSON snapshot có sẵn.')
    if not result:bad('SOURCE_EMPTY','Chưa tìm thấy bảng nguồn.','Tải các tệp có dòng tiêu đề.')
    if len({s['key'] for s in result})!=len(result):bad('SOURCE_DUPLICATE','Trùng tên nguồn trong gói.','Đổi tên CSV/sheet để ánh xạ riêng từng bảng.')
    return result


def inspect(raw,filename):
    sources=read_sources(raw,filename);fields=catalogue();metadata={};coverage={};candidates=[]
    for source in sources:
        if source['table'] in SPECIAL:
            rows=[{k:(scalar(v,k,'iso',{}) if isinstance(v,(datetime,date)) else v) for k,v in zip(source['headers'],cells)} for cells,_ in source['rows']]
            if source['table']=='metadata' and len(rows)==1:metadata=rows[0]
            elif source['table']=='coverage':coverage={r.get('table_name'):r for r in rows}
            elif source['table']=='candidates':candidates=[r.get('transaction_id') for r in rows]
    required={name:sorted(fields) for name,fields in required_fields().items()}
    return dict(version=VERSION,source_hash=digest(raw),fields=fields,required_fields=required,metadata=metadata,coverage=coverage,candidate_transaction_ids=candidates,
                sources=[dict(key=s['key'],suggested_table=s['table'] if s['table'] in fields else '',file=s['file'],headers=s['headers'],row_count=len(s['rows'])) for s in sources])


def scalar(raw,field,fmt,where,kind=None):
    if raw is None or raw=='':return ''
    if field.endswith('_id') or field in ('bank_account','bank_code','phone','account_code','invoice_number','recipient_account','tax_id','tax_code') or field.endswith('_account'):
        if not isinstance(raw,str):bad('IDENTIFIER_TEXT','Mã định danh phải là Text để giữ số 0 đầu.','Xuất lại cột dạng Text từ nguồn.',field=field,**where)
    if field.endswith('_vnd') or kind in ('integer','integer?','positive','days','workdays','year','flag') or field in FLAGS or field=='support_doc_count':
        if isinstance(raw,str) and re.fullmatch(r'-?[0-9]+',raw):return int(raw)
        if type(raw) is int:return raw
        if type(raw) is bool and (field in FLAGS or kind=='flag'):return int(raw)
        bad('NUMBER_FORMAT','Cần số nguyên, không dấu phân nhóm hoặc phần lẻ.','Dùng số nguyên VND có dấu; cờ dữ liệu dùng 0/1.',field=field,**where)
    if type(raw) is float and not math.isfinite(raw):bad('NUMBER_FORMAT','Số không hữu hạn.','Sửa số từ nguồn.',field=field,**where)
    if isinstance(raw,datetime):
        if raw.microsecond:bad('TIME_PRECISION','Mốc thời gian có phần nhỏ hơn một giây.','Xuất mốc giây từ nguồn theo hợp đồng; hệ thống không tự làm tròn thời gian.',field=field,**where)
        if kind in ('date','date?') or field in ('date','effective_date','hire_date','termination_date','period_start','period_end','service_period_start','service_period_end'):return raw.date().isoformat()
        return raw.isoformat(timespec='seconds') if raw.utcoffset() else raw.isoformat(timespec='seconds')+'+07:00'
    if isinstance(raw,date):return raw.isoformat()
    if isinstance(raw,str) and (kind in ('date','date?') or field in ('date','effective_date','hire_date','termination_date','period_start','period_end','service_period_start','service_period_end')
                               or field in ('effective_from','effective_to','expires_at') and len(raw)==10):
        try:return date.fromisoformat(raw).isoformat()
        except ValueError:
            if fmt in ('dmy','mdy'):
                try:return datetime.strptime(raw,'%d/%m/%Y' if fmt=='dmy' else '%m/%d/%Y').date().isoformat()
                except ValueError:pass
            bad('DATE_FORMAT','Ngày không đúng định dạng đã chọn.','Dùng YYYY-MM-DD hoặc xác nhận ngày/tháng trong Tùy chọn nhập tệp.',field=field,**where)
    if field.endswith('_at') or field in ('as_of','covered_from','covered_through') or kind in ('timestamp','timestamp?','date_or_timestamp'):
        if field in ('covered_from','covered_through') and isinstance(raw,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):return raw
        if not isinstance(raw,str):bad('TIME_FORMAT','Thời gian cần ô ngày giờ hoặc chuỗi có định dạng rõ ràng.','Dùng YYYY-MM-DD HH:MM[:SS] hoặc định dạng ngày đã chọn.',field=field,**where)
        from .tabular_import import value
        parsed=value(raw,'observed_at',fmt,where)
        instant=datetime.fromisoformat(parsed)
        if instant.microsecond:bad('TIME_PRECISION','Mốc thời gian có phần nhỏ hơn một giây.','Xuất mốc giây từ nguồn theo hợp đồng; không tự làm tròn thời gian.',field=field,**where)
        return instant.astimezone(timezone(timedelta(hours=7))).isoformat(timespec='seconds')
    return raw


def parse(raw,filename,settings,scope):
    sources=read_sources(raw,filename);settings=mapping(settings);data={};locations={};meta={};claims={};ids=[];seen=set()
    for source in sources:
        table=settings['sources'].get(source['key'],source['table'])
        if table not in (*TABLES,*SPECIAL):bad('TABLE_NAME','Chưa chọn bảng cho nguồn '+source['key']+'.','Chọn bảng đích trước khi kiểm tra.',file=source['file'])
        if table in seen:bad('TABLE_DUPLICATE','Hai nguồn cùng trỏ một bảng.','Gộp đúng bảng tại nguồn hoặc chọn lại bảng đích.',table=table)
        seen.add(table)
        rows=[];required=required_fields().get(table,set())
        for cells,where in source['rows']:
            row={};columns=settings['tables'].get(table,{})
            for column,(header,cell) in enumerate(zip(source['headers'],cells),1):
                if not header:
                    if cell not in ('',None):bad('COLUMN_HEADER','Ô có dữ liệu nhưng thiếu tên cột.','Bổ sung tên cột rồi tải lại tệp.',column=column,**where)
                    continue
                target=columns.get(header,header)
                if target in row:bad('MAPPING_COLLISION','Hai cột ghi vào cùng trường.','Sửa ánh xạ rồi kiểm tra lại.',field=target,**where)
                if cell in ('',None) and target not in required:continue
                if cell in ('',None) and target in required and target.endswith('_vnd'):
                    bad('VALUE_REQUIRED','Chưa có giá trị nguồn cho '+target+'.','Bổ sung số tiền đã biết từ nguồn; không dùng 0 thay dữ liệu chưa biết.',field=target,table=table,**where)
                if target.endswith('_vnd') and type(cell) in (int,float) and abs(cell)>=10**15:
                    bad('MONEY_TEXT','Tiền lớn trong Excel cần lưu dạng Text để tránh mất chữ số.','Xuất lại số nguyên từ nguồn dưới dạng Text.',field=target,**where)
                row[target]=scalar(cell,target,settings['date_format'],where,PROFILES.get(table,{}).get('fields',{}).get(target))
            for field in required:
                if field not in row:bad('COLUMN_REQUIRED','Thiếu cột '+field+'.','Ánh xạ cột nguồn tương ứng; không tự điền 0 hoặc tạo bằng chứng.',field=field,table=table,**where)
            if table in PROFILES:
                try:validated_record(table,row,signed_amounts=True)
                except (ValueError,TypeError) as error:
                    match=re.search(r'\.([A-Za-z_][A-Za-z0-9_]*):',str(error))
                    bad('SOURCE_FIELD_INVALID','Giá trị nguồn không đúng hợp đồng: '+str(error),
                        'Sửa trường được nêu từ nguồn hoặc ánh xạ lại cột; không tự điền số 0 hay tạo bằng chứng.',field=match[1] if match else None,table=table,**where)
            locations[f'source.{table}[{len(rows)+1}]']=where
            locations[f'source.tables.{table}.{len(rows)}']=where;rows.append(row)
        if table=='metadata':
            if len(rows)>1:bad('FILE_METADATA','Chỉ nhận một dòng metadata.','Giữ thông tin cho một doanh nghiệp.')
            if any(set(r)-{'contract_version','tenant_id','company_id','as_of','source_id','is_simulated'} for r in rows):bad('FILE_METADATA','Metadata có cột ngoài hợp đồng.','Chỉ khai báo phiên bản, doanh nghiệp, mốc và tên/loại nguồn; không đưa quyền vào tệp.')
            meta.update(rows[0] if rows else {})
        elif table=='coverage':
            for row in rows:
                name=row.pop('table_name',None)
                if name not in TABLES or name in claims:bad('SOURCE_COVERAGE','Bảng phạm vi không hợp lệ hoặc trùng.','Mỗi bảng có một khai báo phạm vi.')
                if set(row)-{'status','observed_at','covered_from','covered_through','history_basis'}:bad('SOURCE_COVERAGE','Bảng coverage có cột không được hỗ trợ.','Số dòng và checksum được server tính sau ánh xạ; không dùng manifest cũ.')
                claims[name]=row
        elif table=='candidates':ids=[r.get('transaction_id') for r in rows]
        else:data[table]=rows
    for key,value in settings['metadata'].items():
        if value not in ('',None):meta[key]=value
    if meta.get('tenant_id',scope.tenant_id)!=scope.tenant_id or meta.get('company_id',next(iter(scope.company_ids)))!=next(iter(scope.company_ids)):
        bad('ACCESS_DENIED','Metadata ngoài doanh nghiệp được cấp quyền.','Chọn đúng doanh nghiệp; không đổi mã bản ghi để chuyển dữ liệu.')
    if meta.get('contract_version',PROFILE)!=PROFILE:bad('SOURCE_PROFILE','Tệp không thuộc profile 35 luật.','Chọn loại nhập chuẩn cho tệp canonical cũ.')
    for name in ('as_of','source_id','is_simulated'):
        if name not in meta or meta[name]=='':bad('SOURCE_METADATA','Thiếu '+name+' của gói nguồn.','Khai báo mốc phân tích, tên nguồn và dữ liệu mô phỏng/thật.',field=name)
    if isinstance(meta['is_simulated'],str) and meta['is_simulated'].lower() in ('true','false'):meta['is_simulated']=meta['is_simulated'].lower()=='true'
    if type(meta['is_simulated']) is not bool:bad('SOURCE_METADATA','Cần xác nhận dữ liệu mô phỏng hay thật.','Chọn loại nguồn dữ liệu.',field='is_simulated')
    cutoff=scalar(meta['as_of'],'as_of',settings['date_format'],{})
    for table,claim in settings['coverage'].items():
        if table not in data:bad('SOURCE_COVERAGE','Khai báo phạm vi cho bảng chưa tải lên.','Tải bảng tương ứng hoặc bỏ khai báo.',table=table)
        if claim is None:claims.pop(table,None)
        else:claims[table]=dict(claim)
    coverage={}
    for table,claim in claims.items():
        if table not in data:bad('SOURCE_COVERAGE','Khai báo phạm vi cho bảng chưa tải lên.','Tải bảng tương ứng hoặc bỏ khai báo.',table=table)
        claim=dict(claim)
        for f in ('observed_at','covered_from','covered_through'):
            if f in claim:claim[f]=scalar(claim[f],f,settings['date_format'],{})
        claim.update(record_count=len(data[table]),records_sha256=digest(canonical(data[table])))
        coverage[table]=claim
    ids=([r['transaction_id'] for r in data.get('transactions',[])] if settings.get('candidate_selection')=='all' else settings.get('candidate_transaction_ids',ids))
    if len(ids)>200:bad('RULE_CANDIDATES_INVALID','Có hơn 200 giao dịch ứng viên.','Chọn danh sách cần phân tích; giữ nguyên toàn bộ lịch sử trong bảng giao dịch.')
    if not ids:bad('RULE_CANDIDATES_REQUIRED','Chưa chọn giao dịch cần phân tích.','Nhập 1–200 mã ứng viên hoặc dùng sheet candidates; giữ lịch sử trong transactions.')
    source=dict(version=NATIVE_VERSION,tenant_id=scope.tenant_id,company_id=next(iter(scope.company_ids)),as_of=cutoff,source_id=meta['source_id'],is_simulated=meta['is_simulated'],tables=data,coverage=coverage)
    return dict(contract_version=PROFILE,tenant_id=scope.tenant_id,company_id=source['company_id'],source=source,candidate_transaction_ids=ids),locations


def readiness(data,scope):
    """Availability-only local evaluation; no scores, thresholds, fitting or HE."""
    from .native_rule_node import evaluate_bundle
    from .rule_snapshot import source_guards, PUBLIC_NAMES, SCOPE_RULES, ROW_KINDS
    from .rule_snapshot_visibility import visible
    from .import_files import ImportFailure
    try:native=source_guards(data,evaluate_bundle(data['source'],scope,candidate_transaction_ids=data['candidate_transaction_ids']))
    except ImportFailure as error:
        if error.code!='NATIVE_RULE_CORE_MISSING':raise
        from .rule_snapshot_visibility import unavailable_native
        native=unavailable_native(data['source'])
    by_id={r['transaction_id']:r for r in data['source']['tables']['transactions']};checks=[]
    guarded_by_id={identity:{r['rule_id']:r for r in source_guards(dict(data,candidate_transaction_ids=[identity]),dict(rules=deepcopy(native.get('row_rules',{}).get(identity,native['rules']))))['rules']}
                   for identity in data['candidate_transaction_ids']}
    for index,code in enumerate(PUBLIC_NAMES,1):
        scope_entry=next(r for r in native['rules'] if r['rule_id']==code)
        entries=[]
        if code in SCOPE_RULES:entries=[scope_entry]
        else:
            for identity in data['candidate_transaction_ids']:
                tx=by_id[identity]
                entry=guarded_by_id[identity][code]
                if not visible(tx,data['source']['as_of']):entry=dict(entry,available=False,status='unavailable',gaps=[dict(table='transactions',reason='transaction_not_visible_at_as_of')])
                elif code in ROW_KINDS and tx['txn_type'] not in ROW_KINDS[code]:entry=dict(entry,available=False,status='not_applicable',gaps=[])
                entries.append(entry)
        ready=sum(e['available'] for e in entries);missing=sum(not e['available'] and e['status']!='not_applicable' for e in entries);na=len(entries)-ready-missing
        gaps=list({(g.get('table'),g.get('reason'),g.get('field')):dict(table=g.get('table'),reason=g.get('reason'),field=g.get('field')) for e in entries for g in e['gaps']}.values())
        status='partial' if ready and missing else 'needs_data' if missing else 'ready' if ready else 'not_applicable'
        checks.append(dict(check_id=f'check_{index}',name=PUBLIC_NAMES[code],status=status,ready_count=ready,missing_count=missing,not_applicable_count=na,gaps=gaps))
    return dict(version=VERSION,meaning='Khả năng chạy trên nguồn đã khóa; không phải kết luận vi phạm hay hiệu quả phát hiện.',checks=checks,
                summary={s:sum(c['status']==s for c in checks) for s in ('ready','partial','needs_data','not_applicable')})
