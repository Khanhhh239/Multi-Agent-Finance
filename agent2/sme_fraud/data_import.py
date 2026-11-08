"""Preview, validate and atomically import company transactions into the ML workspace.

Uploads never modify connected sources. Only connected masters and calendar are
used; absent operational histories are disclosed and have a separate data version.
"""
import base64
import binascii
import csv
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import threading
import time
import zipfile

import numpy as np

from .company_ml import dump
from .exception_validation import validated_record, validated_tables
from .feature_contract import current_contract, digest
from urllib.parse import urlencode
from .features import build_features
from .generate import PAIRS

VERSION = 'company-transaction-upload-v1'
MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
TZ = timezone(timedelta(hours=7))
REQUIRED = ('transaction_id', 'posted_at', 'created_at', 'approved_at', 'txn_type',
            'amount_vnd', 'approval_limit_vnd', 'creator_id', 'approver_id',
            'is_financial_entry', 'debit_account', 'credit_account', 'journal_signature',
            'accounting_purpose', 'recognised_input_vat_vnd', 'recognised_output_vat_vnd',
            'writeoff_provision_vnd', 'production_cost_vnd')
OPTIONAL = ('company_id', 'vendor_id', 'employee_id', 'customer_id', 'recipient_account',
            'recipient_bank_code', 'payment_channel', 'payroll_period', 'invoice_id',
            'invoice_number', 'invoice_issued_at', 'invoice_observed_at', 'invoice_gross_vnd',
            'invoice_net_vnd', 'invoice_vat_vnd', 'linked_input_vat_vnd',
            'support_doc_count', 'goods_receipt_verified', 'evidence_on_file',
            'support_docs_observed_at', 'goods_receipt_verified_at',
            'journal_document_id', 'linked_document_id', 'business_purpose')
MONEY = {'amount_vnd', 'approval_limit_vnd', 'recognised_input_vat_vnd',
         'recognised_output_vat_vnd', 'writeoff_provision_vnd', 'production_cost_vnd',
         'invoice_gross_vnd', 'invoice_net_vnd', 'invoice_vat_vnd', 'linked_input_vat_vnd'}
FLAGS = {'is_financial_entry', 'goods_receipt_verified', 'evidence_on_file'}
MASTERS = ('companies', 'employees', 'vendors', 'customers', 'calendar')


def issue(row, column, message, fix):
    return dict(row=row, column=column, message=message, fix=fix)


def timestamp(value, date_order):
    if isinstance(value, datetime):
        parsed = value
    else:
        value = str(value)
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?', value):
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        elif date_order == 'dmy':
            parsed = datetime.strptime(value, '%d/%m/%Y %H:%M:%S' if value.count(':') == 2 else '%d/%m/%Y %H:%M')
        else:
            raise ValueError('Dùng YYYY-MM-DD HH:MM[:SS], có thể thêm múi giờ; hoặc chọn DD/MM/YYYY.')
    if parsed.microsecond:
        raise ValueError('Thời gian chỉ hỗ trợ đến giây; hãy bỏ phần mili giây trong tệp nguồn.')
    return parsed.replace(tzinfo=parsed.tzinfo or TZ).astimezone(TZ).isoformat(timespec='seconds')


