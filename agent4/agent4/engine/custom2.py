"""Custom metrics, part 2: anomalies, planning, payroll and the tax view."""
from __future__ import annotations

import calendar
import statistics
from datetime import date, timedelta

from .formatting import fmt_pct, fmt_vnd
from .metrics import PL_ALL

OPEX_COND = "(account_code LIKE '641%' OR account_code LIKE '642%')"
TAX_NOTES = {
    "NO_VALID_INVOICE": "Không có hóa đơn/chứng từ hợp lệ",
    "CASH_OVER_THRESHOLD": "Thanh toán tiền mặt từ 5 triệu đồng trở lên (không đủ điều kiện khấu trừ/được trừ)",
    "ADMIN_PENALTY": "Tiền phạt vi phạm hành chính",
    "LATE_PAYMENT_INTEREST": "Tiền chậm nộp thuế",
}


def _eff(eng, end: date) -> date:
    return min(end, eng.as_of)


def _month_start(d: date, back: int = 0) -> date:
    y, m = d.year, d.month - back
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1)


def _month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def m_expense_spikes(eng, md, start, end, view, fsql, fparams, group, params):
    e = _eff(eng, end)
    base_start, base_end = _month_start(start, 3), _month_start(start) - timedelta(days=1)
    elapsed = (e - start).days + 1
    full = (_month_end(start) - start).days + 1 if start.day == 1 and end == _month_end(start) else elapsed
    prorate = min(1.0, elapsed / full) if full else 1.0
    cur = dict(eng.q(f"""SELECT cost_category, SUM(net_debit) FROM v_mgmt WHERE {OPEX_COND} AND posting_date BETWEEN ? AND ?
                         AND NOT is_closing AND cost_category IS NOT NULL{fsql} GROUP BY 1""", [start, e] + fparams))
    base = dict(eng.q(f"""SELECT cost_category, SUM(net_debit) / 3 FROM v_mgmt WHERE {OPEX_COND} AND posting_date BETWEEN ? AND ?
                          AND NOT is_closing AND cost_category IS NOT NULL{fsql} GROUP BY 1""", [base_start, base_end] + fparams))
    rows = []
    for cc in set(cur) | set(base):
        c, b = float(cur.get(cc) or 0), float(base.get(cc) or 0) * prorate
        delta = c - b
        ratio = c / b if b else None
        rows.append({"key": cc, "label": eng.label_for("cost_category", cc), "value": delta, "display": fmt_vnd(delta) if delta < 0 else "+" + fmt_vnd(delta),
                     "current": fmt_vnd(c), "baseline_avg_3m": fmt_vnd(b), "change_pct": fmt_pct((ratio - 1) * 100) if ratio else "mới phát sinh",
                     "is_spike": bool(delta >= 20_000_000 and (ratio is None or ratio >= 1.3))})
    rows.sort(key=lambda r: -r["value"])
    notes = [f"Bình quân 3 tháng {base_start:%m/%Y}–{base_end:%m/%Y}" + (f", đã quy đổi theo {elapsed}/{full} ngày của kỳ hiện tại." if prorate < 1 else ".")]
    spikes = [r for r in rows if r["is_spike"]]
    return {"value": rows[0]["value"] if rows else 0.0, "rows": rows, "entry_count": len(rows), "notes": notes,
            "summary": {"spike_count": len(spikes), "top_spike": spikes[0]["label"] if spikes else None}}


