"""Build a complete, rich, cross-validated test data kit in DATA_TEST_SAN_SANG (and Downloads/DATA_TEST_MAF_SOSON)
so the user can test every feature of Portal + Agent 1 + Agent 2 + Agent 3 + Agent 4 seamlessly.
"""
from __future__ import annotations

import csv
import io
import json
import re
import shutil
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / 'portal/workspace/datasets/enterprise-x10-v3-full/inputs'
SV = ROOT / 'agent3/agent3_tax_compliance/demo/DN_Phan_mem_Sao_Viet'
OUT = ROOT / 'DATA_TEST_SAN_SANG'
DOWNLOADS_COPY = Path.home() / 'Downloads' / 'DATA_TEST_MAF_SOSON'

MPX_NAME = 'Công ty Cổ phần Phân phối và Dịch vụ Minh Phát — MÔ PHỎNG'
MPX_TAX = '0999999905'
ACCOUNT = '11211'


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = fieldnames or list(rows[0].keys())
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def adapt_sv_xml(xml_text: str) -> str:
    # Remove cryptographic signature block (<DSCKS>...</DSCKS>) since MPX10 workspace is simulated=True
    xml_text = re.sub(r'<DSCKS>.*?</DSCKS>', '', xml_text, flags=re.DOTALL)
    # The first-load kit contains only invoices assigned to the simulated
    # enterprise. The original Sao Viet fixtures keep their negative cases.
    for simulated_tax_id in ('0317776666', '0317776667', '0317779995'):
        xml_text = xml_text.replace(f'<MST>{simulated_tax_id}</MST>', f'<MST>{MPX_TAX}</MST>')
    xml_text = xml_text.replace('Công ty TNHH Phần mềm Sao Việt', MPX_NAME)
    xml_text = xml_text.replace('<STKNHang>0451000123456</STKNHang>', f'<STKNHang>{ACCOUNT}</STKNHang>')
    return xml_text


def build_invoice_zip(pack_dir: Path) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)

    # 1. Agent 3 XMLs adapted to MPX10 (17 purchase + 3 sales = 20 XMLs)
    xml_entries: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(SV / 'A_tha_vao_Nap_nhanh/1_hoa_don_mua_vao_17_hoa_don.zip') as z:
        for name in sorted(z.namelist()):
            if name.endswith('.xml'):
                adapted = adapt_sv_xml(z.read(name).decode('utf-8'))
                xml_entries.append(('mua_vao_' + Path(name).name, adapted.encode('utf-8')))
    for i in (1, 2, 3):
        p = SV / f'A_tha_vao_Nap_nhanh/2_hoa_don_ban_ra_{i}.xml'
        adapted = adapt_sv_xml(p.read_text(encoding='utf-8'))
        xml_entries.append((p.name, adapted.encode('utf-8')))

    zip_path = pack_dir / '08_hoa_don_dien_tu_XML_A3.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, data in xml_entries:
            zf.writestr(fname, data)


