"""Unverified e-invoice extraction scaffold; not an accounting-ledger adapter.

Tag reference: tax authority technical specification accompanying decision
1271/QD-CT (2025), Part II, section II. Real vendor exports are still needed.
Digital signatures, adjustments, currency conversion and tax validity are not
verified here. Posting/approval records cannot be inferred from invoice XML.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from defusedxml import ElementTree

from .base import Adapter


def number(text):
    if text == "":
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid XML numeric value: {text!r}") from exc
    if not value.is_finite():
        raise ValueError("XML numeric values must be finite")
    return value


class EInvoiceXMLAdapter(Adapter):
    def __init__(self, company_id):
        if not str(company_id).strip():
            raise ValueError("company_id is required; it is not inferred from the invoice")
        self.company_id = str(company_id)
        self.last_report = None

    def load(self, path):
        path = Path(path)
        files = sorted(path.glob("*.xml")) if path.is_dir() else [path]
        invoices, lines, seen = [], [], set()
        for source in files:
            root = ElementTree.parse(source).getroot()
            for node in root.iter():
                node.tag = node.tag.rsplit("}", 1)[-1]
            for invoice in root.iter("HDon"):
                data = invoice.find("DLHDon")
                if data is None:
                    raise ValueError("HDon requires DLHDon")

                def text(selector, node=data):
                    return (node.findtext(selector) or "").strip()

                tax = text("NDHDon/NBan/MST")
                series, serial = text("TTChung/KHHDon"), text("TTChung/SHDon")
                issued = text("TTChung/NLap")
                if not all((tax, series, serial, issued)):
                    raise ValueError("invoice requires seller tax code, series, number and issue date")
                pd.Timestamp(issued)  # Reject an invalid date without inventing posting time.
                invoice_id = "|".join((tax, series, serial, issued))
                if invoice_id in seen:
                    raise ValueError(f"duplicate invoice: {invoice_id}")
                seen.add(invoice_id)
                invoices.append(dict(company_id=self.company_id, invoice_id=invoice_id, seller_tax_code=tax,
                                     buyer_tax_code=text("NDHDon/NMua/MST"), invoice_series=series,
                                     invoice_number=serial, invoice_issued_at=issued, currency=text("TTChung/DVTTe"),
                                     invoice_net_vnd=number(text("NDHDon/TToan/TgTCThue")),
                                     invoice_vat_vnd=number(text("NDHDon/TToan/TgTThue")),
                                     invoice_gross_vnd=number(text("NDHDon/TToan/TgTTTBSo")),
                                     source_file=source.name, source_version=text("TTChung/PBan")))
                # Preserve the document currency; columns ending _vnd are only
                # permitted when the source explicitly states VND.
                if invoices[-1]["currency"] != "VND":
                    raise ValueError("only explicit VND invoices are supported; no implicit conversion")
                for ordinal, item in enumerate(data.findall("NDHDon/DSHHDVu/HHDVu"), 1):
                    lines.append(dict(company_id=self.company_id, invoice_id=invoice_id,
                                      line_id=f"{invoice_id}|{ordinal}", line_number=text("STT", item),
                                      item_id=text("MHHDVu", item), description=text("THHDVu", item),
                                      quantity=number(text("SLuong", item)), unit_price_vnd=number(text("DGia", item)),
                                      net_amount_vnd=number(text("ThTien", item)), vat_rate=text("TSuat", item)))
        if not invoices:
            raise ValueError("no supported HDon records found")
        self.last_report = {"status": "unverified", "invoices": len(invoices), "invoice_lines": len(lines),
                            "missing_ledger": True, "signature_verified": False,
                            "real_vendor_sample_verified": False}
        return {"invoices": pd.DataFrame(invoices), "invoice_lines": pd.DataFrame(lines)}
