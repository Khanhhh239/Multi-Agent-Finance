"""Friendly canonical input contracts and explicit observation clocks."""

import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import datetime, date as calendar_date
import pandas as pd
from unidecode import unidecode
from agent1_service.ingest.money import minor
from agent1_service.ingest.invoices import (
    validate_invoices,
    reconcile_invoices,
    resolve_references,
    validate_cancellations,
    effective_invoices,
)

SCHEMAS = {
    "invoices": {
        "invoice_id": ["ma hoa don", "so hoa don"],
        "customer_id": ["ma khach hang", "khach hang"],
        "issue_date": ["ngay lap", "ngay hoa don"],
        "due_date": ["han thanh toan", "ngay den han"],
        "amount": ["so tien", "tong thanh toan", "amount_gross"],
        "known_at": ["ngay ghi nhan", "available_on"],
        "currency": ["tien te"],
    },
    "payments": {
        "payment_id": ["ma thanh toan", "ma giao dich", "txn_id"],
        "invoice_id": ["ma hoa don", "so hoa don"],
        "payment_date": ["ngay thanh toan", "ngay tien ve", "value_date"],
        "amount": ["so tien"],
        "known_at": ["ngay ghi nhan", "available_on"],
    },
    "outflows": {
        "expense_id": ["ma khoan chi"],
        "date": ["ngay chi"],
        "amount": ["so tien"],
        "category": ["loai chi"],
        "known_at": ["ngay ghi nhan", "available_on"],
    },
}
REQUIRED = {k: set(v) - {"known_at", "currency"} for k, v in SCHEMAS.items()}
REQUIRED["outflows"].add("known_at")
IDS = {"invoices": "invoice_id", "payments": "payment_id", "outflows": "expense_id"}
SCHEMAS["outflows"]["expense_id"].append("obligation_id")
SCHEMAS["outflows"]["date"].append("due_date")
SCHEMAS["outflows"].update({
    "obligation_ref": ["ma hop dong", "contract_id", "ma khoan co dinh", "fixed_cost_id"],
    "payment_period": ["ky thanh toan", "ky nghia vu"],
    "installment_no": ["dot den han", "dot thanh toan"],
    "status": ["trang thai nghia vu"],
    "forecast_date": ["ngay du kien tra con lai"],
    "source": ["ho so hop dong"],
    "verified": ["da xac nhan ho so"],
    "refund_approved_at": ["ngay quyet dinh hoan"],
    "business_day": ["quy uoc ngay lam viec"],
    "replaces_expense_id": ["ma lich duoc thay the"],
})
SCHEMAS["expense_payments"] = {
    "settlement_id": ["ma thanh toan nghia vu"],
    "expense_id": ["ma khoan chi", "obligation_id"],
    "bank_id": ["ma dong sao ke"],
    "payment_date": ["ngay thanh toan"],
    "amount": ["so tien"],
    "known_at": ["ngay ghi nhan", "available_on"],
}
REQUIRED["expense_payments"] = set(SCHEMAS["expense_payments"])
IDS["expense_payments"] = "settlement_id"
SCHEMAS["payments"]["bank_id"] = ["ma dong sao ke"]
SCHEMAS["bank"] = {
    "bank_id": ["ma dong sao ke"],
    "account": ["tai khoan", "account_id"],
    "date": ["ngay giao dich", "value_date"],
    "direction": ["thu chi"],
    "amount": ["so tien"],
    "known_at": ["ngay ghi nhan", "available_on"],
}
SCHEMAS["statements"] = {
    "statement_id": ["ma ky sao ke"],
    "account": ["tai khoan", "account_id"],
    "start_date": ["tu ngay"],
    "end_date": ["den ngay"],
    "opening_balance": ["so du dau ky"],
    "closing_balance": ["so du cuoi ky"],
    "known_at": ["ngay ghi nhan", "available_on"],
}
IDS.update(bank="bank_id", statements="statement_id")
for kind in ("bank", "statements"):
    REQUIRED[kind] = set(SCHEMAS[kind]) - {"known_at"}
