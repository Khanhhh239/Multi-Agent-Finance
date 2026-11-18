"""Versioned, exact JSON file mapping for the new import/snapshot workflow."""
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
import re
import threading

import finance_input.json_io as json_io
import finance_input.validation as core_validation
from finance_input import schema,CONTRACT_VERSION,SUPPORTED_CONTRACT_VERSIONS
from finance_input.validation import issue
from . import imports

PARSER_VERSION = "contract-files/1.2.0"
PROTOCOL_VERSION = "1.0.0"
MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 100000
_SLASH_LOCATION_RE = re.compile(r'(/[^/]+/[0-9]+)(?:/|$)')
_DOT_LOCATION_RE = re.compile(r'(source\.(?:tables\.[^.]+\.[0-9]+|[^.\[]+\[[0-9]+\]))(?:\.|$)')
_PARSE_CACHE_LOCK = threading.Lock()
_PARSE_CACHE = OrderedDict()


class ImportFailure(Exception):
    def __init__(self, status, code, message, action):
        super().__init__(message)
        self.status, self.code, self.message, self.action = status, code, message, action


def fail(status, code, message, action):
    raise ImportFailure(status, code, message, action)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


@lru_cache(maxsize=8)
def _cached_schema(ver=None):
    return schema(ver)


@lru_cache(maxsize=1)
def _static_schema_hashes():
    return {v: digest(canonical(_cached_schema(v))) for v in SUPPORTED_CONTRACT_VERSIONS}


def mapping_contract(value):
    if isinstance(value,dict) and value.get('profile')=='rule_sources':
        from .rule_source_intake import mapping
        return mapping(value)
    if not isinstance(value, dict) or set(value) - {"tables","date_format"}:
        fail(422, "MAPPING_INVALID", "Mapping chỉ nhận đối tượng tables đổi tên cột.", "Không dùng biểu thức, giá trị mặc định hoặc quyền trong mapping.")
    tables = value.get("tables", {})
    if not isinstance(tables, dict):
        fail(422, "MAPPING_INVALID", "tables phải là đối tượng mapping theo từng bảng.", "Gửi tables: {transactions: {tên_cột_nguồn: tên_cột_chuẩn}}.")
    result = {}
    definitions = _cached_schema()["$defs"]
    for table, columns in tables.items():
        if table not in imports.DEFINITIONS or not isinstance(columns, dict):
            fail(422, "MAPPING_TABLE", "Bảng mapping không được hỗ trợ.", "Chọn bảng của hợp đồng đã khai báo; trường P1 mới cần contract 1.1.0.")
        allowed = definitions[imports.DEFINITIONS[table]]["properties"]
        for source, target in columns.items():
            if not isinstance(source, str) or not source.strip() or len(source) > 128 or not isinstance(target, str) or target not in allowed:
                fail(422, "MAPPING_FIELD", "Tên cột hoặc cột đích trong mapping không hợp lệ.", "Dẫn tên cột nguồn và một trường được khai báo trong schema; không đổi giá trị dữ liệu.")
        if len(set(columns.values())) != len(columns):
            fail(422, "MAPPING_COLLISION", "Hai cột nguồn đang cùng trỏ vào một cột đích.", "Giữ một nguồn duy nhất cho mỗi cột đích rồi kiểm tra lại.")
        renamed = {k:v for k,v in columns.items() if k != v}
        if renamed:
            result[table] = renamed
    date_format=value.get('date_format','iso')
    if date_format not in ('iso','dmy','mdy'):fail(422,'DATE_MAPPING','Định dạng ngày không hợp lệ.','Chọn ISO, ngày/tháng/năm hoặc tháng/ngày/năm.')
    output={"tables":result} if result else {}
    if date_format!='iso':output['date_format']=date_format
    return output