def m_unusual_account_movements(eng, md, start, end, view, fsql, fparams, group, params):
    e = _eff(eng, end)
    ms = _month_start(e)
    hist_start = _month_start(e, 6)
    data = eng.q("""SELECT account_code, year_month, SUM(debit_amount), SUM(credit_amount) FROM v_mgmt
                    WHERE posting_date BETWEEN ? AND ? AND NOT is_closing AND COALESCE(source_module, '') <> 'OPENING' GROUP BY 1, 2""",
                 [hist_start, e])
    cur_ym = f"{ms:%Y-%m}"
    series: dict = {}
    for acc, ym, d_, c_ in data:
        series.setdefault(acc, {})[ym] = (float(d_), float(c_))
    hist_months = [f"{_month_start(ms, k):%Y-%m}" for k in range(1, 7)]
    rows = []
    for acc, s in series.items():
        for side, idx in (("Nợ", 0), ("Có", 1)):
            hist = [s.get(m, (0.0, 0.0))[idx] for m in hist_months]
            cur = s.get(cur_ym, (0.0, 0.0))[idx]
            mu = statistics.mean(hist)
            sd = statistics.pstdev(hist) or max(mu * 0.1, 1.0)
            z = (cur - mu) / sd
            if abs(z) >= 2.5 and abs(cur - mu) >= 50_000_000:
                rows.append({"key": f"{acc}-{side}", "label": f"{acc} {eng.account_names.get(acc, '')} (phát sinh {side})", "value": cur - mu,
                             "display": fmt_vnd(cur), "avg_6m": fmt_vnd(mu), "z_score": round(z, 1)})
    rows.sort(key=lambda r: -abs(r["z_score"]))
    notes = [f"So sánh phát sinh tháng {ms:%m/%Y}" + (f" (đến {e:%d/%m})" if e < _month_end(ms) else "") + " với 6 tháng trước."]
    return {"value": float(len(rows)), "rows": rows, "entry_count": len(rows), "notes": notes}


def m_unbalanced_journals(eng, md, start, end, view, fsql, fparams, group, params):
    rows = eng.qdict("""SELECT journal_id, MIN(posting_date) AS d, ANY_VALUE(description) AS descr, ANY_VALUE(created_by) AS who,
                               SUM(debit_amount) AS dr, SUM(credit_amount) AS cr FROM v_mgmt WHERE posting_date BETWEEN ? AND ?
                        GROUP BY 1 HAVING SUM(debit_amount) <> SUM(credit_amount) ORDER BY 2""", [start, _eff(eng, end)])
    out = [{"key": r["journal_id"], "label": r["descr"], "date": r["d"].isoformat(), "created_by": r["who"], "debit": fmt_vnd(r["dr"]),
            "credit": fmt_vnd(r["cr"]), "value": float(r["dr"] - r["cr"]), "display": fmt_vnd(float(r["dr"] - r["cr"]), exact=True)} for r in rows]
    n = eng.q("SELECT COUNT(DISTINCT journal_id) FROM v_mgmt WHERE posting_date BETWEEN ? AND ?", [start, _eff(eng, end)])[0][0]
    return {"value": float(len(out)), "rows": out, "entry_count": int(n), "summary": {"journals_checked": int(n)}}


def m_top_sales_transactions(eng, md, start, end, view, fsql, fparams, group, params):
    k = int(params.get("_top_k") or params.get("top_k") or 10)
    e = _eff(eng, end)
    if "ar_invoice" in eng.tables:
        rows = eng.qdict("""SELECT einvoice_no, issue_date, customer_code, subtotal, total_amount, description FROM ar_invoice
                            WHERE issue_date BETWEEN ? AND ? AND NOT is_opening ORDER BY subtotal DESC LIMIT ?""", [start, e, k])
        out = [{"key": r["einvoice_no"], "label": eng.label_for("partner", r["customer_code"]), "date": r["issue_date"].isoformat(),
                "value": float(r["subtotal"]), "display": fmt_vnd(r["subtotal"]), "total_incl_vat": fmt_vnd(r["total_amount"])} for r in rows]
    else:
        rows = eng.q("""SELECT journal_id, MIN(posting_date), ANY_VALUE(partner_code), SUM(credit_amount - debit_amount) v FROM v_mgmt
                        WHERE account_code LIKE '511%' AND posting_date BETWEEN ? AND ? GROUP BY 1 ORDER BY v DESC LIMIT ?""", [start, e, k])
        out = [{"key": j, "label": eng.label_for("partner", p), "date": d.isoformat(), "value": float(v), "display": fmt_vnd(v)} for j, d, p, v in rows]
    return {"value": out[0]["value"] if out else 0.0, "rows": out, "entry_count": len(out)}