def build_pack_01(pack_dir: Path) -> None:
    build_invoice_zip(pack_dir)

    # 2. Agent 3 Tax Portal Purchase List (09_bang_ke_cong_thue_A3.csv)
    shutil.copyfile(SV / 'A_tha_vao_Nap_nhanh/4_bang_ke_cong_thue.csv', pack_dir / '09_bang_ke_cong_thue_A3.csv')

    # 3. Build unified Agent 1 + Agent 3 Shared Bank Statement + Agent 1 Invoices/Payments/Statements/Outflows/Actions
    # Take real MPX10 invoices from Sep & Oct 2026 so Agent 1 has rich customer history + open AR
    inv_sep = read_csv(DS / 'a1/2026-09/01_invoices.csv')[:110]
    inv_oct = read_csv(DS / 'a1/2026-10/01_invoices.csv')[:90]
    selected_invoices = {r['invoice_id']: r for r in (inv_sep + inv_oct)}

    # Also add the 3 sales invoices from XML (HD 13, 14, 15) into Agent 1 invoices so A1 & A3 share them!
    sales_xml_invoices = [
        dict(invoice_id='INV-SV-0013', customer_id='CUST-BLMP', issue_date='2026-07-25', due_date='2026-08-10', amount='220000000', currency='VND', known_at='2026-07-25'),
        dict(invoice_id='INV-SV-0014', customer_id='CUST-LOGT', issue_date='2026-08-25', due_date='2026-09-10', amount='220000000', currency='VND', known_at='2026-08-25'),
        dict(invoice_id='INV-SV-0015', customer_id='CUST-BLMP', issue_date='2026-09-25', due_date='2026-10-10', amount='220000000', currency='VND', known_at='2026-09-25'),
    ]
    for s in sales_xml_invoices:
        selected_invoices[s['invoice_id']] = s

    # Payments from Sep & Oct that reference our selected invoices
    pay_all = read_csv(DS / 'a1/2026-09/03_payments.csv') + read_csv(DS / 'a1/2026-10/03_payments.csv')
    selected_payments = [p for p in pay_all if p['invoice_id'] in selected_invoices][:55]
    needed_bank_ids = {p['bank_id'] for p in selected_payments if p.get('bank_id')}

    bank_sep_oct = {
        r['bank_id']: r
        for r in (read_csv(DS / 'a1/2026-09/02_bank.csv') + read_csv(DS / 'a1/2026-10/02_bank.csv'))
        if r['bank_id'] in needed_bank_ids
    }

    # Build Shared Bank rows (02_sao_ke_chung_A1_A3.csv):
    # (a) The 18 bank rows matching the 20 XML invoices for Agent 3 (dates Jul-Sep 2026)
    sv_bank_specs = [
        ('BT00001', '2026-07-06', 'out', 2200000, 'TT HD 711 Công ty TNHH Viễn thông Hà Thành', '190673974389', 'CÔNG TY TNHH VIỄN THÔNG HÀ THÀNH', '', 'operating_outflow'),
        ('BT00002', '2026-07-09', 'out', 19800000, 'TT HD 766 Công ty Cổ phần Dịch vụ Điện toán Mây Việt', '143862036683', 'CÔNG TY CỔ PHẦN DỊCH VỤ ĐIỆN TOÁN MÂY VIỆT', '', 'operating_outflow'),
        ('BT00003', '2026-07-10', 'out', 380000000, 'Tra luong thang 6', '0011002233', 'BANG LUONG NHAN VIEN', '', 'payroll'),
        ('BT00004', '2026-07-18', 'out', 105600000, 'TT HD 675 Công ty TNHH Thiết bị Tin học Phương Nam', '180091652208', 'CÔNG TY TNHH THIẾT BỊ TIN HỌC PHƯƠNG NAM', '', 'supplier_payment'),
        ('BT00005', '2026-07-28', 'in', 220000000, 'Thanh toan HD 13', '0091000638535', 'CÔNG TY CỔ PHẦN BÁN LẺ MÔ PHỎNG', 'CUST-BLMP', ''),
        ('BT00006', '2026-08-06', 'out', 2200000, 'TT HD 712 Công ty TNHH Viễn thông Hà Thành', '190673974389', 'CÔNG TY TNHH VIỄN THÔNG HÀ THÀNH', '', 'operating_outflow'),
        ('BT00007', '2026-08-09', 'out', 19800000, 'TT HD 767 Công ty Cổ phần Dịch vụ Điện toán Mây Việt', '143862036683', 'CÔNG TY CỔ PHẦN DỊCH VỤ ĐIỆN TOÁN MÂY VIỆT', '', 'operating_outflow'),
        ('BT00008', '2026-08-10', 'out', 380000000, 'Tra luong thang 7', '0011002233', 'BANG LUONG NHAN VIEN', '', 'payroll'),
        ('BT00009', '2026-08-19', 'out', 6600000, 'TT HD 714 Công ty TNHH Viễn thông Hà Thành', '190673974389', 'CÔNG TY TNHH VIỄN THÔNG HÀ THÀNH', '', 'operating_outflow'),
        ('BT00010', '2026-08-22', 'out', 55550000, 'TT HD 264 Công ty TNHH Điện máy Gia dụng An Khang', '121227921900', 'CÔNG TY TNHH ĐIỆN MÁY GIA DỤNG AN KHANG', '', 'supplier_payment'),
        ('BT00011', '2026-08-28', 'in', 220000000, 'Thanh toan HD 14', '0091000768695', 'CÔNG TY TNHH LOGISTICS THỬ NGHIỆM', 'CUST-LOGT', ''),
        ('BT00012', '2026-09-06', 'out', 2200000, 'TT HD 713 Công ty TNHH Viễn thông Hà Thành', '190673974389', 'CÔNG TY TNHH VIỄN THÔNG HÀ THÀNH', '', 'operating_outflow'),
        ('BT00013', '2026-09-10', 'out', 15000000, 'chuyen tien bao tri phong may cho nhat tin', '0071000882206', 'NGUYEN VAN GIAM DOC', '', 'operating_outflow'),
        ('BT00014', '2026-09-10', 'out', 380000000, 'Tra luong thang 8', '0011002233', 'BANG LUONG NHAN VIEN', '', 'payroll'),
        ('BT00015', '2026-09-13', 'out', 7150000, 'TT HD 611 Nhà hàng Hải sản Biển Đông', '126392865197', 'NHÀ HÀNG HẢI SẢN BIỂN ĐÔNG', '', 'operating_outflow'),
        ('BT00016', '2026-09-21', 'out', 77000000, 'TT HD 4 Công ty TNHH Thương mại Dịch vụ Minh Phát', '177367326817', 'CÔNG TY TNHH THƯƠNG MẠI DỊCH VỤ MINH PHÁT', '', 'supplier_payment'),
        ('BT00017', '2026-09-28', 'in', 220000000, 'Thanh toan HD 15', '0091000180027', 'CÔNG TY CỔ PHẦN BÁN LẺ MÔ PHỎNG', 'CUST-BLMP', ''),
        ('BT00018', '2026-09-30', 'in', 150000000, 'Tam ung hop dong trien khai phan mem', '0091000555666', 'CONG TY TNHH LOGISTICS THU NGHIEM', 'CUST-LOGT', 'customer_advance'),
    ]

    shared_bank_rows = []
    for bid, dt, direction, amt, desc, peer_acc, peer_name, cust_id, cf_class in sv_bank_specs:
        shared_bank_rows.append({
            'bank_id': bid,
            'account': ACCOUNT,
            'date': dt,
            'direction': direction,
            'amount': str(amt),
            'known_at': dt,
            'component': 'other',
            'description': desc,
            'counterparty_account': peer_acc,
            'counterparty_name': peer_name,
            'customer_id': cust_id,
            'cash_flow_class': cf_class,
        })

    # Link the 3 sales XML receipts in Agent 1 payments as well
    for rec_id, inv_id, dt, bid in [
        ('REC-SV-0013', 'INV-SV-0013', '2026-07-28', 'BT00005'),
        ('REC-SV-0014', 'INV-SV-0014', '2026-08-28', 'BT00011'),
        ('REC-SV-0015', 'INV-SV-0015', '2026-09-28', 'BT00017'),
    ]:
        selected_payments.append({
            'payment_id': rec_id,
            'invoice_id': inv_id,
            'payment_date': dt,
            'amount': '220000000',
            'bank_id': bid,
            'known_at': dt,
        })

    # Add real MPX10 bank movements matching selected_payments
    pay_by_bank = {p['bank_id']: p for p in selected_payments if p.get('bank_id')}
    for bid, brow in sorted(bank_sep_oct.items()):
        p = pay_by_bank.get(bid)
        inv = selected_invoices.get(p['invoice_id']) if p else None
        cust = inv['customer_id'] if inv else ''
        inv_num = p['invoice_id'] if p else bid
        shared_bank_rows.append({
            'bank_id': bid,
            'account': ACCOUNT,
            'date': brow['date'],
            'direction': brow['direction'],
            'amount': str(brow['amount']),
            'known_at': brow['known_at'],
            'component': brow.get('component', 'other') or 'other',
            'description': f'Khach thanh toan hoa don {inv_num}',
            'counterparty_account': '990011223344',
            'counterparty_name': f'Khách hàng {cust}' if cust else 'Đối tác thương mại',
            'customer_id': cust,
            'cash_flow_class': '',
        })

    shared_bank_rows.sort(key=lambda r: (r['date'], r['bank_id']))

    # Compute exact reconciled monthly/period statements from 2026-07-01 to 2026-10-14!
    opening = 4_500_000_000  # 4.5 tỷ VND opening cash on 2026-07-01
    periods = [
        ('STMT-2026-07', '2026-07-01', '2026-07-31'),
        ('STMT-2026-08', '2026-08-01', '2026-08-31'),
        ('STMT-2026-09', '2026-09-01', '2026-09-30'),
        ('STMT-2026-10', '2026-10-01', '2026-10-14'),
    ]
    statements = []
    cur = opening
    for sid, s_start, s_end in periods:
        net = sum(
            int(r['amount']) if r['direction'] == 'in' else -int(r['amount'])
            for r in shared_bank_rows
            if s_start <= r['date'] <= s_end
        )
        nxt = cur + net
        statements.append({
            'statement_id': sid,
            'account': ACCOUNT,
            'start_date': s_start,
            'end_date': s_end,
            'opening_balance': str(cur),
            'closing_balance': str(nxt),
            'known_at': '2026-10-14',
        })
        cur = nxt

    # Outflows (45 rows across Oct 16 - Dec 30, 2026)
    outflows = read_csv(DS / 'a1/05_outflows.csv')[:45]

    # Actions (collection contacts & promises on invoices in selected_invoices)
    actions_all = read_csv(DS / 'a1/2026-09/06_actions.csv') + read_csv(DS / 'a1/2026-10/06_actions.csv')
    actions = []
    for a in actions_all:
        if a['invoice_id'] in selected_invoices:
            actions.append({
                'event_id': a['event_id'],
                'invoice_id': a['invoice_id'],
                'date': a['date'],
                'kind': a['kind'],
                'promise_date': a.get('promise_date', ''),
                'known_at': a.get('known_at', a['date']),
            })
    if len(actions) < 8:
        open_invs = [inv for inv in selected_invoices.values() if inv['issue_date'] >= '2026-09-15'][:10]
        for idx, inv in enumerate(open_invs, 1):
            is_promise = idx % 2 == 0
            actions.append({
                'event_id': f'ACT-MPX-{idx:03d}',
                'invoice_id': inv['invoice_id'],
                'date': '2026-10-12',
                'kind': 'promise' if is_promise else 'contact',
                'promise_date': '2026-10-26' if is_promise else '',
                'known_at': '2026-10-12',
            })

    # 4. Agent 2 Transactions (120 bank rows <= 200 synchronous UI limit, with realistic risk anomalies!)
    a2_all = read_csv(DS / 'a2/chunks/transactions_0001.csv')
    a2_bank = [r for r in a2_all if r.get('payment_channel') == 'bank' and r.get('txn_type') in ('customer_receipt', 'vendor_payment', 'rent', 'payroll')][:114]
    # Inject 6 clear anomaly candidates (split payments near 20M limit, round 50M/95M amounts, weekend/late-night)
    if a2_bank:
        template = dict(a2_bank[-1])
        anomalies = [
            ('TX-RISK-SPLIT-01', '2026-10-13T09:15:00+07:00', 'vendor_payment', '19500000', 'V000088', 'E000012', 'Thanh toán thiết bị đợt 1 tách nhỏ sát hạn mức duyệt 20tr'),
            ('TX-RISK-SPLIT-02', '2026-10-13T10:05:00+07:00', 'vendor_payment', '19800000', 'V000088', 'E000012', 'Thanh toán thiết bị đợt 2 cùng ngày cùng nhà cung cấp V000088'),
            ('TX-RISK-SPLIT-03', '2026-10-13T14:20:00+07:00', 'vendor_payment', '19600000', 'V000088', 'E000012', 'Thanh toán thiết bị đợt 3 cùng ngày cùng nhà cung cấp V000088'),
            ('TX-RISK-ROUND-01', '2026-10-14T22:45:00+07:00', 'vendor_payment', '90000000', 'V000199', 'E000005', 'Chi phí tư vấn trọn gói số tiền tròn chẵn ngoài giờ làm việc'),
            ('TX-RISK-ROUND-02', '2026-10-14T23:10:00+07:00', 'vendor_payment', '150000000', 'V000199', 'E000005', 'Tạm ứng hợp đồng dịch vụ giá trị lớn bất thường cuối ngày'),
            ('TX-RISK-RENT-01', '2026-10-14T16:00:00+07:00', 'rent', '65000000', 'V000045', 'E000008', 'Thanh toán thuê kho bãi bổ sung'),
        ]
        for tid, ts, ttype, amt, vid, creator, purpose in anomalies:
            row = dict(template)
            row.update({
                'transaction_id': tid,
                'posted_at': ts,
                'created_at': ts,
                'approved_at': ts,
                'txn_type': ttype,
                'amount_vnd': amt,
                'approval_limit_vnd': '20000000',
                'creator_id': creator,
                'approver_id': creator,
                'vendor_id': vid,
                'customer_id': '',
                'payment_channel': 'bank',
                'accounting_purpose': purpose,
                'business_purpose': purpose,
            })
            a2_bank.append(row)

    write_csv(pack_dir / '01_hoa_don_ban_A1.csv', list(selected_invoices.values()))
    write_csv(pack_dir / '02_sao_ke_chung_A1_A3.csv', shared_bank_rows)
    write_csv(pack_dir / '03_tien_khach_tra_A1.csv', selected_payments)
    write_csv(pack_dir / '04_ky_sao_ke_A1.csv', statements)
    write_csv(pack_dir / '05_lich_chi_co_dinh_A1.csv', outflows)
    write_csv(pack_dir / '06_nhac_no_hua_tra_A1.csv', actions)
    write_csv(pack_dir / '07_so_giao_dich_ngan_hang_A2.csv', a2_bank)