SCHEMAS["bank"]["component"] = ["nhom du bao"]
SCHEMAS["bank"].update({
    "memo": ["noi dung", "noi dung chuyen khoan", "dien giai"],
    "counterparty": ["ten nguoi chuyen", "ten doi tac"],
    "customer_id": ["ma khach hang", "ma khach"],
    "cash_flow_class": ["loai dong tien"],
})
SCHEMAS["invoices"]["customer_name"] = ["ten khach hang", "ten nguoi mua"]
SCHEMAS["actions"] = {
    "event_id": ["ma su kien"],
    "invoice_id": ["ma hoa don"],
    "date": ["ngay su kien"],
    "kind": ["hanh dong"],
    "promise_date": ["ngay hua tra"],
    "known_at": ["ngay ghi nhan", "available_on"],
}
IDS["actions"] = "event_id"
REQUIRED["actions"] = {"event_id", "invoice_id", "date", "kind"}

# Basic exports remain usable. Supplying accounting fields opts into the full
# T0 contract; lifecycle documents must never be admitted with invented tax data.
ACCOUNTING = {"seller_mst", "buyer_mst", "symbol", "invoice_no", "amount_net", "vat"}
SCHEMAS["invoices"].update(
    {
        "seller_mst": ["mst nguoi ban"],
        "buyer_mst": ["mst nguoi mua"],
        "symbol": ["ky hieu"],
        "invoice_no": ["so chung tu"],
        "amount_net": ["tien truoc thue"],
        "vat": ["tien thue"],
        "record_version": ["phien ban chung tu"],
        "adjustment_type": ["loai dieu chinh"],
        "adjusts_invoice_id": ["ma hoa don goc"],
        "adjusts_symbol": ["ky hieu hoa don goc"],
        "adjusts_invoice_no": ["so hoa don goc"],
        "adjusts_issue_date": ["ngay lap hoa don goc"],
    }
)
SCHEMAS["invoice_events"] = {
    "event_id": ["ma su kien"],
    "invoice_id": ["ma hoa don"],
    "event_type": ["loai su kien"],
    "event_date": ["ngay huy"],
    "known_at": ["ngay ghi nhan", "available_on"],
}
IDS["invoice_events"] = "event_id"
REQUIRED["invoice_events"] = set(SCHEMAS["invoice_events"])
MONEY_FIELDS = {"amount", "amount_net", "vat", "opening_balance", "closing_balance"}
for _kind in ("payments", "outflows", "expense_payments", "bank", "statements"):
    SCHEMAS[_kind]["currency"] = ["tien te"]


def vnd(value):
    """Accept exact integer Excel cells, never round fractional/unsafe floats."""
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer() or abs(value) > 2**53 - 1:
            raise ValueError("VND phải là số nguyên chính xác; dùng ô Text cho số lớn")
        value = int(value)
    return minor(value, "VND")


def suggested_mapping(columns, kind):
    normalize = lambda x: unidecode(str(x)).lower().strip().replace("_", " ")
    return {
        field: next(
            (
                str(c)
                for c in columns
                if normalize(c) in [normalize(field), *[normalize(a) for a in aliases]]
            ),
            "",
        )
        for field, aliases in SCHEMAS[kind].items()
    }


