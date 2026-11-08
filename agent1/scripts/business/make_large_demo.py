"""Large deterministic fictional SME demo; never production training evidence."""

import csv, json, sys, math
from pathlib import Path
from datetime import date, timedelta
from calendar import monthrange
from collections import Counter
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.data import validate_dataset, observed
from agent1.adaptive.methods import forecast

END = date(2026, 10, 31)
OUT = ROOT / "pilot/demo_dai_phat"
WEB = ROOT / "agent1_service/ui/workspace"


def build():
    data = {
        k: []
        for k in ["invoices", "bank", "payments", "statements", "outflows", "actions"]
    }
    cases = {}

    def bank(day, direction, amount, component="other"):
        key = f"DP-B{len(data['bank']) + 1:06}"
        data["bank"].append(
            dict(
                bank_id=key,
                account="DP-VND01",
                date=str(day),
                direction=direction,
                amount=int(amount),
                known_at=str(day),
                component=component,
            )
        )
        return key

    def action(iid, day, kind, promise=None):
        if day > END:
            return
        r = dict(
            event_id=f"DP-A{len(data['actions']) + 1:06}",
            invoice_id=iid,
            date=str(day),
            known_at=str(day),
            kind=kind,
        )
        if promise:
            r["promise_date"] = str(promise)
        data["actions"].append(r)

    for year in range(2015, 2027):
        for month in range(1, 13):
            if date(year, month, 1) > END:
                break
            for j in range(90):
                issued = date(year, month, 1 + j % 28)
                due = issued + timedelta(days=[15, 30, 45, 60][j % 4])
                iid = f"DEMO_DP{year}{month:02}{j:03}"
                amount = (8 + (j * 17 + month * 3) % 65) * 1_000_000
                customer = f"DP-KH{(j + month * 7) % 120 + 1:03}"
                kind = [
                    "Đúng hạn",
                    "Trả sớm",
                    "Chậm 7 ngày",
                    "Chậm 30 ngày",
                    "Trả từng phần",
                    "Tranh chấp đã xử lý",
                    "Xóa nợ",
                    "Chậm trên 90 ngày",
                    "Lời hứa trả",
                    "Chưa thu một phần",
                ][j % 10]
                data["invoices"].append(
                    dict(
                        invoice_id=iid,
                        customer_id=customer,
                        issue_date=str(issued),
                        due_date=str(due),
                        amount=amount,
                        currency="VND",
                        known_at=str(issued),
                    )
                )
                cases[iid] = kind
                lag = [0, -5, 7, 30, 21, 60, 240, 125, 14, 150][j % 10]
                if year >= 2026 and customer in ["DP-KH004", "DP-KH005", "DP-KH006"]:
                    lag += 35
                paid = due + timedelta(days=lag)
                parts = [(paid, amount)]
                if j % 10 in [4, 9]:
                    parts = [
                        (issued + timedelta(days=10), int(amount * 0.3)),
                        (due + timedelta(days=20), int(amount * 0.3)),
                        (paid, amount - int(amount * 0.3) * 2),
                    ]
                if j % 10 == 6:
                    parts = []
                    action(iid, issued + timedelta(days=250), "write_off")
                if j % 10 == 5:
                    action(iid, due, "dispute")
                    action(iid, paid, "resolved")
                if j % 10 == 8:
                    action(
                        iid, due, "promise", due + timedelta(days=14 if j % 3 else 7)
                    )
                if j % 10 == 9 and year == 2026:
                    parts = parts[:1]
                for day, value in parts:
                    if day > END:
                        continue
                    ref = bank(day, "in", value)
                    data["payments"].append(
                        dict(
                            payment_id=f"P-{ref}",
                            invoice_id=iid,
                            payment_date=str(day),
                            known_at=str(day),
                            amount=value,
                            bank_id=ref,
                        )
                    )
    # Regular weekly operating cash, fully reconciled; seasonality and a visible 2026 shift.
    day = date(2015, 1, 2)
    while day <= END:
        seasonal = 1 + 0.25 * math.sin(day.timetuple().tm_yday / 365 * 2 * math.pi)
        bank(day, "in", round(85_000_000 * seasonal), "cash_sale")
        bank(
            day,
            "out",
            round(65_000_000 * seasonal * (1.2 if day.year == 2026 else 1)),
            "variable_cost",
        )
        day += timedelta(days=7)
    for i in range(6):
        bank(END - timedelta(days=i), "in", (i + 1) * 2_000_000)
    balance = 500_000_000
    for year in range(2015, 2027):
        for month in range(1, 13):
            start = date(year, month, 1)
            end = date(year, month, monthrange(year, month)[1])
            if end > END:
                break
            movement = sum(
                r["amount"] * (1 if r["direction"] == "in" else -1)
                for r in data["bank"]
                if str(start) <= r["date"] <= str(end)
            )
            # Supplier settlement keeps operating balances plausible rather than accumulating 12 years of receipts.
            target = (
                425_000_000 if end == END else 500_000_000 + (month % 3) * 40_000_000
            )
            payout = balance + movement - target
            if payout > 0:
                bank(end, "out", payout)
            closing = balance + movement - max(0, payout)
            data["statements"].append(
                dict(
                    statement_id=f"DP-S{year}{month:02}",
                    account="DP-VND01",
                    start_date=str(start),
                    end_date=str(end),
                    opening_balance=balance,
                    closing_balance=closing,
                    known_at=str(end),
                )
            )
            balance = closing
    for week in range(1, 14):
        for label, value in [
            ("variable_cost", 65_000_000),
            ("Lương và nhà cung cấp", 100_000_000 if week % 4 else 320_000_000),
        ]:
            data["outflows"].append(
                dict(
                    expense_id=f"DP-O{len(data['outflows']) + 1}",
                    date=str(END + timedelta(days=7 * week)),
                    known_at=str(END),
                    amount=value,
                    category=label,
                )
            )
    data["outflows"].append(
        dict(
            expense_id="DP-DEBT",
            date="2026-12-15",
            known_at=str(END),
            amount=1_500_000_000,
            category="Đáo hạn khoản vay",
        )
    )
    validate_dataset(data)
    ledger = observed(data, str(END))
    opened = ledger[(ledger.remaining_amount > 0.01) & ledger.written_off_at.isna()]
    for n, row in enumerate(opened.tail(12).itertuples()):
        action(row.invoice_id, END, ["contact", "skip", "dispute"][n % 3])
    validate_dataset(data)
    plans = {
        "base": forecast(data, str(END), balance, cash_floor=200_000_000),
        "delay": forecast(
            data, str(END), balance, delay_days=28, cash_floor=200_000_000
        ),
        "cost": forecast(
            data, str(END), balance, expense_multiplier=1.3, cash_floor=200_000_000
        ),
        "shared": forecast(
            data, str(END), balance, shared_customer_risk=True, cash_floor=200_000_000
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    files = []
    for n, (kind, rows) in enumerate(data.items(), 1):
        path = OUT / f"{n:02}_{kind}.csv"
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        files.append(path)
    counts = {k: len(v) for k, v in data.items()}
    report = dict(
        company="Đại Phát — doanh nghiệp mô phỏng",
        synthetic=True,
        cutoff=str(END),
        counts=counts,
        customers=120,
        opening_balance=balance,
        open_invoices=len(opened),
        cases=dict(Counter(cases.values())),
        validation="validate_dataset passed; reconciled all statement periods",
        training="Preview uses the baseline. Training is available in a DEMO_ workspace started with -DemoTraining.",
        scope="VND, one bank account. Does not cover FX, tax compliance, or every real-world case.",
    )
    (OUT / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    bad = OUT / "invalid_cases"
    bad.mkdir(exist_ok=True)
    for label, mut in [
        ("due_before_issue", {"due_date": "2010-01-01"}),
        ("negative_amount", {"amount": -1}),
        ("unsupported_currency", {"currency": "USD"}),
    ]:
        row = {**data["invoices"][0], **mut}
        with (bad / f"{label}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=row)
            w.writeheader()
            w.writerow(row)
    with ZipFile(WEB / "demo-dai-phat.zip", "w", ZIP_DEFLATED) as z:
        for p in [
            *files,
            OUT / "manifest.json",
            OUT / "README.md",
            OUT / "README.txt",
            *sorted(bad.glob("*.csv")),
        ]:
            z.write(p, p.relative_to(OUT))
    with ZipFile(WEB / "demo-dai-phat-input-train.zip", "w", ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)
        z.write(ROOT / "docs/06_Pilot/DEMO_INPUT_TRAIN_DAIPHAT.md", "00_HUONG_DAN.md")
    inv = [
        dict(
            invoice_id=r.invoice_id,
            customer_id=r.customer_id,
            due_date=str(r.due_date.date()),
            amount=r.amount,
            remaining=r.remaining_amount,
            case=cases[r.invoice_id],
            written_off=bool(not __import__("pandas").isna(r.written_off_at)),
        )
        for r in ledger.sort_values("issue_date", ascending=False).itertuples()
    ]
    payload = dict(
        manifest=report,
        invoices=inv,
        bank=sorted(data["bank"], key=lambda r: r["date"], reverse=True),
        actions=data["actions"],
        plans=plans,
    )
    (WEB / "dai-phat-data.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    build()
