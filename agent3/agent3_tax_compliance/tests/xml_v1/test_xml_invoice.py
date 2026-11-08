import base64
import datetime as dt
import hashlib
from datetime import date

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from src.extraction.xml_invoice import FIDELITY_SIGNED, FIDELITY_UNSIGNED, extract, mst_checksum_ok, words_to_int
from src.extraction.xml_signature import DS, canonical

TODAY = date(2026, 11, 4)


def _valid_tax_id(prefix='010010910'):
    for d in range(10):
        if mst_checksum_ok(prefix + str(d)):
            return prefix + str(d)
    raise AssertionError


SELLER = _valid_tax_id()
BUYER = _valid_tax_id('030000000')

BODY = f'''<HDon><DLHDon Id="ID1"><TTChung><KHMSHDon>1</KHMSHDon><KHHDon>K26TAA</KHHDon><SHDon>00000012</SHDon>
<NLap>2026-03-01</NLap><DVTTe>VND</DVTTe><HTTToan>CK</HTTToan><THDon>Hóa đơn giá trị gia tăng</THDon></TTChung>
<NDHDon><NBan><Ten>Công ty A</Ten><MST>{SELLER}</MST></NBan><NMua><Ten>Công ty B</Ten><MST>{BUYER}</MST></NMua>
<DSHHDVu><HHDVu><STT>1</STT><THHDVu>Dịch vụ</THHDVu><SLuong>2</SLuong><DGia>1000000</DGia><ThTien>2000000</ThTien><TSuat>10%</TSuat></HHDVu></DSHHDVu>
<TToan><THTTLTSuat><LTSuat><TSuat>10%</TSuat><ThTien>2000000</ThTien><TThue>200000</TThue></LTSuat></THTTLTSuat>
<TgTCThue>2000000</TgTCThue><TgTThue>200000</TgTThue><TgTTTBSo>2200000</TgTTTBSo>
<TgTTTBChu>Hai triệu hai trăm nghìn đồng</TgTTTBChu></TToan></NDHDon></DLHDon><DSCKS><NBan/></DSCKS></HDon>'''


def signed_invoice(body=BODY) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Cong ty A MST:{SELLER}')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(dt.datetime(2025, 1, 1)).not_valid_after(dt.datetime(2027, 1, 1))
            .sign(key, hashes.SHA256()))
    root = etree.fromstring(body.encode())
    digest = base64.b64encode(hashlib.sha256(canonical(root.find('DLHDon'))).digest()).decode()
    cert_b64 = base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
    sig = etree.fromstring(f'''<ds:Signature xmlns:ds="{DS}"><ds:SignedInfo>
<ds:CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<ds:Reference URI="#ID1"><ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/><ds:DigestValue>{digest}</ds:DigestValue></ds:Reference>
</ds:SignedInfo><ds:SignatureValue>AA==</ds:SignatureValue><ds:KeyInfo><ds:X509Data><ds:X509Certificate>{cert_b64}</ds:X509Certificate></ds:X509Data></ds:KeyInfo>
<ds:Object><ds:SignatureProperties><ds:SignatureProperty><SigningTime>x</SigningTime></ds:SignatureProperty></ds:SignatureProperties></ds:Object></ds:Signature>''')
    sig.find('.//SigningTime').tag = f'{{{DS}}}SigningTime'
    sig.find(f'.//{{{DS}}}SigningTime').text = '2026-03-01T10:00:00'
    root.find('DSCKS/NBan').append(sig)
    info = root.find(f'DSCKS/NBan/{{{DS}}}Signature/{{{DS}}}SignedInfo')
    value = key.sign(canonical(info), padding.PKCS1v15(), hashes.SHA256())
    root.find(f'DSCKS/NBan/{{{DS}}}Signature/{{{DS}}}SignatureValue').text = base64.b64encode(value).decode()
    return etree.tostring(root, encoding='utf-8')


def codes(inv):
    return {c.code for c in inv.errors}


def test_valid_signed_invoice_has_no_errors_and_signed_fidelity():
    inv = extract(signed_invoice(), TODAY)
    assert not inv.errors, [(c.code, c.note) for c in inv.errors]
    assert inv.fidelity_policy == FIDELITY_SIGNED
    assert inv.fields['gross_total'].xpath == 'HDon/DLHDon/NDHDon/TToan/TgTTTBSo'


def test_changed_total_is_detected_by_words_arithmetic_and_signature():
    inv = extract(signed_invoice().replace(b'<TgTTTBSo>2200000<', b'<TgTTTBSo>22000000<'), TODAY)
    assert {'XML_CHECK_WORDS', 'XML_CHECK_ARITH_GROSS', 'XML_CHECK_SIGNATURE_SELLER'} <= codes(inv)
    assert inv.fidelity_policy == FIDELITY_UNSIGNED


def test_consistent_times_ten_forgery_is_caught_by_words_and_signature():
    raw = signed_invoice()
    for old, new in ((b'<DGia>1000000<', b'<DGia>10000000<'), (b'<ThTien>2000000<', b'<ThTien>20000000<'),
                     (b'<TThue>200000<', b'<TThue>2000000<'), (b'<TgTCThue>2000000<', b'<TgTCThue>20000000<'),
                     (b'<TgTThue>200000<', b'<TgTThue>2000000<'), (b'<TgTTTBSo>2200000<', b'<TgTTTBSo>22000000<')):
        assert old in raw
        raw = raw.replace(old, new)
    inv = extract(raw, TODAY)
    assert 'XML_CHECK_ARITH_GROSS' not in codes(inv)  # arithmetic alone is fooled
    assert {'XML_CHECK_WORDS', 'XML_CHECK_SIGNATURE_SELLER'} <= codes(inv)


def test_unsigned_invoice_is_never_signed_fidelity():
    inv = extract(BODY.encode(), TODAY)
    assert 'XML_CHECK_SIGNATURE_SELLER' in codes(inv)
    assert inv.fidelity_policy == FIDELITY_UNSIGNED


def test_future_date_and_bad_rate_and_bad_tax_id():
    raw = BODY.replace('2026-03-01', '2027-03-01').replace('<TSuat>10%</TSuat></HHDVu>', '<TSuat>7%</TSuat></HHDVu>')
    raw = raw.replace(f'<MST>{BUYER}', f'<MST>{BUYER[:-1]}{(int(BUYER[-1]) + 1) % 10}')
    assert {'XML_CHECK_DATE', 'XML_CHECK_VAT_RATE', 'XML_CHECK_TAX_ID_CHECKSUM'} <= codes(extract(raw.encode(), TODAY))


def test_doctype_and_foreign_xml_are_rejected():
    with pytest.raises(Exception):
        extract(b'<!DOCTYPE HDon [<!ENTITY x "y">]>' + BODY.encode(), TODAY)
    with pytest.raises(ValueError):
        extract(b'<root><a/></root>', TODAY)


@pytest.mark.parametrize('text,value', [('Hai triệu hai trăm nghìn đồng', 2200000), ('Một trăm lẻ năm đồng', 105),
                                        ('Mười lăm nghìn đồng', 15000), ('Hai mươi mốt triệu đồng', 21000000),
                                        ('Hai tỷ đồng chẵn', 2000000000)])
def test_words_to_int(text, value):
    assert words_to_int(text) == value


def test_words_unreadable_returns_none():
    assert words_to_int('abc') is None
