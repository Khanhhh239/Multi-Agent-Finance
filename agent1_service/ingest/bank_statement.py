import hashlib
from datetime import date,timedelta
import pandas as pd
from .dates import local_dates
from .money import SCALES,major,minor

BANK_COLUMNS = {
    'vcb': {'Ngày giao dịch':'value_date','Số tiền ghi có':'amount','Tên đối tác':'counterparty','Nội dung':'memo'},
    'bidv': {'Ngày GD':'value_date','Ghi có':'amount','Đối tác':'counterparty','Diễn giải':'memo'},
    'tcb': {'Transaction Date':'value_date','Credit':'amount','Counterparty':'counterparty','Description':'memo'},
    'mb': {'Ngày hạch toán':'value_date','Phát sinh có':'amount','Đơn vị đối ứng':'counterparty','Nội dung':'memo'},
    'acb': {'Ngày':'value_date','Tiền vào':'amount','Tên người chuyển':'counterparty','Nội dung giao dịch':'memo'},
}

BANK_DEBITS = {'vcb':'Số tiền ghi nợ','bidv':'Ghi nợ','tcb':'Debit',
               'mb':'Phát sinh nợ','acb':'Tiền ra'}


def _day(value,field):
    if not isinstance(value,str) or len(value)!=10 or date.fromisoformat(value).isoformat()!=value:
        raise ValueError(f'{field} phải là YYYY-MM-DD')
    return value


