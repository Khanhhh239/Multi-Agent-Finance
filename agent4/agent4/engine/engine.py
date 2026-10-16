"""Deterministic execution engine for the semantic metric layer.

``ExecutionEngine.query`` is the single entry point used by the agent's tools:
it validates the request (metric, view, group-by, filters, period), compiles
the metric's terms into parameterised SQL over ``v_mgmt`` / ``v_tax``, runs it
on a read-only DuckDB connection and returns a JSON-able result with display
strings, comparison, breakdown rows and an audit trail (accounts, entry count,
formula, SQL, data-close status).  ``get_metric`` keeps the original v0
contract used by ``test_engine.py``.
"""
from __future__ import annotations

import hashlib
import copy
import json
from functools import wraps
import re
import threading
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from . import periods as P
from .formatting import fmt_delta, fmt_value
from .metrics import GROUP_LABELS, REGISTRY, MetricDef, Term


class EngineError(ValueError):
    """Base class: messages are Vietnamese and safe to show to the LLM/user."""
    code = 'ENGINE_ERROR'


class MetricNotFoundError(EngineError, KeyError):
    code = 'METRIC_NOT_FOUND'
    def __str__(self) -> str:  # KeyError would add quotes
        return self.args[0]


class InvalidDateRangeError(EngineError):
    code = 'INVALID_DATE_RANGE'


