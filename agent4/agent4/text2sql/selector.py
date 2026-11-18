from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, timedelta

from agent4.metric_selection.catalog import MetricCatalogAdapter
from agent4.metric_selection.retrieval import LexicalRetriever

from .catalog import CatalogSnapshot
from .models import FilterDraft, SemanticPlanDraft, SortDraft, TimeDraft


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in text if unicodedata.category(char) != "Mn").replace("đ", "d")


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _quarter_range(year: int, quarter: int) -> tuple[date, date]:
    start_month = 3 * (quarter - 1) + 1
    end_month = 3 * quarter
    return date(year, start_month, 1), date(
        year, end_month, calendar.monthrange(year, end_month)[1]
    )


_BRANCH_VOCAB: dict[str, str] = {
    "HN": r"ha noi",
    "HCM": r"(?:tp\.?\s*)?ho chi minh(?: city)?|tp\.?\s*hcm|sai gon",
    "DN": r"da nang",
    "HP": r"hai phong",
    "BD": r"binh duong",
    "CT": r"can tho",
    "NA": r"nghe an",
}
_DEPT_VOCAB: dict[str, str] = {
    "BGD": r"ban giam doc|executive(?:\s+board)?",
    "KD": r"kinh doanh|sales",
    "MKT": r"marketing",
    "KT": r"ky thuat(?:\s*-\s*dich vu)?|technical(?:\s+services)?",
    "KHO": r"kho van|logistics|warehouse",
    "TCKT": r"tai chinh(?:\s*-\s*)?ke toan|finance(?:\s+and\s+accounting)?",
    "HCNS": r"(?:hanh chinh(?:\s*-\s*)?)?nhan su|hcns|human resources|hr",
    "IT": r"cntt|cong nghe(?:\s+thong tin)?|information technology",
    "CSKH": r"cham soc khach hang|cskh|customer (?:service|support|care)",
    "MH": r"mua hang|thu mua|cung ung|procurement|purchasing",
    "KSNB": r"kiem soat noi bo|kiem toan noi bo|ksnb|internal (?:control|audit)",
}
_PRODUCT_LINE_VOCAB: dict[str, str] = {
    "IT": r"thiet bi cntt",
    "OFF": r"thiet bi van phong",
    "CON": r"vat tu tieu hao",
    "SVC": r"dich vu ky thuat",
}
_COST_CATEGORY_VOCAB: dict[str, str] = {
    "BAOHIEM_TS": r"bao hiem tai san|property insurance",
    "DIEN_NUOC": r"(?:tien )?dien(?:,| va)? nuoc|utilities",
    "LUONG": r"luong|salaries",
    "BAOHIEM": r"bao hiem|insurance",
    "THUONG": r"thuong|bonuses",
    "THUE_MB": r"thue mat bang|rent",
    "VIENTHONG": r"vien thong|telecom",
    "MARKETING": r"quang cao|marketing",
    "VANCHUYEN": r"van chuyen|shipping",
    "CONGTAC": r"cong tac phi|business travel",
    "TIEPKHACH": r"tiep khach",
    "KHAUHAO": r"khau hao|depreciation",
    "PHANMEM": r"phan mem|software",
    "VPP": r"van phong pham|office supplies",
    "PHI_NH": r"phi ngan hang|bank fees",
    "DUPHONG": r"du phong no kho doi",
    "VATTU_DV": r"vat tu phuc vu dich vu",
    "THUE_PHI": r"thue, phi, le phi",
    "KHAC": r"chi phi khac",
}
_CUSTOMER_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:C[0-9]{6}|KH[0-9]{4,7}|KHLE-(?:HN|HCM|DN|HP|BD|CT|NA))(?![A-Za-z0-9_-])"
)
_VENDOR_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:V[0-9]{6}|NCC-[A-Z0-9]{2,12}(?:-[A-Z0-9]{2,12}){0,3})(?![A-Za-z0-9_-])"
)
_HARDWARE_HP_RE = re.compile(
    r"\b(?:laptop|may\s+in|may\s+tinh|may\s+chu|muc(?:\s+in)?|pc)\s+HP\b", re.IGNORECASE
)


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
        if any(
            term in normalized
            for term in (
                "drop table",
                "delete from",
                "insert into",
                "mat khau",
                "schema",
                "bang nao",
            )
        ):
            return self._unsupported("out_of_domain")
        if any(
            term in normalized
            for term in ("du bao", "forecast", "ty gia", "gia co phieu", "bitcoin")
        ):
            return self._unsupported("unsupported_metric")
        if re.search(r"\b(loi nhuan|lai|loi)\b", normalized) and not any(
            qualifier in normalized
            for qualifier in (
                "gop",
                "rong",
                "sau thue",
                "truoc thue",
                "hoat dong",
                "bien",
                "ebitda",
            )
        ):
            return self._clarify(
                "Bạn muốn lợi nhuận gộp, lợi nhuận hoạt động hay lợi nhuận sau thuế?",
                "metric_variant",
            )
        if "cong no" in normalized and not any(
            word in normalized for word in ("phai thu", "phai tra", "khach", "nha cung cap")
        ):
            return self._clarify("Bạn muốn xem công nợ phải thu hay phải trả?", "metric_variant")
        if "dong tien" in normalized and not any(
            word in normalized for word in ("thuan", "thu chi", "theo nhom")
        ):
            return self._clarify(
                "Bạn muốn số dư tiền hay dòng tiền thuần trong kỳ?", "metric_variant"
            )

        metric_ids = self._metric_ids(normalized, question)
        if not metric_ids:
            return self._unsupported("unsupported_metric")
        if self._requests_comparison(normalized, metric_ids):
            return self._unsupported("unsupported_comparison")
        metrics = [self.catalog.get(metric_id) for metric_id in metric_ids]
        dimensions = self._dimensions(normalized)
        if "ar_by_customer" in metric_ids and "customer" not in dimensions:
            dimensions.append("customer")
        filters, filter_error = self._extract_filters(normalized, question)
        if filter_error == "unsupported_filter":
            return self._unsupported("unsupported_filter")
        if filter_error == "needs_clarification":
            return self._clarify(
                "Bạn vui lòng cho biết mã hoặc tên chuẩn của chi nhánh, phòng ban hoặc đối tác cần lọc?",
                "filters",
            )
        time = self._time(normalized, metrics[0].period_type)
        if time is None:
            return self._clarify("Bạn muốn xem chỉ số cho kỳ hoặc ngày chốt nào?", "time")
        explicit_tax_view = any(
            phrase in normalized
            for phrase in ("khung thue", "so thue", "theo thue", "tax view", "tax basis")
        )
        tax_default = all(metric.default_view == "tax" for metric in metrics)
        view = (
            "tax"
            if (explicit_tax_view or tax_default) and all("tax" in m.views for m in metrics)
            else None
        )
        top_match = re.search(r"\btop\s*(\d+)\b", normalized)
        top_k = min(int(top_match.group(1)), 100) if top_match else None
        if any(word in normalized for word in ("lon nhat", "nhieu nhat", "top")) and top_k is None:
            top_k = 5
        operation = "rank" if top_k else ("timeseries" if dimensions else "aggregate")
        sort = SortDraft(metric_id=metric_ids[0], direction="desc") if top_k else None
        return SemanticPlanDraft(
            plan_version="1.0",
            status="ready",
            metric_ids=metric_ids,
            time=time,
            dimensions=dimensions,
            filters=filters,
            view=view,
            operation=operation,
            sort=sort,
            top_k=top_k,
            comparison=None,
            question_for_user=None,
            unresolved_slots=[],
            reason_code=None,
        )

    @classmethod
    def _requests_comparison(cls, normalized: str, metric_ids: list[str]) -> bool:
        cleaned = normalized
        if metric_ids == ["budget_vs_actual"]:
            cleaned = re.sub(r"\b(?:so voi ke hoach|budget vs actual)\b", " ", cleaned)
        elif metric_ids == ["mgmt_vs_tax_gap"]:
            cleaned = re.sub(
                r"\b(?:chenh lech (?:thue va quan tri|quan tri va thue|hai khung)|management vs tax gap)\b",
                " ",
                cleaned,
            )
        elif metric_ids == ["expense_spikes"]:
            cleaned = re.sub(r"\bso voi binh quan 3 thang\b", " ", cleaned)
        if not re.search(
            r"\b(?:so sanh|so voi|cung ky|versus|vs|compare|compared (?:to|with)|"
            r"year[- ]over[- ]year|yoy|qoq|mom|tang truong|tang hay giam|chenh bao nhieu)\b",
            cleaned,
        ):
            return False
        dims = set(cls._dimensions(cleaned))
        grouped_range = (
            bool(re.search(r"\b(?:between|giua)\b", cleaned))
            and bool(dims.intersection({"month", "quarter", "year"}))
            and not re.search(
                r"\b(?:change|growth|difference|delta|increase|decrease|percent(?:age)?|"
                r"chenh|thay doi|tang truong|tang|giam|phan tram|so voi|cung ky)\b",
                cleaned,
            )
        )
        return not grouped_range

    @staticmethod
    def _make_filter(field: str, values: list[str]) -> FilterDraft:
        deduped = list(dict.fromkeys(values))
        return FilterDraft(
            field=field,
            operator="eq" if len(deduped) == 1 else "in",
            values=deduped,
        )

    @classmethod
    def _extract_filters(
        cls, normalized: str, original: str
    ) -> tuple[list[FilterDraft], str | None]:
        filters: list[FilterDraft] = []
        folded_original = unicodedata.normalize("NFKC", original)

        # 1. Branches (all 7 MPX10 branches)
        branches: list[str] = []
        branch_terms = "|".join(
            f"(?P<{code}>{code.lower()}|{alias})"
            for code, alias in sorted(_BRANCH_VOCAB.items(), key=lambda p: -len(p[1]))
        )
        for m in re.finditer(r"\b(?:chi nhanh|branch(?:es)?)(?:\s*[:=]|\s)\s*", normalized):
            rest = normalized[m.end() :]
            while vm := re.match(rf"(?:{branch_terms})(?![a-z0-9_-])", rest):
                branches.append(vm.lastgroup)
                sep = re.match(r"\s*,\s*|\s+(?:va|hoac|and|or)\s+", rest[vm.end() :])
                if sep is None:
                    break
                rest = rest[vm.end() + sep.end() :]
        for code, alias in _BRANCH_VOCAB.items():
            if re.search(rf"\b(?:{alias})\b", normalized):
                branches.append(code)
                continue
            if code == "HP" and _HARDWARE_HP_RE.search(normalized):
                continue
            if code == "NA":
                if re.search(r"(?<![\w/-])NA(?![\w/-])", folded_original):
                    branches.append(code)
            elif re.search(rf"(?<![\w-]){code}(?![\w-])", folded_original):
                branches.append(code)
        if branches:
            filters.append(cls._make_filter("branch", branches))
        elif re.search(
            r"(?<!\btheo )(?<!\btung )\b(?:chi nhanh|branch)\s+(?!nao\b|trong\b|nam\b|quy\b|thang\b)[a-z0-9_-]+",
            normalized,
        ):
            return [], "needs_clarification"

        # 2. Departments (all 11 MPX10 departments; IT requires department marker)
        depts: list[str] = []
        dept_terms = "|".join(
            f"(?P<{code}>{code.lower()}|{alias})"
            for code, alias in sorted(_DEPT_VOCAB.items(), key=lambda p: -len(p[1]))
        )
        for m in re.finditer(
            r"\b(?:phong ban|phong|bo phan|departments?)(?:\s*[:=]|\s)\s*", normalized
        ):
            rest = normalized[m.end() :]
            while vm := re.match(rf"(?:{dept_terms})(?![a-z0-9_-])", rest):
                depts.append(vm.lastgroup)
                sep = re.match(r"\s*,\s*|\s+(?:va|hoac|and|or)\s+", rest[vm.end() :])
                if sep is None:
                    break
                rest = rest[vm.end() + sep.end() :]
        for code in ("BGD", "TCKT", "HCNS", "CSKH", "KSNB"):
            if re.search(rf"(?<![\w-]){code}(?![\w-])", folded_original):
                depts.append(code)
        if depts:
            filters.append(cls._make_filter("department", depts))
        elif re.search(
            r"(?<!\btheo )(?<!\btung )\b(?:phong ban|phong|bo phan|department)\s+(?!nao\b|ban\b|trong\b|nam\b|quy\b|thang\b)[a-z0-9_-]+",
            normalized,
        ):
            return [], "needs_clarification"

        # 3. Product lines
        lines: list[str] = []
        line_terms = "|".join(
            f"(?P<{code}>{code.lower()}|{alias})"
            for code, alias in sorted(_PRODUCT_LINE_VOCAB.items(), key=lambda p: -len(p[1]))
        )
        for m in re.finditer(
            r"\b(?:dong san pham|nhom san pham|product lines?)(?:\s*[:=]|\s)\s*", normalized
        ):
            rest = normalized[m.end() :]
            while vm := re.match(rf"(?:{line_terms})(?![a-z0-9_-])", rest):
                lines.append(vm.lastgroup)
                sep = re.match(r"\s*,\s*|\s+(?:va|hoac|and|or)\s+", rest[vm.end() :])
                if sep is None:
                    break
                rest = rest[vm.end() + sep.end() :]
        if re.search(r"\bthiet bi cntt\b", normalized):
            lines.append("IT")
        for code in ("OFF", "CON", "SVC"):
            if re.search(rf"(?<![\w-]){code}(?![\w-])", folded_original):
                lines.append(code)
        if lines:
            filters.append(cls._make_filter("product_line", lines))
        elif re.search(
            r"(?<!\btheo )(?<!\btung )\b(?:dong san pham|nhom san pham|product line)\s+(?!nao\b)[a-z0-9_-]+",
            normalized,
        ):
            return [], "needs_clarification"

        # 4. Cost categories (explicit khoan muc marker)
        cats: list[str] = []
        cat_terms = "|".join(
            f"(?P<{code}>{code.lower()}|{alias})"
            for code, alias in sorted(_COST_CATEGORY_VOCAB.items(), key=lambda p: -len(p[1]))
        )
        for m in re.finditer(
            r"\b(?:khoan muc(?: chi phi)?|cost categor(?:y|ies))(?:\s*[:=]|\s)\s*", normalized
        ):
            rest = normalized[m.end() :]
            while vm := re.match(rf"(?:{cat_terms})(?![a-z0-9_-])", rest):
                cats.append(vm.lastgroup)
                sep = re.match(r"\s*,\s*|\s+(?:va|hoac|and|or)\s+", rest[vm.end() :])
                if sep is None:
                    break
                rest = rest[vm.end() + sep.end() :]
        if cats:
            filters.append(cls._make_filter("cost_category", cats))
        elif re.search(
            r"(?<!\btheo )(?<!\btung )\b(?:khoan muc(?: chi phi)?|cost category)\s+(?!nao\b|chi\b)[a-z0-9_-]+",
            normalized,
        ):
            return [], "needs_clarification"

        # 5. Customer & Vendor partner codes
        upper_orig = folded_original.upper()
        customers = _CUSTOMER_CODE_RE.findall(upper_orig)
        vendors = _VENDOR_CODE_RE.findall(upper_orig)
        if customers:
            filters.append(cls._make_filter("customer", customers))
        elif re.search(
            r"(?<!\btheo )(?<!\btung )(?<!\btop )(?<!\bcong no )(?<!\bphai thu )\b(?:cua\s+)?khach hang\s+(?!nao\b|lon\b|no\b|qua\b|trong\b|nam\b|quy\b|thang\b)[a-z0-9_-]+",
            normalized,
        ):
            return [], "needs_clarification"
        if vendors:
            filters.append(cls._make_filter("vendor", vendors))
        elif re.search(
            r"(?<!\btheo )(?<!\btung )(?<!\btop )(?<!\bphai tra )(?<!\bno )\b(?:cua\s+)?nha cung cap\s+(?!nao\b|lon\b|trong\b|nam\b|quy\b|thang\b)[a-z0-9_-]+",
            normalized,
        ):
            return [], "needs_clarification"

        if filters and re.search(
            r"\b(?:ngoai tru|khong (?:bao gom|gom|tinh)|except|exclude|excluding|without)\b",
            normalized,
        ):
            return [], "unsupported_filter"
        return filters, None

    def _metric_ids(self, normalized: str, original: str) -> list[str]:
        rules = [
            (("bien loi nhuan gop", "bien lai gop", "gross margin"), "gross_margin_pct"),
            (("loi nhuan gop", "lai gop", "gross profit"), "gross_profit"),
            (("doanh thu thuan",), "net_revenue"),
            (("doanh thu truoc giam tru", "doanh thu gop"), "gross_revenue"),
            (("loi nhuan sau thue", "lai rong", "loi nhuan rong"), "net_profit"),
            (("bien loi nhuan rong", "bien lai rong", "net margin"), "net_margin_pct"),
            (
                ("so du tien", "con bao nhieu tien", "tien con bao nhieu", "tien mat va tien gui"),
                "cash_and_equivalents",
            ),
            (("dong tien thuan",), "net_cash_flow"),
            (("tong tai san",), "total_assets"),
            (
                ("cong no phai thu theo khach", "khach hang nao no", "top khach hang no"),
                "ar_by_customer",
            ),
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
        if (
            "gross_margin_pct" in found
            and "gross_profit" in found
            and "loi nhuan gop va" not in normalized
        ):
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
        return [
            dimension for phrases, dimension in mapping if any(p in normalized for p in phrases)
        ]

    def _time(self, normalized: str, period_type: str) -> TimeDraft | None:
        explicit_date = re.search(r"(?:ngay|as.of)\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})", normalized)
        if explicit_date:
            value = date(
                int(explicit_date.group(3)),
                int(explicit_date.group(2)),
                int(explicit_date.group(1)),
            )
            if period_type == "snapshot":
                return TimeDraft.as_of_date(value)
            return TimeDraft.range(value, value)
        first_half = re.search(r"(?:6|sau)\s*thang\s*dau\s*nam(?:\s*(20\d{2}))?\b", normalized)
        if first_half:
            y = int(first_half.group(1)) if first_half.group(1) else self.today.year
            return (
                TimeDraft.as_of_date(date(y, 6, 30))
                if period_type == "snapshot"
                else TimeDraft.range(date(y, 1, 1), date(y, 6, 30))
            )
        if re.search(r"\b(?:tu\s+)?dau\s+nam\s+den\s+nay\b|\bytd\b", normalized):
            return (
                TimeDraft.as_of_date(self.today)
                if period_type == "snapshot"
                else TimeDraft.range(date(self.today.year, 1, 1), self.today)
            )
        quarter = re.search(r"quy\s*([1-4])(?:\s*[/-]\s*|\s+nam\s+)?(20\d{2})", normalized)
        if quarter:
            q, year = int(quarter.group(1)), int(quarter.group(2))
            start, end = _quarter_range(year, q)
            return (
                TimeDraft.as_of_date(end)
                if period_type == "snapshot"
                else TimeDraft.range(start, end)
            )
        month = re.search(r"thang\s*(1[0-2]|0?[1-9])(?:\s*[/-]\s*|\s+nam\s+)(20\d{2})", normalized)
        if month:
            start, end = _month_range(int(month.group(2)), int(month.group(1)))
            return (
                TimeDraft.as_of_date(end)
                if period_type == "snapshot"
                else TimeDraft.range(start, end)
            )
        year = re.search(r"nam\s*(20\d{2})", normalized)
        if year:
            y = int(year.group(1))
            return (
                TimeDraft.as_of_date(date(y, 12, 31))
                if period_type == "snapshot"
                else TimeDraft.range(date(y, 1, 1), date(y, 12, 31))
            )
        if "thang nay" in normalized:
            start, end = _month_range(self.today.year, self.today.month)
            end = min(end, self.today)
            return (
                TimeDraft.as_of_date(end)
                if period_type == "snapshot"
                else TimeDraft.range(start, end)
            )
        if "thang truoc" in normalized:
            previous = self.today.replace(day=1) - timedelta(days=1)
            start, end = _month_range(previous.year, previous.month)
            return (
                TimeDraft.as_of_date(end)
                if period_type == "snapshot"
                else TimeDraft.range(start, end)
            )
        if "quy nay" in normalized:
            q = (self.today.month - 1) // 3 + 1
            start, end = _quarter_range(self.today.year, q)
            return (
                TimeDraft.as_of_date(min(end, self.today))
                if period_type == "snapshot"
                else TimeDraft.range(start, min(end, self.today))
            )
        if "quy truoc" in normalized:
            q = (self.today.month - 1) // 3 + 1
            prev_year, prev_q = (self.today.year - 1, 4) if q == 1 else (self.today.year, q - 1)
            start, end = _quarter_range(prev_year, prev_q)
            return (
                TimeDraft.as_of_date(end)
                if period_type == "snapshot"
                else TimeDraft.range(start, end)
            )
        if "nam nay" in normalized:
            return (
                TimeDraft.as_of_date(self.today)
                if period_type == "snapshot"
                else TimeDraft.range(
                    date(self.today.year, 1, 1), min(date(self.today.year, 12, 31), self.today)
                )
            )
        if "nam ngoai" in normalized or "nam truoc" in normalized:
            y = self.today.year - 1
            return (
                TimeDraft.as_of_date(date(y, 12, 31))
                if period_type == "snapshot"
                else TimeDraft.range(date(y, 1, 1), date(y, 12, 31))
            )
        if any(word in normalized for word in ("hien tai", "bay gio", "cuoi ky")):
            return (
                TimeDraft.as_of_date(self.today)
                if period_type == "snapshot"
                else TimeDraft.range(date(self.today.year, 1, 1), self.today)
            )
        return None

    @staticmethod
    def _clarify(question: str, slot: str) -> SemanticPlanDraft:
        return SemanticPlanDraft(
            plan_version="1.0",
            status="needs_clarification",
            metric_ids=[],
            time=TimeDraft.none(),
            dimensions=[],
            filters=[],
            view=None,
            operation=None,
            sort=None,
            top_k=None,
            comparison=None,
            question_for_user=question,
            unresolved_slots=[slot],
            reason_code=None,
        )

    @staticmethod
    def _unsupported(reason: str) -> SemanticPlanDraft:
        return SemanticPlanDraft(
            plan_version="1.0",
            status="unsupported",
            metric_ids=[],
            time=TimeDraft.none(),
            dimensions=[],
            filters=[],
            view=None,
            operation=None,
            sort=None,
            top_k=None,
            comparison=None,
            question_for_user=None,
            unresolved_slots=[],
            reason_code=reason,
        )
