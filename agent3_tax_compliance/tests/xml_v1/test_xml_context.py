"""Context guards: buyer versus profile, vendor history (V3, V5), replacement / adjustment references (V10)."""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_xml_invoice as fx  # noqa: E402
import test_xml_pipeline as pipe  # noqa: E402
from src.domain.taxpayer import TaxpayerMaster  # noqa: E402
from src.extraction.xml_context import (MIN_HISTORY, amount_outlier, buyer_profile_issues, fold,  # noqa: E402
                                        similarity, vendor_and_reference_issues)
from src.extraction.xml_invoice import extract  # noqa: E402
from src.quality.repository import replay  # noqa: E402

WORDS = {2: 'Hai triệu hai trăm nghìn đồng', 3: 'Ba triệu ba trăm nghìn đồng', 10: 'Mười một triệu đồng'}


def body(number='00000012', qty=2, words=None, buyer_name='Công ty B', buyer_address=None, related=None, seller_name='Công ty A'):
    net = qty * 1000000
    vat = net // 10
    gross = net + vat
    words = words or {2: WORDS[2], 3: WORDS[3], 10: WORDS[10]}[qty]
    rel = ''
    if related:
        nature, template, symbol, num, day = related
        rel = (f'<TTHDLQuan><TCHDon>{nature}</TCHDon><LHDCLQuan>1</LHDCLQuan><KHMSHDCLQuan>{template}</KHMSHDCLQuan>'
               f'<KHHDCLQuan>{symbol}</KHHDCLQuan><SHDCLQuan>{num}</SHDCLQuan><NLHDCLQuan>{day}</NLHDCLQuan></TTHDLQuan>')
    addr = f'<DChi>{buyer_address}</DChi>' if buyer_address else ''
    return f'''<HDon><DLHDon Id="ID1"><TTChung><KHMSHDon>1</KHMSHDon><KHHDon>K26TAA</KHHDon><SHDon>{number}</SHDon>
<NLap>2026-03-01</NLap><DVTTe>VND</DVTTe><HTTToan>CK</HTTToan><THDon>Hóa đơn giá trị gia tăng</THDon>{rel}</TTChung>
<NDHDon><NBan><Ten>{seller_name}</Ten><MST>{fx.SELLER}</MST></NBan><NMua><Ten>{buyer_name}</Ten><MST>{fx.BUYER}</MST>{addr}</NMua>
<DSHHDVu><HHDVu><STT>1</STT><THHDVu>Dịch vụ</THHDVu><SLuong>{qty}</SLuong><DGia>1000000</DGia><ThTien>{net}</ThTien><TSuat>10%</TSuat></HHDVu></DSHHDVu>
<TToan><THTTLTSuat><LTSuat><TSuat>10%</TSuat><ThTien>{net}</ThTien><TThue>{vat}</TThue></LTSuat></THTTLTSuat>
<TgTCThue>{net}</TgTCThue><TgTThue>{vat}</TgTThue><TgTTTBSo>{gross}</TgTTTBSo>
<TgTTTBChu>{words}</TgTTTBChu></TToan></NDHDon></DLHDon><DSCKS><NBan/></DSCKS></HDon>'''


def master(**kw):
    return TaxpayerMaster(**pipe.STAMP, tenant_id='tenant-a', taxpayer_id='payer-a', revision=1, tax_code=fx.BUYER,
                          effective_from=date(2026, 1, 1), provenance_reference='synthetic', **kw)


def fields(**kw):
    return extract(body(**kw).encode(), fx.TODAY).fields


def codes(issues):
    return [i.code for i in issues]


# ------------------------------------------------------------------ pure rules
def test_fold_and_similarity_ignore_case_diacritics_and_punctuation():
    assert fold('CÔNG TY TNHH Đại Phát, (HN)') == 'cong ty tnhh dai phat hn'
    assert similarity('Công ty TNHH Đại Phát', 'CONG TY TNHH DAI PHAT.') == 1.0
    assert similarity('Công ty A', 'Công ty B') < 0.8


def test_buyer_matching_profile_passes_and_reports_missing_profile_fields():
    m = master(legal_name='Công ty B', registered_address='12 Phố X, Hà Nội')
    ok = buyer_profile_issues(fields(buyer_address='12 pho x ha noi'), m, (), date(2026, 3, 1))
    assert codes(ok) == ['XML_CONTEXT_BUYER_CHECKED']
    partial = buyer_profile_issues(fields(), master(legal_name='Công ty B'), (), date(2026, 3, 1))
    assert codes(partial) == ['XML_CONTEXT_BUYER_ADDRESS_UNAVAILABLE']
    none = buyer_profile_issues(fields(), master(), (), date(2026, 3, 1))
    assert set(codes(none)) == {'XML_CONTEXT_BUYER_NAME_UNAVAILABLE', 'XML_CONTEXT_BUYER_ADDRESS_UNAVAILABLE'}