def m_budget_vs_actual(eng, md, start, end, view, fsql, fparams, group, params):
    if "budget" not in eng.tables:
        from .engine import MetricUnavailableError
        raise MetricUnavailableError("Chưa có bảng ngân sách.")
    e = _eff(eng, end)
    months, d = [], date(start.year, start.month, 1)
    while d <= e:
        me = _month_end(d)
        lo, hi = max(d, start), min(me, e)
        months.append((d.year, d.month, ((hi - lo).days + 1) / ((me - d).days + 1)))
        d = me + timedelta(days=1)
    line = str(params.get("line_type") or "ALL").upper()
    branches = [x["code"] for x in params.get("_resolved", {}).get("branch", [])]

    def budget(kind: str, by: str) -> dict:
        out: dict = {}
        for y, m, w in months:
            cond = " AND branch_code IN (" + ",".join("?" * len(branches)) + ")" if branches else ""
            for k, v in eng.q(f"SELECT {by}, SUM(amount) FROM budget WHERE year_no=? AND month_no=? AND line_type=?{cond} GROUP BY 1",
                              [y, m, kind] + branches):
                out[k] = out.get(k, 0.0) + float(v) * w
        return out
    rev_by = "branch_code"
    exp_by = "cost_category" if group != "branch" else "branch_code"
    act_rev = dict(eng.q(f"""SELECT branch_code, SUM(credit_amount - debit_amount) FROM v_mgmt WHERE account_code LIKE '511%' AND NOT is_closing
                             AND posting_date BETWEEN ? AND ?{fsql} GROUP BY 1""", [start, e] + fparams))
    act_exp = dict(eng.q(f"""SELECT {'cost_category' if exp_by == 'cost_category' else 'COALESCE(branch_code, \'HN\')'}, SUM(net_debit) FROM v_mgmt
                             WHERE {OPEX_COND} AND NOT is_closing AND posting_date BETWEEN ? AND ?{fsql} GROUP BY 1""", [start, e] + fparams))
    b_rev, b_exp = budget("REVENUE", rev_by), budget("EXPENSE", exp_by)
    rows = []
    if line in ("ALL", "REVENUE"):
        for k in sorted(set(b_rev) | set(act_rev), key=str):
            a, b = float(act_rev.get(k) or 0), b_rev.get(k, 0.0)
            rows.append({"key": f"REV-{k}", "label": f"Doanh thu – {eng.label_for('branch', k)}", "type": "REVENUE", "value": a - b,
                         "actual": fmt_vnd(a), "budget": fmt_vnd(b), "achieved_pct": fmt_pct(100 * a / b) if b else None,
                         "display": ("+" if a >= b else "") + fmt_vnd(a - b)})
    if line in ("ALL", "EXPENSE"):
        exp_rows = []
        for k in set(b_exp) | set(act_exp):
            a, b = float(act_exp.get(k) or 0), b_exp.get(k, 0.0)
            lab = eng.label_for("cost_category" if exp_by == "cost_category" else "branch", k)
            exp_rows.append({"key": f"EXP-{k}", "label": f"Chi phí – {lab}", "type": "EXPENSE", "value": a - b, "actual": fmt_vnd(a),
                             "budget": fmt_vnd(b), "achieved_pct": fmt_pct(100 * a / b) if b else None,
                             "display": ("+" if a >= b else "") + fmt_vnd(a - b), "over_budget": a > b * 1.05})
        rows += sorted(exp_rows, key=lambda r: -r["value"])
    tr, tb = sum(float(v or 0) for v in act_rev.values()), sum(b_rev.values())
    te, teb = sum(float(v or 0) for v in act_exp.values()), sum(b_exp.values())
    summary = {"revenue_actual": fmt_vnd(tr), "revenue_budget": fmt_vnd(tb), "revenue_achieved_pct": fmt_pct(100 * tr / tb) if tb else None,
               "expense_actual": fmt_vnd(te), "expense_budget": fmt_vnd(teb), "expense_used_pct": fmt_pct(100 * te / teb) if teb else None}
    notes = ["Tháng chưa kết thúc được phân bổ ngân sách theo số ngày đã qua."] if any(w < 1 for *_, w in months) else []
    value = tr - tb if line != "EXPENSE" else te - teb
    return {"value": value, "rows": rows, "entry_count": len(rows), "summary": summary, "notes": notes}


