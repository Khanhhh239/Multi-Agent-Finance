"""Build a small portal intake bundle from the MPX10 exports."""
import argparse
import csv
import shutil
import zipfile
from pathlib import Path


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream)


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def xml_files(month_dir, role, names):
    remaining = set(names)
    for archive in sorted(month_dir.glob(f'{role}_*.zip')):
        with zipfile.ZipFile(archive) as source:
            for name in sorted(remaining.intersection(source.namelist())):
                yield name, source.read(name)
                remaining.remove(name)
    if remaining:
        raise ValueError(f'Thiếu XML {role}: {", ".join(sorted(remaining))}')


def build(dataset, output):
    inputs = dataset / 'inputs'
    a1 = inputs / 'a1/2026-10'
    a3 = inputs / 'a3/2026-10'
    bank = {row['bank_id']: row for row in csv_rows(a1 / '02_bank.csv')}
    invoices = {row['invoice_id']: row for row in csv_rows(a1 / '01_invoices.csv')}
    demo_invoices, shared_bank = [], []
    for row in csv_rows(a3 / 'bank.csv'):
        description = row['Nội dung']
        if not description.startswith('Thu hóa đơn '):
            continue
        invoice = invoices.get('INV-' + description.removeprefix('Thu hóa đơn '))
        movement = bank.get(row['Mã giao dịch'])
        if not invoice or not movement or movement['direction'] != 'in':
            continue
        if movement['amount'] != row['Ghi Có'] or movement['date'] != row['Ngày']:
            raise ValueError(f'Sao kê A1/A3 không khớp giao dịch {movement["bank_id"]}')
        demo_invoices.append(invoice)
        shared_bank.append(dict(movement, description=description,
                                counterparty_account=row['Tài khoản đối tác'],
                                counterparty_name=row['Tên đối tác'], customer_id=invoice['customer_id']))
        if len(shared_bank) == 2:
            break
    if len(shared_bank) != 2:
        raise ValueError('Cần hai khoản thu có cùng mã giao dịch và hóa đơn trong bản xuất A1/A3.')

    sales_names = [f'sales_{int(row["invoice_id"][4:]):08}.xml' for row in demo_invoices]
    xml = list(xml_files(a3, 'sales', sales_names))
    purchase = next(iter(sorted(a3.glob('purchase_*.zip'))), None)
    if not purchase:
        raise ValueError('Thiếu gói XML hóa đơn mua.')
    with zipfile.ZipFile(purchase) as source:
        name = next(name for name in source.namelist() if name.endswith('.xml'))
        xml.append((name, source.read(name)))
    transactions = list((inputs / 'a2').rglob('transactions_0001.csv'))
    if len(transactions) != 1:
        raise ValueError('Cần đúng một tệp transactions_0001.csv trong bản xuất A2.')
    if {row['company_id'] for row in csv_rows(transactions[0])} != {'MPX10'}:
        raise ValueError('Tệp giao dịch A2 không thuộc bộ MPX10.')

    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / '01_invoices.csv', demo_invoices)
    write_csv(output / '02_sao_ke_chung.csv', shared_bank)
    shutil.copyfile(transactions[0], output / '03_transactions.csv')
    with zipfile.ZipFile(output / '04_hoa_don.zip', 'w') as archive:
        for name, content in xml:
            archive.writestr(zipfile.ZipInfo(name), content, compress_type=zipfile.ZIP_DEFLATED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.dataset, args.output)
    print(args.output.resolve())
