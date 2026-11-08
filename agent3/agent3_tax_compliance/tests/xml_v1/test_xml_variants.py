"""Valid structural variants of Decision 1450 invoices must not raise content errors; real defects still must."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_xml_invoice as fx  # noqa: E402
from src.extraction.xml_canonical import anchors  # noqa: E402
from src.extraction.xml_invoice import extract  # noqa: E402

T = date(2026, 11, 4)


def inv(symbol='K26TAA', lines='', totals='', words='Hai triệu hai trăm nghìn đồng', cur='VND', mccqt=''):
    tgia = '<TGia>25000</TGia>' if cur != 'VND' else ''
    return f'''<HDon><DLHDon Id="ID1"><TTChung><KHMSHDon>1</KHMSHDon><KHHDon>{symbol}</KHHDon><SHDon>00000012</SHDon>
<NLap>2026-03-01</NLap><DVTTe>{cur}</DVTTe>{tgia}<HTTToan>CK</HTTToan></TTChung>
<NDHDon><NBan><Ten>Công ty A</Ten><MST>{fx.SELLER}</MST></NBan><NMua><Ten>Công ty B</Ten><MST>{fx.BUYER}</MST></NMua>
<DSHHDVu>{lines}</DSHHDVu><TToan>{totals}<TgTTTBChu>{words}</TgTTTBChu></TToan></NDHDon></DLHDon>{mccqt}</HDon>'''.encode()


def line(stt, q, p, net, rate='10%', tchat=1, extra=''):
    qty = f'<SLuong>{q}</SLuong><DGia>{p}</DGia>' if q is not None else ''
    amt = f'<ThTien>{net}</ThTien>' if net is not None else ''
    return f'<HHDVu><TChat>{tchat}</TChat><STT>{stt}</STT><THHDVu>Hàng {stt}</THHDVu>{qty}{extra}{amt}<TSuat>{rate}</TSuat></HHDVu>'


def tot(net, vat, gross, groups):
    return f'<THTTLTSuat>{groups}</THTTLTSuat><TgTCThue>{net}</TgTCThue><TgTThue>{vat}</TgTThue><TgTTTBSo>{gross}</TgTTTBSo>'


def grp(rate, base, vat=None):
    return f'<LTSuat><TSuat>{rate}</TSuat><ThTien>{base}</ThTien>' + (f'<TThue>{vat}</TThue>' if vat is not None else '') + '</LTSuat>'


NOTE = '<HHDVu><TChat>4</TChat><STT>2</STT><THHDVu>Theo hợp đồng số 01</THHDVu></HHDVu>'
VALID = {
    'note_line': inv(lines=line(1, 2, 1000000, 2000000) + NOTE, totals=tot(2000000, 200000, 2200000, grp('10%', 2000000, 200000))),
    'exempt_group_without_tax': inv(lines=line(1, 1, 1000000, 1000000) + line(2, 1, 500000, 500000, 'KCT'),
                                    totals=tot(1500000, 100000, 1600000, grp('10%', 1000000, 100000) + grp('KCT', 500000)),
                                    words='Một triệu sáu trăm nghìn đồng'),
    'percentage_discount': inv(lines=line(1, 10, 100000, 900000, extra='<TLCKhau>10</TLCKhau>'),
                               totals=tot(900000, 90000, 990000, grp('10%', 900000, 90000)), words='Chín trăm chín mươi nghìn đồng'),
    'negative_discount_line': inv(lines=line(1, 10, 100000, 1000000) + line(2, None, None, -100000, tchat=3),
                                  totals=tot(900000, 90000, 990000, grp('10%', 900000, 90000)), words='Chín trăm chín mươi nghìn đồng'),
    'foreign_currency': inv(lines=line(1, 1, '1000.50', '1000.50', '0%'), totals=tot('1000.50', 0, '1000.50', grp('0%', '1000.50', 0)),
                            words='Một nghìn đô la Mỹ và năm mươi xu', cur='USD'),
    'cash_register_23_char_code': inv(symbol='C26MAA', lines=line(1, 2, 1000000, 2000000),
                                      totals=tot(2000000, 200000, 2200000, grp('10%', 2000000, 200000)), mccqt='<MCCQT>' + 'A' * 23 + '</MCCQT>'),
    'rounded_fractional_price': inv(lines=line(1, '13.457', '21345.678901', 287249), totals=tot(287249, 28725, 315974, grp('10%', 287249, 28725)),
                                    words='Ba trăm mười lăm nghìn chín trăm bảy mươi tư đồng'),
    'zero_value_promotion': inv(lines=line(1, 1, 0, 0, '0%', tchat=2), totals=tot(0, 0, 0, grp('0%', 0, 0)), words='Không đồng'),
}


def content_errors(raw):
    return sorted({c.code for c in extract(raw, T).errors} - {'XML_CHECK_SIGNATURE_SELLER'})


@pytest.mark.parametrize('name', sorted(VALID))
def test_valid_structural_variants_raise_no_content_error(name):
    assert content_errors(VALID[name]) == [], name


def test_note_lines_are_not_items_but_keep_their_position():
    raw = inv(lines=NOTE.replace('<STT>2', '<STT>1') + line(2, 2, 1000000, 2000000),
              totals=tot(2000000, 200000, 2200000, grp('10%', 2000000, 200000)))
    assert anchors(raw) == ['xml:HHDVu:2']


def test_real_defects_are_still_caught_after_relaxation():
    wrong_pct = inv(lines=line(1, 10, 100000, 950000, extra='<TLCKhau>10</TLCKhau>'),
                    totals=tot(950000, 95000, 1045000, grp('10%', 950000, 95000)), words='Một triệu không trăm bốn mươi lăm nghìn đồng')
    assert 'XML_CHECK_ARITH_LINE' in content_errors(wrong_pct)
    taxable_group_without_tax = inv(lines=line(1, 2, 1000000, 2000000), totals=tot(2000000, 200000, 2200000, grp('10%', 2000000)))
    assert 'XML_CHECK_ARITH_VAT_SUM' in content_errors(taxable_group_without_tax)
    bad_code = inv(symbol='C26TAA', lines=line(1, 2, 1000000, 2000000), totals=tot(2000000, 200000, 2200000, grp('10%', 2000000, 200000)),
                   mccqt='<MCCQT>' + 'A' * 20 + '</MCCQT>')
    assert 'XML_CHECK_AUTHORITY_CODE' in content_errors(bad_code)
    vnd_words_wrong = inv(lines=line(1, 2, 1000000, 2000000), totals=tot(2000000, 200000, 2200000, grp('10%', 2000000, 200000)),
                          words='Hai mươi hai triệu đồng')
    assert 'XML_CHECK_WORDS' in content_errors(vnd_words_wrong)


def test_listed_price_with_separate_commercial_discount_total_is_still_flagged_pending_specification():
    """TTCKTMai semantics (Phụ lục IV of Decision 1450) not yet read: keep flagging rather than guess."""
    raw = inv(lines=line(1, 10, 100000, 1000000), totals=tot(900000, 90000, 990000, grp('10%', 900000, 90000)).replace(
        '<TgTTTBSo>', '<TTCKTMai>100000</TTCKTMai><TgTTTBSo>'), words='Chín trăm chín mươi nghìn đồng')
    assert 'XML_CHECK_ARITH_SUM' in content_errors(raw)
