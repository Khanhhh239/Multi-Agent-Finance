"""Parameters read from a question and checked against the enterprise's own data.

Nothing here guesses: a period, an invoice number, a seller or an issue type is only returned when it is written in the
question (or, for a seller, when its distinctive name words are) and, for numbers and sellers, when it exists in the data.
"""
import re
from dataclasses import dataclass, field
from datetime import date

from ...extraction.xml_context import fold

ROMAN = {'i': 1, 'ii': 2, 'iii': 3, 'iv': 4}
NUM_WORDS = {'mot': 1, 'hai': 2, 'ba': 3, 'bon': 4, 'tu': 4, 'nam': 5, 'sau': 6, 'bay': 7, 'tam': 8, 'chin': 9, 'muoi': 10}
# Legal-form phrases and business-type words that many company names carry; they cannot identify a seller.
NAME_FORMS = ('trach nhiem huu han', 'mot thanh vien', 'co phan', 'cong ty', 'tnhh', 'mtv', 'cp', 'chi nhanh', 'tap doan', 'doanh nghiep tu nhan',
              'cua hang', 'ho kinh doanh', 'viet nam', 'thuong mai dich vu', 'thuong mai', 'dich vu', 'san xuat', 'xuat nhap khau',
              'thiet bi', 'ky thuat', 'cong nghe', 'giai phap', 'he thong', 'phan mem', 'dau tu', 'phat trien')
NAME_STOP = {'tm', 'dv', 'xnk', 'va'}
# Everyday words (unaccented) that also occur inside company names; two of them in a row are not a name.
COMMON_WORDS = {'chua', 'co', 'khi', 'la', 'cua', 'cho', 'nhung', 'nao', 'khong', 'da', 'duoc', 'bi', 'se', 'thi', 'ma', 'den', 'tu',
                'tai', 've', 'voi', 'hoa', 'don', 'mua', 'ban', 'tien', 'thue', 'nam', 'thang', 'quy', 'ngay', 'gi', 'bao', 'nhieu', 'tong',
                'hang', 'hoa', 'dau', 'ra', 'vao', 'moi', 'cu', 'lai', 'con', 'nay', 'do', 'kia', 'hon', 'nhat', 'mot', 'hai', 'ba', 'so',
                'chung', 'chuyen', 'khoan', 'toi', 'ta'}
LAW_CUES = ('vi sao', 'tai sao', 'can cu', 'dieu nao', 'quy dinh nao', 'theo luat', 'theo quy dinh', 'dieu khoan', 'luat nao',
            'nghi dinh nao', 'thong tu nao')


@dataclass
class Period:
    year: int | None = None
    month: int | None = None
    quarter: int | None = None
    label: str = 'toàn bộ dữ liệu'

    def contains(self, d: date | None) -> bool:
        if d is None:
            return False
        if self.year and d.year != self.year:
            return False
        if self.month and d.month != self.month:
            return False
        if self.quarter and (d.month - 1) // 3 + 1 != self.quarter:
            return False
        return True

    @property
    def is_all(self) -> bool:
        return not (self.year or self.month or self.quarter)

    def to_dict(self):
        return {k: v for k, v in dict(year=self.year, month=self.month, quarter=self.quarter).items() if v}


@dataclass
class Params:
    period: Period = field(default_factory=Period)
    invoice_numbers: list = field(default_factory=list)       # written in the question
    invoice_numbers_found: list = field(default_factory=list)  # of those, the ones present in the data
    tax_ids: list = field(default_factory=list)
    seller: str | None = None                                  # seller tax id resolved from the data
    seller_text: str | None = None
    top_n: int | None = None
    issue: list = field(default_factory=list)                  # rule codes
    issue_name: str | None = None
    rank_by: str = 'risk'
    wants_law: bool = False

    def to_dict(self):
        return dict(period=self.period.to_dict(), period_label=self.period.label, invoice_numbers=self.invoice_numbers,
                    invoice_numbers_found=self.invoice_numbers_found, seller=self.seller, top_n=self.top_n,
                    issue=self.issue, issue_name=self.issue_name, rank_by=self.rank_by, wants_law=self.wants_law)


def _data_years(invoices) -> list[int]:
    return sorted({i.issue_date.year for i in invoices if i.issue_date})


