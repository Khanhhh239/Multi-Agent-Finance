"""Question assistant: every domain has a handler and a guide entry, parameters are read only when written, and every
number in an answer equals a direct computation on the same report."""
import json
import re
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from src.assistant import catalog, pipeline, synth
from src.assistant.chat import engine
from src.assistant.chat.handlers import HANDLERS
from src.assistant.chat.params import extract
from src.assistant.chat.router import Router
from src.assistant.report import money

AS_OF = date(2026, 10, 15)


@pytest.fixture(scope='module')
def ws(tmp_path_factory):
    out = tmp_path_factory.mktemp('chat') / 'minhan'
    synth.generate(out, seed=7)
    return out


@pytest.fixture(scope='module')
def ctx(ws):
    rep = pipeline.run(ws, pipeline.DEFAULT_RULESET, AS_OF)
    return engine.ChatContext(ws, pipeline.DEFAULT_RULESET, AS_OF, rep, None)


def ask(ctx, q, domain):
    return engine.answer(q, ctx, domain)


def test_catalog_domains_match_handlers_and_guide():
    cat = catalog.load('chat_domains')
    ids = [d['id'] for d in cat['domains']]
    assert sorted(ids) == sorted(HANDLERS)
    g = engine.guide()
    listed = [d['id'] for grp in g['groups'] for d in grp['domains']]
    assert sorted(listed) == sorted(HANDLERS)
    for d in cat['domains']:
        assert len(d['examples']) >= 3 and d['what'] and d['guide']


def test_params_period_numbers_seller(ctx):
    cat = ctx.catalog
    p = extract('Quý 3 có bao nhiêu thuế có nguy cơ?', ctx.report, cat, AS_OF)
    assert p.period.quarter == 3 and p.period.year
    p = extract('tháng 8/2026 mua vào bao nhiêu', ctx.report, cat, AS_OF)
    assert (p.period.month, p.period.year) == (8, 2026)
    p = extract('Điều kiện khấu trừ là gì?', ctx.report, cat, AS_OF)
    assert p.period.is_all and not p.invoice_numbers and p.seller is None
    p = extract('hóa đơn 4 và 5 thì sao', ctx.report, cat, AS_OF)
    assert p.invoice_numbers == ['4', '5']
    p = extract('mua điện thoại cho giám đốc dùng có được khấu trừ không', ctx.report, cat, AS_OF)
    assert p.seller is None                                    # loose common words never name a seller
    inv = next(i for i in ctx.report.invoices if i.role == 'PURCHASE')
    p = extract(f'người bán {inv.seller_tax_id} có rủi ro gì', ctx.report, cat, AS_OF)
    assert p.seller == inv.seller_tax_id


def test_risk_total_equals_report_totals(ctx):
    a = ask(ctx, 'Có bao nhiêu thuế có nguy cơ bị loại?', 'risk_total')
    assert money(ctx.report.totals['at_risk_vat']) in a['text']
    assert f'{ctx.report.totals["at_risk_invoices"]} hóa đơn' in a['text']


def test_risk_total_by_month_matches_direct_sum(ctx):
    rep = ctx.report
    by_key = {i.key: i for i in rep.invoices}
    month = next(by_key[it.invoice_keys[0]].issue_date for it in rep.items if it.status == 'AT_RISK' and it.invoice_keys)
    per = {}
    for it in rep.items:
        if it.status == 'AT_RISK' and it.invoice_keys and by_key.get(it.invoice_keys[0]) and \
                (by_key[it.invoice_keys[0]].issue_date.year, by_key[it.invoice_keys[0]].issue_date.month) == (month.year, month.month):
            per[it.invoice_keys[0]] = max(per.get(it.invoice_keys[0], Decimal(0)), it.amount)
    a = ask(ctx, f'tháng {month.month}/{month.year} có bao nhiêu thuế có nguy cơ', 'risk_total')
    assert money(sum(per.values(), Decimal(0))) in a['text']
    assert a['understood']['period'].startswith(f'tháng {month.month:02d}/{month.year}')


def test_purchase_and_sales_summary_match_invoices(ctx):
    rep = ctx.report
    buys = [i for i in rep.invoices if i.role == 'PURCHASE' and not i.duplicate_of]
    a = ask(ctx, 'tổng thuế đầu vào', 'purchase_summary')
    assert f'{len(buys)} hóa đơn' in a['text'] and money(sum(i.vat or 0 for i in buys)) in a['text']
    sales = [i for i in rep.invoices if i.role == 'SALE' and not i.duplicate_of]
    a = ask(ctx, 'doanh thu', 'sales_summary')
    if sales:
        assert money(sum(i.net or 0 for i in sales)) in a['text']
    else:
        assert 'Chưa có hóa đơn bán ra' in a['text']


def test_invoice_lookup_and_unknown_number(ctx):
    rep = ctx.report
    it = next(it for it in rep.items if it.status == 'AT_RISK' and it.invoice_keys)
    inv = next(i for i in rep.invoices if i.key == it.invoice_keys[0])
    a = ask(ctx, f'hóa đơn số {int(inv.number)} có vấn đề gì', 'invoice_lookup')
    assert inv.seller_name in a['text'] and money(inv.gross) in a['text']
    a = ask(ctx, 'hóa đơn số 99999999 có vấn đề gì', 'invoice_lookup')
    assert 'Không có hóa đơn số 99999999' in a['text']


def test_by_issue_lists_exactly_the_rule_items(ctx):
    rep = ctx.report
    n = sum(1 for it in rep.items if it.code.startswith('R01') and it.status != 'INFO')
    a = ask(ctx, 'hóa đơn nào chưa có chứng từ chuyển khoản', 'by_issue')
    assert len(a['rows']) == n


