"""Thực thể Việt Nam cho máy phát: tên doanh nghiệp, MST có chữ số kiểm tra, ký hiệu hoá đơn điện tử,
tên đối tác và nội dung chuyển khoản theo kiểu sao kê ngân hàng VN (không dấu, viết tắt, cắt cụt, lỗi gõ)."""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np

try:
    from unidecode import unidecode
except ImportError:  # pragma: no cover
    import unicodedata

    def unidecode(s):
        s = s.replace("Đ", "D").replace("đ", "d")
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()

LEGAL = [("CÔNG TY TNHH", "CTY TNHH", 0.62), ("CÔNG TY CỔ PHẦN", "CTY CP", 0.30),
         ("DOANH NGHIỆP TƯ NHÂN", "DNTN", 0.05), ("HỘ KINH DOANH", "HKD", 0.03)]
SECTOR_WORD = {
    "steel_metals": ["THÉP", "KIM KHÍ", "SẮT THÉP", "CƠ KHÍ", "VẬT LIỆU XÂY DỰNG", "INOX"],
    "textile_clothing": ["DỆT MAY", "MAY MẶC", "SỢI", "THỜI TRANG", "VẢI", "MAY XUẤT KHẨU"],
    "plastic_rubber": ["NHỰA", "BAO BÌ", "CAO SU", "BAO BÌ NHỰA", "HẠT NHỰA"],
    "wholesale": ["THƯƠNG MẠI", "THƯƠNG MẠI DỊCH VỤ", "XUẤT NHẬP KHẨU", "PHÂN PHỐI"],
    "food_processing": ["THỰC PHẨM", "NÔNG SẢN", "CHẾ BIẾN THỰC PHẨM", "THỦY SẢN"],
    "services": ["DỊCH VỤ", "CÔNG NGHỆ", "VẬN TẢI", "LOGISTICS", "TƯ VẤN", "XÂY DỰNG"],
}
CORE = ["HOÀNG PHÁT", "MINH ANH", "TÂN THÀNH", "PHÚ AN", "ĐẠI DƯƠNG", "AN KHANG", "THÀNH ĐẠT", "VIỆT TIẾN",
        "HƯNG THỊNH", "NAM PHONG", "BẢO NGỌC", "TRƯỜNG SƠN", "KIM LONG", "PHƯƠNG ĐÔNG", "HẢI ĐĂNG", "QUANG MINH",
        "THIÊN PHÚ", "ĐỨC TRÍ", "HÒA BÌNH", "SAO VIỆT", "ÁNH DƯƠNG", "TÍN NGHĨA", "LỘC PHÁT", "PHÚC HƯNG",
        "THUẬN PHÁT", "VẠN XUÂN", "ĐÔNG Á", "NHẬT QUANG", "GIA HUY", "KHÁNH AN", "HÀ THÀNH", "SÔNG HỒNG",
        "MÊ KÔNG", "ĐẠI PHÁT", "NGỌC LAN", "TRUNG KIÊN", "THÁI BÌNH", "VĨNH THỊNH", "TOÀN CẦU", "HỢP NHẤT",
        "BÌNH MINH", "TÂN Á", "LIÊN VIỆT", "SƠN HÀ", "HOÀN CẦU", "ĐỒNG TÂM", "MINH KHAI", "PHÚ THỊNH",
        "THẮNG LỢI", "HẢI NAM", "CƯỜNG THỊNH", "THÀNH CÔNG", "HUY HOÀNG", "NHƯ Ý", "TẤN PHÁT", "AN PHÚ"]
SUFFIX = ["", "", "", " VIỆT NAM", " SÀI GÒN", " MIỀN BẮC", " MIỀN NAM", " HÀ NỘI", " QUỐC TẾ", " GROUP"]
PROVINCE_PREFIX = ["01", "03", "02", "04", "37", "36", "23", "31", "38", "34", "08", "27", "25", "33"]
BANKS = ["VCB", "BIDV", "CTG", "TCB", "MBB", "ACB", "VPB", "STB", "TPB", "HDB", "VIB", "SHB", "MSB", "OCB"]
MST_W = np.array([31, 29, 23, 19, 17, 13, 7, 5, 3])


def mst_check_digit(first9: str) -> int | None:
    s = int((np.array([int(c) for c in first9]) * MST_W).sum())
    c = 10 - (s % 11)
    return c if 0 <= c <= 9 else None


def make_mst(rng) -> str:
    while True:
        first9 = rng.choice(PROVINCE_PREFIX) + "".join(str(x) for x in rng.integers(0, 10, 7))
        c = mst_check_digit(first9)
        if c is not None:
            return first9 + str(c)


