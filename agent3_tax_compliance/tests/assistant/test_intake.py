"""Intake: safe zip extraction, MT940 statements, suggested bank column mapping, policy questions from the legal corpus."""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from src.assistant import qa, synth
from src.assistant.input_schema import FILES, PROFILE_FIELDS
from src.assistant.intake import IntakeError, extract_zip, is_mt940, read_mt940, suggest_mapping

MT940 = b""":20:STMT1
:25:0123456789
:28C:1/1
:60F:C260801VND100000000,
:61:2608050805D2200000,NTRFFT0001//REF1
:86:TT HD 123 /ACCT/1020123456 /NAME/CONG TY A
:61:2608060806C5000000,NTRFNONREF
:86:Khach hang thanh toan
:61:2608070807RC2200000,NTRFREV
:86:Hoan tra giao dich loi
:62F:C260806VND102800000,
"""


def test_zip_extraction_flattens_paths_and_keeps_only_xml(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('../../evil.xml', '<HDon/>')
        z.writestr('thang7/hd 1.xml', '<HDon/>')
        z.writestr('readme.exe', 'MZ')
    names = extract_zip(buf.getvalue(), tmp_path / 'in')
    assert sorted(names) == ['evil.xml', 'hd_1.xml']
    assert not (tmp_path / 'evil.xml').exists() and not list((tmp_path / 'in').glob('*.exe'))


def test_zip_limits(tmp_path, monkeypatch):
    import src.assistant.intake as intake
    monkeypatch.setattr(intake, 'MAX_ZIP_FILES', 1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('a.xml', 'x')
        z.writestr('b.xml', 'y')
    with pytest.raises(IntakeError):
        extract_zip(buf.getvalue(), tmp_path)


def test_mt940_statement_lines_directions_and_reversals():
    assert is_mt940(MT940)
    t = read_mt940(MT940, 'vtb.sta')
    assert [(x.booked, x.amount, x.direction) for x in t] == [
        (date(2026, 8, 5), Decimal('2200000'), 'OUT'), (date(2026, 8, 6), Decimal('5000000'), 'IN'), (date(2026, 8, 7), Decimal('2200000'), 'OUT')]
    assert t[0].counterparty_account == '1020123456' and 'TT HD 123' in t[0].description


def test_suggested_mapping_for_known_and_unknown_layouts(tmp_path):
    p = tmp_path / 'vcb.csv'
    p.write_text('Sao kê tài khoản\n\nNgày GD,Số tham chiếu,Diễn giải,Phát sinh nợ,Phát sinh có,TK đối ứng,Tên đối ứng\n'
                 '05/08/2026,FT1,TT HD 123,"2.200.000",,0123,CONG TY A\n', encoding='utf-8')
    s = suggest_mapping(p)
    assert s['format']['columns'] == {'date': 'Ngày GD', 'debit': 'Phát sinh nợ', 'credit': 'Phát sinh có', 'description': 'Diễn giải',
                                      'counterparty_account': 'TK đối ứng', 'counterparty_name': 'Tên đối ứng'}
    assert s['format']['thousands'] == '.' and s['preview'][0] == dict(date='2026-08-05', debit='2200000', credit='', description='TT HD 123')
    x = tmp_path / 'b.xlsx'
    synth._write_xlsx(x, [['Posting Date', 'Remark', 'Debit', 'Credit'], ['2026-08-07', 'Pay', 3300000, '']])
    assert suggest_mapping(x)['format']['date_format'] == '%Y-%m-%d'
    bad = tmp_path / 'bad.csv'
    bad.write_text('a,b\n1,2\n', encoding='utf-8')
    with pytest.raises(IntakeError):
        suggest_mapping(bad)


def test_input_schema_is_complete_for_the_interface():
    assert {f['key'] for f in PROFILE_FIELDS} >= {'tax_code', 'legal_name', 'vat_method', 'filing_period'}
    assert all(f['how'] and f['accept'] for f in FILES)
    assert next(f for f in FILES if f['key'] == 'purchase_xml')['required'] is True


def test_policy_question_is_answered_from_the_legal_corpus(tmp_path, monkeypatch):
    from tests.lawbase.test_lawbase import LAW, page
    from src.lawbase.store import Corpus
    from src.lawbase.vbpl import parse_page
    db = tmp_path / 'law.sqlite3'
    c = Corpus(db)
    c.upsert(parse_page('https://vbpl.vn/van-ban/chi-tiet/luat', page('1', '108/2025/QH15', 'Luật', 'Luật', '2026-07-01', None, 'Còn hiệu lực', LAW)),
             'luat', 'm', 'h', True, True)
    c.db.commit()
    c.close()

    class FakeLLM:
        def chat(self, system, user, schema=None, num_predict=900):
            return json.dumps(dict(abstain=False, answer=[dict(text='Mức tính tiền chậm nộp là 0,03%/ngày.', sources=['P1'],
                                                                quote='Mức tính tiền chậm nộp bằng 0,03%/ngày')])), {}
    ctx = qa.Context(tmp_path, tmp_path / 'none.json', date(2026, 11, 5), report=None, lawbase_db=db, llm=FakeLLM())
    a = qa.answer('Quy định mức tính tiền chậm nộp mỗi ngày là gì?', ctx)
    assert a.branch == 'POLICY' and '0,03%' in a.text and '108/2025/QH15' in a.text
