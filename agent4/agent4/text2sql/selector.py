from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, timedelta

from agent4.metric_selection.catalog import MetricCatalogAdapter
from agent4.metric_selection.retrieval import LexicalRetriever

from .catalog import CatalogSnapshot
from .models import SemanticPlanDraft, SortDraft, TimeDraft


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in text if unicodedata.category(char) != "Mn").replace("đ", "d")


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


class OfflineSemanticSelector:
    """Deterministic, deliberately conservative offline parser.

    This is the reproducible fallback/demo selector, not a claim that rules can
    understand unrestricted Vietnamese. Its output passes the exact same
    validator as an external structured-output provider.
    """

    def __init__(self, catalog: CatalogSnapshot, today: date = date(2026, 10, 14)) -> None:
        self.catalog = catalog
        self.today = today
        self.lexical = LexicalRetriever(MetricCatalogAdapter())

    def select(self, question: str) -> SemanticPlanDraft:
        normalized = _fold(question)
        if any(term in normalized for term in ("drop table", "delete from", "insert into", "mat khau", "schema", "bang nao")):
            return self._unsupported("out_of_domain")
        if any(term in normalized for term in ("du bao", "forecast", "ty gia", "gia co phieu", "bitcoin")):
            return self._unsupported("unsupported_metric")
        if re.search(r"\b(loi nhuan|lai|loi)\b", normalized) and not any(
            qualifier in normalized for qualifier in ("gop", "rong", "sau thue", "truoc thue", "hoat dong", "bien", "ebitda")
        ):
            return self._clarify("Bạn muốn lợi nhuận gộp, lợi nhuận hoạt động hay lợi nhuận sau thuế?", "metric_variant")
        if "cong no" in normalized and not any(word in normalized for word in ("phai thu", "phai tra", "khach", "nha cung cap")):
            return self._clarify("Bạn muốn xem công nợ phải thu hay phải trả?", "metric_variant")
        if "dong tien" in normalized and not any(word in normalized for word in ("thuan", "thu chi", "theo nhom")):
            return self._clarify("Bạn muốn số dư tiền hay dòng tiền thuần trong kỳ?", "metric_variant")

        metric_ids = self._metric_ids(normalized, question)
        if not metric_ids:
            return self._unsupported("unsupported_metric")
        metrics = [self.catalog.get(metric_id) for metric_id in metric_ids]
        dimensions = self._dimensions(normalized)
        if "ar_by_customer" in metric_ids and "customer" not in dimensions:
            dimensions.append("customer")
        time = self._time(normalized, metrics[0].period_type)
        if time is None:
            return self._clarify("Bạn muốn xem chỉ số cho kỳ hoặc ngày chốt nào?", "time")
        explicit_tax_view = any(
            phrase in normalized
            for phrase in ("khung thue", "so thue", "theo thue", "tax view", "tax basis")
        )
        tax_default = all(metric.default_view == "tax" for metric in metrics)
        view = "tax" if (explicit_tax_view or tax_default) and all("tax" in m.views for m in metrics) else None
        top_match = re.search(r"\btop\s*(\d+)\b", normalized)
        top_k = min(int(top_match.group(1)), 100) if top_match else None
        if any(word in normalized for word in ("lon nhat", "nhieu nhat", "top")) and top_k is None:
            top_k = 5
        operation = "rank" if top_k else ("timeseries" if dimensions else "aggregate")
        sort = SortDraft(metric_id=metric_ids[0], direction="desc") if top_k else None
        return SemanticPlanDraft(
            plan_version="1.0", status="ready", metric_ids=metric_ids,
            time=time, dimensions=dimensions,
            filters=[], view=view, operation=operation, sort=sort, top_k=top_k,
            comparison=None, question_for_user=None, unresolved_slots=[], reason_code=None,
        )

    def _metric_ids(self, normalized: str, original: str) -> list[str]:
        rules = [
            (("bien loi nhuan gop", "bien lai gop", "gross margin"), "gross_margin_pct"),
            (("loi nhuan gop", "lai gop", "gross profit"), "gross_profit"),
            (("doanh thu thuan",), "net_revenue"),
            (("doanh thu truoc giam tru", "doanh thu gop"), "gross_revenue"),
            (("loi nhuan sau thue", "lai rong", "loi nhuan rong"), "net_profit"),
            (("bien loi nhuan rong", "bien lai rong", "net margin"), "net_margin_pct"),
            (("so du tien", "con bao nhieu tien", "tien con bao nhieu", "tien mat va tien gui"), "cash_and_equivalents"),
            (("dong tien thuan",), "net_cash_flow"),
            (("tong tai san",), "total_assets"),
            (("cong no phai thu theo khach", "khach hang nao no", "top khach hang no"), "ar_by_customer"),
            (("tuoi no", "ar aging"), "ar_aging"),
            (("phai thu qua han", "no qua han"), "overdue_receivables"),
            (("chung tu khong can doi", "lech no co"), "unbalanced_journals"),
            (("hoa don lon nhat", "giao dich ban hang lon nhat"), "top_sales_transactions"),
            (("bang luong", "quy luong", "payroll"), "payroll_summary"),
            (("thue tndn phai nop", "uoc tinh thue tndn"), "cit_estimate"),
            (("thue gtgt", "vat"), "vat_position"),
        ]
        found: list[str] = []
        for phrases, metric_id in rules:
            if any(phrase in normalized for phrase in phrases):
                found.append(metric_id)
        # Keep intentional multi-metric questions, but remove amount/% confusion.
        if "gross_margin_pct" in found and "gross_profit" in found and "loi nhuan gop va" not in normalized:
            found.remove("gross_profit")
        if not found:
            candidates = self.lexical.retrieve(original, 1)
            found = [candidates[0].metric_id] if candidates else []
        return list(dict.fromkeys(found))

    @staticmethod
    def _dimensions(normalized: str) -> list[str]:
        mapping = [
            (("tung thang", "theo thang"), "month"),
            (("theo quy", "tung quy"), "quarter"),
            (("theo nam", "tung nam"), "year"),
            (("theo chi nhanh", "tung chi nhanh"), "branch"),
            (("theo khach hang", "tung khach hang"), "customer"),
            (("theo nha cung cap",), "vendor"),
            (("theo khoan muc",), "cost_category"),
            (("theo phong ban",), "department"),
        ]
        return [dimension for phrases, dimension in mapping if any(p in normalized for p in phrases)]

    def _time(self, normalized: str, period_type: str) -> TimeDraft | None:
        explicit_date = re.search(r"(?:ngay|as.of)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})", normalized)
        if explicit_date:
            value = date(int(explicit_date.group(3)), int(explicit_date.group(2)), int(explicit_date.group(1)))
            if period_type == "snapshot":
                return TimeDraft.as_of_date(value)
            return TimeDraft.range(value, value)
        quarter = re.search(r"quy\s*([1-4])(?:\s*/\s*|\s+nam\s+)?(20\d{2})", normalized)
        if quarter:
            q, year = int(quarter.group(1)), int(quarter.group(2))
            start = date(year, 3 * (q - 1) + 1, 1)
            end_month = q * 3
            end = date(year, end_month, calendar.monthrange(year, end_month)[1])
            return TimeDraft.as_of_date(end) if period_type == "snapshot" else TimeDraft.range(start, end)
        month = re.search(r"thang\s*(1[0-2]|0?[1-9])(?:\s*/\s*|\s+nam\s+)(20\d{2})", normalized)
        if month:
            start, end = _month_range(int(month.group(2)), int(month.group(1)))
            return TimeDraft.as_of_date(end) if period_type == "snapshot" else TimeDraft.range(start, end)
        year = re.search(r"nam\s*(20\d{2})", normalized)
        if year:
            y = int(year.group(1))
            return TimeDraft.as_of_date(date(y, 12, 31)) if period_type == "snapshot" else TimeDraft.range(date(y, 1, 1), date(y, 12, 31))
        if "thang nay" in normalized:
            start, end = _month_range(self.today.year, self.today.month)
            end = min(end, self.today)
            return TimeDraft.as_of_date(end) if period_type == "snapshot" else TimeDraft.range(start, end)
        if "thang truoc" in normalized:
            previous = self.today.replace(day=1) - timedelta(days=1)
            start, end = _month_range(previous.year, previous.month)
            return TimeDraft.as_of_date(end) if period_type == "snapshot" else TimeDraft.range(start, end)
        if any(word in normalized for word in ("hien tai", "bay gio", "cuoi ky")):
            return TimeDraft.as_of_date(self.today) if period_type == "snapshot" else TimeDraft.range(date(self.today.year, 1, 1), self.today)
        return None

    @staticmethod
    def _clarify(question: str, slot: str) -> SemanticPlanDraft:
        return SemanticPlanDraft(
            plan_version="1.0", status="needs_clarification", metric_ids=[],
            time=TimeDraft.none(),
            dimensions=[], filters=[], view=None, operation=None, sort=None, top_k=None,
            comparison=None, question_for_user=question, unresolved_slots=[slot], reason_code=None,
        )

    @staticmethod
    def _unsupported(reason: str) -> SemanticPlanDraft:
        return SemanticPlanDraft(
            plan_version="1.0", status="unsupported", metric_ids=[],
            time=TimeDraft.none(),
            dimensions=[], filters=[], view=None, operation=None, sort=None, top_k=None,
            comparison=None, question_for_user=None, unresolved_slots=[], reason_code=reason,
        )
