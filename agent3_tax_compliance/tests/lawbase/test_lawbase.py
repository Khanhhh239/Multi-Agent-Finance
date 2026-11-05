"""Legal corpus: page parsing, no-loss chunking, polite fetching, dated retrieval with version merging, grounded answers."""
import json
from datetime import date

import pytest

from src.lawbase import rag
from src.lawbase.fetch import FetchError, PoliteFetcher
from src.lawbase.llm import ContextOverflow, LLMUnavailable, Ollama
from src.lawbase.store import Corpus
from src.lawbase.vbpl import coverage_errors, in_scope, parse_page, parse_sitemap


def page(doc_id, num, title, dtype, eff_from, eff_to, status, body, issue='2025-12-10'):
    doc = {'id': doc_id, 'docType': {'name': dtype, 'code': 'X'}, 'docGroup': 'VBQPPL', 'docNum': num, 'title': title,
           'issueDate': f'{issue}T00:00:00', 'effFrom': f'{eff_from}T00:00:00' if eff_from else None,
           'effTo': f'{eff_to}T00:00:00' if eff_to else None, 'effStatus': {'name': status, 'code': 'S'},
           'documentContentFileName': 'x.pdf'}
    flight = '"initialDoc":' + json.dumps(doc, ensure_ascii=False) + ',"documentContent":{"content":"' + body + '"}'
    return '<html><script>self.__next_f.push([1,' + json.dumps(flight, ensure_ascii=False) + '])</script></html>'


def p(cls, pid, text, order='class-first'):
    return f'<p class="{cls}" id="{pid}">{text}</p>' if order == 'class-first' else f'<p id="{pid}" class="{cls}">{text}</p>'


LAW = ''.join([
    p('prov-chapter', 'c1', 'Chương I. QUY ĐỊNH CHUNG'),
    p('prov-article', 'a1', '<strong>Điều 1. Phạm vi điều chỉnh</strong>', 'id-first'),
    p('prov-content', 'x1', 'Luật này quy định về quản lý thuế.'),
    p('prov-article', 'a2', 'Điều 2. Xử lý chậm nộp'),
    p('prov-clause', 'k1', '1. Các trường hợp phải nộp tiền chậm nộp bao gồm:'),
    p('prov-item', 'i1', 'a) Chậm nộp so với thời hạn;'),
    p('prov-item', 'i2', 'b) Khai bổ sung làm tăng số thuế.'),
    p('prov-clause', 'k2', '2. Mức tính tiền chậm nộp bằng 0,03%/ngày tính trên số tiền thuế chậm nộp.'),
])


@pytest.fixture
def law_html():
    return page('187043', '108/2025/QH15', 'Luật Quản lý thuế', 'Luật', '2026-07-01', None, 'Còn hiệu lực', LAW)


def test_metadata_and_provision_tree_with_any_attribute_order(law_html):
    d = parse_page('https://vbpl.vn/van-ban/chi-tiet/x', law_html)
    assert d.meta['doc_num'] == '108/2025/QH15' and d.meta['eff_from'] == '2026-07-01' and d.meta['status_name'] == 'Còn hiệu lực'
    assert d.structure == 'marked' and d.notes == []
    labels = [(x.level, x.label) for x in d.provisions]
    assert labels == [(1, 'Chương I'), (3, 'Điều 1'), (3, 'Điều 2'), (4, 'Khoản 1'), (5, 'Điểm a'), (5, 'Điểm b'), (4, 'Khoản 2')]
    assert 'quy định về quản lý thuế' in d.provisions[1].text          # content paragraph attached to its article


def test_unmarked_pages_get_an_inferred_tree_and_attachment_only_pages_are_flagged():
    body = ''.join(f'<p>{t}</p>' for t in ['Điều 1. Sửa đổi', '1. Sửa khoản 2 như sau:', 'a) nội dung một;', 'Điều 2. Hiệu lực', 'Nghị định có hiệu lực.'])
    d = parse_page('u', page('1', '9/2025/NĐ-CP', 't', 'Nghị định', None, None, 'Còn hiệu lực', body))
    assert d.structure == 'heuristic' and [x.label for x in d.provisions] == ['Điều 1', 'Khoản 1', 'Điểm a', 'Điều 2']
    empty = parse_page('u', page('2', '10/VBHN-BTC', 't', 'Văn bản hợp nhất', None, None, None, '<html><body></body></html>'))
    assert empty.structure == 'none' and empty.provisions == [] and 'chưa nạp' in empty.notes[0]


