"""T0 — Hoá đơn điện tử XML theo cấu trúc QĐ 1450/QĐ-TCT (sửa đổi QĐ 1510/QĐ-TCT), tập con các trường
cần cho Agent 1: HDon/DLHDon/{TTChung, NDHDon/{NBan, NMua, DSHHDVu, TToan}}.
Máy phát ghi XML; bộ phân tích đọc XML về lược đồ chuẩn (một nguồn - hai góc nhìn)."""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET
from defusedxml import ElementTree as SafeET

import pandas as pd


def _sub(parent, tag, text=None):
    e = ET.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


def _format_vat_label(rate) -> str:
    if isinstance(rate, str):
        s = rate.strip().upper()
        if s in {"KCT", "KKKNT"} or s.endswith("%"):
            return s
        return f"{int(round(float(s) * 100))}%"
    return f"{int(round(float(rate) * 100))}%"


def invoice_to_xml(inv: pd.Series, seller: pd.Series, buyer: pd.Series) -> bytes:
    root = ET.Element("HDon")
    dl = _sub(root, "DLHDon", None)
    dl.set("Id", str(inv["invoice_id"]))
    tt = _sub(dl, "TTChung")
    _sub(tt, "PBan", str(inv.get("document_version") or "2.0.0"))
    _sub(tt, "THDon", "HÓA ĐƠN GIÁ TRỊ GIA TĂNG")
    _sub(tt, "KHMSHDon", "1")
    _sub(tt, "KHHDon", inv["symbol"])
    _sub(tt, "SHDon", inv["invoice_no"])
    _sub(tt, "NLap", pd.Timestamp(inv["issue_date"]).strftime("%Y-%m-%d"))
    _sub(tt, "DVTTe", inv.get("currency", "VND"))
    _sub(tt, "TGia", "1")
    term_days = inv.get("term_days")
    _sub(tt, "HTTToan", inv.get("payment_method") or ("TM/CK" if term_days == 0 else "CK"))
    nd = _sub(dl, "NDHDon")
    nb = _sub(nd, "NBan")
    _sub(nb, "Ten", seller["name"])
    _sub(nb, "MST", seller["mst"])
    nmua = _sub(nd, "NMua")
    _sub(nmua, "Ten", buyer["name"])
    _sub(nmua, "MST", buyer["mst"])
    ds = _sub(nd, "DSHHDVu")
    line_items = inv.get("line_items")
    if isinstance(line_items, (list, tuple)) and line_items:
        for idx, item in enumerate(line_items, 1):
            h = _sub(ds, "HHDVu")
            _sub(h, "STT", idx)
            _sub(h, "THHDVu", item.get("description", f"Hàng hoá dòng {idx}"))
            _sub(h, "ThTien", int(round(item["amount_net"])))
            _sub(h, "TSuat", _format_vat_label(item["vat_rate"]))
    else:
        h = _sub(ds, "HHDVu")
        _sub(h, "STT", 1)
        _sub(h, "THHDVu", "Hàng hoá theo hợp đồng")
        _sub(h, "ThTien", int(inv["amount_net"]))
        _sub(h, "TSuat", _format_vat_label(inv.get("vat_rate", 0.10)))
    tto = _sub(nd, "TToan")
    vat_breakdown = inv.get("vat_breakdown")
    if isinstance(vat_breakdown, (list, tuple)) and vat_breakdown:
        thtt = _sub(tto, "THTTLTSuat")
        for item in vat_breakdown:
            lt = _sub(thtt, "LTSuat")
            _sub(lt, "TSuat", _format_vat_label(item["vat_rate"]))
            _sub(lt, "ThTien", int(round(item["amount_net"])))
            _sub(lt, "TThue", int(round(item.get("vat", 0))))
    vat = int(round(inv["vat"])) if "vat" in inv and pd.notna(inv["vat"]) else int(round(inv["amount_gross"] - inv["amount_net"]))
    _sub(tto, "TgTCThue", int(inv["amount_net"]))
    _sub(tto, "TgTThue", vat)
    _sub(tto, "TgTTTBSo", int(inv["amount_gross"]))
    # trường mở rộng (TTKhac) — hạn thanh toán theo hợp đồng, không bắt buộc trong chuẩn QĐ 1450
    due_val = inv.get("due_date")
    if due_val is not None and pd.notna(due_val) and str(due_val).strip() != "":
        tk = _sub(tt, "TTKhac")
        t = _sub(tk, "TTin")
        _sub(t, "TTruong", "HanThanhToan")
        _sub(t, "DLieu", pd.Timestamp(due_val).strftime("%Y-%m-%d"))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_xml_samples(invoices: pd.DataFrame, firms: pd.DataFrame, customers: pd.DataFrame, out_dir: Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    f = firms.set_index("firm_id")
    c = customers.set_index("customer_id")
    for _, inv in invoices.iterrows():
        x = invoice_to_xml(inv, f.loc[inv["firm_id"]], c.loc[inv["customer_id"]])
        (out_dir / f"{inv['invoice_id']}.xml").write_bytes(x)


def parse_xml(path, *, default_payment_terms_days: int = 30) -> dict:
    raw = path if isinstance(path, bytes) else Path(path).read_bytes()
    root = SafeET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    for el in root.iter():
        el.tag = el.tag.split("}")[-1]
    g = lambda p: (root.find(p).text.strip() if root.find(p) is not None and root.find(p).text is not None else None)  # noqa: E731
    issue = g("DLHDon/TTChung/NLap")
    due = g("DLHDon/TTChung/HThanhToan") or g("DLHDon/TTChung/HanThanhToan")
    if not due:
        for t in root.iter("TTin"):
            if (t.findtext("TTruong") or "").strip() == "HanThanhToan":
                due = (t.findtext("DLieu") or "").strip() or None
                break
    if not due and issue:
        htt = (g("DLHDon/TTChung/HTTToan") or "").strip().upper()
        days = 0 if htt in {"TM", "TIỀN MẶT", "TIEN MAT"} else default_payment_terms_days
        due = (pd.Timestamp(issue) + pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    dl = root.find("DLHDon")
    symbol = g("DLHDon/TTChung/KHHDon")
    invoice_no = g("DLHDon/TTChung/SHDon")
    seller_mst = g("DLHDon/NDHDon/NBan/MST")
    buyer_mst = g("DLHDon/NDHDon/NMua/MST") or g("DLHDon/NDHDon/NMua/CCCDan")
    gross = float(g("DLHDon/NDHDon/TToan/TgTTTBSo"))
    vat_text = g("DLHDon/NDHDon/TToan/TgTThue")
    vat = float(vat_text) if vat_text else 0.0
    net_text = g("DLHDon/NDHDon/TToan/TgTCThue")
    net = float(net_text) if net_text else gross - vat
    rates = []
    for tag_path in (".//TToan/THTTLTSuat/LTSuat/TSuat", ".//DSHHDVu/HHDVu/TSuat"):
        for node in root.findall(tag_path):
            if node.text and node.text.strip() and node.text.strip() not in rates:
                rates.append(node.text.strip())
    out = dict(
        invoice_key=(dl.get("Id") if dl is not None else None) or f"{seller_mst}-{symbol}-{invoice_no}",
        symbol=symbol, invoice_no=invoice_no,
        issue_date=issue, currency=g("DLHDon/TTChung/DVTTe") or "VND", seller_mst=seller_mst,
        buyer_mst=buyer_mst, buyer_name=g("DLHDon/NDHDon/NMua/Ten") or g("DLHDon/NDHDon/NMua/HVTNMHang"),
        amount_net=net, vat=vat, amount_gross=gross, due_date=due,
    )
    if rates:
        out["vat_rates"] = ",".join(rates)
    return out