def parse_rows(
    raw, kind, mapping, date_format="%d/%m/%Y", number_format="vi-VN", *, source="erp"
):
    if kind not in SCHEMAS:
        raise ValueError("Bảng không được hỗ trợ")
    if date_format not in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y"]:
        raise ValueError("Chọn ngày dd-mm-yy, dd/mm/yyyy hoặc yyyy-mm-dd")
    if number_format not in ["vi-VN", "plain"]:
        raise ValueError("Chọn định dạng số tiền")
    missing = [
        c for c in REQUIRED[kind] if not mapping.get(c) or mapping[c] not in raw.columns
    ]
    if missing:
        return (
            [],
            [
                dict(row=1, column=c, message="Chưa ghép cột bắt buộc")
                for c in sorted(missing)
            ],
            [],
        )
    records = []
    errors = []
    seen = set()
    warnings = []
    for index, raw_row in raw.iterrows():
        row = {}
        bad = False
        adjustment = kind == "invoices" and (
            str(raw_row.get(mapping.get("adjustment_type"), "")).strip() == "adjustment"
        )
        for field in SCHEMAS[kind]:
            col = mapping.get(field)
            value = raw_row.get(col) if col else None
            if value is None or pd.isna(value) or str(value).strip() == "":
                if field in REQUIRED[kind]:
                    errors.append(
                        dict(
                            row=int(index) + 2,
                            column=field,
                            message="Ô bắt buộc đang trống",
                        )
                    )
                    bad = True
                continue
            try:
                if field in MONEY_FIELDS:
                    if isinstance(value, str):
                        value = value.strip().replace(" ", "")
                        pattern = (
                            r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?"
                            if number_format == "vi-VN"
                            else r"\d+(?:\.\d+)?"
                        )
                        if (
                            field in ("opening_balance", "closing_balance")
                            or adjustment
                        ):
                            pattern = "-?" + pattern
                        if not re.fullmatch(pattern, value):
                            raise ValueError()
                        if number_format == "vi-VN":
                            value = value.replace(".", "").replace(",", ".")
                    value = vnd(value)
                    if field == "amount" and (
                        value == 0 or (value < 0 and not adjustment)
                    ):
                        raise ValueError()
                elif field in ("record_version", "installment_no"):
                    if field == "installment_no" and isinstance(value, float) and value.is_integer():
                        value = int(value)
                    if not re.fullmatch(r"[1-9]\d*", str(value)):
                        raise ValueError()
                    value = str(value) if field == "installment_no" else int(value)
                elif field == "verified":
                    if str(value).strip().lower() not in ("true", "false"):
                        raise ValueError()
                    value = str(value).strip().lower() == "true"
                elif field.endswith("date") or field in ["date", "known_at", "refund_approved_at"]:
                    parsed = (
                        pd.Timestamp(value)
                        if isinstance(value, (datetime, calendar_date, pd.Timestamp))
                        else pd.to_datetime(value, format=date_format, errors="raise")
                    )
                    if pd.isna(parsed) or parsed.tzinfo is not None:
                        raise ValueError()
                    value = parsed.date().isoformat()
                else:
                    value = str(value).strip()
                row[field] = value
            except (ValueError, TypeError, OverflowError):
                errors.append(
                    dict(
                        row=int(index) + 2,
                        column=field,
                        message="Giá trị không hợp lệ; kiểm tra định dạng đã chọn",
                    )
                )
                bad = True
        if bad:
            continue
        key = row[IDS[kind]]
        if key in seen:
            errors.append(
                dict(
                    row=int(index) + 2,
                    column=IDS[kind],
                    message="Mã bị trùng trong file",
                )
            )
            continue
        seen.add(key)
        date = row.get(
            "issue_date",
            row.get(
                "payment_date",
                row.get("date", row.get("end_date", row.get("event_date"))),
            ),
        )
        if kind == "bank":
            row["direction"] = {"thu": "in", "chi": "out"}.get(
                row["direction"].strip().lower(), row["direction"].strip().lower()
            )
            if row["direction"] not in ("in", "out"):
                errors.append(
                    dict(
                        row=int(index) + 2,
                        column="direction",
                        message="Chọn thu hoặc chi",
                    )
                )
                continue
        if kind == "statements" and row["end_date"] < row["start_date"]:
            errors.append(
                dict(
                    row=int(index) + 2,
                    column="end_date",
                    message="Ngày cuối phải từ ngày đầu kỳ",
                )
            )
            continue
        accounting = kind == "invoices" and (
            ACCOUNTING.intersection(row)
            or row.get("adjustment_type")
            or any(k.startswith("adjusts_") for k in row)
        )
        if "known_at" not in row:
            row["known_at"] = (
                str(pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date())
                if accounting
                else date
            )
            warnings.append(
                "Thiếu ngày ghi nhận chứng từ kế toán: dùng ngày nạp, không suy là đã biết từ ngày lập."
                if accounting
                else "Thiếu ngày ghi nhận: giả định dữ liệu được biết từ ngày nghiệp vụ. Kiểm định lịch sử dựa trên giả định này."
            )
        if row.get("currency", "VND") != "VND":
            errors.append(
                dict(
                    row=int(index) + 2,
                    column="currency",
                    message="Luồng này chỉ nhận VND; không tự quy đổi ngoại tệ",
                )
            )
            continue
        if kind != "outflows" and row["known_at"] < date:
            errors.append(
                dict(
                    row=int(index) + 2,
                    column="known_at",
                    message="Ngày ghi nhận phải từ ngày nghiệp vụ trở đi",
                )
            )
            continue
        if kind == "invoices":
            row.setdefault("currency", "VND")
            if row["due_date"] < row["issue_date"]:
                errors.append(
                    dict(
                        row=int(index) + 2,
                        column="due_date",
                        message="Hạn trả trước ngày lập",
                    )
                )
                continue
            row.setdefault("record_version", 1)
            if accounting:
                try:
                    canonical = validate_invoices(
                        [
                            dict(
                                row,
                                amount_gross=row["amount"],
                                available_on=row["known_at"],
                            )
                        ],
                        source=source,
                    )[0]
                    row = dict(
                        canonical, amount=row["amount"], known_at=row["known_at"]
                    )
                except ValueError as exc:
                    errors.append(
                        dict(row=int(index) + 2, column="invoice_id", message=str(exc))
                    )
                    continue
            else:
                warnings.append(
                    "Hóa đơn đơn giản chưa có MST, ký hiệu/số và tiền trước thuế/VAT: chưa kiểm tra đủ T0; không dùng cho điều chỉnh/thay thế."
                )
        records.append(row)
    return records, errors, list(dict.fromkeys(warnings))