def valid_mst(m: str) -> bool:
    m = re.sub(r"\D", "", str(m))[:10]
    return len(m) == 10 and mst_check_digit(m[:9]) == int(m[9])


def make_company_name(rng, sector: str, used: set) -> tuple[str, str, str]:
    """-> (tên đầy đủ có dấu, tên viết tắt pháp lý, tên ngắn giao dịch)."""
    for _ in range(1000):
        li = rng.choice(len(LEGAL), p=[x[2] for x in LEGAL])
        full_l, short_l, _ = LEGAL[li]
        core = rng.choice(CORE)
        sec = rng.choice(SECTOR_WORD.get(sector, SECTOR_WORD["wholesale"]))
        suf = rng.choice(SUFFIX)
        order = rng.random()
        mid = f"{sec} {core}" if order < 0.6 else f"{core}"
        name = f"{full_l} {mid}{suf}".strip()
        if name not in used:
            used.add(name)
            short = f"{short_l} {mid}{suf}".strip()
            return name, short, core
    raise RuntimeError("name space exhausted")


@lru_cache(maxsize=16384)
def ascii_upper(s: str) -> str:
    return unidecode(s).upper()


def counterparty_variant(rng, full: str, short: str) -> str:
    """Tên đối tác hiện trên sao kê: không dấu, viết tắt, cắt 50 ký tự, đôi khi trống."""
    r = rng.random()
    if r < 0.04:
        return ""
    base = ascii_upper(full if r < 0.55 else short)
    if rng.random() < 0.15:
        base = base.replace("CONG TY", "CT").replace("TRACH NHIEM HUU HAN", "TNHH")
    return base[:50]


def _typo(rng, s: str, p=0.04) -> str:
    if len(s) < 6 or rng.random() > p:
        return s
    i = rng.integers(1, len(s) - 1)
    return s[:i] + s[i + 1:] if rng.random() < 0.5 else s[:i] + s[i + 1] + s[i] + s[i + 2:]


def transfer_memo(rng, payer_short: str, payee_core: str, invoice_nos: list[str], month: int, style: float) -> str:
    """Nội dung chuyển khoản. style: xác suất khách ghi số hoá đơn (đặc trưng theo khách)."""
    p = ascii_upper(payer_short)
    p_core = p.replace("CTY TNHH ", "").replace("CTY CP ", "").replace("DNTN ", "").replace("HKD ", "")
    with_no = rng.random() < style and invoice_nos
    nos = []
    if with_no:
        for n in invoice_nos[: rng.integers(1, 6)]:
            nos.append(n.lstrip("0") if rng.random() < 0.45 else n)
        sep = rng.choice([" ", ",", ", ", "+", " VA "])
        nos_s = sep.join(nos)
        tpl = rng.choice([
            f"{p_core} TT HD {nos_s}", f"{p} THANH TOAN HD SO {nos_s}", f"TT TIEN HANG HD {nos_s}",
            f"{p_core} THANH TOAN TIEN HANG THEO HOA DON {nos_s}", f"IBFT {p_core} TT HD{nos_s}",
            f"{p_core} CK TT HDON {nos_s} CHO {ascii_upper(payee_core)}", f"HD{nos_s} {p_core}",
        ])
    else:
        tpl = rng.choice([
            f"{p_core} THANH TOAN TIEN HANG", f"TT TIEN HANG T{month}", f"{p} CHUYEN TIEN",
            f"CK {p_core}", f"{p_core} TRA TIEN HANG CHO {ascii_upper(payee_core)}", "THANH TOAN CONG NO",
            f"{p_core} TT CONG NO THANG {month}", f"TRA NO {ascii_upper(payee_core)}", f"{p_core} CHUYEN KHOAN",
        ])
    pre = rng.random()
    if pre < 0.25:
        tpl = f"MB{rng.choice(BANKS)}.{rng.integers(10**6, 10**7)}.{rng.integers(10**5, 10**6)}.{tpl}"
    elif pre < 0.40:
        tpl = f"FT{rng.integers(10**4, 10**5)}{''.join(rng.choice(list('ABCDEFGHJK'), 5))} {tpl}"
    tpl = _typo(rng, tpl)
    return tpl[: rng.choice([70, 140, 210], p=[0.25, 0.6, 0.15])]


def einvoice_symbol(year: int, rng, kind="T") -> str:
    """Ký hiệu hoá đơn TT78: C/K (có mã/không mã) + 2 số năm + loại (T: DN đăng ký) + 2 chữ do DN tự đặt."""
    return f"{'C' if rng.random() < 0.85 else 'K'}{year % 100:02d}{kind}{''.join(rng.choice(list('ABCDEGHKLMNPQRSTUVXY'), 2))}"