def build_pack_02(pack_dir: Path) -> None:
    """Supplemental never-before-seen files so the user can test uploading v2 live anytime."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    write_csv(pack_dir / '01_hoa_don_bo_sung_A1.csv', [
        dict(invoice_id='INV-SUPP-2001', customer_id='CUST-NEW-01', issue_date='2026-10-15', due_date='2026-11-15', amount='48500000', currency='VND', known_at='2026-10-15'),
        dict(invoice_id='INV-SUPP-2002', customer_id='CUST-NEW-02', issue_date='2026-10-15', due_date='2026-11-20', amount='72000000', currency='VND', known_at='2026-10-15'),
    ])
    write_csv(pack_dir / '02_sao_ke_chung_bo_sung_A1_A3.csv', [
        dict(bank_id='BT-SUPP-901', account=ACCOUNT, date='2026-10-15', direction='in', amount='48500000', known_at='2026-10-15', component='other',
             description='Thu tien hoa don INV-SUPP-2001', counterparty_account='009100998877', counterparty_name='CONG TY TNHH KHACH HANG MOI 01', customer_id='CUST-NEW-01', cash_flow_class=''),
        dict(bank_id='BT-SUPP-902', account=ACCOUNT, date='2026-10-15', direction='out', amount='12500000', known_at='2026-10-15', component='other',
             description='Chi phi van chuyen lo hang thang 10', counterparty_account='190088776655', counterparty_name='CONG TY VAN TAI NHANH', customer_id='', cash_flow_class='operating_outflow'),
    ])


def build_pack_03(pack_dir: Path) -> None:
    """Advanced Agent 2 & Agent 3 test files."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'agent2/sme_fraud/web/rule-sources.xlsx', pack_dir / 'Agent2_Mau_Excel_Da_Bang_35_Luat.xlsx')
    shutil.copyfile(ROOT / 'agent2/examples/full_rules/C001_B1_signal.json', pack_dir / 'Agent2_Goi_JSON_35_Luat_C001.json')
    shutil.copyfile(SV / 'B_nhap_o_Quan_tri/danh_sach_doanh_nghiep_rui_ro.csv', pack_dir / 'Agent3_Danh_Sach_MST_Rui_Ro.csv')


