"""Custom metrics that need sub-ledgers or multi-step logic (AR/AP/cash).

Each function returns ``{"value", "rows", "entry_count", "notes", "summary"}``
and receives the already-validated period and resolved filters, so results
stay consistent with the linear metrics in :mod:`metrics`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .formatting import fmt_days, fmt_vnd
from .metrics import Term

AR = (Term(("131",)),)
AP = (Term(("331",), 1, "net_credit"),)
INV = (Term(("151", "152", "153", "154", "155", "156", "157")),)
CASH = (Term(("111", "112")),)
BUCKETS = [("Chưa đến hạn", None, 0), ("Quá hạn 1–30 ngày", 1, 30), ("Quá hạn 31–60 ngày", 31, 60), ("Quá hạn 61–90 ngày", 61, 90),
           ("Quá hạn 91–180 ngày", 91, 180), ("Quá hạn trên 180 ngày", 181, None)]


def _codes(params: dict, key: str) -> list[str]:
    return [x["code"] for x in params.get("_resolved", {}).get(key, [])]


def _require(eng, table: str) -> None:
    if table not in eng.tables:
        from .engine import MetricUnavailableError
        raise MetricUnavailableError(f"Dữ liệu chưa có sổ chi tiết '{table}' nên không tính được chỉ số này.")


def _eff(eng, end: date) -> date:
    return min(end, eng.as_of)


def balance(eng, terms, on: date, view: str, fsql: str, fparams: list) -> float:
    if on < date(1990, 1, 1):
        return 0.0
    total, *_ = eng.linear(terms, "snapshot", on, on, view, fsql, fparams, None)
    return total


def flow(eng, terms, start: date, end: date, view: str, fsql: str, fparams: list) -> float:
    total, *_ = eng.linear(terms, "flow", start, end, view, fsql, fparams, None)
    return total


# ------------------------------------------------------------------ AR open items
def ar_open_items(eng, on: date, params: dict) -> list[dict]:
    """Open invoices at date ``on``.  Unapplied credits (customer advances,
    year-end rebates) are applied FIFO to the oldest open invoices."""
    _require(eng, "ar_invoice")
    inv = eng.qdict("""
        SELECT i.invoice_id, i.einvoice_no, i.issue_date, i.due_date, i.customer_code, i.salesperson_code, i.branch_code, i.total_amount,
               i.total_amount - COALESCE(r.paid, 0) - COALESCE(a.adj, 0) AS remaining
        FROM ar_invoice i
        LEFT JOIN (SELECT invoice_id, SUM(amount) paid FROM ar_receipt WHERE receipt_date <= ? AND invoice_id IS NOT NULL GROUP BY 1) r USING (invoice_id)
        LEFT JOIN (SELECT invoice_id, SUM(total_amount) adj FROM ar_adjustment WHERE adjustment_date <= ? AND invoice_id IS NOT NULL GROUP BY 1) a
          USING (invoice_id)
        WHERE i.issue_date <= ? ORDER BY i.issue_date, i.invoice_id""", [on, on, on])
    credits = dict(eng.q("""SELECT customer_code, SUM(x) FROM (
        SELECT customer_code, amount x FROM ar_receipt WHERE invoice_id IS NULL AND receipt_date <= ?
        UNION ALL SELECT customer_code, total_amount FROM ar_adjustment WHERE invoice_id IS NULL AND adjustment_date <= ?) GROUP BY 1""", [on, on]))
    include, exclude = set(_codes(params, "customer")), set(_codes(params, "exclude_customers") + _codes(params, "exclude_top_customers"))
    branches, sales = set(_codes(params, "branch")), set(_codes(params, "salesperson"))
    out = []
    credit_left = {c: float(v) for c, v in credits.items()}
    for r in inv:
        c = r["customer_code"]
        rem = float(r["remaining"])
        if rem <= 0.5:
            continue
        use = min(rem, credit_left.get(c, 0.0))
        if use > 0:
            credit_left[c] -= use
            rem -= use
        if rem <= 0.5:
            continue
        if (include and c not in include) or c in exclude or (branches and r["branch_code"] not in branches) or (sales and r["salesperson_code"] not in sales):
            continue
        out.append({**r, "remaining": rem, "days_overdue": (on - r["due_date"]).days})
    for c, left in credit_left.items():
        if left > 0.5 and not ((include and c not in include) or c in exclude):
            out.append({"invoice_id": None, "einvoice_no": "(trả trước/chiết khấu chưa phân bổ)", "issue_date": None, "due_date": None,
                        "customer_code": c, "salesperson_code": None, "branch_code": None, "total_amount": 0, "remaining": -left, "days_overdue": None})
    return out


def _bucket(days) -> str:
    if days is None:
        return "Khoản trả trước chưa phân bổ"
    for label, lo, hi in BUCKETS:
        if (lo is None or days >= lo) and (hi is None or days <= hi):
            return label
    return BUCKETS[0][0]


def m_ar_aging(eng, md, start, end, view, fsql, fparams, group, params):
    on = _eff(eng, end)
    items = ar_open_items(eng, on, params)
    total = sum(i["remaining"] for i in items)
    agg = defaultdict(lambda: [0.0, 0])
    for i in items:
        b = _bucket(i["days_overdue"])
        agg[b][0] += i["remaining"]
        agg[b][1] += 1
    order = [b[0] for b in BUCKETS] + ["Khoản trả trước chưa phân bổ"]
    rows = [{"key": b, "label": b, "value": agg[b][0], "display": fmt_vnd(agg[b][0]), "invoices": agg[b][1],
             "share_pct": round(100 * agg[b][0] / total, 1) if total else None} for b in order if b in agg]
    overdue = sum(i["remaining"] for i in items if (i["days_overdue"] or 0) > 0)
    summary = {"total_open": fmt_vnd(total), "overdue": fmt_vnd(overdue), "overdue_pct": f"{100 * overdue / total:.1f}%".replace(".", ",") if total else None}
    if group == "customer":
        per = defaultdict(lambda: defaultdict(float))
        for i in items:
            per[i["customer_code"]][_bucket(i["days_overdue"])] += i["remaining"]
        rows = sorted(({"key": c, "label": eng.label_for("partner", c), "value": sum(b.values()), "display": fmt_vnd(sum(b.values())),
                        "buckets": {k: fmt_vnd(v) for k, v in b.items()}} for c, b in per.items()), key=lambda r: -r["value"])
    gl = balance(eng, AR, on, "mgmt", fsql, fparams)
    notes = [] if abs(gl - total) < 1000 else [f"Lệch sổ chi tiết và sổ cái 131: {fmt_vnd(gl - total)}."]
    return {"value": total, "rows": rows, "entry_count": len(items), "summary": summary, "notes": notes, "sql": "ar_invoice/ar_receipt/ar_adjustment"}


def m_overdue_receivables(eng, md, start, end, view, fsql, fparams, group, params):
    on = _eff(eng, end)
    min_days = int(params.get("min_days") or 0)
    items = [i for i in ar_open_items(eng, on, params) if i["days_overdue"] is not None and i["days_overdue"] > min_days]
    items.sort(key=lambda i: -i["remaining"])
    total = sum(i["remaining"] for i in items)
    rows = [{"key": i["einvoice_no"], "label": eng.label_for("partner", i["customer_code"]), "customer_code": i["customer_code"],
             "invoice_no": i["einvoice_no"], "issue_date": i["issue_date"].isoformat(), "due_date": i["due_date"].isoformat(),
             "days_overdue": i["days_overdue"], "value": i["remaining"], "display": fmt_vnd(i["remaining"])} for i in items]
    by_c = defaultdict(lambda: [0.0, 0, 0])
    for i in items:
        b = by_c[i["customer_code"]]
        b[0] += i["remaining"]
        b[1] += 1
        b[2] = max(b[2], i["days_overdue"])
    top = sorted(by_c.items(), key=lambda kv: -kv[1][0])[:5]
    summary = {"invoice_count": len(items), "customer_count": len(by_c), "min_days_overdue": min_days,
               "top_customers": [{"customer": eng.label_for("partner", c), "amount": fmt_vnd(v[0]), "invoices": v[1], "max_days_overdue": v[2]}
                                 for c, v in top]}
    return {"value": total, "rows": rows, "entry_count": len(items), "summary": summary, "sql": "ar_invoice open items"}


def _period_days(eng, start, end) -> tuple[date, int]:
    e = _eff(eng, end)
    return e, max((e - start).days + 1, 1)


def m_dso(eng, md, start, end, view, fsql, fparams, group, params):
    e, days = _period_days(eng, start, end)
    ar0 = balance(eng, AR, start - timedelta(days=1), view, fsql, fparams)
    ar1 = balance(eng, AR, e, view, fsql, fparams)
    sales = flow(eng, (Term(("131",), 1, "debit", "source_document_type = 'SALES_INVOICE'"),), start, e, view, fsql, fparams)
    if not sales:  # ledgers without document types
        sales = flow(eng, (Term(("511",), 1, "net_credit"),), start, e, view, fsql, fparams)
    val = ((ar0 + ar1) / 2) / sales * days if sales else None
    summary = {"ar_begin": fmt_vnd(ar0), "ar_end": fmt_vnd(ar1), "credit_sales_incl_vat": fmt_vnd(sales), "days": days}
    return {"value": val, "entry_count": 0, "summary": summary, "sql": "avg(131) / Dr131(SALES_INVOICE) × days"}


def m_dpo(eng, md, start, end, view, fsql, fparams, group, params):
    e, days = _period_days(eng, start, end)
    ap0 = balance(eng, AP, start - timedelta(days=1), view, fsql, fparams)
    ap1 = balance(eng, AP, e, view, fsql, fparams)
    purch = flow(eng, (Term(("331",), 1, "credit", "source_document_type IN ('PURCHASE_INVOICE','PURCHASE_SERVICE','ASSET_PURCHASE')"),),
                 start, e, view, fsql, fparams)
    val = ((ap0 + ap1) / 2) / purch * days if purch else None
    return {"value": val, "entry_count": 0, "summary": {"ap_begin": fmt_vnd(ap0), "ap_end": fmt_vnd(ap1), "purchases_incl_vat": fmt_vnd(purch), "days": days}}


def m_dio(eng, md, start, end, view, fsql, fparams, group, params):
    e, days = _period_days(eng, start, end)
    i0 = balance(eng, INV, start - timedelta(days=1), view, fsql, fparams)
    i1 = balance(eng, INV, e, view, fsql, fparams)
    cogs = flow(eng, (Term(("632",)),), start, e, view, fsql, fparams)
    val = ((i0 + i1) / 2) / cogs * days if cogs else None
    return {"value": val, "entry_count": 0, "summary": {"inventory_begin": fmt_vnd(i0), "inventory_end": fmt_vnd(i1), "cogs": fmt_vnd(cogs), "days": days}}


def m_ccc(eng, md, start, end, view, fsql, fparams, group, params):
    parts = {k: f(eng, md, start, end, view, fsql, fparams, group, params)["value"] for k, f in (("dso", m_dso), ("dio", m_dio), ("dpo", m_dpo))}
    val = None if None in parts.values() else parts["dso"] + parts["dio"] - parts["dpo"]
    rows = [{"key": k, "label": k.upper(), "value": v, "display": fmt_days(v)} for k, v in parts.items()]
    return {"value": val, "rows": rows, "entry_count": 0}


def m_dso_actual(eng, md, start, end, view, fsql, fparams, group, params):
    _require(eng, "ar_receipt")
    e = _eff(eng, end)
    basis = params.get('date_basis','receipt')
    if basis not in ('receipt','bank'):
        from .engine import EngineError
        raise EngineError('date_basis chỉ nhận receipt hoặc bank.')
    date_column = {'receipt':'receipt_date','bank':'bank_txn_date'}[basis]
    cond, prm = "", []
    inc = _codes(params, "customer")
    if inc:
        cond = f" AND r.customer_code IN ({', '.join('?' * len(inc))})"
        prm = inc
    for key,column in (('branch','i.branch_code'),('salesperson','i.salesperson_code')):
        codes = _codes(params,key)
        if codes:
            cond += f" AND {column} IN ({','.join('?' for _ in codes)})"
            prm += codes
    excluded = _codes(params,'exclude_customers')+_codes(params,'exclude_top_customers')
    if excluded:
        cond += f" AND r.customer_code NOT IN ({','.join('?' for _ in excluded)})"
        prm += excluded
    row = eng.q(f"""SELECT SUM(r.amount * date_diff('day', i.issue_date, r.{date_column})) / NULLIF(SUM(r.amount), 0), SUM(r.amount), COUNT(*)
                    FROM ar_receipt r JOIN ar_invoice i USING (invoice_id) JOIN dim_partner p ON p.partner_code = r.customer_code
                    WHERE r.{date_column} BETWEEN ? AND ? AND p.segment <> 'RET'{cond}""", [start, e] + prm)[0]
    val = float(row[0]) if row[0] is not None else None
    return {"value": val, "entry_count": int(row[2] or 0), "summary": {"collected": fmt_vnd(row[1] or 0), "receipts": int(row[2] or 0)},
            "notes": ["Không tính khách lẻ thanh toán ngay.", 'Cơ sở ngày: '+('ngày tiền về ngân hàng.' if basis=='bank' else 'ngày ghi sổ thu tiền.')],
            "date_basis":basis}


# ------------------------------------------------------------------ AP
def ap_open_bills(eng, on: date, params: dict) -> list[dict]:
    _require(eng, "ap_bill")
    rows = eng.qdict("""SELECT b.bill_id, b.vendor_invoice_no, b.bill_date, b.due_date, b.vendor_code, b.category, b.total_amount,
                               b.total_amount - COALESCE(p.paid, 0) AS remaining
                        FROM ap_bill b LEFT JOIN (SELECT bill_id, SUM(amount) paid FROM ap_payment WHERE payment_date <= ? GROUP BY 1) p USING (bill_id)
                        WHERE b.bill_date <= ?""", [on, on])
    inc = set(_codes(params, "vendor"))
    return [{**r, "remaining": float(r["remaining"])} for r in rows if abs(float(r["remaining"])) > 0.5 and (not inc or r["vendor_code"] in inc)]


def m_ap_due_soon(eng, md, start, end, view, fsql, fparams, group, params):
    on = eng.as_of
    horizon = end if start > on else on + timedelta(days=int(params.get("days") or 15))
    bills = ap_open_bills(eng, on, params)
    due = [b for b in bills if b["remaining"] > 0 and b["due_date"] <= horizon]
    overpaid = [b for b in bills if b["remaining"] < 0]
    due.sort(key=lambda b: b["due_date"])
    rows = [{"key": b["vendor_invoice_no"], "label": eng.label_for("partner", b["vendor_code"]), "vendor_code": b["vendor_code"],
             "due_date": b["due_date"].isoformat(), "status": "Đã quá hạn" if b["due_date"] < on else "Sắp đến hạn",
             "value": b["remaining"], "display": fmt_vnd(b["remaining"])} for b in due]
    over = sum(b["remaining"] for b in due if b["due_date"] < on)
    summary = {"horizon_end": horizon.isoformat(), "already_overdue": fmt_vnd(over), "due_in_window": fmt_vnd(sum(b["remaining"] for b in due) - over),
               "bills": len(due)}
    notes = [f"Có {len(overpaid)} hóa đơn mua bị thanh toán thừa, tổng {fmt_vnd(-sum(b['remaining'] for b in overpaid))} "
             f"({', '.join(sorted({eng.label_for('partner', b['vendor_code']) for b in overpaid}))})."] if overpaid else []
    return {"value": sum(b["remaining"] for b in due), "rows": rows, "entry_count": len(due), "summary": summary, "notes": notes}


def m_upcoming_obligations(eng, md, start, end, view, fsql, fparams, group, params):
    on = eng.as_of
    horizon = max(end, on)
    rows = []

    def add(key, label, value, due, source):
        if value and value > 0.5:
            rows.append({"key": key, "label": label, "value": value, "display": fmt_vnd(value), "due": due, "source": source})
    bills = [b for b in ap_open_bills(eng, on, params) if b["remaining"] > 0 and b["due_date"] <= horizon]
    add("AP_OVERDUE", "Nhà cung cấp – đã quá hạn", sum(b["remaining"] for b in bills if b["due_date"] < on), "ngay", "331 sổ chi tiết")
    add("AP_DUE", "Nhà cung cấp – đến hạn trong kỳ", sum(b["remaining"] for b in bills if b["due_date"] >= on), f"đến {horizon:%d/%m/%Y}", "331 sổ chi tiết")
    bal = {a: -balance(eng, (Term((a,)),), on, "mgmt", "", []) for a in ("33311", "3334", "3335", "3338", "334", "3382", "3383", "3384", "3385")}
    add("VAT", "Thuế GTGT phải nộp", bal["33311"], "ngày 20 tháng sau", "số dư 33311")
    add("PIT", "Thuế TNCN đã khấu trừ", bal["3335"], "ngày 20 tháng sau", "số dư 3335")
    add("CIT", "Thuế TNDN tạm tính", bal["3334"], "ngày 30 tháng đầu quý sau", "số dư 3334")
    add("INS", "BHXH, BHYT, BHTN, KPCĐ", sum(bal[a] for a in ("3382", "3383", "3384", "3385")), "cuối tháng", "số dư 338x")
    add("SALARY_DUE", "Lương còn phải trả", bal["334"], "ngày 05", "số dư 334")
    if "payroll" in eng.tables:
        last = eng.q("SELECT year_month, SUM(net_pay) FROM payroll GROUP BY 1 ORDER BY 1 DESC LIMIT 1")
        n_pay = sum(1 for k in range((horizon - on).days + 1) if (on + timedelta(days=k)).day == 5)
        if last and n_pay and bal["334"] < float(last[0][1]) * 0.5:
            add("SALARY_EST", f"Lương ước tính ({n_pay} kỳ trả, theo bảng lương {last[0][0]})", float(last[0][1]) * n_pay, "ngày 05", "bảng lương")
    if "loan_schedule" in eng.tables:
        p = eng.q("SELECT SUM(principal) FROM loan_schedule WHERE due_date > ? AND due_date <= ?", [on, horizon])[0][0]
        add("LOAN", "Trả nợ gốc vay theo lịch", float(p or 0), f"đến {horizon:%d/%m/%Y}", "lịch trả nợ")
    m = max(1, round((horizon - on).days / 30))
    intr = flow(eng, (Term(("635",)),), on - timedelta(days=89), on, "mgmt", "", []) / 3 * m
    add("INTEREST", "Lãi vay ước tính", intr, "cuối tháng", "bình quân 635 3 tháng")
    total = sum(r["value"] for r in rows)
    cash = balance(eng, CASH, on, "mgmt", "", [])
    return {"value": total, "rows": rows, "entry_count": len(bills),
            "summary": {"window": f"{on:%d/%m/%Y}–{horizon:%d/%m/%Y}", "cash_now": fmt_vnd(cash), "gap_vs_cash": fmt_vnd(cash - total)},
            "notes": ["Chưa gồm chi phí vận hành phát sinh mới (điện, marketing…) và tiền sẽ thu từ khách hàng."]}


# ------------------------------------------------------------------ cash
CASH_CATEGORY_SQL = """
CASE
  WHEN accs IS NULL THEN 'Chuyển tiền nội bộ (quỹ ↔ ngân hàng)'
  WHEN accs LIKE '%131%' THEN 'Thu tiền khách hàng'
  WHEN accs LIKE '%331%' THEN 'Trả nhà cung cấp'
  WHEN accs LIKE '%334%' OR accs LIKE '%335%' THEN 'Chi lương, thưởng'
  WHEN accs LIKE '%338%' THEN 'Nộp BHXH, BHYT, BHTN, KPCĐ'
  WHEN accs LIKE '%333%' THEN 'Nộp thuế'
  WHEN accs LIKE '%341%' AND amt > 0 THEN 'Giải ngân vay'
  WHEN accs LIKE '%341%' THEN 'Trả nợ gốc vay'
  WHEN accs LIKE '%635%' THEN 'Trả lãi vay'
  WHEN accs LIKE '%515%' THEN 'Thu lãi tiền gửi'
  WHEN accs LIKE '%141%' THEN 'Tạm ứng / hoàn ứng nhân viên'
  WHEN accs LIKE '%211%' THEN 'Đầu tư tài sản cố định'
  WHEN accs LIKE '%711%' THEN 'Thu nhập khác'
  ELSE 'Chi phí khác bằng tiền'
