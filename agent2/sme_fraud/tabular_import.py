"""Bounded CSV/XLSX contract adapter, preserving source bytes in SnapshotStore."""
import csv
from datetime import datetime,date,timezone,timedelta
from functools import lru_cache
import io
import re
import zipfile
from finance_input.json_io import loads
from finance_input import schema,SUPPORTED_CONTRACT_VERSIONS
from .imports import DEFINITIONS,parse_vnd

VERSION='tabular-contract/1.0.0'
MAX_ROWS=100000
VN=timezone(timedelta(hours=7))
IDS={'record_id','tenant_id','company_id','bank_account','bank_code','tax_id','phone','number'}
CONTAINERS={'source','accounting_lines','subject_refs','invoice_refs','transaction_refs','allocation_refs','manifest','record_counts','missing_fields','payroll_period','verification','vendor_ref','employee_ref','created_by_ref','transaction_ref','invoice_ref','adjusts_ref'}
_DIGITS_RE=re.compile(r'[0-9]+\Z')


class TabularError(ValueError):
    def __init__(self,code,message,action,**detail):self.code,self.message,self.action,self.detail=code,message,action,detail;super().__init__(message)


def bad(code,message,action,**detail):raise TabularError(code,message,action,**detail)


@lru_cache(maxsize=65536)
def _parse_time_str(raw,fmt):
    try:
        parsed=datetime.fromisoformat(raw)
        if 'T' not in raw and ' ' not in raw:raise ValueError()
        return parsed.replace(tzinfo=VN).isoformat() if parsed.utcoffset() is None else raw
    except ValueError:
        if fmt in ('dmy','mdy'):
            for pattern in (('%d/%m/%Y %H:%M:%S','%d/%m/%Y %H:%M') if fmt=='dmy' else ('%m/%d/%Y %H:%M:%S','%m/%d/%Y %H:%M')):
                try:return datetime.strptime(raw,pattern).replace(tzinfo=VN).isoformat()
                except ValueError:pass
        return None


def value(raw,name,fmt,where,_flags=None):
    if raw is None or raw=='':return None
    if _flags is None:
        leaf=name.split('.')[-1]
        is_id=leaf in IDS;is_cont=leaf in CONTAINERS;is_vnd=leaf.endswith('_vnd')
        is_rev=leaf=='revision';is_bool=leaf.startswith('is_')
        is_time=leaf.endswith('_at') or leaf in ('covered_from','covered_through')
    else:
        is_id,is_cont,is_vnd,is_rev,is_bool,is_time=_flags
    if is_id and not isinstance(raw,str):bad('IDENTIFIER_TEXT','Mã định danh phải là Text để giữ số 0 đầu.','Xuất lại mã từ nguồn dưới dạng Text; không tự thêm lại số 0 đã mất.',**where)
    if is_cont and isinstance(raw,str) and raw.lstrip().startswith(('{','[')):
        try:return loads(raw)
        except (ValueError,UnicodeError):bad('CELL_JSON','Nội dung cấu trúc trong ô không phải JSON hợp lệ.','Sửa JSON trong ô hoặc dùng các cột con như vendor_ref.record_id.',**where)
    if is_vnd:
        if type(raw) in (int,float) and abs(raw)>=10**15:bad('MONEY_TEXT','Số tiền lớn trong Excel cần lưu dưới dạng Text để tránh làm tròn.','Xuất lại số tiền nguyên từ nguồn dưới dạng Text.',**where)
        try:return parse_vnd(raw)
        except (ValueError,TypeError):bad('MONEY_FORMAT','Số tiền VND không hợp lệ hoặc có dấu phân nhóm/phần lẻ.','Dùng số nguyên VND có dấu; không dùng dấu phân nhóm.',**where)
    if is_rev:
        if type(raw) is int:return raw
        if isinstance(raw,str) and _DIGITS_RE.fullmatch(raw):return int(raw)
        bad('REVISION_FORMAT','Phiên bản phải là số nguyên.','Nhập revision từ 1.',**where)
    if is_bool:
        if type(raw) is bool:return raw
        if isinstance(raw,str):
            low=raw.lower()
            if low in ('true','false'):return low=='true'
        bad('BOOLEAN_FORMAT','Trường này cần true hoặc false.','Dùng true/false hoặc ô Boolean trong Excel.',**where)
    if isinstance(raw,datetime):return (raw.replace(tzinfo=VN) if raw.utcoffset() is None else raw).isoformat()
    if isinstance(raw,date):return raw.isoformat()
    if is_time and isinstance(raw,str):
        norm=_parse_time_str(raw,fmt)
        if norm is not None:return norm
        bad('TIME_FORMAT','Thời gian thiếu giờ hoặc có định dạng chưa được xác nhận.','Dùng YYYY-MM-DD HH:MM[:SS], hoặc chọn ngày/tháng hay tháng/ngày trong Tùy chọn nhập tệp.',**where)
    return raw