def m_payroll_summary(eng, md, start, end, view, fsql, fparams, group, params):
    if "payroll" not in eng.tables:
        from .engine import MetricUnavailableError
        raise MetricUnavailableError("Chưa có bảng lương chi tiết.")
    e = _eff(eng, end)
    lo, hi = f"{start:%Y-%m}", f"{e:%Y-%m}"
    by = {"branch": "branch_code", "department": "department_code"}.get(group or "department", "department_code")
    tot = eng.q("""SELECT SUM(gross_salary + bonus), SUM(employer_contribution), SUM(pit), SUM(net_pay), MAX(year_month)
                   FROM payroll WHERE year_month BETWEEN ? AND ?""", [lo, hi])[0]
    if tot[4] is None:
        return {"value": 0.0, "rows": [], "entry_count": 0, "notes": [f"Chưa có bảng lương cho kỳ {lo}–{hi} (lương tính vào cuối tháng)."]}
    head = eng.q("SELECT COUNT(DISTINCT employee_code) FROM payroll WHERE year_month = ?", [tot[4]])[0][0]
    rows = eng.q(f"""SELECT {by}, COUNT(DISTINCT employee_code) FILTER (WHERE year_month = ?), SUM(gross_salary + bonus), SUM(employer_contribution)
                     FROM payroll WHERE year_month BETWEEN ? AND ? GROUP BY 1 ORDER BY 3 DESC""", [tot[4], lo, hi])
    dim = "branch" if by == "branch_code" else "department"
    out = [{"key": k, "label": eng.label_for(dim, k), "headcount": int(n), "value": float(g) + float(c), "display": fmt_vnd(float(g) + float(c)),
            "gross_and_bonus": fmt_vnd(g), "employer_contribution": fmt_vnd(c)} for k, n, g, c in rows]
    summary = {"headcount": int(head), "headcount_month": tot[4], "gross_and_bonus": fmt_vnd(tot[0]), "employer_contribution": fmt_vnd(tot[1]),
               "pit_withheld": fmt_vnd(tot[2]), "net_pay": fmt_vnd(tot[3])}
    return {"value": float(tot[0]) + float(tot[1]), "rows": out, "entry_count": len(out), "summary": summary,
            "notes": [f"Bảng lương các tháng {lo}–{tot[4]} (lương tháng hiện tại chưa tính nếu chưa hết tháng)."]}


def m_mgmt_vs_tax_gap(eng, md, start, end, view, fsql, fparams, group, params):
    e = _eff(eng, end)
    rows = eng.q(f"""SELECT COALESCE(tax_note, 'KHAC'), cost_category, SUM(net_debit), COUNT(*) FROM v_mgmt
                     WHERE NOT tax_deductible AND (account_code LIKE '6%' OR account_code LIKE '8%') AND NOT is_closing
                       AND posting_date BETWEEN ? AND ?{fsql} GROUP BY 1, 2 ORDER BY 3 DESC""", [start, e] + fparams)
    vat = eng.q(f"""SELECT SUM(net_debit) FROM v_mgmt WHERE NOT tax_deductible AND account_code LIKE '133%' AND posting_date BETWEEN ? AND ?{fsql}""",
                [start, e] + fparams)[0][0]
    out = [{"key": f"{n}-{c}", "label": f"{TAX_NOTES.get(n, n)} – {eng.label_for('cost_category', c)}", "reason": TAX_NOTES.get(n, n),
            "value": float(v), "display": fmt_vnd(v), "lines": int(k)} for n, c, v, k in rows]
    total = sum(r["value"] for r in out)
    return {"value": total, "rows": out, "entry_count": sum(r["lines"] for r in out),
            "summary": {"non_deductible_expenses": fmt_vnd(total), "non_creditable_input_vat": fmt_vnd(vat or 0),
                        "cit_impact_20pct": fmt_vnd(total * 0.2)}}