def test_buyer_name_and_address_deviations_are_flagged():
    m = master(legal_name='Công ty B', registered_address='12 Phố X, Hà Nội')
    assert codes(buyer_profile_issues(fields(buyer_name='Công ty Khác', buyer_address='12 Phố X, Hà Nội'), m, (), date(2026, 3, 1))) == ['XML_REVIEW_BUYER_NAME']
    assert codes(buyer_profile_issues(fields(buyer_address='99 Đường Y, Đà Nẵng'), m, (), date(2026, 3, 1))) == ['XML_REVIEW_BUYER_ADDRESS']
    assert codes(buyer_profile_issues(fields(), m, (), date(2026, 3, 1))) == ['XML_REVIEW_BUYER_ADDRESS']  # address missing


def test_buyer_block_with_taxpayer_name_but_other_tax_id_is_flagged():
    other = master(legal_name='Công ty B').model_copy(update={'tax_code': fx._valid_tax_id('050000000')})
    assert codes(buyer_profile_issues(fields(), other, (), date(2026, 3, 1))) == ['XML_REVIEW_BUYER_TAX_ID_MISMATCH']
    unrelated = master(legal_name='Công ty Z').model_copy(update={'tax_code': fx._valid_tax_id('050000000')})
    assert codes(buyer_profile_issues(fields(), unrelated, (), date(2026, 3, 1))) == ['XML_CONTEXT_BUYER_NOT_TAXPAYER']


def test_amount_outlier_uses_robust_scale_and_ratio_fallback():
    spread = [Decimal(x) for x in (100, 110, 95, 105, 102, 98)]
    assert not amount_outlier(spread, Decimal(120))
    assert amount_outlier(spread, Decimal(300))
    flat = [Decimal(100)] * 5
    assert not amount_outlier(flat, Decimal(250))
    assert amount_outlier(flat, Decimal(301))


def _row(number, name='Công ty A', gross='2200000', issued='2026-03-01', series='1K26TAA'):
    return dict(record_id='cfr-' + number, name=name, series=series, number=number, issued=issued, gross=gross)


def test_vendor_rules_on_synthetic_history():
    f = fields(number='00000099')
    # nothing known: nothing can be judged, and the report says so
    first = codes(vendor_and_reference_issues(f, [], []))
    assert 'XML_CONTEXT_VENDOR_FIRST_SEEN' in first and 'XML_CONTEXT_AMOUNT_HISTORY_INSUFFICIENT' in first
    # name changed against earlier invoices of this tax code
    changed = codes(vendor_and_reference_issues(fields(seller_name='Công ty Lạ'), [_row('1')], []))
    assert 'XML_REVIEW_VENDOR_NAME_CHANGED' in changed
    # same name under a different tax code
    assert 'XML_REVIEW_VENDOR_NAME_OTHER_TAX_ID' in codes(vendor_and_reference_issues(f, [_row('1')], ['cong ty a']))
    # enough history and a normal amount
    history = [_row(str(n)) for n in range(1, MIN_HISTORY + 1)]
    assert 'XML_CONTEXT_AMOUNT_HISTORY_SUFFICIENT' in codes(vendor_and_reference_issues(f, history, []))
    # enough history and a 5x amount
    assert 'XML_REVIEW_VENDOR_AMOUNT_OUTLIER' in codes(vendor_and_reference_issues(fields(qty=10), history, []))


def test_related_invoice_reference_rules():
    history = [_row('12')]
    found = vendor_and_reference_issues(fields(related=('1', '1', 'K26TAA', '00000012', '2026-03-01')), history, [])
    assert 'XML_REVIEW_RELATED_FOUND' in codes(found)  # leading zeros do not matter
    missing = vendor_and_reference_issues(fields(related=('2', '1', 'K26TAA', '00000077', '2026-03-01')), history, [])
    assert 'XML_REVIEW_RELATED_NOT_CAPTURED' in codes(missing)
    wrong_date = vendor_and_reference_issues(fields(related=('1', '1', 'K26TAA', '00000012', '2026-02-27')), history, [])
    assert 'XML_CHECK_RELATED_MISMATCH' in codes(wrong_date)


def test_malformed_related_reference_is_an_error():
    for related in (('3', '1', 'K26TAA', '00000012', '2026-03-01'), ('1', '1', 'K26TAA', '00000012', '2026-04-01'),
                    ('1', '1', 'K26TAA', '00000012', 'not-a-date')):
        inv = extract(body(related=related).encode(), fx.TODAY)
        assert 'XML_CHECK_RELATED_INVOICE' in {c.code for c in inv.errors}, related
    assert 'XML_CHECK_RELATED_INVOICE' not in {c.code for c in extract(body().encode(), fx.TODAY).checks}
    ok = extract(body(related=('2', '1', 'K26TAA', '00000012', '2026-02-01')).encode(), fx.TODAY)
    assert 'XML_CHECK_RELATED_INVOICE' not in {c.code for c in ok.errors}


