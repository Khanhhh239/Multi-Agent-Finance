"""Friendly canonical input contracts and explicit observation clocks."""

import hashlib
import json
import math
import re
from datetime import datetime, date as calendar_date
import pandas as pd
from unidecode import unidecode

SCHEMAS = {
    "invoices": {
        "invoice_id": ["ma hoa don", "so hoa don"],
        "customer_id": ["ma khach hang", "khach hang"],
        "issue_date": ["ngay lap", "ngay hoa don"],
        "due_date": ["han thanh toan", "ngay den han"],
        "amount": ["so tien", "tong thanh toan", "amount_gross"],
        "known_at": ["ngay ghi nhan"],
        "currency": ["tien te"],
    },
    "payments": {
        "payment_id": ["ma thanh toan", "ma giao dich", "txn_id"],
        "invoice_id": ["ma hoa don", "so hoa don"],
        "payment_date": ["ngay thanh toan", "ngay tien ve", "value_date"],
        "amount": ["so tien"],
        "known_at": ["ngay ghi nhan"],
    },
    "outflows": {
        "expense_id": ["ma khoan chi"],
        "date": ["ngay chi"],
        "amount": ["so tien"],
        "category": ["loai chi"],
        "known_at": ["ngay ghi nhan"],
    },
}
REQUIRED = {k: set(v) - {"known_at", "currency"} for k, v in SCHEMAS.items()}
REQUIRED["outflows"].add("known_at")
IDS = {"invoices": "invoice_id", "payments": "payment_id", "outflows": "expense_id"}
SCHEMAS["payments"]["bank_id"] = ["ma dong sao ke"]
SCHEMAS["bank"] = {
    "bank_id": ["ma dong sao ke"],
    "account": ["tai khoan"],
    "date": ["ngay giao dich"],
    "direction": ["thu chi"],
    "amount": ["so tien"],
    "known_at": ["ngay ghi nhan"],
}
SCHEMAS["statements"] = {
    "statement_id": ["ma ky sao ke"],
    "account": ["tai khoan"],
    "start_date": ["tu ngay"],
    "end_date": ["den ngay"],
    "opening_balance": ["so du dau ky"],
    "closing_balance": ["so du cuoi ky"],
    "known_at": ["ngay ghi nhan"],
}
IDS.update(bank="bank_id", statements="statement_id")
for kind in ("bank", "statements"):
    REQUIRED[kind] = set(SCHEMAS[kind]) - {"known_at"}
SCHEMAS["bank"]["component"] = ["nhom du bao"]
SCHEMAS["actions"] = {
    "event_id": ["ma su kien"],
    "invoice_id": ["ma hoa don"],
    "date": ["ngay su kien"],
    "kind": ["hanh dong"],
    "promise_date": ["ngay hua tra"],
    "known_at": ["ngay ghi nhan"],
}
IDS["actions"] = "event_id"
REQUIRED["actions"] = {"event_id", "invoice_id", "date", "kind"}


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


def parse_rows(raw, kind, mapping, date_format="%d/%m/%Y", number_format="vi-VN"):
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
    if not mapping.get("known_at"):
        warnings.append(
            "Thiếu ngày ghi nhận: giả định dữ liệu được biết từ ngày nghiệp vụ. Kiểm định lịch sử dựa trên giả định này."
        )
    for index, source in raw.iterrows():
        row = {}
        bad = False
        for field in SCHEMAS[kind]:
            col = mapping.get(field)
            value = source.get(col) if col else None
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
                if field in ("amount", "opening_balance", "closing_balance"):
                    if isinstance(value, str):
                        value = value.strip().replace(" ", "")
                        pattern = (
                            r"(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?"
                            if number_format == "vi-VN"
                            else r"\d+(?:\.\d+)?"
                        )
                        if field != "amount":
                            pattern = "-?" + pattern
                        if not re.fullmatch(pattern, value):
                            raise ValueError()
                        if number_format == "vi-VN":
                            value = value.replace(".", "").replace(",", ".")
                    value = float(value)
                    if not math.isfinite(value) or (field == "amount" and value <= 0):
                        raise ValueError()
                elif field.endswith("date") or field in ["date", "known_at"]:
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
            "issue_date", row.get("payment_date", row.get("date", row.get("end_date")))
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
        row.setdefault("known_at", date)
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
            if row["currency"] != "VND":
                errors.append(
                    dict(
                        row=int(index) + 2,
                        column="currency",
                        message="Luồng này chỉ nhận VND; không tự quy đổi ngoại tệ",
                    )
                )
                continue
            if row["due_date"] < row["issue_date"]:
                errors.append(
                    dict(
                        row=int(index) + 2,
                        column="due_date",
                        message="Hạn trả trước ngày lập",
                    )
                )
                continue
        records.append(row)
    return records, errors, warnings