def _compile_plan(names,table_map,where):
    plan=[]
    for index,header in enumerate(names,1):
        if not header:
            plan.append((index,'',None,None,None))
            continue
        target=table_map.get(header,header)
        parts=tuple(target.split('.'))
        if any(not p or len(p)>128 for p in parts):
            bad('COLUMN_PATH','Tên cột không hợp lệ.','Dùng tên cột trong tệp mẫu.',field=header,**where)
        leaf=parts[-1]
        flags=(leaf in IDS,leaf in CONTAINERS,leaf.endswith('_vnd'),leaf=='revision',leaf.startswith('is_'),leaf.endswith('_at') or leaf in ('covered_from','covered_through'))
        plan.append((index,header,target,parts,flags))
    return plan


def record(headers,cells,mapping,fmt,where,_plan=None):
    row={}
    plan=_plan if _plan is not None else _compile_plan(headers,mapping,where)
    for (index,header,target,parts,flags),raw in zip(plan,cells):
        if not header:
            if raw is not None and raw!='':bad('COLUMN_HEADER','Ô có dữ liệu nhưng thiếu tên cột.','Bổ sung tên cột ở dòng đầu.',column=index,**where)
            continue
        if raw is None or raw=='':continue
        parsed=value(raw,target,fmt,dict(where,field=header,column=index),flags)
        if parsed is None:continue
        if len(parts)==1:
            key_leaf=parts[0]
            if key_leaf in row:bad('COLUMN_CONFLICT','Các cột cùng ghi vào một trường.','Sửa tên cột hoặc mapping để không ghi đè.',field=header,**where)
            row[key_leaf]=parsed
        else:
            cursor=row
            for part in parts[:-1]:
                existing=cursor.get(part)
                if existing is not None and not isinstance(existing,dict):bad('COLUMN_CONFLICT','Các cột cùng ghi vào một trường.','Giữ một cột gốc hoặc các cột con, không dùng cả hai.',field=header,**where)
                if existing is None:
                    existing={};cursor[part]=existing
                cursor=existing
            if parts[-1] in cursor:bad('COLUMN_CONFLICT','Các cột cùng ghi vào một trường.','Sửa tên cột hoặc mapping để không ghi đè.',field=header,**where)
            cursor[parts[-1]]=parsed
    return row


def headers(values,where):
    result=[str(v).strip() if v is not None else '' for v in values]
    non_empty=[v for v in result if v]
    if len(result)>256 or len(non_empty)!=len(set(non_empty)):bad('COLUMN_HEADER','Tên cột trùng hoặc quá 256 cột.','Sửa tên cột trùng; bỏ các cột không dùng.',**where)
    return result


