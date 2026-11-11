"""Accounting decomposition of the served expected cash path, not of its quantiles."""

import numpy as np

PROTOCOL = "cash-decomposition-v1"


def _check(actual, expected, label):
    if not np.allclose(actual, expected, rtol=1e-12, atol=1e-6):
        raise ValueError(f"Phân rã dòng tiền không khớp {label}.")


def _timing_comparison(ar, cash_sales, new_credit, outgoing, opening, floor, weeks):
    """Shift finite forecast receipts only; the unresolved tail has no known date."""
    horizon = len(ar)
    current_balance = opening + np.cumsum(ar + new_credit + cash_sales - outgoing)
    scenarios = []
    for key, label, shift in (
        ("current", "Kế hoạch đang xem", 0),
        ("early", "Thu sớm 2 tuần", -2),
        ("late", "Thu chậm 2 tuần", 2),
    ):
        shifted = np.zeros(horizon)
        pushed_out = 0.0
        for i, amount in enumerate(ar):
            target = max(0, i + shift)
            if target < horizon:
                shifted[target] += amount
            else:
                pushed_out += amount
        cin = shifted + new_credit + cash_sales
        balances = opening + np.cumsum(cin - outgoing)
        shortfalls = np.flatnonzero(balances < floor)
        scenarios.append(
            {
                "key": key,
                "label": label,
                "shift_weeks": shift,
                "ar_in": float(shifted.sum()),
                "cash_in": float(cin.sum()),
                "cash_out": float(outgoing.sum()),
                "receipts_pushed_beyond_horizon": float(pushed_out),
                "minimum_balance": float(balances.min()),
                "closing_balance": float(balances[-1]),
                "first_below_floor_week": int(shortfalls[0] + 1)
                if len(shortfalls)
                else None,
                "minimum_balance_change": float(balances.min() - current_balance.min()),
                "closing_balance_change": float(balances[-1] - current_balance[-1]),
                "weeks": [
                    {
                        "week": w["week"],
                        "date": w["date"],
                        "ar_in": float(shifted[i]),
                        "cash_in": float(cin[i]),
                        "cash_out": float(outgoing[i]),
                        "balance": float(balances[i]),
                        "balance_change": float(balances[i] - current_balance[i]),
                    }
                    for i, w in enumerate(weeks)
                ],
            }
        )
    return {
        "target": "expected_balance",
        "relative_to": "saved_plan",
        "scenarios": scenarios,
        "assumptions": [
            "So với kế hoạch đang xem: dịch phần dự thu công nợ trong kỳ sớm/chậm 2 tuần cho mọi khách; thu sớm nhất vào tuần 1.",
            "Giữ nguyên số dư đầu, lịch chi, thu bán ngay và thu bán chịu mới. Nếu đang xem một kịch bản, so sánh được tính tiếp từ kịch bản đó.",
            "Không kéo phần dư nợ chưa có thời điểm thu trong kỳ vào kịch bản sớm. Thu chậm ra ngoài kỳ được ghi riêng, không coi là mất tiền.",
            "Đây là độ nhạy số dư kỳ vọng, chưa mô phỏng lại xác suất thiếu tiền hay P10/P90 và chưa chứng minh tác động của biện pháp thu nợ.",
        ],
    }