def validate_dataset(data):
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
    for row in data.get("payments", []):
        bank_id = row.get("bank_id")
        if bank_id:
            txn = bank.get(bank_id)
            if (
                not txn
                or txn["direction"] != "in"
                or txn.get("component") == "cash_sale"
                or row["payment_date"] != txn["date"]
                or row["known_at"] < txn["known_at"]
            ):
                raise ValueError(
                    "Sai tham chiếu, ngày hoặc chiều dòng sao kê: " + bank_id
                )
            allocations[bank_id] = allocations.get(bank_id, 0) + row["amount"]
            if allocations[bank_id] > txn["amount"] + 0.01:
                raise ValueError("Phân bổ vượt số tiền đã nhận: " + bank_id)
        if row["invoice_id"] not in invoices:
            raise ValueError(
                "Thanh toán tham chiếu hóa đơn chưa có: " + row["invoice_id"]
            )
        inv = invoices[row["invoice_id"]]
        if row["payment_date"] < inv["issue_date"]:
            raise ValueError("Thanh toán trước ngày lập hóa đơn: " + row["payment_id"])
        paid[row["invoice_id"]] = paid.get(row["invoice_id"], 0) + row["amount"]
        if paid[row["invoice_id"]] > inv["amount"] + 0.01:
            raise ValueError("Tổng thu vượt giá trị hóa đơn: " + row["invoice_id"])
    periods = {}
    for s in sorted(data.get("statements", []), key=lambda r: r["start_date"]):
        prev = periods.get(s["account"])
        if prev and prev["end_date"] >= s["start_date"]:
            raise ValueError("Kỳ sao kê cùng tài khoản chồng lấn")
        if (
            prev
            and pd.Timestamp(prev["end_date"]) + pd.Timedelta(days=1)
            == pd.Timestamp(s["start_date"])
            and abs(prev["closing_balance"] - s["opening_balance"]) > 0.01
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
            r["amount"] * (1 if r["direction"] == "in" else -1) for r in lines
        )
        if abs(s["opening_balance"] + movement - s["closing_balance"]) > 0.01:
            raise ValueError("Chênh lệch số dư sao kê: " + s["statement_id"])


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def observed(data, clock):
    """Only payments posted/available by clock can settle an invoice or enter features."""
    date = pd.Timestamp(clock)
    invoices = pd.DataFrame(data.get("invoices", []))
    if invoices.empty:
        raise ValueError("Chưa có hóa đơn")
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
    payments = sorted(
        data.get("payments", []), key=lambda r: (r["payment_date"], r["payment_id"])
    )
    for r in payments:
        if (
            pd.Timestamp(r["payment_date"]) > date
            or pd.Timestamp(r["known_at"]) > date
            or r["invoice_id"] not in amounts
        ):
            continue
        iid = r["invoice_id"]
        totals[iid] = totals.get(iid, 0) + r["amount"]
        known[iid] = max(
            known.get(iid, pd.Timestamp(r["known_at"])), pd.Timestamp(r["known_at"])
        )
        if totals[iid] >= amounts[iid] - 0.01:
            settled.setdefault(iid, pd.Timestamp(r["payment_date"]))
            settled_known.setdefault(iid, known[iid])
    invoices["settled"] = pd.to_datetime(invoices.invoice_id.map(settled))
    invoices["settled_known_at"] = pd.to_datetime(
        invoices.invoice_id.map(settled_known)
    )
    invoices["received"] = invoices.invoice_id.map(totals).fillna(0.0)
    invoices["remaining_amount"] = (invoices.amount - invoices.received).clip(lower=0)
    stops = {}
    for e in data.get("actions", []):
        if (
            e["kind"] == "write_off"
            and pd.Timestamp(e["known_at"]) <= date
            and pd.Timestamp(e["date"]) <= date
        ):
            stops[e["invoice_id"]] = min(
                stops.get(e["invoice_id"], date), pd.Timestamp(e["date"])
            )
    invoices["written_off_at"] = pd.to_datetime(invoices.invoice_id.map(stops))
    return invoices