def test_chunks_never_lose_or_truncate_text(law_html):
    long_clause = '1. ' + ' '.join(f'Câu thứ {n} của khoản rất dài về thuế giá trị gia tăng.' for n in range(400))
    body = p('prov-article', 'a', 'Điều 5. Khấu trừ') + p('prov-clause', 'k', long_clause) + p('prov-item', 'i', 'a) ' + 'x' * 3000)
    d = parse_page('u', page('3', '1/2026/TT-BTC', 't', 'Thông tư', '2026-01-01', None, 'Còn hiệu lực', body))
    assert coverage_errors(d) == []
    assert coverage_errors(parse_page('u', law_html)) == []


def test_scope_selection():
    scope = json.load(open('configs/lawbase/scope.json', encoding='utf-8'))
    base = 'https://vbpl.vn/van-ban/chi-tiet/'
    assert in_scope(base + 'luat-quan-ly-thue-so-108-2025-qh15--187043', scope) == (True, True)
    assert in_scope(base + 'thong-tu-so-80-2019-tt-btc-huong-dan-thu-tuc-hai-quan-quan-ly-thue--1', scope)[0] is False
    assert in_scope(base + 'thong-tu-so-35-2011-tt-btc-huong-dan-thue-gia-tri-gia-tang--2', scope)[0] is False   # before min_year
    sm = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://vbpl.vn/van-ban/chi-tiet/a</loc><lastmod>2026-11-04</lastmod></url></urlset>'
    assert parse_sitemap(sm) == [('https://vbpl.vn/van-ban/chi-tiet/a', '2026-11-04')]


def test_fetcher_honours_robots_and_caches(tmp_path):
    calls = []

    def opener(url):
        calls.append(url)
        return b'User-Agent: *\nDisallow: /api/\n' if url.endswith('robots.txt') else b'<html>ok</html>'
    f = PoliteFetcher('test-agent', 0, tmp_path, opener=opener)
    assert f.get('https://vbpl.vn/van-ban/chi-tiet/a') == b'<html>ok</html>'
    assert f.get('https://vbpl.vn/van-ban/chi-tiet/a') == b'<html>ok</html>' and calls.count('https://vbpl.vn/van-ban/chi-tiet/a') == 1
    with pytest.raises(FetchError):
        f.get('https://vbpl.vn/api/document/1')


@pytest.fixture
def corpus(tmp_path, law_html):
    c = Corpus(tmp_path / 'c.sqlite3')
    c.upsert(parse_page('https://vbpl.vn/van-ban/chi-tiet/luat', law_html), 'luat', '2026-11-01', 'h1', True, True)
    old = page('99', '38/2019/QH14', 'Luật cũ', 'Luật', '2020-07-01', '2026-07-01', 'Hết hiệu lực toàn bộ',
               p('prov-article', 'o1', 'Điều 2. Xử lý chậm nộp') + p('prov-clause', 'o2', '2. Mức tính tiền chậm nộp bằng 0,03%/ngày (bản cũ).'), '2019-06-13')
    c.upsert(parse_page('https://vbpl.vn/van-ban/chi-tiet/old', old), 'old', '2026-11-01', 'h2', False, True)
    hn = page('77', '12/VBHN-VPQH', 'Hợp nhất Luật Quản lý thuế', 'Văn bản hợp nhất', None, None, None,
              p('prov-article', 'h1', 'Điều 2. Xử lý chậm nộp') + p('prov-clause', 'h2', '2. Mức tính tiền chậm nộp bằng 0,03%/ngày tính trên số tiền thuế chậm nộp.'),
              '2026-08-01')
    c.upsert(parse_page('https://vbpl.vn/van-ban/chi-tiet/hn', hn), 'hn', '2026-11-01', 'h3', False, True)
    c.db.commit()
    yield c
    c.close()


def test_retrieval_filters_by_date_and_merges_versions(corpus):
    now = corpus.search('mức tính tiền chậm nộp mỗi ngày', date(2026, 11, 5), 5)
    assert all(r['doc_num'] != '38/2019/QH14' for r in now)             # expired on 01/7/2026
    same = [r for r in now if 'Khoản 2' in r['path']]
    assert len(same) == 1 and same[0]['doc_num'] == '12/VBHN-VPQH'      # newest version of the identical clause kept
    before = corpus.search('mức tính tiền chậm nộp mỗi ngày', date(2025, 1, 1), 5)
    assert before and before[0]['doc_num'] == '38/2019/QH14'            # historical question uses the law then in force