def parse(raw,filename,mapping):
    data={};locations={};metadata=[];total=0;fmt=mapping.get('date_format','iso')
    plans={}
    table_mappings=mapping.get('tables',{})
    def append(table,names,cells,where,plan_key=None):
        nonlocal total
        if not any(v is not None and v!='' for v in cells):return
        if table not in DEFINITIONS and table!='metadata':bad('TABLE_NAME','Tên bảng/sheet chưa được hỗ trợ.','Dùng tên bảng trong tệp mẫu.',**where)
        pkey=(table,plan_key) if plan_key is not None else None
        plan=plans.get(pkey) if pkey is not None else None
        if plan is None:
            plan=_compile_plan(names,table_mappings.get(table,{}),where)
            if pkey is not None:plans[pkey]=plan
        row=record(names,cells,table_mappings.get(table,{}),fmt,where,plan)
        if table=='metadata':metadata.append(row);return
        total+=1
        if total>MAX_ROWS:bad('ROW_LIMIT','Tệp vượt 100.000 bản ghi.','Chia gói nhưng giữ đủ nguồn tham chiếu.',**where)
        records=data.setdefault(table,[]);locations[f'/{table}/{len(records)}']=where;records.append(row)
    if filename.lower().endswith('.csv'):
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:bad('CSV_ENCODING','CSV chưa phải UTF-8.','Xuất lại CSV UTF-8 từ Excel hoặc hệ thống nguồn.')
        try:
            first_line=text.partition('\n')[0]
            dialect=csv.Sniffer().sniff(first_line,delimiters=',;\t')
            dialect.doublequote=True;dialect.quotechar='"'
            rows=csv.reader(io.StringIO(text,newline=''),dialect)
            names=headers(next(rows),dict(csv_row=1))
            if not names or names[0]!='table':bad('CSV_TABLE','CSV cần cột đầu tiên table để phân biệt các nguồn.','Tải mẫu CSV; dùng metadata, companies, transactions, invoices… trong cột table.')
            body_names=names[1:];ncols=len(names)
            for cells in rows:
                if not any(cells):continue
                if len(cells)!=ncols:bad('CSV_WIDTH','Số ô không khớp số cột.','Sửa dấu phân cách hoặc dấu nháy của dòng này.',csv_row=rows.line_num)
                append(cells[0],body_names,cells[1:],dict(csv_row=rows.line_num),'csv')
        except (csv.Error,StopIteration):bad('CSV_FORMAT','Không đọc được cấu trúc CSV.','Dùng mẫu CSV UTF-8, giữ dòng tiêu đề và dấu phân cách nhất quán.')
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                info=archive.infolist()
                if len(info)>200 or sum(x.file_size for x in info)>80*1024*1024 or any('vbaproject' in x.filename.lower() for x in info):bad('EXCEL_LIMIT','Excel vượt giới hạn giải nén hoặc chứa macro.','Dùng .xlsx không macro, tối đa 80 MB sau giải nén.')
                for member in info:
                    if member.filename.endswith('.xml'):
                        xml=archive.read(member).upper()
                        if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:bad('EXCEL_XML','Excel chứa cấu trúc XML không được hỗ trợ.','Xuất lại .xlsx từ nguồn tin cậy.')
            from openpyxl import load_workbook
            book=load_workbook(io.BytesIO(raw),read_only=True,data_only=False,keep_links=False)
        except ImportError:bad('EXCEL_DEPENDENCY','Backend chưa cài bộ đọc Excel.','Người vận hành cài openpyxl theo requirements.')
        except TabularError:raise
        except (zipfile.BadZipFile,OSError,ValueError,KeyError):bad('EXCEL_FORMAT','Không đọc được tệp Excel .xlsx.','Xuất lại .xlsx không mật khẩu, không macro.')
        try:
            if len(book.worksheets)>len(DEFINITIONS)+1:bad('EXCEL_SHEETS','Excel có quá nhiều sheet.','Giữ các sheet theo hợp đồng dữ liệu.')
            for sheet in book:
                if sheet.max_row is not None and sheet.max_row>MAX_ROWS+1 or sheet.max_column is not None and sheet.max_column>256:bad('EXCEL_DIMENSIONS','Sheet vượt giới hạn hàng hoặc cột.','Bỏ định dạng thừa ngoài vùng dữ liệu.',sheet=sheet.title)
                iterator=sheet.iter_rows();first=next(iterator,None)
                if first is None:continue
                if any(c.data_type=='f' for c in first):bad('EXCEL_FORMULA','Tiêu đề không được là công thức.','Dùng tên cột dạng Text.',sheet=sheet.title,row=1)
                names=headers([c.value for c in first],dict(sheet=sheet.title,row=1))
                for index,cells in enumerate(iterator,2):
                    if any(c.data_type=='f' for c in cells):bad('EXCEL_FORMULA','Tệp còn công thức chưa được xác nhận giá trị.','Xuất bản chỉ chứa giá trị trước khi nhập.',sheet=sheet.title,row=index)
                    append(sheet.title,names,[c.value for c in cells],dict(sheet=sheet.title,row=index),sheet.title)
        finally:book.close()
    if len(metadata)!=1 or set(metadata[0])!={'contract_version','tenant_id'}:bad('FILE_METADATA','Cần đúng một dòng metadata gồm contract_version và tenant_id.','Dùng sheet/dòng metadata trong tệp mẫu; không đưa quyền truy cập vào tệp.')
    data.update(metadata[0])
    if data['contract_version'] in SUPPORTED_CONTRACT_VERSIONS:
        properties=schema(data['contract_version'])['properties']
        for table in DEFINITIONS:
            if table in properties:data.setdefault(table,[])
    return data,locations