def write_cheatsheet(base: Path) -> None:
    text = """====================================================================
  BỘ DỮ LIỆU KIỂM THỬ SẴN SÀNG — SỔ SON (MULTI-AGENT FINANCE)
====================================================================

1. ĐỊA CHỈ WEB & MẬT KHẨU ĐĂNG NHẬP
   - Web chung (Portal) : http://127.0.0.1:8800  (hoặc http://localhost:8800 khi dùng FaceID)
   - Mật khẩu mở khóa   : SoSon@2026
   - Mã doanh nghiệp    : MPX10
   - Mã số thuế         : 0999999905
   - Định dạng tệp      : Ngày yyyy-mm-dd (ISO) · Số tiền dấu chấm thập phân (plain)

2. CẤU TRÚC THƯ MỤC DỮ LIỆU
   [01_Goi_Chuan_Nap_Chung_4_Agent_MPX10]
     Gói chính gồm 9 tệp đồng bộ xuyên suốt cho Agent 1, Agent 2, Agent 3 (khớp kho Agent 4):
       - 01_hoa_don_ban_A1.csv            -> Agent 1 (203 hóa đơn bán & công nợ phải thu)
       - 02_sao_ke_chung_A1_A3.csv        -> Agent 1 & Agent 3 (Sao kê dùng chung, nạp 1 lần cho 2 Agent)
       - 03_tien_khach_tra_A1.csv         -> Agent 1 (Các khoản khách thanh toán khớp hóa đơn & sao kê)
       - 04_ky_sao_ke_A1.csv              -> Agent 1 (Số dư đầu kỳ / cuối kỳ khớp chính xác từng đồng)
       - 05_lich_chi_co_dinh_A1.csv       -> Agent 1 (45 khoản lịch chi cố định 13 tuần tới)
       - 06_nhac_no_hua_tra_A1.csv        -> Agent 1 (Sự kiện nhắc nợ & khách hứa trả)
       - 07_so_giao_dich_ngan_hang_A2.csv -> Agent 2 (120 giao dịch ngân hàng kèm 6 mẫu bất thường để rà 4 nhánh)
       - 08_hoa_don_dien_tu_XML_A3.zip    -> Agent 3 (20 hóa đơn điện tử XML mua vào / bán ra có cài tình huống rủi ro thuế)
       - 09_bang_ke_cong_thue_A3.csv      -> Agent 3 (Bảng kê cổng thuế đối chiếu thừa/thiếu hóa đơn)

   [02_Goi_Bo_Sung_Ky_Moi_Test_Nap_Them]
     Dùng khi bạn muốn tự tay kéo-thả nạp thêm gói phiên bản mới (v2) ngay trên giao diện Nạp dữ liệu
     mà không bị báo trùng với gói v1 đã niêm phong sẵn.

   [03_File_Test_Chuyen_Sau_Agent2_Agent3]
     - Agent2_Mau_Excel_Da_Bang_35_Luat.xlsx : Test tính năng "Đọc bảng và cột" đa nguồn 35 luật trong Agent 2
     - Agent2_Goi_JSON_35_Luat_C001.json     : Test phân tích đầy đủ 35 luật (chọn doanh nghiệp C001 trong Agent 2)
     - Agent3_Danh_Sach_MST_Rui_Ro.csv       : Test nạp danh sách MST bỏ địa chỉ kinh doanh tại Quản trị Agent 3

3. CÂU HỎI GỢI Ý CHO AGENT 4 (HỎI ĐÁP SỐ LIỆU CFO)
   - "Doanh thu thuần quý 3 năm 2026 là bao nhiêu?"  (Đáp án kho MPX10: 3.459.561.433.330 VND)
   - "Lợi nhuận sau thuế tháng 8 năm 2026?"
   - "Công nợ phải thu hiện tại?"
   - "Tiền mặt cuối tháng 8 năm 2026?"
   - "Doanh thu thuần theo tháng năm 2026"
"""
    (base / '00_THONG_TIN_DANG_NHAP_VA_TOM_TAT.txt').write_text(text, encoding='utf-8')


