"""Synthetic enterprise for development and demonstration when no real enterprise data is available.

Generates a workspace (see pipeline.py) with signed e-invoice XML following the Decision 1450 structure, bank
statements from two simulated banks with different layouts (CSV and XLSX), a portal invoice list, an adaptive pack,
reviewer decisions, and labels.json with the expected result of every injected scenario, including negative controls.
Results on this data measure the software against known answers; they say nothing about real enterprises.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import random
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from ..extraction.xml_invoice import mst_checksum_ok, words_to_int
from ..extraction.xml_signature import DS, canonical

UNITS = ['không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín']


def _three(n: int, full: bool) -> list[str]:
    h, t, u = n // 100, n // 10 % 10, n % 10
    out = []
    if full or h:
        out += [UNITS[h], 'trăm']
    if t == 0 and u and (full or h):
        out += ['lẻ']
    if t == 1:
        out += ['mười']
    elif t > 1:
        out += [UNITS[t], 'mươi']
    if u:
        out += ['mốt' if u == 1 and t > 1 else 'lăm' if u == 5 and t >= 1 else UNITS[u]]
    return out


def int_to_words_vi(n: int) -> str:
    """Vietnamese reading of a non-negative integer amount, e.g. 2200000 -> 'Hai triệu hai trăm nghìn đồng'."""
    if n == 0:
        return 'Không đồng'
    groups, scales = [], ['', 'nghìn', 'triệu', 'tỷ']
    while n:
        groups.append(n % 1000)
        n //= 1000
    words = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        words += _three(g, full=bool(words)) + ([scales[i]] if scales[i] else [])
    text = ' '.join(words) + ' đồng'
    return text[0].upper() + text[1:]


def valid_tax_id(prefix9: str) -> str:
    """First checksum-valid 10-digit code at or after the prefix (some prefixes have no valid check digit)."""
    for bump in range(50):
        p = str(int(prefix9) + bump).zfill(9)
        for d in range(10):
            if mst_checksum_ok(p + str(d)):
                return p + str(d)
    raise ValueError(prefix9)


@dataclass
class Seller:
    code: str
    name: str
    tax_id: str
    account: str
    symbol: str
    vat: str = '10%'
    key: object = None
    cert_b64: str = ''
    counter: int = 0


@dataclass
class Scenario:
    labels: dict = field(default_factory=dict)
    payments: list = field(default_factory=list)
    sales: dict = field(default_factory=dict)          # the company's own sales invoices    # (date, amount, account, name, description, bank)
    files: dict = field(default_factory=dict)


def _make_cert(seller: Seller):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'{seller.code} MST:{seller.tax_id}')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(random.randint(1, 10**9))
            .not_valid_before(dt.datetime(2025, 1, 1)).not_valid_after(dt.datetime(2027, 12, 31)).sign(key, hashes.SHA256()))
    seller.key = key
    seller.cert_b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()


def sign(body: str, seller: Seller, signing_time: str) -> bytes:
    root = etree.fromstring(body.encode('utf-8'))
    digest = base64.b64encode(hashlib.sha256(canonical(root.find('DLHDon'))).digest()).decode()
    sig = etree.fromstring(f'''<ds:Signature xmlns:ds="{DS}"><ds:SignedInfo>
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference URI="#{root.find('DLHDon').get('Id')}"><ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/><ds:DigestValue>{digest}</ds:DigestValue></ds:Reference>
</ds:SignedInfo><ds:SignatureValue>AA==</ds:SignatureValue><ds:KeyInfo><ds:X509Data><ds:X509Certificate>{seller.cert_b64}</ds:X509Certificate></ds:X509Data></ds:KeyInfo>
<ds:Object><ds:SignatureProperties><ds:SignatureProperty><ds:SigningTime>{signing_time}</ds:SigningTime></ds:SignatureProperty></ds:SignatureProperties></ds:Object></ds:Signature>''')
    root.find('DSCKS/NBan').append(sig)
    info = root.find(f'DSCKS/NBan/{{{DS}}}Signature/{{{DS}}}SignedInfo')
    value = seller.key.sign(canonical(info), padding.PKCS1v15(), hashes.SHA256())
    root.find(f'DSCKS/NBan/{{{DS}}}Signature/{{{DS}}}SignatureValue').text = base64.b64encode(value).decode()
    return etree.tostring(root, encoding='utf-8', xml_declaration=True)


class Builder:
    def __init__(self, company: dict, rng: random.Random):
        self.company, self.rng, self.sc = company, rng, Scenario()

    def invoice(self, seller: Seller, day: date, lines: list, *, payment_label='CK', buyer_tax_id=None, buyer_name=None,
                related=None, labels=(), note='', file_suffix=''):
        """lines: list of (description, quantity, unit_price). Returns (file name, gross)."""
        seller.counter += 1
        number = f'{seller.counter:08d}'
        rate = int(seller.vat.rstrip('%'))
        rows, net = [], 0
        for n, (desc, q, p) in enumerate(lines, 1):
            amount = q * p
            net += amount
            rows.append(f'<HHDVu><TChat>1</TChat><STT>{n}</STT><THHDVu>{escape(desc)}</THHDVu><DVTinh>Cái</DVTinh><SLuong>{q}</SLuong>'
                        f'<DGia>{p}</DGia><ThTien>{amount}</ThTien><TSuat>{seller.vat}</TSuat></HHDVu>')
        vat = net * rate // 100
        gross = net + vat
        rel = ''
        if related:
            nature, rsym, rnum, rday = related
            rel = (f'<TTHDLQuan><TCHDon>{nature}</TCHDon><LHDCLQuan>1</LHDCLQuan><KHMSHDCLQuan>1</KHMSHDCLQuan><KHHDCLQuan>{rsym}</KHHDCLQuan>'
                   f'<SHDCLQuan>{rnum}</SHDCLQuan><NLHDCLQuan>{rday}</NLHDCLQuan></TTHDLQuan>')
        body = f'''<HDon><DLHDon Id="DL{seller.code}{number}"><TTChung><PBan>2.1.0</PBan><THDon>Hóa đơn giá trị gia tăng</THDon><KHMSHDon>1</KHMSHDon>
<KHHDon>{seller.symbol}</KHHDon><SHDon>{number}</SHDon><NLap>{day.isoformat()}</NLap><DVTTe>VND</DVTTe><HTTToan>{payment_label}</HTTToan>{rel}</TTChung>
<NDHDon><NBan><Ten>{escape(seller.name)}</Ten><MST>{seller.tax_id}</MST><DChi>Địa chỉ mô phỏng</DChi><STKNHang>{seller.account}</STKNHang></NBan>
<NMua><Ten>{escape(buyer_name or self.company['legal_name'])}</Ten><MST>{buyer_tax_id or self.company['tax_code']}</MST><DChi>{escape(self.company['registered_address'])}</DChi></NMua>
<DSHHDVu>{''.join(rows)}</DSHHDVu><TToan><THTTLTSuat><LTSuat><TSuat>{seller.vat}</TSuat><ThTien>{net}</ThTien><TThue>{vat}</TThue></LTSuat></THTTLTSuat>
<TgTCThue>{net}</TgTCThue><TgTThue>{vat}</TgTThue><TgTTTBSo>{gross}</TgTTTBSo><TgTTTBChu>{int_to_words_vi(gross)}</TgTTTBChu></TToan></NDHDon></DLHDon>
<DSCKS><NBan/></DSCKS></HDon>'''
        assert words_to_int(int_to_words_vi(gross)) == gross
        raw = sign(body, seller, f'{day.isoformat()}T10:00:00')
        name = f'{day.isoformat()}_{seller.code}_{number}{file_suffix}.xml'
        self.sc.files[name] = raw
        self.sc.labels[name] = dict(expected=sorted(labels), note=note, seller=seller.code, number=number, gross=gross, vat=vat)
        return name, number, gross

    def pay(self, day, amount, seller=None, *, account=None, name=None, desc=None, bank='A', signal='account'):
        acc = account if account is not None else (seller.account if seller and signal == 'account' else '')
        nm = name if name is not None else (seller.name.upper() if seller and signal in ('account', 'name') else '')
        self.sc.payments.append((day, amount, acc, nm, desc or 'Thanh toan', bank))


def _fmt(n: int) -> str:
    return f'{n:,}'.replace(',', '.')


def _write_xlsx(path: Path, rows: list[list]):
    def cell(ref, v):
        if isinstance(v, int):
            return f'<c r="{ref}"><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
    cols = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    sheet = ''.join(f'<row r="{r}">' + ''.join(cell(f'{cols[c]}{r}', v) for c, v in enumerate(row)) + '</row>' for r, row in enumerate(rows, 1))
    parts = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="SaoKe" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml': '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{sheet}</sheetData></worksheet>'}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, content in parts.items():
            z.writestr(n, content)
    path.write_bytes(buf.getvalue())


BANK_A = dict(name='Ngân hàng mô phỏng A (CSV)', columns=dict(date='Ngày giao dịch', debit='Số tiền ghi nợ', credit='Số tiền ghi có',
              description='Nội dung', counterparty_account='Số tài khoản đối ứng', counterparty_name='Tên đơn vị đối ứng'),
              date_format='%d/%m/%Y', thousands='.', decimal=',', delimiter=',')
BANK_B = dict(name='Ngân hàng mô phỏng B (XLSX)', columns=dict(date='Posting Date', debit='Debit', credit='Credit', description='Remark',
              counterparty_account='Beneficiary Account', counterparty_name='Beneficiary Name'),
              date_format='%Y-%m-%d', thousands=',', decimal='.', delimiter=',')


def generate(out: Path, seed: int = 7) -> dict:
    rng = random.Random(seed)
    random.seed(seed)
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    company = dict(tax_code=valid_tax_id('010999998'), legal_name='Công ty TNHH Vật liệu Xây dựng Minh An',
                   registered_address='Số 12 đường Mô Phỏng, phường Thử Nghiệm, Hà Nội')
    names = [('V01', 'Công ty Cổ phần Xi măng Bắc Hà', '10%'), ('V02', 'Công ty TNHH Thép Đông Phong', '10%'), ('V03', 'Công ty TNHH Gạch Ngói Phú Thọ', '10%'),
             ('V04', 'Công ty TNHH Vận tải Hòa Bình', '8%'), ('V05', 'Cửa hàng Văn phòng phẩm Hồng Hà', '10%'), ('V06', 'Nhà hàng Sen Vàng', '8%'),
             ('V07', 'Công ty TNHH Điện máy Thành Công', '10%'), ('V08', 'Công ty TNHH Thiết bị Kim Long', '10%'), ('V09', 'Công ty TNHH Sửa chữa Cơ khí An Phú', '10%'),
             ('V10', 'Công ty TNHH Sơn Nam Việt', '10%'), ('V11', 'Công ty TNHH Thương mại Quang Minh', '10%')]
    sellers = {}
    for n, (code, nm, vat) in enumerate(names, 1):
        s = Seller(code, nm, valid_tax_id(f'03{n:02d}88877'), f'1{n:02d}0{rng.randint(10**8, 10**9 - 1)}',
                   f'K26T{chr(64 + n)}{chr(64 + n)}', vat, counter=rng.randint(120, 900))
        _make_cert(s)
        sellers[code] = s
    b = Builder(company, rng)
    V = sellers
    months = [7, 8, 9]

    # Regular, properly paid purchases with a mix of matching signals.
    for m in months:
        for k, (code, item, price, signal) in enumerate([('V01', 'Xi măng PCB40', 95000, 'account'), ('V02', 'Thép cuộn D8', 18500, 'name'),
                                                         ('V03', 'Gạch đặc A1', 1450, 'number'), ('V04', 'Cước vận chuyển', 1200000, 'account')]):
            day = date(2026, m, 3 + k * 5)
            qty = {'V01': 200, 'V02': 1500, 'V03': 9000, 'V04': 4}[code]
            f, num, gross = b.invoice(V[code], day, [(item, qty, price)], note='mua hàng thường xuyên, đã chuyển khoản')
            desc = f'TT HD {int(num)} {V[code].code}' if signal == 'number' else 'Thanh toan tien hang'
            b.pay(day + timedelta(days=rng.randint(2, 20)), gross, V[code], desc=desc, signal=signal)

    # S1 R01: from the threshold, no transfer.
    b.invoice(V['V07'], date(2026, 7, 21), [('Máy phát điện 5kVA', 1, 30000000)], payment_label='TM', labels=['R01_PAYMENT_EVIDENCE'],
              note='S1 trả tiền mặt 33 triệu đồng')
    b.invoice(V['V06'], date(2026, 8, 14), [('Chi phí tiếp khách đối tác', 1, 6100000)], payment_label='TM', labels=['R01_PAYMENT_EVIDENCE'],
              note='S1 và S16 tiếp khách trả tiền mặt trên ngưỡng')
    b.invoice(V['V01'], date(2026, 9, 25), [('Xi măng PCB40', 220, 95000)], labels=['R01_PAYMENT_EVIDENCE'], note='S1 chưa thanh toán trong kỳ sao kê')

    # S2 R02 and S3, S4 negative controls (small cash purchases).
    for t in range(3):
        b.invoice(V['V05'], date(2026, 8, 6), [('Giấy in A4', 25, 80000)], payment_label='TM', labels=['R02_SAME_DAY_CUMULATIVE'],
                  note='S2 ba hóa đơn 2,2 triệu đồng cùng ngày, trả tiền mặt')
    b.invoice(V['V05'], date(2026, 8, 20), [('Bút bi', 100, 20000)], payment_label='TM', note='S3 đối chứng: hai hóa đơn cùng ngày tổng dưới ngưỡng')
    b.invoice(V['V05'], date(2026, 8, 20), [('Sổ tay', 50, 22000)], payment_label='TM', note='S3 đối chứng')
    b.invoice(V['V05'], date(2026, 9, 9), [('Mực in', 10, 400000)], payment_label='TM', note='S4 đối chứng: một hóa đơn dưới ngưỡng trả tiền mặt')

    # S5 split payments, S6 combined payment (negative controls for R01).
    f, num, gross = b.invoice(V['V02'], date(2026, 9, 5), [('Thép hình I200', 2500, 20000)], note='S5 đối chứng: trả ba lần')
    for part, d in ((20000000, 7), (20000000, 15), (gross - 40000000, 28)):
        b.pay(date(2026, 9, 5) + timedelta(days=d), part, V['V02'], desc='Thanh toan dot hang thep')
    f1, n1, g1 = b.invoice(V['V04'], date(2026, 8, 22), [('Cước vận chuyển chuyến 1', 1, 6000000)], note='S6 đối chứng: một lần trả cho hai hóa đơn')
    f2, n2, g2 = b.invoice(V['V04'], date(2026, 8, 24), [('Cước vận chuyển chuyến 2', 1, 5000000)], note='S6 đối chứng')
    b.pay(date(2026, 8, 30), g1 + g2, V['V04'], desc=f'TT cuoc van chuyen HD {int(n1)} {int(n2)}')

    # S7 ambiguous: same amount sent to a third party.
    f, num, gross = b.invoice(V['V03'], date(2026, 7, 28), [('Gạch block', 10000, 1000)], labels=['R03_AMBIGUOUS_PAYMENT'], note='S7 chuyển cho bên thứ ba')
    b.pay(date(2026, 8, 2), gross, account='9704' + str(rng.randint(10**8, 10**9 - 1)), name='CONG TY TAI CHINH XYZ', desc='Chuyen tien')

    # S8 duplicate file of a paid invoice.
    f, num, gross = b.invoice(V['V01'], date(2026, 8, 18), [('Xi măng rời', 300, 90000)], note='S8 bản gốc, đã chuyển khoản')
    b.pay(date(2026, 8, 25), gross, V['V01'])
    b.sc.files[f.replace('.xml', '_banSao.xml')] = b.sc.files[f]
    b.sc.labels[f.replace('.xml', '_banSao.xml')] = dict(b.sc.labels[f], expected=['R05_DUPLICATE'], note='S8 bản sao nhập trùng')

    # S9 replaced invoice: original stays in the data.
    f, onum, og = b.invoice(V['V09'], date(2026, 7, 10), [('Sửa chữa máy trộn', 1, 8000000)], labels=['R06_REPLACED_ORIGINAL', 'R01_PAYMENT_EVIDENCE'],
                            note='S9 hóa đơn gốc đã bị thay thế, vẫn còn trong dữ liệu')
    f, rnum, rg = b.invoice(V['V09'], date(2026, 7, 15), [('Sửa chữa máy trộn (lập lại)', 1, 9000000)],
                            related=('1', V['V09'].symbol, onum, '2026-07-10'), note='S9 hóa đơn thay thế, đã chuyển khoản')
    b.pay(date(2026, 7, 20), rg, V['V09'])

    # S10 file changed after signing.
    f, num, gross = b.invoice(V['V03'], date(2026, 9, 12), [('Gạch ốp lát', 400, 25000)], labels=['R04_INVOICE_INTEGRITY'], note='S10 sửa nội dung sau khi ký')
    b.sc.files[f] = b.sc.files[f].replace('Gạch ốp lát'.encode(), 'Gạch men cao cấp'.encode())
    b.pay(date(2026, 9, 18), gross, V['V03'])

    # S11 buyer tax id of another company; S12 buyer name differs.
    f, num, gross = b.invoice(V['V01'], date(2026, 7, 30), [('Xi măng PCB30', 150, 88000)], buyer_tax_id=valid_tax_id('010777666'),
                              labels=['R07_BUYER_TAX_ID'], note='S11 ghi nhầm mã số thuế người mua')
    b.pay(date(2026, 8, 5), gross, V['V01'])
    f, num, gross = b.invoice(V['V03'], date(2026, 8, 27), [('Gạch đặc A2', 6000, 1500)], buyer_name='Cửa hàng Vật liệu Minh An',
                              labels=['R07_BUYER_NAME'], note='S12 tên người mua khác hồ sơ')
    b.pay(date(2026, 9, 2), gross, V['V03'])

    # S13 seller on a published risk list.
    for d in (date(2026, 7, 16), date(2026, 9, 16)):
        f, num, gross = b.invoice(V['V08'], d, [('Máy cắt gạch', 2, 4500000)], labels=['R08_RISKY_SELLER'], note='S13 người bán trong danh sách rủi ro')
        b.pay(d + timedelta(days=4), gross, V['V08'])

    # S14 invoice missing from the portal list; S15 vendor outlier paid through bank B (XLSX).
    f14, num, gross = b.invoice(V['V11'], date(2026, 8, 11), [('Phụ kiện cửa nhôm', 30, 400000)], labels=['R09_NOT_ON_PORTAL'],
                                note='S14 không có trong bảng kê cổng thuế')
    b.pay(date(2026, 8, 15), gross, V['V11'])
    for k in range(6):
        f, num, gross = b.invoice(V['V10'], date(2026, 7, 2) + timedelta(days=9 * k), [('Sơn chống thấm 5L', 4, 500000)], note='S15 lịch sử đều')
        b.pay(date(2026, 7, 4) + timedelta(days=9 * k), gross, V['V10'], bank='B')
    f, num, gross = b.invoice(V['V10'], date(2026, 9, 22), [('Sơn chống thấm 5L', 50, 500000)], labels=['R11_VENDOR_OUTLIER'], note='S15 số tiền lệch xa')
    b.pay(date(2026, 9, 26), gross, V['V10'], bank='B')

    # S16 internal policy flag only (paid by transfer).
    f, num, gross = b.invoice(V['V06'], date(2026, 9, 19), [('Chi phí tiếp khách', 1, 3000000)], note='S16 cờ chính sách nội bộ, không phải rủi ro')
    b.pay(date(2026, 9, 21), gross, V['V06'])

    # S17 negative control: reviewer attached evidence from an account not loaded.
    f17, num17, g17 = b.invoice(V['V07'], date(2026, 9, 3), [('Quạt công nghiệp', 5, 2000000)], note='S17 đối chứng: người duyệt đã đính kèm ủy nhiệm chi')

    # S18 a line that does not look like business use (found only by the AI layer, A1); paid by transfer.
    f18, num18, g18 = b.invoice(V['V07'], date(2026, 9, 8), [('Điện thoại di động iPhone 16 Pro Max 256GB', 1, 32000000), ('Máy khoan bê tông Bosch GBH 2-26', 1, 3500000)],
                                note='S18 dòng hàng có thể không phục vụ kinh doanh (chỉ lớp AI phát hiện)')
    b.pay(date(2026, 9, 10), g18, V['V07'])

    # S19 low-volume seller: invoice number 3 of its symbol in September, large amount, paid by transfer.
    v12 = Seller('V12', 'Công ty TNHH Thương mại Dịch vụ Hưng Phát', valid_tax_id('031288877'), f'1120{rng.randint(10**8, 10**9 - 1)}', 'K26TLL', '10%', counter=2)
    _make_cert(v12)
    V['V12'] = v12
    f19, num19, g19 = b.invoice(v12, date(2026, 9, 24), [('Thép hình I200', 4000, 15000)], labels=['R13_LOW_VOLUME_SELLER'],
                                note='S19 người bán mới lập rất ít hóa đơn trong năm')
    b.pay(date(2026, 9, 27), g19, v12, signal='name')

    # S20 paid from the owner's other account; only the free-text note names the seller (found only by the AI layer, A2).
    f20, num20, g20 = b.invoice(V['V09'], date(2026, 9, 14), [('Sửa chữa cẩu trục kho', 1, 12500000)], labels=['R03_AMBIGUOUS_PAYMENT'],
                                note='S20 chỉ nội dung chuyển khoản nhắc tên người bán (lớp AI đề xuất ghép, người duyệt xác nhận)')
    b.pay(date(2026, 9, 19), g20, account='0451000' + str(rng.randint(100000, 999999)), name='TRAN THI B',
          desc='ck tien sua cau truc kho cho co khi an phu')

    # Sales: the company's own invoices to a customer, paid by transfer; S21 a receipt with no sales invoice.
    own = Seller('MA', company['legal_name'], company['tax_code'], '0123456789', 'C26TMA', '10%', counter=40)
    _make_cert(own)
    customer = (valid_tax_id('010555444'), 'Công ty TNHH Xây dựng Khách hàng Mô phỏng')
    sales_paid = []
    for m in (7, 8):
        fs, _, gs = b.invoice(own, date(2026, m, 24), [('Xi măng PCB40 bao 50kg', 1000, 100000)], buyer_tax_id=customer[0], buyer_name=customer[1])
        b.sc.sales[fs] = b.sc.files.pop(fs)
        b.sc.labels.pop(fs)
        sales_paid.append((date(2026, m, 26), gs))
    sales_paid.append((date(2026, 9, 26), 120000000))       # S21: money received, no sales invoice

    # Noise: customer receipts, salaries, utilities.
    for m in months:
        b.pay(date(2026, m, 10), 45000000, account='0011002233', name='NGUYEN VAN A VA CAC NHAN VIEN', desc=f'Tra luong thang {m - 1}')
        b.pay(date(2026, m, 12), 3850000, account='1600201001', name='DIEN LUC MO PHONG', desc='Tien dien')
    # Write workspace.
    (out / 'invoices' / 'purchase').mkdir(parents=True)
    for name, raw in sorted(b.sc.files.items()):
        (out / 'invoices' / 'purchase' / name).write_bytes(raw)
    (out / 'bank').mkdir()
    rows_a = [['SAO KÊ TÀI KHOẢN (MÔ PHỎNG)'], ['Số tài khoản: 0123456789'], [],
              ['Ngày giao dịch', 'Số tham chiếu', 'Nội dung', 'Số tiền ghi nợ', 'Số tiền ghi có', 'Số tài khoản đối ứng', 'Tên đơn vị đối ứng']]
    rows_b = [['Posting Date', 'Ref', 'Remark', 'Debit', 'Credit', 'Beneficiary Account', 'Beneficiary Name']]
    for n, (day, amount, acc, nm, desc, bank) in enumerate(sorted(b.sc.payments, key=lambda p: (p[0], p[1])), 1):
        if bank == 'A':
            rows_a.append([day.strftime('%d/%m/%Y'), f'FT{n:06d}', desc, _fmt(amount), '', acc, nm])
        else:
            rows_b.append([day.isoformat(), f'B{n:05d}', desc, amount, '', acc, nm])
    for k, (day, amount) in enumerate(sales_paid, 1):
        rows_a.append([day.strftime('%d/%m/%Y'), f'IN{k}', 'Khach hang thanh toan', '', _fmt(amount), '0099887766', 'CONG TY KHACH HANG'])
    (out / 'invoices' / 'sales').mkdir(parents=True, exist_ok=True)
    for name, raw in sorted(b.sc.sales.items()):
        (out / 'invoices' / 'sales' / name).write_bytes(raw)
    rows_a.append(['', '', 'Tổng cộng', '', '', '', ''])
    import csv
    with open(out / 'bank' / 'saoke_nganhang_A.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        csv.writer(fh).writerows(rows_a)
    _write_xlsx(out / 'bank' / 'saoke_nganhang_B.xlsx', rows_b)

    # Portal list: every invoice except S14, plus one portal invoice with no XML.
    (out / 'portal').mkdir()
    portal = [['MST người bán', 'Ký hiệu mẫu số', 'Ký hiệu hóa đơn', 'Số hóa đơn', 'Ngày lập', 'Tổng tiền thuế', 'Tổng tiền thanh toán']]
    for name, lab in sorted(b.sc.labels.items()):
        if name == f14 or name.endswith('_banSao.xml'):
            continue
        s = V[lab['seller']]
        portal.append([s.tax_id, '1', s.symbol, lab['number'], name[:10], lab['vat'], lab['gross']])
    portal.append([V['V01'].tax_id, '1', V['V01'].symbol, '00000099', '2026-09-28', 1650000, 18150000])
    with open(out / 'portal' / 'purchase_list.csv', 'w', encoding='utf-8-sig', newline='') as fh:
        csv.writer(fh).writerows(portal)

    pack = dict(pack_version=1, simulated=True, profile=dict(company, industry=['4663 Bán buôn vật liệu xây dựng'], vat_method='DEDUCTION',
                filing_period='MONTH'), bank_formats=[BANK_A, BANK_B], thresholds={},
                policies=[dict(id='TIEP_KHACH', flag='Chi tiếp khách trên 2 triệu đồng cần giấy đề nghị thanh toán và danh sách khách',
                               min_gross=2000000, description_contains=['tiếp khách'])],
                reference_lists=[dict(name='Danh sách doanh nghiệp rủi ro (mô phỏng)', as_of='2026-06-30', tax_ids=[V['V08'].tax_id],
                                      source='tệp mô phỏng, không phải công văn thật')])
    (out / 'pack.json').write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding='utf-8')
    key17 = f'{V["V07"].tax_id}|1{V["V07"].symbol}|{int(num17)}'
    (out / 'decisions.json').write_text(json.dumps([dict(invoice_key=key17, action='PAYMENT_EVIDENCE_ATTACHED', evidence='UNC số 5521 ngày 05/09/2026 (bản quét)',
                                                         by='Kế toán trưởng (mô phỏng)', at='2026-10-10')], ensure_ascii=False, indent=2), encoding='utf-8')
    labels = dict(files=b.sc.labels, portal_only={f'{V["V01"].tax_id}|1{V["V01"].symbol}|99': ['R09_UNCAPTURED']},
                  policy_flags=['S16'], as_of='2026-10-15')
    (out / 'labels.json').write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding='utf-8')
    return dict(workspace=str(out), invoices=len(b.sc.files), payments=len(b.sc.payments), sellers=len(sellers))
