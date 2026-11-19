"""Sinh bộ tệp đầu vào để huấn luyện mô hình Agent 2 (cùng cột với 07_so_giao_dich_ngan_hang_A2.csv).

Mỗi tệp là một giai đoạn lịch sử của doanh nghiệp, phần lớn là giao dịch bình thường để mô hình học "thế nào là bình thường".
Chọn tất cả các tệp một lần trong tab "Huấn luyện & mô hình".  Dữ liệu mô phỏng, dùng lại được: cùng mã nguồn sinh ra cùng kết quả.
Dùng: python scripts/make_a2_training_input.py <thư mục đích> [mã doanh nghiệp]
"""
import csv
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HEAD = ['transaction_id', 'posted_at', 'created_at', 'approved_at', 'txn_type', 'amount_vnd', 'approval_limit_vnd', 'creator_id', 'approver_id',
        'is_financial_entry', 'debit_account', 'credit_account', 'journal_signature', 'accounting_purpose', 'recognised_input_vat_vnd',
        'recognised_output_vat_vnd', 'writeoff_provision_vnd', 'production_cost_vnd', 'company_id', 'vendor_id', 'employee_id', 'customer_id',
        'payment_channel', 'support_doc_count', 'goods_receipt_verified', 'evidence_on_file', 'journal_document_id', 'linked_document_id', 'business_purpose']
TZ = timezone(timedelta(hours=7))
PERIODS = [('2026-07-01', 31), ('2026-08-01', 31), ('2026-09-01', 30), ('2026-10-01', 9)]  # 4 tệp, lịch sử trước kỳ đang rà soát


def rows_for(company, start, days, rng, serial):
    day0 = datetime.fromisoformat(start).replace(tzinfo=TZ)
    out = []
    for d in range(days):
        day = day0 + timedelta(days=d)
        if day.weekday() >= 5:
            continue
        for _ in range(rng.randint(3, 6)):
            kind = rng.choices(['customer_receipt', 'vendor_payment', 'rent', 'salary'], [55, 32, 3, 10])[0]
            hour = rng.choice([8, 9, 10, 11, 14, 15, 16])
            created = day.replace(hour=hour, minute=rng.choice([0, 10, 20, 30]))
            approved = created + timedelta(minutes=rng.randint(5, 55))
            posted = approved + timedelta(minutes=rng.randint(2, 20))
            if kind == 'customer_receipt':
                amount, vendor, customer, purpose, docs = int(rng.lognormvariate(17.4, .7)), '', f'C{rng.randint(1, 40):06d}', 'customer_receipt', 0
            elif kind == 'vendor_payment':
                amount, vendor, customer, purpose, docs = int(rng.lognormvariate(16.3, .8)), f'V{rng.randint(1, 60):06d}', '', 'Thanh toán nhà cung cấp theo hóa đơn', rng.randint(1, 3)
            elif kind == 'rent':
                amount, vendor, customer, purpose, docs = rng.choice([45_000_000, 52_000_000, 65_000_000]), f'V{rng.randint(40, 50):06d}', '', 'Thuê kho bãi định kỳ', 2
            else:
                amount, vendor, customer, purpose, docs = int(rng.uniform(8e6, 22e6)), '', '', 'Lương và phụ cấp', 1
            amount = max(100_000, round(amount, -3))
            if kind != 'customer_receipt' and amount % 1_000_000 == 0 and rng.random() < .5:
                amount += rng.choice([-37_000, 12_000, 54_000])  # tránh quá nhiều số tròn triệu trong lịch sử bình thường
            serial[0] += 1
            tid = f'{kind[:4].upper()}-{serial[0]:07d}'
            out.append([tid, posted.isoformat(), created.isoformat(), approved.isoformat(), kind, amount, 20_000_000, 'E000001', 'E000002',
                        1, '112', '131', '112/131', purpose, 0, 0, 0, 0, company, vendor, '', customer, 'bank', docs,
                        1 if kind != 'customer_receipt' else 0, 1 if docs else 0, tid, '', 'Dữ liệu mô phỏng'])
    return out


def main():
    dest = Path(sys.argv[1])
    company = sys.argv[2] if len(sys.argv) > 2 else 'MPX10'
    dest.mkdir(parents=True, exist_ok=True)
    rng = random.Random(f'a2-training-{company}')
    serial = [1_400_000]
    for i, (start, days) in enumerate(PERIODS, 1):
        rows = rows_for(company, start, days, rng, serial)
        path = dest / f'A2_huan_luyen_{i:02d}_{start[:7]}.csv'
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(HEAD)
            w.writerows(rows)
        print(path.name, len(rows), 'dòng')


if __name__ == '__main__':
    main()