def normalize_verified_statement(df,firm_id,bank,statement,existing=(),mapping=None,source=None,registry=None):
    """Admit a complete bank period, retaining debit evidence and credit model rows."""
    if not isinstance(statement,dict):raise ValueError('Cần metadata sao kê dạng JSON object')
    required={'account_id','currency','period_start','period_end','opening_balance',
              'closing_balance','total_credits','total_debits'}
    if required-set(statement):raise ValueError(f'Thiếu metadata sao kê: {sorted(required-set(statement))}')
    if not isinstance(statement['account_id'],str):
        raise ValueError('account_id phải là chuỗi để giữ số 0 đầu')
    account=statement['account_id'].strip()
    currency=str(statement['currency']).upper()
    if registry is None:
        raise ValueError('Chưa có danh mục tài khoản ngân hàng được duyệt')
    accounts=registry['accounts']
    approved=accounts.get(account)
    if approved is None or approved['bank']!=bank or approved['currency']!=currency:
        raise ValueError('Tài khoản, ngân hàng hoặc tiền tệ không khớp danh mục đã duyệt')
    expected=sorted(accounts)
    if not account or currency not in SCALES:
        raise ValueError('Mã tài khoản hoặc tiền tệ không hợp lệ')
    declared=statement.get('expected_accounts')
    if declared is not None and (not isinstance(declared,list) or
            len(declared)!=len(set(declared)) or sorted(declared)!=expected):
        raise ValueError('expected_accounts của file không khớp danh mục tài khoản đã duyệt')
    start=_day(statement['period_start'],'period_start')
    end=_day(statement['period_end'],'period_end')
    if start>end:raise ValueError('Kỳ sao kê có ngày kết thúc trước ngày bắt đầu')
    available=_day(source['available_on'],'available_on')
    if available<end:raise ValueError('Sao kê không thể sẵn có trước khi kết thúc kỳ')
    amounts={field:minor(statement[field],currency) for field in
             ('opening_balance','closing_balance','total_credits','total_debits')}
    if amounts['total_credits']<0 or amounts['total_debits']<0 or amounts['opening_balance']+amounts['total_credits']-amounts['total_debits']!=amounts['closing_balance']:
        raise ValueError('Số dư đầu + ghi có - ghi nợ không bằng số dư cuối')
    columns={**BANK_COLUMNS.get(bank,{}), BANK_DEBITS.get(bank,'debit'):'debit'}
    columns.update(mapping or {})
    out=df.rename(columns=columns).copy()
    if not {'value_date','credit','debit'}<=set(out):
        # The default bank mapping calls credits "amount" in the legacy path.
        if 'amount' in out and 'credit' not in out:out=out.rename(columns={'amount':'credit'})
    if not {'value_date','credit','debit'}<=set(out):
        raise ValueError('Sao kê cần cột ngày, ghi có và ghi nợ; không nhận file chỉ có tiền vào')
    if 'account_id' in out and any(str(value).strip()!=account for value in out.account_id):
        raise ValueError('File chứa tài khoản khác metadata sao kê')
    dates=local_dates(out.value_date,dayfirst=True)
    credits=[];debits=[];entries=[];ids=set()
    for index,row in out.iterrows():
        line=int(df.attrs.get('source_rows',list(range(2,len(df)+2)))[index])
        day=dates.iloc[index]
        if pd.isna(day) or not start<=day.date().isoformat()<=end:
            raise ValueError(f'Dòng {line}: ngày giao dịch nằm ngoài kỳ sao kê hoặc không hợp lệ')
        try:
            credit_value=row['credit'].strip() or '0' if isinstance(row['credit'],str) else row['credit']
            debit_value=row['debit'].strip() or '0' if isinstance(row['debit'],str) else row['debit']
            credit=minor(credit_value,currency)
            debit=minor(debit_value,currency)
        except (TypeError,ValueError) as exc:
            raise ValueError(f'Dòng {line}: {exc}') from exc
        if credit<0 or debit<0 or (credit>0)==(debit>0):
            raise ValueError(f'Dòng {line}: cần đúng một khoản ghi có hoặc ghi nợ dương')
        credits.append(credit);debits.append(debit)
        txn_id=str(row.get('txn_id') or f"{account}-{source['sha256'][:16]}-{line}")
        if txn_id in ids:raise ValueError(f'Dòng {line}: trùng txn_id')
        ids.add(txn_id)
        entries.append(dict(id=txn_id,txn_id=txn_id,firm_id=firm_id,account_id=account,
                            value_date=day.date().isoformat(),currency=currency,
                            credit_minor=credit,debit_minor=debit,source_row=line,
                            source_file=source['file'],source_sha256=source['sha256'],
                            counterparty=str(row.get('counterparty') or ''),
                            memo=str(row.get('memo') or ''),available_on=available))
    if sum(credits)!=amounts['total_credits'] or sum(debits)!=amounts['total_debits']:
        raise ValueError('Tổng giao dịch ghi có/ghi nợ không khớp tổng kỳ sao kê')
    statement_id=str(statement.get('statement_id') or f'{account}:{start}:{end}')
    for entry in entries:entry['statement_id']=statement_id
    current=dict(id=statement_id,statement_id=statement_id,firm_id=firm_id,account_id=account,
                 currency=currency,period_start=start,period_end=end,expected_accounts=expected,
                 account_registry_sha256=registry['registry_sha256'],
                 account_evidence_sha256=registry['evidence_sha256'],
                 source_file=source['file'],source_sha256=source['sha256'],
                 available_on=available,ingested_on=source['ingested_on'],
                 transaction_count=len(entries),credit_count=sum(x>0 for x in credits),
                 debit_count=sum(x>0 for x in debits),
                 **{k+'_minor':v for k,v in amounts.items()})
    for old in existing:
        if old['statement_id']==statement_id:
            if {k:v for k,v in old.items() if k!='ingested_on'}!={k:v for k,v in current.items() if k!='ingested_on'}:
                raise ValueError('Trùng statement_id với nội dung khác')
            current=old
            continue
        if old['account_id']==account and old.get('currency')!=currency:
            raise ValueError('Một tài khoản có nhiều tiền tệ trong sao kê')
    same=[s for s in existing if s['account_id']==account and s['statement_id']!=statement_id]+[current]
    same.sort(key=lambda s:s['period_start'])
    for before,after in zip(same,same[1:]):
        if date.fromisoformat(before['period_end'])+timedelta(days=1)!=date.fromisoformat(after['period_start']):
            raise ValueError('Kỳ sao kê của tài khoản bị trùng hoặc thiếu đoạn')
        if before['closing_balance_minor']!=after['opening_balance_minor']:
            raise ValueError('Số dư đầu kỳ không nối tiếp số dư cuối kỳ trước')
    credit_rows=[]
    for index,(row,entry) in enumerate(zip(out.to_dict('records'),entries)):
        if entry['credit_minor']==0:continue
        credit_rows.append(dict(txn_id=entry['txn_id'],firm_id=firm_id,value_date=entry['value_date'],
                                amount=entry['credit_minor']/(10**SCALES[currency]),
                                amount_minor=entry['credit_minor'],direction='in',
                                account_id=account,currency=currency,statement_id=statement_id,
                                available_on=available,
                                counterparty=str(row.get('counterparty') or ''),memo=str(row.get('memo') or ''),
                                source_file=source['file'],source_row=entry['source_row'],
                                source_sha256=source['sha256']))
    return credit_rows,entries,current