def verify_pack(pack_dir: Path) -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'agent1'))
    import pandas as pd
    from portal import server as ps, bank_intake, agent2_intake
    from agent1.adaptive.data import parse_rows, suggested_mapping, validate_dataset

    for p in sorted(pack_dir.iterdir()):
        raw = p.read_bytes()
        cls = ps.classify(p.name, raw)
        print(f'  [classify] {p.name}: kind={cls["kind"]}, targets={cls["targets"]}')

    a1_data = {}
    for fn, kind in [
        ('01_hoa_don_ban_A1.csv', 'invoices'),
        ('03_tien_khach_tra_A1.csv', 'payments'),
        ('04_ky_sao_ke_A1.csv', 'statements'),
        ('05_lich_chi_co_dinh_A1.csv', 'outflows'),
        ('06_nhac_no_hua_tra_A1.csv', 'actions'),
    ]:
        df = pd.read_csv(pack_dir / fn, dtype=str, keep_default_na=False)
        rows, errs, _ = parse_rows(df, kind, suggested_mapping(df.columns, kind), '%Y-%m-%d', 'plain')
        assert not errs, f'A1 {kind} errors: {errs[:5]}'
        a1_data[kind] = rows
        print(f'  [A1] {kind}: {len(rows)} valid rows, 0 errors')

    raw_sb = (pack_dir / '02_sao_ke_chung_A1_A3.csv').read_bytes()
    it = bank_intake.csv_rows(raw_sb)
    hdr = next(it)
    b_rows = bank_intake.normalize_rows(it, bank_intake.columns(hdr, ps.plain), 'plain', ps.plain)
    proj_a1 = bank_intake.project(b_rows, 'agent1', date_format='iso', number_format='plain')
    df_b = pd.read_csv(io.BytesIO(proj_a1), dtype=str, keep_default_na=False)
    rows_b, errs_b, _ = parse_rows(df_b, 'bank', suggested_mapping(df_b.columns, 'bank'), '%Y-%m-%d', 'plain')
    assert not errs_b, f'A1 bank errors: {errs_b[:5]}'
    a1_data['bank'] = rows_b
    a1_data['expense_payments'] = []
    validate_dataset(a1_data)
    print(f'  [A1] bank: {len(rows_b)} valid rows -> validate_dataset PASSED!')

    _, sum_a2 = agent2_intake.build_contract((pack_dir / '07_so_giao_dich_ngan_hang_A2.csv').read_bytes(), 'demo', 'MPX10', MPX_NAME)
    print(f'  [A2] contract PASSED: {sum_a2}')