def test_change_detection_and_rereview(corpus, law_html):
    corpus.db.execute("UPDATE documents SET review_status='REVIEWED' WHERE doc_num='108/2025/QH15'")
    changed = law_html.replace('0,03%/ngày', '0,05%/ngày')
    ch = corpus.upsert(parse_page('https://vbpl.vn/van-ban/chi-tiet/luat', changed), 'luat', '2026-11-05', 'h9', True, True)
    assert ('TEXT', '1 đoạn đổi, 0 thêm, 0 bỏ') in ch
    assert corpus.db.execute("SELECT review_status FROM documents WHERE doc_num='108/2025/QH15'").fetchone()[0] == 'NEEDS_REREVIEW'


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def chat(self, system, user, schema=None, num_predict=900):
        assert '[P1]' in user and 'Câu hỏi:' in user
        return json.dumps(self.payload, ensure_ascii=False), dict(prompt_tokens=100)


def test_grounded_answer_keeps_only_checked_sentences(corpus):
    good = dict(text='Mức tính tiền chậm nộp là 0,03%/ngày.', sources=['P1'], quote='Mức tính tiền chậm nộp bằng 0,03%/ngày')
    bad_quote = dict(text='Mức phạt là 0,03%/ngày.', sources=['P1'], quote='mức phạt bằng 0,03%')
    bad_number = dict(text='Mức tính là 0,05%/ngày.', sources=['P1'], quote='Mức tính tiền chậm nộp bằng 0,03%/ngày')
    bad_source = dict(text='Theo đoạn khác.', sources=['P9'], quote='x')
    r = rag.answer(corpus, 'Mức tính tiền chậm nộp mỗi ngày là bao nhiêu?', date(2026, 11, 5),
                   FakeLLM(dict(abstain=False, answer=[good, bad_quote, bad_number, bad_source])))
    assert r.mode == 'LLM_VERIFIED' and [s['text'] for s in r.sentences] == [good['text']]
    assert sorted(d['reason'][:12] for d in r.dropped) == sorted(['trích dẫn kh', 'số không có ', 'mã đoạn khôn'])
    assert r.sentences[0]['citations'][0]['url'].startswith('https://vbpl.vn/')


def test_fallbacks_extractive_and_abstain(corpus):
    r = rag.answer(corpus, 'Mức tính tiền chậm nộp mỗi ngày là bao nhiêu?', date(2026, 11, 5),
                   FakeLLM(dict(abstain=False, answer=[dict(text='Sai 9%.', sources=['P1'], quote='không có')])))
    assert r.mode == 'EXTRACTIVE' and '0,03%' in r.sentences[0]['text']
    off = rag.answer(corpus, 'Thuế nhập khẩu ô tô nguyên chiếc bao nhiêu?', date(2026, 11, 5), FakeLLM(dict(abstain=False, answer=[])))
    assert off.mode == 'ABSTAIN'

    class Down:
        def chat(self, *a, **k):
            raise LLMUnavailable('down')
    r2 = rag.answer(corpus, 'Mức tính tiền chậm nộp mỗi ngày là bao nhiêu?', date(2026, 11, 5), Down())
    assert r2.mode == 'EXTRACTIVE' and 'Không dùng được mô hình' in r2.note


def test_context_overflow_is_refused_before_calling_the_model():
    with pytest.raises(ContextOverflow):
        Ollama(num_ctx=1024).chat('x' * 3000, 'y' * 3000)