def statement_scope(statements,start,end,registry=None):
    """Report coverage against the approved registry, ignoring legacy unreviewed rows."""
    if registry is None:
        return {'verified':False,'reason':'Chưa có danh mục tài khoản ngân hàng được duyệt'}
    expected=set(registry['accounts'])
    if not statements:
        return {'verified':False,'reason':'Chưa có sao kê','expected_accounts':sorted(expected)}
    trusted=[s for s in statements if s.get('account_evidence_sha256') and
             s['account_id'] in expected and
             s.get('currency')==registry['accounts'][s['account_id']]['currency']]
    untrusted=sorted(s['statement_id'] for s in statements if s not in trusted)
    missing={}
    for account in sorted(expected):
        periods=sorted((s['period_start'],s['period_end']) for s in trusted if s['account_id']==account)
        cursor=date.fromisoformat(start)
        for left,right in periods:
            if right<start or left>end:continue
            if date.fromisoformat(left)>cursor:break
            cursor=max(cursor,date.fromisoformat(right)+timedelta(days=1))
        if cursor<=date.fromisoformat(end):missing[account]=cursor.isoformat()
    return {'verified':not missing and not untrusted,'expected_accounts':sorted(expected),
            'missing_from':missing,'untrusted_statements':untrusted,
            'registry_sha256':registry['registry_sha256']}


def normalize_statement(df, firm_id, bank='vcb', mapping=None, dayfirst=True):
    out=df.rename(columns=mapping or BANK_COLUMNS[bank]).copy()
    if not {'value_date','amount','memo'} <= set(out):
        raise ValueError('Thiếu ngày, tiền ghi có hoặc nội dung; cần cấu hình ánh xạ cột')
    out['value_date']=local_dates(out.value_date,dayfirst=dayfirst)
    if not pd.api.types.is_numeric_dtype(out.amount):
        converted=pd.to_numeric(out.amount,errors='coerce')
        if converted.isna().any():
            index=int(converted.isna().to_numpy().nonzero()[0][0])
            raise ValueError(f'Dòng {index + 2}: cột tiền không phải số; cần chỉ rõ quy ước dấu thập phân')
        out['amount']=converted
    out['amount']=pd.to_numeric(out.amount,errors='coerce')
    if out[['value_date','amount']].isna().any().any() or (out.amount<0).any():
        invalid=out[['value_date','amount']].isna().any(axis=1) | (out.amount<0)
        raise ValueError(f'Dòng {int(invalid.to_numpy().nonzero()[0][0]) + 2}: ngày hoặc số tiền không hợp lệ')
    out['memo']=out.memo.fillna('').astype(str)
    out['counterparty']=out.get('counterparty',pd.Series('',index=out.index)).fillna('').astype(str)
    out['firm_id'],out['direction']=firm_id,'in'
    if 'txn_id' not in out:
        # Thứ tự trùng trong cùng file giữ hai giao dịch có cùng ngày/tiền/nội dung.
        base=out[['value_date','amount','memo','counterparty']].astype(str).agg('|'.join,axis=1)
        duplicate=base.groupby(base).cumcount().astype(str)
        out['txn_id']=[firm_id+'-'+hashlib.sha256((a+'|'+b).encode()).hexdigest()[:24] for a,b in zip(base,duplicate)]
    if out.txn_id.duplicated().any():
        raise ValueError('Trùng txn_id')
    return out[['txn_id','firm_id','value_date','amount','direction','counterparty','memo']]


def read_statement(path, firm_id, bank='vcb', mapping=None, **read_options):
    loader=pd.read_excel if str(path).lower().endswith(('.xlsx','.xls')) else pd.read_csv
    return normalize_statement(loader(path,**read_options),firm_id,bank,mapping)
