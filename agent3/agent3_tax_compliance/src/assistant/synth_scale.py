"""A large simulated enterprise for load testing: N purchase invoices from many sellers over one quarter, bank payments
for most of them, some cash, a portal list. Used to check that analysis and the interface stay usable at 1,000 invoices.

  python -m src.assistant.synth_scale <out_dir> [n_invoices]
"""
import csv
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from .synth import BANK_A, Builder, Seller, _make_cert, valid_tax_id

ITEMS = [('Giấy in A4 Double A', 85000, 'vpp'), ('Mực in HP 107A', 650000, 'vpp'), ('Cước internet doanh nghiệp', 2200000, 'dv'),
         ('Thuê văn phòng tháng', 45000000, 'dv'), ('Máy tính xách tay Dell Latitude', 21000000, 'tb'), ('Màn hình Dell 27 inch', 6200000, 'tb'),
         ('Dịch vụ vệ sinh văn phòng', 3500000, 'dv'), ('Nước uống đóng bình', 60000, 'vpp'), ('Phí bảo trì điều hòa', 1800000, 'dv'),
         ('Vé máy bay công tác', 3200000, 'ct'), ('Khách sạn công tác', 1600000, 'ct'), ('Chi phí tiếp khách', 4800000, 'tk'),
         ('Xăng RON95', 25000, 'xd'), ('Phần mềm kế toán bản quyền 1 năm', 9900000, 'pm'), ('Bàn ghế văn phòng', 2900000, 'tb')]


def generate(out: Path, n: int = 1000, seed: int = 11) -> dict:
    rng = random.Random(seed)
    company = dict(tax_code=valid_tax_id('031999888'), legal_name='Công ty Cổ phần Dịch vụ Mô Phỏng Quy Mô Lớn',
                   registered_address='Số 1 đường Mô Phỏng, TP Hồ Chí Minh')
    b = Builder(company, rng)
    sellers = []
    for k in range(60):
        s = Seller(f'S{k:02d}', f'Công ty TNHH Nhà Cung Cấp Số {k + 1}', valid_tax_id(f'03{rng.randint(1000000, 9999999)}'),
                   f'1{rng.randint(10**10, 10**11 - 1)}', f'K26T{chr(65 + k % 26)}{chr(65 + k // 26)}', '10%', counter=rng.randint(100, 900))
        _make_cert(s)
        sellers.append(s)
    pay, portal = [], []
    start = date(2026, 7, 1)
    for k in range(n):
        s = rng.choice(sellers)
        name, price, _ = rng.choice(ITEMS)
        qty = rng.randint(1, 12) if price < 1000000 else 1
        day = start + timedelta(days=rng.randint(0, 91))
        cash = rng.random() < 0.06
        f, num, gross = b.invoice(s, day, [(name, qty, price)], payment_label='TM' if cash else 'CK')
        if not cash and rng.random() < 0.93:
            pay.append((day + timedelta(days=rng.randint(0, 10)), gross, s.account, s.name.upper(), f'TT HD {int(num)}'))
        portal.append([s.tax_id, '1', s.symbol, num, day.isoformat(), '', gross])
    ws = Path(out)
    for p in ('invoices/purchase', 'invoices/sales', 'bank', 'portal'):
        (ws / p).mkdir(parents=True, exist_ok=True)
    for name, raw in b.sc.files.items():
        (ws / 'invoices/purchase' / name).write_bytes(raw)
    cols = BANK_A['columns']
    rows = [[cols['date'], cols['description'], cols['debit'], cols['credit'], cols['counterparty_account'], cols['counterparty_name']]]
    for d, amt, acc, nm, desc in sorted(pay):
        rows.append([d.strftime('%d/%m/%Y'), desc, f'{amt:,}'.replace(',', '.'), '', acc, nm])
    with open(ws / 'bank' / 'sao_ke_A.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        csv.writer(fh).writerows(rows)
    with open(ws / 'portal' / 'purchase_list.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        csv.writer(fh).writerows([['MST người bán', 'Ký hiệu mẫu số', 'Ký hiệu hóa đơn', 'Số hóa đơn', 'Ngày lập', 'Tổng tiền thuế', 'Tổng tiền thanh toán']] + portal)
    from .synth import generate as small
    tmp = ws / '_tmp_pack'
    small(tmp, seed=1)                                  # borrow a valid pack layout, then set this company's profile
    pack = json.loads((tmp / 'pack.json').read_text(encoding='utf-8'))
    pack['profile'].update(tax_code=company['tax_code'], legal_name=company['legal_name'], registered_address=company['registered_address'],
                           filing_period='QUARTER')
    (ws / 'pack.json').write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding='utf-8')
    import shutil
    shutil.rmtree(tmp)
    return dict(invoices=n, payments=len(pay))


if __name__ == '__main__':
    print(generate(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 1000))
