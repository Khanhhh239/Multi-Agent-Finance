"""Build a compact, multi-agent Portal intake bundle from the MPX10 exports.

Outputs in `output/`:
  01_invoices.csv       AR invoices (paid + open receivables) for Agent 1
  02_sao_ke_chung.csv   Shared bank statement (AR receipts + AP supplier payments) for Agent 1 & Agent 3
  03_transactions.csv   Rich tabular transaction slice preserving ground-truth anomalies for Agent 2
  03_agent2_bundle.json Canonical 1.1.0 JSON bundle for Agent 2 v2 intake (portal/agent2_intake.py)
  04_hoa_don.zip        Sales & Purchase e-invoice XMLs (clean + R02 split pairs + R12 non-deductible) for Agent 3
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from pathlib import Path

SHARED_BANK_FIELDS = [
    'bank_id',
    'account',
    'date',
    'direction',
    'amount',
    'known_at',
    'component',
    'description',
    'counterparty_account',
    'counterparty_name',
    'customer_id',
    'cash_flow_class',
]


def csv_rows(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None):
    if not rows:
        raise ValueError(f'Không có dòng dữ liệu để ghi {path}')
    cols = fieldnames or list(rows[0])
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def all_xml_in_dir(month_dir: Path, role: str) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for archive in sorted(month_dir.glob(f'{role}_*.zip')):
        with zipfile.ZipFile(archive) as source:
            for name in sorted(source.namelist()):
                if name.endswith('.xml'):
                    found[name] = source.read(name)
    return found


def build(dataset: Path, output: Path) -> None:
    dataset = Path(dataset).resolve()
    output = Path(output).resolve()
    inputs = dataset / 'inputs'

    # Find latest month present in both A1 and A3 (typically '2026-10', fallback to latest common month)
    a1_months = {p.name for p in (inputs / 'a1').iterdir() if p.is_dir()}
    a3_months = {p.name for p in (inputs / 'a3').iterdir() if p.is_dir()}
    common_months = sorted(a1_months & a3_months, reverse=True)
    if not common_months:
        raise ValueError('Không tìm thấy tháng chung giữa inputs/a1 và inputs/a3.')

    chosen_month = None
    demo_invoices: list[dict] = []
    shared_bank: list[dict] = []
    sales_xml_items: list[tuple[str, bytes]] = []
    purchase_xml_items: list[tuple[str, bytes]] = []

    # A1 files a payment under the month its invoice was issued, not the month the money arrived (an August
    # invoice paid in October sits in a1/2026-08), so payments and invoices are looked up across every month.
    all_invoices: dict[str, dict] = {}
    payments_by_bank: dict[str, dict] = {}
    for month_dir in sorted(p for p in (inputs / 'a1').iterdir() if p.is_dir()):
        if (month_dir / '01_invoices.csv').is_file():
            for row in csv_rows(month_dir / '01_invoices.csv'):
                all_invoices.setdefault(row['invoice_id'], row)
        if (month_dir / '03_payments.csv').is_file():
            for prow in csv_rows(month_dir / '03_payments.csv'):
                if prow.get('bank_id'):
                    payments_by_bank[prow['bank_id']] = prow
    paid_invoice_ids = {p['invoice_id'] for p in payments_by_bank.values()}

    for month in common_months:
        a1_dir = inputs / 'a1' / month
        a3_dir = inputs / 'a3' / month
        if not ((a1_dir / '01_invoices.csv').is_file() and (a1_dir / '02_bank.csv').is_file() and (a3_dir / 'bank.csv').is_file()):
            continue
        bank_a1 = {row['bank_id']: row for row in csv_rows(a1_dir / '02_bank.csv')}
        invoices_a1 = {row['invoice_id']: row for row in csv_rows(a1_dir / '01_invoices.csv')}

        sales_xml_map = all_xml_in_dir(a3_dir, 'sales')
        cand_invoices, cand_bank, cand_sxml = [], [], []
        for row in csv_rows(a3_dir / 'bank.csv'):
            bid = row['Mã giao dịch']
            movement = bank_a1.get(bid)
            pay = payments_by_bank.get(bid)
            if not movement or not pay or movement['direction'] != 'in':
                continue
            inv = all_invoices.get(pay['invoice_id'])
            if not inv:
                continue
            if movement['amount'] != row['Ghi Có'] or movement['date'] != row['Ngày']:
                raise ValueError(f'Sao kê A1/A3 không khớp giao dịch {bid}')
            xml_name = f'sales_{int(inv["invoice_id"][4:]):08}.xml'
            if xml_name not in sales_xml_map:
                continue
            cand_invoices.append(inv)
            cand_sxml.append((xml_name, sales_xml_map[xml_name]))
            cand_bank.append({
                'bank_id': movement['bank_id'],
                'account': movement['account'],
                'date': movement['date'],
                'direction': movement['direction'],
                'amount': movement['amount'],
                'known_at': movement['known_at'],
                'component': movement.get('component', 'other'),
                'description': row['Nội dung'],
                'counterparty_account': row['Tài khoản đối tác'],
                'counterparty_name': row['Tên đối tác'],
                'customer_id': inv['customer_id'],
                'cash_flow_class': movement.get('cash_flow_class', 'ar'),
            })
            if len(cand_bank) == 2:
                break

        if len(cand_bank) >= 2:
            chosen_month = month
            demo_invoices = cand_invoices
            # Also include up to 2 open receivables so Agent 1 forecasts open AR right away
            paid_ids = {r['invoice_id'] for r in demo_invoices}
            for inv in invoices_a1.values():
                if inv['invoice_id'] not in paid_ids and inv['invoice_id'] not in paid_invoice_ids:
                    demo_invoices.append(inv)
                    if len(demo_invoices) >= 4:
                        break
            shared_bank = cand_bank
            sales_xml_items = cand_sxml
            break

    if not chosen_month or len(shared_bank) < 2:
        raise ValueError('Cần ít nhất hai khoản thu khớp đồng thời giữa A1 và A3 để đóng gói demo.')

    # Add outgoing supplier AP payments & corresponding purchase XMLs from chosen_month (including R02 split & R12 items!)
    a1_m = inputs / 'a1' / chosen_month
    a3_m = inputs / 'a3' / chosen_month
    bank_a1_m = {row['bank_id']: row for row in csv_rows(a1_m / '02_bank.csv')}
    purchase_xml_map = all_xml_in_dir(a3_m, 'purchase')

    # Select special showcase purchase XMLs (R02 split pairs + R12 golf/entertainment + 1 regular paid purchase)
    selected_pxml: dict[str, bytes] = {}
    for pname, content in sorted(purchase_xml_map.items(), reverse=True):
        text = content.decode('utf-8', 'ignore')
        if any(kw in text for kw in ('golf', 'spa', 'tiếp khách', 'phúc lợi', 'đợt 1', 'đợt 2', 'buổi sáng', 'buổi chiều')):
            selected_pxml[pname] = content
        elif len(selected_pxml) < 8:
            selected_pxml[pname] = content
        if len(selected_pxml) >= 10:
            break
    if not selected_pxml and purchase_xml_map:
        first_p = sorted(purchase_xml_map)[0]
        selected_pxml[first_p] = purchase_xml_map[first_p]
    purchase_xml_items = sorted(selected_pxml.items())

    # Include outgoing bank transactions from A3 bank.csv that match selected purchase XMLs (by invoice number)
    selected_p_nums = {str(int(name.split('_')[1].split('.')[0])) for name in selected_pxml}
    selected_p_padded = {name.split('_')[1].split('.')[0] for name in selected_pxml}
    for row in csv_rows(a3_m / 'bank.csv'):
        if int(row['Ghi Nợ'] or 0) <= 0:
            continue
        bid = row['Mã giao dịch']
        movement = bank_a1_m.get(bid)
        if not movement or movement['direction'] != 'out':
            continue
        desc = row['Nội dung']
        if any(pnum in desc for pnum in selected_p_padded) or any(f' {n} ' in f' {desc} ' for n in selected_p_nums):
            shared_bank.append({
                'bank_id': movement['bank_id'],
                'account': movement['account'],
                'date': movement['date'],
                'direction': 'out',
                'amount': movement['amount'],
                'known_at': movement['known_at'],
                'component': movement.get('component', 'other'),
                'description': desc,
                'counterparty_account': row['Tài khoản đối tác'],
                'counterparty_name': row['Tên đối tác'],
                'customer_id': '',
                'cash_flow_class': movement.get('cash_flow_class', 'operating'),
            })

    # Agent 2 tabular slice (preserve 100% of ground-truth anomalies + bounded normal context) & canonical 1.1.0 JSON bundle
    chunks = sorted((inputs / 'a2/chunks').glob('transactions_*.csv'))
    if not chunks:
        raise ValueError('Không tìm thấy tệp transactions_0001.csv trong bản xuất A2.')
    tx_rows_all = list(csv_rows(chunks[0]))
    if {row['company_id'] for row in tx_rows_all} != {'MPX10'}:
        raise ValueError('Tệp giao dịch A2 không thuộc bộ MPX10.')

    gt_ids = set()
    gt_file = inputs / 'a2/anomaly_ground_truth.csv'
    if gt_file.is_file():
        gt_ids = {r['transaction_id'] for r in csv_rows(gt_file)}
    anomaly_txs = [r for r in tx_rows_all if r['transaction_id'] in gt_ids]
    normal_txs = [r for r in tx_rows_all if r['transaction_id'] not in gt_ids and r.get('payment_channel') in ('bank', 'cash')][:400]
    bounded_txs = sorted(anomaly_txs + normal_txs, key=lambda r: (r['posted_at'], r['transaction_id']))

    canonical_json = inputs / 'a2/canonical_bundle.json'
    if not canonical_json.is_file():
        raise ValueError('Thiếu tệp canonical_bundle.json chuẩn 1.1.0 trong bản xuất A2.')
    bundle_doc = json.loads(canonical_json.read_text(encoding='utf-8'))
    if bundle_doc.get('contract_version') != '1.1.0':
        raise ValueError('canonical_bundle.json không đúng phiên bản hợp đồng 1.1.0.')

    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / '01_invoices.csv', demo_invoices)
    write_csv(output / '02_sao_ke_chung.csv', shared_bank, fieldnames=SHARED_BANK_FIELDS)
    write_csv(output / '03_transactions.csv', bounded_txs, fieldnames=list(tx_rows_all[0]))
    shutil.copyfile(canonical_json, output / '03_agent2_bundle.json')
    with zipfile.ZipFile(output / '04_hoa_don.zip', 'w') as archive:
        for name, content in [*sales_xml_items, *purchase_xml_items]:
            archive.writestr(zipfile.ZipInfo(name, date_time=(2023, 1, 1, 0, 0, 0)), content, compress_type=zipfile.ZIP_DEFLATED)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.dataset, args.output)
    print(args.output.resolve())
