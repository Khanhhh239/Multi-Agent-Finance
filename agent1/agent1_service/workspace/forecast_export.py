"""Excel export of a saved forecast, including plans from older releases."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from agent1.adaptive.obligations import obligation_amounts

DATE_FIELDS = {"date", "due_date", "promised_date", "cutoff", "known_at", "forecast_date", "payment_date"}
PERCENT_FIELDS = {
    "below_floor_probability",
    "payment_probability_4w",
    "triage_probability_4w",
    "promise_reliability",
    "write_off_probability_365d_at_issue",
}
OUTFLOW_LABELS = {
    "scheduled": "Đã xác nhận đủ lịch",
    "scheduled_unconfirmed": "Có khoản chi, chưa xác nhận đủ",
    "confirmed_zero": "Đã xác nhận 0",
    "unknown": "Chưa biết",
}


def _value(field, value, score_unit=None):
    if (
        field == "outstanding"
        or field == "priority_score"
        and score_unit != "probability"
    ) and value is not None:
        number = Decimal(str(value))
        # Excel retains at most 15 significant digits in a numeric cell.
        # Keep large amounts/scores as decimal text, including fractional scores.
        if len(number.as_tuple().digits) > 15:
            return str(value)
        return int(number) if number == number.to_integral_value() else float(number)
    if field == "priority_score_unit":
        return {"probability": "Xác suất", "VND": "VND"}.get(value, value)
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
        sheet.append(
            [
                _value(field, row.get(field), row.get("priority_score_unit"))
                for field, _ in columns
            ]
        )
        for cell, (field, _) in zip(sheet[sheet.max_row], columns):
            if isinstance(cell.value, str):
                # Customer identifiers and notes are data, including strings starting with '='.
                cell.data_type = "s"
            elif isinstance(cell.value, date):
                cell.number_format = "dd-mm-yy"
            elif isinstance(cell.value, (int, float)):
                cell.number_format = (
                    "0.0%"
                    if field in PERCENT_FIELDS
                    or (
                        field == "priority_score"
                        and row.get("priority_score_unit") == "probability"
                    )
                    else "#,##0.##"
                )
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
        ("Số dư kỳ vọng thấp nhất (VND)", plan.get("minimum_balance")),
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
    ranking = plan.get("collection_ranking")
    if ranking:
        details.extend(
            [
                ("Chính sách ưu tiên thu nợ", ranking["label"]),
                ("Công thức điểm ưu tiên", ranking["formula"]),
                ("Quy tắc xếp hạng", "Điểm giảm dần; cùng điểm giữ thứ tự snapshot."),
            ]
        )
    decomposition = plan.get("cash_decomposition")
    if decomposition:
        details.extend(
            [
                ("Dự thu công nợ mở (VND)", decomposition["totals"]["ar_in"]),
                ("Dự thu bán ngay (VND)", decomposition["totals"]["cash_sale_in"]),
                ("Dự thu bán chịu mới (VND)", decomposition["totals"]["new_credit_in"]),
                ("Dự thu hoàn theo hồ sơ T5 (VND)", decomposition["totals"].get("obligation_in", 0)),
                ("Chi đã có lịch (VND)", decomposition["totals"]["scheduled_out"]),
                (
                    "Chi biến đổi bổ sung (VND)",
                    decomposition["totals"]["variable_cost_topup"],
                ),
                ("Số dư cuối kỳ (VND)", decomposition["totals"]["closing_balance"]),
            ]
        )
        details.extend(
            ("Giới hạn phân rã tiền", note) for note in decomposition["assumptions"]
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
            summary.row_dimensions[row[1].row].height = min(
                120, 18 * ((len(str(row[1].value)) + 84) // 85)
            )
    _write_table(
        workbook.create_sheet("Kế hoạch từng tuần"),
        [
            ("week", "Tuần"),
            ("date", "Đến ngày"),
            ("cash_in", "Dự thu (VND)"),
            ("new_credit_in", "Thu từ bán chịu mới (VND)"),
            ("cash_out", "Dự chi (VND)"),
            ("balance", "Số dư kỳ vọng (VND)"),
            ("median_balance", "Trung vị số dư · P50 (VND)"),
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
            ("collection_rank", "Thứ tự ưu tiên"),
            ("priority_score", "Điểm ưu tiên"),
            ("priority_score_unit", "Đơn vị điểm"),
            ("priority_policy_label", "Chính sách ưu tiên"),
            ("triage_probability_4w", "Xác suất lịch sử khách 4 tuần"),
            ("ranking_probability_source", "Nguồn ước lượng xếp hạng"),
        ],
        (
            {
                **row,
                "priority_policy_label": row.get("ranking_explanation", {}).get(
                    "label"
                ),
                "ranking_probability_source": row.get("ranking_explanation", {})
                .get("probability_source", {})
                .get("label"),
            }
            for row in plan.get("collections", [])
        ),
    )
    if decomposition:
        _cash_sheets(workbook, decomposition)
    if plan.get("t10"):
        _t10_sheets(workbook, plan)
    if plan.get('t5'):
        _write_table(workbook.create_sheet('Nghĩa vụ T5'), [
            ('expense_id', 'Mã nghĩa vụ'), ('due_date', 'Ngày đến hạn'),
            ('obligation_ref', 'Hợp đồng/khoản cố định'), ('payment_period', 'Kỳ thanh toán'),
            ('installment_no', 'Đợt đến hạn'),
            ('category', 'Loại'), ('direction', 'Chiều tiền'), ('status', 'Trạng thái'),
            ('obligation_amount', 'Số tiền nghĩa vụ'), ('settled_amount', 'Đã thanh toán'),
            ('cancelled_amount', 'Đã hủy'), ('replaced_amount', 'Đã thay thế'),
            ('remaining_amount', 'Còn phải trả/nhận'), ('forecast_date', 'Ngày dự kiến còn lại'),
            ('known_at', 'Ngày ghi nhận'), ('source', 'Nguồn hồ sơ'),
        ], (dict(r, **obligation_amounts(r)) for r in plan['t5']['obligations']))
        _write_table(workbook.create_sheet('Thanh toán T5'), [
            ('settlement_id', 'Mã thanh toán'), ('expense_id', 'Mã nghĩa vụ'),
            ('bank_id', 'Mã dòng sao kê'), ('payment_date', 'Ngày thanh toán'),
            ('amount', 'Số tiền'), ('known_at', 'Ngày ghi nhận'),
        ], plan['t5']['payments'])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _cash_sheets(workbook, decomposition):
    _write_table(
        workbook.create_sheet("Phân rã từng tuần"),
        [
            ("week", "Tuần"),
            ("date", "Đến ngày"),
            ("opening_balance", "Số dư đầu tuần"),
            ("ar_in", "Thu công nợ mở"),
            ("cash_sale_in", "Thu bán ngay"),
            ("new_credit_in", "Thu bán chịu mới"),
            ("scheduled_out", "Chi đã có lịch"),
            ("variable_cost_topup", "Chi biến đổi bổ sung"),
            ("net_change", "Thay đổi số dư"),
            ("balance", "Số dư cuối tuần"),
            ("headroom", "Số dư trừ ngưỡng"),
            ("outflow_status", "Phạm vi lịch chi"),
            ("obligation_in", "Thu hoàn theo hồ sơ T5"),
        ],
        decomposition["weeks"],
    )
    weekly_columns = [
        (f"receipt_week_{w['week']}", f"Dự thu tuần {w['week']} (VND)")
        for w in decomposition["weeks"]
    ]
    for key, title, identifiers in (
        (
            "invoices",
            "Thu theo hóa đơn",
            [("invoice_id", "Hóa đơn"), ("customer_id", "Khách hàng")],
        ),
        (
            "customers",
            "Thu theo khách",
            [("customer_id", "Khách hàng"), ("invoice_count", "Số hóa đơn")],
        ),
    ):
        _write_table(
            workbook.create_sheet(title),
            identifiers
            + [
                ("outstanding", "Dư nợ tại ngày chốt"),
                ("expected_in", "Dự thu trong kỳ"),
                ("expected_after_horizon", "Chưa dự thu trong kỳ"),
            ]
            + weekly_columns,
            (
                {
                    **row,
                    **{
                        f"receipt_week_{i + 1}": amount
                        for i, amount in enumerate(row["expected_by_week"])
                    },
                }
                for row in decomposition[key]
            ),
        )
    _write_table(
        workbook.create_sheet("Lịch chi đã biết"),
        [
            ("expense_id", "Mã khoản chi"),
            ("date", "Ngày chi"),
            ("known_at", "Ngày ghi nhận"),
            ("week", "Tuần"),
            ("category", "Loại chi"),
            ("original_amount", "Số tiền gốc"),
            ("amount", "Số tiền sau kịch bản"),
        ],
        decomposition["outflows"],
    )
    if decomposition.get('inflows'):
        _write_table(workbook.create_sheet('Hoàn thuế theo lịch'), [
            ('expense_id', 'Mã nghĩa vụ'), ('date', 'Ngày dự kiến nhận'),
            ('known_at', 'Ngày được biết'), ('original_amount', 'Số còn được nhận'),
            ('amount', 'Dự thu'), ('source', 'Nguồn quyết định'),
        ], decomposition['inflows'])


def _t10_sheets(workbook, plan):
    t10 = plan["t10"]
    _write_table(workbook.create_sheet("Bằng chứng partial theo tuần"), [
        ("invoice_id", "Hóa đơn"), ("customer_id", "Khách hàng"), ("week", "Tuần"),
        ("expected_opening_debt", "Dư nợ đầu kỳ vọng"),
        ("settlement_probability", "P tất toán tuần"), ("settlement_hazard", "Hazard tất toán"),
        ("expected_from_settlement", "Thu từ tất toán"), ("expected_from_partial", "Thu từ partial"),
        ("expected_receipt", "Tổng dự thu"), ("expected_remaining_debt", "Dư nợ cuối kỳ vọng"),
    ], (dict(w, invoice_id=r["invoice_id"], customer_id=r["customer_id"])
        for r in plan["cash_decomposition"]["invoices"] for w in r["receipt_explanation"]["weeks"]))
    p = t10["partial_profile"]
    support = p.get("evidence", {}).get("cells", [])
    _write_table(workbook.create_sheet("Profile partial và hỗ trợ"), [
        ("cell", "Ô profile"), ("q", "q khi chưa tất toán"), ("mean_ratio", "Tỷ lệ trả trung bình"),
        ("weeks", "Tuần học"), ("effective_weeks", "Tuần hiệu dụng"), ("partial_weeks", "Tuần partial"),
        ("ratio", "Tỷ lệ trả"), ("weight", "Trọng số tỷ lệ"),
    ], (dict(cell=c, q=q, mean_ratio=p["mean_ratios"][c],
             **(support[c] if c < len(support) else {}), ratio=r, weight=p["weights"][c][j])
        for c, q in enumerate(p["probability"]) for j, r in enumerate(p["ratios"][c])))
    _write_table(workbook.create_sheet("Phiên bản T10"), [("key", "Trường"), ("value", "Giá trị")], [
        *[dict(key=k, value=v if isinstance(v, str) else str(v)) for k, v in t10["identity"].items()],
        dict(key="snapshot_sha256", value=t10.get("replay", {}).get("snapshot_sha256")),
        dict(key="partial_prior_sha256", value=p.get("evidence", {}).get("prior_sha256")),
        dict(key="partial_prior_strength", value=p.get("evidence", {}).get("prior_strength")),
        *[dict(key="Giả định/giới hạn", value=note) for note in t10["assumptions"]],
    ])