def build_agent2_inputs(out: Path) -> None:
    """Agent 2 files the guide asks for: the training set (tab "Huấn luyện & mô hình") and the labelled
    contribution files for joint encrypted training (tab "Đóng góp huấn luyện"). Without a training upload the
    "Phân tích dữ liệu mới nhất" button has no model and answers ANALYZE_MODEL_REQUIRED."""
    import subprocess
    train = out / 'input-A2-training'
    contrib = out / 'input-A2-dong-gop'
    subprocess.run([sys.executable, str(ROOT / 'scripts/make_a2_training_input.py'), str(train), 'MPX10'], check=True)
    # Minh Phát's own ledger (10,000 transactions, 2023-2026, same columns as 07_so_giao_dich_ngan_hang_A2.csv).
    full = DS / 'a2' / 'transactions_full.csv'
    if full.is_file():
        shutil.copyfile(full, train / 'A2_huan_luyen_00_MinhPhat_2023-2026.csv')
    subprocess.run([sys.executable, str(ROOT / 'scripts/make_a2_contribution_input.py'), str(contrib)], check=True)


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    build_pack_01(OUT / '01_Goi_Chuan_Nap_Chung_4_Agent_MPX10')
    build_pack_02(OUT / '02_Goi_Bo_Sung_Ky_Moi_Test_Nap_Them')
    build_pack_03(OUT / '03_File_Test_Chuyen_Sau_Agent2_Agent3')
    build_agent2_inputs(OUT)
    write_cheatsheet(OUT)
    if '--verify' in sys.argv:
        verify_pack(OUT / '01_Goi_Chuan_Nap_Chung_4_Agent_MPX10')

    # Convenience copy in the current user's Downloads; the kit itself is OUT, so skip it when there is no such folder.
    if DOWNLOADS_COPY.parent.is_dir():
        if DOWNLOADS_COPY.exists():
            shutil.rmtree(DOWNLOADS_COPY)
        shutil.copytree(OUT, DOWNLOADS_COPY)
        print(f'[ok] Built {OUT} and mirrored to {DOWNLOADS_COPY}')
    else:
        print(f'[ok] Built {OUT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
