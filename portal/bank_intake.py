"""Normalize a bank export once and project it into the two agent contracts."""
import csv
import io
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


ALIASES = {
    'bank_id': ('bank id', 'ma dong sao ke', 'ma giao dich', 'transaction id', 'txn id', 'so tham chieu',
                'so giao dich', 'ma tham chieu', 'ref no', 'reference'),
    'account': ('account', 'tai khoan', 'tai khoan cua doanh nghiep', 'so tai khoan', 'own account',
                'account no', 'account number'),
    'date': ('date', 'ngay giao dich', 'ngay', 'booking date', 'ngay hach toan', 'transaction date', 'ngay hieu luc'),
    'direction': ('direction', 'thu chi'),
    'amount': ('amount', 'so tien'),
    'debit': ('debit', 'ghi no', 'phat sinh no', 'tien ra', 'so tien ghi no', 'ps no'),
    'credit': ('credit', 'ghi co', 'phat sinh co', 'tien vao', 'so tien ghi co', 'ps co'),
    'description': ('description', 'memo', 'noi dung', 'dien giai', 'noi dung giao dich', 'chi tiet giao dich'),
    'counterparty_account': ('counterparty account', 'tai khoan doi tac', 'so tai khoan doi ung', 'tai khoan doi ung', 'beneficiary account'),
    'counterparty_name': ('counterparty name', 'counterparty', 'ten doi tac', 'ten don vi doi ung', 'ten doi ung', 'beneficiary name'),
    'customer_id': ('customer id', 'ma khach hang'),
    'cash_flow_class': ('cash flow class', 'loai dong tien'),
    'known_at': ('known at', 'ngay ghi nhan', 'available on'),
    'component': ('component', 'nhom du bao'),
    'currency': ('currency', 'tien te', 'loai tien'),
}


def columns(header, normalize):
    """Identify a bank table only when it carries stable transaction identity."""
    names = [normalize(cell) for cell in header]
    found = {key: [i for i, name in enumerate(names) if name in aliases] for key, aliases in ALIASES.items()}
    required = all(found[key] for key in ('bank_id', 'account', 'date'))
    money = (found['direction'] and found['amount']) or (found['debit'] and found['credit'])
    if not required or not money:
        return None
    if any(len(indexes) > 1 for indexes in found.values()):
        raise ValueError('Sao kê có nhiều cột cùng nghĩa. Mỗi trường chỉ dùng một cột.')
    if (found['direction'] or found['amount']) and (found['debit'] or found['credit']):
        raise ValueError('Chọn cặp Ghi Nợ/Ghi Có hoặc cặp Thu/Chi và Số tiền, không dùng đồng thời.')
    return {key: indexes[0] for key, indexes in found.items() if indexes}


def csv_rows(raw):
    source = raw.decode('utf-8-sig')
    first = next((line for line in source.splitlines() if line.strip()), '')
    delimiter = max((',', ';', '\t'), key=first.count)
    return csv.reader(io.StringIO(source, newline=''), delimiter=delimiter, strict=True)


def day(value):
    if isinstance(value, Decimal):
        if not value.is_finite() or not 61 <= value <= 100000:
            raise ValueError('Ngày dạng số Excel không hợp lệ')
        return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
    value = str(value).strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return date.fromisoformat(value).isoformat()
    match = re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', value)
    if match:
        d, m, y = map(int, match.groups())
        return date(y, m, d).isoformat()
    raise ValueError('Ngày phải là YYYY-MM-DD hoặc DD/MM/YYYY')


MAX_VND = 2**53 - 1
_CURRENCY_RE = re.compile(r'^(?:vnd|vnđ|[đ₫])\s*|\s*(?:vnd|vnđ|[đ₫])$', re.IGNORECASE)
_COMMA_GROUP_RE = re.compile(r'^([1-9]\d{0,2}(?:,\d{3})+)(?:\.(\d{1,2}))?$')
_DOT_GROUP_RE = re.compile(r'^([1-9]\d{0,2}(?:\.\d{3})+)(?:,(\d{1,2}))?$')
_PLAIN_FRAC_RE = re.compile(r'^(\d+)[.,](\d{1,2})$|^(\d{4,})[.,](\d+)$|^(0+)[.,](0+)$')


def _strip_currency(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _CURRENCY_RE.sub('', text).strip()
    return text


def money(value, number_format='vi-VN'):
    """Parse domestic VND bank amounts without confusing comma thousands grouping for decimals."""
    if number_format not in ('vi-VN', 'plain', None):
        raise ValueError('Định dạng số tiền trong hồ sơ không hợp lệ')
    if isinstance(value, bool) or value is None:
        raise ValueError('Số tiền VND không hợp lệ')
    if isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, float):
        if not Decimal(str(value)).is_finite():
            raise ValueError('Số tiền VND không hợp lệ')
        dec = Decimal(str(value))
    elif isinstance(value, Decimal):
        dec = value
    else:
        s = str(value).replace('\u00a0', ' ').replace('\u202f', ' ').strip()
        if not s:
            return Decimal(0)
        s = _strip_currency(s)
        negative = False
        if s.startswith('(') and s.endswith(')'):
            negative = True
            s = _strip_currency(s[1:-1].strip())
            if not s or s[0] in '+-(':
                raise ValueError('Số tiền âm dạng ngoặc đơn không hợp lệ')
        elif s.startswith(('-', '+', '−')):
            negative = s[0] in ('-', '−')
            s = _strip_currency(s[1:].strip())
            if not s or s[0] in '+-−(':
                raise ValueError('Dấu số tiền không hợp lệ')

        if re.fullmatch(r'\d+', s):
            digits, frac = s, ''
        elif m := _COMMA_GROUP_RE.fullmatch(s):
            digits, frac = m.group(1).replace(',', ''), m.group(2) or ''
        elif m := _DOT_GROUP_RE.fullmatch(s):
            digits, frac = m.group(1).replace('.', ''), m.group(2) or ''
        elif m := _PLAIN_FRAC_RE.fullmatch(s):
            digits = m.group(1) or m.group(3) or m.group(5)
            frac = m.group(2) or m.group(4) or m.group(6) or ''
        else:
            raise ValueError('Số tiền không khớp định dạng VND hợp lệ')

        if any(ch != '0' for ch in frac):
            raise ValueError('Số tiền phải là số nguyên VND, không có phần lẻ thập phân')
        dec = Decimal(digits)
        if negative and dec:
            dec = -dec

    if not dec.is_finite() or dec != dec.to_integral_value() or abs(dec) > MAX_VND:
        raise ValueError('Số tiền phải là số nguyên VND trong giới hạn cho phép')
    return Decimal(int(dec))


