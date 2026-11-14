"""One executable schema plus common scope, chronology and identity checks."""
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
import json
import re

from jsonschema import Draft202012Validator, FormatChecker, validators

CONTRACT_VERSION = "1.1.0"
SUPPORTED_CONTRACT_VERSIONS = ("1.0.0", "1.1.0", "1.2.0")
TABLES = ("companies", "transactions", "vendors", "invoices", "payment_allocations",
          "employees", "approvals", "supporting_documents", "vendor_bank_history", "payment_history_coverage")


@dataclass(frozen=True)
class AccessScope:
    """Trusted caller context. Not a token parser or an authentication mechanism."""
    tenant_id: str
    company_ids: frozenset[str]
    actor_id: str
    permissions: frozenset[str]


def schema(version=None):
    version=CONTRACT_VERSION if version is None else version
    if version not in SUPPORTED_CONTRACT_VERSIONS:raise ValueError('Unsupported input contract version')
    name={'1.0.0':'input.v1_0.schema.json','1.1.0':'input.schema.json','1.2.0':'input.v1_2.schema.json'}[version]
    return json.loads(files("finance_input").joinpath(name).read_text("utf-8"))


def stamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value
    ):
        raise ValueError("ISO timestamp with timezone required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None or value.endswith("-00:00"):
        raise ValueError("Unknown timezone")
    return result


FORMATS = FormatChecker()


@FORMATS.checks("source-timestamp", raises=(ValueError, TypeError))
def _timestamp(value):
    stamp(value)
    return True


# JSON Schema ordinarily regards 1.0 as an integer; money/versions must be real ints.
StrictValidator = validators.extend(Draft202012Validator, type_checker=
    Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _checker, value: type(value) is int))


def issue(code, path, message, action):
    parts = path.strip("/").split("/")
    row = int(parts[1]) + 1 if len(parts) > 1 and parts[1].isdigit() else None
    field = "/".join(parts[2:]) if len(parts) > 2 else None
    table = parts[0] if parts[0] in TABLES else None
    return dict(code=code, path=path, table=table, row=row, field=field, message=message, action=action)


def _pointer(path):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in path)


def _schema_issues(error):
    path = list(error.absolute_path)
    if error.validator == "required" and isinstance(error.instance, dict):
        for field in error.validator_value:
            if field not in error.instance:
                names = {"company_id":"mã doanh nghiệp", "tenant_id":"mã tổ chức", "amount_vnd":"số tiền VND", "observed_at":"thời điểm nguồn được biết", "effective_at":"thời điểm nghiệp vụ", "record_id":"mã bản ghi"}
                name = "mã giao dịch" if field == "record_id" and path and path[0] == "transactions" else names.get(field, field)
                yield issue("REQUIRED_FIELD", _pointer([*path, field]), f"Thiếu {name}.",
                            f"Bổ sung {name} từ nguồn rồi gửi lại; không tự điền giá trị giả.")
        return
    if error.validator == "anyOf":
        # Nullable references: prefer actionable nested errors for object inputs.
        specific = [e for e in error.context if e.validator != "type"]
        if specific:
            for child in specific:
                yield from _schema_issues(child)
            return
    if error.validator == "additionalProperties" and isinstance(error.instance, dict):
        allowed = error.schema.get("properties", {})
        for field in sorted(error.instance.keys() - allowed.keys(), key=str):
            if isinstance(field, str) and len(field) <= 128 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field):
                yield issue("UNKNOWN_FIELD", _pointer([*path, field]), "Cột không có trong hợp đồng dữ liệu.",
                            "Sửa tên cột hoặc mapping theo schema; không âm thầm bỏ cột.")
            else:
                yield issue("UNKNOWN_FIELD", _pointer(path), "Có tên cột không hợp lệ hoặc không được hỗ trợ.",
                            "Đối chiếu tên cột với phiên bản schema đã khai báo và sửa mapping.")
        return
    messages = {
        "type": ("Sai kiểu dữ liệu.", "Dùng đúng kiểu trong schema; tiền VND và revision phải là số nguyên, ID phải là chuỗi."),
        "format": ("Thời điểm không hợp lệ hoặc thiếu múi giờ.", "Dùng ISO 8601 có giờ và offset, ví dụ 2026-10-10T10:00:00+07:00; không đoán ngày hoặc múi giờ."),
        "pattern": ("Định dạng trường không hợp lệ.", "Kiểm tra định dạng ID, thời điểm hoặc SHA256 theo schema; giữ ID ở dạng chuỗi."),
        "enum": ("Giá trị không nằm trong danh sách được hỗ trợ.", "Chọn giá trị cho phép của trường trong phiên bản schema đã khai báo."),
        "const": ("Giá trị không đúng phiên bản hoặc đơn vị được hỗ trợ.", "Dùng contract_version 1.0.0 hoặc 1.1.0 và currency VND theo đúng trường."),
        "minimum": ("Giá trị nhỏ hơn giới hạn cho phép.", "Kiểm tra giới hạn trường; revision bắt đầu từ 1, không sửa dấu điều chỉnh hợp lệ."),
        "maximum": ("Giá trị vượt giới hạn cho phép.", "Kiểm tra đơn vị và giới hạn 18 chữ số VND; không cắt số hoặc làm tròn."),
        "minLength": ("Trường chưa có giá trị.", "Bổ sung giá trị từ nguồn; nếu là trường tùy chọn chưa biết, dùng null/trạng thái thiếu phù hợp."),
    }
    message, action = messages.get(error.validator, ("Trường không đúng hợp đồng dữ liệu.", "Đối chiếu giá trị với phiên bản schema đã khai báo rồi gửi lại."))
    yield issue("SCHEMA", _pointer(path), message, action)


