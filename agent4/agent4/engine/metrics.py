"""Semantic metric layer: the only place where financial formulas live.

Every metric is declared once with its TT133 accounts, formula, unit, kind
(flow / snapshot / ratio / custom), the views it may be computed on and the
Vietnamese phrases a CEO uses for it.  The LLM never writes these formulas —
it only picks a metric id — so the same question always returns the same,
tested number.

Sign conventions: a ``Term`` reads account lines whose code starts with one of
``prefixes`` and measures ``net_debit`` (Nợ − Có), ``net_credit`` (Có − Nợ),
``debit`` or ``credit``; ``coef`` combines terms linearly.  Flow terms skip
closing entries (kết chuyển 911) and the opening-balance journal, snapshot
terms read the cumulative balance up to the end date.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Term:
    prefixes: tuple[str, ...]
    coef: float = 1.0
    measure: str = "net_debit"  # net_debit | net_credit | debit | credit
    where: str | None = None


@dataclass(frozen=True)
class MetricDef:
    id: str
    label: str
    description: str
    kind: str  # flow | snapshot | ratio | custom
    unit: str  # VND | % | days | ratio | count
    category: str
    formula: str
    accounts: tuple[str, ...] = ()
    terms: tuple[Term, ...] = ()
    num: tuple[Term, ...] = ()
    den: tuple[Term, ...] = ()
    num_kind: str = "flow"
    den_kind: str = "flow"
    scale: float = 1.0
    synonyms: tuple[str, ...] = ()
    group_bys: tuple[str, ...] = ()
    views: tuple[str, ...] = ("mgmt",)
    default_view: str = "mgmt"
    better: str | None = None  # up | down
    params: dict = field(default_factory=dict)

    @property
    def period_type(self) -> str:
        if self.kind == "snapshot":
            return "snapshot"
        if self.kind == "ratio" and self.num_kind == "snapshot" and self.den_kind == "snapshot":
            return "snapshot"
        if self.id in SNAPSHOT_CUSTOM:
            return "snapshot"
        return "flow"


SNAPSHOT_CUSTOM = {"ar_aging", "overdue_receivables", "cash_coverage_days"}
PL_GROUPS = ("month", "quarter", "year", "branch", "product_line", "customer", "item", "salesperson", "account")
EXP_GROUPS = ("month", "quarter", "year", "branch", "cost_category", "department", "account", "vendor")
BAL_GROUPS = ("month", "account")
BOTH = ("mgmt", "tax")

REV = Term(("511",), 1, "net_credit")
DED_521 = Term(("521",), -1, "net_debit")  # legacy TT200-style ledgers; TT133 debits deductions to 511
COGS = Term(("632",), -1, "net_debit")
OPEX = Term(("641", "642"), -1, "net_debit")
FIN_INC = Term(("515",), 1, "net_credit")
FIN_COST = Term(("635",), -1, "net_debit")
OTH_INC = Term(("711",), 1, "net_credit")
OTH_EXP = Term(("811",), -1, "net_debit")
CIT = Term(("821",), -1, "net_debit")
DEPR = Term(("214",), 1, "credit", "source_document_type = 'DEPRECIATION'")
EQUITY_ALL = Term(("4", "5", "6", "7", "8", "9"), 1, "net_credit")

CURRENT_ASSETS = (Term(("111", "112", "113", "121", "128", "131", "133", "136", "138", "141", "151", "152", "153", "154", "155", "156", "157")),
                  Term(("229",)))
CURRENT_LIAB = (Term(("331", "333", "334", "335", "338", "34111"), 1, "net_credit"),)
INVENTORY = (Term(("151", "152", "153", "154", "155", "156", "157")),)
PL_ALL = (REV, DED_521, COGS, OPEX, FIN_INC, FIN_COST, OTH_INC, OTH_EXP)


def _m(*args, **kw) -> MetricDef:
    return MetricDef(*args, **kw)


M: list[MetricDef] = [
    # ------------------------------------------------------------ P&L
    _m("net_revenue", "Doanh thu thuần", "Doanh thu bán hàng và cung cấp dịch vụ sau các khoản giảm trừ (trả lại, chiết khấu thương mại).",
       "flow", "VND", "pnl", "Có 511 − Nợ 511 (giảm trừ theo TT133) − Nợ 521 (nếu có); không tính bút toán kết chuyển 911",
       ("511", "521"), (REV, DED_521),
       synonyms=("doanh thu", "doanh thu thuần", "doanh số", "bán được bao nhiêu", "doanh thu bán hàng", "revenue", "sales", "doanh thu theo"),
       group_bys=PL_GROUPS, views=BOTH, better="up"),
    _m("gross_revenue", "Doanh thu bán hàng (trước giảm trừ)", "Tổng doanh thu xuất hóa đơn, chưa trừ hàng bán trả lại và chiết khấu.",
       "flow", "VND", "pnl", "Tổng phát sinh Có 511 (không gồm kết chuyển)", ("511",), (Term(("511",), 1, "credit"),),
       synonyms=("doanh thu gộp", "doanh thu trước giảm trừ", "tổng doanh thu xuất hóa đơn", "doanh thu chưa trừ"), group_bys=PL_GROUPS, views=BOTH),
    _m("revenue_deductions", "Các khoản giảm trừ doanh thu", "Hàng bán bị trả lại, chiết khấu thương mại, giảm giá hàng bán.",
       "flow", "VND", "pnl", "Phát sinh Nợ 511 (không gồm kết chuyển) + Nợ 521", ("511", "521"),
       (Term(("511",), 1, "debit"), Term(("521",), 1, "net_debit")),
       synonyms=("giảm trừ doanh thu", "hàng bán bị trả lại", "chiết khấu thương mại", "trả lại hàng", "giảm giá hàng bán"),
       group_bys=PL_GROUPS, better="down"),
    _m("goods_revenue", "Doanh thu bán hàng hóa", "Doanh thu thuần từ bán hàng hóa (TK 5111).", "flow", "VND", "pnl",
       "Có 5111 − Nợ 5111", ("5111",), (Term(("5111",), 1, "net_credit"),),
       synonyms=("doanh thu hàng hóa", "doanh thu bán hàng hóa", "doanh thu thiết bị"), group_bys=PL_GROUPS, views=BOTH, better="up"),
    _m("service_revenue", "Doanh thu dịch vụ", "Doanh thu thuần từ cung cấp dịch vụ (TK 5113): bảo trì, lắp đặt, cho thuê, tư vấn.",
       "flow", "VND", "pnl", "Có 5113 − Nợ 5113", ("5113",), (Term(("5113",), 1, "net_credit"),),
       synonyms=("doanh thu dịch vụ", "doanh thu bảo trì", "doanh thu mảng dịch vụ", "dịch vụ kỹ thuật"), group_bys=PL_GROUPS, views=BOTH, better="up"),
    _m("cogs", "Giá vốn hàng bán", "Giá trị hàng hóa, dịch vụ đã tiêu thụ trong kỳ.", "flow", "VND", "pnl",
       "Nợ 632 − Có 632 (không gồm kết chuyển)", ("632",), (Term(("632",), 1, "net_debit"),),
       synonyms=("giá vốn", "giá vốn hàng bán", "cogs", "chi phí giá vốn"), group_bys=PL_GROUPS, views=BOTH, better="down"),
    _m("gross_profit", "Lợi nhuận gộp", "Doanh thu thuần trừ giá vốn hàng bán.", "flow", "VND", "pnl",
       "Doanh thu thuần − Giá vốn hàng bán", ("511", "521", "632"), (REV, DED_521, COGS),
       synonyms=("lợi nhuận gộp", "lãi gộp", "lời gộp", "gross profit"), group_bys=PL_GROUPS, views=BOTH, better="up"),
    _m("gross_margin_pct", "Biên lợi nhuận gộp", "Lợi nhuận gộp / Doanh thu thuần.", "ratio", "%", "pnl",
       "(Doanh thu thuần − Giá vốn) / Doanh thu thuần × 100", ("511", "521", "632"), num=(REV, DED_521, COGS), den=(REV, DED_521), scale=100,
       synonyms=("biên lợi nhuận gộp", "biên lãi gộp", "tỷ suất lợi nhuận gộp", "gross margin", "biên gộp"),
       group_bys=PL_GROUPS, views=BOTH, better="up"),
    _m("selling_expenses", "Chi phí bán hàng", "Chi phí phát sinh trong quá trình bán hàng (TK 6421 theo TT133).", "flow", "VND", "opex",
       "Nợ 6421 − Có 6421 (+ 641 nếu dùng TT200)", ("6421", "641"), (Term(("6421", "641"), 1, "net_debit"),),
       synonyms=("chi phí bán hàng", "cp bán hàng"), group_bys=EXP_GROUPS, views=BOTH, better="down"),
    _m("admin_expenses", "Chi phí quản lý doanh nghiệp", "Chi phí quản lý chung của doanh nghiệp (TK 6422).", "flow", "VND", "opex",
       "Nợ 6422 − Có 6422", ("6422",), (Term(("6422",), 1, "net_debit"),),
       synonyms=("chi phí quản lý doanh nghiệp", "chi phí quản lý", "cp qldn", "chi phí hành chính"), group_bys=EXP_GROUPS, views=BOTH, better="down"),
    _m("operating_expenses", "Chi phí bán hàng và quản lý doanh nghiệp", "Tổng chi phí quản lý kinh doanh (TK 642 = 6421 + 6422).",
       "flow", "VND", "opex", "Nợ 642 − Có 642 (+ 641)", ("641", "642"), (Term(("641", "642"), 1, "net_debit"),),
       synonyms=("chi phí hoạt động", "chi phí vận hành", "chi phí bán hàng và quản lý", "chi phí quản lý kinh doanh", "opex", "tổng chi phí"),
       group_bys=EXP_GROUPS, views=BOTH, better="down"),
    _m("finance_income", "Doanh thu hoạt động tài chính", "Lãi tiền gửi, lãi đầu tư.", "flow", "VND", "pnl", "Có 515 − Nợ 515", ("515",),
       (Term(("515",), 1, "net_credit"),), synonyms=("doanh thu tài chính", "lãi tiền gửi", "thu nhập tài chính"),
       group_bys=("month", "quarter", "year"), views=BOTH),
    _m("finance_cost", "Chi phí tài chính (lãi vay)", "Chi phí lãi vay và chi phí tài chính khác.", "flow", "VND", "pnl", "Nợ 635 − Có 635",
       ("635",), (Term(("635",), 1, "net_debit"),), synonyms=("chi phí tài chính", "lãi vay", "chi phí lãi vay", "tiền lãi phải trả"),
       group_bys=("month", "quarter", "year"), views=BOTH, better="down"),
    _m("operating_profit", "Lợi nhuận thuần từ hoạt động kinh doanh", "Lợi nhuận gộp − chi phí BH & QLDN + doanh thu tài chính − chi phí tài chính.",
       "flow", "VND", "pnl", "LN gộp − (6421 + 6422) + 515 − 635", ("511", "521", "632", "642", "515", "635"),
       (REV, DED_521, COGS, OPEX, FIN_INC, FIN_COST),
       synonyms=("lợi nhuận thuần hoạt động kinh doanh", "lợi nhuận hoạt động", "lãi từ kinh doanh", "lợi nhuận kinh doanh", "ebit", "lợi nhuận thuần"),
       group_bys=("month", "quarter", "year", "branch"), views=BOTH, better="up"),
    _m("other_income", "Thu nhập khác", "Thu nhập ngoài hoạt động kinh doanh chính (thanh lý tài sản…).", "flow", "VND", "pnl", "Có 711 − Nợ 711",
       ("711",), (Term(("711",), 1, "net_credit"),), synonyms=("thu nhập khác", "thu nhập bất thường"), views=BOTH),
    _m("other_expenses", "Chi phí khác", "Chi phí ngoài hoạt động kinh doanh (tiền phạt, chậm nộp…).", "flow", "VND", "pnl", "Nợ 811 − Có 811",
       ("811",), (Term(("811",), 1, "net_debit"),), synonyms=("chi phí khác", "tiền phạt", "chi phí bất thường"), views=BOTH, better="down"),
    _m("profit_before_tax", "Lợi nhuận trước thuế", "Tổng lợi nhuận kế toán trước thuế TNDN.", "flow", "VND", "pnl",
       "LN thuần HĐKD + 711 − 811", ("511", "521", "632", "642", "515", "635", "711", "811"), PL_ALL,
       synonyms=("lợi nhuận trước thuế", "lãi trước thuế", "ebt", "lợi nhuận kế toán"), group_bys=("month", "quarter", "year", "branch"),
       views=BOTH, better="up"),
    _m("income_tax_expense", "Chi phí thuế TNDN", "Chi phí thuế thu nhập doanh nghiệp đã ghi nhận (tạm tính + quyết toán).", "flow", "VND", "tax",
       "Nợ 821 − Có 821", ("821",), (Term(("821",), 1, "net_debit"),),
       synonyms=("chi phí thuế tndn", "thuế tndn đã ghi nhận", "chi phí thuế thu nhập doanh nghiệp"), group_bys=("month", "quarter", "year"), views=BOTH),
    _m("net_profit", "Lợi nhuận sau thuế", "Lợi nhuận cuối cùng sau thuế TNDN — 'lãi' của doanh nghiệp.", "flow", "VND", "pnl",
       "LN trước thuế − Chi phí thuế TNDN (821)", ("511", "521", "632", "642", "515", "635", "711", "811", "821"), PL_ALL + (CIT,),
       synonyms=("lợi nhuận sau thuế", "lãi ròng", "lợi nhuận ròng", "lãi sau thuế", "net profit", "lời ròng", "kết quả kinh doanh", "lỗ hay lãi"),
       group_bys=("month", "quarter", "year", "branch"), views=BOTH, better="up"),
    _m("net_margin_pct", "Biên lợi nhuận ròng", "Lợi nhuận sau thuế / Doanh thu thuần.", "ratio", "%", "pnl", "LNST / Doanh thu thuần × 100",
       ("511", "521", "632", "642", "515", "635", "711", "811", "821"), num=PL_ALL + (CIT,), den=(REV, DED_521), scale=100,
       synonyms=("biên lợi nhuận ròng", "tỷ suất lợi nhuận", "biên lãi ròng", "net margin"), group_bys=("month", "quarter", "year"), views=BOTH, better="up"),
    _m("ebitda", "EBITDA", "Lợi nhuận trước thuế, lãi vay và khấu hao.", "flow", "VND", "pnl", "LN trước thuế + Chi phí lãi vay (635) + Khấu hao (Có 214)",
       ("511", "632", "642", "515", "635", "711", "811", "214"), PL_ALL + (Term(("635",), 1, "net_debit"), DEPR),
       synonyms=("ebitda", "lợi nhuận trước lãi vay thuế và khấu hao"), group_bys=("month", "quarter", "year"), better="up"),
    _m("depreciation_expense", "Chi phí khấu hao TSCĐ", "Khấu hao tài sản cố định trích trong kỳ.", "flow", "VND", "opex", "Phát sinh Có 214 từ bút toán khấu hao",
       ("214",), (DEPR,), synonyms=("khấu hao", "chi phí khấu hao"), group_bys=("month", "quarter", "year")),
    _m("salary_expense", "Chi phí lương nhân viên", "Tiền lương, phụ cấp và thưởng phát sinh (gồm kỹ thuật viên dịch vụ ghi qua 154).",
       "flow", "VND", "opex", "Nợ 6421/6422/154 khoản mục Lương + Thưởng (đối ứng Có 334/335)", ("642", "154", "334"),
       (Term(("642", "641", "154", "622", "627"), 1, "net_debit", "cost_category IN ('LUONG','THUONG')"),),
       synonyms=("chi phí lương", "tiền lương", "quỹ lương", "lương nhân viên", "chi lương", "lương thưởng"),
       group_bys=("month", "quarter", "year", "branch", "department"), views=BOTH, better="down"),
    _m("labor_cost", "Tổng chi phí nhân sự", "Lương, thưởng và các khoản bảo hiểm, KPCĐ doanh nghiệp đóng.", "flow", "VND", "opex",
       "Nợ 6421/6422/154 khoản mục Lương + Thưởng + Bảo hiểm", ("642", "154", "334", "338"),
       (Term(("642", "641", "154", "622", "627"), 1, "net_debit", "cost_category IN ('LUONG','THUONG','BAOHIEM')"),),
       synonyms=("chi phí nhân sự", "chi phí nhân công", "tổng chi phí lao động", "chi phí con người"),
       group_bys=("month", "quarter", "year", "branch", "department"), views=BOTH, better="down"),
    # ------------------------------------------------------------ balances
    _m("cash_and_equivalents", "Tiền mặt và tiền gửi ngân hàng", "Số dư tiền mặt tại quỹ và tiền gửi không kỳ hạn tại ngày cuối kỳ.", "snapshot", "VND",
       "cash", "Số dư Nợ 111 + 112 lũy kế đến ngày cuối kỳ", ("111", "112"), (Term(("111", "112")),),
       synonyms=("tiền mặt", "tiền gửi ngân hàng", "số dư tiền", "tiền còn bao nhiêu", "tiền trong tài khoản", "quỹ tiền", "cash", "số dư ngân hàng",
                 "còn bao nhiêu tiền"), group_bys=BAL_GROUPS, better="up"),
    _m("term_deposits", "Tiền gửi có kỳ hạn", "Tiền gửi có kỳ hạn (đầu tư nắm giữ đến ngày đáo hạn).", "snapshot", "VND", "cash", "Số dư Nợ 128",
       ("128",), (Term(("128",)),), synonyms=("tiền gửi có kỳ hạn", "sổ tiết kiệm", "tiền gửi kỳ hạn")),
    _m("ar_balance", "Phải thu khách hàng", "Tổng công nợ phải thu khách hàng còn lại tại ngày cuối kỳ (đã trừ khoản khách trả trước).", "snapshot", "VND",
       "ar", "Số dư Nợ 131 − Có 131 lũy kế", ("131",), (Term(("131",)),),
       synonyms=("phải thu", "công nợ phải thu", "khách nợ", "tiền khách đang nợ", "phải thu khách hàng", "công nợ khách hàng", "accounts receivable"),
       group_bys=("month", "customer", "salesperson", "branch"), better="down"),
    _m("ar_by_customer", "Công nợ phải thu theo khách hàng", "Số dư phải thu phân rã theo từng khách hàng, sắp xếp giảm dần.", "snapshot", "VND",
       "ar", "Số dư 131 theo đối tượng khách hàng", ("131",), (Term(("131",)),),
       synonyms=("khách hàng nào nợ nhiều nhất", "công nợ theo khách hàng", "khách nợ lớn nhất", "top khách hàng nợ", "danh sách công nợ khách hàng"),
       group_bys=("customer",), params={"group_by": "customer"}),
    _m("ar_by_salesperson", "Công nợ phải thu theo nhân viên phụ trách", "Số dư phải thu theo nhân viên kinh doanh phụ trách khách hàng.", "snapshot", "VND",
       "ar", "Số dư 131 theo nhân viên phụ trách", ("131",), (Term(("131",)),),
       synonyms=("công nợ theo nhân viên", "nhân viên phụ trách", "công nợ theo sales", "nhân viên kinh doanh nào"),
       group_bys=("salesperson",), params={"group_by": "salesperson"}),
    _m("ap_balance", "Phải trả người bán", "Tổng công nợ phải trả nhà cung cấp còn lại tại ngày cuối kỳ.", "snapshot", "VND", "ap",
       "Số dư Có 331 − Nợ 331 lũy kế", ("331",), (Term(("331",), 1, "net_credit"),),
       synonyms=("phải trả", "công nợ phải trả", "nợ nhà cung cấp", "phải trả người bán", "nợ ncc", "accounts payable"),
       group_bys=("month", "vendor"), better="down"),
    _m("ap_by_vendor", "Công nợ phải trả theo nhà cung cấp", "Số dư phải trả theo từng nhà cung cấp.", "snapshot", "VND", "ap",
       "Số dư 331 theo nhà cung cấp", ("331",), (Term(("331",), 1, "net_credit"),),
       synonyms=("nhà cung cấp nào", "nợ nhà cung cấp nào nhiều nhất", "công nợ theo nhà cung cấp", "top nhà cung cấp"),
       group_bys=("vendor",), params={"group_by": "vendor"}),
    _m("inventory_value", "Giá trị hàng tồn kho", "Giá trị hàng tồn kho cuối kỳ theo giá vốn bình quân.", "snapshot", "VND", "inventory",
       "Số dư Nợ 151–157 lũy kế", ("152", "153", "154", "155", "156", "157"), INVENTORY,
       synonyms=("tồn kho", "hàng tồn kho", "giá trị tồn kho", "hàng trong kho", "inventory", "mặt hàng tồn kho", "tỷ trọng tồn kho"),
       group_bys=("month", "item", "account")),
    _m("tax_payable", "Thuế và các khoản phải nộp Nhà nước", "Số thuế còn phải nộp tại ngày cuối kỳ (GTGT, TNDN, TNCN, khác).", "snapshot", "VND", "tax",
       "Số dư Có 333 lũy kế", ("333",), (Term(("333",), 1, "net_credit"),),
       synonyms=("thuế phải nộp", "nợ thuế", "thuế còn phải nộp", "các khoản phải nộp nhà nước", "nghĩa vụ thuế"),
       group_bys=("account", "month"), views=BOTH, default_view="tax"),
    _m("debt_balance", "Dư nợ vay", "Tổng dư nợ vay ngân hàng (ngắn hạn + dài hạn).", "snapshot", "VND", "debt", "Số dư Có 341 lũy kế", ("341",),
       (Term(("341",), 1, "net_credit"),), synonyms=("dư nợ vay", "nợ vay", "vay ngân hàng", "khoản vay", "nợ ngân hàng"), group_bys=("account", "month")),
    _m("fixed_assets_net", "Giá trị còn lại TSCĐ", "Nguyên giá TSCĐ trừ hao mòn lũy kế.", "snapshot", "VND", "balance", "Số dư 211 − 214", ("211", "214"),
       (Term(("211", "214")),), synonyms=("tài sản cố định", "giá trị còn lại tài sản", "tscđ")),
    _m("total_assets", "Tổng tài sản", "Tổng tài sản trên bảng cân đối kế toán.", "snapshot", "VND", "balance", "Tổng số dư các TK loại 1, 2 (sau dự phòng, hao mòn)",
       ("1", "2"), (Term(("1", "2")),), synonyms=("tổng tài sản", "quy mô tài sản")),
    _m("total_liabilities", "Tổng nợ phải trả", "Tổng nợ phải trả trên bảng cân đối kế toán.", "snapshot", "VND", "balance", "Tổng số dư Có các TK loại 3",
       ("3",), (Term(("3",), 1, "net_credit"),), synonyms=("tổng nợ phải trả", "tổng nợ", "nợ phải trả")),
    _m("equity", "Vốn chủ sở hữu", "Vốn góp + lợi nhuận chưa phân phối (gồm lãi/lỗ các tháng chưa kết chuyển).", "snapshot", "VND", "balance",
       "Số dư Có loại 4 + kết quả chưa kết chuyển (loại 5–9)", ("4",), (EQUITY_ALL,), synonyms=("vốn chủ sở hữu", "vốn chủ", "equity", "giá trị sổ sách")),
    _m("working_capital", "Vốn lưu động ròng", "Tài sản ngắn hạn trừ nợ ngắn hạn.", "snapshot", "VND", "liquidity",
       "TS ngắn hạn (111–157, 229) − Nợ ngắn hạn (331, 333–338, vay ngắn hạn 34111)", ("1", "33", "34111"),
       CURRENT_ASSETS + (Term(("331", "333", "334", "335", "338", "34111"), -1, "net_credit"),), synonyms=("vốn lưu động", "vốn lưu động ròng", "working capital")),
    _m("current_ratio", "Hệ số thanh toán hiện hành", "Tài sản ngắn hạn / Nợ ngắn hạn.", "ratio", "ratio", "liquidity", "TS ngắn hạn / Nợ ngắn hạn",
       ("1", "33", "34111"), num=CURRENT_ASSETS, den=CURRENT_LIAB, num_kind="snapshot", den_kind="snapshot",
       synonyms=("hệ số thanh toán hiện hành", "current ratio", "khả năng thanh toán ngắn hạn", "thanh khoản"), better="up"),
    _m("quick_ratio", "Hệ số thanh toán nhanh", "(Tài sản ngắn hạn − Hàng tồn kho) / Nợ ngắn hạn.", "ratio", "ratio", "liquidity",
       "(TS ngắn hạn − Tồn kho) / Nợ ngắn hạn", ("1", "15", "33", "34111"),
       num=CURRENT_ASSETS + (Term(INVENTORY[0].prefixes, -1),), den=CURRENT_LIAB, num_kind="snapshot", den_kind="snapshot",
       synonyms=("hệ số thanh toán nhanh", "quick ratio", "khả năng thanh toán nhanh"), better="up"),
    _m("debt_to_equity", "Hệ số nợ vay / vốn chủ sở hữu", "Dư nợ vay / Vốn chủ sở hữu.", "ratio", "ratio", "debt", "Dư nợ 341 / Vốn chủ sở hữu",
       ("341", "4"), num=(Term(("341",), 1, "net_credit"),), den=(EQUITY_ALL,), num_kind="snapshot", den_kind="snapshot",
       synonyms=("đòn bẩy tài chính", "nợ trên vốn chủ", "debt to equity", "hệ số nợ"), better="down"),
    # ------------------------------------------------------------ cash flow
    _m("net_cash_flow", "Dòng tiền thuần trong kỳ", "Biến động tiền mặt và tiền gửi ngân hàng trong kỳ (thu − chi).", "flow", "VND", "cash",
       "Phát sinh Nợ − Có của 111 + 112 trong kỳ", ("111", "112"), (Term(("111", "112")),),
       synonyms=("dòng tiền", "dòng tiền thuần", "lưu chuyển tiền", "tiền vào tiền ra", "thu chi", "cash flow", "dòng tiền biến động"),
       group_bys=("month", "quarter", "year", "account"), better="up"),
    _m("cash_flow_breakdown", "Dòng tiền theo nhóm thu/chi", "Dòng tiền thuần phân loại theo nguồn: thu khách hàng, trả NCC, lương, thuế, vay, đầu tư…",
       "custom", "VND", "cash", "Phát sinh 111/112 phân loại theo tài khoản đối ứng của chứng từ (phương pháp trực tiếp)", ("111", "112"),
       synonyms=("dòng tiền theo nhóm", "tiền thu từ đâu chi vào đâu", "thu chi theo loại", "cơ cấu dòng tiền", "lưu chuyển tiền tệ trực tiếp"),
       group_bys=("month",)),
    _m("cash_coverage_days", "Số ngày tiền hiện có đủ chi trả", "Tiền và tương đương tiền / chi tiêu tiền bình quân mỗi ngày (90 ngày gần nhất, không gồm trả nợ gốc).",
       "custom", "days", "cash", "Số dư 111+112 / (Tổng chi tiền 90 ngày trước ÷ 90)", ("111", "112"),
       synonyms=("đủ tiền chi bao lâu", "runway", "tiền đủ dùng bao nhiêu ngày", "số ngày tiền mặt", "sống được bao lâu"), better="up"),
    # ------------------------------------------------------------ AR / AP analytics
    _m("ar_aging", "Tuổi nợ phải thu", "Phân nhóm công nợ phải thu theo số ngày quá hạn (chưa đến hạn, 1–30, 31–60, 61–90, >90 ngày).", "custom", "VND", "ar",
       "Sổ chi tiết hóa đơn bán: số còn phải thu theo hạn thanh toán; khoản trả trước/chiết khấu chưa phân bổ cấn trừ hóa đơn cũ nhất", ("131",),
       synonyms=("tuổi nợ", "phân tích tuổi nợ", "aging", "nợ quá hạn theo nhóm", "cơ cấu nợ quá hạn"), group_bys=("customer",)),
    _m("overdue_receivables", "Các khoản phải thu quá hạn", "Danh sách hóa đơn bán còn nợ đã quá hạn thanh toán trên N ngày.", "custom", "VND", "ar",
       "Hóa đơn có ngày đến hạn < ngày cuối kỳ − N và còn số phải thu > 0", ("131",), params={"min_days": 30},
       synonyms=("quá hạn", "nợ quá hạn", "khoản phải thu quá hạn", "khách trả chậm", "hóa đơn quá hạn", "nợ xấu", "khó đòi"), better="down"),
    _m("dso", "Số ngày thu tiền bình quân (DSO)", "Phải thu bình quân / doanh số bán chịu (gồm VAT) × số ngày trong kỳ.", "custom", "days", "ar",
       "((Dư 131 đầu kỳ + cuối kỳ) / 2) / Phát sinh Nợ 131 từ hóa đơn bán × số ngày kỳ", ("131", "511"),
       synonyms=("dso", "số ngày thu hồi nợ", "kỳ thu tiền bình quân", "vòng quay phải thu", "thu hồi nợ bình quân", "bao lâu thu được tiền"), better="down"),
    _m("dso_actual", "Số ngày thực tế khách thanh toán", "Bình quân gia quyền số ngày từ ngày hóa đơn đến ngày thu tiền, với các khoản thu trong kỳ.",
       "custom", "days", "ar", "Σ(số tiền × (ngày thu − ngày hóa đơn)) / Σ số tiền thu", ("131",),
       synonyms=("khách trả tiền sau bao nhiêu ngày", "thời gian thanh toán thực tế", "dso thực tế", "hành vi thanh toán"), better="down"),
    _m("dpo", "Số ngày trả tiền bình quân (DPO)", "Phải trả bình quân / giá trị mua chịu (gồm VAT) × số ngày.", "custom", "days", "ap",
       "((Dư 331 đầu + cuối) / 2) / Phát sinh Có 331 từ hóa đơn mua × số ngày", ("331",),
       synonyms=("dpo", "số ngày trả nợ nhà cung cấp", "kỳ trả tiền bình quân"), better="up"),
    _m("dio", "Số ngày tồn kho bình quân (DIO)", "Tồn kho bình quân / giá vốn × số ngày.", "custom", "days", "inventory",
       "((Tồn kho đầu + cuối) / 2) / Giá vốn hàng bán × số ngày", ("156", "632"),
       synonyms=("dio", "số ngày tồn kho", "vòng quay hàng tồn kho", "hàng nằm kho bao lâu"), better="down"),
    _m("cash_conversion_cycle", "Chu kỳ chuyển đổi tiền mặt", "DSO + DIO − DPO.", "custom", "days", "liquidity", "DSO + DIO − DPO", ("131", "156", "331"),
       synonyms=("chu kỳ tiền mặt", "cash conversion cycle", "ccc", "chu kỳ chuyển đổi tiền"), better="down"),
    _m("ap_due_soon", "Khoản phải trả sắp đến hạn", "Hóa đơn mua còn nợ đến hạn trong N ngày tới (kèm các khoản đã quá hạn chưa trả).", "custom", "VND", "ap",
       "Sổ chi tiết hóa đơn mua: số còn phải trả có hạn thanh toán ≤ ngày dữ liệu + N", ("331",), params={"days": 15},
       synonyms=("phải trả sắp đến hạn", "đến hạn thanh toán", "sắp phải trả", "khoản phải trả nào đến hạn", "lịch trả nợ nhà cung cấp")),
    _m("upcoming_obligations", "Nghĩa vụ thanh toán sắp tới", "Dự kiến tiền phải chi trong kỳ tới: nhà cung cấp đến hạn, thuế, BHXH, lương, nợ gốc/lãi vay.",
       "custom", "VND", "cash", "Công nợ 331 đến hạn + số dư 333, 338, 334 + lương ước tính + lịch trả nợ vay", ("331", "333", "334", "338", "341"),
       synonyms=("cần chi bao nhiêu", "số tiền cần chi", "phải chi trong tháng tới", "tiền cần để thanh toán", "nghĩa vụ thanh toán"),
       params={"period_default": "next_month"}),
    # ------------------------------------------------------------ analysis & anomalies
    _m("expense_by_category", "Chi phí theo khoản mục", "Chi phí bán hàng & quản lý phân theo khoản mục (lương, thuê, marketing…).", "flow", "VND", "opex",
       "Nợ 642 − Có 642 nhóm theo khoản mục chi phí", ("642", "641"), (Term(("641", "642"), 1, "net_debit"),),
       synonyms=("chi phí gồm những khoản nào", "cơ cấu chi phí", "khoản mục chi phí", "chi phí theo loại", "chi tiết chi phí", "các khoản chi phí"),
       group_bys=("cost_category",), params={"group_by": "cost_category"}, views=BOTH),
    _m("expense_spikes", "Khoản chi phí tăng bất thường", "So sánh chi phí từng khoản mục trong kỳ với bình quân 3 tháng trước đó.", "custom", "VND", "anomaly",
       "Chi phí khoản mục kỳ này − bình quân 3 tháng liền trước; xếp theo mức tăng", ("642", "154"),
       synonyms=("chi phí tăng mạnh", "chi phí nào tăng", "tăng bất thường", "chi phí bất thường", "so với bình quân 3 tháng", "vượt bình quân"), better="down"),
    _m("unusual_account_movements", "Tài khoản phát sinh bất thường", "Tài khoản có phát sinh Nợ/Có trong tháng lệch mạnh so với 6 tháng trước (z-score).", "custom",
       "count", "anomaly", "|Phát sinh tháng − TB 6 tháng trước| / độ lệch chuẩn ≥ 2,5 và chênh ≥ 50 triệu", (),
       synonyms=("phát sinh lớn bất thường", "tài khoản bất thường", "biến động bất thường tài khoản", "phát sinh nợ có bất thường")),
    _m("unbalanced_journals", "Chứng từ không cân đối Nợ/Có", "Chứng từ có tổng phát sinh Nợ khác tổng phát sinh Có.", "custom", "count", "anomaly",
       "Nhóm theo số chứng từ: Σ Nợ ≠ Σ Có", (), synonyms=("không cân bằng", "lệch nợ có", "chứng từ lệch", "không cân đối", "nợ có không khớp"),
       params={"period_default": "all"}, better="down"),
    _m("top_sales_transactions", "Giao dịch bán hàng lớn nhất", "Các hóa đơn bán có giá trị lớn nhất trong kỳ.", "custom", "VND", "pnl",
       "Hóa đơn bán xếp theo giá trị trước thuế", ("511",), params={"top_k": 10},
       synonyms=("giao dịch doanh thu lớn nhất", "hóa đơn lớn nhất", "đơn hàng lớn nhất", "giao dịch lớn")),
    _m("budget_vs_actual", "Thực hiện so với kế hoạch", "So sánh doanh thu, chi phí thực tế với ngân sách kế hoạch.", "custom", "VND", "planning",
       "Thực tế (511, 642 theo khoản mục) so với bảng ngân sách; tháng dở dang được phân bổ theo số ngày", ("511", "642"),
       synonyms=("kế hoạch", "ngân sách", "so với kế hoạch", "vượt ngân sách", "budget", "chỉ tiêu", "hoàn thành kế hoạch"),
       group_bys=("branch", "cost_category"), params={"line_type": "ALL"}),
    _m("payroll_summary", "Tổng hợp quỹ lương & nhân sự", "Số nhân sự, tổng lương, thưởng, bảo hiểm DN đóng, thuế TNCN khấu trừ theo bảng lương.", "custom", "VND",
       "opex", "Bảng lương chi tiết theo nhân viên (đối chiếu 334/338)", ("334", "338", "3335"),
       synonyms=("bảng lương", "số nhân viên", "nhân sự", "headcount", "bao nhiêu nhân viên", "quỹ lương"), group_bys=("branch", "department")),
    # ------------------------------------------------------------ tax view
    _m("taxable_income", "Thu nhập chịu thuế TNDN (ước tính)", "Doanh thu trừ chi phí được trừ theo khung dữ liệu thuế (đã loại chi phí không được trừ).",
       "flow", "VND", "tax", "Trên view thuế: 511 + 515 + 711 − (632 + 642 + 635 + 811), chỉ gồm dòng được trừ", ("511", "515", "711", "632", "642", "635", "811"),
       PL_ALL, synonyms=("thu nhập chịu thuế", "thu nhập tính thuế", "lợi nhuận tính thuế", "thu nhập chịu thuế tndn"),
       group_bys=("month", "quarter", "year"), views=("tax",), default_view="tax"),
    _m("cit_estimate", "Thuế TNDN phải nộp ước tính", "20% × thu nhập chịu thuế (khung thuế) trong kỳ.", "custom", "VND", "tax", "max(0, Thu nhập chịu thuế) × 20%",
       ("511", "632", "642", "821"), synonyms=("thuế tndn phải nộp", "thuế thu nhập doanh nghiệp phải nộp", "ước tính thuế tndn", "thuế tndn tạm tính"),
       views=("tax",), default_view="tax"),
    _m("deductible_expenses", "Chi phí được trừ khi tính thuế", "Tổng chi phí hợp lệ được trừ khi tính thuế TNDN.", "flow", "VND", "tax",
       "Trên view thuế: 632 + 642 + 635 + 811 (chỉ dòng được trừ)", ("632", "642", "635", "811"),
       (Term(("632", "641", "642", "635", "811"), 1, "net_debit"),), synonyms=("chi phí được trừ", "chi phí hợp lệ", "chi phí được khấu trừ thuế"),
       group_bys=("month", "quarter", "cost_category"), views=("tax",), default_view="tax"),
    _m("mgmt_vs_tax_gap", "Chênh lệch khung quản trị và khung thuế", "Chi phí không được trừ khi tính thuế (có trong sổ quản trị nhưng bị loại ở khung thuế).",
       "custom", "VND", "tax", "Σ chi phí dòng tax_deductible = FALSE, theo lý do", ("6", "8"),
       synonyms=("chi phí không được trừ", "chênh lệch thuế và quản trị", "chi phí bị loại", "không hợp lệ thuế", "chênh lệch hai khung"),
       views=("tax",), default_view="tax"),
    _m("vat_position", "Thuế GTGT trong kỳ", "Thuế GTGT đầu ra, đầu vào được khấu trừ và số phải nộp.", "custom", "VND", "tax",
       "Đầu ra: Có 33311 từ hóa đơn bán; đầu vào: Nợ 1331 (khung thuế); phải nộp = đầu ra − đầu vào", ("33311", "1331"),
       synonyms=("thuế gtgt", "vat", "thuế giá trị gia tăng", "vat phải nộp", "thuế đầu ra đầu vào"), views=("tax",), default_view="tax"),
]

REGISTRY: dict[str, MetricDef] = {m.id: m for m in M}

GROUP_LABELS = {
    "month": "tháng", "quarter": "quý", "year": "năm", "branch": "chi nhánh", "product_line": "nhóm sản phẩm/dịch vụ", "customer": "khách hàng",
    "vendor": "nhà cung cấp", "item": "mặt hàng", "cost_category": "khoản mục chi phí", "department": "phòng ban", "salesperson": "nhân viên phụ trách",
    "account": "tài khoản",
}