def period(q: str, invoices, as_of: date) -> Period:
    years = _data_years(invoices)
    latest = max((i.issue_date for i in invoices if i.issue_date), default=as_of)
    y = re.search(r'nam\s*(20\d{2})', q) or re.search(r'/\s*(20\d{2})', q)
    year = int(y.group(1)) if y else None
    m = re.search(r'thang\s*(\d{1,2})(?!\d)', q)
    if m and 1 <= int(m.group(1)) <= 12:
        month = int(m.group(1))
        if not year:
            cands = [yy for yy in years if any(i.issue_date and i.issue_date.year == yy and i.issue_date.month == month for i in invoices)]
            year = cands[-1] if cands else (years[-1] if years else as_of.year)
        return Period(year, month, None, f'tháng {month:02d}/{year}')
    qm = re.search(r'quy\s*(\d|iv|iii|ii|i)\b', q)
    if qm:
        quarter = int(qm.group(1)) if qm.group(1).isdigit() else ROMAN[qm.group(1)]
        if 1 <= quarter <= 4:
            if not year:
                cands = [yy for yy in years if any(i.issue_date and i.issue_date.year == yy and (i.issue_date.month - 1) // 3 + 1 == quarter
                                                   for i in invoices)]
                year = cands[-1] if cands else (years[-1] if years else as_of.year)
            return Period(year, None, quarter, f'quý {quarter}/{year}')
    if re.search(r'thang\s*(nay|hien tai)', q):
        return Period(latest.year, latest.month, None, f'tháng {latest.month:02d}/{latest.year} (tháng gần nhất có dữ liệu)')
    if 'thang truoc' in q:
        yy, mm = (latest.year, latest.month - 1) if latest.month > 1 else (latest.year - 1, 12)
        return Period(yy, mm, None, f'tháng {mm:02d}/{yy}')
    if re.search(r'quy\s*(nay|hien tai)', q) or re.search(r'\bky\s*(nay|hien tai)\b', q):
        qq = (latest.month - 1) // 3 + 1
        return Period(latest.year, None, qq, f'quý {qq}/{latest.year} (quý gần nhất có dữ liệu)')
    if 'quy truoc' in q:
        qq = (latest.month - 1) // 3 + 1
        yy, qq = (latest.year, qq - 1) if qq > 1 else (latest.year - 1, 4)
        return Period(yy, None, qq, f'quý {qq}/{yy}')
    if year:
        return Period(year, None, None, f'năm {year}')
    if re.search(r'nam\s*nay', q):
        return Period(latest.year, None, None, f'năm {latest.year}')
    return Period()


def invoice_numbers(q: str) -> list[str]:
    """Numbers written after 'hóa đơn', 'hđ' or 'số', including lists such as 'hóa đơn 4 và 5'."""
    out = []
    for m in re.finditer(r'(?:hoa don|\bhd|\bso)\s*(?:so\s*)?((?:\d{1,8})(?:\s*(?:,|va|\bvoi\b)\s*\d{1,8})*)', q):
        out += [str(int(n)) for n in re.findall(r'\d{1,8}', m.group(1))]
    q2 = re.sub(r'\d{10}(?:-\d{3})?', ' ', q)
    q2 = re.sub(r'(?:thang|quy|nam|top)\s*\d+', ' ', q2)
    q2 = re.sub(r'\d+\s*(?:trieu|ty|nghin|ngan|dong|%|phan tram|ngay|hoa don|nha cung cap|nguoi ban|khach)', ' ', q2)
    if not out:
        out = [str(int(n)) for n in re.findall(r'(?<![\d/.,])(\d{3,8})(?![\d/.,])', q2) if not (len(n) == 4 and n.startswith('20'))]
    return list(dict.fromkeys(out))


def top_n(q: str) -> int | None:
    m = re.search(r'top\s*(\d{1,2})', q) or re.search(r'(\d{1,2})\s*(?:hoa don|hd|nguoi ban|nha cung cap|ncc|khoan|khach)\b', q)
    if m:
        return max(1, min(50, int(m.group(1))))
    m = re.search(r'\b(' + '|'.join(NUM_WORDS) + r')\s*(?:hoa don|nguoi ban|nha cung cap|khoan|khach)', q)
    return NUM_WORDS[m.group(1)] if m else None


