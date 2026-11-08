"""Ẩn danh bằng HMAC-SHA256 ở bước nạp (cam kết bảo mật, docs/06_Pilot/02_CAM_KET_BAO_MAT.md Điều 3.4).

Hai cách, để KHÔNG phá việc ghép sao kê T9 (so khớp gần đúng tên người chuyển với tên khách, đọc số hoá đơn trong nội dung CK):
- Mã định danh (mã khách, MST): băm nguyên chuỗi ⇒ cùng giá trị ⇒ cùng mã, ở mọi bảng.
- Tên và nội dung CK: chuẩn hoá giống T9 (`norm_name`: bỏ dấu, viết hoa, bỏ tiền tố pháp lý) rồi băm TỪNG TỪ.
  Hai tên chung một từ vẫn chung một mã ⇒ so khớp gần đúng vẫn chạy. Mã chỉ gồm chữ cái (không chữ số) để bộ đọc số hoá đơn
  không nhặt nhầm. Trong nội dung CK, từ có chữ số (số hoá đơn, tiền tố ngân hàng như `MBVCB.123.456.`) và từ thanh toán chung (TT, HD, CK...)
  được GIỮ nguyên; các từ chữ còn lại (thường là tên người/công ty) bị băm.
Băm một chiều: Bên B không đảo ngược được. Bảng đối chiếu mã ↔ tên chỉ dựng được khi có khoá (do Bên A giữ bản sao, xem `pseudonym_map`).
"""
import hashlib
import hmac

from agent1.models.t9_recon import norm_name

LETTERS = "abcdefghijklmnop"          # 16 chữ cái ⇒ mỗi nửa byte một chữ, không có chữ số
ID_FIELDS = {"customer_id", "mst", "buyer_mst", "seller_mst", "true_customer_id"}
NAME_FIELDS = {"name", "short", "counterparty", "buyer_name"}
MEMO_FIELDS = {"memo"}
MEMO_KEEP = {"TT", "THANH", "TOAN", "HD", "HOA", "DON", "CK", "CHUYEN", "KHOAN", "TIEN", "HANG", "TRA", "NO", "CONG",
             "THEO", "SO", "VE", "CHO", "DOT", "LAN", "PHAN", "CON", "LAI", "NOP", "TAI", "VA", "CUA", "INV", "INVOICE",
             "PAYMENT", "PAY", "FOR", "REF", "GD", "IBFT", "NAPAS", "QR", "MUA", "BAN", "DV", "PHI", "THU", "UNG", "TRUOC"}


def _check(key):
    if not key or len(key) < 32:
        raise ValueError('Khoá HMAC cần ít nhất 32 byte')


def anonymize(value, key, namespace='party'):
    _check(key)
    return hmac.new(key, (namespace + '|' + str(value)).encode('utf-8'), hashlib.sha256).hexdigest()


def _letters(digest, n):
    return "".join(LETTERS[b >> 4] + LETTERS[b & 15] for b in digest)[:n]


def pseudo_id(value, key):
    _check(key)
    return "k" + _letters(hmac.new(key, ("id|" + str(value)).encode("utf-8"), hashlib.sha256).digest(), 16)


def _token(word, key):
    return "x" + _letters(hmac.new(key, ("tok|" + word).encode("utf-8"), hashlib.sha256).digest(), 8)


def pseudo_name(text, key):
    _check(key)
    return " ".join(_token(w, key) for w in norm_name(str(text)).split())


def pseudo_memo(text, key):
    _check(key)
    out = []
    for w in norm_name(str(text)).split():
        out.append(w if (any(c.isdigit() for c in w) or w in MEMO_KEEP) else _token(w, key))
    return " ".join(out)


def pseudonymize_row(row, key):
    """Trả bản sao đã ẩn danh của một bản ghi nạp vào (mọi bảng). Giá trị rỗng giữ nguyên."""
    out = dict(row)
    for col, value in row.items():
        if value is None or value == "":
            continue
        if col in ID_FIELDS:
            out[col] = pseudo_id(value, key)
        elif col in NAME_FIELDS:
            out[col] = pseudo_name(value, key)
        elif col in MEMO_FIELDS:
            out[col] = pseudo_memo(value, key)
    return out


def pseudonym_map(customers, key):
    """Bảng đối chiếu cho Bên A (người giữ khoá): mã khách gốc/tên gốc → mã ẩn danh. Không lưu ở phía Bên B."""
    return [dict(customer_id=r.get("customer_id"), name=r.get("name") or r.get("short"),
                 pseudo_customer_id=pseudo_id(r.get("customer_id"), key)) for r in customers]