def records(bundle):
    for table in TABLES:
        for index, row in enumerate(bundle.get(table, [])):
            yield table, index, row


def key(table, row):
    return (row["tenant_id"], row["company_id"], table, row["record_id"], row["revision"])


def check_core(bundle, scope):
    """Return all errors; never silently drop rows or fill observation times.

    Scope is checked before schema/row traversal. Permission to pass this function
    does not grant permission to open a file; API must authenticate before I/O.
    """
    denied = [issue("ACCESS_DENIED", "$", "Không có quyền nhập trong phạm vi này.",
                    "Dùng tài khoản được cấp data.import cho đúng doanh nghiệp.")]
    if not isinstance(scope, AccessScope) or not scope.actor_id or not scope.tenant_id:
        return denied
    if "data.import" not in scope.permissions or not scope.company_ids:
        return denied
    def valid_identifier(value):
        return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is not None
    if isinstance(bundle, dict) and valid_identifier(bundle.get("tenant_id")) and bundle["tenant_id"] != scope.tenant_id:
        return denied
    # No row values, foreign IDs or counts are included in an access denial.
    for table in TABLES if isinstance(bundle, dict) else ():
        rows = bundle.get(table, [])
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and (
                    (valid_identifier(row.get("tenant_id")) and row["tenant_id"] != scope.tenant_id) or
                    (valid_identifier(row.get("company_id")) and row["company_id"] not in scope.company_ids)
                ):
                    return denied
    errors = []
    seen_errors = set()
    declared=bundle.get('contract_version') if isinstance(bundle,dict) else None
    selected=declared if isinstance(declared,str) and declared in SUPPORTED_CONTRACT_VERSIONS else CONTRACT_VERSION
    for error in StrictValidator(schema(selected), format_checker=FORMATS).iter_errors(bundle):
        for detail in _schema_issues(error):
            identity = (detail["code"], detail["path"])
            if identity not in seen_errors:
                errors.append(detail)
                seen_errors.add(identity)
    if errors:
        return errors
    seen = set()
    timelines = {}
    declared = {row["company_id"] for row in bundle["companies"]}
    for table, index, row in records(bundle):
        path = f"/{table}/{index}"
        if row["company_id"] not in declared:
            errors.append(issue("COMPANY_MISSING", path+"/company_id", "Chưa có doanh nghiệp trong danh mục.",
                                "Bổ sung bản ghi companies trong cùng gói dữ liệu."))
        if table == "companies" and row["record_id"] != row["company_id"]:
            errors.append(issue("COMPANY_ID", path+"/record_id", "ID danh mục doanh nghiệp không khớp company_id.",
                                "Dùng cùng mã ở record_id và company_id của doanh nghiệp."))
        identity = key(table, row)
        if identity in seen:
            errors.append(issue("DUPLICATE_REVISION", path+"/record_id", "Trùng định danh và phiên bản trong doanh nghiệp.",
                                "Bỏ bản sao nhập trùng; sửa đổi nghiệp vụ phải tạo revision mới."))
        seen.add(identity)
        timelines.setdefault(identity[:-1], []).append((row["revision"], stamp(row["observed_at"]), path))
    for versions in timelines.values():
        ordered = sorted(versions)
        for previous, current in zip(ordered, ordered[1:]):
            if current[1] < previous[1]:
                errors.append(issue("REVISION_TIME", current[2]+"/observed_at", "Revision mới có thời điểm biết sớm hơn revision cũ.",
                                    "Kiểm tra revision và observed_at; không ghi lùi lịch sử đã biết."))
    return errors