def context(scope):
    # Binds a preview to executable validation and permissions, not just a label.
    sh_hashes = dict(_static_schema_hashes())
    versions = dict(protocol_version=PROTOCOL_VERSION, parser_version=PARSER_VERSION,
        contract_version=CONTRACT_VERSION, schema_sha256=sh_hashes[CONTRACT_VERSION],
        supported_contract_versions=list(SUPPORTED_CONTRACT_VERSIONS),
        schema_hashes=sh_hashes,
        validator_version=imports.VALIDATOR_VERSION, profile_version=imports.PROFILE_VERSION,
        report_version=imports.REPORT_VERSION,
        parser_fingerprint=digest(Path(__file__).read_bytes()+Path(__file__).with_name('tabular_import.py').read_bytes()+Path(__file__).with_name('rule_source_intake.py').read_bytes()), jsonschema_version=version("jsonschema"),
        validator_fingerprint=digest(b"\n".join(Path(module.__file__).read_bytes()
            for module in (imports, imports.p1_inputs, core_validation, json_io))))
    identity = dict(tenant_id=scope.tenant_id, company_ids=sorted(scope.company_ids),
                    actor_id=scope.actor_id, permissions=sorted(scope.permissions))
    versions['agent2_rule_profile']='agent2-rule-snapshot/1.0.0'
    versions['agent2_rule_validator_sha256']=digest(b''.join(Path(__file__).with_name(name).read_bytes() for name in ('rule_snapshot.py','native_rule_node.py','native_rule_execution.py','exception_validation.py','rule_snapshot.schema.json')))
    return versions, digest(canonical(dict(versions=versions, identity=identity)))


def rejected(code, message, action, **detail):
    error = issue(code, "$", message, action)
    error.update(detail)
    return dict(status="rejected", contract_version=CONTRACT_VERSION, validator_version=imports.VALIDATOR_VERSION,
                profile_version=imports.PROFILE_VERSION, report_version=imports.REPORT_VERSION,
                errors=[error], warnings=[], counts={}, capabilities={}, analysis_limits={})


def _attach_locations(report, locations):
    if not locations:
        return
    for item in report.get('errors', []) + report.get('warnings', []):
        path = item.get('path', '')
        if not path:
            continue
        if path.startswith('/'):
            match = _SLASH_LOCATION_RE.match(path)
            if match and match[1] in locations:
                item.update(locations[match[1]])
            continue
        if path in locations:
            item.update(locations[path])
            continue
        dot_match = _DOT_LOCATION_RE.match(path)
        if dot_match and dot_match[1] in locations:
            prefix = dot_match[1]
            item.update(locations[prefix])
            tail = path[len(prefix):].lstrip('.')
            if tail:
                item['field'] = tail
            continue
        for prefix, where in locations.items():
            if path == prefix or path.startswith(prefix + '.'):
                item.update(where)
                tail = path[len(prefix):].lstrip('.')
                if tail:
                    item['field'] = tail
                break


