"""Build the Minh An SME rehearsal from deterministic, wholly fictional transactions."""

from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
import csv
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "pilot/demo_minh_an"
ARCHIVE = ROOT / "agent1_service/ui/workspace/demo-minh-an.zip"
CUTOFF = date(2026, 9, 30)


def build():
    invoices, bank, payments, statements, expenses, actions = [], [], [], [], [], []

    def txn(day, direction, amount, component="other"):
        key = f"MA-TX{len(bank) + 1:04}"
        bank.append(
            dict(
                bank_id=key,
                account="MA-TK01",
                date=day,
                direction=direction,
                amount=amount,
                known_at=day,
                component=component,
            )
        )
        return key

    for month in range(1, 10):
        for j in range(16):
            issued = date(2026, month, 1 + j * 1 if j < 8 else 10 + (j - 8) * 2)
            due = issued + timedelta(days=(15, 30, 45)[j % 3])
            iid = f"DEMO_MA{month:02}{j + 1:02}"
            amount = (6 + (j * 3 + month) % 12) * 1_000_000
            invoices.append(
                dict(
                    invoice_id=iid,
                    customer_id=f"MA-KH{j % 12 + 1:02}",
                    issue_date=issued,
                    due_date=due,
                    amount=amount,
                    currency="VND",
                    known_at=issued,
                )
            )
            settled = due + timedelta(days=(-3, 2, 6, 12, 21)[j % 5])
            parts = (
                [(settled, amount)]
                if j % 4
                else [(issued + timedelta(days=7), amount // 2), (settled, amount // 2)]
            )
            for day, money in parts:
                if day > CUTOFF:
                    continue
                ref = txn(day, "in", money)
                payments.append(
                    dict(
                        payment_id="P-" + ref,
                        invoice_id=iid,
                        payment_date=day,
                        amount=money,
                        bank_id=ref,
                        known_at=day,
                    )
                )
        txn(date(2026, month, 12), "in", 9_000_000, "cash_sale")
        for day, money, group in [
            (5, 12_000_000, "other"),
            (19, 68_000_000, "variable_cost"),
            (27, 52_000_000, "other"),
        ]:
            txn(date(2026, month, day), "out", money, group)
    receipt = txn(CUTOFF, "in", 3_000_000)
    balance = 260_000_000
    for m in range(1, 10):
        end = date(2026, m, monthrange(2026, m)[1])
        closing = balance + sum(
            r["amount"] * (1 if r["direction"] == "in" else -1)
            for r in bank
            if r["date"].month == m
        )
        statements.append(
            dict(
                statement_id=f"MA-KY{m:02}",
                account="MA-TK01",
                start_date=date(2026, m, 1),
                end_date=end,
                opening_balance=balance,
                closing_balance=closing,
                known_at=end,
            )
        )
        balance = closing
    for m in (10, 11, 12):
        for day, amount, kind in [
            (5, 12_000_000, "Thuê kho"),
            (19, 68_000_000, "variable_cost"),
            (27, 52_000_000, "Lương"),
        ]:
            expenses.append(
                dict(
                    expense_id=f"MA-CHI{m}{day}",
                    date=date(2026, m, day),
                    amount=amount,
                    category=kind,
                    known_at=CUTOFF,
                )
            )
    actions.append(
        dict(
            event_id="MA-HUA01",
            invoice_id="DEMO_MA0916",
            date=CUTOFF,
            kind="promise",
            promise_date=date(2026, 10, 16),
            known_at=CUTOFF,
        )
    )
    FOLDER.mkdir(parents=True, exist_ok=True)
    tables = [
        ("01_invoices", invoices),
        ("02_bank", bank),
        ("03_payments", payments),
        ("04_statements", statements),
        ("05_outflows", expenses),
        ("06_actions", actions),
    ]
    files = []
    for name, rows in tables:
        path = FOLDER / (name + ".csv")
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0])
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        k: v.strftime("%d/%m/%Y") if isinstance(v, date) else v
                        for k, v in row.items()
                    }
                )
        files.append(path)
    info = FOLDER / "BAT_DAU.txt"
    info.write_text(
        f"""MINH AN · DOANH NGHIỆP GIẢ LẬP
Nhà phân phối vật tư văn phòng bán chịu cho 12 khách. Dữ liệu từ tháng 1–9/2026, một tài khoản VND.
Mọi mã chứng từ, giao dịch và lời hứa trả đều được tạo cho buổi demo.

1. Từ thư mục dự án chạy .\\scripts\\start-business.ps1 -Port 8012 -Company MINHANDEMO
   Mở http://127.0.0.1:8012/workspace và kết nối bằng khóa của MINHANDEMO.
2. Trong Dữ liệu doanh nghiệp, nạp sáu CSV đúng thứ tự số. Chọn lần lượt:
   Hóa đơn / Dòng sao kê / Khoản thanh toán / Kỳ sao kê / Lịch chi / Nhật ký thu nợ.
   Chọn ngày/tháng/năm và định dạng số Việt Nam. Mỗi file bấm Kiểm tra file rồi Xác nhận lưu.
3. Đối chiếu: {len(invoices)} hóa đơn, {len(bank)} dòng ngân hàng, {len(payments)} phân bổ, 9 kỳ sao kê.
   Ở Tiền về chưa phân bổ còn đúng 3.000.000 VND từ dòng {receipt}. Tiền đã vào số dư ngân hàng.
   Có thể ghép 3 triệu này vào DEMO_MA0916, dùng mã P-DEMO-GHEP. Ghi nhận thủ công sẽ mang ngày thao tác.
4. Dự báo theo mốc trên kho mới, chốt 30/09/2026, số dư đầu {balance} VND (số dư cuối kỳ 09).
   Xác nhận đủ thu đã phân bổ cho ví dụ gốc. Lập kế hoạch 13 tuần rồi thử riêng khách MA-KH04 trả chậm 14 ngày.
   Lịch chi có tiền thuê, nhập hàng và lương. Phần chi chưa xác nhận vẫn hiện chưa biết.
5. Bộ này dùng để diễn tập nạp sổ, đối soát và dự báo; mã DEMO_ giúp hệ thống chặn huấn luyện bằng dữ liệu giả.
""",
        encoding="utf-8-sig",
    )
    with ZipFile(ARCHIVE, "w", ZIP_DEFLATED) as archive:
        for path in [info, *files]:
            archive.write(path, path.name)
    print(balance, [(k, len(v)) for k, v in tables])


if __name__ == "__main__":
    build()