def seller(q: str, invoices) -> tuple[str | None, str | None]:
    """A seller named in the question by tax id, or by at least one distinctive name word (two when the word is short)."""
    sellers = {}
    for i in invoices:
        if i.role == 'PURCHASE' and i.seller_tax_id:
            sellers.setdefault(i.seller_tax_id, i.seller_name or '')
    for t in re.findall(r'\d{10}(?:-\d{3})?', q):
        if t in sellers:
            return t, sellers[t]
    best, score = None, 0
    qtext = f' {" ".join(re.findall(r"[a-z0-9]+", q))} '
    def name_words(name):
        t = f' {fold(name)} '
        for f in NAME_FORMS:
            t = t.replace(f' {f} ', ' | ')
        return [w for w in re.findall(r'[a-z0-9|]+', t) if (w == '|' or (w not in NAME_STOP and len(w) > 1))]
    names = {tax: name_words(name) for tax, name in sellers.items()}
    counts = {}
    for ws in names.values():
        for w in set(ws):
            counts[w] = counts.get(w, 0) + 1
    # words written right after "công ty", "nhà cung cấp", "người bán", "bên", "của hàng"
    named = set(re.findall(r'(?:cong ty|nha cung cap|nguoi ban|ben|cua hang|mua cua)\s+([a-z0-9]+)', q)) - {
        'minh', 'toi', 'chung', 'ta', 'nay', 'do', 'nao', 'ghi', 'co', 'da', 'khong', 'xuat', 'lap', 'ban', 'moi'}
    for tax, words in names.items():
        # an adjacent pair of the name's own words ("an khang", "phuong nam"), or one word unique to this seller written
        # right after "công ty" / "nhà cung cấp"; loose common words ("dien", "dung", "thanh") never identify a seller
        # a pair made only of everyday words does not name anyone: "chưa có" folds to the same "chua co" as "Sửa chữa Cơ khí"
        pairs = sum(f' {a} {b} ' in qtext for a, b in zip(words, words[1:])
                    if '|' not in (a, b) and not (a in COMMON_WORDS and b in COMMON_WORDS))
        single = sum(1 for w in words if w != '|' and len(w) >= 3 and counts[w] == 1 and w in named)
        s = pairs * 2 + single
        if s > score:
            best, score = tax, s
    return (best, sellers.get(best)) if best else (None, None)


def issue(q: str, catalog_issues: list) -> tuple[list, str | None]:
    best, n = None, 0
    for it in catalog_issues:
        hits = sum(w in q for w in it['words'])
        if hits > n:
            best, n = it, hits
    return (list(best['codes']), best['name']) if best else ([], None)


ABBREV = [(r'\bhd\b', 'hoa don'), (r'\bncc\b', 'nha cung cap'), (r'\bmst\b', 'ma so thue'), (r'\bgtgt\b', 'gia tri gia tang'),
          (r'\btndn\b', 'thu nhap doanh nghiep'), (r'\btncn\b', 'thu nhap ca nhan'), (r'\bdn\b', 'doanh nghiep'), (r'\bck\b', 'chuyen khoan'),
          (r'\bunc\b', 'uy nhiem chi'), (r'\bsk\b', 'sao ke'), (r'\bko\b|\bk\b|\bkh\b', 'khong')]
ABBREV_VI = [(r'\b[hH][đĐ]\b', 'hóa đơn'), (r'\b[nN][cC][cC]\b', 'nhà cung cấp'), (r'\b[mM][sS][tT]\b', 'mã số thuế'), (r'\b[gG][tT][gG][tT]\b', 'giá trị gia tăng'),
             (r'\b[tT][nN][dD][nN]\b', 'thu nhập doanh nghiệp'), (r'\b[tT][nN][cC][nN]\b', 'thu nhập cá nhân'), (r'\b[hH][dD]\b', 'hóa đơn'),
             (r'\b[kK][oO]\b', 'không'), (r'\b[cC][kK]\b', 'chuyển khoản')]


def expand(question: str) -> str:
    """Spell out the abbreviations accountants type (hđ, ncc, mst, gtgt, tndn, ck, ko), keeping the rest as written."""
    out = question
    for pat, rep in ABBREV_VI:
        out = re.sub(pat, rep, out)
    return out


def extract(question: str, report, catalog: dict, as_of: date) -> Params:
    q = fold(question)
    for pat, rep in ABBREV:
        q = re.sub(pat, rep, q)
    p = Params()
    p.period = period(q, report.invoices, as_of)
    p.invoice_numbers = invoice_numbers(q)
    known = {str(int(i.number)) for i in report.invoices if i.number and i.number.isdigit()}
    p.invoice_numbers_found = [n for n in p.invoice_numbers if n in known]
    p.tax_ids = re.findall(r'\d{10}(?:-\d{3})?', q)
    p.seller, p.seller_text = seller(q, report.invoices)
    p.top_n = top_n(q)
    p.issue, p.issue_name = issue(q, catalog.get('issues', []))
    if any(w in q for w in ('nhieu tien', 'gia tri', 'mua nhieu', 'lon nhat theo', 'doanh so', 'chi nhieu')):
        p.rank_by = 'amount'
    p.wants_law = any(w in q for w in LAW_CUES)
    return p