def as_of(data, clock):
    """Select whole record versions by knowledge date, including late corrections."""
    stamp = pd.Timestamp(clock)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert('Asia/Ho_Chi_Minh').tz_localize(None)
    limit = stamp.date().isoformat()
    intraday = (isinstance(clock, str) and len(clock) > 10
                or isinstance(clock, (datetime, pd.Timestamp)) and stamp != stamp.normalize())
    result = dict(data)
    for kind, history in data.get("record_history", {}).items():
        selected = {}
        for row in history:
            if row["known_at"] > limit:
                continue
            if not intraday:
                selected[row[IDS[kind]]] = row
                continue
            available = pd.Timestamp(row.get('known_at_time') or row['known_at'])
            if available.tzinfo is not None:
                available = available.tz_convert('Asia/Ho_Chi_Minh').tz_localize(None)
            if available <= stamp:
                selected[row[IDS[kind]]] = row
        result[kind] = [r for r in selected.values() if not r.get("_deleted")]
    return result


def merge_import(data, kind, incoming):
    """Stage one import without mutating the active dataset or its audit history."""
    if kind == 'outflows':
        from .obligation_imports import plan_obligation_import
        plan = plan_obligation_import(data, incoming)
        if plan['errors']:
            raise ValueError('; '.join('Dòng ' + str(e['row']) + ': ' + e['message'] for e in plan['errors']))
        incoming = plan['records']
    result = deepcopy(data)
    existing = {r[IDS[kind]]: r for r in result.get(kind, [])}
    for row in incoming:
        old = existing.get(row[IDS[kind]])
        if old and row["known_at"] < old["known_at"]:
            raise ValueError("Ngày ghi nhận của phiên bản đi lùi")
    history = result.setdefault("record_history", {}).setdefault(
        kind, list(existing.values())
    )
    last_known = {}
    for version in history:
        key = version[IDS[kind]]
        last_known[key] = max(last_known.get(key, "0001-01-01"), version["known_at"])
    for row in incoming:
        key = row[IDS[kind]]
        if key not in existing and key in last_known and row["known_at"] <= last_known[key]:
            raise ValueError("Nhập lại mã đã xóa cần ngày ghi nhận mới hơn lịch sử trước; không được sửa ngược snapshot")
    if kind == "invoices":
        full = [r for r in incoming if ACCOUNTING <= r.keys()]
        old_full = [r for r in existing.values() if ACCOUNTING <= r.keys()]
        # Reuse source/version checks and XML/ERP identity merging from T0.
        if full:
            business_keys = {
                (r["seller_mst"], r["symbol"], r["invoice_no"]) for r in old_full
            }
            for row in full:
                old = existing.get(row["invoice_id"])
                if old and not ACCOUNTING <= old.keys():
                    if (
                        row.get("adjustment_type")
                        or any(
                            old.get(k) != row.get(k)
                            for k in (
                                "amount",
                                "issue_date",
                                "due_date",
                                "customer_id",
                                "currency",
                            )
                        )
                        or (row["seller_mst"], row["symbol"], row["invoice_no"])
                        in business_keys
                    ):
                        raise ValueError(
                            "Bổ sung chứng từ cần cùng mã, khách hàng, ngày và số tiền; đối chiếu hóa đơn trước"
                        )
            _, updates = reconcile_invoices(old_full, full)
            for row in updates:
                row["known_at"] = max(row["known_at"], row["available_on"])
                row["amount"] = row["amount_gross_minor"]
        else:
            updates = []
        for row in incoming:
            if ACCOUNTING <= row.keys():
                continue
            old = existing.get(row["invoice_id"])
            if old and ACCOUNTING <= old.keys():
                raise ValueError("Không được bỏ thông tin kế toán của hóa đơn đã nhập")
            updates.append(row)
    elif kind == "invoice_events":
        events = [dict(r, available_on=r["known_at"]) for r in incoming]
        validated = validate_cancellations(
            list(existing.values()), events, result.get("invoices", [])
        )
        updates = [r for r in validated if r["event_id"] not in existing]
    else:
        aliases = {
            alias: r["invoice_id"]
            for r in result.get("invoices", [])
            for alias in r.get("source_ids", {}).values()
        }
        updates = [
            dict(r, invoice_id=aliases.get(r["invoice_id"], r["invoice_id"]))
            if "invoice_id" in r
            else r
            for r in incoming
        ]
    for row in updates:
        row = dict(row)
        key = row[IDS[kind]]
        old = existing.get(key)
        if old == row:
            continue
        if old:
            # Same-day XML/ERP confirmations may add lineage, but cannot change
            # the financial facts that an earlier forecast was allowed to see.
            confirmation = kind == "invoices" and all(
                old.get(k) == row.get(k)
                for k in ("amount", "issue_date", "due_date", "customer_id", "currency")
            )
            if ACCOUNTING <= old.keys():
                confirmation = confirmation and all(
                    old.get(k) == row.get(k)
                    for k in ACCOUNTING
                    | {
                        "adjustment_type",
                        "adjusts_invoice_id",
                        "adjusts_symbol",
                        "adjusts_invoice_no",
                        "adjusts_issue_date",
                    }
                )
            if row["known_at"] < old["known_at"] or (
                row["known_at"] == old["known_at"] and not confirmation
            ):
                raise ValueError(
                    "Bản sửa cần ngày ghi nhận mới hơn bản trước; không ghi đè lịch sử"
                )
            if (
                kind == "invoices"
                and not ACCOUNTING <= row.keys()
                and row.get("record_version", 1) <= old.get("record_version", 1)
                and not confirmation
            ):
                raise ValueError("Cần tăng record_version khi sửa hóa đơn")
        existing[key] = row
        history.append(row)
    result[kind] = list(existing.values())
    if kind == "invoices":
        resolve_references(result[kind])
    validate_dataset(result)
    return result