def test_verifier_recites_the_right_passage_and_refuses_off_topic_answers():
    import json as _j
    from src.lawbase.rag import Passage, verify
    p1 = Passage('P1', '398/2026/NĐ-CP', 'Nghị định', 'Nghị định 398/2026/NĐ-CP > Điều 2', 'u', None, None, 'Giảm 30% số thuế thu nhập cá nhân phải nộp.')
    p2 = Passage('P2', '141/2026/NĐ-CP', 'Nghị định', 'Nghị định 141/2026/NĐ-CP > Điều 1', 'u', None, None,
                 'Sửa đổi cụm từ “500 triệu đồng” thành “01 tỷ đồng” đối với hộ kinh doanh, cá nhân kinh doanh có doanh thu.')
    raw = _j.dumps(dict(answer=[dict(text='Ngưỡng doanh thu hộ kinh doanh được sửa thành 01 tỷ đồng.', sources=['P1'],
                                      quote='thành “01 tỷ đồng” đối với hộ kinh doanh')]))
    kept, dropped, _, _ = verify(raw, [p1, p2], 'Nghị định 141/2026 sửa ngưỡng doanh thu của hộ kinh doanh thành bao nhiêu?')
    assert kept and kept[0]['sources'] == ['P2'] and not dropped
    p3 = Passage('P3', '67/2025/QH15', 'Luật', 'Luật 67/2025/QH15 > Điều 10', 'u', None, None, 'Thuế suất ưu đãi 0% áp dụng cho dự án đặc biệt.')
    raw = _j.dumps(dict(answer=[dict(text='Thuế suất là 0%.', sources=['P3'], quote='Thuế suất ưu đãi 0%')]))
    kept, dropped, _, _ = verify(raw, [p3], 'Thuế suất thuế nhập khẩu ưu đãi đặc biệt đối với xe ô tô nguyên chiếc là bao nhiêu?')
    assert not kept and 'chủ đề' in dropped[0]['reason']


def test_verifier_regrounds_a_true_claim_on_the_sentence_that_supports_it():
    import json as _j
    from src.lawbase.rag import Passage, verify
    p1 = Passage('P1', '398/2026/NĐ-CP', 'Nghị định', 'Nghị định 398/2026/NĐ-CP > Điều 3', 'u', None, None,
                 'Doanh thu năm làm căn cứ thực hiện theo Nghị định số 68/2026/NĐ-CP được sửa đổi bởi Nghị định số 141/2026/NĐ-CP.')
    p2 = Passage('P2', '141/2026/NĐ-CP', 'Nghị định', 'Nghị định 141/2026/NĐ-CP > Điều 1', 'u', None, None,
                 'Sửa đổi, bổ sung Nghị định 68/2026: 1. Sửa đổi cụm từ “500 triệu đồng” thành “01 tỷ đồng” đối với ngưỡng doanh thu của hộ kinh doanh.')
    raw = _j.dumps(dict(answer=[dict(text='Nghị định 141/2026 sửa ngưỡng doanh thu hộ kinh doanh thành 01 tỷ đồng.', sources=['P1'],
                                      quote='Doanh thu năm làm căn cứ thực hiện theo Nghị định số 68/2026/NĐ-CP')]))
    kept, dropped, _, _ = verify(raw, [p1, p2], 'Nghị định 141/2026 sửa ngưỡng doanh thu của hộ kinh doanh thành bao nhiêu?')
    assert kept and kept[0]['sources'] == ['P2'] and '01 tỷ đồng' in kept[0]['quote']
    raw = _j.dumps(dict(answer=[dict(text='Ngưỡng mới là 02 tỷ đồng.', sources=['P1'], quote='Doanh thu năm làm căn cứ')]))
    kept, dropped, _, _ = verify(raw, [p1, p2], 'Nghị định 141/2026 sửa ngưỡng doanh thu của hộ kinh doanh thành bao nhiêu?')
    assert not kept                                             # a number no passage supports is never regrounded


def test_verifier_drops_a_sentence_that_only_repeats_the_question():
    import json as _j
    from src.lawbase.rag import Passage, verify
    p = Passage('P1', '252/2026/NĐ-CP', 'Nghị định', 'Nghị định 252/2026/NĐ-CP > Điều 24 > Khoản 2', 'u', None, None,
                'Thời hạn tạm nộp quý chậm nhất là ngày cuối cùng của tháng đầu của quý tiếp theo quý phát sinh nghĩa vụ thuế.')
    q = 'Thời hạn tạm nộp thuế thu nhập doanh nghiệp theo quý là khi nào?'
    raw = _j.dumps(dict(answer=[dict(text=q, sources=['P1'], quote='Thời hạn tạm nộp quý chậm nhất'),
                                 dict(text='Chậm nhất là ngày cuối cùng của tháng đầu của quý tiếp theo.', sources=['P1'], quote='ngày cuối cùng của tháng đầu của quý tiếp theo')]))
    kept, dropped, _, _ = verify(raw, [p], q)
    assert [k['text'] for k in kept] == ['Chậm nhất là ngày cuối cùng của tháng đầu của quý tiếp theo.'] and 'lặp lại' in dropped[0]['reason']