def explain_cash(
    opened,
    receipt_amounts,
    weeks,
    *,
    cutoff,
    opening_balance,
    cash_floor,
    scheduled_outflows,
    cash_sales,
    new_credit,
    variable_cost_topup,
    partial_profile,
    partial_supported,
    written_off_count,
    model_asof=None,
):
    horizon = len(weeks)
    amounts = opened.remaining_amount.to_numpy(float)
    ar = receipt_amounts.sum(axis=0)
    scheduled = np.zeros(horizon)
    for row in scheduled_outflows:
        scheduled[row["week"] - 1] += row["amount"]
    # Preserve serving's addition order, including at large VND magnitudes.
    incoming = ar + new_credit + cash_sales
    outgoing = scheduled + variable_cost_topup
    balances = opening_balance + np.cumsum(incoming - outgoing)
    _check(incoming, [w["cash_in"] for w in weeks], "dự thu")
    _check(outgoing, [w["cash_out"] for w in weeks], "dự chi")
    _check(balances, [w["balance"] for w in weeks], "số dư")
    if np.any(receipt_amounts < -1e-6) or np.any(
        receipt_amounts.sum(1) > amounts + 1e-6 + amounts * 1e-12
    ):
        raise ValueError("Dự thu hóa đơn vượt phần công nợ đang mở.")
    invoices = []
    customers = {}
    for i, row in enumerate(opened.itertuples()):
        total = float(receipt_amounts[i].sum())
        invoices.append(
            {
                "invoice_id": str(row.invoice_id),
                "customer_id": str(row.customer_id),
                "due_date": str(row.due_date.date()),
                "outstanding": float(amounts[i]),
                "received_before_cutoff": float(row.received),
                "expected_in": total,
                "expected_after_horizon": max(0.0, float(amounts[i] - total)),
                "expected_by_week": receipt_amounts[i].tolist(),
                "receipt_basis": "observed_partial_profile"
                if partial_profile[i]
                else "settlement_timing",
            }
        )
        customer = customers.setdefault(
            str(row.customer_id),
            {
                "customer_id": str(row.customer_id),
                "invoice_count": 0,
                "outstanding": 0.0,
                "expected_in": 0.0,
                "expected_after_horizon": 0.0,
                "expected_by_week": np.zeros(horizon),
            },
        )
        customer["invoice_count"] += 1
        customer["outstanding"] += float(amounts[i])
        customer["expected_in"] += total
        customer["expected_after_horizon"] += max(0.0, float(amounts[i] - total))
        customer["expected_by_week"] += receipt_amounts[i]
    for customer in customers.values():
        customer["expected_by_week"] = customer["expected_by_week"].tolist()
    bridge = [
        {
            "week": w["week"],
            "date": w["date"],
            "opening_balance": float(opening_balance if i == 0 else balances[i - 1]),
            "ar_in": float(ar[i]),
            "cash_sale_in": float(cash_sales[i]),
            "new_credit_in": float(new_credit[i]),
            "cash_in": float(incoming[i]),
            "scheduled_out": float(scheduled[i]),
            "variable_cost_topup": float(variable_cost_topup[i]),
            "cash_out": float(outgoing[i]),
            "net_change": float(incoming[i] - outgoing[i]),
            "balance": float(balances[i]),
            "headroom": float(balances[i] - cash_floor),
            "outflow_status": w["outflow_status"],
        }
        for i, w in enumerate(weeks)
    ]
    expected_shortfalls = np.flatnonzero(balances < cash_floor)
    simulated_alerts = [
        i for i, w in enumerate(weeks) if w["below_floor_probability"] >= 0.25
    ]
    focus_index = (
        min(list(expected_shortfalls) + simulated_alerts)
        if len(expected_shortfalls) or simulated_alerts
        else int(np.argmin(balances))
    )
    focus = bridge[focus_index]
    cumulative_in, cumulative_out = (
        float(incoming[: focus_index + 1].sum()),
        float(outgoing[: focus_index + 1].sum()),
    )
    focus_customers = sorted(
        (
            {
                "customer_id": r["customer_id"],
                "unreceived": float(
                    r["outstanding"] - sum(r["expected_by_week"][: focus_index + 1])
                ),
                "expected_in": float(sum(r["expected_by_week"][: focus_index + 1])),
            }
            for r in customers.values()
        ),
        key=lambda r: (-r["unreceived"], r["customer_id"]),
    )
    return {
        "protocol": PROTOCOL,
        "target": "expected_balance",
        "units": "VND",
        "cutoff": cutoff,
        "model_asof": model_asof,
        "model_version": None,
        "dataset_hash": None,
        "scope": {
            "open_invoices": len(opened),
            "customers": len(customers),
            "written_off_count": written_off_count,
            "partial_cash_supported": partial_supported,
            "description": "Toàn bộ công nợ đang mở sau loại xóa nợ; gồm cả khoản vừa liên hệ/tạm bỏ qua, không giới hạn 30 khoản ưu tiên.",
        },
        "totals": {
            "opening_balance": float(opening_balance),
            "ar_in": float(ar.sum()),
            "cash_sale_in": float(cash_sales.sum()),
            "new_credit_in": float(new_credit.sum()),
            "cash_in": float(incoming.sum()),
            "scheduled_out": float(scheduled.sum()),
            "variable_cost_topup": float(variable_cost_topup.sum()),
            "cash_out": float(outgoing.sum()),
            "net_change": float(incoming.sum() - outgoing.sum()),
            "closing_balance": float(balances[-1]),
            "expected_after_horizon": max(0.0, float(amounts.sum() - ar.sum())),
        },
        "invoices": sorted(
            invoices, key=lambda r: (-r["expected_in"], r["invoice_id"])
        ),
        "customers": sorted(
            customers.values(), key=lambda r: (-r["expected_in"], r["customer_id"])
        ),
        "outflows": sorted(
            scheduled_outflows, key=lambda r: (r["date"], r["expense_id"])
        ),
        "weeks": bridge,
        "risk_focus": {
            "week": focus["week"],
            "date": focus["date"],
            "balance": focus["balance"],
            "cash_floor": float(cash_floor),
            "trigger": "expected_shortfall"
            if focus["balance"] < cash_floor
            else "simulation_only"
            if focus_index in simulated_alerts
            else "minimum_expected_balance",
            "first_expected_shortfall_week": int(expected_shortfalls[0] + 1)
            if len(expected_shortfalls)
            else None,
            "first_simulated_alert_week": simulated_alerts[0] + 1
            if simulated_alerts
            else None,
            "expected_shortfall": max(0.0, float(cash_floor - focus["balance"])),
            "opening_balance": float(opening_balance),
            "cumulative_cash_in": cumulative_in,
            "cumulative_cash_out": cumulative_out,
            "headroom": focus["headroom"],
            "unreceived_ar": float(amounts.sum() - ar[: focus_index + 1].sum()),
            "largest_unreceived_customers": focus_customers[:3],
            "largest_scheduled_outflows": sorted(
                [r for r in scheduled_outflows if r["week"] <= focus["week"]],
                key=lambda r: (-r["amount"], r["expense_id"]),
            )[:3],
            "unknown_outflow_weeks": [
                w["week"] for w in bridge if w["outflow_status"] == "unknown"
            ],
        },
        "timing_comparison": _timing_comparison(
            ar, cash_sales, new_credit, outgoing, opening_balance, cash_floor, weeks
        ),
        "assumptions": [
            "Dự thu hóa đơn = dư nợ tại ngày chốt × phần tiền phân bổ vào từng tuần; không nhân lại số tiền với xác suất tất toán 4 tuần.",
            "Phần chưa dự thu trong kỳ chỉ là dư nợ còn ngoài kỳ kỳ vọng, không phải dự báo xóa nợ hay cam kết sẽ thu đủ sau kỳ.",
            "Thu/chi hoạt động ước lượng được ghi riêng, không gán cho hóa đơn chưa tồn tại. Chi biến đổi chỉ bổ sung phần vượt chi biến đổi đã có lịch, tránh tính hai lần.",
            "Số dư kỳ vọng = số dư đầu + lũy kế dự thu − lũy kế dự chi. Phân rã này không phải SHAP của xác suất thiếu tiền hoặc phân vị số dư.",
            "Mô phỏng hiện dùng 400 đường, seed 7; mỗi dư nợ được rút một tuần thu (kể cả khi kỳ vọng dùng hồ sơ trả từng phần). Rủi ro thời điểm độc lập hoặc dùng cùng biến ngẫu nhiên theo khách khi bật căng thẳng; thu/chi hoạt động dùng sai số lịch sử nếu có. Xác suất cảnh báo chưa hiệu chỉnh.",
        ],
    }