def invoice_view(data, clock=None):
    """Use the original lifecycle engine; exact VND stays in the canonical rows."""
    columns = [
        "invoice_id",
        "customer_id",
        "issue_date",
        "due_date",
        "known_at",
        "amount",
    ]
    rows = deepcopy(data.get("invoices", []))
    if not rows:
        return pd.DataFrame(columns=columns)
    events = data.get("invoice_events", [])
    for row in rows:
        row.setdefault("amount_gross_minor", vnd(row["amount"]))
        row.setdefault("amount_gross", str(row["amount"]))
        row.setdefault("currency", "VND")
    frame = effective_invoices(rows, events, clock)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["amount"] = frame.amount_gross_minor.map(int)
    # A late adjustment must not become an issuance-time feature or backdate a
    # settlement that became complete only through that adjustment.
    adjustments = {}
    by_id = {r["invoice_id"]: r for r in rows}
    limit = str(pd.Timestamp(clock).date()) if clock is not None else None
    for row in rows:
        if row.get("adjustment_type") == "adjustment" and (
            limit is None or (row["known_at"] <= limit and row["issue_date"] <= limit)
        ):
            adjustments.setdefault(row["adjusts_invoice_id"], []).append(row)
    # Plain lists and one column assignment: iterrows() with three .at writes per row took minutes on 50,000 invoices.
    known_at, balance_date, origin_date = [], [], []
    for invoice_id, known, issued in zip(frame["invoice_id"], frame["known_at"], frame["issue_date"]):
        changes = adjustments.get(invoice_id, [])
        known_at.append(max([known, *[r["known_at"] for r in changes]]))
        balance_date.append(max([issued, *[r["issue_date"] for r in changes]]))
        root = by_id[invoice_id]
        while root.get("adjustment_type") == "replacement":
            root = by_id[root["adjusts_invoice_id"]]
        origin_date.append(root["issue_date"])
    frame["known_at"] = known_at
    frame["balance_effective_date"] = balance_date
    frame["origin_issue_date"] = origin_date
    return frame


