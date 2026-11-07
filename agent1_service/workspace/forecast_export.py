"""Excel export of a saved forecast, including plans from older releases."""

from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


DATE_FIELDS = {"date", "due_date", "promised_date", "cutoff"}
PERCENT_FIELDS = {
    "below_floor_probability",
    "payment_probability_4w",
    "promise_reliability",
    "write_off_probability_365d_at_issue",
}
OUTFLOW_LABELS = {
    "scheduled": "Có lịch",
    "confirmed_zero": "Đã xác nhận 0",
    "unknown": "Chưa biết",
}


def _value(field, value):
    if field in DATE_FIELDS and value:
        return date.fromisoformat(value)
    if field == "outflow_status":
        return OUTFLOW_LABELS.get(value, value)
    if isinstance(value, bool):
        return "Có" if value else "Không"
    return value


def _write_table(sheet, columns, rows):
    sheet.append([label for _, label in columns])
    for row in rows:
        sheet.append([_value(field, row.get(field)) for field, _ in columns])
        for cell, (field, _) in zip(sheet[sheet.max_row], columns):
            if isinstance(cell.value, str):
                # Customer identifiers and notes are data, including strings starting with '='.
                cell.data_type = "s"
            elif isinstance(cell.value, date):
                cell.number_format = "dd-mm-yy"
            elif isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%" if field in PERCENT_FIELDS else "#,##0.##"
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="264A42")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for index, column in enumerate(sheet.columns, 1):
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[get_column_letter(index)].width = max(
            14, min(44, width + 3)
        )


def workbook_bytes(plan, company):
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Kết quả dự báo"
    scenario = plan.get("scenario") or {}
    details = [
        ("Doanh nghiệp", company),
        ("Ngày dự báo", _value("cutoff", plan["cutoff"])),
        ("Số tuần", len(plan["weeks"])),
        ("Số dư đầu kỳ (VND)", plan.get("opening_balance")),
        ("Số dư thấp nhất (VND)", plan.get("minimum_balance")),
        ("Ngưỡng tiền tối thiểu (VND)", plan.get("cash_floor")),
        ("Công nợ đang mở (VND)", plan.get("outstanding")),
        (
            "Số tuần ước lượng hoạt động",
            plan.get("operating_weeks", 13 if plan.get("operating_included") else 0),
        ),
        ("Số ngày thu chậm thêm", scenario.get("delay_days", 0)),
        ("Phạm vi thu chậm", scenario.get("delay_customer") or "Mọi khách"),
        ("Hệ số chi", scenario.get("expense_multiplier", 1)),
        ("Rủi ro chung theo khách", bool(scenario.get("shared_customer_risk"))),
        ("Thời gian tính (ms)", plan.get("inference_ms")),
        ("Phiên bản", plan.get("model_version") or "Theo lịch sử"),
        ("Mã kế hoạch", plan.get("id")),
    ]
    details.extend(
        ("Phạm vi và giả định", note) for note in plan.get("assumptions", [])
    )
    _write_table(
        summary,
        [("label", "Chỉ tiêu"), ("value", "Kết quả")],
        ({"label": label, "value": value} for label, value in details),
    )
    summary.column_dimensions["B"].width = 86
    for row in summary.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
        if len(str(row[1].value or "")) > 85:
            summary.row_dimensions[row[1].row].height = 36
    _write_table(
        workbook.create_sheet("Kế hoạch từng tuần"),
        [
            ("week", "Tuần"),
            ("date", "Đến ngày"),
            ("cash_in", "Dự thu (VND)"),
            ("new_credit_in", "Thu từ bán chịu mới (VND)"),
            ("cash_out", "Dự chi (VND)"),
            ("balance", "Số dư (VND)"),
            ("low", "P10 (VND)"),
            ("high", "P90 (VND)"),
            ("outflow_status", "Lịch chi"),
            ("below_floor_probability", "Xác suất dưới ngưỡng"),
        ],
        plan["weeks"],
    )
    _write_table(
        workbook.create_sheet("Khoản cần chú ý"),
        [
            ("invoice_id", "Hóa đơn"),
            ("customer_id", "Khách hàng"),
            ("outstanding", "Còn phải thu (VND)"),
            ("overdue_days", "Ngày quá hạn"),
            ("due_date", "Hạn trả"),
            ("promised_date", "Ngày hứa trả"),
            ("promise_reliability", "Độ tin cậy lời hứa"),
            ("disputed", "Tranh chấp"),
            ("payment_probability_4w", "Xác suất tất toán 4 tuần"),
            (
                "write_off_probability_365d_at_issue",
                "Rủi ro xóa nợ 365 ngày lúc phát hành",
            ),
            ("reason", "Lý do"),
        ],
        plan.get("collections", []),
    )
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