# ------------------------------------------------------------------ through the real pipeline
class ContextPipelineTests(pipe.PipelineBase):
    def groups(self, job):
        return {g['group']: g for g in self.jobs.view(pipe.CTX, 'payer-a', job['record_id'])['check_groups']}

    def quality(self, job):
        return self.jobs.quality.get(pipe.CTX, 'payer-a', job['assessment_id'])

    def test_outlier_after_history_is_flagged_as_review_and_replays(self):
        from src.review.correction_service import CorrectionService
        for n in range(MIN_HISTORY):
            self.run_job(fx.signed_invoice(body(number=f'{100 + n:08d}')), f'hist-{n}')
        _, job = self.run_job(fx.signed_invoice(body(number='00000200', qty=10)), 'big')
        q = self.quality(job)
        warn = {i.code: i.severity for i in q.issues if i.code.startswith('XML_REVIEW_')}
        self.assertEqual(warn, {'XML_REVIEW_VENDOR_AMOUNT_OUTLIER': 'WARNING'})
        self.assertFalse([i for i in q.issues if i.severity == 'ERROR'])  # a deviation to review, not a rejection
        self.assertEqual(self.groups(job)['vendor']['status'], 'REVIEW')
        self.assertEqual(replay(self.jobs.quality.inputs(pipe.CTX, 'payer-a', q.assessment_id), q), q)
        self.assertTrue(CorrectionService(self.settings).rebuild(pipe.CTX, 'payer-a', job['record_id'])['verified'])

    def test_short_history_is_reported_unavailable_not_ok(self):
        _, job = self.run_job(fx.signed_invoice(body()), 'solo')
        vendor = self.groups(job)['vendor']
        self.assertEqual(vendor['status'], 'UNAVAILABLE')
        self.assertIn('XML_CONTEXT_VENDOR_FIRST_SEEN', {i['code'] for i in vendor['items']})

    def test_replacement_links_to_captured_original(self):
        from src.review.correction_service import CorrectionService
        _, original = self.run_job(fx.signed_invoice(body(number='00000012')), 'orig')
        _, repl = self.run_job(fx.signed_invoice(body(number='00000013', related=('1', '1', 'K26TAA', '00000012', '2026-03-01'))), 'repl')
        q = self.quality(repl)
        found = [i for i in q.issues if i.code == 'XML_REVIEW_RELATED_FOUND']
        self.assertEqual(len(found), 1)
        self.assertIn(original['record_id'], found[0].message)
        self.assertEqual(self.groups(repl)['related']['status'], 'REVIEW')
        self.assertEqual(replay(self.jobs.quality.inputs(pipe.CTX, 'payer-a', q.assessment_id), q), q)
        self.assertTrue(CorrectionService(self.settings).rebuild(pipe.CTX, 'payer-a', repl['record_id'])['verified'])
        _, mismatch = self.run_job(fx.signed_invoice(body(number='00000014', related=('2', '1', 'K26TAA', '00000012', '2026-02-20'))), 'mismatch')
        self.assertIn('XML_CHECK_RELATED_MISMATCH', {i.code for i in self.quality(mismatch).issues if i.severity == 'ERROR'})
        self.assertEqual(self.groups(mismatch)['related']['status'], 'FAIL')


class BuyerPipelineTests(pipe.PipelineBase):
    master = master(legal_name='Công ty B', registered_address='12 Phố X, Hà Nội')

    def test_purchase_invoice_buyer_block_is_checked_against_profile(self):
        _, good = self.run_job(fx.signed_invoice(body(buyer_address='12 Phố X, Hà Nội')), 'good')
        view = self.jobs.view(pipe.CTX, 'payer-a', good['record_id'])
        self.assertEqual(view['record']['derived']['invoice_direction']['value'], 'INPUT')
        groups = {g['group']: g for g in view['check_groups']}
        self.assertEqual(groups['buyer']['status'], 'OK')
        _, bad = self.run_job(fx.signed_invoice(body(number='00000013', buyer_name='Công ty Khác', buyer_address='1 Đường Lạ, Huế')), 'bad')
        q = self.jobs.quality.get(pipe.CTX, 'payer-a', bad['assessment_id'])
        self.assertEqual({i.code for i in q.issues if i.code.startswith('XML_REVIEW_BUYER_')}, {'XML_REVIEW_BUYER_NAME', 'XML_REVIEW_BUYER_ADDRESS'})
        self.assertEqual({g['group']: g for g in self.jobs.view(pipe.CTX, 'payer-a', bad['record_id'])['check_groups']}['buyer']['status'], 'REVIEW')
        self.assertEqual(replay(self.jobs.quality.inputs(pipe.CTX, 'payer-a', q.assessment_id), q), q)