def _payment_links(invoices):
    links = {
        alias: r["invoice_id"]
        for r in invoices
        for alias in r.get("source_ids", {}).values()
        if alias != r["invoice_id"]
    }
    links.update(
        {
            r["adjusts_invoice_id"]: r["invoice_id"]
            for r in invoices
            if r.get("adjustment_type") == "replacement"
        }
    )
    links.update(
        {
            r["invoice_id"]: r["adjusts_invoice_id"]
            for r in invoices
            if r.get("adjustment_type") == "adjustment"
        }
    )
    return links


def payment_target(invoice_id, links):
    """Carry allocations forward through replacement chains, once per receipt."""
    seen = set()
    while invoice_id in links:
        if invoice_id in seen:
            raise ValueError("Tham chiếu hóa đơn vòng")
        seen.add(invoice_id)
        invoice_id = links[invoice_id]
    return invoice_id


def effective_data(data, clock):
    """Numeric consumers use active debts rather than counting credit notes as sales."""
    result = as_of(data, clock)
    limit = str(pd.Timestamp(clock).date())
    links = _payment_links(
        [
            r
            for r in result.get("invoices", [])
            if r["known_at"] <= limit and r["issue_date"] <= limit
        ]
    )
    frame = invoice_view(result, clock)
    result["invoices"] = frame.to_dict("records")
    for kind in ("payments", "actions"):
        result[kind] = [dict(r, invoice_id=payment_target(r["invoice_id"], links))
                        for r in result.get(kind, [])]
    return result


def account_scope(data, clock):
    return sorted(
        data.get("bank_scope", {}).get("accounts")
        or {
            r["account"]
            for kind in ("bank", "statements")
            for r in as_of(data, clock).get(kind, [])
            if r["known_at"] <= str(pd.Timestamp(clock).date())
        }
    )