END"""


def cash_journals(eng, start: date, end: date) -> str:
    return f"""
    WITH c AS (SELECT journal_id, year_month, SUM(net_debit) AS amt FROM v_mgmt
               WHERE (account_code LIKE '111%' OR account_code LIKE '112%') AND posting_date BETWEEN DATE '{start}' AND DATE '{end}'
                 AND COALESCE(source_module, '') <> 'OPENING' GROUP BY 1, 2),
         o AS (SELECT journal_id, string_agg(DISTINCT left(account_code, 3), ',') AS accs FROM v_mgmt
               WHERE NOT (account_code LIKE '111%' OR account_code LIKE '112%') AND journal_id IN (SELECT journal_id FROM c) GROUP BY 1)
    SELECT c.journal_id, c.year_month, c.amt, {CASH_CATEGORY_SQL} AS category
    FROM c LEFT JOIN o USING (journal_id)"""


def m_cash_flow_breakdown(eng, md, start, end, view, fsql, fparams, group, params):
    e = _eff(eng, end)
    base = cash_journals(eng, start, e)
    rows = eng.qdict(f"""SELECT category, SUM(CASE WHEN amt > 0 THEN amt ELSE 0 END) AS inflow, SUM(CASE WHEN amt < 0 THEN -amt ELSE 0 END) AS outflow,
                                SUM(amt) AS net, COUNT(*) AS docs FROM ({base}) GROUP BY 1 ORDER BY ABS(SUM(amt)) DESC""")
    out = [{"key": r["category"], "label": r["category"], "value": float(r["net"]), "display": fmt_vnd(r["net"]),
            "inflow": fmt_vnd(r["inflow"]), "outflow": fmt_vnd(r["outflow"]), "documents": int(r["docs"])} for r in rows
           if not r["category"].startswith("Chuyển tiền nội bộ")]
    total = sum(float(r["net"]) for r in rows)
    summary = {"total_inflow": fmt_vnd(sum(float(r["inflow"]) for r in rows if not r["category"].startswith("Chuyển"))),
               "total_outflow": fmt_vnd(sum(float(r["outflow"]) for r in rows if not r["category"].startswith("Chuyển")))}
    if group == "month":
        monthly = eng.q(f"SELECT year_month, SUM(amt) FROM ({base}) GROUP BY 1 ORDER BY 1")
        summary["by_month"] = [{"month": m, "net": fmt_vnd(v), "value": float(v)} for m, v in monthly]
    return {"value": total, "rows": out, "entry_count": sum(int(r["docs"]) for r in rows), "summary": summary, "sql": base}


def m_cash_coverage_days(eng, md, start, end, view, fsql, fparams, group, params):
    on = _eff(eng, end)
    cash = balance(eng, CASH, on, "mgmt", "", [])
    base = cash_journals(eng, on - timedelta(days=89), on)
    out = eng.q(f"""SELECT -SUM(amt) FROM ({base}) WHERE amt < 0 AND category NOT IN ('Trả nợ gốc vay', 'Chuyển tiền nội bộ (quỹ ↔ ngân hàng)')""")[0][0]
    daily = float(out or 0) / 90
    val = cash / daily if daily else None
    return {"value": val, "entry_count": 0, "summary": {"cash": fmt_vnd(cash), "avg_daily_outflow": fmt_vnd(daily)},
            "notes": ["Chưa tính tiền sẽ thu từ khách hàng; dùng để đánh giá vùng đệm thanh khoản."]}


from .custom2 import CUSTOM2  # noqa: E402

CUSTOM = {
    "ar_aging": m_ar_aging, "overdue_receivables": m_overdue_receivables, "dso": m_dso, "dpo": m_dpo, "dio": m_dio,
    "cash_conversion_cycle": m_ccc, "dso_actual": m_dso_actual, "ap_due_soon": m_ap_due_soon, "upcoming_obligations": m_upcoming_obligations,
    "cash_flow_breakdown": m_cash_flow_breakdown, "cash_coverage_days": m_cash_coverage_days, **CUSTOM2,
}