def parse_file(raw, mapping, scope, filename='input.json'):
    cache_key = None
    if isinstance(raw, bytes) and isinstance(mapping, dict) and hasattr(scope, 'tenant_id'):
        try:
            _, ctx_hash = context(scope)
            cache_key = (digest(raw), digest(canonical(mapping)), filename, ctx_hash, MAX_ROWS)
            with _PARSE_CACHE_LOCK:
                if cache_key in _PARSE_CACHE:
                    _PARSE_CACHE.move_to_end(cache_key)
                    cached_parsed, cached_report = _PARSE_CACHE[cache_key]
                    return cached_parsed, deepcopy(cached_report)
        except Exception:
            cache_key = None

    tabular=filename.lower().endswith(('.csv','.xlsx'));locations={}
    try:
        if mapping.get('profile')=='rule_sources':
            from .rule_source_intake import parse
            from .tabular_import import TabularError
            try:data,locations=parse(raw,filename,mapping,scope)
            except TabularError as error:return None,rejected(error.code,error.message,error.action,**error.detail)
        elif tabular:
            from .tabular_import import parse,TabularError
            try:data,locations=parse(raw,filename,mapping)
            except TabularError as error:
                return None,rejected(error.code,error.message,error.action,**error.detail)
        else:data = json_io.loads(raw)
    except json.JSONDecodeError as error:
        return None, rejected("INVALID_JSON", "Cú pháp tệp JSON không hợp lệ.", "Sửa cú pháp tại dòng/cột JSON rồi tải lại tệp.", json_line=error.lineno, json_column=error.colno)
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        return None, rejected("INVALID_JSON", "Tệp phải là JSON UTF-8, không khóa lặp hoặc số không hữu hạn.", "Xuất lại tệp đúng hợp đồng rồi tải lại; không tự bỏ dòng lỗi.")
    if isinstance(data,dict) and data.get('contract_version')=='agent2-rule-snapshot/1.0.0' and mapping and mapping.get('profile')!='rule_sources':
        return None,rejected('RULE_MAPPING_UNSUPPORTED','Profile nguồn luật cần JSON đúng tên trường.','Xuất theo profile nguồn; không đổi mapping lồng nhau bằng giá trị mặc định.')
    if isinstance(data, dict):
        if sum(len(rows) for rows in data.values() if isinstance(rows, list)) > MAX_ROWS:
            return None, rejected("ROW_LIMIT", "Tệp vượt 100.000 bản ghi.", "Chia gói và giữ đủ các bản ghi được tham chiếu.")
        errors = []
        for table, columns in ({} if tabular or mapping.get('profile')=='rule_sources' else mapping.get("tables", {})).items():
            rows = data.get(table)
            if not isinstance(rows, list):
                continue  # canonical validator supplies the required/table error
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                renamed = {}
                for source, value in row.items():
                    target = columns.get(source, source)
                    if target in renamed:
                        errors.append(issue("MAPPING_COLLISION", f"/{table}/{index}/{target}",
                            "Mapping làm hai cột trên cùng dòng ghi đè nhau.", "Sửa mapping để mỗi cột đích có đúng một nguồn; không bỏ cột ngầm."))
                    renamed[target] = value
                rows[index] = renamed
        if errors:
            report = rejected("MAPPING_COLLISION", "Mapping có cột ghi đè.", "Sửa mapping rồi kiểm tra lại.")
            if data.get('contract_version') in SUPPORTED_CONTRACT_VERSIONS:report['contract_version']=data['contract_version']
            report["errors"] = errors
            return None, report
    try:
        report = imports.validate_input(data, scope)
    except (RecursionError, OverflowError):
        return None, rejected("INPUT_STRUCTURE", "Cấu trúc dữ liệu quá sâu hoặc không hợp lệ.", "Xuất lại theo schema 1.0.0.")
    if mapping.get('profile')=='rule_sources' and report['status']!='rejected':
        from .rule_source_intake import readiness
        try:report['rule_readiness']=readiness(data,scope)
        except (KeyError,ValueError,ZeroDivisionError) as error:
            field=str(error.args[0]) if isinstance(error,KeyError) else None
            report['status']='rejected'
            report['errors'].append(dict(code='RULE_EXECUTION_INPUT',path='source.tables',table=None,row=None,field=field,
                message='Nguồn chưa đủ trường để chạy kiểm tra'+(': '+field if field else ' hoặc còn giá trị ngoài miền hỗ trợ')+'.',
                action='Đối chiếu các bảng/cột với mẫu 35 luật; giữ nguyên nguồn và bổ sung dữ liệu, không tự điền 0.'))
    if tabular or mapping.get('profile')=='rule_sources':
        report['source_format']='xlsx' if filename.lower().endswith('.xlsx') else 'csv'
        _attach_locations(report, locations)
    parsed_bytes = canonical(data) if report["status"] != "rejected" else None
    if parsed_bytes is not None and hasattr(scope, "tenant_id") and hasattr(scope, "company_ids"):
        imports.mark_validated_checksum(digest(parsed_bytes), scope.tenant_id, scope.company_ids)
    if cache_key is not None:
        with _PARSE_CACHE_LOCK:
            _PARSE_CACHE[cache_key] = (parsed_bytes, deepcopy(report))
            while len(_PARSE_CACHE) > 8:
                _PARSE_CACHE.popitem(last=False)
    return parsed_bytes, report
