"""T0 — Hoá đơn điện tử XML theo cấu trúc QĐ 1450/QĐ-TCT (sửa đổi QĐ 1510/QĐ-TCT), tập con các trường
cần cho Agent 1: HDon/DLHDon/{TTChung, NDHDon/{NBan, NMua, DSHHDVu, TToan}}.
Máy phát ghi XML; bộ phân tích đọc XML về lược đồ chuẩn (một nguồn - hai góc nhìn)."""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd


def _sub(parent, tag, text=None):
    e = ET.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


def invoice_to_xml(inv: pd.Series, seller: pd.Series, buyer: pd.Series) -> bytes:
    root = ET.Element("HDon")
    dl = _sub(root, "DLHDon", None)
    dl.set("Id", str(inv["invoice_id"]))
    tt = _sub(dl, "TTChung")
    _sub(tt, "PBan", "2.0.0")
    _sub(tt, "THDon", "HÓA ĐƠN GIÁ TRỊ GIA TĂNG")
    _sub(tt, "KHMSHDon", "1")
    _sub(tt, "KHHDon", inv["symbol"])
    _sub(tt, "SHDon", inv["invoice_no"])
    _sub(tt, "NLap", pd.Timestamp(inv["issue_date"]).strftime("%Y-%m-%d"))
    _sub(tt, "DVTTe", inv.get("currency", "VND"))
    _sub(tt, "TGia", "1")
    _sub(tt, "HTTToan", "TM/CK" if inv["term_days"] == 0 else "CK")
    nd = _sub(dl, "NDHDon")
    nb = _sub(nd, "NBan")
    _sub(nb, "Ten", seller["name"])
    _sub(nb, "MST", seller["mst"])
    nmua = _sub(nd, "NMua")
    _sub(nmua, "Ten", buyer["name"])
    _sub(nmua, "MST", buyer["mst"])
    ds = _sub(nd, "DSHHDVu")
    h = _sub(ds, "HHDVu")
    _sub(h, "STT", 1)
    _sub(h, "THHDVu", "Hàng hoá theo hợp đồng")
    _sub(h, "ThTien", int(inv["amount_net"]))
    _sub(h, "TSuat", f"{int(round(inv['vat_rate'] * 100))}%")
    tto = _sub(nd, "TToan")
    vat = int(round(inv["amount_gross"] - inv["amount_net"]))
    _sub(tto, "TgTCThue", int(inv["amount_net"]))
    _sub(tto, "TgTThue", vat)
    _sub(tto, "TgTTTBSo", int(inv["amount_gross"]))
    # trường mở rộng (TTKhac) — hạn thanh toán theo hợp đồng, không bắt buộc trong chuẩn
    tk = _sub(tt, "TTKhac")
    t = _sub(tk, "TTin")
    _sub(t, "TTruong", "HanThanhToan")
    _sub(t, "DLieu", pd.Timestamp(inv["due_date"]).strftime("%Y-%m-%d"))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_xml_samples(invoices: pd.DataFrame, firms: pd.DataFrame, customers: pd.DataFrame, out_dir: Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    f = firms.set_index("firm_id")
    c = customers.set_index("customer_id")
    for _, inv in invoices.iterrows():
        x = invoice_to_xml(inv, f.loc[inv["firm_id"]], c.loc[inv["customer_id"]])
        (out_dir / f"{inv['invoice_id']}.xml").write_bytes(x)


def parse_xml(path) -> dict:
    root = ET.parse(path).getroot()
    g = lambda p: (root.find(p).text if root.find(p) is not None else None)  # noqa: E731
    due = None
    for t in root.iter("TTin"):
        if t.findtext("TTruong") == "HanThanhToan":
            due = t.findtext("DLieu")
    return dict(
        invoice_key=root.find("DLHDon").get("Id"), symbol=g("DLHDon/TTChung/KHHDon"), invoice_no=g("DLHDon/TTChung/SHDon"),
        issue_date=g("DLHDon/TTChung/NLap"), currency=g("DLHDon/TTChung/DVTTe"), seller_mst=g("DLHDon/NDHDon/NBan/MST"),
        buyer_mst=g("DLHDon/NDHDon/NMua/MST"), buyer_name=g("DLHDon/NDHDon/NMua/Ten"),
        amount_net=float(g("DLHDon/NDHDon/TToan/TgTCThue")), vat=float(g("DLHDon/NDHDon/TToan/TgTThue")),
        amount_gross=float(g("DLHDon/NDHDon/TToan/TgTTTBSo")), due_date=due,
    )