class FilterError(EngineError):
    code = 'INVALID_FILTER'
    def __init__(self, message: str, candidates: list[dict] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


class ViewNotAllowedError(EngineError):
    code = 'VIEW_NOT_ALLOWED'


class MetricUnavailableError(EngineError):
    code = 'METRIC_UNAVAILABLE'


class ScopeNotSupported(EngineError):
    code = 'SCOPE_NOT_SUPPORTED'


def _validated_request(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except EngineError:
            raise
        except (ValueError, TypeError) as exc:
            raise EngineError('Tham số yêu cầu không hợp lệ. Kiểm tra kiểu dữ liệu, kỳ và bộ lọc.') from exc
    return wrapped


LEGACY_VIEW_SQL = """
CREATE OR REPLACE TEMP VIEW v_gl AS
SELECT g.entry_id, g.journal_id, g.entry_no, g.posting_date, g.period_key, strftime(g.posting_date, '%Y-%m') AS year_month,
       year(g.posting_date) AS year_no, quarter(g.posting_date) AS quarter_no, month(g.posting_date) AS month_no,
       a.account_code, a.account_name, a.account_type, pa.partner_code, pa.partner_name, pa.partner_type, NULL::VARCHAR AS segment,
       i.item_code, i.item_name, NULL::VARCHAR AS product_line, NULL::VARCHAR AS cost_category, NULL::VARCHAR AS branch_code,
       NULL::VARCHAR AS department_code, NULL::VARCHAR AS employee_code, NULL::VARCHAR AS employee_name, g.description,
       g.debit_amount, g.credit_amount, g.debit_amount - g.credit_amount AS net_debit, g.source_document_type, g.source_document_no,
       NULL::VARCHAR AS source_module, FALSE AS is_closing, TRUE AS tax_deductible, NULL::VARCHAR AS tax_note, NULL::VARCHAR AS created_by, g.created_at
FROM gl_entry g JOIN dim_account a USING (account_key) LEFT JOIN dim_partner pa USING (partner_key) LEFT JOIN dim_item i USING (item_key);
CREATE OR REPLACE TEMP VIEW v_mgmt AS SELECT * FROM v_gl;
CREATE OR REPLACE TEMP VIEW v_tax AS SELECT * FROM v_gl WHERE tax_deductible;
"""

GROUP_SQL = {
    "month": ("year_month", None), "quarter": ("CAST(year_no AS VARCHAR) || '-Q' || CAST(quarter_no AS VARCHAR)", None),
    "year": ("CAST(year_no AS VARCHAR)", None), "branch": ("branch_code", "branch"), "product_line": ("product_line", "product_line"),
    "customer": ("partner_code", "partner"), "vendor": ("partner_code", "partner"), "item": ("item_code", "item"),
    "cost_category": ("cost_category", "cost_category"), "department": ("department_code", "department"),
    "salesperson": ("employee_code", "employee"), "account": ("account_code", "account"),
}
FILTER_KEYS = ("customer", "vendor", "branch", "product_line", "item", "cost_category", "department", "salesperson",
               "exclude_customers", "exclude_top_customers")
MEASURE_SQL = {"net_debit": "(debit_amount - credit_amount)", "net_credit": "(credit_amount - debit_amount)",
               "debit": "debit_amount", "credit": "credit_amount"}
VIEW_TABLE = {"mgmt": "v_mgmt", "tax": "v_tax"}
COMPARE_MODES = ('previous_period','same_period_last_year')
FLOW_COND = "NOT COALESCE(is_closing, FALSE) AND COALESCE(source_module, '') <> 'OPENING'"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", P.strip_accents(str(s).lower())).strip()


class ExecutionEngine:
    def __init__(self, database_path: str | Path, as_of: date | None = None, read_only: bool = True) -> None:
        self.path = str(database_path)
        self.con = duckdb.connect(self.path, read_only=read_only)
        # Bound allocator/thread pressure when a local model shares laptop RAM.
        # These are execution resources, never financial formula settings.
        self.con.execute('SET threads=4')
        self.con.execute("SET memory_limit='512MB'")
        self._lock = threading.RLock()
        self.tables = {r[0] for r in self.con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        self.legacy = "v_gl" not in self.tables
        if self.legacy:
            self.con.execute(LEGACY_VIEW_SQL)
        info = dict(self.con.execute("SELECT key, value FROM company_info").fetchall()) if "company_info" in self.tables else {}
        self.info = info
        if as_of is None:
            as_of = date.fromisoformat(info["as_of_date"]) if "as_of_date" in info else (
                self.con.execute("SELECT MAX(posting_date) FROM gl_entry").fetchone()[0] or date.today())
        self.as_of: date = as_of
        self.last_closed: str | None = info.get("last_closed_month")
        self._load_dims()

    # ------------------------------------------------------------------ utils
    def q(self, sql: str, params: list | None = None) -> list[tuple]:
        with self._lock:
            return self.con.execute(sql, params or []).fetchall()

    def qdict(self, sql: str, params: list | None = None) -> list[dict]:
        with self._lock:
            cur = self.con.execute(sql, params or [])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def cursor(self):
        """Independent DuckDB cursor and lock per request; close it after use."""
        with self._lock:
            child = copy.copy(self)
            child.con = self.con.cursor()
            child._lock = threading.RLock()
            if self.legacy:
                child.con.execute(LEGACY_VIEW_SQL)
            return child

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _load_dims(self) -> None:
        self.partners = {r[0]: {"code": r[0], "name": r[1], "type": r[2]} for r in self.q("SELECT partner_code, partner_name, partner_type FROM dim_partner")}
        self.items = {r[0]: r[1] for r in self.q("SELECT item_code, item_name FROM dim_item")}
        self.account_names = {r[0]: r[1] for r in self.q("SELECT account_code, account_name FROM dim_account")}

        def opt(t: str, sql: str) -> dict:
            return dict(self.q(sql)) if t in self.tables else {}
        self.branches = opt("dim_branch", "SELECT branch_code, branch_name FROM dim_branch")
        self.departments = opt("dim_department", "SELECT department_code, department_name FROM dim_department")
        self.employees = opt("dim_employee", "SELECT employee_code, employee_name FROM dim_employee")
        self.cost_categories = opt("dim_cost_category", "SELECT cost_category, cost_category_name FROM dim_cost_category")
        self.product_lines = opt("dim_product_line", "SELECT product_line, product_line_name FROM dim_product_line")

    def label_for(self, dim: str | None, key: Any) -> str:
        if key is None:
            return "(không phân bổ)"
        k = str(key)
        table = {"partner": {c: p["name"] for c, p in self.partners.items()}, "item": self.items, "account": self.account_names,
                 "branch": self.branches, "department": self.departments, "employee": self.employees, "cost_category": self.cost_categories,
                 "product_line": self.product_lines}.get(dim or "", {})
        return table.get(k, k)

    # --------------------------------------------------------------- metadata
    def get_definition(self, metric_id: str) -> MetricDef:
        md = REGISTRY.get(metric_id)
        if md is None:
            raise MetricNotFoundError(f"Không có chỉ số '{metric_id}'. Các chỉ số hợp lệ: {', '.join(sorted(REGISTRY))}")
        return md

    def list_metrics(self) -> list[dict]:
        return [{"id": m.id, "label": m.label, "unit": m.unit, "kind": m.kind, "views": list(m.views), "group_bys": list(m.group_bys)}
                for m in REGISTRY.values()]

    def month_status(self, start: date, end: date) -> tuple[str, list[str]]:
        end = min(end, self.as_of)
        if start > end or not self.last_closed:
            return ("Đã khóa sổ" if self.last_closed else "Không rõ trạng thái khóa sổ", [])
        months = [f"{ym[5:]}/{ym[:4]}" for ym in self._months_between(start, end) if ym > self.last_closed]
        return (f"Tạm tính – chưa khóa sổ ({', '.join(months)})", months) if months else ("Đã khóa sổ", [])

    @staticmethod
    def _months_between(start: date, end: date) -> list[str]:
        out, y, m = [], start.year, start.month
        while (y, m) <= (end.year, end.month):
            out.append(f"{y}-{m:02d}")
            y, m = (y, m + 1) if m < 12 else (y + 1, 1)
        return out

    # ---------------------------------------------------------------- filters
    def resolve_entity(self, kind: str, value: str) -> list[str]:
        """Resolve a code or a (partial, accent-insensitive) name to codes."""
        value = str(value).strip()
        if kind in ("customer", "vendor"):
            ptype = "CUSTOMER" if kind == "customer" else "VENDOR"
            pool = {c: p["name"] for c, p in self.partners.items() if p["type"] == ptype}
        else:
            pool = {"branch": self.branches, "item": self.items, "cost_category": self.cost_categories, "department": self.departments,
                    "salesperson": self.employees, "product_line": self.product_lines}[kind]
        for cand in (value, value.upper()):
            if cand in pool:
                return [cand]
        nv = _norm(value)
        for code, name in pool.items():
            if _norm(code) == nv or _norm(name) == nv:
                return [code]
        stop = {"cong", "ty", "tnhh", "co", "phan", "cp", "mtv", "tap", "doan", "khach", "hang", "nha", "cung", "cap", "chi", "nhanh", "phong"}
        tokens = [t for t in nv.split() if t not in stop] or nv.split()
        scored = []
        for code, name in pool.items():
            nn = _norm(name)
            hit = sum(1 for t in tokens if re.search(rf"\b{re.escape(t)}\b", nn))
            if hit:
                scored.append((hit / len(tokens), code, name))
        scored.sort(key=lambda x: -x[0])
        if not scored or scored[0][0] < 0.5:
            raise FilterError(f"Không tìm thấy {GROUP_LABELS.get(kind, kind)} khớp với '{value}'.")
        best = [s for s in scored if s[0] == scored[0][0]]
        if (len(best) > 1 and scored[0][0] < 1.0) or len(best) > 3:
            raise FilterError(f"'{value}' khớp với nhiều {GROUP_LABELS.get(kind, kind)}; cần chọn rõ một.",
                              [{"code": c, "name": n} for _, c, n in best[:5]])
        return [c for _, c, _ in best]

    def build_filters(self, filters: dict | None, as_of: date, scope_sql: str = '', scope_params: list | None = None) -> tuple[str, list, dict]:
        if not filters:
            return "", [], {}
        unknown = set(filters) - set(FILTER_KEYS)
        if unknown:
            raise FilterError(f"Bộ lọc không hỗ trợ: {', '.join(sorted(unknown))}. Hỗ trợ: {', '.join(FILTER_KEYS)}")
        conds, params, resolved = [], [], {}
        col = {"customer": "partner_code", "vendor": "partner_code", "branch": "branch_code", "product_line": "product_line", "item": "item_code",
               "cost_category": "cost_category", "department": "department_code", "salesperson": "employee_code"}
        for key, val in filters.items():
            if val in (None, "", [], 0, "0"):
                continue
            if key == "exclude_top_customers":
                top = self.q(f"""SELECT partner_code FROM v_mgmt WHERE account_code LIKE '131%' AND posting_date <= ? AND partner_code IS NOT NULL
                                {scope_sql} GROUP BY 1 ORDER BY SUM(net_debit) DESC LIMIT ?""", [as_of] + (scope_params or []) + [int(val)])
                codes = [r[0] for r in top]
            elif key == "exclude_customers":
                codes = [c for v in (val if isinstance(val, list) else [val]) for c in self.resolve_entity("customer", v)]
            else:
                codes = [c for v in (val if isinstance(val, list) else [val]) for c in self.resolve_entity(key, v)]
                dim = "partner" if key in ("customer", "vendor") else {"salesperson": "employee"}.get(key, key)
                resolved[key] = [{"code": c, "name": self.label_for(dim, c)} for c in codes]
                conds.append(f"{col[key]} IN ({', '.join('?' * len(codes))})")
                params += codes
                continue
            resolved[key] = [{"code": c, "name": self.partners[c]["name"]} for c in codes]
            if codes:
                conds.append(f"COALESCE(partner_code, '') NOT IN ({', '.join('?' * len(codes))})")
                params += codes
        return (" AND " + " AND ".join(conds)) if conds else "", params, resolved

    # ------------------------------------------------------------------ core SQL
    def term_cond(self, t: Term) -> str:
        cond = "(" + " OR ".join(f"account_code LIKE '{p}%'" for p in t.prefixes) + ")"
        where = t.where
        if where and self.legacy and "cost_category" in where:
            # legacy ledgers have no expense items: salary = expense lines of journals that credit 334
            where = "journal_id IN (SELECT journal_id FROM v_gl WHERE account_code LIKE '334%' AND credit_amount > 0)"
        if where and self.legacy and "DEPRECIATION" in where:
            where = None
        return f"({cond} AND {where})" if where else cond

    def aggregate(self, terms: tuple[Term, ...], kind: str, start: date, end: date, view: str, fsql: str, fparams: list,
                  group: str | None = None) -> tuple[dict, int, str, list]:
        """Return ({group_key: [term sums]}, entry_count, sql, params)."""
        conds = [self.term_cond(t) for t in terms]
        sums = ", ".join(f"SUM(CASE WHEN {c} THEN {MEASURE_SQL[t.measure]} ELSE 0 END)" for c, t in zip(conds, terms))
        if kind == "flow":
            date_cond, dparams = f"posting_date BETWEEN ? AND ? AND {FLOW_COND}", [start, end]
        else:
            date_cond, dparams = "posting_date <= ?", [end]
        gexpr = GROUP_SQL[group][0] if group else "'__all__'"
        sql = f"SELECT {gexpr} AS k, {sums}, COUNT(*) FROM {VIEW_TABLE[view]} WHERE {date_cond} AND ({' OR '.join(conds)}){fsql} GROUP BY 1"
        params = dparams + fparams
        rows = self.q(sql, params)
        return {r[0]: [float(x or 0) for x in r[1:-1]] for r in rows}, int(sum(r[-1] for r in rows)), sql, params

    @staticmethod
    def combine(terms: tuple[Term, ...], sums: list[float]) -> float:
        return sum(t.coef * s for t, s in zip(terms, sums))

    def linear(self, terms, kind, start, end, view, fsql, fparams, group):
        """Value (+ per-group values) of a linear combination of terms."""
        if kind == "snapshot" and group == "month":
            moves, n, sql, params = self.aggregate(terms, "snapshot", start, end, view, fsql, fparams, "month")
            months = self._months_between(start, end)
            running, out = 0.0, {}
            for ym in sorted(set(moves) | set(months)):
                running += self.combine(terms, moves.get(ym, [0.0] * len(terms)))
                if ym in months:
                    out[ym] = running
            return (out[months[-1]] if months else 0.0), out, n, sql, params
        agg, n, sql, params = self.aggregate(terms, kind, start, end, view, fsql, fparams, group)
        groups = {k: self.combine(terms, v) for k, v in agg.items()}
        if group:
            tot, n, sql, params = self.aggregate(terms, kind, start, end, view, fsql, fparams, None)
            total = self.combine(terms, tot.get("__all__", [0.0] * len(terms)))
        else:
            total = groups.get("__all__", 0.0)
        return total, groups, n, sql, params

    # ------------------------------------------------------------------ compute
    def compute(self, md: MetricDef, start: date, end: date, view: str, fsql: str, fparams: list, group: str | None,
                params: dict) -> dict:
        e = min(end, self.as_of) if start <= self.as_of else end
        if md.kind in ("flow", "snapshot"):
            total, groups, n, sql, sp = self.linear(md.terms, md.kind, start, e, view, fsql, fparams, group)
            return {"value": total, "groups": groups if group else None, "entry_count": n, "sql": sql, "sql_params": sp}
        if md.kind == "ratio":
            num, ng, n1, sql1, _ = self.linear(md.num, md.num_kind, start, e, view, fsql, fparams, group)
            den, dg, n2, sql2, _ = self.linear(md.den, md.den_kind, start, e, view, fsql, fparams, group)
            val = md.scale * num / den if den else None
            groups = {k: (md.scale * ng.get(k, 0.0) / dg[k] if dg.get(k) else None) for k in dg} if group else None
            return {"value": val, "groups": groups, "entry_count": max(n1, n2), "sql": f"{sql1} /* chia */ {sql2}", "sql_params": [],
                    "components": {"numerator": num, "denominator": den}}
        from .custom import CUSTOM  # custom metrics reuse the helpers above
        fn = CUSTOM.get(md.id)
        if fn is None:
            raise MetricUnavailableError(f"Chỉ số {md.id} chưa được cài đặt.")
        return fn(self, md, start, end, view, fsql, fparams, group, params)

    # ------------------------------------------------------------------- public
    def resolve(self, md: MetricDef, period: str | dict | None, params: dict) -> P.Period:
        default = params.get("period_default") or ("today" if md.period_type == "snapshot" else "this_month")
        try:
            if period in (None, "") and default == "all":
                return P.resolve_period({"start_date": "2000-01-01", "end_date": self.as_of.isoformat()}, self.as_of)
            return P.resolve_period(period, self.as_of, default="this_month" if default == "all" else default)
        except P.PeriodError as exc:
            raise InvalidDateRangeError(str(exc)) from exc

    @_validated_request
    def query(self, metric: str, period: str | dict | None = None, compare_to: str | None = None, group_by: str | None = None,
              filters: dict | None = None, view: str | None = None, top_k: int | None = None, params: dict | None = None,
              scope: dict | None = None) -> dict:
        md = self.get_definition(metric)
        if compare_to not in (None,'none','null','previous_period','prev','previous','same_period_last_year','yoy'):
            raise EngineError('compare_to không hợp lệ. Dùng previous_period hoặc same_period_last_year.')
        if params is not None and not isinstance(params,dict) or filters is not None and not isinstance(filters,dict):
            raise EngineError('params và filters phải là ánh xạ.')
        if view is not None and not isinstance(view,str):
            raise ViewNotAllowedError('Khung dữ liệu phải là mgmt hoặc tax.')
        params = {**md.params, **{k: v for k, v in (params or {}).items() if v is not None}}
        view = (view or md.default_view).lower()
        view = {"v_mgmt": "mgmt", "quan_tri": "mgmt", "management": "mgmt", "v_tax": "tax", "thue": "tax"}.get(view, view)
        if view not in md.views:
            names = " / ".join("quản trị" if v == "mgmt" else "thuế" for v in md.views)
            raise ViewNotAllowedError(f"Chỉ số '{md.label}' chỉ tính trên khung {names}; không dùng view '{view}'.")
        group_by = group_by or params.get("group_by")
        if group_by in ("none", "", "null"):
            group_by = None
        if group_by and group_by not in md.group_bys:
            raise EngineError(f"Chỉ số '{md.label}' không hỗ trợ nhóm theo '{group_by}'. Hỗ trợ: {', '.join(md.group_bys) or 'không có'}.")
        per = self.resolve(md, period, params)
        if top_k is not None and (isinstance(top_k,bool) or not isinstance(top_k,int) or not 1 <= top_k <= 100_000):
            raise EngineError('top_k phải là số nguyên từ 1 đến 100000.')
        comparable_custom = {'dso','dpo','dio','cash_conversion_cycle','dso_actual','cash_coverage_days',
                             'cash_flow_breakdown','ar_aging','overdue_receivables','expense_spikes',
                             'payroll_summary','cit_estimate','mgmt_vs_tax_gap','vat_position'}
        if compare_to and compare_to not in ('none','null') and md.kind=='custom' and md.id not in comparable_custom:
            raise EngineError(f"Chỉ số '{md.label}' chưa hỗ trợ so sánh kỳ.")
        from .scope import compile_scope
        ssql,sparams,canonical_scope = compile_scope(self,md,scope)
        fsql, fparams, resolved = self.build_filters(filters, min(per.end, self.as_of),ssql,sparams)
        fsql, fparams = fsql+ssql, fparams+sparams
        params["_resolved"] = resolved
        params["_top_k"] = top_k
        res = self.compute(md, per.start, per.end, view, fsql, fparams, group_by, params)
        out = self._package(md, per, view, res, group_by, top_k, resolved)
        identity = {'data_version':self.info.get('data_version','unversioned'), 'seed':self.info.get('seed'),
                    'data_through':str(self.as_of),'closed':self.last_closed,'metric':metric,'period':per.as_dict(),
                    'view':view,'filters':resolved,'scope':canonical_scope,'params':params,'group_by':group_by,
                    'top_k':top_k,'compare_to':compare_to}
        out['audit_trail']['lineage_id'] = 'L-'+hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:20]
        out['audit_trail']['data_version'] = self.info.get('data_version','unversioned')
        if scope is not None:
            out['scope'] = canonical_scope
        if compare_to and compare_to not in ("none", "null") and res.get("value") is not None:
            out["comparison"] = self._compare(md, per, view, fsql, fparams, compare_to, out["value"], params)
        return out

    def _compare(self, md, per, view, fsql, fparams, mode, current, params) -> dict:
        if mode in ("previous_period", "prev", "previous"):
            cmp = P.previous_period(per)
        elif mode in ("same_period_last_year", "yoy"):
            cmp = P.same_period_last_year(per)
        else:
            raise EngineError(f"compare_to không hợp lệ: {mode}. Dùng previous_period hoặc same_period_last_year.")
        note, full = None, None
        if md.period_type == "flow":
            like = P.comparable_partial(per, cmp, self.as_of)
            if like.end != cmp.end:
                note = f"Kỳ hiện tại mới có dữ liệu đến {self.as_of:%d/%m/%Y} nên so sánh cùng số ngày với {like.label}."
                full = self.compute(md, cmp.start, cmp.end, view, fsql, fparams, None, params)["value"]
                cmp = like
        prev = self.compute(md, cmp.start, cmp.end, view, fsql, fparams, None, params)["value"]
        delta = None if prev is None or current is None else current - prev
        pct = None if not prev or delta is None or md.unit == "%" else delta / abs(prev) * 100
        out = {"period": {"start_date": cmp.start.isoformat(), "end_date": cmp.end.isoformat(), "label": cmp.label},
               "value": prev, "display": fmt_value(prev, md.unit), "delta": delta, "delta_display": fmt_delta(delta, md.unit),
               "delta_pct": pct, "delta_pct_display": None if pct is None else fmt_delta(pct, "%").replace(" điểm %", "%"),
               "direction": None if delta is None else ("tăng" if delta > 0 else "giảm" if delta < 0 else "không đổi")}
        if note:
            out["note"] = note
            out["full_period_value"] = full
            out["full_period_display"] = fmt_value(full, md.unit)
        return out

    def _package(self, md, per, view, res, group_by, top_k, resolved) -> dict:
        eff_end = min(per.end, self.as_of)
        status, _ = self.month_status(per.start if md.period_type == "flow" else eff_end, eff_end)
        value = res.get("value")
        lineage = "L-" + hashlib.sha1(f"{md.id}|{per.start}|{per.end}|{view}|{resolved}".encode()).hexdigest()[:10]
        out: dict[str, Any] = {
            "metric_id": md.id, "metric_name": md.label, "value": value, "unit": md.unit, "display": fmt_value(value, md.unit),
            "period": {"type": md.period_type, "start_date": per.start.isoformat(), "end_date": per.end.isoformat()},
            "period_label": per.label if md.period_type == "flow" else f"tại ngày {eff_end:%d/%m/%Y}",
            "view": view, "view_label": "Quản trị (toàn bộ giao dịch)" if view == "mgmt" else "Thuế (chỉ chứng từ/chi phí được trừ)",
            "data_status": status, "data_through": self.as_of.isoformat(),
            "audit_trail": {"accounts_involved": list(md.accounts), "entry_count": int(res.get("entry_count", 0)),
                            "as_of_date": (eff_end if per.start <= self.as_of else per.end).isoformat(),
                            "formula": md.formula, "source": "v_mgmt" if view == "mgmt" else "v_tax", "lineage_id": lineage},
        }
        notes = []
        if per.end > self.as_of >= per.start and md.period_type == "flow":
            notes.append(f"Kỳ {per.label} chưa kết thúc: số liệu lũy kế đến {self.as_of:%d/%m/%Y}.")
        if per.start > self.as_of and md.period_type == "flow" and md.id != "upcoming_obligations":
            notes.append(f"Kỳ {per.label} chưa có dữ liệu (dữ liệu đến {self.as_of:%d/%m/%Y}).")
        notes += res.get("notes") or []
        if notes:
            out["notes"] = notes
        if resolved:
            out["filters"] = resolved
        if res.get("components"):
            out["components"] = {k: {"value": v, "display": fmt_value(v, "VND")} for k, v in res["components"].items()}
        for k in ("summary",):
            if res.get(k):
                out[k] = res[k]
        rows = res.get("rows")
        if res.get("groups") is not None and group_by:
            dim = GROUP_SQL[group_by][1]
            rows = [{"key": k, "label": self.label_for(dim, k) if dim else k, "value": v} for k, v in res["groups"].items()]
            rows.sort(key=(lambda r: str(r["key"])) if group_by in ("month", "quarter", "year") else (lambda r: (-(r["value"] or 0),str(r['key']))))
            for r in rows:
                r["display"] = fmt_value(r["value"], md.unit)
                if md.unit == "VND" and md.kind != "ratio" and value:
                    r["share_pct"] = round(100 * (r["value"] or 0) / value, 1)
            out["group_by"] = group_by
        if rows is not None:
            limit = top_k or (len(rows) if group_by in ("month", "quarter", "year") else 15)
            out["rows_total"] = len(rows)
            out["rows"] = rows[:limit]
            if len(rows) > limit:
                out.setdefault("notes", []).append(f"Hiển thị {limit}/{len(rows)} dòng lớn nhất.")
        out["_sql"] = res.get("sql")
        out["_sql_params"] = [str(p) for p in res.get("sql_params", [])]
        return out

    # ------------------------------------------------------------------ v0 API
    def get_metric(self, metric_id: str, start_date: str, end_date: str) -> dict:
        self.get_definition(metric_id)
        s, e = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if s > e:
            raise InvalidDateRangeError(f"Khoảng thời gian không hợp lệ: {start_date} > {end_date}")
        rng = {"start_date": start_date, "end_date": end_date}
        res = self.query(metric_id, rng, top_k=100_000)
        if metric_id in ("ar_by_customer", "ap_by_vendor"):
            ptype = "CUSTOMER" if metric_id == "ar_by_customer" else "VENDOR"
            balances = {c: 0.0 for c, p in self.partners.items() if p["type"] == ptype}
            for r in res.get("rows", []):
                if r["key"] is not None:
                    balances[r["key"]] = r["value"]
            res["value"] = balances
        res["audit_trail"]["as_of_date"] = e.isoformat()
        res.pop("_sql", None)
        res.pop("_sql_params", None)
        return res

    # --------------------------------------------------------------- lineage
    @_validated_request
    def explain(self, metric: str, period: str | dict | None = None, filters: dict | None = None, view: str | None = None,
                limit: int = 10, scope: dict | None = None) -> dict:
        """'Xem cách tính': formula + per-account totals + the largest GL lines behind a metric."""
        md = self.get_definition(metric)
        view = view or md.default_view
        if view not in md.views:
            raise ViewNotAllowedError(f"Chỉ số '{md.label}' không hỗ trợ khung '{view}'.")
        if isinstance(limit,bool) or not isinstance(limit,int) or not 1 <= limit <= 1000:
            raise EngineError('limit phải là số nguyên từ 1 đến 1000.')
        per = self.resolve(md, period, md.params)
        from .scope import compile_scope
        ssql,sparams,_ = compile_scope(self,md,scope)
        fsql, fparams, resolved = self.build_filters(filters, min(per.end, self.as_of),ssql,sparams)
        fsql,fparams = fsql+ssql,fparams+sparams
        terms = md.terms or (md.num + md.den)
        base = {"metric_id": md.id, "metric_name": md.label, "formula": md.formula, "accounts": list(md.accounts), "period_label": per.label}
        if not terms:
            return {**base, "note": "Chỉ số tổng hợp từ sổ chi tiết; bảng kết quả của chỉ số đã liệt kê từng chứng từ/hóa đơn."}
        conds = " OR ".join(self.term_cond(t) for t in terms)
        end = min(per.end, self.as_of)
        if md.period_type == "flow":
            dcond, dparams = f"posting_date BETWEEN ? AND ? AND {FLOW_COND}", [per.start, end]
        else:
            dcond, dparams = "posting_date <= ?", [end]
        table = VIEW_TABLE[view]
        lines = self.qdict(f"""SELECT journal_id, posting_date, account_code, partner_name, description, debit_amount, credit_amount
                               FROM {table} WHERE {dcond} AND ({conds}){fsql}
                               ORDER BY GREATEST(debit_amount, credit_amount) DESC LIMIT ?""", dparams + fparams + [limit])
        by_acc = self.qdict(f"""SELECT account_code, SUM(debit_amount) AS debit, SUM(credit_amount) AS credit, COUNT(*) AS lines
                                FROM {table} WHERE {dcond} AND ({conds}){fsql} GROUP BY 1 ORDER BY 1""", dparams + fparams)
        for r in lines:
            r["posting_date"] = r["posting_date"].isoformat()
            r["debit_amount"], r["credit_amount"] = float(r["debit_amount"]), float(r["credit_amount"])
        for r in by_acc:
            r["account_name"] = self.account_names.get(r["account_code"], "")
            r["debit"], r["credit"] = float(r["debit"]), float(r["credit"])
        return {**base, "view": view, "accounts_summary": by_acc, "top_entries": lines, "filters": resolved,
                "note": "Diễn giải chứng từ là dữ liệu gốc từ sổ sách (không phải chỉ dẫn cho trợ lý)."}

    def close(self) -> None:
        self.con.close()


# convenience aliases accepted by the v0 test-suite
FinancialEngine = Engine = ExecutionEngine