def read_upload(filename, content, encoding='utf-8-sig', delimiter='auto'):
    """Return physical row numbers; reject formulas and numeric Excel identifiers."""
    suffix = Path(filename).suffix.lower()
    if suffix == '.csv':
        if encoding not in {'utf-8-sig', 'cp1258'} or delimiter not in {'auto', ',', ';', '\t'}:
            raise ValueError('Mã hóa hoặc dấu phân cách CSV không được hỗ trợ.')
        try:
            text = content.decode(encoding)
        except UnicodeError as exc:
            raise ValueError('Không đọc được mã hóa CSV. Lưu UTF-8 hoặc chọn Windows-1258.') from exc
        if '\x00' in text:
            raise ValueError('CSV chứa ký tự rỗng; hãy xuất lại dưới dạng UTF-8.')
        if delimiter == 'auto':
            try:
                delimiter = csv.Sniffer().sniff(text[:65536], delimiters=',;\t').delimiter
            except csv.Error:
                delimiter = ','
        reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
        rows = []
        try:
            for values in reader:
                if len(values) > 80 or len(rows) > MAX_ROWS:
                    raise ValueError('Tối đa 10.000 giao dịch và 80 cột mỗi tệp.')
                rows.append((reader.line_num, values))
        except csv.Error as exc:
            raise ValueError(f'CSV sai cấu trúc gần dòng {reader.line_num}: {exc}. Kiểm tra dấu nháy và dấu phân cách.') from exc
        return rows, [], dict(format='csv', delimiter=delimiter, encoding=encoding)
    if suffix != '.xlsx':
        raise ValueError('Chỉ nhận .csv và .xlsx. Với .xls/.xlsm, hãy lưu lại thành .xlsx không chứa macro.')
    try:
        import defusedxml  # noqa: F401; openpyxl uses hardened XML readers when installed
        from openpyxl import load_workbook
        from openpyxl.xml import DEFUSEDXML
        if not DEFUSEDXML:
            raise ImportError('openpyxl XML protection disabled')
    except ImportError as exc:
        raise ValueError('Máy chủ cần cài requirements-data-import.txt để đọc Excel an toàn.') from exc
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if (len(entries) > 2000 or sum(e.file_size for e in entries) > 64 * 1024 * 1024
                    or any(e.flag_bits & 1 or 'vbaproject' in e.filename.lower() for e in entries)):
                raise ValueError('Excel quá lớn sau giải nén, có macro hoặc được mã hóa. Xuất lại tệp .xlsx đơn giản.')
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
        try:
            if len(book.sheetnames) != 1:
                raise ValueError('Excel cần đúng một sheet giao dịch. Tách các sheet khác ra trước khi nhập.')
            sheet = book.worksheets[0]
            sheet.reset_dimensions()  # do not trust producer-supplied used range
            rows, errors, headers = [], [], []
            for number, cells in enumerate(sheet.iter_rows(), 1):
                if number > MAX_ROWS + 1 or len(cells) > 80:
                    raise ValueError('Tối đa 10.000 giao dịch và 80 cột mỗi tệp.')
                values = []
                for i, cell in enumerate(cells):
                    value = cell.value
                    column = str(headers[i]) if number > 1 and i < len(headers) else str(i+1)
                    if cell.data_type in {'f', 'e'}:
                        errors.append(issue(number, column, 'Ô chứa công thức hoặc lỗi Excel.', 'Dán giá trị đã kiểm tra, không dùng công thức.'))
                    if (number > 1 and value is not None and not isinstance(value, str)
                            and (column.endswith('_id') or 'account' in column or column in {'invoice_number', 'recipient_bank_code'})):
                        errors.append(issue(number, column, 'Mã định danh/tài khoản đang là ô số hoặc ngày.', 'Định dạng Text và nhập lại từ nguồn để giữ số 0 đầu; đổi định dạng sau khi mất số không khôi phục được mã.'))
                    values.append('' if value is None else value)
                if number == 1:
                    headers = [str(v).strip() for v in values]
                elif len(values)<len(headers):
                    values.extend(['']*(len(headers)-len(values)))
                rows.append((number, values))
            return rows, errors, dict(format='xlsx', sheet=sheet.title)
        finally:
            book.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Không đọc được Excel: tệp hỏng, sai định dạng hoặc XML không an toàn. Xuất lại .xlsx rồi thử lại.') from exc