def test_what_if_reruns_with_hypothetical_evidence(ctx):
    rep = ctx.report
    it = next(it for it in rep.items if it.code.startswith('R01') and it.status == 'AT_RISK')
    inv = next(i for i in rep.invoices if i.key == it.invoice_keys[0])
    a = ask(ctx, f'nếu bổ sung chứng từ chuyển khoản cho hóa đơn {int(inv.number)} thì còn bao nhiêu', 'what_if_evidence')
    after = pipeline.run(ctx.workspace, ctx.ruleset_path, AS_OF, {inv.key: dict(invoice_key=inv.key, action='PAYMENT_EVIDENCE_ATTACHED',
                                                                                evidence='x', by='y')}).totals['at_risk_vat']
    assert money(after) in a['text'] and 'không ghi vào dữ liệu' in a['text']


def test_deadlines_and_penalty_and_data_status(ctx):
    a = ask(ctx, 'hạn nộp tờ khai', 'deadlines')
    assert a['rows'] and 'Hạn gần nhất' in a['text']
    a = ask(ctx, 'nếu bị phát hiện thì phạt bao nhiêu', 'penalty_exposure')
    assert 'phạt thêm tối đa' in a['text'] or 'không có khoản nào' in a['text']
    a = ask(ctx, 'đã nạp những dữ liệu gì', 'data_status')
    assert f'{ctx.report.meta["counts"]["purchase_invoices"]} hóa đơn mua vào' in a['text']


def test_every_handler_runs_without_error(ctx):
    for d in HANDLERS:
        if d in ('law_question', 'law_updates', 'judgment'):
            continue
        a = ask(ctx, 'câu hỏi thử', d)
        assert a['text'] and a['domain'] in (d, None)


def test_law_domains_without_corpus_say_so(ctx):
    assert 'Chưa có kho luật' in ask(ctx, 'điều kiện khấu trừ', 'law_question')['text']
    a = ask(ctx, 'chi tiếp khách có được trừ không', 'judgment')
    assert 'không kết luận' in a['text']


def test_suggestions_come_from_the_data(ctx):
    s = engine.suggestions(ctx)
    known = {str(int(i.number)) for i in ctx.report.invoices if i.number}
    nums = [n for x in s for n in re.findall(r'hóa đơn số (\d+)', x)]
    assert s and all(n in known for n in nums)          # a suggested invoice number is always one of this enterprise's


class FakeEmbed:
    """Bag-of-words vectors: enough to check the router's mechanics without the embedding server."""

    def __init__(self):
        self.vocab = {}

    def __call__(self, texts):
        from src.extraction.xml_context import fold
        rows = []
        for t in texts:
            v = np.zeros(4096, dtype=np.float32)
            for w in fold(t).split():
                v[hash(w) % 4096] += 1
            rows.append(v / max(np.linalg.norm(v), 1e-9))
        return np.vstack(rows)


class NoneLLM:
    def chat(self, system, user, schema, num_predict=30):
        return json.dumps({'domain': 'NONE'}), {}


def test_router_refuses_when_unclear_and_uses_structure(ctx, tmp_path):
    r = Router(embed=FakeEmbed(), llm=NoneLLM(), index_path=tmp_path / 'idx.npz')
    route = r.route('viết một bài thơ về mùa thu', extract('viết một bài thơ về mùa thu', ctx.report, ctx.catalog, AS_OF))
    assert route.domain is None and route.method == 'REFUSED'
    inv = next(i for i in ctx.report.invoices if i.number)
    q = f'nếu có ủy nhiệm chi cho hóa đơn {int(inv.number)} thì sao'
    assert r.route(q, extract(q, ctx.report, ctx.catalog, AS_OF)).domain == 'what_if_evidence'


def test_catalog_save_validates_and_records_history(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, 'DIR', tmp_path)
    monkeypatch.setattr(catalog, 'HISTORY', tmp_path / 'hist.json')
    src = catalog.PROJECT / 'configs/assistant/catalog'
    for n in catalog.NAMES:
        (tmp_path / f'{n}.json').write_text((src / f'{n}.json').read_text(encoding='utf-8'), encoding='utf-8')
    catalog._cache.clear()
    d = catalog.load('ai_categories')
    with pytest.raises(catalog.CatalogError):
        catalog.save('ai_categories', dict(d, categories=[c for c in d['categories'] if c['id'] != 'CA_NHAN']), 'kt')
    d2 = dict(d, categories=d['categories'] + [dict(id='THIET_BI_Y_TE', description='máy móc, vật tư y tế')])
    out = catalog.save('ai_categories', d2, 'kế toán trưởng')
    assert 'THIET_BI_Y_TE' in catalog.ai_categories()
    assert catalog.history('ai_categories')[0]['summary']['added'] == ['THIET_BI_Y_TE'] and out['version']
    h = catalog.load('holidays')
    with pytest.raises(catalog.CatalogError):
        catalog.save('holidays', dict(h, years={'2027': [dict(date='2026-01-05', name='sai năm')]}), 'kt')
    catalog._cache.clear()


def test_everyday_words_do_not_name_a_seller(ctx):
    # "chưa có" folds to "chua co", the same as "Sửa chữa Cơ khí ..." in the demo's seller list
    p = extract('Quý 3 có những hóa đơn nào chưa có chứng từ chuyển khoản?', ctx.report, ctx.catalog, AS_OF)
    assert p.seller is None
    inv = next(i for i in ctx.report.invoices if i.role == 'PURCHASE' and 'An Phú' in (i.seller_name or ''))
    p = extract('Nhà cung cấp An Phú có rủi ro gì?', ctx.report, ctx.catalog, AS_OF)
    assert p.seller == inv.seller_tax_id