def validate_dataset(data):
    from agent1.reconciliation.pipeline import NON_AR
    for kind in SCHEMAS:
        for row in data.get(kind, []):
            if row.get("currency", "VND") != "VND":
                raise ValueError("Luồng này chỉ nhận VND; không tự quy đổi ngoại tệ")
            for field in MONEY_FIELDS.intersection(row):
                amount = vnd(row[field])
                if (
                    field == "amount"
                    and not (
                        kind == "invoices"
                        and row.get("adjustment_type") == "adjustment"
                    )
                    and amount <= 0
                ):
                    raise ValueError(
                        "Số tiền phải dương, trừ chênh lệch điều chỉnh hóa đơn"
                    )
    canonical = deepcopy(data.get("invoices", []))
    resolve_references(canonical)
    by_id = {r["invoice_id"]: r for r in canonical}

    def target_was_known(target, known):
        return target["known_at"] <= known or any(
            r["invoice_id"] == target["invoice_id"] and r["known_at"] <= known
            for r in as_of(data, known).get("invoices", [])
        )

    for row in canonical:
        if row.get("adjustment_type"):
            target = by_id[row["adjusts_invoice_id"]]
            if not ACCOUNTING <= target.keys() or not target_was_known(
                target, row["known_at"]
            ):
                raise ValueError(
                    "Hóa đơn liên quan cần đủ thông tin kế toán và được ghi nhận trước chứng từ mới"
                )
    events = validate_cancellations(
        [],
        [dict(r, available_on=r["known_at"]) for r in data.get("invoice_events", [])],
        canonical,
    )
    for e in events:
        if not target_was_known(by_id[e["invoice_id"]], e["known_at"]):
            raise ValueError("Sự kiện hủy ghi nhận trước hóa đơn")
    effective = (
        invoice_view(dict(data, invoices=canonical))
        .set_index("invoice_id")
        .amount.to_dict()
    )
    bank = {r["bank_id"]: r for r in data.get("bank", [])}
    for r in bank.values():
        component = r.get("component", "other")
        if (
            component not in ("other", "cash_sale", "variable_cost")
            or (component == "cash_sale" and r["direction"] != "in")
            or (component == "variable_cost" and r["direction"] != "out")
        ):
            raise ValueError(
                "Sai nhóm sao kê. cash_sale dùng cho bán thu ngay, variable_cost cho chi biến đổi, other cho dòng khác."
            )
    allocations = {}
    invoices = {r["invoice_id"]: r for r in data.get("invoices", [])}
    for e in data.get("actions", []):
        if (
            e["invoice_id"] not in invoices
            or e["date"] < invoices[e["invoice_id"]]["issue_date"]
        ):
            raise ValueError("Sự kiện sai hóa đơn/ngày: " + e["event_id"])
        if e["kind"] not in (
            "contact",
            "promise",
            "dispute",
            "resolved",
            "write_off",
            "skip",
        ):
            raise ValueError(
                "Chọn contact, promise, dispute, resolved, write_off hoặc skip"
            )
        if e["kind"] == "promise" and e.get("promise_date", "") < e["date"]:
            raise ValueError("Ngày hứa trả phải từ ngày ghi lời hứa")
    paid = {}
    links = _payment_links(canonical)
    bank_parties = {}
    for row in data.get("payments", []):
        if row["invoice_id"] not in invoices:
            raise ValueError("Thanh toán tham chiếu hóa đơn chưa có: " + row["invoice_id"])
        inv = invoices[row["invoice_id"]]
        target = payment_target(row["invoice_id"], links)
        party = invoices.get(target, inv)["customer_id"]
        if party != inv["customer_id"]:
            raise ValueError("Hóa đơn thay thế không được tự chuyển khoản thu đã ghi nhận sang khách khác; cần đối chiếu và phân bổ lại")
        bank_id = row.get("bank_id")
        if bank_id:
            txn = bank.get(bank_id)
            if (
                not txn
                or txn["direction"] != "in"
                or txn.get("component") == "cash_sale"
                or txn.get("cash_flow_class") in NON_AR
                or row["payment_date"] != txn["date"]
                or row["known_at"] < txn["known_at"]
            ):
                raise ValueError(
                    "Sai tham chiếu, ngày hoặc chiều dòng sao kê: " + bank_id
                )
            if txn.get("customer_id") not in (None, "", party) or bank_parties.get(bank_id, party) != party:
                raise ValueError("Một dòng sao kê không được phân bổ chéo khách hàng: " + bank_id)
            bank_parties[bank_id] = party
            allocations[bank_id] = allocations.get(bank_id, 0) + vnd(row["amount"])
            if allocations[bank_id] > vnd(txn["amount"]):
                raise ValueError("Phân bổ vượt số tiền đã nhận: " + bank_id)
        if row["payment_date"] < inv["issue_date"]:
            raise ValueError("Thanh toán trước ngày lập hóa đơn: " + row["payment_id"])
        paid[target] = paid.get(target, 0) + vnd(row["amount"])
        if paid[target] > effective.get(target, vnd(inv["amount"])):
            raise ValueError("Tổng thu vượt giá trị hóa đơn: " + row["invoice_id"])
    from .obligations import validate_obligations
    validate_obligations(data)
    periods = {}
    for s in sorted(data.get("statements", []), key=lambda r: r["start_date"]):
        prev = periods.get(s["account"])
        if prev and prev["end_date"] >= s["start_date"]:
            raise ValueError("Kỳ sao kê cùng tài khoản chồng lấn")
        if (
            prev
            and pd.Timestamp(prev["end_date"]) + pd.Timedelta(days=1)
            == pd.Timestamp(s["start_date"])
            and vnd(prev["closing_balance"]) != vnd(s["opening_balance"])
        ):
            raise ValueError("Số dư đầu kỳ không nối với kỳ trước")
        periods[s["account"]] = s
        lines = [
            r
            for r in bank.values()
            if r["account"] == s["account"]
            and s["start_date"] <= r["date"] <= s["end_date"]
        ]
        if any(r["known_at"] > s["known_at"] for r in lines):
            raise ValueError(
                "Có giao dịch ghi nhận sau ngày xác nhận kỳ; cập nhật kỳ sao kê: "
                + s["statement_id"]
            )
        movement = sum(
            vnd(r["amount"]) * (1 if r["direction"] == "in" else -1) for r in lines
        )
        if vnd(s["opening_balance"]) + movement != vnd(s["closing_balance"]):
            raise ValueError("Chênh lệch số dư sao kê: " + s["statement_id"])


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def observed(data, clock):
    """Only payments posted/available by clock can settle an invoice or enter features."""
    date = pd.Timestamp(clock)
    if not data.get("invoices") and not data.get("record_history", {}).get("invoices"):
        raise ValueError("Chưa có hóa đơn")
    data = as_of(data, clock)
    invoices = invoice_view(data, clock)
    for c in ["issue_date", "due_date", "known_at"]:
        invoices[c] = pd.to_datetime(invoices[c])
    invoices = invoices[
        (invoices.issue_date <= date) & (invoices.known_at <= date)
    ].copy()
    totals = {}
    settled = {}
    known = {}
    settled_known = {}
    amounts = invoices.set_index("invoice_id").amount.to_dict()
    effect_dates = (
        invoices.set_index("invoice_id")
        .get("balance_effective_date", pd.Series(dtype=object))
        .to_dict()
    )
    invoice_known = invoices.set_index("invoice_id").known_at.to_dict()
    links = _payment_links(
        [
            r
            for r in data.get("invoices", [])
            if r["issue_date"] <= str(date.date()) and r["known_at"] <= str(date.date())
        ]
    )
    payments = sorted(
        data.get("payments", []), key=lambda r: (r["payment_date"], r["payment_id"])
    )
    for r in payments:
        iid = payment_target(r["invoice_id"], links)
        if (
            pd.Timestamp(r["payment_date"]) > date
            or pd.Timestamp(r["known_at"]) > date
            or iid not in amounts
        ):
            continue
        totals[iid] = totals.get(iid, 0) + vnd(r["amount"])
        known[iid] = max(
            known.get(iid, pd.Timestamp(r["known_at"])), pd.Timestamp(r["known_at"])
        )
        if totals[iid] >= amounts[iid]:
            settled.setdefault(
                iid,
                max(
                    pd.Timestamp(r["payment_date"]),
                    pd.Timestamp(effect_dates.get(iid, r["payment_date"])),
                ),
            )
            settled_known.setdefault(iid, max(known[iid], invoice_known[iid]))
    invoices["settled"] = pd.to_datetime(invoices.invoice_id.map(settled))
    invoices["settled_known_at"] = pd.to_datetime(
        invoices.invoice_id.map(settled_known)
    )
    invoices["received"] = [totals.get(iid, 0) for iid in invoices.invoice_id]
    invoices["remaining_amount"] = (invoices.amount - invoices.received).clip(lower=0)
    stops = {}
    for e in data.get("actions", []):
        if (
            e["kind"] == "write_off"
            and pd.Timestamp(e["known_at"]) <= date
            and pd.Timestamp(e["date"]) <= date
        ):
            target = payment_target(e["invoice_id"], links)
            stops[target] = min(stops.get(target, date), pd.Timestamp(e["date"]))
    invoices["written_off_at"] = pd.to_datetime(invoices.invoice_id.map(stops))
    return invoices