def normalize_rows(rows, fields, number_format, normalize):
    output = {}
    for line, row in enumerate(rows, 2):
        if not any(str(cell).strip() for cell in row):
            continue

        def get(key):
            index = fields.get(key, len(row))
            return row[index] if index < len(row) else ''

        try:
            account, bank_id = get('account'), get('bank_id')
            if not isinstance(account, str) or not isinstance(bank_id, str) or not account.strip() or not bank_id.strip():
                raise ValueError('Mã giao dịch và tài khoản bắt buộc, để kiểu văn bản để giữ số 0 đầu')
            account, bank_id = account.strip(), bank_id.strip()
            if len(bank_id) > 160:
                raise ValueError('Mã giao dịch dài quá 160 ký tự')
            if str(get('currency')).strip().upper() not in ('', 'VND', 'VNĐ'):
                raise ValueError('Sao kê dùng chung hiện chỉ nhận VND')
            booked = day(get('date'))
            known = day(get('known_at')) if get('known_at') != '' else booked
            if known < booked:
                raise ValueError('Ngày ghi nhận không được trước ngày giao dịch')
            if 'direction' in fields:
                direction = {'in': 'in', 'out': 'out', 'thu': 'in', 'chi': 'out',
                             'credit': 'in', 'debit': 'out', 'cr': 'in', 'dr': 'out'}.get(normalize(get('direction')))
                amount = money(get('amount'), number_format)
                if direction == 'in' and amount < 0:
                    raise ValueError('Chiều Thu (in) không được có số tiền âm')
                if direction == 'out' and amount < 0:
                    amount = -amount
                if not direction or amount <= 0:
                    raise ValueError('Chiều phải là Thu/Chi hoặc in/out và số tiền phải dương')
            else:
                debit_raw, credit_raw = (money(get(key), number_format) for key in ('debit', 'credit'))
                if credit_raw < 0:
                    raise ValueError('Cột Ghi Có không được có số tiền âm')
                debit = abs(debit_raw)
                credit = credit_raw
                if bool(debit) == bool(credit):
                    raise ValueError('Chỉ một trong hai cột Ghi Nợ/Ghi Có được có số tiền dương')
                direction, amount = ('out', debit) if debit else ('in', credit)
            component = str(get('component')).strip() or 'other'
            values = (bank_id, account, booked, direction, str(int(amount)), known, component,
                      *(str(get(k)).strip() for k in ('description', 'counterparty_account', 'counterparty_name',
                                                     'customer_id', 'cash_flow_class')))
            if bank_id in output and output[bank_id] != values:
                raise ValueError('Mã giao dịch trùng nhưng nội dung khác, hoặc dùng chung giữa hai tài khoản')
            output[bank_id] = values
        except (ValueError, InvalidOperation, OverflowError) as error:
            raise ValueError(f'Dòng {line}: {error}') from error
    if not output:
        raise ValueError('Sao kê không có dòng giao dịch')
    return sorted(output.values())


def project(rows, agent, *, date_format='iso', number_format='plain'):
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    if agent == 'agent1':
        if date_format not in ('iso', 'dmy') or number_format not in ('plain', 'vi-VN'):
            raise ValueError('Định dạng hồ sơ doanh nghiệp không hợp lệ')
        def formatted_day(value):
            parsed = date.fromisoformat(value)
            return parsed.isoformat() if date_format == 'iso' else parsed.strftime('%d/%m/%Y')
        writer.writerow(('bank_id', 'account', 'date', 'direction', 'amount', 'known_at', 'component',
                         'memo', 'counterparty', 'customer_id', 'cash_flow_class'))
        for bank_id, account, booked, direction, amount, known, component, description, _, name, customer_id, cash_flow_class in rows:
            exact = int(amount)
            amount = format(exact, ',').replace(',', '.') if number_format == 'vi-VN' else str(exact)
            writer.writerow((bank_id, account, formatted_day(booked), direction, amount, formatted_day(known), component,
                             description, name, customer_id, cash_flow_class))
    else:
        writer.writerow(('portal_bank_id', 'portal_bank_account', 'Ngày giao dịch', 'Ghi Nợ', 'Ghi Có',
                         'Nội dung', 'Số tài khoản đối ứng', 'Tên đơn vị đối ứng'))
        for bank_id, account, booked, direction, amount, _, _, description, peer, name, *_ in rows:
            writer.writerow((bank_id, account, booked, amount if direction == 'out' else '',
                             amount if direction == 'in' else '', description, peer, name))
    return out.getvalue().encode('utf-8')