def m_cit_estimate(eng, md, start, end, view, fsql, fparams, group, params):
    e = _eff(eng, end)
    taxable, *_ = eng.linear(PL_ALL, "flow", start, e, "tax", fsql, fparams, None)
    pbt, *_ = eng.linear(PL_ALL, "flow", start, e, "mgmt", fsql, fparams, None)
    recorded = eng.q("SELECT SUM(net_debit) FROM v_mgmt WHERE account_code LIKE '821%' AND NOT is_closing AND posting_date BETWEEN ? AND ?",
                     [start, e])[0][0]
    cit = max(taxable, 0.0) * 0.20
    rows = [{"key": "pbt", "label": "Lợi nhuận kế toán trước thuế (khung quản trị)", "value": pbt, "display": fmt_vnd(pbt)},
            {"key": "gap", "label": "Cộng: chi phí không được trừ", "value": taxable - pbt, "display": fmt_vnd(taxable - pbt)},
            {"key": "taxable", "label": "Thu nhập chịu thuế (khung thuế)", "value": taxable, "display": fmt_vnd(taxable)},
            {"key": "cit", "label": "Thuế TNDN 20%", "value": cit, "display": fmt_vnd(cit)},
            {"key": "recorded", "label": "Thuế TNDN đã tạm tính trên sổ (821)", "value": float(recorded or 0), "display": fmt_vnd(recorded or 0)}]
    return {"value": cit, "rows": rows, "entry_count": 0,
            "notes": ["Ước tính theo thuế suất phổ thông 20%; chưa gồm ưu đãi, lỗ chuyển kỳ và điều chỉnh khác khi quyết toán."]}


def m_vat_position(eng, md, start, end, view, fsql, fparams, group, params):
    e = _eff(eng, end)
    out_vat = eng.q("""SELECT SUM(CASE WHEN source_document_type IN ('SALES_INVOICE') THEN credit_amount ELSE 0 END)
                            - SUM(CASE WHEN source_document_type IN ('SALES_RETURN','SALES_REBATE') THEN debit_amount ELSE 0 END)
                       FROM v_mgmt WHERE account_code LIKE '33311%' AND posting_date BETWEEN ? AND ?""", [start, e])[0][0] or 0
    in_vat = eng.q("""SELECT SUM(debit_amount) FROM v_tax WHERE account_code LIKE '133%' AND posting_date BETWEEN ? AND ?
                      AND source_document_type <> 'VAT_OFFSET'""", [start, e])[0][0] or 0
    bal = eng.q("SELECT -SUM(net_debit) FROM v_mgmt WHERE account_code LIKE '33311%' AND posting_date <= ?", [e])[0][0] or 0
    out_vat, in_vat, bal = float(out_vat), float(in_vat), float(bal)
    rows = [{"key": "output", "label": "Thuế GTGT đầu ra", "value": out_vat, "display": fmt_vnd(out_vat)},
            {"key": "input", "label": "Thuế GTGT đầu vào được khấu trừ", "value": in_vat, "display": fmt_vnd(in_vat)},
            {"key": "net", "label": "Số thuế GTGT phát sinh phải nộp (đầu ra − đầu vào)", "value": out_vat - in_vat, "display": fmt_vnd(out_vat - in_vat)},
            {"key": "balance", "label": f"Số dư 33311 còn phải nộp tại {e:%d/%m/%Y}", "value": bal, "display": fmt_vnd(bal)}]
    return {"value": out_vat - in_vat, "rows": rows, "entry_count": 0, "notes": ["Kê khai GTGT theo tháng; hạn nộp ngày 20 tháng sau."]}


CUSTOM2 = {
    "expense_spikes": m_expense_spikes, "unusual_account_movements": m_unusual_account_movements, "unbalanced_journals": m_unbalanced_journals,
    "top_sales_transactions": m_top_sales_transactions, "budget_vs_actual": m_budget_vs_actual, "payroll_summary": m_payroll_summary,
    "mgmt_vs_tax_gap": m_mgmt_vs_tax_gap, "cit_estimate": m_cit_estimate, "vat_position": m_vat_position,
}
