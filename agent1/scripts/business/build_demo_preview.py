"""Render a public read-only preview strictly from the six fictional Minh An CSVs."""

import sys
from html import escape
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.data import (
    parse_rows,
    suggested_mapping,
    validate_dataset,
    observed,
)
from agent1.adaptive.methods import forecast


def money(v):
    return f"{v:,.0f}".replace(",", ".")


def table(headers, rows):
    def cells(tag, values):
        return "".join(f"<{tag}>{escape(str(value))}</{tag}>" for value in values)

    return (
        '<div class="scroll"><table><thead><tr>'
        + cells("th", headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + cells("td", r) + "</tr>" for r in rows)
        + "</tbody></table></div>"
    )


def main():
    data = {}
    for k, kind in enumerate(
        ("invoices", "bank", "payments", "statements", "outflows", "actions"), 1
    ):
        raw = pd.read_csv(ROOT / f"pilot/demo_minh_an/{k:02}_{kind}.csv", dtype=str)
        rows, errors, _ = parse_rows(raw, kind, suggested_mapping(raw.columns, kind))
        if errors:
            raise ValueError(errors[:2])
        data[kind] = rows
    validate_dataset(data)
    end = "2026-09-30"
    opening = data["statements"][-1]["closing_balance"]
    original = forecast(data, end, opening)
    delayed = forecast(data, end, opening, delay_days=14, delay_customer="MA-KH04")
    ledger = observed(data, end).sort_values("issue_date", ascending=False)

    def plan(p):
        return table(
            ["Tuần", "Đến ngày", "Dự thu", "Dự chi", "Số dư cuối tuần", "Lịch chi"],
            [
                (
                    w["week"],
                    w["date"],
                    money(w["cash_in"]),
                    money(w["cash_out"]),
                    money(w["balance"]),
                    "Có lịch"
                    if w["outflow_status"] == "scheduled"
                    else "Chưa xác nhận",
                )
                for w in p["weeks"]
            ],
        )

    invoices = table(
        ["Mã hóa đơn", "Khách", "Hạn trả", "Giá trị", "Còn phải thu"],
        [
            (
                r.invoice_id,
                r.customer_id,
                r.due_date.date(),
                money(r.amount),
                money(r.remaining_amount),
            )
            for r in ledger.itertuples()
        ],
    )
    linked = {}
    for p in data["payments"]:
        linked[p["bank_id"]] = linked.get(p["bank_id"], 0) + p["amount"]
    bank = sorted(data["bank"], key=lambda r: r["date"], reverse=True)
    pending = sum(
        r["amount"] - linked.get(r["bank_id"], 0)
        for r in bank
        if r["direction"] == "in" and r["component"] != "cash_sale"
    )
    statement = table(
        ["Ngày", "Giao dịch", "Thu", "Chi", "Đã ghép hóa đơn"],
        [
            (
                r["date"],
                r["bank_id"],
                money(r["amount"]) if r["direction"] == "in" else "—",
                money(r["amount"]) if r["direction"] == "out" else "—",
                money(linked[r["bank_id"]]) if r["bank_id"] in linked else "—",
            )
            for r in bank
        ],
    )
    s = f"""<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Minh An · Xem thử Agent1</title><link rel="stylesheet" href="minh-an.css"><header><b>Agent1 / Trợ lý dòng tiền</b><span>Minh An · Dữ liệu mô phỏng</span></header><div class="layout"><nav aria-label="Sổ Minh An"><a href="#tong-quan">Tổng quan</a><a href="#hoa-don">Hóa đơn</a><a href="#ngan-hang">Ngân hàng</a><a href="#du-bao">Dự báo &amp; kịch bản</a><a href="/workspace#overview">← Về doanh nghiệp của tôi</a></nav><main>
<section id="tong-quan"><h1>Công ty vật tư Minh An</h1><p>Sổ mẫu đến 30/09/2026 · 12 khách hàng · Đơn vị VND</p><div class="numbers"><div>Số dư ngân hàng<strong>{money(opening)}</strong></div><div>Công nợ còn mở<strong>{money(original["outstanding"])}</strong></div><div>Tiền về chưa ghép<strong>{money(pending)}</strong></div></div><h2>Kiểm tra sổ tháng 9</h2><p>Có {original["open_invoices"]} hóa đơn còn dư trên tổng số {len(ledger)} hóa đơn. Khoản thu {money(pending)} đồng ngày 30/09 đã vào ngân hàng và còn chờ phân bổ.</p><a href="#ngan-hang">Xem giao dịch ngân hàng →</a><h2>Tiền có về kịp lịch chi?</h2><p>Thử cho khách MA-KH04 trả chậm hai tuần để xem số dư từng tuần thay đổi bao nhiêu.</p><a href="#du-bao">Mở kế hoạch 13 tuần →</a></section>
<section id="hoa-don" hidden><h1>Sổ hóa đơn</h1><p>{len(ledger)} hóa đơn bán chịu, sắp theo ngày lập gần nhất. Số còn phải thu đã trừ những lần thanh toán được ghép.</p>{invoices}</section>
<section id="ngan-hang" hidden><h1>Sổ ngân hàng</h1><p>{len(bank)} giao dịch trên MA-TK01. Các khoản bán thu ngay được tính vào số dư và không cần ghép với hóa đơn công nợ.</p>{statement}</section>
<section id="du-bao" hidden><h1>Kế hoạch thu chi 13 tuần</h1><p>Từ ngày 01/10/2026. Thu từ công nợ đang mở; chi theo lịch đã khai báo. Tuần chưa xác nhận có thể phát sinh thêm chi phí.</p><label for="scenario">Kịch bản</label> <select id="scenario"><option value="base">Kế hoạch ban đầu</option><option value="stress">Khách MA-KH04 trả chậm 14 ngày</option></select><div id="base">{plan(original)}</div><div id="stress" hidden>{plan(delayed)}</div></section></main></div><script src="minh-an.js"></script></html>"""
    (ROOT / "agent1_service/ui/workspace/minh-an.html").write_text(s, encoding="utf-8")


if __name__ == "__main__":
    main()