class DataImport:
    def __init__(self, ml, *, monotonic=time.monotonic):
        self.ml, self.store, self.now = ml, ml.store, monotonic
        self.lock = threading.Lock()
        self.pending = {}
        with self.store.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS company_ml_imports(
                import_id TEXT PRIMARY KEY, company_id TEXT, revision TEXT,
                metadata TEXT, raw_records TEXT)''')

    def _sources(self, scenario, company):
        root = self.store.data_root / ('sme_fraud_' + scenario)
        tables, hashes = {}, {}
        for name in MASTERS:
            path = root / (name + '.csv')
            if not path.is_file():
                tables[name], hashes[name] = [], None
                continue
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError(f'Danh mục {name} quá lớn cho nhập liệu web; cần quản trị viên kiểm tra nguồn.')
            content = path.read_bytes()
            hashes[name] = hashlib.sha256(content).hexdigest()
            rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
            tables[name] = [r for r in rows if r.get('company_id') == company or (name == 'calendar' and not r.get('company_id'))]
        if len(tables['companies']) != 1:
            raise ValueError('Nguồn danh mục doanh nghiệp bị thiếu hoặc trùng. Cần sửa danh mục trước khi nhập.')
        if tables['companies'][0].get('accounting_framework') not in {'TT133', 'TT200'}:
            raise ValueError('Danh mục doanh nghiệp cần accounting_framework TT133 hoặc TT200 phù hợp feature hiện tại.')
        try:
            validated_tables(tables)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f'Danh mục kết nối chưa hợp lệ: {exc}. Sửa nguồn danh mục trước khi nhập.') from exc
        return tables, hashes

    def context(self, scenario, company, principal):
        self.ml._company(scenario, company, principal)
        tables, _ = self._sources(scenario, company)
        status = self.ml.status(scenario, company, principal)
        return dict(required=list(REQUIRED), optional=list(OPTIONAL), txn_types=list(PAIRS),
                    max_bytes=MAX_BYTES, max_rows=MAX_ROWS, status=status,
                    references={name:sorted({r[name[:-1]+'_id'] for r in tables[name]})
                                for name in ('employees', 'vendors', 'customers')})

    @staticmethod
    def template():
        output = io.StringIO(newline='')
        csv.writer(output).writerow((*REQUIRED, *OPTIONAL))
        return '\ufeff' + output.getvalue()

    def preview(self, scenario, company, principal, *, filename, content_base64,
                expected_revision, date_order='iso', encoding='utf-8-sig', delimiter='auto'):
        self.ml._company(scenario, company, principal, True)
        if date_order not in {'iso', 'dmy'}:
            raise ValueError('Chọn định dạng thời gian ISO hoặc ngày/tháng/năm.')
        if not isinstance(filename, str) or not filename or len(filename) > 255:
            raise ValueError('Tên tệp không hợp lệ.')
        if not isinstance(content_base64, str) or len(content_base64) > (MAX_BYTES+2)//3*4:
            raise ValueError('Tệp vượt giới hạn 10 MB.')
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Nội dung tệp không hợp lệ. Chọn lại tệp rồi kiểm tra.') from exc
        if not 0 < len(content) <= MAX_BYTES:
            raise ValueError('Tệp rỗng hoặc vượt giới hạn 10 MB.')
        with self.store.connection() as db:
            current = db.execute('SELECT revision FROM company_ml_data WHERE company_id=?', (company,)).fetchone()
        if (current[0] if current else None) != expected_revision:
            raise RuntimeError('Dữ liệu đã đổi. Tải lại doanh nghiệp rồi kiểm tra tệp lại.')
        rows, errors, parsed = read_upload(filename, content, encoding, delimiter)
        def fail(row, column, message, fix):
            errors.append(issue(row, column, message, fix))
        if not rows:
            raise ValueError('Tệp chưa có dòng tiêu đề và giao dịch.')
        fields = [str(c).strip() for c in rows[0][1]]
        if len(set(fields)) != len(fields) or '' in fields:
            fail(1, 'tiêu đề', 'Có tên cột rỗng hoặc trùng.', 'Dùng đúng một cột cho mỗi tên trong tệp mẫu.')
        for field in REQUIRED:
            if field not in fields:
                fail(1, field, 'Thiếu cột bắt buộc.', 'Thêm cột từ tệp mẫu và điền dữ liệu gốc; không điền giá trị phỏng đoán.')
        for field in fields:
            if field not in (*REQUIRED, *OPTIONAL):
                fail(1, field, 'Cột chưa được hỗ trợ trong định dạng nhập giao dịch.', 'Dùng tệp mẫu; nhãn ML được nhập riêng tại màn hình chọn ML.')
        records, seen, changes, empty = [], {}, 0, 0
        missing = {}
        tables, hashes = self._sources(scenario, company)
        masters = {}
        for name,key in [('employees','employee_id'),('vendors','vendor_id'),('customers','customer_id')]:
            masters[name] = defaultdict(list)
            for r in sorted(tables[name],key=lambda r:r.get('recorded_at','')):
                masters[name][r[key]].append(r)
        header_ok = not any(e['row'] == 1 for e in errors)
        for number, values in rows[1:] if header_ok else []:
            if not any(str(v).strip() for v in values):
                empty += 1; continue
            if len(values) != len(fields):
                fail(number, 'cấu trúc', f'Dòng có {len(values)} ô, tiêu đề có {len(fields)} cột.', 'Kiểm tra dấu phân cách, dấu nháy và các ô thừa/thiếu.'); continue
            before = len(errors)
            raw = dict(zip(fields, values)); row = {}
            for field, value in raw.items():
                original = value
                if isinstance(value, str):
                    value = value.strip()
                    changes += int(value != original)
                if value == '':
                    if field in REQUIRED and not (field in {'debit_account','credit_account','journal_signature'} and str(raw.get('is_financial_entry','')).strip()=='0'):
                        fail(number, field, 'Thiếu giá trị bắt buộc.', 'Bổ sung từ chứng từ hoặc nguồn hệ thống trước khi nhập.')
                    elif field in {'debit_account','credit_account','journal_signature'}:
                        row[field]=''
                    else:
                        missing[field] = missing.get(field, 0) + 1
                    continue
                try:
                    if field.endswith('_at'):
                        value = timestamp(value, date_order)
                    elif field in MONEY or field == 'support_doc_count':
                        if isinstance(value, bool) or not re.fullmatch(r'[0-9]+', str(value)):
                            raise ValueError('Cần số nguyên VND không âm; không dùng dấu phân nhóm, số thập phân hoặc ký hiệu tiền.')
                        value = str(int(value))
                        if int(value) > 9_000_000_000_000_000 or (field in {'amount_vnd','approval_limit_vnd'} and int(value) == 0):
                            raise ValueError('Số tiền vượt giới hạn; amount_vnd và approval_limit_vnd phải lớn hơn 0.')
                    elif field in FLAGS:
                        if isinstance(value, bool): value = int(value)
                        if str(value) not in {'0', '1'}:
                            raise ValueError('Cờ dữ liệu chỉ nhận 0 hoặc 1.')
                        value = str(value)
                    else:
                        if not isinstance(value, str):
                            raise ValueError('Cần ô Text; không dùng ô số cho mã hoặc tài khoản.')
                        if len(value) > 1000 or any(ord(c) < 32 for c in value):
                            raise ValueError('Giá trị quá dài hoặc chứa ký tự điều khiển.')
                    row[field] = value
                except (ValueError, TypeError, OverflowError) as exc:
                    fail(number, field, str(exc), 'Sửa giá trị trong tệp rồi bấm kiểm tra lại.')
            for field in ('vendor_id','employee_id','customer_id','recipient_account','recipient_bank_code',
                          'invoice_issued_at','payroll_period','invoice_number','invoice_id'):
                row.setdefault(field, '')
            row['advance_id'] = ''
            if row.get('company_id', company) != company:
                fail(number, 'company_id', 'Giao dịch không thuộc doanh nghiệp đang chọn.', f'Chọn đúng doanh nghiệp hoặc chỉ giữ dòng của {company}.')
            row['company_id'] = company
            tid = row.get('transaction_id')
            if tid in seen:
                fail(number, 'transaction_id', f'Mã trùng với dòng {seen[tid]}.', 'Mỗi giao dịch cần một mã duy nhất, kể cả khi hai dòng có nội dung giống nhau.')
            if tid: seen[tid] = number
            if row.get('txn_type') and row['txn_type'] not in PAIRS:
                fail(number, 'txn_type', 'Loại giao dịch không được hỗ trợ.', 'Chọn một loại trong danh sách định dạng. Không suy đoán tự động từ diễn giải.')
            if all(k in row for k in ('created_at','approved_at','posted_at')) and not any(e['row']==number and e['column'].endswith('_at') for e in errors[before:]):
                if not row['created_at'] <= row['approved_at'] <= row['posted_at']:
                    fail(number, 'posted_at', 'Thời gian cần thỏa tạo ≤ duyệt ≤ ghi sổ.', 'Đối chiếu lại ba thời điểm trong hệ thống nguồn.')
                if datetime.fromisoformat(row['posted_at']) > self.store.clock():
                    fail(number, 'posted_at', 'Giao dịch có thời điểm ghi sổ trong tương lai.', 'Chỉ nhập giao dịch đã ghi sổ; kiểm tra múi giờ.')
            for field, name, cutoff in [('creator_id','employees','created_at'),('approver_id','employees','approved_at'),
                                        ('employee_id','employees','posted_at'),('vendor_id','vendors','posted_at'),('customer_id','customers','posted_at')]:
                identity = row.get(field)
                if not identity or not row.get(cutoff): continue
                versions = [r for r in masters[name].get(identity, []) if r.get('recorded_at','') <= row[cutoff]]
                if not versions:
                    fail(number, field, 'Mã chưa có trong danh mục của doanh nghiệp tại thời điểm giao dịch.', 'Kiểm tra mã, doanh nghiệp và recorded_at trong danh mục kết nối.'); continue
                master = versions[-1]
                required = ('self_approval_limit_vnd',) if field == 'creator_id' else ('contract_on_file',) if field == 'employee_id' else ('registered_at','onboarded_at','related_party_disclosed_at') if field == 'vendor_id' else ()
                if any(k not in master for k in required):
                    fail(number, field, f'Danh mục {identity} thiếu thuộc tính: {", ".join(k for k in required if k not in master)}.', 'Cập nhật danh mục kết nối; hệ thống không tự tạo hạn mức hoặc bằng chứng.')
            if row.get('journal_signature') and not re.fullmatch(r'\d{2,12}/\d{2,12}(;\d{2,12}/\d{2,12})*', row['journal_signature']):
                fail(number, 'journal_signature', 'Cặp tài khoản sai định dạng.', 'Ví dụ 331/112 hoặc 156/331;133/331, dùng mã tài khoản gốc.')
            if row.get('payroll_period') and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', row['payroll_period']):
                fail(number, 'payroll_period', 'Kỳ lương không hợp lệ.', 'Dùng YYYY-MM.')
            if 'support_docs_observed_at' in row:
                for key in ('support_doc_count','goods_receipt_verified','evidence_on_file'):
                    if key not in row:
                        fail(number, key, 'Đã khai thời điểm biết hồ sơ nhưng thiếu nội dung hồ sơ.', 'Điền đủ số hồ sơ và hai cờ 0/1, hoặc bỏ thời điểm nếu chưa biết hồ sơ.')
            if len(errors) == before:
                try:
                    validated_record('transactions', row)
                    records.append(row)
                except ValueError as exc:
                    fail(number, 'dữ liệu', str(exc), 'Đối chiếu định dạng với tệp mẫu.')
        if header_ok and not records and not errors:
            fail(None, 'tệp', 'Không có giao dịch để nhập.', 'Thêm ít nhất một dòng dữ liệu dưới tiêu đề.')
        for field in OPTIONAL:
            if field not in fields and field!='company_id': missing[field]=len(records)
        result = dict(valid=not errors, errors=errors[:200], error_count=len(errors), token=None,
                      summary=dict(rows=len(records), skipped_blank_rows=empty, trimmed_cells=changes,
                                   missing_optional=missing, company_id=company, **parsed),
                      normalized_preview=records[:10], warnings=[])
        if errors: return result
        warnings = [
            'Lần lưu này THAY THẾ toàn bộ tập dữ liệu ML của doanh nghiệp, không nối thêm. Hãy nhập đầy đủ lịch sử cần dùng để tạo feature theo thời gian.',
            'Chỉ dùng danh mục doanh nghiệp/nhân viên/NCC/khách hàng và lịch nghỉ đã kết nối. Tệp giao dịch chưa cung cấp lịch sử quan hệ, chấm công, đổi ngân hàng, tạm ứng hoặc dòng bút toán; các feature phụ thuộc nguồn này có thể bằng 0 và không chứng minh không có rủi ro.',
            'Hồ sơ và hóa đơn không có thời điểm quan sát sẽ giữ trạng thái chưa biết trong feature; không tự điền bằng chứng. Các khoản VAT đã ghi nhận, dự phòng và chi phí bắt buộc khai rõ, kể cả giá trị 0.',
            'Không nhập nhãn từ tệp này. Nhãn cũ sẽ được xóa khỏi tập ML thay thế; có thể tải lại nhãn đã rà tại bước chọn ML.'
        ]
        contract = current_contract()
        try:
            features = build_features(dict(tables, transactions=records))
            by_id = {r['transaction_id']:r for r in features}
            records.sort(key=lambda r:(r['posted_at'],r['transaction_id']))
            matrix = np.asarray([[by_id[r['transaction_id']][c] for c in contract['columns']] for r in records], dtype=np.float32)
            if matrix.shape != (len(records),len(contract['columns'])) or not np.isfinite(matrix).all():
                raise ValueError('Feature không hữu hạn hoặc sai kích thước.')
        except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
            result.update(valid=False, error_count=1, errors=[issue(None, 'tạo feature', str(exc), 'Kiểm tra nguồn danh mục và dữ liệu giao dịch; chưa có dữ liệu nào được lưu.')])
            return result
        status = self.ml.status(scenario, company, principal)
        active = next((v for v in status['versions'] if v['version_id']==status['active_version']),None)
        incompatible = bool(active and (active['dataset_version'] != VERSION or active['feature_fingerprint'] != contract['fingerprint']))
        if incompatible:
            warnings.append('Model đang dùng vẫn được giữ, nhưng khác định dạng nguồn của lần nhập này. Cần đánh giá và kích hoạt ứng viên mới trước khi chấm dữ liệu nhập.')
        times = sorted({r['posted_at'] for r in records})
        defaults = None
        if len(times)>=7:
            defaults = dict(train_end=times[min(len(times)-3,max(2,int(len(times)*.6)))],
                            calibration_end=times[min(len(times)-2,max(3,int(len(times)*.8)))])
        if len(records)<9 or len(times)<3:
            warnings.append('Dữ liệu có thể chưa đủ để tách ít nhất 5 dòng train, 2 calibration, 2 evaluation theo thời gian. Có thể lưu và bổ sung lịch sử trước khi đánh giá ML.')
        blob = dump(matrix)
        metadata = dict(company_id=company, scenario=scenario, rows=len(records), columns=contract['columns'],
                        feature_fingerprint=contract['fingerprint'], dataset_version=VERSION,
                        manifest_sha256=None, labels_count=0, first_at=records[0]['posted_at'],last_at=records[-1]['posted_at'],
                        suggested_windows=defaults, source='csv_excel_upload', source_sha256=hashlib.sha256(content).hexdigest(),
                        master_sha256=hashes, imported_at=self.store.clock().isoformat())
        revision = digest([metadata,records,hashlib.sha256(blob).hexdigest(),{}])
        result.update(warnings=warnings, feature_count=len(contract['columns']))
        result['summary'].update(first_at=metadata['first_at'],last_at=metadata['last_at'],
                                 previous_rows=status['data']['rows'] if status['data'] else 0,
                                 active_version=status['active_version'],model_needs_evaluation=incompatible)
        with self.lock:
            self.pending = {k:v for k,v in self.pending.items() if self.now()-v['at']<1200
                            and (v['actor'],v['company'])!=(principal.user_id,company)}
            if len(self.pending)>=8:
                raise OverflowError('Đang có quá nhiều bản xem trước. Chờ bản cũ hết hạn sau 20 phút rồi thử lại.')
            token = secrets.token_urlsafe(32)
            self.pending[token] = dict(at=self.now(),actor=principal.user_id,company=company,scenario=scenario,
                                       expected=expected_revision,metadata=metadata,records=records,blob=blob,
                                       revision=revision,hashes=hashes,warnings=warnings,active=status['active_version'])
        result['token'] = token
        return result

    def commit(self, scenario, company, principal, *, token, acknowledge):
        self.ml._company(scenario, company, principal, True)
        if acknowledge is not True:
            raise ValueError('Cần xác nhận đã đọc bản xem trước, cảnh báo và thao tác thay thế dữ liệu.')
        if not isinstance(token,str): raise ValueError('Bản xem trước không hợp lệ.')
        with self.lock:
            item = self.pending.get(token)
            if not item or self.now()-item['at']>=1200:
                raise RuntimeError('Bản xem trước đã hết hạn, được thay thế hoặc đã lưu. Kiểm tra lại tệp trước khi lưu.')
            if (item['actor'],item['company'],item['scenario']) != (principal.user_id,company,scenario):
                raise PermissionError('Bản xem trước thuộc người dùng hoặc doanh nghiệp khác.')
            _, hashes = self._sources(scenario, company)
            if hashes != item['hashes'] or current_contract()['fingerprint'] != item['metadata']['feature_fingerprint']:
                raise RuntimeError('Danh mục hoặc bộ tạo feature đã đổi. Kiểm tra lại tệp trước khi lưu.')
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('SELECT revision FROM company_ml_data WHERE company_id=?',(company,)).fetchone()
                if (current[0] if current else None)!=item['expected']:
                    raise RuntimeError('Dữ liệu đã đổi sau khi xem trước. Tải lại và kiểm tra tệp trước khi lưu.')
                if self.ml._active(db,company)!=item['active']:
                    raise RuntimeError('Model đang dùng đã đổi sau khi xem trước. Kiểm tra lại tệp để xem cảnh báo tương thích mới.')
                import_id=secrets.token_hex(16)
                db.execute('INSERT OR REPLACE INTO company_ml_data VALUES(?,?,?,?,?,?)',
                           (company,item['revision'],json.dumps(item['metadata']),json.dumps(item['records']),item['blob'],'{}'))
                db.execute('INSERT INTO company_ml_imports VALUES(?,?,?,?,?)',
                           (import_id,company,item['revision'],json.dumps(item['metadata']),json.dumps(item['records'])))
                self.ml._event(db,company,principal,'data_imported',import_id=import_id,revision=item['revision'],
                               source_sha256=item['metadata']['source_sha256'],rows=len(item['records']),
                               acknowledged_warnings=item['warnings'],active_version=self.ml._active(db,company))
            del self.pending[token]
        return dict(import_id=import_id,status=self.ml.status(scenario,company,principal),
                    next_url='/company-ml?'+urlencode(dict(company=company,scenario=scenario)))
